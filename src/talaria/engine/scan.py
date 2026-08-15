"""Scanner: walk a Hermes root, classify everything, chase references (ARCHITECTURE §4).

Metadata-only and read-only (R-SCAN-06/09): stat + classify, no hashing, no writes, symlinks
recorded but never followed, exclusions pruned at descent. Output is the typed inventory the
rest of the pipeline consumes.
"""

from __future__ import annotations

import json
import os
import stat as stat_mod
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from talaria.engine import yamlmini
from talaria.engine.resolve import (
    InstallIdentity,
    detect_identity,
    profile_homes,
    resolve_root_and_profile,
)
from talaria.engine.sqlite_snap import is_sqlite_file
from talaria.model.artifact import Artifact, Dependency, FileEntry, Touchpoint, artifact_id
from talaria.model.catalog import UNRECOGNIZED_KIND, classify, should_prune
from talaria.model.secrets_registry import scan_text_for_secrets
from talaria.platform.process import pid_alive

UNRECOGNIZED_TEXT_SCAN_CAP = 1024 * 1024  # 1 MiB (R-SCAN-10)
UPDATE_MARKER_FRESH_SECONDS = 20 * 60
BACKUP_LOCK_FRESH_SECONDS = 15 * 60


@dataclass
class MachineRef:
    """One machine-specific reference found inside carried data (feeds the rewrite planner)."""

    profile: str
    file: str            # home-relative POSIX path of the file holding the reference
    format: str          # yaml|json|dotenv|frontmatter
    locator: str         # dotted key path / JSON pointer-ish locator
    value: str
    ref_kind: str        # path|url|localhost-url|home-path|external-dir|script|workdir

    def to_json(self) -> dict:
        return self.__dict__.copy()


@dataclass
class ScanResult:
    identity: InstallIdentity
    artifacts: List[Artifact]
    touchpoints: List[Touchpoint]
    machine_refs: List[MachineRef]
    warnings: List[str] = field(default_factory=list)
    refusals: List[str] = field(default_factory=list)
    capture_mode: str = "quiesced"          # quiesced|live
    excluded_counts: Dict[str, int] = field(default_factory=dict)
    config: Dict[str, dict] = field(default_factory=dict)   # per-profile parsed config
    cron_jobs: Dict[str, list] = field(default_factory=dict)  # per-profile job records
    scanned_files: int = 0
    scanned_bytes: int = 0

    def artifact(self, art_id: str) -> Optional[Artifact]:
        for art in self.artifacts:
            if art.id == art_id:
                return art
        return None

    def by_kind(self, kind: str, profile: str = "") -> List[Artifact]:
        return [a for a in self.artifacts if a.kind == kind and a.profile == profile]


def scan(home: Path, on_item: Optional[Callable[[str], None]] = None,
         run_venv_probe: bool = False) -> ScanResult:
    """Scan the install anchored at the ROOT above ``home`` (R-SCAN-02)."""
    home = Path(home)
    root, _active = resolve_root_and_profile(home)
    identity = detect_identity(home, run_venv_probe=run_venv_probe)
    result = ScanResult(identity=identity, artifacts=[], touchpoints=[], machine_refs=[])

    _live_install_etiquette(root, result)

    groups: Dict[Tuple[str, str, str], Artifact] = {}
    for profile, phome in profile_homes(root).items():
        if profile:  # skip the profiles/ subtree during the root walk; walked here instead
            _walk_profile(root, phome, profile, groups, result, on_item)
    _walk_profile(root, root, "", groups, result, on_item, skip_profiles_subtree=True)

    result.artifacts = sorted(groups.values(), key=lambda a: (a.profile, a.family, a.id))

    for profile, phome in profile_homes(root).items():
        _chase_references(phome, profile, result)

    _apply_unrecognized_gates(root, result)
    return result


# --------------------------------------------------------------------------- walking

