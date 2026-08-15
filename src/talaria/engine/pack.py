"""The streaming packer: SCAN → SNAPSHOT → PACK → SELF-VERIFY → PUBLISH (ARCH §8).

Every payload file is read once, hashed in the same pass as the zip write (R-PACK-01);
SQLite goes through the snapshot protocol; output is atomic (`.partial` → `os.replace`)
and self-verified before publish. Credential-class artifacts never enter the payload in
plaintext — checklist by default, vault members when enabled (R-SEC-01).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from talaria import BUNDLE_FORMAT_VERSION, __version__
from talaria.engine import deps as deps_engine
from talaria.engine.bundle import (
    MANIFEST_NAME,
    PAYLOAD_EXTERNAL,
    PAYLOAD_HOME,
    STUB_NAME,
    BundleReader,
)
from talaria.engine.diffs import checkout_state
from talaria.engine.provenance import HashSemantics, classify_skills
from talaria.engine.scan import ScanResult
from talaria.engine.sqlite_snap import SqliteSnapshotError, snapshot_db
from talaria.errors import EXIT_CAPTURE_FAILED, Refusal, TalariaError
from talaria.events import EventLog
from talaria.model.artifact import Artifact
from talaria.model.catalog import exclusion_for
from talaria.model.secrets_registry import EXTERNAL_ALLOWLIST, is_secret_env_name
from talaria.model.selection import Selection, apply_selection, validate_couples
from talaria.platform.fsprobe import FAT_FILE_CAP, free_bytes, fs_type_of, is_fat_like
from talaria.platform.paths import find_collisions, windows_path_problems

CHUNK = 1024 * 1024
DB_SOFT_CAP = 8 * 1024 * 1024 * 1024  # 8 GiB (`--db-cap` overrides)


@dataclass
class PackOptions:
    selection: Selection = field(default_factory=Selection)
    intent: str = "replace"                  # replace|clone
    vault_passphrase: Optional[str] = None   # None = checklist mode
    lock_everything: bool = False
    db_cap_bytes: int = DB_SOFT_CAP
    db_cap_confirmed: bool = False
    require_quiesced: bool = False
    hold_secrets: bool = True                # False only under --vault


@dataclass
class PackResult:
    bundle_path: Path
    manifest: dict
    checklist: List[dict]
    warnings: List[str] = field(default_factory=list)
    members_written: int = 0
    bytes_written: int = 0


def pack(scan_result: ScanResult, out_path: Path, options: Optional[PackOptions] = None,
         log: Optional[EventLog] = None) -> PackResult:
    options = options or PackOptions()
    log = log or EventLog()
    out_path = Path(out_path)
    root = Path(scan_result.identity.root)

    _refuse_if_blocked(scan_result, options)
    apply_selection(scan_result.artifacts, options.selection)
    violations = [v for v in validate_couples(scan_result.artifacts,
                                              scan_result.cron_jobs, scan_result.config)]
    if violations:
        names = ", ".join(v.couple_id for v in violations)
        raise Refusal("TAL-208",
                      "the selection breaks hard couples: " + names + " — " +
                      "; ".join(v.message for v in violations),
                      detail={"violations": [v.to_json() for v in violations]})

    log.emit("phase", "pack", "Planning the bundle")
    plan = _build_plan(scan_result, options, log)
    _destination_prechecks(out_path, plan.total_bytes, log)

    staging = out_path.parent / f".talaria-pack-{os.getpid()}"
    partial = out_path.with_name(out_path.name + ".partial")
    try:
        staging.mkdir(parents=True, exist_ok=True)
        _snapshot_databases(root, plan, staging, options, log)
        manifest, checklist = _write_zip(scan_result, plan, options, partial, log)
        _registry_belt(manifest)
        log.emit("phase", "pack", "Double-checking the finished bundle")
        _self_verify(partial, manifest)
        os.replace(partial, out_path)
        try:
            os.chmod(out_path, 0o600)
        except OSError:
            pass
        log.emit("done", "pack", f"Bundle published: {out_path.name}")
        return PackResult(bundle_path=out_path, manifest=manifest, checklist=checklist,
                          warnings=list(scan_result.warnings),
                          members_written=len(manifest.get("artifacts", [])),
                          bytes_written=out_path.stat().st_size)
    except Exception:
        try:
            if partial.exists():
                partial.unlink()
        except OSError:
            pass
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)


# --------------------------------------------------------------------------- refusals

def _refuse_if_blocked(scan_result: ScanResult, options: PackOptions) -> None:
    if scan_result.refusals:
        raise Refusal("TAL-102", scan_result.refusals[0])
    if options.require_quiesced and scan_result.capture_mode == "live":
        raise Refusal("TAL-401",
                      "--require-quiesced set but the gateway/ticker is running",
                      fix="run `hermes gateway stop`, then pack again")


# --------------------------------------------------------------------------- planning

@dataclass
class _PlanEntry:
    member: str
    source: Path              # absolute file to read (may be replaced by a snapshot)
    root_rel: str             # path relative to HERMES root (with profiles/<n>/ prefix)
    home_rel: str             # profile-local path
    artifact: Artifact
    size: int
    mode: int
    mtime: float
    is_sqlite: bool = False
    vaulted: bool = False


@dataclass
class _Plan:
    entries: List[_PlanEntry] = field(default_factory=list)
    vault_entries: List[_PlanEntry] = field(default_factory=list)
    total_bytes: int = 0
    checklist: List[dict] = field(default_factory=list)
    external_entries: List[_PlanEntry] = field(default_factory=list)


def _root_rel(artifact: Artifact, home_rel: str) -> str:
    if artifact.profile:
        return f"profiles/{artifact.profile}/{home_rel}"
    return home_rel


def _build_plan(scan_result: ScanResult, options: PackOptions, log: EventLog) -> _Plan:
    plan = _Plan()
    root = Path(scan_result.identity.root)
    vault_on = options.vault_passphrase is not None
    for art in scan_result.artifacts:
        if not art.travels:
            continue
        credential = art.secrecy == "credential"
        vaulted_content = options.lock_everything and art.secrecy == "content" and vault_on
        for fe in art.files:
            if fe.is_symlink:
                continue
            root_rel = _root_rel(art, fe.home_rel)
            source = root / root_rel
            entry = _PlanEntry(
                member=PAYLOAD_HOME + root_rel, source=source, root_rel=root_rel,
                home_rel=fe.home_rel, artifact=art, size=fe.size, mode=fe.mode,
                mtime=fe.mtime, is_sqlite=fe.is_sqlite)
            if credential:
                _checklist_from_credential(plan, root, art, fe.home_rel, source)
                if vault_on:
                    entry.vaulted = True
                    plan.vault_entries.append(entry)
                    plan.total_bytes += fe.size
                continue  # never a plaintext payload member (R-SEC-01)
            if vaulted_content:
                entry.vaulted = True
                plan.vault_entries.append(entry)
                plan.total_bytes += fe.size
                continue
            plan.entries.append(entry)
            plan.total_bytes += fe.size

    _plan_external(scan_result, plan, log)
    return plan


def _plan_external(scan_result: ScanResult, plan: _Plan, log: EventLog) -> None:
    """Memory-provider external dirs → payload/external/home/<rel> (D16 allowlist)."""
    home_dir = Path.home()
    seen: Set[str] = set()
    for ref in scan_result.machine_refs:
        if ref.ref_kind != "external-dir" or ref.locator != "memory.provider":
            continue
        target = Path(os.path.expanduser(ref.value))
        key = str(target)
        if key in seen or not target.exists():
            continue
        seen.add(key)
        allowed = any(os.path.expanduser(a) == str(target) or
                      str(target).startswith(os.path.expanduser(a).rstrip("/"))
                      for a in EXTERNAL_ALLOWLIST)
        if not allowed:
            log.emit("warn", "pack", f"external path {ref.value} is outside the "
                                     "allowlist — recorded, not packed")
            continue
        files = [target] if target.is_file() else \
            [p for p in target.rglob("*") if p.is_file()]
        for f in files:
            try:
                rel = f.relative_to(home_dir).as_posix()
            except ValueError:
                continue  # not under home — record-only (D16)
            try:
                st = f.stat()
            except OSError:
                continue
            synthetic = Artifact(id=f"external-state@/{ref.value}", kind="external-state",
                                 family="external-state", profile="", portability="a",
                                 secrecy="content", default="on", selected=True)
            plan.external_entries.append(_PlanEntry(
                member=PAYLOAD_EXTERNAL + rel, source=f, root_rel="", home_rel=rel,
                artifact=synthetic, size=st.st_size, mode=st.st_mode & 0o777,
                mtime=st.st_mtime))
            plan.total_bytes += st.st_size


def _checklist_from_credential(plan: _Plan, root: Path, art: Artifact, home_rel: str,
                               source: Path) -> None:
    """Secrets Handoff entries: names + where-used, never values (R-SEC-03)."""
    if home_rel.endswith(".env"):
        try:
            for line in source.read_text(encoding="utf-8-sig",
                                         errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name = line.split("=", 1)[0].strip()
                if name:
                    plan.checklist.append({
                        "name": name, "file": home_rel,
                        "secret": is_secret_env_name(name),
                        "profile": art.profile})
        except OSError:
            pass
    else:
        plan.checklist.append({"name": home_rel.rsplit("/", 1)[-1], "file": home_rel,
                               "secret": True, "profile": art.profile,
                               "kind": art.kind})


# --------------------------------------------------------------------------- prechecks

def _destination_prechecks(out_path: Path, estimate: int, log: EventLog) -> None:
    parent = out_path.parent
    free = free_bytes(parent)
    if estimate and free < estimate * 1.1 + 64 * 1024 * 1024:
        raise Refusal("TAL-202",
                      f"about {estimate // (1024 * 1024)} MiB needed but only "
                      f"{free // (1024 * 1024)} MiB free at {parent}",
                      fix="free space or choose another save location",
                      exit_code=EXIT_CAPTURE_FAILED)
    fstype = fs_type_of(parent)
    if is_fat_like(fstype) and estimate > FAT_FILE_CAP:
        raise Refusal("TAL-203",
                      f"the destination filesystem ({fstype}) caps files at 4 GiB but "
                      f"this bundle is about {estimate // (1024 ** 3)} GiB",
                      fix="save to another drive or shrink the selection",
                      exit_code=EXIT_CAPTURE_FAILED)


# --------------------------------------------------------------------------- snapshots

def _snapshot_databases(root: Path, plan: _Plan, staging: Path, options: PackOptions,
                        log: EventLog) -> None:
    log.emit("phase", "snapshot", "Taking safe copies of live databases")
    for entry in plan.entries + plan.vault_entries:
        if not entry.is_sqlite:
            continue
        if entry.size > options.db_cap_bytes and not options.db_cap_confirmed:
            raise Refusal("TAL-201",
                          f"{entry.root_rel} is {entry.size // (1024 ** 3)} GiB — over "
                          f"the {options.db_cap_bytes // (1024 ** 3)} GiB cap",
                          fix="re-run with --db-cap raised to confirm, or deselect it")
        snap_path = staging / entry.root_rel.replace("/", "_")
        attempts = 0
        while True:
            attempts += 1
            try:
                snapshot_db(entry.source, snap_path)
                break
            except SqliteSnapshotError as exc:
                if attempts >= 3:
                    raise Refusal(
                        "TAL-201", f"{entry.root_rel}: {exc}",
                        fix="stop the gateway (`hermes gateway stop`) so the database "
                            "quiesces, then pack again",
                        exit_code=EXIT_CAPTURE_FAILED)
                time.sleep(0.5 * attempts)
        entry.source = snap_path
        entry.size = snap_path.stat().st_size
        log.emit("item", "snapshot", entry.root_rel)


# --------------------------------------------------------------------------- writing

def _zipinfo_for(entry: _PlanEntry) -> zipfile.ZipInfo:
    dt = datetime.fromtimestamp(entry.mtime or time.time())
    zinfo = zipfile.ZipInfo(entry.member,
                            date_time=(max(dt.year, 1980), dt.month, dt.day,
                                       dt.hour, dt.minute, dt.second))
    zinfo.external_attr = (entry.mode & 0o777) << 16
    zinfo.compress_type = zipfile.ZIP_DEFLATED
    return zinfo


def _write_zip(scan_result: ScanResult, plan: _Plan, options: PackOptions,
               partial: Path, log: EventLog) -> Tuple[dict, List[dict]]:
    ident = scan_result.identity
    created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    bundle_id = hashlib.sha256(
        f"{ident.hermes_home}|{created_at}|{os.getpid()}".encode()).hexdigest()[:16]
    semantics = HashSemantics.for_os(ident.os_name)
    stub = {
        "schema_version": BUNDLE_FORMAT_VERSION,
        "min_reader_tool_version": "1.0.0",
        "created_by_tool_version": __version__,
        "created_at": created_at,
        "source": _source_snapshot(scan_result, semantics),
    }

    fd = os.open(partial, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    written_members: List[dict] = []
    vault_section: Optional[dict] = None
    log.emit("phase", "pack", "Packing your Hermes into one file")
    total = plan.total_bytes or 1
    done_bytes = 0
    with os.fdopen(fd, "wb") as raw, zipfile.ZipFile(raw, "w", allowZip64=True) as zf:
        zf.writestr(zipfile.ZipInfo(STUB_NAME), json.dumps(stub, indent=1),
                    compress_type=zipfile.ZIP_STORED)

        artifact_files: Dict[str, List[dict]] = {}
        for entry in plan.entries + plan.external_entries:
            digest, size = _stream_member(zf, entry)
            done_bytes += size
            log.emit("progress", "pack", entry.root_rel or entry.home_rel,
                     bytes_done=done_bytes, bytes_total=total)
            artifact_files.setdefault(entry.artifact.id, []).append({
                "member": entry.member, "home_rel": entry.home_rel, "size": size,
                "sha256": digest, "mode": entry.mode, "mtime": entry.mtime})

        if plan.vault_entries:
            from talaria.engine import vault as vault_mod

            vault_section, done_bytes = vault_mod.write_vault_members(
                zf, plan.vault_entries, options.vault_passphrase or "", bundle_id,
                BUNDLE_FORMAT_VERSION,
                scope="everything" if options.lock_everything else "credentials",
                progress=lambda inc: log.emit("progress", "pack", "vault",
                                              bytes_done=done_bytes + inc,
                                              bytes_total=total))

        _write_meta(zf, scan_result, semantics)

        manifest = dict(stub)
        manifest.update({
            "bundle_id": bundle_id,
            "intent": options.intent,
            "profiles": [""] + ident.profiles,
            "counts": {"files": sum(len(v) for v in artifact_files.values()),
                       "artifacts": len(artifact_files)},
            "bytes": {"payload": done_bytes},
            "artifacts": _manifest_artifacts(scan_result, artifact_files),
            "selection": options.selection.to_json(),
            "rewrite_anchors": {
                "source_home": str(Path.home()),
                "source_hermes_home": ident.hermes_home,
                "user": os.environ.get("USER") or os.environ.get("USERNAME") or "",
                "sep": "\\" if ident.layout_family == "windows" else "/",
            },
            "predictive": _predictive(plan),
            "checklist": {"items": _checklist_names(plan.checklist)},
            "unrecognized": [
                {"member": PAYLOAD_HOME + _root_rel(a, f.home_rel), "gate": "clean-text"}
                for a in scan_result.artifacts if a.kind == "unrecognized" and a.travels
                for f in a.files],
            "vault": vault_section or {"present": False},
            "compat": {"config_floor": 12, "notes": ident.notes},
            "capture_mode": scan_result.capture_mode,
            "hash_semantics": semantics.to_json(),
        })
        zf.writestr(zipfile.ZipInfo(MANIFEST_NAME), json.dumps(manifest, indent=1),
                    compress_type=zipfile.ZIP_STORED)
    return manifest, plan.checklist


def _stream_member(zf: zipfile.ZipFile, entry: _PlanEntry) -> Tuple[str, int]:
    """Read once, hash + write in the same pass (R-PACK-01)."""
    hasher = hashlib.sha256()
    size = 0
    zinfo = _zipinfo_for(entry)
    with open(entry.source, "rb") as src, zf.open(zinfo, "w") as out:
        while True:
            chunk = src.read(CHUNK)
            if not chunk:
                break
            hasher.update(chunk)
            size += len(chunk)
            out.write(chunk)
    return hasher.hexdigest(), size


def _write_meta(zf: zipfile.ZipFile, scan_result: ScanResult,
                semantics: HashSemantics) -> None:
    root = Path(scan_result.identity.root)
    prov = []
    skills_dir = root / "skills"
    if skills_dir.is_dir():
        prov = [p.to_json() for p in classify_skills(skills_dir, semantics)]
    zf.writestr(zipfile.ZipInfo("meta/provenance.json"),
                json.dumps({"skills": prov, "semantics": semantics.to_json()}, indent=1))
    zf.writestr(zipfile.ZipInfo("meta/touchpoints.json"),
                json.dumps([t.to_json() for t in scan_result.touchpoints], indent=1))
    zf.writestr(zipfile.ZipInfo("meta/machine_refs.json"),
                json.dumps([r.to_json() for r in scan_result.machine_refs], indent=1))
    state = checkout_state(root)
    if state.patch:
        zf.writestr(zipfile.ZipInfo("meta/checkout.patch"), state.patch)
    zf.writestr(zipfile.ZipInfo("meta/checkout.json"), json.dumps(state.to_json()))


def _manifest_artifacts(scan_result: ScanResult,
                        artifact_files: Dict[str, List[dict]]) -> List[dict]:
    out = []
    for art in scan_result.artifacts:
        record = art.to_json()
        record["files"] = artifact_files.get(art.id, [])
        if not art.travels:
            record["files"] = []   # recorded, not carried
        out.append(record)
    return out


def _predictive(plan: _Plan) -> dict:
    members = [e.member for e in plan.entries]
    illegal = []
    for member in members:
        problems = windows_path_problems(member[len(PAYLOAD_HOME):]
                                         if member.startswith(PAYLOAD_HOME) else member)
        if problems:
            illegal.append({"member": member, "problems": problems})
    collisions = find_collisions(members)
    return {"windows": {"illegal_names": illegal, "collisions": collisions}}


def _checklist_names(checklist: List[dict]) -> List[dict]:
    return [{"name": item["name"], "file": item.get("file", ""),
             "profile": item.get("profile", "")}
            for item in checklist if item.get("secret")]


def _source_snapshot(scan_result: ScanResult, semantics: HashSemantics) -> dict:
    import platform as _platform
    import socket

    ident = scan_result.identity
    tz_offset = -time.timezone // 60 if not time.daylight else -time.altzone // 60
    return {
        "hermes_version": ident.hermes_version,
        "release_date": ident.release_date,
        "git_head": ident.git_head, "git_tag": ident.git_tag,
        "git_dirty": ident.git_dirty, "build_sha": ident.build_sha,
        "install_method": ident.install_method,
        "config_version": ident.config_version,
        "os": ident.os_name, "arch": _platform.machine(),
        "layout_family": ident.layout_family,
        "hermes_home": ident.hermes_home, "home": str(Path.home()),
        "user": os.environ.get("USER") or os.environ.get("USERNAME") or "",
        "hostname": socket.gethostname(),
        "python": ident.python,
        "tz": {"name": time.tzname[0], "utc_offset_min": tz_offset,
               "dst": bool(time.daylight)},
        "lazy_features": ident.lazy_features,
        "capture_mode": scan_result.capture_mode,
        "hash_semantics": semantics.to_json(),
    }


# --------------------------------------------------------------------------- verify

def _registry_belt(manifest: dict) -> None:
    """Belt check (R-PACK-06): no member may match a capture-scope exclusion."""
    for art in manifest.get("artifacts", []):
        for f in art.get("files", []):
            rel = f.get("home_rel", "")
            exc = exclusion_for(rel, "capture")
            if exc is not None:
                raise TalariaError(
                    "TAL-204",
                    f"exclusion breach: {rel} matches registry rule '{exc.id}' but was "
                    "packed — refusing to publish",
                    exit_code=EXIT_CAPTURE_FAILED)


def _self_verify(partial: Path, manifest: dict) -> None:
    """Re-read the finished archive and re-hash every member (R-PACK-04)."""
    with zipfile.ZipFile(partial) as zf:
        names = set(zf.namelist())
        for art in manifest.get("artifacts", []):
            for f in art.get("files", []):
                member = f["member"]
                if member not in names:
                    raise TalariaError("TAL-204", f"self-verify: {member} missing",
                                       exit_code=EXIT_CAPTURE_FAILED)
                hasher = hashlib.sha256()
                with zf.open(member) as src:
                    while True:
                        chunk = src.read(CHUNK)
                        if not chunk:
                            break
                        hasher.update(chunk)
                if hasher.hexdigest() != f["sha256"]:
                    raise TalariaError(
                        "TAL-204", f"self-verify: checksum mismatch on {member}",
                        exit_code=EXIT_CAPTURE_FAILED)
