"""Selection + the coupling engine (D10): binds pack AND apply narrowing.

Pack writes exactly the validated pack-time selection; apply may narrow but never widen,
and every narrowing re-runs this engine. A violated hard couple refuses (exit 3) naming
the couple id (TAL-208).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set

from talaria.model.artifact import Artifact
from talaria.model.catalog import COUPLE_RULES

PRESETS = {
    "everything-portable": None,          # all default-on artifacts (the default)
    "essentials": {"identity-memory", "configuration", "skills", "automations",
                   "credentials", "boards-projects"},
    "identity-only": {"identity-memory"},
}


@dataclass
class CoupleViolation:
    couple_id: str
    message: str
    needed: List[str] = field(default_factory=list)   # artifact ids that must be selected

    def to_json(self) -> dict:
        return {"couple": self.couple_id, "message": self.message, "needed": self.needed}


@dataclass
class Selection:
    preset: str = "everything-portable"
    include: Set[str] = field(default_factory=set)    # artifact ids force-included
    exclude: Set[str] = field(default_factory=set)    # artifact ids force-excluded

    def to_json(self) -> dict:
        return {"preset": self.preset, "include": sorted(self.include),
                "exclude": sorted(self.exclude)}

    @classmethod
    def from_json(cls, data: dict) -> "Selection":
        return cls(preset=data.get("preset", "everything-portable"),
                   include=set(data.get("include", [])),
                   exclude=set(data.get("exclude", [])))


def apply_selection(artifacts: Sequence[Artifact], selection: Selection) -> None:
    """Set ``selected`` on every artifact from preset + overrides.

    `never`-default artifacts cannot be included (the exclusion registry is not
    overridable — D23 explicitly ships no force-include for device-linked stores).
    """
    families = PRESETS.get(selection.preset)
    for art in artifacts:
        if art.default == "never":
            art.selected = False
            continue
        if art.id in selection.exclude:
            art.selected = False
            continue
        if art.id in selection.include:
            art.selected = art.default != "never"
            continue
        if art.default in ("off", "record_only"):
            art.selected = False
            continue
        art.selected = families is None or art.family in families


def narrow_selection(artifacts: Sequence[Artifact], only: Iterable[str] = (),
                     skip: Iterable[str] = ()) -> List[str]:
    """Apply-side narrowing (`--only/--skip`); returns unknown ids (never widens)."""
    only_set, skip_set = set(only), set(skip)
    known = {a.id for a in artifacts}
    unknown = sorted((only_set | skip_set) - known)
    for art in artifacts:
        if only_set:
            art.selected = art.selected and art.id in only_set
        if art.id in skip_set:
            art.selected = False
    return unknown


def validate_couples(artifacts: Sequence[Artifact],
                     cron_jobs: Optional[Dict[str, list]] = None,
                     config: Optional[Dict[str, dict]] = None) -> List[CoupleViolation]:
    """Run every hard coupling rule over the current selection (D10)."""
    cron_jobs = cron_jobs or {}
    config = config or {}
    violations: List[CoupleViolation] = []
    by_id = {a.id: a for a in artifacts}

    def selected(art_id: str) -> bool:
        art = by_id.get(art_id)
        return bool(art and art.selected)

    def exists(art_id: str) -> bool:
        return art_id in by_id

    profiles = sorted({a.profile for a in artifacts})
    for profile in profiles:
        p = profile  # readability
        skills_selected = [a for a in artifacts
                           if a.profile == p and a.kind == "skill-dir" and a.selected]
        meta_id = f"skills-metadata@{p}"
        if skills_selected and exists(meta_id) and not selected(meta_id):
            violations.append(CoupleViolation(
                "skill-metadata",
                COUPLE_RULES["skill-metadata"].description,
                [meta_id]))
        hub_selected = [a for a in skills_selected
                        if a.provenance.get("skill") == "hub-installed"]
        hub_id = f"hub-metadata@{p}"
        if hub_selected and exists(hub_id) and not selected(hub_id):
            violations.append(CoupleViolation(
                "hub-lock", COUPLE_RULES["hub-lock"].description, [hub_id]))

        jobs = cron_jobs.get(p, [])
        jobs_id = f"cron-jobs@{p}"
        if selected(jobs_id) and jobs:
            needs_scripts = any(j.get("script") or j.get("monitor_script") for j in jobs)
            scripts_id = f"scripts-dir@{p}"
            if needs_scripts and exists(scripts_id) and not selected(scripts_id):
                violations.append(CoupleViolation(
                    "job-script", COUPLE_RULES["job-script"].description, [scripts_id]))
            needs_output = any(j.get("context_from") or j.get("monitor_state")
                               for j in jobs)
            if needs_output:
                output_ids = [a.id for a in artifacts
                              if a.profile == p and a.kind == "cron-output"]
                unselected = [oid for oid in output_ids if not selected(oid)]
                if output_ids and unselected:
                    violations.append(CoupleViolation(
                        "job-context",
                        COUPLE_RULES["job-context"].description + " / " +
                        COUPLE_RULES["job-monitor"].description,
                        unselected))

        cfg = config.get(p, {})
        provider = _dig(cfg, "cron", "provider")
        if selected(jobs_id) and provider and provider != "builtin":
            plugin_id = f"plugin-dir@{p}/{provider}"
            candidates = [a.id for a in artifacts
                          if a.profile == p and a.kind == "plugin-dir"
                          and a.id.endswith("/" + str(provider))]
            if candidates and not any(selected(c) for c in candidates):
                violations.append(CoupleViolation(
                    "cron-provider-plugin",
                    COUPLE_RULES["cron-provider-plugin"].description, candidates))
            elif not candidates:
                violations.append(CoupleViolation(
                    "cron-provider-plugin",
                    f"cron.provider is '{provider}' but no plugins/{provider} exists — "
                    "scheduling silently degrades to builtin on the target",
                    [plugin_id]))

        mem_provider = _dig(cfg, "memory", "provider")
        if mem_provider in ("honcho", "hindsight", "openviking"):
            ext_ids = [a.id for a in artifacts if a.kind == "external-state"
                       and mem_provider in a.id]
            if ext_ids and not any(selected(e) for e in ext_ids):
                violations.append(CoupleViolation(
                    "memory-provider", COUPLE_RULES["memory-provider"].description,
                    ext_ids))
    return violations


def _dig(node: dict, *keys: str):
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node
