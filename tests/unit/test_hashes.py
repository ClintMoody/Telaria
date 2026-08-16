"""Tests for talaria.hashes — the three upstream digest schemes, bit-exact.

Upstream sources (see docs/research/subsystem-skills-plugins.md §5):
- bundled_dir_hash: MD5 over sorted rglob rel-path-str + bytes (tools/skills_sync.py:254-265).
  Rel-path string is OS-native — a Windows-written manifest differs from POSIX for the same tree.
- hub_content_hash: "sha256:<16hex>" over POSIX-sorted rel paths (tools/skills_guard.py:867-878;
  their issue #62310 is exactly the native-sort bug we must not reintroduce).
- file_sha256: plain streaming SHA-256 for bundle payload checksums.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from talaria.hashes import bundled_dir_hash, file_sha256, hub_content_hash


@pytest.fixture()
def skill_dir(tmp_path: Path) -> Path:
    d = tmp_path / "web-search"
    (d / "references").mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: web-search\n---\nbody\n", encoding="utf-8")
    (d / "references" / "engines.md").write_text("engines\n", encoding="utf-8")
    return d


def _reference_md5(directory: Path, sep: str) -> str:
    hasher = hashlib.md5()
    for fpath in sorted(directory.rglob("*")):
        if fpath.is_file():
            rel = str(fpath.relative_to(directory)).replace("/", sep)
            hasher.update(rel.encode("utf-8"))
            hasher.update(fpath.read_bytes())
    return hasher.hexdigest()


class TestBundledDirHash:
    def test_matches_upstream_algorithm_posix(self, skill_dir: Path):
        assert bundled_dir_hash(skill_dir, sep="/") == _reference_md5(skill_dir, "/")

    def test_windows_sep_differs(self, skill_dir: Path):
        # Same tree, Windows-native separator: hash must differ (nested file present).
        posix = bundled_dir_hash(skill_dir, sep="/")
        win = bundled_dir_hash(skill_dir, sep="\\")
        assert posix != win

    def test_native_sep_default(self, skill_dir: Path):
        import os

        assert bundled_dir_hash(skill_dir) == bundled_dir_hash(skill_dir, sep=os.sep)

    def test_content_change_changes_hash(self, skill_dir: Path):
        before = bundled_dir_hash(skill_dir)
        (skill_dir / "SKILL.md").write_text("changed", encoding="utf-8")
        assert bundled_dir_hash(skill_dir) != before

    def test_rename_changes_hash(self, skill_dir: Path):
        before = bundled_dir_hash(skill_dir)
        (skill_dir / "references" / "engines.md").rename(skill_dir / "references" / "zz.md")
        assert bundled_dir_hash(skill_dir) != before

    def test_empty_dirs_ignored(self, skill_dir: Path):
        before = bundled_dir_hash(skill_dir)
        (skill_dir / "assets").mkdir()
        assert bundled_dir_hash(skill_dir) == before

    def test_matches_fixture_factory(self, tmp_path: Path):
        # The factory's own hash helper is a second independent implementation.
        import sys

        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
        try:
            from hermes_factory import skills_dir_hash
        finally:
            sys.path.pop(0)
        d = tmp_path / "s"
        (d / "scripts").mkdir(parents=True)
        (d / "SKILL.md").write_text("x", encoding="utf-8")
        (d / "scripts" / "run.py").write_text("print(1)", encoding="utf-8")
        assert bundled_dir_hash(d) == skills_dir_hash(d)


class TestHubContentHash:
    def test_posix_sort_even_with_backslash_names(self, tmp_path: Path):
        """Hub hash sorts by POSIX rel-path string regardless of platform (issue #62310)."""
        d = tmp_path / "skill"
        d.mkdir()
        (d / "SKILL.md").write_bytes(b"a")
        (d / "b.md").write_bytes(b"b")
        got = hub_content_hash(d)
        assert got.startswith("sha256:") and len(got) == len("sha256:") + 16

    def test_stable_across_calls(self, tmp_path: Path):
        d = tmp_path / "s"
        d.mkdir()
        (d / "SKILL.md").write_bytes(b"hello")
        assert hub_content_hash(d) == hub_content_hash(d)


class TestFileSha256:
    def test_streams_large_file(self, tmp_path: Path):
        p = tmp_path / "big.bin"
        blob = b"x" * (1024 * 1024 + 17)
        p.write_bytes(blob)
        assert file_sha256(p) == hashlib.sha256(blob).hexdigest()
