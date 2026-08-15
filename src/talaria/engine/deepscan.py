"""Deep-Scan: agent-assisted discovery with a hard trust boundary (ARCH §7.3).

The generated skill asks the user's OWN Hermes agent to inventory what it touches
day-to-day — names and paths, never values. The ingest side treats that report as
untrusted input (A12): exact nonce-named file, size cap, schema validation, secret-value
scrub over every string, never-registry gating BEFORE anything is offered, lstat-only
probing, and zero ability to mutate selection, exclusions, or scrubs.
"""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from talaria.errors import Refusal
from talaria.model.secrets_registry import (
    is_never_path,
    mask_secret_values,
    scan_text_for_secrets,
)

INGEST_MAX_BYTES = 1024 * 1024   # 1 MiB (R-DISC-04)
MAX_ITEMS = 500

SKILL_TEMPLATE = """---
name: talaria-deep-scan
description: One-time observation pass for a machine migration — inventory the external
  paths, tools, services, and credential NAMES this install relies on day to day, then
  write ONE json report file. Never include secret values.
version: 1.0.0
author: talaria
license: MIT
---

# Talaria Deep-Scan (one-time, read-only)

You are helping your human migrate this Hermes install to a new computer. A migration
tool has already inventoried `~/.hermes` itself. What it cannot see is what YOU know
from experience: the outside-of-Hermes things you actually touch when working.

## Rules (hard)

1. READ-ONLY. Do not modify, move, or delete anything during this pass.
2. NAMES, NEVER VALUES. List the *name* of an environment variable or credential —
   never its value, never file contents.
3. Report only what you have actually used or seen referenced. No guessing, no
   directory listings for their own sake.
4. Write exactly one file, exactly named: `talaria-deepscan-{nonce}.json`, in your
   working directory (or ~/). Nothing else.

## What to inventory

- Project directories and files outside ~/.hermes you work in (from memory of real
  sessions — e.g. repos, notes folders, data directories).
- External tools/binaries your workflows call (names only).
- Services/endpoints you rely on (names/hosts, e.g. "the NAS at 10.0.0.5",
  "local n8n on :5678").
- Environment variable NAMES your skills/jobs need beyond the standard ones.
- Anything you know would silently break on a fresh machine, with one line on why.

## Output schema (exact)

```json
{{
  "talaria_deepscan": 1,
  "nonce": "{nonce}",
  "paths": [{{"path": "~/projects/site", "why": "the deploy job edits it"}}],
  "tools": [{{"name": "ffmpeg", "why": "audio conversion in the podcast skill"}}],
  "services": [{{"name": "NAS smb://10.0.0.5", "why": "media library"}}],
  "env_names": [{{"name": "CUSTOM_API_KEY", "why": "the weather skill reads it"}}],
  "notes": ["one-line caveats worth a human reading"]
}}
```

Keep it under 500 items total. When done, tell your human the file name and that the
talaria tool on the new machine will verify every claim itself — nothing you write is
trusted blindly.
"""


@dataclass
class DeepScanResult:
    nonce: str
    candidates: List[dict] = field(default_factory=list)   # verified, user-optional
    refused: List[dict] = field(default_factory=list)      # never-registry hits
    unverified: List[str] = field(default_factory=list)    # advisory appendix
    tools: List[dict] = field(default_factory=list)
    services: List[dict] = field(default_factory=list)
    env_names: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    scrubbed: int = 0

    def to_json(self) -> dict:
        return {"nonce": self.nonce, "candidates": self.candidates,
                "refused": self.refused, "unverified": self.unverified,
                "tools": self.tools, "services": self.services,
                "env_names": self.env_names, "notes": self.notes,
                "scrubbed": self.scrubbed}


def generate_skill(out_dir: Path) -> Tuple[Path, str]:
    """Write the observation skill with a minted nonce; returns (skill_dir, nonce)."""
    nonce = secrets.token_hex(8)
    skill_dir = Path(out_dir) / "talaria-deep-scan"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(SKILL_TEMPLATE.format(nonce=nonce),
                                        encoding="utf-8")
    (skill_dir / ".talaria-nonce").write_text(nonce + "\n", encoding="utf-8")
    return skill_dir, nonce


