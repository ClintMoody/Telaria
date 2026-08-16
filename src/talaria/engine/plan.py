"""Rewrite-plan builder + executor (ARCHITECTURE §9.4; R-APPLY-08).

Plans are computed on the target from the bundle's recorded machine refs and rewrite
anchors, then executed against STAGED files only — never against the live install.
Every entry is previewable, individually skippable, and `needs_review` on any ambiguity.
Blanket regex over file bytes does not exist here by construction: every mutation goes
through a format editor addressing one located field.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from talaria.engine.rewrite import dotenv_edit, json_edit, yaml_edit
from talaria.model.secrets_registry import mask_secret_values
from talaria.platform.paths import translate_home_path

#: dotenv vars whose values are URLs pointing at machine-local services — flag-class,
#: never auto-rewritten (SEC-12/R-SEC-11).
URL_ENV_VARS = ("SIGNAL_HTTP_URL", "HASS_URL", "CAMOFOX_URL", "N8N_BASE_URL",
                "BROWSER_CDP_URL")


@dataclass
class PlanEntry:
    op_id: str
    file: str                 # root-relative POSIX path (as staged)
    format: str               # yaml|json|dotenv|manifest
    locator: str
    old: str
    new: Optional[str]
    rule: str                 # translate-home|relativize-script|skill-ref|flag|omit-credential
    status: str = "auto"      # auto|needs_review|manual|skipped|applied|failed
    reason: str = ""

    def preview(self) -> str:
        old = mask_secret_values(self.old)
        new = mask_secret_values(self.new or "(flag only)")
        return f"{self.file} :: {self.locator}\n  - {old}\n  + {new}"

    def to_json(self) -> dict:
        return {"op_id": self.op_id, "file": self.file, "format": self.format,
                "locator": self.locator, "old": mask_secret_values(self.old),
                "new": mask_secret_values(self.new) if self.new else None,
                "rule": self.rule, "status": self.status, "reason": self.reason}


@dataclass
class RewritePlan:
    entries: List[PlanEntry] = field(default_factory=list)

    def auto_entries(self) -> List[PlanEntry]:
        return [e for e in self.entries if e.status == "auto"]

    def needs_review(self) -> List[PlanEntry]:
        return [e for e in self.entries if e.status in ("needs_review", "manual")]

    def to_json(self) -> dict:
        return {"entries": [e.to_json() for e in self.entries]}


def build_plan(manifest: dict, machine_refs: List[dict], target_home_dir: str,
               target_hermes_home: str, target_sep: str) -> RewritePlan:
    """Translate every recorded machine ref for the target machine."""
    anchors = manifest.get("rewrite_anchors", {})
    source_home = anchors.get("source_home", "")
    source_hh = anchors.get("source_hermes_home", "")
    source_sep = anchors.get("sep", "/")
    plan = RewritePlan()
    seq = 0

    def next_id() -> str:
        nonlocal seq
        seq += 1
        return f"rw{seq:04d}"

    for ref in machine_refs:
        profile = ref.get("profile", "")
        prefix = f"profiles/{profile}/" if profile else ""
        file_rel = prefix + ref["file"]
        value = str(ref.get("value", ""))
        kind = ref.get("ref_kind", "path")
        fmt = ref.get("format", "yaml")
        locator = ref.get("locator", "")

        if kind in ("url", "localhost-url"):
            plan.entries.append(PlanEntry(
                next_id(), file_rel, fmt, locator, value, None, "flag",
                status="manual",
                reason=("points at a service on the old machine — verify it exists here "
                        "or update it" if kind == "localhost-url" else
                        "an outward URL — confirm it still applies from this machine")))
            continue

        if kind == "script" and fmt == "json":
            if "/" in value or "\\" in value:
                new_value = value.replace("\\", "/").rsplit("/", 1)[-1]
                plan.entries.append(PlanEntry(
                    next_id(), file_rel, fmt, locator, value, new_value,
                    "relativize-script",
                    reason="absolute script paths are blocked by the scheduler's "
                           "containment on a different home — relative form always works"))
            continue

        if kind == "path" and locator.endswith("]") and "skills[" in locator:
            name = value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
            plan.entries.append(PlanEntry(
                next_id(), file_rel, fmt, locator, value, name, "skill-ref",
                reason="absolute skill references become names (upstream resolves names "
                       "against the skills dir)"))
            continue

        translated = translate_home_path(value, source_hh, target_hermes_home,
                                         source_sep, target_sep)
        if translated is None:
            translated = translate_home_path(value, source_home, target_home_dir,
                                             source_sep, target_sep)
        if translated is not None:
            plan.entries.append(PlanEntry(
                next_id(), file_rel, fmt, locator, value, translated, "translate-home"))
        else:
            plan.entries.append(PlanEntry(
                next_id(), file_rel, fmt, locator, value, None, "flag", status="manual",
                reason="outside the old home directory — cannot be translated "
                       "mechanically; recreate or edit it on this machine"))

    return plan


# --------------------------------------------------------------------------- execution

def execute_plan(plan: RewritePlan, stage_root: Path,
                 accepted_ops: Optional[set] = None) -> List[PlanEntry]:
    """Apply auto entries to staged files; returns entries that changed a file.

    ``accepted_ops`` narrows execution (None = all auto entries). Manual/needs_review
    entries are never executed.
    """
    changed: List[PlanEntry] = []
    by_file: Dict[str, List[PlanEntry]] = {}
    for entry in plan.auto_entries():
        if accepted_ops is not None and entry.op_id not in accepted_ops:
            entry.status = "skipped"
            continue
        by_file.setdefault(entry.file, []).append(entry)

    for file_rel, entries in by_file.items():
        target = stage_root / file_rel
        if not target.is_file():
            for e in entries:
                e.status = "failed"
                e.reason = "file not staged"
            continue
        raw = target.read_bytes()
        text = raw.decode("utf-8-sig", errors="replace")
        had_bom = raw.startswith(b"\xef\xbb\xbf")
        fmt = entries[0].format
        if fmt == "json":
            text, ok_entries = _execute_json(text, entries)
        elif fmt == "dotenv":
            text, ok_entries = _execute_dotenv(text, entries)
        else:
            text, ok_entries = _execute_yaml(text, entries)
        if ok_entries:
            out = text.encode("utf-8")
            if had_bom:
                out = b"\xef\xbb\xbf" + out
            target.write_bytes(out)
            changed.extend(ok_entries)
    return changed


def _execute_yaml(text: str, entries: List[PlanEntry]) -> Tuple[str, List[PlanEntry]]:
    ok: List[PlanEntry] = []
    for entry in entries:
        locator = entry.locator
        if "[" in locator:   # list-valued locators can't be line-anchored safely
            entry.status = "needs_review"
            entry.reason = "list-valued key — edit it by hand or re-add in Hermes"
            continue
        outcome = yaml_edit.set_scalar(text, locator, entry.new or "")
        if outcome.ok:
            text = outcome.text
            entry.status = "applied"
            ok.append(entry)
        else:
            entry.status = "needs_review"
            entry.reason = outcome.reason
    return text, ok


def _execute_json(text: str, entries: List[PlanEntry]) -> Tuple[str, List[PlanEntry]]:
    try:
        data = json_edit.load(text)
    except ValueError as exc:
        for e in entries:
            e.status = "failed"
            e.reason = f"unparseable JSON: {exc}"
        return text, []
    ok: List[PlanEntry] = []
    for entry in entries:
        pointer = _job_locator_to_pointer(data, entry.locator)
        if pointer is None:
            entry.status = "needs_review"
            entry.reason = "locator not found in the staged file"
            continue
        try:
            json_edit.pointer_set(data, pointer, entry.new)
            entry.status = "applied"
            ok.append(entry)
        except (KeyError, IndexError, TypeError) as exc:
            entry.status = "failed"
            entry.reason = str(exc)
    if ok:
        text = json_edit.dumps_like_hermes(data, text)
    return text, ok


_JOB_LOC = re.compile(r"^jobs\[id=([0-9a-f]+)\]\.(\w+)(?:\[(\d+)\])?$")


def _job_locator_to_pointer(data, locator: str):
    m = _JOB_LOC.match(locator)
    if not m:
        return None
    job_id, fieldname, index = m.group(1), m.group(2), m.group(3)
    jobs = data.get("jobs") if isinstance(data, dict) else None
    if not isinstance(jobs, list):
        return None
    try:
        job_index = json_edit.find_job_index(jobs, job_id)
    except KeyError:
        return None
    pointer: List = ["jobs", job_index, fieldname]
    if index is not None:
        pointer.append(int(index))
    try:
        json_edit.pointer_get(data, pointer)
    except (KeyError, IndexError, TypeError):
        return None
    return pointer


def _execute_dotenv(text: str, entries: List[PlanEntry]) -> Tuple[str, List[PlanEntry]]:
    ok: List[PlanEntry] = []
    for entry in entries:
        key = entry.locator
        if key in URL_ENV_VARS:
            entry.status = "needs_review"
            entry.reason = "URL-valued variable — confirm the service address by hand"
            continue
        text, replaced = dotenv_edit.set_value(text, key, entry.new or "")
        if replaced:
            entry.status = "applied"
            ok.append(entry)
        else:
            entry.status = "needs_review"
            entry.reason = "variable not present in the staged file"
    return text, ok
