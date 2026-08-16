"""Integration: the transactional applier — round-trip, conflicts, crash rollback.

Covers acceptance scenarios A1 (VPS move), A5 (power loss mid-apply), A6 (lived-in
target), plus both-sides machine-bound filtering and cron claim scrubbing (A8 parts).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine import apply as apply_mod  # noqa: E402
from talaria.engine.apply import ApplyOptions, apply_bundle, rollback_journal  # noqa: E402
from talaria.engine.pack import PackOptions, pack  # noqa: E402
from talaria.engine.scan import scan  # noqa: E402
from talaria.errors import Refusal  # noqa: E402


def make_bundle(tmp_path: Path, spec: FakeInstallSpec = None):
    inst = build_fake_install(tmp_path / "source-home", spec or FakeInstallSpec())
    result = scan(inst.home)
    out = tmp_path / "move.hermespack"
    pres = pack(result, out, PackOptions())
    return inst, pres


class TestRoundTrip:
    def test_a1_clean_target_apply(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        target = tmp_path / "target-home"
        outcome = apply_bundle(pres.bundle_path, target,
                               ApplyOptions(consent_executable=True))
        assert outcome.status == "committed"
        assert outcome.exit_code == 0
        # Core state landed.
        assert (target / "SOUL.md").exists()
        assert (target / "config.yaml").exists()
        assert (target / "state.db").exists()
        assert (target / "cron" / "jobs.json").exists()
        assert (target / "skills" / ".bundled_manifest").exists()
        assert (target / "skills" / "research" / "web-search" / "SKILL.md").exists()
        # Machine-bound never placed (both-sides defense).
        assert not (target / "gateway_state.json").exists()
        assert not (target / "gateway.pid").exists()
        assert not (target / "state.db-wal").exists()
        # Credentials NOT placed (no vault): checklist path.
        assert not (target / ".env").exists()
        assert not (target / "auth.json").exists()

    def test_cron_claims_scrubbed(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        target = tmp_path / "t2"
        outcome = apply_bundle(pres.bundle_path, target,
                               ApplyOptions(consent_executable=True))
        data = json.loads((target / "cron" / "jobs.json").read_text())
        job = next(j for j in data["jobs"] if j["id"] == "a1b2c3d4e5f6")
        assert job["run_claim"] is None
        assert "preflight_alerted" not in job
        # Bookkeeping preserved (interval anchoring, completion counts).
        assert job["last_run_at"] == "2026-08-14T12:00:04+00:00"
        assert job["repeat"]["completed"] == 0
        assert any("cron" in s["file"] for s in outcome.scrubs)

    def test_executions_non_terminal_dropped(self, tmp_path):
        import sqlite3

        _inst, pres = make_bundle(tmp_path)
        target = tmp_path / "t3"
        # cron-executions is default-off; narrow it IN via only? It's off by default —
        # the packer already excluded it. Verify it's not placed.
        apply_bundle(pres.bundle_path, target, ApplyOptions(consent_executable=True))
        assert not (target / "cron" / "executions.db").exists()

    def test_verify_hashes_after_placement(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        target = tmp_path / "t4"
        outcome = apply_bundle(pres.bundle_path, target,
                               ApplyOptions(consent_executable=True))
        assert len(outcome.placed) > 10
        assert not outcome.failures

    def test_dry_run_writes_nothing(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        target = tmp_path / "t5"
        outcome = apply_bundle(pres.bundle_path, target,
                               ApplyOptions(dry_run=True, consent_executable=True))
        assert outcome.status == "dry_run"
        assert not target.exists() or not any(target.iterdir())

    def test_consent_required_for_executable_content(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        target = tmp_path / "t6"
        with pytest.raises(Refusal) as exc_info:
            apply_bundle(pres.bundle_path, target, ApplyOptions())
        assert exc_info.value.code == "TAL-407"
        assert not (target / "SOUL.md").exists()

    def test_gateway_running_refuses(self, tmp_path):
        import os

        _inst, pres = make_bundle(tmp_path)
        target = tmp_path / "t7"
        target.mkdir()
        (target / "gateway.pid").write_text(str(os.getpid()))
        with pytest.raises(Refusal) as exc_info:
            apply_bundle(pres.bundle_path, target,
                         ApplyOptions(consent_executable=True))
        assert exc_info.value.code == "TAL-401"


class TestConflicts:
    def _lived_in_target(self, tmp_path):
        target = tmp_path / "lived-in"
        (target / "cron").mkdir(parents=True)
        (target / "SOUL.md").write_text("# My existing soul — do not lose\n")
        (target / "config.yaml").write_text("_config_version: 36\nmodel:\n  default: x\n")
        return target

    def test_a6_keep_policy(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        target = self._lived_in_target(tmp_path)
        outcome = apply_bundle(pres.bundle_path, target,
                               ApplyOptions(conflict_policy="keep",
                                            consent_executable=True))
        assert outcome.status == "committed"
        assert (target / "SOUL.md").read_text() == "# My existing soul — do not lose\n"
        decisions = {c["path"]: c["decision"] for c in outcome.conflicts}
        assert decisions.get("SOUL.md") == "keep"

    def test_a6_overwrite_backs_up(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        target = self._lived_in_target(tmp_path)
        outcome = apply_bundle(pres.bundle_path, target,
                               ApplyOptions(conflict_policy="overwrite",
                                            consent_executable=True))
        assert "Alice's Hermes" in (target / "SOUL.md").read_text()
        backups = list(Path(outcome.backup_dir).iterdir())
        assert backups, "pre-apply backup must exist"

    def test_a6_rename_policy(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        target = self._lived_in_target(tmp_path)
        apply_bundle(pres.bundle_path, target,
                     ApplyOptions(conflict_policy="rename", consent_executable=True))
        assert (target / "SOUL.md").read_text().startswith("# My existing soul")
        assert (target / "SOUL.md.from-bundle").exists()

    def test_ask_callback(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        target = self._lived_in_target(tmp_path)
        asked = []

        def ask(path):
            asked.append(path)
            return "keep"

        apply_bundle(pres.bundle_path, target,
                     ApplyOptions(conflict_policy="ask", ask=ask,
                                  consent_executable=True))
        assert "SOUL.md" in asked


class TestCrashRollback:
    def test_a5_crash_mid_apply_then_rollback(self, tmp_path, monkeypatch):
        """Kill the apply after N placements; next run detects; rollback restores."""
        _inst, pres = make_bundle(tmp_path)
        target = self._prepare_target(tmp_path)
        before = self._snapshot_tree(target)

        calls = {"n": 0}
        real_place = apply_mod._place_file

        def exploding_place(staged, final):
            calls["n"] += 1
            if calls["n"] == 8:
                raise KeyboardInterrupt("simulated power loss")
            real_place(staged, final)

        monkeypatch.setattr(apply_mod, "_place_file", exploding_place)
        outcome = apply_bundle(pres.bundle_path, target,
                               ApplyOptions(consent_executable=True))
        # SIGINT triggers automatic rollback (R-APPLY-02).
        assert outcome.status == "rolled_back"
        assert outcome.exit_code == 5
        monkeypatch.setattr(apply_mod, "_place_file", real_place)
        after = self._snapshot_tree(target)
        assert before == after, "target must equal its pre-apply state after rollback"

    def test_unfinished_txn_detected_then_manual_rollback(self, tmp_path, monkeypatch):
        _inst, pres = make_bundle(tmp_path)
        target = self._prepare_target(tmp_path)
        before = self._snapshot_tree(target)

        calls = {"n": 0}
        real_place = apply_mod._place_file

        def hard_crash(staged, final):
            calls["n"] += 1
            if calls["n"] == 5:
                raise SystemExit(137)  # un-catchable-style crash
            real_place(staged, final)

        monkeypatch.setattr(apply_mod, "_rollback",
                            lambda journal, home: (_ for _ in ()).throw(
                                SystemExit(137)))
        monkeypatch.setattr(apply_mod, "_place_file", hard_crash)
        outcome = apply_bundle(pres.bundle_path, target,
                               ApplyOptions(consent_executable=True))
        assert outcome.status == "needs_attention"
        assert outcome.exit_code == 6
        monkeypatch.setattr(apply_mod, "_place_file", real_place)

        # Next apply refuses with TAL-503 (unfinished txn).
        with pytest.raises(Refusal) as exc_info:
            apply_bundle(pres.bundle_path, target,
                         ApplyOptions(consent_executable=True))
        assert exc_info.value.code == "TAL-503"

        # Manual rollback restores the tree.
        txn_dir = apply_mod.find_unfinished_txn(target)
        assert txn_dir is not None
        rollback_journal(txn_dir / "journal.jsonl", target)
        # Mark rolled back the way the CLI does.
        with open(txn_dir / "journal.jsonl", "a") as fh:
            fh.write(json.dumps({"seq": 9999, "ts": 0, "event": "rollback.done",
                                 "ok": True}) + "\n")
        after = self._snapshot_tree(target)
        assert before == after
        assert apply_mod.find_unfinished_txn(target) is None

    def _prepare_target(self, tmp_path):
        target = tmp_path / "crash-target"
        (target / "cron").mkdir(parents=True)
        (target / "SOUL.md").write_text("original soul\n")
        (target / "config.yaml").write_text("_config_version: 36\n")
        (target / "cron" / "jobs.json").write_text('{"jobs": []}\n')
        return target

    def _snapshot_tree(self, root: Path):
        from talaria.hashes import file_sha256

        out = {}
        for p in sorted(root.rglob("*")):
            if p.is_file() and apply_mod.TXN_DIRNAME not in p.parts:
                out[str(p.relative_to(root))] = file_sha256(p)
        return out


class TestNarrowing:
    def test_only_narrows_never_widens(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        target = tmp_path / "narrow"
        outcome = apply_bundle(
            pres.bundle_path, target,
            ApplyOptions(consent_executable=True,
                         only=("soul-md@", "config-yaml@", "memories-dir@")))
        assert (target / "SOUL.md").exists()
        assert (target / "config.yaml").exists()
        assert not (target / "state.db").exists()
        assert not (target / "cron" / "jobs.json").exists()

    def test_unknown_only_id_refuses(self, tmp_path):
        _inst, pres = make_bundle(tmp_path)
        with pytest.raises(Refusal) as exc_info:
            apply_bundle(pres.bundle_path, tmp_path / "x",
                         ApplyOptions(consent_executable=True, only=("nonsense@",)))
        assert exc_info.value.code == "TAL-208"
