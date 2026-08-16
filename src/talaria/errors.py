"""Talaria error model: TAL-coded errors and the exit-code table.

One user-facing registry (TAL-xxx, D4); internal F/PF ids from the reliability proposal are
aliases carried in the registry data. Exit codes are SPEC D3 / ARCHITECTURE §14, verbatim.
Guarantee encoded here and relied on by the CLI: only exit codes 5/6/7 imply the target machine
was touched.
"""

from __future__ import annotations

import json
from typing import Dict, Optional

try:  # zip-safe registry load (works from .pyz too)
    from importlib.resources import files as _res_files
except ImportError:  # pragma: no cover - 3.8 fallback path, floor is 3.9
    _res_files = None

# Exit codes (D3; P3 §13 verbatim)
EXIT_OK = 0
EXIT_INTERNAL = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3            # nothing modified
EXIT_CAPTURE_FAILED = 4     # no bundle published
EXIT_ROLLED_BACK = 5        # apply failed, rollback succeeded
EXIT_NEEDS_ATTENTION = 6    # rollback incomplete; pre-apply backup still exists
EXIT_RESERVED_STRICT = 7    # reserved for v1.1 strict-verify/commit
EXIT_SKEW_BLOCKED = 8
EXIT_BUNDLE_UNREADABLE = 9

#: Exit codes that mean "the target machine was modified".
TARGET_TOUCHED_EXITS = frozenset({EXIT_ROLLED_BACK, EXIT_NEEDS_ATTENTION, EXIT_RESERVED_STRICT})


class TalariaError(Exception):
    """An error with a stable TAL code, a one-line fix, and an exit code."""

    def __init__(self, code: str, message: str, *, fix: Optional[str] = None,
                 exit_code: int = EXIT_INTERNAL, detail: Optional[dict] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        entry = registry().get(code, {})
        self.title = entry.get("title", code)
        self.fix = fix if fix is not None else entry.get("fix_line", "")
        self.doc_anchor = entry.get("doc_anchor", code.lower())
        self.aliases = entry.get("aliases", [])
        self.exit_code = exit_code
        self.detail = detail or {}

    def render(self) -> str:
        lines = [f"[{self.code}] {self.message}"]
        if self.fix:
            lines.append(f"  fix: {self.fix}")
        lines.append(f"  docs: docs/troubleshooting.md#{self.doc_anchor}")
        return "\n".join(lines)

    def to_json(self) -> dict:
        return {
            "code": self.code,
            "title": self.title,
            "message": self.message,
            "fix": self.fix,
            "aliases": self.aliases,
            "exit_code": self.exit_code,
            "detail": self.detail,
        }


class Refusal(TalariaError):
    """A refusal that guarantees nothing was modified (exit 3 unless overridden)."""

    def __init__(self, code: str, message: str, **kw):
        kw.setdefault("exit_code", EXIT_REFUSED)
        super().__init__(code, message, **kw)


_REGISTRY_CACHE: Optional[Dict[str, dict]] = None


def registry() -> Dict[str, dict]:
    """The TAL registry, keyed by code. Loaded zip-safely, cached."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is None:
        raw = None
        if _res_files is not None:
            try:
                raw = (_res_files("talaria") / "data" / "tal_registry.json").read_text("utf-8")
            except (FileNotFoundError, TypeError, OSError):
                raw = None
        if raw is None:  # pragma: no cover - registry ships with the package
            _REGISTRY_CACHE = {}
        else:
            data = json.loads(raw)
            _REGISTRY_CACHE = {e["code"]: e for e in data["errors"]}
    return _REGISTRY_CACHE


def by_alias(alias: str) -> Optional[str]:
    """Resolve an internal alias (F13, PF-01, WA-DEVICE-LINK) to its TAL code."""
    for code, entry in registry().items():
        if alias in entry.get("aliases", []):
            return code
    return None
