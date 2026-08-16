"""Regression tests for the adversarial-review findings (critical + high).

Each test reproduces a confirmed vulnerability from the hostile bug hunt and asserts it is
now closed. These are the tests the original 267-test suite was missing.
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine import vault as vault_mod  # noqa: E402
from talaria.engine.apply import ApplyOptions, apply_bundle  # noqa: E402
from talaria.engine.bundle import BundleReader, MANIFEST_NAME, STUB_NAME  # noqa: E402
from talaria.engine.pack import PackOptions, pack  # noqa: E402
from talaria.engine.scan import scan  # noqa: E402
from talaria.errors import Refusal  # noqa: E402


pytestmark = pytest.mark.skipif(not vault_mod.crypto_available(),
                                reason="cryptography needed for vault regression tests")


def _forge_vault_bundle(tmp_path: Path, hostile_root_rel: str) -> Path:
    """Build a valid, correctly-MAC'd vault bundle whose member targets ``hostile_root_rel``.

    Models the real threat: the attacker owns the passphrase they share, so a section MAC
    is no defense — they sign their own hostile manifest.
    """
    inst = build_fake_install(tmp_path / "src", FakeInstallSpec())
    result = scan(inst.home)
    good = tmp_path / "good.hermespack"
    pres = pack(result, good, PackOptions(vault_passphrase="pw"))

    manifest = pres.manifest
    # Point the first vault member at the hostile destination and re-sign the section.
    manifest = json.loads(json.dumps(manifest))
    manifest["vault"]["members"][0]["root_rel"] = hostile_root_rel
    manifest["vault"]["members"][0]["home_rel"] = hostile_root_rel
    salt = bytes.fromhex(manifest["vault"]["kdf"]["salt"])
    _enc, mac_key = vault_mod._derive_keys("pw", salt)
    manifest["vault"]["mac"] = vault_mod._section_mac(manifest["vault"], mac_key)

    hostile = tmp_path / "hostile.hermespack"
    with zipfile.ZipFile(good) as zin, zipfile.ZipFile(hostile, "w") as zout:
        for item in zin.infolist():
            if item.filename in (MANIFEST_NAME, STUB_NAME):
                continue
            zout.writestr(item, zin.read(item.filename))
        zout.writestr(STUB_NAME, json.dumps({k: manifest[k] for k in
                      ("schema_version", "min_reader_tool_version",
                       "created_by_tool_version", "created_at", "source")}))
        zout.writestr(MANIFEST_NAME, json.dumps(manifest))
    return hostile


class TestRollbackDbIntegrity:
    """Finding #3/#6/#9: rollback must restore the target DB's committed WAL data."""

    def test_wal_data_survives_rollback(self, tmp_path, monkeypatch):
        import sqlite3

        from talaria.engine import apply as apply_mod

        inst = build_fake_install(tmp_path / "src", FakeInstallSpec())
        result = scan(inst.home)
        bundle = tmp_path / "b.hermespack"
        pack(result, bundle, PackOptions())

        # Target has a state.db with un-checkpointed WAL frames (a crashed gateway).
        target = tmp_path / "target" / ".hermes"
        target.mkdir(parents=True)
        db = target / "state.db"
        conn = sqlite3.connect(db)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE sessions (session_key TEXT PRIMARY KEY, cwd TEXT,"
                     " git_branch TEXT, git_repo_root TEXT, created_at TEXT)")
        conn.execute("INSERT INTO sessions VALUES ('pre','/precious','m','/p','t')")
        conn.commit()   # committed but left in WAL — keep the connection open
        assert (target / "state.db-wal").exists()
        conn2 = sqlite3.connect(db)  # second handle keeps WAL uncheckpointed
        conn.close()

        # Force a verify failure so apply rolls back after mutating.
        monkeypatch.setattr(apply_mod, "_verify_gating",
                            lambda *a, **k: (_ for _ in ()).throw(
                                apply_mod.TalariaError("TAL-602", "forced")))
        outcome = apply_bundle(bundle, target, ApplyOptions(consent_executable=True,
                                                            conflict_policy="overwrite"))
        conn2.close()
        assert outcome.status == "rolled_back"
        # The pre-apply committed row must still be readable after rollback.
        check = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        rows = check.execute("SELECT cwd FROM sessions WHERE session_key='pre'").fetchall()
        check.close()
        assert rows == [("/precious",)], "committed WAL data lost across rollback"

    def test_crashed_inflight_op_rolled_back(self, tmp_path, monkeypatch):
        """An op that fsynced op.intent but crashed before op.done must still revert."""
        from talaria.engine import apply as apply_mod
        from talaria.hashes import file_sha256

        inst = build_fake_install(tmp_path / "src", FakeInstallSpec())
        result = scan(inst.home)
        bundle = tmp_path / "b.hermespack"
        pack(result, bundle, PackOptions())

        target = tmp_path / "target" / ".hermes"
        (target / "cron").mkdir(parents=True)
        (target / "SOUL.md").write_text("ORIGINAL soul\n")
        before = file_sha256(target / "SOUL.md")

        calls = {"n": 0}
        real_place = apply_mod._place_file

        def crash_after_partial(staged, final):
            calls["n"] += 1
            if "SOUL.md" in str(final):
                # Simulate a crash AFTER the target file was mutated but before op.done:
                # write the new content, then raise as if killed.
                real_place(staged, final)
                raise KeyboardInterrupt("killed right after replace")
            real_place(staged, final)

        monkeypatch.setattr(apply_mod, "_place_file", crash_after_partial)
        outcome = apply_bundle(bundle, target, ApplyOptions(consent_executable=True,
                                                            conflict_policy="overwrite"))
        monkeypatch.setattr(apply_mod, "_place_file", real_place)
        assert outcome.status == "rolled_back"
        # The half-applied SOUL.md must be restored to its original content.
        assert file_sha256(target / "SOUL.md") == before, \
            "crashed in-flight op was not rolled back"


