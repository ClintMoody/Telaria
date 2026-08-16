"""Path correctness helpers: Windows legality, long paths, containment, rename maps.

All functions are pure and take the platform as data (a :class:`FsFlavor`), so Linux CI
exercises Windows semantics (ARCHITECTURE §15.3). The live flavor for this host is
:func:`host_flavor`.
"""

from __future__ import annotations

import os
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

# Windows reserved device names (case-insensitive, with or without extension).
WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
WINDOWS_ILLEGAL_CHARS = '<>:"|?*'
DEFAULT_MAX_PATH = 260


@dataclass(frozen=True)
class FsFlavor:
    """Filesystem semantics as data."""

    sep: str = "/"
    case_insensitive: bool = False
    normalizes_unicode: bool = False   # APFS-style NFD folding behavior
    windows_rules: bool = False        # reserved names / illegal chars / trailing dot-space
    max_path: Optional[int] = None


POSIX_FLAVOR = FsFlavor()
WINDOWS_FLAVOR = FsFlavor(sep="\\", case_insensitive=True, windows_rules=True,
                          max_path=DEFAULT_MAX_PATH)
MACOS_FLAVOR = FsFlavor(case_insensitive=True, normalizes_unicode=True)

FLAVORS = {"linux": POSIX_FLAVOR, "termux": POSIX_FLAVOR, "macos": MACOS_FLAVOR,
           "windows": WINDOWS_FLAVOR}


def host_flavor() -> FsFlavor:
    if sys.platform == "win32":
        return WINDOWS_FLAVOR
    if sys.platform == "darwin":
        return MACOS_FLAVOR
    return POSIX_FLAVOR


# ------------------------------------------------------------------ legality

def windows_name_problems(name: str) -> List[str]:
    """Why one path *component* is illegal on Windows (empty list = legal)."""
    problems: List[str] = []
    stem = name.split(".", 1)[0]
    if stem.upper() in WINDOWS_RESERVED:
        problems.append(f"reserved device name '{stem.upper()}'")
    bad = sorted({c for c in name if c in WINDOWS_ILLEGAL_CHARS or ord(c) < 32})
    if bad:
        problems.append("illegal characters " + "".join(bad))
    if name.endswith((".", " ")):
        problems.append("trailing dot or space")
    if "\\" in name or "/" in name:
        problems.append("separator inside component")
    return problems


def windows_path_problems(rel_posix: str) -> List[str]:
    """Aggregate problems for a POSIX-relative path checked against Windows rules."""
    problems: List[str] = []
    for part in rel_posix.split("/"):
        for issue in windows_name_problems(part):
            problems.append(f"{part}: {issue}")
    return problems


def sanitize_for_windows(name: str) -> str:
    """Deterministic legal rename for one component (R-APPLY-18 rename maps)."""
    out = []
    for ch in name:
        if ch in WINDOWS_ILLEGAL_CHARS or ord(ch) < 32:
            out.append("_")
        else:
            out.append(ch)
    result = "".join(out).rstrip(". ")
    if not result:
        result = "_"
    stem, dot, ext = result.partition(".")
    if stem.upper() in WINDOWS_RESERVED:
        result = "_" + result
    return result


def build_rename_map(rel_paths: Iterable[str]) -> Dict[str, str]:
    """Deterministic rename map for Windows-illegal paths, re-checked for collisions.

    Keys are the original POSIX rel paths that need renaming; values are legal
    replacements, suffixed ``~2``, ``~3``… on collision with existing or produced names.
    """
    paths = list(rel_paths)
    taken = {casefold_key(p) for p in paths}
    renames: Dict[str, str] = {}
    for rel in paths:
        if not windows_path_problems(rel):
            continue
        parts = [sanitize_for_windows(p) for p in rel.split("/")]
        candidate = "/".join(parts)
        if casefold_key(candidate) in taken - {casefold_key(rel)} or candidate in renames.values():
            base, dot, ext = candidate.rpartition(".")
            stem = base if dot else candidate
            suffix = ext if dot else ""
            n = 2
            while True:
                probe = f"{stem}~{n}" + (f".{suffix}" if suffix else "")
                if casefold_key(probe) not in taken and probe not in renames.values():
                    candidate = probe
                    break
                n += 1
        renames[rel] = candidate
        taken.add(casefold_key(candidate))
    return renames


# ------------------------------------------------------------------ collisions

def casefold_key(rel_posix: str) -> str:
    """Collision key under case-insensitive + unicode-normalizing semantics."""
    return unicodedata.normalize("NFC", rel_posix).casefold()


