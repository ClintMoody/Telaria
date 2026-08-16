"""Diff engines: per-file skill diffs, config-vs-defaults, SOUL, checkout (R-DIFF-03..06).

Skill diffs mirror upstream `diff_bundled_skill` semantics: unified diff per file with
binary detection by NUL sniff. Config diffing shells the source venv for DEFAULT_CONFIG
when available and degrades honestly otherwise (R-DIFF-04).
"""

from __future__ import annotations

import difflib
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from talaria.engine.resolve import _venv_python, find_install_dir


@dataclass
class FileDiff:
    path: str                    # skill-relative POSIX path
    status: str                  # modified|added|removed|binary
    diff: str = ""               # unified diff text ("" for binary)

    def to_json(self) -> dict:
        return {"path": self.path, "status": self.status, "diff": self.diff}


def _is_binary(blob: bytes) -> bool:
    return b"\x00" in blob[:8192]


def diff_skill_trees(baseline_dir: Path, current_dir: Path) -> List[FileDiff]:
    """Per-file diff between two skill trees (baseline = stock, current = user's)."""
    baseline_dir, current_dir = Path(baseline_dir), Path(current_dir)
    base_files = {p.relative_to(baseline_dir).as_posix(): p
                  for p in baseline_dir.rglob("*") if p.is_file()} if baseline_dir.is_dir() else {}
    cur_files = {p.relative_to(current_dir).as_posix(): p
                 for p in current_dir.rglob("*") if p.is_file()} if current_dir.is_dir() else {}
    out: List[FileDiff] = []
    for rel in sorted(set(base_files) | set(cur_files)):
        in_base, in_cur = rel in base_files, rel in cur_files
        if in_base and not in_cur:
            out.append(FileDiff(rel, "removed"))
            continue
        blob_cur = cur_files[rel].read_bytes()
        blob_base = base_files[rel].read_bytes() if in_base else b""
        if _is_binary(blob_cur) or _is_binary(blob_base):
            if not in_base or blob_base != blob_cur:
                out.append(FileDiff(rel, "binary" if in_base else "added"))
            continue
        if not in_base:
            text = blob_cur.decode("utf-8", errors="replace")
            diff = "".join(difflib.unified_diff(
                [], text.splitlines(keepends=True), fromfile="/dev/null", tofile=rel))
            out.append(FileDiff(rel, "added", diff))
            continue
        if blob_base == blob_cur:
            continue
        diff = "".join(difflib.unified_diff(
            blob_base.decode("utf-8", errors="replace").splitlines(keepends=True),
            blob_cur.decode("utf-8", errors="replace").splitlines(keepends=True),
            fromfile=f"stock/{rel}", tofile=f"yours/{rel}"))
        out.append(FileDiff(rel, "modified", diff))
    return out


def diff_modified_stock_skill(install_dir: Optional[Path], skills_dir: Path,
                              skill_rel: str, category_rel: Optional[str] = None
                              ) -> Tuple[List[FileDiff], str]:
    """Diff a user's stock skill against the repo copy when the checkout exists.

    Returns (diffs, status) where status explains a degraded result.
    """
    current = Path(skills_dir) / skill_rel
    if install_dir is None:
        return [], "no Hermes checkout — stock baseline unavailable for line diffs"
    bundled_root = Path(install_dir) / "skills"
    candidate = bundled_root / (category_rel or skill_rel)
    if not candidate.is_dir():
        matches = list(bundled_root.glob(f"*/{Path(skill_rel).name}"))
        if len(matches) == 1:
            candidate = matches[0]
        else:
            return [], "skill not found in bundled tree (renamed or optional)"
    return diff_skill_trees(candidate, current), "ok"


# --------------------------------------------------------------------------- config

MASKED = "•••"

#: Config key paths whose values are masked in any diff output (R-SEC-02).
_MASK_KEY_MARKERS = ("api_key", "password", "secret", "token", "authorization")


@dataclass
class ConfigDiff:
    status: str                          # ok|unknown_no_venv
    customized: Dict[str, dict] = field(default_factory=dict)  # dotted key -> {default, current}
    sections_total: int = 0
    sections_customized: int = 0

    def to_json(self) -> dict:
        return {"status": self.status, "customized": self.customized,
                "sections_total": self.sections_total,
                "sections_customized": self.sections_customized}


