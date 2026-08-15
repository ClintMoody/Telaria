"""Safe capture of live SQLite databases.

Hermes keeps a dozen SQLite stores (state.db, kanban.db, cron/*.db, ...) in WAL mode. A
byte-copy of a hot database pairs a torn main file with stale sidecars — upstream's own
backup refuses to do it, and so do we. Protocol (mirrors hermes_cli/backup.py:342-556):

- open the source read-only (URI mode) so a locked/busy writer is never disturbed;
- stream through ``sqlite3.Connection.backup`` — page-consistent even mid-write, and folds
  un-checkpointed WAL content into the output;
- verify the result (header magic; full ``PRAGMA integrity_check`` under a size cap, O(1)
  schema probe above it — upstream saw real 30 GB state.db files);
- fail closed: any error removes the partial output and raises.

Sidecar files (-wal/-shm/-journal) are never captured — the snapshot is self-contained.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Tuple

SQLITE_MAGIC = b"SQLite format 3\x00"

# Full integrity_check is O(n); above this size use the O(1) schema probe instead.
# Upstream caps at 2 GiB (hermes_cli/backup.py:405-413).
FULL_CHECK_MAX_BYTES = 2 * 1024 * 1024 * 1024


class SqliteSnapshotError(RuntimeError):
    """A database snapshot could not be taken safely."""


def is_sqlite_file(path: Path) -> bool:
    """True when ``path`` exists and starts with the SQLite header magic."""
    try:
        with open(path, "rb") as handle:
            return handle.read(len(SQLITE_MAGIC)) == SQLITE_MAGIC
    except OSError:
        return False


def is_zeroed_sqlite(path: Path) -> bool:
    """Detect the all-zero/empty '.db' failure mode (upstream issue #68474).

    A zero-length or NUL-prefixed file is not a database; capturing it as one would
    smuggle corruption into the bundle.
    """
    try:
        size = os.path.getsize(path)
    except OSError:
        return False
    if size == 0:
        return True
    try:
        with open(path, "rb") as handle:
            head = handle.read(len(SQLITE_MAGIC))
    except OSError:
        return False
    return head == b"\x00" * len(head)


def verify_integrity(path: Path) -> Tuple[bool, str]:
    """Verify a database file. Returns ``(ok, detail)``; never raises."""
    path = Path(path)
    if not is_sqlite_file(path):
        return False, "not a SQLite database (bad header magic)"
    try:
        size = path.stat().st_size
    except OSError as exc:
        return False, f"unreadable: {exc}"
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if size <= FULL_CHECK_MAX_BYTES:
                row = conn.execute("PRAGMA integrity_check(1)").fetchone()
                if row and row[0] == "ok":
                    return True, "integrity_check ok"
                return False, f"integrity_check: {row[0] if row else 'no result'}"
            # O(1) probe for very large databases: schema read + first page access.
            conn.execute("SELECT name FROM sqlite_master LIMIT 1").fetchone()
            return True, "schema probe ok (size over full-check cap)"
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return False, f"sqlite error: {exc}"


def snapshot_db(src: Path, dst: Path) -> None:
    """Snapshot ``src`` into ``dst`` page-consistently; fail closed.

    The output is written to ``dst`` directly after its parent is created; on any failure
    the partial output is removed and :class:`SqliteSnapshotError` is raised.
    """
    src, dst = Path(src), Path(dst)
    if not src.is_file():
        raise SqliteSnapshotError(f"source database missing: {src}")
    if is_zeroed_sqlite(src):
        raise SqliteSnapshotError(f"source database is zeroed/empty: {src}")
    if not is_sqlite_file(src):
        raise SqliteSnapshotError(f"source is not a SQLite database: {src}")

    dst.parent.mkdir(parents=True, exist_ok=True)
    src_conn = None
    dst_conn = None
    try:
        src_conn = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
        dst_conn = sqlite3.connect(dst)
        src_conn.backup(dst_conn)
        dst_conn.commit()
    except sqlite3.Error as exc:
        _cleanup_partial(dst_conn, dst)
        dst_conn = None
        raise SqliteSnapshotError(f"snapshot of {src.name} failed: {exc}") from exc
    finally:
        if src_conn is not None:
            src_conn.close()
        if dst_conn is not None:
            dst_conn.close()

    ok, detail = verify_integrity(dst)
    if not ok:
        try:
            dst.unlink()
        except OSError:
            pass
        raise SqliteSnapshotError(f"snapshot of {src.name} failed verification: {detail}")


def _cleanup_partial(conn, dst: Path) -> None:
    if conn is not None:
        try:
            conn.close()
        except sqlite3.Error:
            pass
    for suffix in ("", "-wal", "-shm", "-journal"):
        try:
            Path(str(dst) + suffix).unlink()
        except OSError:
            pass