def find_collisions(rel_paths: Iterable[str]) -> List[List[str]]:
    """Groups of distinct paths that collide under casefold+NFC (and NFD) semantics."""
    groups: Dict[str, List[str]] = {}
    for rel in rel_paths:
        groups.setdefault(casefold_key(rel), []).append(rel)
        nfd = unicodedata.normalize("NFD", rel).casefold()
        if nfd != casefold_key(rel):
            groups.setdefault(nfd, []).append(rel)
    seen: set = set()
    out: List[List[str]] = []
    for members in groups.values():
        distinct = sorted(set(members))
        if len(distinct) > 1 and tuple(distinct) not in seen:
            seen.add(tuple(distinct))
            out.append(distinct)
    return out


# ------------------------------------------------------------------ containment

def is_contained(child: str, root: str, flavor: Optional[FsFlavor] = None) -> bool:
    """True when ``child`` (absolute) is ``root`` or inside it — component-safe.

    Avoids the competitor's `startswith` prefix bug (`/target-evil` vs `/target`).
    Case-insensitive comparison under Windows/mac flavors.
    """
    flavor = flavor or host_flavor()
    child_n = os.path.normpath(child)
    root_n = os.path.normpath(root)
    if flavor.case_insensitive:
        child_n, root_n = child_n.lower(), root_n.lower()
    if flavor.sep == "\\":
        child_n = child_n.replace("/", "\\")
        root_n = root_n.replace("/", "\\")
        parts_c = [p for p in re.split(r"[\\]+", child_n) if p]
        parts_r = [p for p in re.split(r"[\\]+", root_n) if p]
    else:
        parts_c = [p for p in child_n.split("/") if p]
        parts_r = [p for p in root_n.split("/") if p]
    return parts_c[: len(parts_r)] == parts_r


def member_name_problems(member: str) -> List[str]:
    """Bundle/zip member-name legality (R-BND-07): reject anything path-hostile."""
    problems: List[str] = []
    if member.startswith("/") or member.startswith("\\"):
        problems.append("absolute path")
    if re.match(r"^[A-Za-z]:", member):
        problems.append("drive letter")
    if member.startswith("//") or member.startswith("\\\\"):
        problems.append("UNC path")
    if "\\" in member:
        problems.append("backslash separator")
    parts = member.split("/")
    if any(p == ".." for p in parts):
        problems.append("parent traversal '..'")
    if any(p == "" for p in parts[:-1]):
        problems.append("empty component")
    for part in parts:
        stem = part.split(".", 1)[0]
        if stem.upper() in WINDOWS_RESERVED:
            problems.append(f"reserved name component '{part}'")
        if part.endswith((".", " ")) and part not in (".", ""):
            problems.append(f"trailing dot/space component '{part}'")
    return problems


# ------------------------------------------------------------------ long paths

def extended_length(path: str) -> str:
    r"""Apply the Windows \\?\ prefix for tool I/O (never for final recorded paths)."""
    if sys.platform != "win32":
        return path
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):  # UNC
        return "\\\\?\\UNC" + path[1:]
    return "\\\\?\\" + os.path.abspath(path)


def longest_final_path(root: str, rel_paths: Iterable[str], flavor: FsFlavor) -> Tuple[int, str]:
    """(length, path) of the longest final path a placement would create."""
    best = (0, "")
    for rel in rel_paths:
        full = root.rstrip("/\\") + flavor.sep + rel.replace("/", flavor.sep)
        if len(full) > best[0]:
            best = (len(full), full)
    return best


# ------------------------------------------------------------------ translation

def translate_home_path(value: str, source_home: str, target_home: str,
                        source_sep: str, target_sep: str) -> Optional[str]:
    """Structurally translate one absolute path that lives under the source home.

    Returns the translated path, or None when ``value`` is not under ``source_home``
    (caller then flags instead of rewriting — R-XPLAT-01 rule-addressed fields only).
    """
    norm_value = value.replace("\\", "/") if source_sep == "\\" else value
    norm_home = source_home.replace("\\", "/") if source_sep == "\\" else source_home
    norm_home = norm_home.rstrip("/")
    if not norm_value.startswith(norm_home):
        return None
    remainder = norm_value[len(norm_home):]
    if remainder and not remainder.startswith("/"):
        return None
    rel = remainder.lstrip("/")
    target = target_home.rstrip("/\\")
    if rel:
        target = target + target_sep + rel.replace("/", target_sep)
    return target
