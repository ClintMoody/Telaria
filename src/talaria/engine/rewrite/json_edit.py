"""JSON editor: parse → mutate at a pointer → dump matching upstream's writer.

Used for `cron/jobs.json` (upstream writes `json.dump(indent=2)` after an atomic temp —
cron/jobs.py:1288-1340) and other machine-written JSON. Reads `utf-8-sig` (BOM-tolerant,
mirroring upstream's reader) and preserves a trailing newline if one existed.
"""

from __future__ import annotations

import json
from typing import Any, List, Tuple


def load(text: str) -> Any:
    return json.loads(text)


def dumps_like_hermes(data: Any, original_text: str = "") -> str:
    out = json.dumps(data, indent=2, ensure_ascii=False)
    if original_text.endswith("\n") or not original_text:
        out += "\n"
    return out


def pointer_get(data: Any, pointer: List[Any]) -> Any:
    node = data
    for part in pointer:
        node = node[part]
    return node


def pointer_set(data: Any, pointer: List[Any], value: Any) -> Any:
    node = data
    for part in pointer[:-1]:
        node = node[part]
    old = node[pointer[-1]]
    node[pointer[-1]] = value
    return old


def find_job_index(jobs: List[dict], job_id: str) -> int:
    for i, job in enumerate(jobs):
        if isinstance(job, dict) and job.get("id") == job_id:
            return i
    raise KeyError(f"job {job_id} not found")
