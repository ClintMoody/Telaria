"""Line-oriented dotenv editor: byte-faithful outside the targeted assignment (R-XPLAT-07).

Only lines assigning exactly the named key are touched; every other byte — comments,
ordering, blank lines, CRLF/LF per line, BOM — is preserved.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

BOM = "﻿"


def _split_eol(line: str) -> Tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n"):
        return line[:-1], "\n"
    if line.endswith("\r"):
        return line[:-1], "\r"
    return line, ""


def dominant_eol(text: str) -> str:
    crlf = text.count("\r\n")
    lf = text.count("\n") - crlf
    return "\r\n" if crlf > lf else "\n"


def _match_key(body: str, key: str) -> Optional[int]:
    """Offset of the value if this line assigns ``key`` (export-tolerant), else None."""
    stripped = body.lstrip()
    prefix_len = len(body) - len(stripped)
    candidate = stripped
    if candidate.startswith("export "):
        candidate = candidate[len("export "):]
        prefix_len += len("export ")
    if not candidate.startswith(key):
        return None
    rest = candidate[len(key):]
    if not rest.startswith("="):
        return None
    return prefix_len + len(key) + 1


def get_value(text: str, key: str) -> Optional[str]:
    for raw in text.splitlines(keepends=True):
        body, _eol = _split_eol(raw)
        if body.startswith(BOM):
            body = body[1:]
        offset = _match_key(body, key)
        if offset is not None:
            return body[offset:]
    return None


def set_value(text: str, key: str, new_value: str) -> Tuple[str, bool]:
    """Replace the value of ``key``; append (dominant EOL) when absent.

    Returns (new_text, replaced_existing).
    """
    out: List[str] = []
    replaced = False
    for raw in text.splitlines(keepends=True):
        body, eol = _split_eol(raw)
        bom = ""
        if body.startswith(BOM):
            bom, body = BOM, body[1:]
        if not replaced:
            offset = _match_key(body, key)
            if offset is not None:
                body = body[:offset] + new_value
                replaced = True
        out.append(bom + body + eol)
    if not replaced:
        eol = dominant_eol(text) if text else "\n"
        if out and not out[-1].endswith(("\n", "\r")):
            out[-1] = out[-1] + eol
        out.append(f"{key}={new_value}{eol}")
    return "".join(out), replaced


def remove_key(text: str, key: str) -> Tuple[str, bool]:
    out: List[str] = []
    removed = False
    for raw in text.splitlines(keepends=True):
        body, _eol = _split_eol(raw)
        if body.startswith(BOM):
            body = body[1:]
        if _match_key(body, key) is not None:
            removed = True
            continue
        out.append(raw)
    return "".join(out), removed