def _walk_profile(root: Path, phome: Path, profile: str,
                  groups: Dict[Tuple[str, str, str], Artifact], result: ScanResult,
                  on_item: Optional[Callable[[str], None]],
                  skip_profiles_subtree: bool = False) -> None:
    prefix_parts: Tuple[str, ...] = ()

    def visit_dir(dir_path: Path, rel_parts: Tuple[str, ...]) -> None:
        try:
            entries = sorted(os.scandir(dir_path), key=lambda e: e.name)
        except OSError as exc:
            result.warnings.append(f"unreadable directory {dir_path}: {exc}")
            return
        for entry in entries:
            name = entry.name
            child_parts = rel_parts + (name,)
            if skip_profiles_subtree and rel_parts == () and name == "profiles":
                continue
            try:
                is_symlink = entry.is_symlink()
                if is_symlink:
                    _record_file(entry, child_parts, profile, groups, result,
                                 symlink=True)
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if should_prune(child_parts):
                        result.excluded_counts["pruned-dirs"] = \
                            result.excluded_counts.get("pruned-dirs", 0) + 1
                        continue
                    visit_dir(Path(entry.path), child_parts)
                elif entry.is_file(follow_symlinks=False):
                    _record_file(entry, child_parts, profile, groups, result)
                    if on_item is not None and result.scanned_files % 500 == 0:
                        on_item("/".join(child_parts))
            except OSError as exc:
                result.warnings.append(f"unreadable {entry.path}: {exc}")

    visit_dir(phome, prefix_parts)


def _record_file(entry, rel_parts: Tuple[str, ...], profile: str,
                 groups: Dict[Tuple[str, str, str], Artifact], result: ScanResult,
                 symlink: bool = False) -> None:
    rel_posix = "/".join(rel_parts)
    cls = classify(rel_posix, profile)
    if cls.excluded is not None:
        key = cls.excluded.id
        result.excluded_counts[key] = result.excluded_counts.get(key, 0) + 1
        # Excluded artifacts still appear (once per exclusion id) so nothing is silent.
        akey = (profile, cls.kind, cls.group_key)
        if akey not in groups:
            groups[akey] = Artifact(
                id=artifact_id(cls.kind, profile), kind=cls.kind, family=cls.family,
                profile=profile, portability=cls.portability, secrecy=cls.secrecy,
                machine_bound=True, default="never", selected=False,
                reasons=[f"{cls.reason} [{cls.excluded.citation}]"])
        return

    try:
        st = entry.stat(follow_symlinks=False)
        size = st.st_size
        mode = stat_mod.S_IMODE(st.st_mode)
        mtime = st.st_mtime
    except OSError:
        size, mode, mtime = 0, 0o644, 0.0

    fe = FileEntry(home_rel=rel_posix, size=size, mode=mode, mtime=mtime,
                   is_symlink=symlink)
    if not symlink and (rel_posix.endswith(".db") or rel_posix.endswith(".sqlite")):
        fe.is_sqlite = is_sqlite_file(Path(entry.path))

    akey = (profile, cls.kind, cls.group_key)
    art = groups.get(akey)
    if art is None:
        discriminator = cls.group_key.rsplit("/", 1)[-1] if cls.group_key else ""
        art = Artifact(
            id=artifact_id(cls.kind, profile, discriminator), kind=cls.kind,
            family=cls.family, profile=profile, portability=cls.portability,
            secrecy=cls.secrecy, machine_bound=cls.machine_bound, default=cls.default,
            selected=cls.default == "on", reasons=[cls.reason] if cls.reason else [])
        groups[akey] = art
    if cls.secrecy == "credential" and art.secrecy == "none":
        art.secrecy = "credential"
    art.files.append(fe)
    result.scanned_files += 1
    result.scanned_bytes += size


# --------------------------------------------------------------------------- etiquette

def _live_install_etiquette(root: Path, result: ScanResult) -> None:
    """R-SCAN-09: read-only checks for live-install hazards."""
    update_marker = root / ".hermes-update-in-progress"
    if update_marker.exists():
        try:
            age = time.time() - update_marker.stat().st_mtime
        except OSError:
            age = 0
        if age < UPDATE_MARKER_FRESH_SECONDS:
            result.refusals.append(
                "a Hermes update is in progress (fresh .hermes-update-in-progress); "
                "capture refused until it finishes")

    backup_lock = root / ".backup.lock"
    if backup_lock.exists():
        try:
            age = time.time() - backup_lock.stat().st_mtime
        except OSError:
            age = 0
        if age < BACKUP_LOCK_FRESH_SECONDS:
            result.warnings.append(
                "hermes backup holds its lock — capture will wait for it, never take it")

    gateway_pid = _read_pid(root / "gateway.pid")
    if gateway_pid and pid_alive(gateway_pid):
        result.capture_mode = "live"
        result.warnings.append(
            "the Hermes gateway is running — capture proceeds read-only, but files may "
            "change while packing (cross-file skew); for a perfectly consistent bundle run "
            "`hermes gateway stop` first")
    else:
        cron_pid = _read_pid(root / "cron.pid")
        if cron_pid and pid_alive(cron_pid):
            result.capture_mode = "live"
            result.warnings.append("the cron ticker is running — same live-capture caveat")


