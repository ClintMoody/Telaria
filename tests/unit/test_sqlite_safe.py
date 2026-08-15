"""Tests for talaria.sqlite_safe — hot-DB snapshot protocol.

Mirrors upstream hermes_cli/backup.py behaviors (research: subsystem-state-layout.md §2.3,
hermes-backup-precedent.md): backup-API snapshot (never byte-copy), integrity gate, zeroed-file
detection, WAL sidecar independence, fail-closed semantics.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from talaria.sqlite_safe import (
    SqliteSnapshotError,
    is_sqlite_file,
    is_zeroed_sqlite,
    snapshot_db,
    verify_integrity,
)


def _make_db(path: Path, rows: int = 3, wal: bool = True) -> None:
    conn = sqlite3.connect(path)
    try:
        if wal:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
        conn.executemany("INSERT INTO t (v) VALUES (?)", [(f"row{i}",) for i in range(rows)])
        conn.commit()
    finally:
        conn.close()


class TestSnapshot:
    def test_snapshot_copies_all_rows(self, tmp_path: Path):
        src, dst = tmp_path / "state.db", tmp_path / "out" / "state.db"
        _make_db(src, rows=5)
        snapshot_db(src, dst)
        conn = sqlite3.connect(dst)
        try:
            assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 5
        finally:
            conn.close()

    def test_snapshot_with_uncheckpointed_wal(self, tmp_path: Path):
        """Rows still only in the -wal must land in the snapshot."""
        src = tmp_path / "state.db"
        dst = tmp_path / "snap.db"
        conn = sqlite3.connect(src)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE t (v TEXT)")
        conn.execute("INSERT INTO t VALUES ('in-wal')")
        conn.commit()  # committed but not checkpointed; keep connection open
        try:
            assert (tmp_path / "state.db-wal").exists()
            snapshot_db(src, dst)
        finally:
            conn.close()
        out = sqlite3.connect(dst)
        try:
            assert out.execute("SELECT v FROM t").fetchone()[0] == "in-wal"
        finally:
            out.close()
        # Snapshot must not drag sidecars along.
        assert not (tmp_path / "snap.db-wal").exists()

    def test_snapshot_source_untouched(self, tmp_path: Path):
        src, dst = tmp_path / "a.db", tmp_path / "b.db"
        _make_db(src)
        before = src.read_bytes()
        snapshot_db(src, dst)
        assert src.read_bytes() == before

    def test_snapshot_missing_source_fails_closed(self, tmp_path: Path):
        with pytest.raises(SqliteSnapshotError):
            snapshot_db(tmp_path / "nope.db", tmp_path / "out.db")

    def test_snapshot_corrupt_source_fails_closed(self, tmp_path: Path):
        src = tmp_path / "bad.db"
        src.write_bytes(b"SQLite format 3\x00" + b"\xff" * 100)
        with pytest.raises(SqliteSnapshotError):
            snapshot_db(src, tmp_path / "out.db")
        assert not (tmp_path / "out.db").exists(), "failed snapshot must not leave partial output"

    def test_snapshot_creates_parent_dirs(self, tmp_path: Path):
        src = tmp_path / "a.db"
        _make_db(src)
        dst = tmp_path / "deep" / "nested" / "a.db"
        snapshot_db(src, dst)
        assert dst.exists()


class TestDetection:
    def test_is_sqlite_file(self, tmp_path: Path):
        db = tmp_path / "x.db"
        _make_db(db)
        assert is_sqlite_file(db)
        txt = tmp_path / "y.db"
        txt.write_text("not a database")
        assert not is_sqlite_file(txt)

    def test_zeroed_detection(self, tmp_path: Path):
        z = tmp_path / "z.db"
        z.write_bytes(b"\x00" * 4096)
        assert is_zeroed_sqlite(z)
        real = tmp_path / "r.db"
        _make_db(real)
        assert not is_zeroed_sqlite(real)
        assert not is_zeroed_sqlite(tmp_path / "empty.db.absent")

    def test_empty_file_counts_as_zeroed(self, tmp_path: Path):
        e = tmp_path / "e.db"
        e.write_bytes(b"")
        assert is_zeroed_sqlite(e)


class TestVerify:
    def test_good_db_passes(self, tmp_path: Path):
        db = tmp_path / "ok.db"
        _make_db(db)
        ok, detail = verify_integrity(db)
        assert ok, detail

    def test_bad_magic_fails(self, tmp_path: Path):
        db = tmp_path / "bad.db"
        db.write_bytes(b"garbage header" + b"\x00" * 100)
        ok, detail = verify_integrity(db)
        assert not ok

    def test_size_cap_switches_to_probe(self, tmp_path: Path, monkeypatch):
        """Above the cap we do the O(1) schema probe instead of full integrity_check."""
        db = tmp_path / "big.db"
        _make_db(db)
        import talaria.sqlite_safe as mod

        monkeypatch.setattr(mod, "FULL_CHECK_MAX_BYTES", 1)
        ok, detail = verify_integrity(db)
        assert ok
        assert "probe" in detail
