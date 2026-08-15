"""Tests for the scanner engine against the synthetic install factory."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine.scan import scan  # noqa: E402


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    root = tmp_path_factory.mktemp("hermes-home")
    inst = build_fake_install(root / "h", FakeInstallSpec(with_profile="coder",
                                                          with_git=False))
    return inst, scan(inst.home)


class TestWalk:
    def test_scan_finds_core_artifacts(self, installed):
        _inst, result = installed
        kinds = {a.kind for a in result.artifacts}
        for expected in ("config-yaml", "env-file", "soul-md", "memories-dir", "state-db",
                         "cron-jobs", "cron-notepad", "scripts-dir", "skill-dir",
                         "pairing-stores", "channel-routing", "kanban", "auth-stores",
                         "mcp-tokens", "plugin-dir", "plugin-data", "skills-metadata",
                         "hub-metadata", "skill-bundles"):
            assert expected in kinds, expected

    def test_machine_bound_never_carried(self, installed):
        _inst, result = installed
        for art in result.artifacts:
            if art.kind.startswith("excluded:"):
                assert art.default == "never"
                assert not art.selected
        excluded_ids = {a.kind for a in result.artifacts if a.kind.startswith("excluded:")}
        assert "excluded:gateway-runtime" in excluded_ids
        assert "excluded:device-linked" in excluded_ids

    def test_sidecars_not_in_files(self, installed):
        _inst, result = installed
        all_files = [f.home_rel for a in result.artifacts for f in a.files
                     if not a.kind.startswith("excluded:")]
        assert "state.db" in all_files
        assert "state.db-wal" not in all_files
        assert "state.db-shm" not in all_files

    def test_vendored_runtimes_pruned(self, installed):
        _inst, result = installed
        all_files = [f.home_rel for a in result.artifacts for f in a.files]
        assert not any(f.startswith("hermes-agent/") for f in all_files)
        assert not any(f.startswith("bin/") or f.startswith("node/") for f in all_files)
        assert not any(f.startswith("logs/") or f.startswith("cache/") for f in all_files)

    def test_profile_subtree_scanned(self, installed):
        _inst, result = installed
        coder = [a for a in result.artifacts if a.profile == "coder"]
        assert {a.kind for a in coder} >= {"config-yaml", "env-file", "soul-md",
                                           "cron-jobs", "skill-dir", "skills-metadata"}

    def test_skill_artifacts_grouped_per_skill(self, installed):
        _inst, result = installed
        skills = result.by_kind("skill-dir")
        names = {a.id.rsplit("/", 1)[-1] for a in skills}
        assert {"web-search", "daily-brief", "playlist-curator", "budget-watch"} <= names
        web = next(a for a in skills if a.id.endswith("web-search"))
        rels = {f.home_rel for f in web.files}
        assert "skills/research/web-search/SKILL.md" in rels
        assert "skills/research/web-search/references/engines.md" in rels

    def test_state_db_flagged_sqlite(self, installed):
        _inst, result = installed
        state = result.by_kind("state-db")[0]
        assert state.files[0].is_sqlite
        assert state.secrecy == "content"

    def test_credentials_classified(self, installed):
        _inst, result = installed
        env = result.by_kind("env-file")[0]
        assert env.secrecy == "credential"
        mcp = result.by_kind("mcp-tokens")[0]
        assert mcp.secrecy == "credential"


class TestReferences:
    def test_config_refs_found(self, installed):
        _inst, result = installed
        locators = {r.locator for r in result.machine_refs if r.profile == ""}
        assert "terminal.cwd" in locators
        assert "mcp_servers.n8n.command" in locators
        assert "skills.external_dirs[]" not in locators  # spec had none for root profile
        assert "dashboard.public_url" in locators

    def test_localhost_urls_flagged(self, installed):
        _inst, result = installed
        kinds = {(r.locator, r.ref_kind) for r in result.machine_refs}
        assert ("jobs[id=b2c3d4e5f6a7].monitor_url", "localhost-url") in kinds

    def test_cron_refs_found(self, installed):
        _inst, result = installed
        locs = {r.locator for r in result.machine_refs if r.file == "cron/jobs.json"}
        assert "jobs[id=b2c3d4e5f6a7].script" in locs
        assert "jobs[id=b2c3d4e5f6a7].workdir" in locs
        assert "jobs[id=c3d4e5f6a7b8].skills[0]" in locs

    def test_touchpoints_ledger(self, installed):
        _inst, result = installed
        assert result.touchpoints
        provs = {p for t in result.touchpoints for p in t.provenance}
        assert "config-ref" in provs and "cron-ref" in provs
        for t in result.touchpoints:
            assert t.confidence == "verified"

    def test_external_skill_dir_chased(self, tmp_path):
        ext = tmp_path / "shared-skills"
        inst = build_fake_install(tmp_path / "h",
                                  FakeInstallSpec(with_external_skill_dir=ext))
        result = scan(inst.home)
        refs = [r for r in result.machine_refs if r.ref_kind == "external-dir"]
        assert any(str(ext) in r.value for r in refs)


class TestEtiquette:
    def test_quiesced_by_default(self, installed):
        _inst, result = installed
        # Fixture writes pid files with dead pids -> quiesced.
        assert result.capture_mode == "quiesced"

    def test_live_gateway_warns(self, tmp_path):
        import os

        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        (inst.home / "gateway.pid").write_text(str(os.getpid()))
        result = scan(inst.home)
        assert result.capture_mode == "live"
        assert any("gateway is running" in w for w in result.warnings)

    def test_update_marker_refuses(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        (inst.home / ".hermes-update-in-progress").write_text("")
        result = scan(inst.home)
        assert result.refusals


class TestUnrecognized:
    def test_clean_text_carried(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        (inst.home / "my-notes.txt").write_text("just some notes\n")
        result = scan(inst.home)
        unrec = [a for a in result.artifacts if a.kind == "unrecognized"
                 and any(f.home_rel == "my-notes.txt" for f in a.files)]
        assert unrec and unrec[0].default == "on" and unrec[0].selected

    def test_secretish_text_quarantined(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        (inst.home / "oops.txt").write_text("here: sk-abcdefghijklmnop1234567890\n")
        result = scan(inst.home)
        art = next(a for a in result.artifacts
                   if any(f.home_rel == "oops.txt" for f in a.files))
        assert art.secrecy == "credential"
        assert art.default == "record_only" and not art.selected

    def test_credential_variant_name_quarantined(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        (inst.home / ".env.bak").write_text("OPENROUTER_API_KEY=sk-x\n")
        result = scan(inst.home)
        art = next(a for a in result.artifacts
                   if any(f.home_rel == ".env.bak" for f in a.files))
        assert art.secrecy == "credential" and art.default == "record_only"

    def test_binary_record_only(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        (inst.home / "blob.bin").write_bytes(b"\x00\x01\x02" * 100)
        result = scan(inst.home)
        art = next(a for a in result.artifacts
                   if any(f.home_rel == "blob.bin" for f in a.files))
        assert art.default == "record_only"

    def test_nothing_silent(self, tmp_path):
        """Every file is either in an artifact or counted excluded (Promise 3)."""
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        result = scan(inst.home)
        assert result.scanned_files > 0
        assert sum(result.excluded_counts.values()) > 0