def _read_pid(path: Path) -> Optional[int]:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------- references

_LOCALHOST_MARKERS = ("127.0.0.1", "localhost", "0.0.0.0", "[::1]")

#: config.yaml keys that hold machine-specific paths/URLs (state §7; ARCH §4.3).
_CONFIG_REF_KEYS: Tuple[Tuple[str, str], ...] = (
    ("terminal.cwd", "workdir"),
    ("prefill_messages_file", "path"),
    ("model.base_url", "url"),
    ("dashboard.public_url", "url"),
    ("cron.chronos.callback_url", "url"),
)


def _chase_references(phome: Path, profile: str, result: ScanResult) -> None:
    cfg = _load_config(phome)
    if cfg:
        result.config[profile] = cfg
        _chase_config(cfg, phome, profile, result)
    jobs = _load_jobs(phome)
    if jobs is not None:
        result.cron_jobs[profile] = jobs
        _chase_jobs(jobs, phome, profile, result)
    _chase_memory_provider(cfg or {}, phome, profile, result)


def _load_config(phome: Path) -> Optional[dict]:
    config_path = phome / "config.yaml"
    if not config_path.is_file():
        return None
    try:
        return yamlmini.parse(config_path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None


def _load_jobs(phome: Path) -> Optional[list]:
    jobs_path = phome / "cron" / "jobs.json"
    if not jobs_path.is_file():
        return None
    try:
        data = json.loads(jobs_path.read_text(encoding="utf-8-sig", errors="replace"))
        jobs = data.get("jobs", [])
        return jobs if isinstance(jobs, list) else []
    except (OSError, ValueError):
        return []


def _touch(result: ScanResult, phome: Path, path_value: str, provenance: str,
           verdict: str = "") -> None:
    expanded = os.path.expanduser(path_value)
    exists: Optional[bool]
    try:
        exists = os.path.lexists(expanded)
    except OSError:
        exists = None
    inside = None
    try:
        home_dir = str(Path.home())
        inside = os.path.abspath(expanded).startswith(home_dir)
    except OSError:
        pass
    result.touchpoints.append(Touchpoint(
        path=path_value, provenance=[provenance], confidence="verified",
        verdict=verdict, exists=exists, inside_home=inside))


def _chase_config(cfg: dict, phome: Path, profile: str, result: ScanResult) -> None:
    for dotted, ref_kind in _CONFIG_REF_KEYS:
        value = yamlmini.get_path(cfg, dotted)
        if not isinstance(value, str) or not value:
            continue
        kind = ref_kind
        if ref_kind == "url" and any(m in value for m in _LOCALHOST_MARKERS):
            kind = "localhost-url"
        result.machine_refs.append(MachineRef(profile, "config.yaml", "yaml", dotted,
                                              value, kind))
        if ref_kind != "url":
            _touch(result, phome, value, "config-ref")

    for ext in yamlmini.get_path(cfg, "skills.external_dirs", []) or []:
        if isinstance(ext, str):
            result.machine_refs.append(MachineRef(profile, "config.yaml", "yaml",
                                                  "skills.external_dirs[]", ext,
                                                  "external-dir"))
            _touch(result, phome, ext, "config-ref", "external skill dir")

    servers = yamlmini.get_path(cfg, "mcp_servers", {}) or {}
    if isinstance(servers, dict):
        for name, entry in servers.items():
            if not isinstance(entry, dict):
                continue
            command = entry.get("command")
            if isinstance(command, str) and ("/" in command or "\\" in command):
                result.machine_refs.append(MachineRef(
                    profile, "config.yaml", "yaml", f"mcp_servers.{name}.command",
                    command, "path"))
                _touch(result, phome, command, "config-ref", "mcp stdio command")
            for i, arg in enumerate(entry.get("args") or []):
                if isinstance(arg, str) and (arg.startswith("/") or
                                             (len(arg) > 2 and arg[1] == ":")):
                    result.machine_refs.append(MachineRef(
                        profile, "config.yaml", "yaml",
                        f"mcp_servers.{name}.args[{i}]", arg, "path"))
                    _touch(result, phome, arg, "config-ref")
            cwd = entry.get("cwd")
            if isinstance(cwd, str) and cwd:
                result.machine_refs.append(MachineRef(
                    profile, "config.yaml", "yaml", f"mcp_servers.{name}.cwd", cwd,
                    "workdir"))
                _touch(result, phome, cwd, "config-ref")


def _chase_jobs(jobs: list, phome: Path, profile: str, result: ScanResult) -> None:
    for job in jobs:
        if not isinstance(job, dict):
            continue
        jid = str(job.get("id", "?"))
        script = job.get("script") or job.get("monitor_script")
        if isinstance(script, str) and script:
            kind = "script"
            locator = f"jobs[id={jid}].script"
            result.machine_refs.append(MachineRef(profile, "cron/jobs.json", "json",
                                                  locator, script, kind))
            script_path = script if os.path.isabs(script) else str(phome / "scripts" / script)
            _touch(result, phome, script_path, "cron-ref", "job script")
        workdir = job.get("workdir")
        if isinstance(workdir, str) and workdir:
            result.machine_refs.append(MachineRef(profile, "cron/jobs.json", "json",
                                                  f"jobs[id={jid}].workdir", workdir,
                                                  "workdir"))
            _touch(result, phome, workdir, "cron-ref", "job workdir")
        for i, skill_ref in enumerate(job.get("skills") or []):
            if isinstance(skill_ref, str) and (os.path.isabs(skill_ref) or "\\" in skill_ref):
                result.machine_refs.append(MachineRef(
                    profile, "cron/jobs.json", "json", f"jobs[id={jid}].skills[{i}]",
                    skill_ref, "path"))
                _touch(result, phome, skill_ref, "cron-ref", "absolute skill reference")
        monitor_url = job.get("monitor_url")
        if isinstance(monitor_url, str) and monitor_url:
            kind = ("localhost-url" if any(m in monitor_url for m in _LOCALHOST_MARKERS)
                    else "url")
            result.machine_refs.append(MachineRef(profile, "cron/jobs.json", "json",
                                                  f"jobs[id={jid}].monitor_url",
                                                  monitor_url, kind))


_MEMORY_EXTERNAL = {
    "honcho": "~/.honcho",
    "hindsight": "~/.hindsight",
    "openviking": "~/.openviking/ovcli.conf",
}


def _chase_memory_provider(cfg: dict, phome: Path, profile: str, result: ScanResult) -> None:
    provider = yamlmini.get_path(cfg, "memory.provider")
    if isinstance(provider, str) and provider in _MEMORY_EXTERNAL:
        target = _MEMORY_EXTERNAL[provider]
        result.machine_refs.append(MachineRef(profile, "config.yaml", "yaml",
                                              "memory.provider", target, "external-dir"))
        _touch(result, phome, target, "config-ref", f"memory provider '{provider}' state")


# --------------------------------------------------------------------------- unrecognized

def _apply_unrecognized_gates(root: Path, result: ScanResult) -> None:
    """R-SCAN-10/D9: content-scan small text unknowns; suspicious ⇒ credential handling."""
    for art in result.artifacts:
        if art.kind != UNRECOGNIZED_KIND:
            continue
        for fe in art.files:
            if fe.is_symlink:
                art.default = "record_only"
                art.selected = False
                art.reasons.append("symlink — recorded, never followed (R-SCAN-05)")
                continue
            if art.secrecy == "credential":
                art.default = "record_only"
                art.selected = False
                art.reasons.append("name suggests credential material — carried only via "
                                   "secrets handling (D9 gate)")
                continue
            if fe.size > UNRECOGNIZED_TEXT_SCAN_CAP:
                art.default = "record_only"
                art.selected = False
                art.reasons.append("large unrecognized file — recorded, not carried by "
                                   "default (D9 gate)")
                continue
            profile_prefix = f"profiles/{art.profile}/" if art.profile else ""
            path = root / (profile_prefix + fe.home_rel)
            try:
                blob = path.read_bytes()
            except OSError:
                continue
            if b"\x00" in blob[:4096]:
                art.default = "record_only"
                art.selected = False
                art.reasons.append("binary unrecognized file — recorded, not carried by "
                                   "default (D9 gate)")
                continue
            hits = scan_text_for_secrets(blob.decode("utf-8", errors="replace"))
            if hits:
                art.secrecy = "credential"
                art.default = "record_only"
                art.selected = False
                art.reasons.append(
                    "content scan matched secret patterns (" + ", ".join(sorted(set(hits)))
                    + ") — quarantined to credential handling (R-SCAN-10)")