def extract_default_config(install_dir: Path) -> Optional[dict]:
    """DEFAULT_CONFIG via the source venv (enrichment; None when unavailable)."""
    py = _venv_python(Path(install_dir))
    if py is None:
        return None
    code = ("import json;from hermes_cli.config_defaults import DEFAULT_CONFIG;"
            "print(json.dumps(DEFAULT_CONFIG))")
    try:
        out = subprocess.run([str(py), "-c", code], capture_output=True, text=True,
                             timeout=45, check=False, cwd=str(install_dir))
        if out.returncode == 0 and out.stdout.lstrip().startswith("{"):
            return json.loads(out.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None


def diff_config(user_config: dict, default_config: Optional[dict]) -> ConfigDiff:
    """Deep-diff user config vs defaults; credential-key values masked (R-DIFF-04)."""
    if default_config is None:
        return ConfigDiff(status="unknown_no_venv")
    customized: Dict[str, dict] = {}

    def mask(key: str, value):
        if any(m in key.lower() for m in _MASK_KEY_MARKERS):
            return MASKED
        return value

    def walk(user_node, default_node, prefix: str):
        if isinstance(user_node, dict):
            for key, value in user_node.items():
                if key == "_config_version":
                    continue
                dotted = f"{prefix}.{key}" if prefix else str(key)
                dnode = default_node.get(key) if isinstance(default_node, dict) else None
                if isinstance(value, dict) and isinstance(dnode, dict):
                    walk(value, dnode, dotted)
                elif value != dnode:
                    customized[dotted] = {"default": mask(dotted, dnode),
                                          "current": mask(dotted, value)}
        elif user_node != default_node:
            customized[prefix] = {"default": mask(prefix, default_node),
                                  "current": mask(prefix, user_node)}

    walk(user_config, default_config, "")
    top_user = {k for k in user_config if k != "_config_version"}
    customized_sections = {key.split(".", 1)[0] for key in customized}
    return ConfigDiff(status="ok", customized=customized,
                      sections_total=max(len(set(default_config) | top_user), 1),
                      sections_customized=len(customized_sections))


# --------------------------------------------------------------------------- soul

def diff_soul(soul_path: Path, install_dir: Optional[Path]) -> Tuple[str, str]:
    """('customized'|'stock'|'unknown', unified diff). Compares against the shipped default.

    The default persona lives in the checkout (install research §8); absent checkout we
    report 'unknown' rather than guessing (anti-overclaiming).
    """
    try:
        current = Path(soul_path).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return "unknown", ""
    default_text = _find_default_soul(install_dir)
    if default_text is None:
        return "unknown", ""
    if current.strip() == default_text.strip():
        return "stock", ""
    diff = "".join(difflib.unified_diff(
        default_text.splitlines(keepends=True), current.splitlines(keepends=True),
        fromfile="stock/SOUL.md", tofile="yours/SOUL.md"))
    return "customized", diff


def _find_default_soul(install_dir: Optional[Path]) -> Optional[str]:
    if install_dir is None:
        return None
    for rel in ("hermes_cli/default_soul.py", "agent/default_soul.py"):
        cand = Path(install_dir) / rel
        if cand.is_file():
            try:
                text = cand.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            # The default persona is a module-level triple-quoted string.
            for quote in ('"""', "'''"):
                start = text.find(quote)
                if start != -1:
                    end = text.find(quote, start + 3)
                    if end != -1:
                        return text[start + 3:end]
    for rel in ("assets/SOUL.default.md", "SOUL.md"):
        cand = Path(install_dir) / rel
        if cand.is_file():
            try:
                return cand.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return None


# --------------------------------------------------------------------------- checkout

@dataclass
class CheckoutState:
    status: str                      # clean|dirty|absent|not-git
    patch: str = ""                  # git diff output (dirty stock files)
    untracked: List[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {"status": self.status, "untracked": self.untracked,
                "patch_bytes": len(self.patch.encode("utf-8"))}


def checkout_state(root: Path) -> CheckoutState:
    """Record the code checkout as ref + dirty patch + untracked list (R-DIFF-06)."""
    install_dir = find_install_dir(Path(root))
    if install_dir is None:
        return CheckoutState(status="absent")
    if not (install_dir / ".git").exists():
        return CheckoutState(status="not-git")

    def git(*args: str) -> Optional[str]:
        try:
            out = subprocess.run(["git", "-C", str(install_dir), *args],
                                 capture_output=True, text=True, timeout=30, check=False)
            return out.stdout if out.returncode == 0 else None
        except (OSError, subprocess.SubprocessError):
            return None

    porcelain = git("status", "--porcelain") or ""
    untracked = [line[3:] for line in porcelain.splitlines() if line.startswith("?? ")]
    dirty = any(not line.startswith("??") for line in porcelain.splitlines())
    if not dirty and not untracked:
        return CheckoutState(status="clean")
    patch = git("diff", "HEAD") or ""
    return CheckoutState(status="dirty", patch=patch, untracked=untracked)
