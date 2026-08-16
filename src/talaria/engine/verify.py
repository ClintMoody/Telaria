"""Standalone verification: gating integrity re-run + advisory functional checks
(R-VERIFY-01..03). `talaria verify` replays these against the last apply; `--watch`
polls for the heartbeat proof-of-life.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from talaria.engine.apply import TXN_DIRNAME, Journal
from talaria.engine.resolve import find_install_dir
from talaria.hashes import file_sha256
from talaria.model.catalog import exclusion_for


@dataclass
class Check:
    id: str
    title: str
    status: str          # ok|warn|fail|info
    detail: str = ""

    def to_json(self) -> dict:
        return {"id": self.id, "title": self.title, "status": self.status,
                "detail": self.detail}


def verify_last_apply(target_home: Path) -> List[Check]:
    """Re-verify the most recent committed transaction (R-VERIFY-03)."""
    checks: List[Check] = []
    target_home = Path(target_home)
    txn_root = target_home / TXN_DIRNAME / "txn"
    latest: Optional[Path] = None
    if txn_root.is_dir():
        for txn_dir in sorted(txn_root.iterdir(), reverse=True):
            if (txn_dir / "journal.jsonl").is_file():
                latest = txn_dir
                break
    if latest is None:
        checks.append(Check("V-00", "No talaria transaction found here", "info",
                            "nothing to verify — run an apply first"))
        return checks

    records = Journal.read_all(latest / "journal.jsonl")
    committed = any(r.get("event") == "commit" for r in records)
    checks.append(Check("V-01", "Transaction state",
                        "ok" if committed else "warn",
                        f"txn {latest.name} " +
                        ("committed" if committed else "did not commit — `talaria "
                                                       "rollback` is available")))

    verified = failed = 0
    for record in records:
        if record.get("event") != "op.intent" or record.get("kind") not in (
                "replace_file", "db_place"):
            continue
        final = Path(record.get("final", ""))
        expected = record.get("expected_sha")
        if not final.exists():
            failed += 1
            checks.append(Check("V-02", f"Missing: {final.name}", "fail",
                                str(final)))
            continue
        if expected:
            if file_sha256(final) == expected:
                verified += 1
            else:
                failed += 1
                checks.append(Check("V-02", f"Changed since apply: {final.name}",
                                    "warn",
                                    f"{final} differs from the applied content (Hermes "
                                    "may legitimately have written it since)"))
    checks.append(Check("V-02", "File integrity", "ok" if not failed else "warn",
                        f"{verified} verified, {failed} flagged"))

    checks.extend(functional_checks(target_home))
    return checks


def functional_checks(target_home: Path) -> List[Check]:
    """Advisory checks — never block anything (R-VERIFY-02)."""
    checks: List[Check] = []
    target_home = Path(target_home)

    # Machine-bound absence sweep.
    present = [name for name in ("gateway_state.json", "gateway.pid", "cron.pid",
                                 "processes.json")
               if (target_home / name).exists()]
    checks.append(Check("V-03", "Machine-bound leftovers",
                        "warn" if present else "ok",
                        ", ".join(present) if present else "none present"))

    # DB quick_check (small DBs only).
    for rel in ("state.db", "kanban.db", "cron/notepad.db"):
        db = target_home / rel
        if not db.is_file():
            continue
        try:
            if db.stat().st_size > 2 * 1024 * 1024 * 1024:
                checks.append(Check("V-04", f"{rel}", "info",
                                    "over 2 GiB — schema probe only"))
                continue
            conn = sqlite3.connect(f"file:{db}?mode=ro&immutable=1", uri=True)
            row = conn.execute("PRAGMA quick_check(1)").fetchone()
            conn.close()
            ok = bool(row) and row[0] == "ok"
            checks.append(Check("V-04", f"Database {rel}", "ok" if ok else "fail",
                                "quick_check " + ("ok" if ok else str(row))))
        except sqlite3.Error as exc:
            checks.append(Check("V-04", f"Database {rel}", "fail", str(exc)))

    # Secret modes (POSIX).
    if os.name == "posix":
        loose = []
        for rel in (".env", "auth.json"):
            f = target_home / rel
            if f.is_file() and (f.stat().st_mode & 0o077):
                loose.append(rel)
        checks.append(Check("V-05", "Secret file permissions",
                            "warn" if loose else "ok",
                            ("world/group-readable: " + ", ".join(loose) +
                             " — run chmod 600") if loose else "0600 respected"))

    # Hermes smoke test.
    hermes = _hermes_command(target_home)
    if hermes:
        try:
            out = subprocess.run([*hermes, "--version"], capture_output=True, text=True,
                                 timeout=60, check=False)
            line = (out.stdout or out.stderr).strip().splitlines()
            checks.append(Check("V-06", "Hermes answers", "ok" if out.returncode == 0
                                else "warn",
                                line[0] if line else f"exit {out.returncode}"))
        except (OSError, subprocess.SubprocessError) as exc:
            checks.append(Check("V-06", "Hermes answers", "warn", str(exc)))
    else:
        checks.append(Check("V-06", "Hermes not installed yet", "info",
                            "install Hermes, then run `talaria verify` again"))

    # Legacy empty-dir shadow audit (#27602).
    shadows = []
    for new, old in (("platforms/pairing", "pairing"),):
        old_dir = target_home / old
        new_dir = target_home / new
        if old_dir.is_dir() and not any(old_dir.iterdir()) and new_dir.is_dir():
            shadows.append(old)
    if shadows:
        checks.append(Check("V-07", "Empty legacy directories", "warn",
                            ", ".join(shadows) + " — empty legacy dirs can shadow real "
                            "data; remove them"))
    return checks


def _hermes_command(target_home: Path) -> Optional[List[str]]:
    import shutil as _shutil

    exe = _shutil.which("hermes")
    if exe:
        return [exe]
    install_dir = find_install_dir(Path(target_home))
    if install_dir is not None:
        for rel in ("venv/bin/hermes", ".venv/bin/hermes"):
            cand = install_dir / rel
            if cand.is_file():
                return [str(cand)]
    return None


def watch_heartbeat(target_home: Path, timeout_seconds: int = 180,
                    poll_seconds: float = 5.0) -> Check:
    """Proof-of-life: cron/ticker_heartbeat advancing means the gateway lives
    (deliberately unmigrated — its absence-then-appearance IS the signal)."""
    heartbeat = Path(target_home) / "cron" / "ticker_heartbeat"
    started = time.time()
    initial = _mtime(heartbeat)
    while time.time() - started < timeout_seconds:
        current = _mtime(heartbeat)
        if current and current != initial:
            return Check("V-08", "Hermes is alive", "ok",
                         "the scheduler heartbeat is ticking on this machine")
        time.sleep(poll_seconds)
    return Check("V-08", "No heartbeat yet", "warn",
                 f"no ticker heartbeat within {timeout_seconds}s — is the gateway "
                 "started? (`hermes gateway start`; the first beat can take ~60s)")


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
