"""Indentation-anchored YAML scalar editor with an explicit refuse-list (R-XPLAT-07).

Edits exactly one `key: value` scalar located by a dotted key path, preserving every other
byte (per-line EOLs, BOM, comments, ordering). Constructs on the refuse-list turn the edit
into ``needs_review`` instead of a risky mutation: anchors/aliases, block scalars, flow
collections on the target line, merge keys, duplicate keys on the path, tabs.

Validation: the mutated text is re-parsed with the yamlmini subset reader and the new
value must be found at the same path, or the edit reports failure (caller reverts).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

from talaria.engine import yamlmini


@dataclass
class EditOutcome:
    ok: bool
    text: str
    reason: str = ""          # non-empty on refusal / failure
    old_value: Optional[str] = None


_REFUSE_PATTERNS = (
    (re.compile(r"[&*]\w"), "anchors/aliases"),
    (re.compile(r":\s*[|>][+-]?\s*$"), "block scalar"),
    (re.compile(r"<<\s*:"), "merge key"),
)


def _split_eol(line: str) -> Tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    return line, ""


def _needs_quoting(value: str) -> bool:
    if value == "":
        return True
    if re.search(r"[:#{}\[\],&*?|>%@`\"']", value):
        return True
    if value != value.strip():
        return True
    if value.lower() in ("true", "false", "yes", "no", "on", "off", "null", "~"):
        return True
    if re.fullmatch(r"[+-]?[\d.]+([eE][+-]?\d+)?", value):
        return True
    return False


def quote_scalar(value: str) -> str:
    """Deterministic quoting rule: single-quote unless plain-safe (C2-13)."""
    if _needs_quoting(value):
        return "'" + value.replace("'", "''") + "'"
    return value


def set_scalar(text: str, dotted_path: str, new_value: str) -> EditOutcome:
    """Set `a.b.c` to ``new_value`` (quoted deterministically); byte-faithful elsewhere."""
    if "\t" in text:
        return EditOutcome(False, text, "file contains tabs (refuse-list)")
    parts = dotted_path.split(".")
    lines = text.splitlines(keepends=True)

    # Walk the indentation tree to the parent of the target key.
    idx = 0
    depth_indent = 0
    for depth, key in enumerate(parts):
        found = None
        seen_at_level = set()
        scan = idx if depth else 0
        while scan < len(lines):
            body, _eol = _split_eol(lines[scan])
            stripped = body.strip()
            if not stripped or stripped.startswith("#"):
                scan += 1
                continue
            indent = len(body) - len(body.lstrip(" "))
            if depth and indent < depth_indent:
                break  # left the parent block
            if indent == depth_indent:
                m = re.match(r"^([^:\s][^:]*?):(?:\s+(.*))?$", stripped)
                if m:
                    line_key = m.group(1).strip().strip("\"'")
                    if line_key in seen_at_level and line_key == key:
                        return EditOutcome(False, text,
                                           f"duplicate key '{key}' (refuse-list)")
                    seen_at_level.add(line_key)
                    if line_key == key:
                        if found is not None:
                            return EditOutcome(False, text,
                                               f"duplicate key '{key}' (refuse-list)")
                        found = scan
            scan += 1
        if found is None:
            return EditOutcome(False, text, f"key path not found at '{key}'")
        idx = found
        if depth < len(parts) - 1:
            body, _eol = _split_eol(lines[idx])
            child_indent = None
            probe = idx + 1
            while probe < len(lines):
                pbody, _peol = _split_eol(lines[probe])
                pstr = pbody.strip()
                if pstr and not pstr.startswith("#"):
                    child_indent = len(pbody) - len(pbody.lstrip(" "))
                    break
                probe += 1
            if child_indent is None or child_indent <= depth_indent:
                return EditOutcome(False, text, f"'{key}' has no nested block")
            depth_indent = child_indent
            idx = probe

    body, eol = _split_eol(lines[idx])
    for pattern, why in _REFUSE_PATTERNS:
        if pattern.search(body):
            return EditOutcome(False, text, f"{why} on the target line (refuse-list)")
    m = re.match(r"^(\s*[^:\s][^:]*?:\s+)(.*)$", body)
    if not m:
        return EditOutcome(False, text, "target key has no inline scalar value")
    old_raw = m.group(2)
    if old_raw.lstrip().startswith(("[", "{")):
        return EditOutcome(False, text, "flow collection on the target line (refuse-list)")
    comment = ""
    cm = re.search(r"\s+#.*$", old_raw)
    if cm and not _inside_quotes(old_raw, cm.start()):
        comment = old_raw[cm.start():]
        old_raw = old_raw[:cm.start()]
    new_line = m.group(1) + quote_scalar(new_value) + comment + eol
    mutated = lines[:idx] + [new_line] + lines[idx + 1:]
    new_text = "".join(mutated)

    parsed = yamlmini.parse(new_text)
    if yamlmini.get_path(parsed, dotted_path) != new_value:
        got = yamlmini.get_path(parsed, dotted_path)
        if not (isinstance(got, (int, float, bool)) and str(got) == new_value):
            return EditOutcome(False, text,
                               "self-reparse did not find the new value at the path")
    return EditOutcome(True, new_text, old_value=old_raw.strip().strip("\"'"))


def _inside_quotes(text: str, pos: int) -> bool:
    in_s = in_d = False
    for i, ch in enumerate(text):
        if i >= pos:
            break
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
    return in_s or in_d


def remove_key_line(text: str, dotted_path: str) -> EditOutcome:
    """Comment out the target scalar line (used by D29 inline-credential omission)."""
    probe = set_scalar(text, dotted_path, "\x00TALARIA-PROBE\x00")
    if not probe.ok:
        return probe
    lines_before = text.splitlines(keepends=True)
    lines_after = probe.text.splitlines(keepends=True)
    for i, (a, b) in enumerate(zip(lines_before, lines_after)):
        if a != b:
            body, eol = _split_eol(a)
            indent = body[: len(body) - len(body.lstrip(" "))]
            commented = (indent + "# removed by talaria (credential value — see the "
                         "Secrets Handoff Checklist)" + eol)
            mutated = lines_before[:i] + [commented] + lines_before[i + 1:]
            return EditOutcome(True, "".join(mutated), old_value=probe.old_value)
    return EditOutcome(False, text, "could not locate the target line")
