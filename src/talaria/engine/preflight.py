"""Preflight gates PF-01..PF-18 (ARCHITECTURE §9.2; R-APPLY-04).

Each gate probes the REAL target and yields ok/warn/refuse/consent. Nothing here writes.
The wizard renders who-acts groups from these results; the CLI prints them sectioned
like `hermes doctor`.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from talaria.engine.bundle import BundleReader, PAYLOAD_HOME
from talaria.engine.resolve import find_install_dir, detect_identity
from talaria.platform.fsprobe import (
    free_bytes,
    fs_type_of,
    is_wal_hostile,
    probe_behavior,
)
from talaria.platform.paths import (
    build_rename_map,
    find_collisions,
    longest_final_path,
    windows_path_problems,
    POSIX_FLAVOR,
    WINDOWS_FLAVOR,
)
from talaria.platform.process import pid_alive
from talaria.platform.timeparse import parse_rfc3339, tz_mismatch


@dataclass
class Gate:
    id: str
    title: str
    status: str          # ok|warn|refuse|consent
    detail: str = ""
    fix: str = ""

    def to_json(self) -> dict:
        return {"id": self.id, "title": self.title, "status": self.status,
                "detail": self.detail, "fix": self.fix}


@dataclass
class PreflightReport:
    gates: List[Gate] = field(default_factory=list)
    rename_map: Dict[str, str] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)       # root-relative paths
    executable_summary: Dict[str, int] = field(default_factory=dict)
    skew_class: str = "UNKNOWN"
    hermes_present: bool = False

    @property
    def refusals(self) -> List[Gate]:
        return [g for g in self.gates if g.status == "refuse"]

    @property
    def consents(self) -> List[Gate]:
        return [g for g in self.gates if g.status == "consent"]

    def to_json(self) -> dict:
        return {"gates": [g.to_json() for g in self.gates],
                "rename_map": self.rename_map, "conflicts": self.conflicts,
                "executable_summary": self.executable_summary,
                "skew_class": self.skew_class, "hermes_present": self.hermes_present}


def _read_pid(path: Path) -> Optional[int]:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def run_preflight(reader: BundleReader, target_home: Path,
                  scratch_dir: Optional[Path] = None) -> PreflightReport:
    report = PreflightReport()
    manifest = reader.manifest
    target_home = Path(target_home)
    gates = report.gates

    # PF-01 gateway not running — check the root home AND every profile home, since a
    # gateway/ticker can be running for a named profile (its pid files live under
    # profiles/<name>/) while the root is idle.
    homes = [target_home]
    profiles_dir = target_home / "profiles"
    if profiles_dir.is_dir():
        for child in sorted(profiles_dir.iterdir()):
            if child.is_dir() and not child.is_symlink() and not child.name.startswith("."):
                homes.append(child)
    running = []
    for phome in homes:
        label = "" if phome == target_home else f" (profile {phome.name})"
        gw_pid = _read_pid(phome / "gateway.pid")
        cron_pid = _read_pid(phome / "cron.pid")
        if gw_pid and pid_alive(gw_pid):
            running.append((f"gateway{label}", gw_pid))
        if cron_pid and pid_alive(cron_pid):
            running.append((f"cron ticker{label}", cron_pid))
    if running:
        names = " and ".join(n for n, _ in running)
        gates.append(Gate("PF-01", "Hermes must be stopped", "refuse",
                          f"the {names} is running on this machine",
                          "run `hermes gateway stop` (for each running profile), "
                          "then apply again"))
    else:
        gates.append(Gate("PF-01", "Hermes is stopped", "ok"))

    # PF-02 backup lock
    lock = target_home / ".backup.lock"
    if lock.exists() and time.time() - _mtime(lock) < 15 * 60:
        gates.append(Gate("PF-02", "A hermes backup is running", "refuse",
                          "the .backup.lock is fresh", "wait a minute and retry"))
    else:
        gates.append(Gate("PF-02", "No backup in flight", "ok"))

    # PF-03 update marker
    marker = target_home / ".hermes-update-in-progress"
    if marker.exists() and time.time() - _mtime(marker) < 20 * 60:
        gates.append(Gate("PF-03", "A Hermes update is running", "refuse",
                          "fresh .hermes-update-in-progress marker",
                          "let the update finish first"))
    else:
        gates.append(Gate("PF-03", "No update in flight", "ok"))

    # PF-04 disk space (payload × 2.2: stage + backup + slack)
    payload = int((manifest.get("bytes") or {}).get("payload", 0))
    needed = int(payload * 2.2) + 64 * 1024 * 1024
    free = free_bytes(target_home if target_home.exists() else target_home.parent)
    if free < needed:
        gates.append(Gate("PF-04", "Not enough disk space", "refuse",
                          f"{needed // (1024**2)} MiB needed (payload ×2.2 for the "
                          f"safety copy), {free // (1024**2)} MiB free",
                          "free space and retry"))
    else:
        gates.append(Gate("PF-04", "Enough disk space", "ok",
                          f"{free // (1024**2)} MiB free"))

    # PF-05 managed / container target
    if (target_home / ".managed").exists() or os.environ.get("HERMES_MANAGED"):
        gates.append(Gate("PF-05", "Managed install", "refuse",
                          "this Hermes is managed (NixOS/admin scope); restoring plain "
                          "state would fight the activation system",
                          "migrate via the platform's own configuration instead"))
    elif Path("/.dockerenv").exists() and not os.environ.get("TALARIA_ALLOW_CONTAINER"):
        gates.append(Gate("PF-05", "Container target", "refuse",
                          "applying inside a running container image is not supported "
                          "in v1", "migrate the data volume instead"))
    else:
        gates.append(Gate("PF-05", "Plain install target", "ok"))

    # PF-06/PF-07 version skew & hermes presence
    report.skew_class, skew_gate, report.hermes_present = _skew_gate(manifest,
                                                                     target_home)
    gates.append(skew_gate)

    # PF-08 WAL-hostile filesystem
    fstype = fs_type_of(target_home if target_home.exists() else target_home.parent)
    if is_wal_hostile(fstype):
        gates.append(Gate("PF-08", "Network filesystem", "warn",
                          f"{fstype} does not support SQLite WAL safely; Hermes will "
                          "fall back to journal_mode=delete",
                          "consider setting database.journal_mode: delete explicitly"))
    else:
        gates.append(Gate("PF-08", "Filesystem supports WAL", "ok", fstype))

    # PF-09 one-shot jobs past grace
    stale_oneshots = _stale_oneshots(reader)
    if stale_oneshots:
        gates.append(Gate("PF-09", "One-time jobs already due", "warn",
                          f"{len(stale_oneshots)} one-shot job(s) passed their fire time "
                          "during the move: " + ", ".join(stale_oneshots),
                          "re-schedule them after the move (they will not auto-fire)"))
    else:
        gates.append(Gate("PF-09", "Scheduled times fine", "ok"))

    # PF-10 timezone
    src_tz = (manifest.get("source") or {}).get("tz") or {}
    local_offset = -time.timezone // 60 if not time.daylight else -time.altzone // 60
    msg = tz_mismatch((src_tz.get("name"), src_tz.get("utc_offset_min"),
                       src_tz.get("dst")),
                      (time.tzname[0], local_offset, bool(time.daylight)))
    if msg:
        gates.append(Gate("PF-10", "Timezone changed", "warn", msg,
                          "pin `timezone:` in config.yaml to keep schedules meaning "
                          "the same wall-clock times"))
    else:
        gates.append(Gate("PF-10", "Timezone matches", "ok"))

    # PF-11 lived-in target → conflict preview
    report.conflicts = _find_conflicts(reader, target_home)
    if report.conflicts:
        gates.append(Gate("PF-11", "This machine already has Hermes data", "consent",
                          f"{len(report.conflicts)} file(s) here differ from the bundle "
                          "(first: " + report.conflicts[0] + ")",
                          "wizard: replace with a safety copy; CLI: --conflict "
                          "keep|overwrite|rename|ask"))
    else:
        gates.append(Gate("PF-11", "Clean target", "ok"))

    # PF-12 schema — enforced at open; record it
    gates.append(Gate("PF-12", "Bundle format supported", "ok",
                      f"schema {manifest.get('schema_version')}"))

    # PF-13 executable content summary
    report.executable_summary = _executable_summary(reader)
    if any(report.executable_summary.values()):
        detail = ", ".join(f"{v} {k}" for k, v in report.executable_summary.items() if v)
        gates.append(Gate("PF-13", "This bundle contains things that run", "consent",
                          detail + " — applying a bundle is installing software",
                          "review the list; apply only bundles you created or trust"))
    else:
        gates.append(Gate("PF-13", "No executable content", "ok"))

    # PF-14/PF-15 filename legality + collisions vs the REAL filesystem behavior
    member_rels = [m.home_rel for m in reader.iter_payload()]
    scratch = scratch_dir or (target_home if target_home.exists()
                              else target_home.parent)
    behavior = probe_behavior(Path(scratch))
    if os.name == "nt":  # pragma: no cover
        illegal = [r for r in member_rels if windows_path_problems(r)]
        if illegal:
            report.rename_map = build_rename_map(member_rels)
            gates.append(Gate("PF-14", "Names not legal here", "consent",
                              f"{len(illegal)} file name(s) cannot exist on Windows",
                              "they will be placed under the recorded rename map"))
    if behavior.case_insensitive or behavior.normalizes_unicode:
        collisions = find_collisions(member_rels)
        if collisions:
            flat = ["/".join(g) for g in collisions[:3]]
            report.rename_map.update(build_rename_map(
                [p for group in collisions for p in group[1:]]))
            gates.append(Gate("PF-15", "Names collide on this filesystem", "consent",
                              f"{len(collisions)} group(s) differ only by case or accent "
                              "form (e.g. " + "; ".join(flat) + ")",
                              "colliding files land under the recorded rename plan"))
        else:
            gates.append(Gate("PF-15", "No name collisions", "ok"))
    else:
        gates.append(Gate("PF-15", "Case-sensitive filesystem", "ok"))

    # PF-16 long paths
    flavor = WINDOWS_FLAVOR if os.name == "nt" else POSIX_FLAVOR
    if flavor.max_path:
        length, worst = longest_final_path(str(target_home), member_rels, flavor)
        from talaria.platform.winreg_compat import long_paths_enabled

        if length >= flavor.max_path and not long_paths_enabled():
            gates.append(Gate("PF-16", "Very long paths", "warn",
                              f"longest final path is {length} chars ({worst[:80]}…) and "
                              "LongPathsEnabled is off",
                              "enable Windows long paths or shorten the target location"))

    # PF-17 unrecognized files
    unrecognized = manifest.get("unrecognized") or []
    if unrecognized:
        gates.append(Gate("PF-17", "Files Hermes doesn't own", "consent",
                          f"{len(unrecognized)} unrecognized file(s) travel in this "
                          "bundle (they passed the content safety scan at pack time)",
                          "they are listed in the consent summary; CLI: "
                          "--include-unrecognized places them"))

    # PF-18 external members
    externals = [m.member for m in reader.iter_payload()
                 if m.member.startswith("payload/external/")]
    if externals:
        gates.append(Gate("PF-18", "Files outside the Hermes folder", "consent",
                          f"{len(externals)} file(s) restore outside HERMES_HOME "
                          "(memory-provider state under your home directory)",
                          "each destination is shown before it is written"))
    return report


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _skew_gate(manifest: dict, target_home: Path) -> Tuple[str, Gate, bool]:
    source = manifest.get("source") or {}
    src_ver = source.get("hermes_version")
    ident = detect_identity(target_home, run_venv_probe=False)
    present = ident.install_dir is not None
    tgt_ver = ident.hermes_version
    if not present:
        return "UNKNOWN", Gate(
            "PF-06", "Hermes is not installed here", "warn",
            "state will be placed, and Hermes installed afterwards will adopt it",
            "install Hermes with the official command, then run `talaria verify`"), False
    if src_ver and tgt_ver:
        if src_ver == tgt_ver:
            return "EXACT", Gate("PF-06", "Same Hermes version", "ok",
                                 f"{src_ver} on both machines"), True
        if _version_tuple(tgt_ver) > _version_tuple(src_ver):
            cfg_ver = source.get("config_version")
            if isinstance(cfg_ver, int) and cfg_ver < 12:
                return "FLOOR-BREACH", Gate(
                    "PF-06", "Config too old to migrate forward", "refuse",
                    f"source config version {cfg_ver} is below upstream's floor (12)",
                    "run `hermes setup` on the OLD machine, re-pack, then retry"), True
            return "FORWARD-OK", Gate(
                "PF-06", "Newer Hermes here", "ok",
                f"{src_ver} → {tgt_ver}; Hermes migrates config forward on first "
                "start"), True
        return "BLOCKED-DOWNGRADE", Gate(
            "PF-06", "This machine runs an older Hermes", "refuse",
            f"bundle from {src_ver}, this machine has {tgt_ver}; downgrading state is "
            "refused",
            f"update Hermes here (`hermes update`), or install the matching version"), True
    return "UNKNOWN", Gate("PF-06", "Version unknown", "warn",
                           "could not read one of the versions",
                           "pass --force-skew to proceed anyway (recorded)"), present


def _version_tuple(v: str) -> tuple:
    parts = []
    for piece in str(v).split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _stale_oneshots(reader: BundleReader) -> List[str]:
    import json as _json

    stale: List[str] = []
    for rec in reader.iter_payload():
        if not rec.home_rel.endswith("cron/jobs.json") and rec.home_rel != "cron/jobs.json":
            continue
        try:
            assert reader.zf is not None
            data = _json.loads(reader.zf.read(rec.member).decode("utf-8-sig"))
        except (KeyError, ValueError, AssertionError):
            continue
        for job in data.get("jobs", []):
            sched = job.get("schedule") or {}
            if sched.get("kind") == "once" and job.get("enabled") \
                    and job.get("state") == "scheduled":
                run_at = parse_rfc3339(str(sched.get("run_at", "")))
                if run_at is not None:
                    import datetime

                    now = datetime.datetime.now(datetime.timezone.utc)
                    if run_at.tzinfo is None:
                        run_at = run_at.replace(tzinfo=datetime.timezone.utc)
                    if (now - run_at).total_seconds() > 120:
                        stale.append(job.get("name") or job.get("id", "?"))
    return stale


def _find_conflicts(reader: BundleReader, target_home: Path) -> List[str]:
    """Root-relative paths that already exist on the target (a lived-in install).

    Existence is the conflict signal for PF-11's consent gate; content-level decisions
    happen per file during APPLY under the chosen conflict policy.
    """
    conflicts: List[str] = []
    for rec in reader.iter_payload():
        if not rec.member.startswith(PAYLOAD_HOME):
            continue
        root_rel = rec.member[len(PAYLOAD_HOME):]
        if (target_home / root_rel).exists():
            conflicts.append(root_rel)
    return conflicts


def _executable_summary(reader: BundleReader) -> Dict[str, int]:
    """PF-13: counts of things that will RUN once Hermes starts (C1 SEC-09)."""
    counts = {"plugins": 0, "hooks": 0, "cron scripts": 0, "skill scripts": 0,
              "MCP stdio commands": 0}
    for rec in reader.iter_payload():
        rel = rec.home_rel
        if rel.startswith("plugins/") and rel.endswith((".py", ".sh")):
            counts["plugins"] += 1
        elif rel.startswith("hooks/"):
            counts["hooks"] += 1
        elif rel.startswith("scripts/"):
            counts["cron scripts"] += 1
        elif rel.startswith("skills/") and "/scripts/" in rel:
            counts["skill scripts"] += 1
    for ref in json_loads_safe(reader.read_meta("machine_refs.json")) or []:
        if isinstance(ref, dict) and ref.get("locator", "").startswith("mcp_servers.") \
                and ref.get("locator", "").endswith(".command"):
            counts["MCP stdio commands"] += 1
    return counts


def json_loads_safe(blob):
    import json as _json

    if not blob:
        return None
    try:
        return _json.loads(blob)
    except ValueError:
        return None
