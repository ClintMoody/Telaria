"""Tests for provenance tagging and diffs against the fixture factory."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine import diffs, provenance  # noqa: E402
from talaria.engine.provenance import HashSemantics, classify_skills, dir_hash  # noqa: E402


@pytest.fixture(scope="module")
def install(tmp_path_factory):
    root = tmp_path_factory.mktemp("prov")
    return build_fake_install(root / "h", FakeInstallSpec())


class TestDirHash:
    def test_posix_matches_factory(self, install):
        d = install.skills / "research" / "web-search"
        assert dir_hash(d) == install.stock_hashes["web-search"]

    def test_nt_semantics_differ(self, install):
        d = install.skills / "research" / "web-search"
        posix = dir_hash(d, HashSemantics("posix", "posix"))
        nt = dir_hash(d, HashSemantics("nt", "nt"))
        assert posix != nt  # nested file => separator flavored

    def test_nt_collation_casefolds(self, tmp_path):
        d = tmp_path / "s"
        d.mkdir()
        (d / "B.md").write_bytes(b"b")
        (d / "a.md").write_bytes(b"a")
        # POSIX byte sort: B < a; NT casefolded sort: a < B — orders differ.
        assert dir_hash(d, HashSemantics("posix", "posix")) != \
            dir_hash(d, HashSemantics("posix", "nt"))


class TestClassification:
    def test_six_tags(self, install):
        tags = {p.name: p.tag for p in classify_skills(install.skills)}
        assert tags["web-search"] == "stock-pristine"
        assert tags["daily-brief"] == "stock-modified"
        assert tags["social-media-poster"] == "stock-deleted"
        assert tags["playlist-curator"] == "agent-created"
        assert tags["budget-watch"] == "hub-installed"

    def test_archive_not_counted_as_skill(self, install):
        names = {p.name for p in classify_skills(install.skills)}
        assert "old-notes-skill" not in names  # .archive is excluded from discovery

    def test_usage_provenance_carried(self, install):
        provs = {p.name: p for p in classify_skills(install.skills)}
        assert provs["playlist-curator"].usage.get("created_by") == "agent"
        assert provs["web-search"].usage.get("use_count") == 42

    def test_nested_support_dir_skill_md_ignored(self, install):
        nested = install.skills / "research" / "web-search" / "references" / "old-pkg"
        nested.mkdir(parents=True)
        (nested / "SKILL.md").write_text("---\nname: ghost\n---\n")
        try:
            names = {p.name for p in classify_skills(install.skills)}
            assert "ghost" not in names
        finally:
            (nested / "SKILL.md").unlink()
            nested.rmdir()

    def test_rebaseline_only_pristine(self, install):
        provs = classify_skills(install.skills)
        manifest = provenance.read_bundled_manifest(install.skills)
        target = HashSemantics("nt", "nt")
        rebased = provenance.rebaseline_manifest(manifest, provs, install.skills, target)
        # Pristine skill: hash recomputed under NT semantics.
        assert rebased["web-search"] == dir_hash(
            install.skills / "research" / "web-search", target)
        # Modified skill: seed-time hash untouched.
        assert rebased["daily-brief"] == manifest["daily-brief"]
        # Deleted entry preserved.
        assert rebased["social-media-poster"] == manifest["social-media-poster"]


class TestDiffs:
    def test_skill_tree_diff(self, tmp_path):
        base, cur = tmp_path / "base", tmp_path / "cur"
        for d in (base, cur):
            (d / "scripts").mkdir(parents=True)
        (base / "SKILL.md").write_text("---\nname: x\n---\nline1\n")
        (cur / "SKILL.md").write_text("---\nname: x\n---\nline1\nline2 added\n")
        (base / "gone.md").write_text("bye")
        (cur / "new.md").write_text("hello")
        (cur / "blob.bin").write_bytes(b"\x00\x01")
        out = {d.path: d for d in diffs.diff_skill_trees(base, cur)}
        assert out["SKILL.md"].status == "modified"
        assert "+line2 added" in out["SKILL.md"].diff
        assert out["gone.md"].status == "removed"
        assert out["new.md"].status == "added"
        assert out["blob.bin"].status == "added"

    def test_config_diff_masks_credentials(self):
        user = {"model": {"default": "custom-model", "api_key": "sk-secret"},
                "memory": {"memory_enabled": True}}
        default = {"model": {"default": "stock-model", "api_key": None},
                   "memory": {"memory_enabled": True}}
        cd = diffs.diff_config(user, default)
        assert cd.status == "ok"
        assert cd.customized["model.default"]["current"] == "custom-model"
        assert cd.customized["model.api_key"]["current"] == diffs.MASKED
        assert "memory.memory_enabled" not in cd.customized

    def test_config_diff_degrades_without_defaults(self):
        cd = diffs.diff_config({"a": 1}, None)
        assert cd.status == "unknown_no_venv"

    def test_checkout_state(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(with_git=True,
                                                                  with_dirty_checkout=True))
        state = diffs.checkout_state(inst.home)
        assert state.status == "dirty"
        assert "local tweak" in state.patch

    def test_checkout_clean(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(with_git=True))
        assert diffs.checkout_state(inst.home).status == "clean"

    def test_checkout_absent(self, tmp_path):
        (tmp_path / "config.yaml").write_text("x: 1\n")
        assert diffs.checkout_state(tmp_path).status == "absent"
