"""Minimal YAML-subset reader for Hermes config files (stdlib-only).

Reads the subset Hermes actually writes into `config.yaml` / `plugin.yaml` / SKILL.md
frontmatter: nested mappings by indentation, block lists of scalars/maps, inline flow lists,
quoted and plain scalars, comments. Anything outside the subset (anchors, block scalars,
multi-doc, tabs) makes the affected node degrade to a raw string rather than raising —
reference chasing must never crash on a hand-edited config (R-SCAN-07 is best-effort by
design; the venv-assisted path cross-checks when Hermes is present).

This is a READER. Config mutation goes through the indentation-anchored editor
(engine/rewrite/yaml_edit.py) with its explicit refuse-list — never through a re-dump of
this parse.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_SCALAR_TRUE = {"true", "yes", "on"}
_SCALAR_FALSE = {"false", "no", "off"}
_SCALAR_NULL = {"null", "~", ""}


def parse(text: str) -> Dict[str, Any]:
    """Parse YAML-subset text into nested dicts/lists/scalars. Never raises."""
    lines = _logical_lines(text)
    value, _idx = _parse_block(lines, 0, 0)
    return value if isinstance(value, dict) else {}


def get_path(tree: Any, dotted: str, default: Any = None) -> Any:
    """`get_path(cfg, "model.base_url")` — dotted lookup with None-safety."""
    node = tree
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return default
    return node


# --------------------------------------------------------------------------- internals

def _logical_lines(text: str) -> List[Tuple[int, str]]:
    """(indent, content) pairs, comments and blanks removed; tabs degrade the line."""
    out: List[Tuple[int, str]] = []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw.startswith("\t") or raw.lstrip(" ").startswith("\t"):
            continue  # tabs are outside the subset; skip the line, keep going
        indent = len(raw) - len(raw.lstrip(" "))
        content = _strip_comment(raw.strip())
        if content:
            out.append((indent, content))
    return out


def _strip_comment(content: str) -> str:
    """Strip a trailing comment that is not inside quotes."""
    in_s = in_d = False
    for i, ch in enumerate(content):
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif ch == "#" and not in_s and not in_d:
            if i == 0 or content[i - 1] in (" ", "\t"):
                return content[:i].rstrip()
    return content


_KEY_RE = re.compile(r"^(?P<key>[^:\s][^:]*?):(?:\s+(?P<value>.*))?$")


def _parse_block(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[Any, int]:
    """Parse a block starting at ``start`` with items at exactly ``indent``."""
    if start >= len(lines):
        return {}, start
    if lines[start][1].startswith("- "):
        return _parse_list(lines, start, indent)
    mapping: Dict[str, Any] = {}
    idx = start
    while idx < len(lines):
        line_indent, content = lines[idx]
        if line_indent < indent:
            break
        if line_indent > indent:
            idx += 1  # stray deeper line without a parent key — skip defensively
            continue
        if content.startswith("- "):
            break
        m = _KEY_RE.match(content)
        if not m:
            idx += 1
            continue
        key = _unquote(m.group("key").strip())
        value_text = m.group("value")
        if value_text is None or value_text == "":
            if idx + 1 < len(lines) and lines[idx + 1][0] > indent:
                child, idx = _parse_block(lines, idx + 1, lines[idx + 1][0])
                mapping[key] = child
                continue
            mapping[key] = None
            idx += 1
            continue
        if value_text in ("|", ">", "|-", ">-", "|+", ">+"):
            # Block scalar: outside the subset; consume deeper lines as one raw string.
            chunks = []
            idx += 1
            while idx < len(lines) and lines[idx][0] > indent:
                chunks.append(lines[idx][1])
                idx += 1
            mapping[key] = "\n".join(chunks)
            continue
        mapping[key] = _parse_scalar(value_text)
        idx += 1
    return mapping, idx


def _parse_list(lines: List[Tuple[int, str]], start: int, indent: int) -> Tuple[List[Any], int]:
    items: List[Any] = []
    idx = start
    while idx < len(lines):
        line_indent, content = lines[idx]
        if line_indent != indent or not content.startswith("- "):
            if line_indent < indent or not content.startswith("- "):
                break
        body = content[2:].strip()
        m = _KEY_RE.match(body)
        if m and (m.group("value") is not None or
                  (idx + 1 < len(lines) and lines[idx + 1][0] > indent)):
            # list item that is itself a mapping: re-parse the item body as a mapping whose
            # first line is `body` at a synthetic indent.
            sub_lines = [(indent + 2, body)]
            j = idx + 1
            while j < len(lines) and lines[j][0] > indent:
                sub_lines.append(lines[j])
                j += 1
            value, _ = _parse_block(sub_lines, 0, indent + 2)
            items.append(value)
            idx = j
            continue
        items.append(_parse_scalar(body))
        idx += 1
    return items, idx


def _parse_scalar(text: str) -> Any:
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip()) for part in _split_flow(inner)]
    if text.startswith("{") and text.endswith("}"):
        inner = text[1:-1].strip()
        result: Dict[str, Any] = {}
        for part in _split_flow(inner):
            if ":" in part:
                k, _, v = part.partition(":")
                result[_unquote(k.strip())] = _parse_scalar(v.strip())
        return result
    if (text.startswith('"') and text.endswith('"') and len(text) >= 2) or \
       (text.startswith("'") and text.endswith("'") and len(text) >= 2):
        return _unquote(text)
    low = text.lower()
    if low in _SCALAR_TRUE:
        return True
    if low in _SCALAR_FALSE:
        return False
    if low in _SCALAR_NULL:
        return None
    try:
        if re.fullmatch(r"[+-]?\d+", text):
            return int(text)
        if re.fullmatch(r"[+-]?\d*\.\d+(e[+-]?\d+)?", text, re.I):
            return float(text)
    except ValueError:
        pass
    return text


def _split_flow(inner: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    in_s = in_d = False
    current = ""
    for ch in inner:
        if ch == "'" and not in_d:
            in_s = not in_s
        elif ch == '"' and not in_s:
            in_d = not in_d
        elif not in_s and not in_d:
            if ch in "[{":
                depth += 1
            elif ch in "]}":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append(current.strip())
                current = ""
                continue
        current += ch
    if current.strip():
        parts.append(current.strip())
    return parts


def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        inner = text[1:-1]
        if text[0] == '"':
            return inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner.replace("''", "'")
    return text