def ingest_report(report_path: Path, home: Path,
                  expected_nonce: Optional[str] = None) -> DeepScanResult:
    """Ingest one agent report under the full trust model (R-DISC-04..06)."""
    report_path = Path(report_path)
    name = report_path.name
    if not (name.startswith("talaria-deepscan-") and name.endswith(".json")):
        raise Refusal("TAL-101",
                      f"{name} is not a deep-scan report (expected "
                      "talaria-deepscan-<nonce>.json — exact file, never a glob)")
    file_nonce = name[len("talaria-deepscan-"):-len(".json")]
    try:
        size = report_path.stat().st_size
    except OSError as exc:
        raise Refusal("TAL-104", f"cannot read {name}: {exc}")
    if size > INGEST_MAX_BYTES:
        raise Refusal("TAL-101", f"{name} is {size} bytes — over the 1 MiB ingest cap")

    raw = report_path.read_text(encoding="utf-8-sig", errors="replace")
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise Refusal("TAL-101", f"{name} is not valid JSON: {exc}")
    if not isinstance(data, dict) or data.get("talaria_deepscan") != 1:
        raise Refusal("TAL-101", f"{name} lacks the talaria_deepscan schema marker")
    body_nonce = str(data.get("nonce", ""))
    if body_nonce != file_nonce:
        raise Refusal("TAL-101",
                      "nonce mismatch between the file name and its body — a stale or "
                      "renamed report is rejected")
    if expected_nonce is not None and body_nonce != expected_nonce:
        raise Refusal("TAL-101", "this report answers a different generate run "
                      "(stale nonce) — regenerate and re-run the skill")

    result = DeepScanResult(nonce=body_nonce)
    home_str = str(Path(home).parent) if Path(home).name == ".hermes" \
        else str(Path.home())

    def scrub(text: str) -> str:
        hits = scan_text_for_secrets(text)
        if hits:
            result.scrubbed += 1
            return mask_secret_values(text)
        return text

    items = 0
    for entry in _as_list(data.get("paths"))[:MAX_ITEMS]:
        items += 1
        path_text = scrub(str(entry.get("path", "") if isinstance(entry, dict)
                              else entry))
        why = scrub(str(entry.get("why", ""))) if isinstance(entry, dict) else ""
        if not path_text:
            continue
        refusal = is_never_path(path_text, home_str)
        if refusal:
            result.refused.append({"path": path_text,
                                   "reason": f"agent suggested a sensitive path — "
                                             f"refused ({refusal})"})
            continue
        import os

        expanded = os.path.expanduser(path_text)
        if os.path.lexists(expanded):
            result.candidates.append({"path": path_text, "note": why or "exists",
                                      "provenance": "agent-reported/verified"})
        else:
            result.unverified.append(path_text)

    for entry in _as_list(data.get("tools"))[:MAX_ITEMS - items]:
        if isinstance(entry, dict) and entry.get("name"):
            result.tools.append({"name": scrub(str(entry["name"])),
                                 "why": scrub(str(entry.get("why", "")))})
    for entry in _as_list(data.get("services"))[:100]:
        if isinstance(entry, dict) and entry.get("name"):
            result.services.append({"name": scrub(str(entry["name"])),
                                    "why": scrub(str(entry.get("why", "")))})
    for entry in _as_list(data.get("env_names"))[:100]:
        name_value = entry.get("name") if isinstance(entry, dict) else entry
        if name_value:
            cleaned = str(name_value).strip()
            if "=" in cleaned:  # someone pasted VALUE — keep the name only
                cleaned = cleaned.split("=", 1)[0]
                result.scrubbed += 1
            result.env_names.append(cleaned)
    for note in _as_list(data.get("notes"))[:50]:
        result.notes.append(scrub(str(note)))
    return result


def _as_list(value) -> list:
    return value if isinstance(value, list) else []
