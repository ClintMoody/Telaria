"""Regression tests for the adversarial-review findings (critical + high).

Each test reproduces a confirmed vulnerability from the hostile bug hunt and asserts it is
now closed. These are the tests the original 267-test suite was missing.
"""

from __future__ import annotations

import json
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
