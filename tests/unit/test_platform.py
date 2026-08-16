"""Tests for talaria.platform.* — path legality, collisions, containment, time, probes."""

from __future__ import annotations

import unicodedata
from datetime import timezone
from pathlib import Path

from talaria.platform import fsprobe, paths, process, timeparse


class TestWindowsLegality:
    def test_reserved_names(self):
        assert paths.windows_name_problems("CON")
        assert paths.windows_name_problems("con.txt")
        assert paths.windows_name_problems("Lpt3.log")
        assert not paths.windows_name_problems("console.txt")
        assert not paths.windows_name_problems("config.yaml")

    def test_illegal_chars_and_trailing(self):
        assert paths.windows_name_problems("a:b")
        assert paths.windows_name_problems("what?.md")
        assert paths.windows_name_problems("name.")
        assert paths.windows_name_problems("name ")
        assert not paths.windows_name_problems("plain-name_1.txt")

    def test_path_aggregation(self):
        probs = paths.windows_path_problems("skills/CON/aux.txt")
        assert any("CON" in p for p in probs)
        assert any("AUX" in p.upper() for p in probs)

    def test_sanitize(self):
        assert paths.sanitize_for_windows("what?.md") == "what_.md"
        assert paths.sanitize_for_windows("CON") == "_CON"
        assert paths.sanitize_for_windows("name.") == "name"
        assert paths.sanitize_for_windows("???") == "___"
        assert paths.sanitize_for_windows(". ") == "_"  # empty after strip -> placeholder

    def test_rename_map_deterministic_and_collision_free(self):
        rels = ["skills/CON/SKILL.md", "notes?.md", "notes_.md"]
        renames = paths.build_rename_map(rels)
        assert set(renames) == {"skills/CON/SKILL.md", "notes?.md"}
        assert renames["notes?.md"] != "notes_.md"  # collision avoided
        again = paths.build_rename_map(rels)
        assert renames == again  # deterministic


class TestCollisions:
    def test_casefold_collision(self):
        groups = paths.find_collisions(["skills/Foo/SKILL.md", "skills/foo/SKILL.md", "b.txt"])
        assert groups == [["skills/Foo/SKILL.md", "skills/foo/SKILL.md"]]

    def test_nfc_nfd_collision(self):
        nfc = unicodedata.normalize("NFC", "café.md")
        nfd = unicodedata.normalize("NFD", "café.md")
        assert nfc != nfd
        groups = paths.find_collisions([nfc, nfd])
        assert len(groups) == 1

    def test_no_false_positives(self):
        assert paths.find_collisions(["a.txt", "b.txt", "dir/a.txt"]) == []


class TestContainment:
    def test_prefix_attack_rejected(self):
        assert not paths.is_contained("/target-evil/x", "/target")
        assert paths.is_contained("/target/x", "/target")
        assert paths.is_contained("/target", "/target")

    def test_windows_flavor(self):
        f = paths.WINDOWS_FLAVOR
        assert paths.is_contained("C:\\Users\\A\\AppData\\hermes\\x", "c:\\users\\a\\appdata\\hermes", f)
        assert not paths.is_contained("C:\\Users\\Ahermes\\x", "C:\\Users\\A", f)


class TestMemberNames:
    def test_hostile_members(self):
        assert paths.member_name_problems("/abs/path")
        assert paths.member_name_problems("C:evil")
        assert paths.member_name_problems("a\\b")
        assert paths.member_name_problems("a/../b")
        assert paths.member_name_problems("skills/CON/SKILL.md")
        assert paths.member_name_problems("dir /x")  # trailing space component

    def test_good_members(self):
        assert not paths.member_name_problems("payload/home/config.yaml")
        assert not paths.member_name_problems("payload/home/skills/research/web-search/SKILL.md")


class TestTranslation:
    def test_posix_to_windows(self):
        got = paths.translate_home_path(
            "/home/alice/.hermes/scripts/x.sh",
            "/home/alice/.hermes", "C:\\Users\\bob\\AppData\\Local\\hermes", "/", "\\")
        assert got == "C:\\Users\\bob\\AppData\\Local\\hermes\\scripts\\x.sh"

    def test_windows_to_posix(self):
        got = paths.translate_home_path(
            "C:\\Users\\bob\\AppData\\Local\\hermes\\cron\\jobs.json",
            "C:\\Users\\bob\\AppData\\Local\\hermes", "/home/alice/.hermes", "\\", "/")
        assert got == "/home/alice/.hermes/cron/jobs.json"

    def test_outside_home_returns_none(self):
        assert paths.translate_home_path("/etc/passwd", "/home/a/.hermes", "/x", "/", "/") is None
        # Prefix trap: /home/alice2 is NOT under /home/alice
        assert paths.translate_home_path("/home/alice2/f", "/home/alice", "/x", "/", "/") is None


class TestProcess:
    def test_own_pid_alive(self):
        import os

        assert process.pid_alive(os.getpid())

    def test_bogus_pid_dead(self):
        assert not process.pid_alive(2 ** 22 + 12345 if hasattr(0, 'bit_length') else 999999)
        assert not process.pid_alive(-1)
        assert not process.pid_alive(0)


class TestTimeparse:
    def test_z_suffix(self):
        dt = timeparse.parse_rfc3339("2026-08-15T12:00:00Z")
        assert dt is not None and dt.tzinfo == timezone.utc

    def test_offset_forms(self):
        assert timeparse.parse_rfc3339("2026-08-15T12:00:00+05:30") is not None
        assert timeparse.parse_rfc3339("2026-08-15T12:00:00-0700") is not None
        assert timeparse.parse_rfc3339("2026-08-15 12:00:00.123456+00:00") is not None

    def test_naive_allowed(self):
        dt = timeparse.parse_rfc3339("2026-08-15T12:00:00")
        assert dt is not None and dt.tzinfo is None

    def test_garbage_none(self):
        assert timeparse.parse_rfc3339("not a date") is None
        assert timeparse.parse_rfc3339("") is None

    def test_tz_mismatch(self):
        src = ("America/Chicago", -300, True)
        tgt = ("Europe/Paris", 120, True)
        msg = timeparse.tz_mismatch(src, tgt)
        assert msg and "7 hour" in msg
        assert timeparse.tz_mismatch(src, ("US/Central", -300, True)) is None

    def test_windows_zone_map(self):
        assert timeparse.windows_to_iana("Central Standard Time") == "America/Chicago"
        assert timeparse.windows_to_iana("Nope Standard Time") is None


class TestFsprobe:
    def test_probe_runs(self, tmp_path: Path):
        b = fsprobe.probe_behavior(tmp_path)
        assert isinstance(b.case_insensitive, bool)
        assert list(tmp_path.iterdir()) == []  # probes cleaned up

    def test_fs_type_and_flags(self, tmp_path: Path):
        t = fsprobe.fs_type_of(tmp_path)
        assert isinstance(t, str) and t
        assert fsprobe.is_fat_like("vfat")
        assert fsprobe.is_wal_hostile("nfs4")
        assert not fsprobe.is_wal_hostile("ext4")

    def test_volume_grouping(self, tmp_path: Path):
        a, b = tmp_path / "a", tmp_path / "b"
        groups = fsprobe.group_by_volume([a, b])
        assert len(groups) == 1  # same tmp volume