class TestExternalStateBundle:
    """Finding #2/#4: memory-provider external state must not make bundles unappliable."""

    def _install_with_external(self, tmp_path, fake_home):
        import os

        os.environ["HOME"] = str(fake_home)
        fake_home.mkdir(parents=True, exist_ok=True)
        honcho = fake_home / ".honcho"
        honcho.mkdir()
        (honcho / "state.json").write_text('{"session": "abc"}')
        inst = build_fake_install(fake_home / ".hermes", FakeInstallSpec())
        # Point the config at the honcho memory provider.
        cfg = (inst.home / "config.yaml").read_text()
        cfg = cfg.replace("memory:\n  memory_enabled: true\n  provider: null",
                          "memory:\n  memory_enabled: true\n  provider: honcho")
        (inst.home / "config.yaml").write_text(cfg)
        return inst

    def test_external_bundle_is_valid_and_applies(self, tmp_path, monkeypatch):
        real_home = os.environ.get("HOME")
        try:
            fake_home = tmp_path / "userhome"
            inst = self._install_with_external(tmp_path, fake_home)
            result = scan(inst.home)
            # The external dir must have been discovered as a machine ref.
            assert any(r.ref_kind == "external-dir" and "honcho" in r.value
                       for r in result.machine_refs)
            bundle = tmp_path / "ext.hermespack"
            pres = pack(result, bundle, PackOptions())
            # The external member is now IN the manifest (was the bug).
            ext_arts = [a for a in pres.manifest["artifacts"]
                        if a["kind"] == "external-state" and a["files"]]
            assert ext_arts, "external-state artifact missing from manifest"

            # verify_structure must pass (previously: 'zip member not in manifest').
            with BundleReader(bundle) as reader:
                assert reader.verify_structure() == []

            # Apply lands the external file under the (fake) home, with consent.
            target_home = fake_home / ".hermes-target"
            outcome = apply_bundle(bundle, target_home,
                                   ApplyOptions(consent_executable=True,
                                                consent_external=True))
            assert outcome.status == "committed"
            assert (fake_home / ".honcho" / "state.json").exists()
        finally:
            if real_home:
                os.environ["HOME"] = real_home


class TestVaultArbitraryWrite:
    """Finding #1/#5: vault member root_rel must not escape HERMES_HOME."""

    def test_traversal_root_rel_refused_before_write(self, tmp_path):
        hostile = _forge_vault_bundle(tmp_path, "../OUTSIDE/pwned.bashrc")
        target = tmp_path / "target" / ".hermes"
        target.mkdir(parents=True)
        sentinel = tmp_path / "target" / "OUTSIDE"
        with pytest.raises(Refusal) as exc_info:
            apply_bundle(hostile, target,
                         ApplyOptions(vault_passphrase="pw", consent_executable=True))
        assert exc_info.value.code == "TAL-303"
        assert not sentinel.exists(), "traversal write must never happen"

    def test_absolute_root_rel_refused(self, tmp_path):
        evil = tmp_path / "evil-abs.txt"
        hostile = _forge_vault_bundle(tmp_path, str(evil))
        target = tmp_path / "t2" / ".hermes"
        target.mkdir(parents=True)
        with pytest.raises(Refusal) as exc_info:
            apply_bundle(hostile, target,
                         ApplyOptions(vault_passphrase="pw", consent_executable=True))
        assert exc_info.value.code == "TAL-303"
        assert not evil.exists()

    def test_verify_structure_flags_hostile_vault_root_rel(self, tmp_path):
        hostile = _forge_vault_bundle(tmp_path, "../../etc/cron.d/x")
        with BundleReader(hostile) as reader:
            problems = reader.verify_structure()
        assert any("vault member root_rel" in p for p in problems)

    def test_wrong_passphrase_clean_refusal_not_rollback(self, tmp_path):
        """Finding #10 / A4: wrong passphrase on apply = clean refuse (exit 3), zero writes."""
        inst = build_fake_install(tmp_path / "src", FakeInstallSpec())
        result = scan(inst.home)
        good = tmp_path / "good.hermespack"
        pack(result, good, PackOptions(vault_passphrase="right"))
        target = tmp_path / "target" / ".hermes"
        with pytest.raises(Refusal) as exc_info:
            apply_bundle(good, target,
                         ApplyOptions(vault_passphrase="wrong",
                                      consent_executable=True))
        assert exc_info.value.code == "TAL-305"
        assert exc_info.value.exit_code == 3          # refused, NOT 5 (rolled back)
        assert not (target / ".env").exists()          # zero partial writes
        assert not (target / "SOUL.md").exists()
        # No orphan transaction left behind.
        assert not (target / ".talaria" / "txn").exists() or \
            not any((target / ".talaria" / "txn").iterdir())

    def test_legitimate_vault_still_applies(self, tmp_path):
        """The fix must not break honest vaults."""
        inst = build_fake_install(tmp_path / "src", FakeInstallSpec())
        result = scan(inst.home)
        good = tmp_path / "good.hermespack"
        pack(result, good, PackOptions(vault_passphrase="pw"))
        target = tmp_path / "target" / ".hermes"
        outcome = apply_bundle(good, target,
                               ApplyOptions(vault_passphrase="pw",
                                            consent_executable=True))
        assert outcome.status == "committed"
        assert (target / ".env").exists()  # credentials restored from the vault
        assert "OPENROUTER_API_KEY" in (target / ".env").read_text()
