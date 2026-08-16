"""Transactional applier: INIT → PREFLIGHT → STAGE → BACKUP → APPLY → VERIFY → COMMIT
(ARCHITECTURE §9; R-APPLY-*).

Safety model:
- a write-ahead JSONL journal is fsynced BEFORE every mutation it describes;
- every replaced file is backed up first; the pre-apply backup is never deleted by any
  failure path;
- any error, integrity failure, or interrupt triggers reverse-journal rollback verified
  by re-hash; a rollback failure freezes as NEEDS_ATTENTION (exit 6) deleting nothing;
- the machine-bound registry filters the bundle AGAIN on this side, and the target's own
  stale runtime files are swept (journaled) the way container boot does.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from talaria.engine.bundle import (
    BundleReader,
    PAYLOAD_EXTERNAL,
    PAYLOAD_HOME,
    clamp_mode,
)
from talaria.engine.plan import RewritePlan, build_plan, execute_plan
from talaria.engine.preflight import PreflightReport, run_preflight, json_loads_safe
from talaria.engine.sqlite_snap import (
    SqliteSnapshotError,
    is_sqlite_file,
    snapshot_db,
)
from talaria.engine.provenance import (
    HashSemantics,
    classify_skills,
    read_bundled_manifest,
    rebaseline_manifest,
    write_bundled_manifest,
)
from talaria.errors import (
    EXIT_NEEDS_ATTENTION,
    EXIT_ROLLED_BACK,
    Refusal,
    TalariaError,
)
from talaria.events import EventLog
from talaria.hashes import file_sha256
from talaria.model.catalog import exclusion_for
from talaria.model.secrets_registry import is_credential_path, is_never_path
from talaria.platform.paths import member_name_problems
from talaria.model.selection import narrow_selection

TXN_DIRNAME = ".talaria"
QUICK_STATE_FLOOR = ("state.db", "config.yaml", ".env", "auth.json", "cron/jobs.json")

#: Stale runtime files swept from the target before placement (container-boot mirror).
STALE_SWEEP = ("gateway_state.json", "gateway.pid", "cron.pid", "gateway.lock",
               "processes.json", ".update_check")


@dataclass
class ApplyOptions:
    conflict_policy: str = "overwrite"       # keep|overwrite|rename|ask
    ask: Optional[Callable[[str], str]] = None
    only: Tuple[str, ...] = ()
    skip: Tuple[str, ...] = ()
    include_unrecognized: bool = False
    accept_url_changes: bool = False
    intent: str = "replace"
    dry_run: bool = False
    force_skew: bool = False
    vault_passphrase: Optional[str] = None
    consent_executable: bool = False         # PF-13 consent granted
    consent_external: bool = False           # PF-18 consent granted
    accepted_rewrites: Optional[Set[str]] = None


@dataclass
class ApplyOutcome:
    status: str                              # committed|rolled_back|refused|dry_run
    txn_id: str = ""
    exit_code: int = 0
    preflight: Optional[PreflightReport] = None
    plan: Optional[RewritePlan] = None
    placed: List[str] = field(default_factory=list)
    skipped: List[dict] = field(default_factory=list)
    conflicts: List[dict] = field(default_factory=list)
    scrubs: List[dict] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    backup_dir: str = ""
    journal_path: str = ""

    def to_json(self) -> dict:
        return {"status": self.status, "txn_id": self.txn_id,
                "exit_code": self.exit_code,
                "preflight": self.preflight.to_json() if self.preflight else None,
                "plan": self.plan.to_json() if self.plan else None,
                "placed": self.placed, "skipped": self.skipped,
                "conflicts": self.conflicts, "scrubs": self.scrubs,
                "failures": self.failures, "backup_dir": self.backup_dir,
                "journal": self.journal_path}


class Journal:
    """Append-only JSONL, fsynced before each described action (R-APPLY-01)."""

    def __init__(self, path: Path):
        self.path = path
        self._fh = open(path, "a", encoding="utf-8")
        self.seq = 0

    def write(self, event: str, **fields) -> int:
        self.seq += 1
        record = {"seq": self.seq, "ts": time.time(), "event": event}
        record.update(fields)
        self._fh.write(json.dumps(record, separators=(",", ":")) + "\n")
        self._fh.flush()
        os.fsync(self._fh.fileno())
        return self.seq

    def close(self) -> None:
        try:
            self._fh.close()
        except OSError:
            pass

    @staticmethod
    def read_all(path: Path) -> List[dict]:
        records: List[dict] = []
        try:
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except ValueError:
                        break  # torn final line — truncate here
        except OSError:
            pass
        return records


def find_unfinished_txn(target_home: Path) -> Optional[Path]:
    """An unterminated journal from a crashed apply (R-APPLY-03)."""
    txn_root = Path(target_home) / TXN_DIRNAME / "txn"
    if not txn_root.is_dir():
        return None
    for txn_dir in sorted(txn_root.iterdir(), reverse=True):
        journal = txn_dir / "journal.jsonl"
        if not journal.is_file():
            continue
        records = Journal.read_all(journal)
        committed = any(r.get("event") == "commit" for r in records)
        rolled_back_ok = any(r.get("event") == "rollback.done" and r.get("ok")
                             for r in records)
        if not committed and not rolled_back_ok and \
                any(r.get("event") == "op.done" for r in records):
            return txn_dir
    return None


def apply_bundle(bundle_path: Path, target_home: Path,
                 options: Optional[ApplyOptions] = None,
                 log: Optional[EventLog] = None) -> ApplyOutcome:
    options = options or ApplyOptions()
    log = log or EventLog()
    target_home = Path(target_home)
    outcome = ApplyOutcome(status="refused")

    stale = find_unfinished_txn(target_home)
    if stale is not None:
        raise Refusal("TAL-503",
                      f"an interrupted apply left transaction {stale.name} unfinished",
                      fix="run `talaria rollback` to restore the pre-apply state",
                      detail={"txn_dir": str(stale)})

    with BundleReader(bundle_path) as reader:
        problems = reader.verify_structure()
        if problems:
            raise Refusal("TAL-303",
                          "the bundle failed structural hardening: " + problems[0] +
                          (f" (+{len(problems)-1} more)" if len(problems) > 1 else ""),
                          detail={"problems": problems})

        log.emit("phase", "preflight", "Checking this machine")
        preflight = run_preflight(reader, target_home)
        outcome.preflight = preflight
        _enforce_gates(preflight, options)

        manifest = reader.manifest
        machine_refs = json_loads_safe(reader.read_meta("machine_refs.json")) or []
        target_sep = "\\" if os.name == "nt" else "/"
        plan = build_plan(manifest, machine_refs, str(Path.home()), str(target_home),
                          target_sep)
        outcome.plan = plan

        # Selection narrowing validates BEFORE the transaction exists: a refusal here
        # must propagate as exit 3 (nothing modified), never enter the rollback path.
        selected_ids = _selected_artifact_ids(manifest, options, reader)

        if options.dry_run:
            outcome.status = "dry_run"
            outcome.txn_id = "dry-run"
            log.emit("done", "preflight", "Dry run: nothing was written")
            return outcome

        txn_id = uuid.uuid4().hex[:12]
        txn_dir = target_home / TXN_DIRNAME / "txn" / txn_id
        stage_dir = txn_dir / "s"
        backup_dir = txn_dir / "b"
        for d in (stage_dir, backup_dir):
            d.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(target_home / TXN_DIRNAME, 0o700)
        except OSError:
            pass
        readme = target_home / TXN_DIRNAME / "README"
        if not readme.exists():
            readme.write_text("Talaria transaction area — safe to ignore; upstream "
                              "`hermes backup` may zip it.\n", encoding="utf-8")
        lock_path = txn_dir / "lock"
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.write(fd, f"{os.getpid()}\n{time.time()}\n".encode())
        os.close(fd)

        journal = Journal(txn_dir / "journal.jsonl")
        outcome.txn_id = txn_id
        outcome.backup_dir = str(backup_dir)
        outcome.journal_path = str(journal.path)
        journal.write("state", state="INIT", bundle=str(bundle_path),
                      bundle_id=manifest.get("bundle_id"), intent=options.intent)

        # STAGE and BACKUP touch only the transaction area, never the target's real
        # files — the first target mutation is _do_apply. A failure before that point
        # (wrong vault passphrase, hostile vault path, coupling violation, extraction
        # error) is a clean refusal: nothing was modified, so it must NOT roll back
        # (which would exit 5 and imply the target was touched). We tear down the txn
        # and re-raise. Only once mutation begins does the rollback path apply.
        try:
            placements = _stage(reader, manifest, plan, stage_dir, target_home,
                                options, journal, log, outcome, selected_ids)
            _backup(placements, target_home, backup_dir, journal, log)
        except BaseException as stage_exc:
            journal.close()
            shutil.rmtree(txn_dir, ignore_errors=True)
            _prune_empty_txn_root(target_home)
            if isinstance(stage_exc, (Refusal, TalariaError)):
                raise
            raise TalariaError("TAL-501",
                               f"apply could not be prepared: {stage_exc}",
                               exit_code=EXIT_ROLLED_BACK) from stage_exc

        try:
            _do_apply(placements, target_home, journal, log, outcome)
            _rebaseline_placed(manifest, placements, target_home, journal, outcome)
            _sweep_stale(target_home, backup_dir, journal, outcome)
            _verify_gating(placements, target_home, journal, log)
            journal.write("commit")
            outcome.status = "committed"
            outcome.exit_code = 0
            log.emit("done", "apply", "Everything moved in and double-checked")
            return outcome
        except BaseException as exc:
            log.emit("error", "apply", f"{exc} — rolling back")
            journal.write("rollback.begin", reason=str(exc)[:500])
            try:
                _rollback(journal, target_home)
                journal.write("rollback.done", ok=True)
                outcome.status = "rolled_back"
                outcome.exit_code = EXIT_ROLLED_BACK
                outcome.failures.append(str(exc))
                log.emit("done", "rollback",
                         "The machine is back to its pre-apply state")
                if isinstance(exc, (Refusal, TalariaError)):
                    return outcome
                return outcome
            except BaseException as rb_exc:
                journal.write("rollback.done", ok=False, error=str(rb_exc)[:500])
                outcome.status = "needs_attention"
                outcome.exit_code = EXIT_NEEDS_ATTENTION
                outcome.failures.extend([str(exc), f"rollback: {rb_exc}"])
                log.emit("error", "rollback",
                         f"Rollback incomplete — nothing deleted. Safety copy: "
                         f"{backup_dir}; journal: {journal.path}")
                return outcome
        finally:
            journal.close()


# --------------------------------------------------------------------------- gates

def _enforce_gates(preflight: PreflightReport, options: ApplyOptions) -> None:
    for gate in preflight.refusals:
        if gate.id == "PF-06" and options.force_skew and \
                preflight.skew_class in ("UNKNOWN",):
            continue
        code = {"PF-01": "TAL-401", "PF-05": "TAL-403", "PF-04": "TAL-404",
                "PF-06": "TAL-402"}.get(gate.id, "TAL-407")
        exit_code = 8 if gate.id == "PF-06" else 3
        raise Refusal(code, f"{gate.title}: {gate.detail}", fix=gate.fix,
                      exit_code=exit_code)
    for gate in preflight.consents:
        if gate.id == "PF-13" and not options.consent_executable:
            raise Refusal("TAL-407",
                          f"consent required — {gate.title}: {gate.detail}",
                          fix="re-run with --yes after reviewing `talaria inspect`, "
                              "or answer the consent prompt")
        if gate.id == "PF-18" and not options.consent_external:
            raise Refusal("TAL-407",
                          f"consent required — {gate.title}: {gate.detail}",
                          fix="re-run with --include-external after reviewing the "
                              "destinations")


# --------------------------------------------------------------------------- staging

@dataclass
class _Placement:
    member: str
    staged: Path
    final: Path
    root_rel: str
    expected_sha: str            # post-rewrite hash (computed after staging edits)
    mode: int
    is_credential: bool
    is_db: bool
    conflict: Optional[str] = None   # None|keep|overwrite|rename


def _stage(reader: BundleReader, manifest: dict, plan: RewritePlan, stage_dir: Path,
           target_home: Path, options: ApplyOptions, journal: Journal, log: EventLog,
           outcome: ApplyOutcome, selected_ids: Set[str]) -> List[_Placement]:
    log.emit("phase", "stage", "Preparing everything (nothing on this machine changes yet)")
    placements: List[_Placement] = []
    unrecognized_members = {u.get("member") for u in manifest.get("unrecognized", [])}
    rename_map = outcome.preflight.rename_map if outcome.preflight else {}

    for rec in reader.iter_payload():
        art_id = rec.artifact_id
        if art_id and art_id not in selected_ids:
            outcome.skipped.append({"path": rec.home_rel, "reason": "narrowed out"})
            continue
        if rec.member in unrecognized_members and not options.include_unrecognized:
            outcome.skipped.append({"path": rec.home_rel,
                                    "reason": "unrecognized (no consent — D9)"})
            continue
        if rec.member.startswith(PAYLOAD_HOME):
            root_rel = rec.member[len(PAYLOAD_HOME):]
            exc = exclusion_for(root_rel, "apply")
            if exc is None and "/" in root_rel and root_rel.startswith("profiles/"):
                profile_local = root_rel.split("/", 2)[2] if root_rel.count("/") >= 2 \
                    else root_rel
                exc = exclusion_for(profile_local, "apply")
            if exc is not None:
                outcome.skipped.append({"path": root_rel,
                                        "reason": f"machine-bound ({exc.id}) — filtered "
                                                  "on the apply side too"})
                continue
            mapped = rename_map.get(root_rel, root_rel)
            final = target_home / mapped
        elif rec.member.startswith(PAYLOAD_EXTERNAL):
            home_rel = rec.member[len(PAYLOAD_EXTERNAL):]
            refusal = is_never_path("~/" + home_rel, str(Path.home()))
            if refusal:
                outcome.skipped.append({"path": home_rel,
                                        "reason": f"never-registry: {refusal}"})
                continue
            final = Path.home() / home_rel
            root_rel = "_external/" + home_rel
        else:
            continue

        # Index-named staged files: flattening path separators can collide
        # ("a/b__c" vs "a__b/c"); an ordinal never does.
        staged = stage_dir / f"{len(placements):06d}"
        reader.extract_member(rec.member, staged)
        placements.append(_Placement(
            member=rec.member, staged=staged, final=final, root_rel=root_rel,
            expected_sha=rec.sha256, mode=rec.mode,
            is_credential=is_credential_path(rec.home_rel),
            is_db=rec.home_rel.endswith(".db")))

    _stage_vault(reader, manifest, stage_dir, target_home, options, placements, outcome)
    _apply_rewrites(plan, placements, stage_dir, options, journal, outcome)
    _scrub_cron(placements, journal, outcome)
    for placement in placements:
        placement.expected_sha = file_sha256(placement.staged)
    _resolve_conflicts(placements, options, outcome)
    return placements


def _selected_artifact_ids(manifest: dict, options: ApplyOptions,
                           reader: Optional[BundleReader] = None) -> Set[str]:
    from talaria.model.artifact import Artifact

    artifacts = []
    for record in manifest.get("artifacts", []):
        art = Artifact(id=record.get("id", ""), kind=record.get("kind", ""),
                       family=record.get("family", ""),
                       profile=record.get("profile", ""),
                       default=record.get("default", "on"),
                       provenance=record.get("provenance", {}) or {},
                       selected=record.get("selected", True) and
                       bool(record.get("files")))
        artifacts.append(art)
    unknown = narrow_selection(artifacts, options.only, options.skip)
    if unknown:
        raise Refusal("TAL-208", "unknown artifact ids in --only/--skip: "
                      + ", ".join(unknown))
    if options.only or options.skip:
        from talaria.model.selection import validate_couples

        # The coupling engine needs the actual cron jobs + config to tell whether a job
        # has a script / context_from / monitor etc. Load them from the bundle payload so
        # narrowing that would strand a dependent unit (e.g. --skip scripts-dir while
        # keeping a job that runs a script) is refused, not silently applied broken.
        cron_jobs, config = _load_couple_context(reader, manifest)
        violations = validate_couples(artifacts, cron_jobs, config)
        if violations:
            raise Refusal("TAL-208",
                          "narrowing breaks hard couples: " +
                          "; ".join(f"{v.couple_id} ({v.message})" for v in violations))
    return {a.id for a in artifacts if a.selected}


def _load_couple_context(reader: Optional[BundleReader], manifest: dict
                         ) -> Tuple[Dict[str, list], Dict[str, dict]]:
    """Read cron jobs.json and config.yaml per profile from the bundle for couple checks."""
    cron_jobs: Dict[str, list] = {}
    config: Dict[str, dict] = {}
    if reader is None or reader.zf is None:
        return cron_jobs, config
    from talaria.engine import yamlmini

    profiles = manifest.get("profiles", [""]) or [""]
    for profile in profiles:
        base = PAYLOAD_HOME + (f"profiles/{profile}/" if profile else "")
        try:
            raw = reader.zf.read(base + "cron/jobs.json")
            data = json.loads(raw.decode("utf-8-sig"))
            jobs = data.get("jobs", [])
            cron_jobs[profile] = jobs if isinstance(jobs, list) else []
        except (KeyError, ValueError):
            pass
        try:
            raw = reader.zf.read(base + "config.yaml")
            config[profile] = yamlmini.parse(raw.decode("utf-8-sig", errors="replace"))
        except (KeyError, ValueError):
            pass
    return cron_jobs, config


def _stage_vault(reader: BundleReader, manifest: dict, stage_dir: Path,
                 target_home: Path, options: ApplyOptions,
                 placements: List[_Placement], outcome: ApplyOutcome) -> None:
    section = manifest.get("vault") or {}
    if not section.get("present"):
        return
    if not options.vault_passphrase:
        outcome.skipped.append({"path": "(vault)", "reason":
                                "vault present but no passphrase given — credentials "
                                "stay on the checklist"})
        return
    from talaria.engine import vault as vault_mod

    vr = vault_mod.open_vault(manifest, options.vault_passphrase)
    assert reader.zf is not None
    for seq, record in enumerate(vr.members()):
        profile = record.get("profile", "")
        root_rel = record.get("root_rel") or record["home_rel"]
        # A vault member's destination is manifest-declared and the passphrase-holder
        # may be a hostile bundle author (they own+share it) — so root_rel is UNTRUSTED
        # and must clear the same containment the payload path enforces, or it writes
        # anywhere on disk (arbitrary-write → RCE). It never escapes HERMES_HOME.
        problems = member_name_problems("payload/home/" + root_rel)
        final = (target_home / root_rel).resolve()
        if problems or not _within(final, target_home):
            raise Refusal("TAL-303",
                          f"vault member declares an unsafe destination {root_rel!r} — "
                          "refusing before any write",
                          detail={"root_rel": root_rel, "problems": problems})
        staged = stage_dir / f"vault-{seq:06d}"
        vr.decrypt_member(reader.zf, record, staged)
        placements.append(_Placement(
            member=record["member"], staged=staged, final=target_home / root_rel,
            root_rel=root_rel, expected_sha=record.get("plain_sha256", ""),
            mode=record.get("mode", 0o600), is_credential=True,
            is_db=root_rel.endswith(".db")))


def _within(child: Path, root: Path) -> bool:
    """True when the resolved ``child`` is ``root`` or strictly inside it."""
    try:
        child.resolve().relative_to(Path(root).resolve())
        return True
    except (ValueError, OSError):
        return False


def _prune_empty_txn_root(target_home: Path) -> None:
    """Remove the .talaria txn scaffolding when a refused apply left it empty."""
    txn_root = Path(target_home) / TXN_DIRNAME / "txn"
    try:
        if txn_root.is_dir() and not any(txn_root.iterdir()):
            txn_root.rmdir()
        talaria_dir = Path(target_home) / TXN_DIRNAME
        remaining = {p.name for p in talaria_dir.iterdir()} if talaria_dir.is_dir() \
            else set()
        if remaining <= {"README"}:
            shutil.rmtree(talaria_dir, ignore_errors=True)
    except OSError:
        pass


def _apply_rewrites(plan: RewritePlan, placements: List[_Placement], stage_dir: Path,
                    options: ApplyOptions, journal: Journal,
                    outcome: ApplyOutcome) -> None:
    staged_by_rel = {p.root_rel: p.staged for p in placements}

    class _StageView:
        def __truediv__(self, rel: str) -> Path:
            return staged_by_rel.get(rel, stage_dir / "__absent__")

    accepted = options.accepted_rewrites
    if accepted is None and not options.accept_url_changes:
        pass  # auto entries run; URL/flag entries are manual already
    changed = execute_plan(plan, _StageView(), accepted)  # type: ignore[arg-type]
    for entry in changed:
        journal.write("op.done", op_id=entry.op_id, kind="rewrite", file=entry.file,
                      locator=entry.locator)


def _scrub_cron(placements: List[_Placement], journal: Journal,
                outcome: ApplyOutcome) -> None:
    """Null runtime claims; drop alert bits; delete non-terminal executions rows."""
    for placement in placements:
        name = placement.root_rel.rsplit("/", 1)[-1]
        if name == "jobs.json":
            try:
                data = json.loads(placement.staged.read_text(encoding="utf-8-sig"))
            except (OSError, ValueError):
                continue
            scrubbed = 0
            for job in data.get("jobs", []):
                for fieldname in ("run_claim", "fire_claim"):
                    if job.get(fieldname) is not None:
                        job[fieldname] = None
                        scrubbed += 1
                for fieldname in ("preflight_alerted", "drift_alerted"):
                    if fieldname in job:
                        del job[fieldname]
                        scrubbed += 1
            if scrubbed:
                placement.staged.write_text(
                    json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
                outcome.scrubs.append({"file": placement.root_rel,
                                       "fields": scrubbed,
                                       "reason": "machine-scoped cron runtime claims"})
        elif name == "executions.db":
            try:
                conn = sqlite3.connect(placement.staged)
                with conn:
                    cur = conn.execute(
                        "DELETE FROM executions WHERE status NOT IN "
                        "('completed','failed')")
                    dropped = cur.rowcount
                conn.close()
                if dropped:
                    outcome.scrubs.append({"file": placement.root_rel,
                                           "rows": dropped,
                                           "reason": "non-terminal execution rows "
                                                     "(pid liveness fails safe-to-alive "
                                                     "on foreign machines)"})
            except sqlite3.Error:
                pass


def _rebaseline_placed(manifest: dict, placements: List[_Placement], target_home: Path,
                       journal: Journal, outcome: ApplyOutcome) -> None:
    """D14/R-DIFF-02: after placement, recompute stock-pristine `.bundled_manifest`
    hashes under the TARGET OS's separator/collation semantics.

    Runs post-_do_apply on the real placed skills trees (staging uses ordinal names, so
    the tree can't be reconstructed there). Without this, every stock skill's seed-time
    hash was computed under the source OS's semantics and would never match on the target
    — freezing all upstream skill updates (`hermes skills list-modified` would report the
    whole stock set as modified). The matching placement's expected hash is updated so
    the gating verify still passes.
    """
    source_sem = (manifest.get("hash_semantics") or
                  (manifest.get("source") or {}).get("hash_semantics") or {})
    target_os = "windows" if os.name == "nt" else "posix"
    source_sep = source_sem.get("separator", "posix")
    if source_sep == ("nt" if target_os == "windows" else "posix"):
        return  # same semantics — nothing to rebaseline
    source_semantics = HashSemantics(separator=source_sep,
                                     collation=source_sem.get("collation", "posix"))
    target_semantics = HashSemantics.for_os("windows" if target_os == "windows"
                                            else "linux")

    manifest_placements = {p.root_rel: p for p in placements
                           if p.root_rel.endswith("skills/.bundled_manifest")}
    for root_rel, placement in manifest_placements.items():
        skills_dir = placement.final.parent
        if not skills_dir.is_dir():
            continue
        provenances = classify_skills(skills_dir, source_semantics)
        current = read_bundled_manifest(skills_dir)
        rebased = rebaseline_manifest(current, provenances, skills_dir, target_semantics)
        if rebased == current:
            continue
        # Rollback of this file is already covered by its placement backup (the pre-apply
        # target state), so no extra backup is needed — just record the modification.
        journal.write("op.done", op_id=f"rb-{root_rel[:20]}", kind="rebaseline",
                      final=str(placement.final))
        write_bundled_manifest(skills_dir, rebased)
        placement.expected_sha = file_sha256(placement.final)  # keep verify happy
        pristine = sum(1 for p in provenances if p.tag == "stock-pristine")
        outcome.scrubs.append({
            "file": root_rel,
            "reason": f"cross-OS apply: rebaselined {pristine} stock-pristine skill "
                      "hash(es) to this machine's semantics so upstream updates keep "
                      "working"})


def _resolve_conflicts(placements: List[_Placement], options: ApplyOptions,
                       outcome: ApplyOutcome) -> None:
    for placement in placements:
        final = placement.final
        if not final.exists():
            continue
        try:
            same = file_sha256(final) == placement.expected_sha
        except OSError:
            same = False
        if same:
            continue
        policy = options.conflict_policy
        if policy == "ask" and options.ask is not None:
            policy = options.ask(placement.root_rel)
        if policy == "keep":
            placement.conflict = "keep"
            outcome.conflicts.append({"path": placement.root_rel, "decision": "keep",
                                      "detail": "your existing file stays"})
        elif policy == "rename":
            placement.conflict = "rename"
            placement.final = final.with_name(final.name + ".from-bundle")
            outcome.conflicts.append({"path": placement.root_rel, "decision": "rename",
                                      "detail": f"bundle copy lands as "
                                                f"{placement.final.name}"})
        else:
            placement.conflict = "overwrite"
            outcome.conflicts.append({"path": placement.root_rel,
                                      "decision": "overwrite",
                                      "detail": "existing file backed up, then replaced"})


# --------------------------------------------------------------------------- phases

def _backup(placements: List[_Placement], target_home: Path, backup_dir: Path,
            journal: Journal, log: EventLog) -> None:
    log.emit("phase", "backup", "Making the safety copy")
    seen: Set[Path] = set()
    seq = 0
    is_db_by_final = {p.final: p.is_db for p in placements}
    for placement in placements:
        final = placement.final
        if final in seen or not final.exists():
            continue
        seen.add(final)
        seq += 1
        _backup_one(final, backup_dir / f"{seq:05d}", placement.is_db,
                    f"bk{seq:05d}", journal)
    # Quick-state floor: back up even when unselected (they may be replaced by sweeps).
    for rel in QUICK_STATE_FLOOR:
        final = target_home / rel
        if final.exists() and final not in seen:
            seen.add(final)
            seq += 1
            _backup_one(final, backup_dir / f"{seq:05d}",
                        rel.endswith(".db") or is_db_by_final.get(final, False),
                        f"bk{seq:05d}", journal)


def _backup_one(final: Path, backup_path: Path, is_db: bool, op_id: str,
                journal: Journal) -> None:
    """Back up one target file. Databases are snapshotted (WAL folded into a complete,
    self-contained copy) so a rollback restores every committed transaction — a plain
    file-copy of a hot WAL database loses un-checkpointed frames and its sidecars.
    """
    journal.write("op.intent", op_id=op_id, kind="backup", final=str(final),
                  backup=str(backup_path), is_db=bool(is_db))
    used_snapshot = False
    if is_db and is_sqlite_file(final):
        try:
            snapshot_db(final, backup_path)
            used_snapshot = True
        except SqliteSnapshotError:
            used_snapshot = False
    if not used_snapshot:
        shutil.copy2(final, backup_path)
    journal.write("op.done", op_id=op_id, kind="backup", final=str(final),
                  backup=str(backup_path), backup_sha=_safe_sha(backup_path),
                  is_db=bool(is_db))


def _do_apply(placements: List[_Placement], target_home: Path, journal: Journal,
              log: EventLog, outcome: ApplyOutcome) -> None:
    log.emit("phase", "apply", "Moving everything in")
    for i, placement in enumerate(placements):
        if placement.conflict == "keep":
            continue
        final = placement.final
        op_id = f"pl{i:05d}"
        journal.write("op.intent", op_id=op_id,
                      kind="db_place" if placement.is_db else "replace_file",
                      final=str(final), staged=str(placement.staged),
                      expected_sha=placement.expected_sha,
                      is_db=bool(placement.is_db),
                      existed=final.exists())
        final.parent.mkdir(parents=True, exist_ok=True)
        if placement.is_db:
            # The pre-apply DB backup is a WAL-folded snapshot (see _backup_one), so the
            # old sidecars' committed data is already preserved and rollback restores a
            # complete database. Removing the stale sidecars here is therefore safe; the
            # journal marks the placement is_db so rollback clears any sidecars again.
            for suffix in ("-wal", "-shm", "-journal"):
                sidecar = Path(str(final) + suffix)
                if sidecar.exists():
                    try:
                        sidecar.unlink()
                    except OSError:
                        pass
        _place_file(placement.staged, final)
        mode = clamp_mode(placement.mode, placement.is_credential)
        try:
            os.chmod(final, mode)
        except OSError:
            pass
        journal.write("op.done", op_id=op_id, kind="replace_file", final=str(final))
        outcome.placed.append(placement.root_rel)


def _place_file(staged: Path, final: Path) -> None:
    """Same-volume rename, falling back to copy+fsync+replace across devices (C2-06)."""
    try:
        os.replace(staged, final)
        return
    except OSError:
        pass
    tmp = final.with_name(final.name + ".talaria-tmp")
    with open(staged, "rb") as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())
    os.replace(tmp, final)
    try:
        staged.unlink()
    except OSError:
        pass


def _sweep_stale(target_home: Path, backup_dir: Path, journal: Journal,
                 outcome: ApplyOutcome) -> None:
    """Sweep the target's own stale runtime files (backed up first, journaled)."""
    seq = 0
    for name in STALE_SWEEP:
        target = target_home / name
        if not target.exists():
            continue
        seq += 1
        backup_path = backup_dir / f"sweep{seq:03d}"
        journal.write("op.intent", op_id=f"sw{seq:03d}", kind="delete_stale",
                      final=str(target), backup=str(backup_path),
                      pre_sha=_safe_sha(target))
        try:
            shutil.copy2(target, backup_path)
            target.unlink()
            journal.write("op.done", op_id=f"sw{seq:03d}", kind="delete_stale",
                          final=str(target))
            outcome.scrubs.append({"file": name,
                                   "reason": "stale runtime state from this machine "
                                             "(container-boot mirror sweep)"})
        except OSError as exc:
            journal.write("op.done", op_id=f"sw{seq:03d}", kind="delete_stale",
                          final=str(target), error=str(exc))


def _verify_gating(placements: List[_Placement], target_home: Path, journal: Journal,
                   log: EventLog) -> None:
    """Integrity verification — failure raises, which triggers rollback (R-VERIFY-01)."""
    log.emit("phase", "verify", "Double-checking every file")
    for placement in placements:
        if placement.conflict == "keep":
            continue
        final = placement.final
        if not final.exists():
            raise TalariaError("TAL-602", f"verify: {final} missing after placement")
        if placement.expected_sha:
            actual = file_sha256(final)
            if actual != placement.expected_sha:
                raise TalariaError("TAL-602",
                                   f"verify: {placement.root_rel} hash mismatch after "
                                   "placement")
        if placement.is_db and final.stat().st_size <= 2 * 1024 * 1024 * 1024:
            try:
                # immutable=1: nothing writes during apply, and it stops SQLite from
                # materializing -wal/-shm sidecars next to the freshly placed snapshot.
                conn = sqlite3.connect(f"file:{final}?mode=ro&immutable=1", uri=True)
                row = conn.execute("PRAGMA quick_check(1)").fetchone()
                conn.close()
                if not row or row[0] != "ok":
                    raise TalariaError("TAL-602",
                                       f"verify: {placement.root_rel} failed "
                                       "quick_check")
            except sqlite3.Error as exc:
                raise TalariaError("TAL-602",
                                   f"verify: {placement.root_rel} unreadable: {exc}")
    journal.write("state", state="VERIFIED")


# --------------------------------------------------------------------------- rollback

def _safe_sha(path: Path) -> Optional[str]:
    try:
        return file_sha256(path)
    except OSError:
        return None


def _rollback(journal: Journal, target_home: Path) -> None:
    rollback_journal(Path(journal.path), target_home)


def _clear_db_sidecars(final: Path) -> None:
    for suffix in ("-wal", "-shm", "-journal"):
        try:
            Path(str(final) + suffix).unlink()
        except OSError:
            pass


def rollback_journal(journal_path: Path, target_home: Path) -> List[str]:
    """Reverse-walk a journal restoring pre-apply state; re-hash verified (R-APPLY-02).

    Handles the crash case: an op whose ``op.intent`` was fsynced but whose ``op.done``
    never landed still mutated (or half-mutated) the target, so it MUST be rolled back
    too — keying only on ``op.done`` would leave the half-applied file in place.
    """
    records = Journal.read_all(journal_path)
    restored: List[str] = []
    backups: Dict[str, dict] = {}
    done_backup_sha: Dict[str, str] = {}
    for record in records:
        if record.get("event") == "op.intent" and record.get("kind") in (
                "backup", "delete_stale"):
            backups[record["final"]] = record
        if record.get("event") == "op.done" and record.get("kind") == "backup":
            if record.get("backup_sha"):
                done_backup_sha[record["final"]] = record["backup_sha"]

    # Every mutating op that at least reached op.intent, newest first. An op with an
    # intent but no matching done is the crashed op — still rolled back.
    intents = [r for r in records if r.get("event") == "op.intent"
               and r.get("kind") in ("replace_file", "db_place", "delete_stale")]
    for record in reversed(intents):
        kind = record.get("kind")
        final_str = record.get("final", "")
        final = Path(final_str)
        is_db = bool(record.get("is_db"))
        if kind in ("replace_file", "db_place"):
            intent = backups.get(final_str)
            if intent is not None and Path(intent["backup"]).exists():
                backup_path = Path(intent["backup"])
                # COPY, never move: the pre-apply safety copy survives rollback intact.
                if is_db:
                    _clear_db_sidecars(final)
                shutil.copy2(backup_path, final)
                expect = done_backup_sha.get(final_str)
                if expect and _safe_sha(final) != expect:
                    raise TalariaError(
                        "TAL-502", f"rollback verification failed for {final}")
                restored.append(final_str)
            elif not record.get("existed", False):
                # The file did not exist before this apply — remove what we created.
                if final.exists():
                    final.unlink()
                if is_db:
                    _clear_db_sidecars(final)
                restored.append(final_str + " (removed)")
        elif kind == "delete_stale":
            intent = backups.get(final_str)
            if intent is not None:
                backup_path = Path(intent["backup"])
                if backup_path.exists() and not final.exists():
                    shutil.copy2(backup_path, final)
                    restored.append(final_str)
    return restored
