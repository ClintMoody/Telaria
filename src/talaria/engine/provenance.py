"""Skill provenance: the six tags, computed with upstream's own mechanisms (R-DIFF-01).

Sources, in authority order (skills research §5):
- ``skills/.bundled_manifest`` — `name:md5` seed-time baseline (dir-hash, OS-parameterized)
- ``skills/.hub/lock.json`` — hub install provenance
- ``skills/_org/<id>/.org-baseline.json`` — org fingerprints (flagged, never recomputed)
- ``skills/.usage.json`` ``created_by`` — agent vs user authorship

The three digest schemes are never cross-compared; ``dir_hash`` takes explicit semantics
(D14/C2-01) and the manifest we write records which semantics were used.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

TAGS = ("stock-pristine", "stock-modified", "stock-deleted", "hub-installed", "org",
        "agent-created", "user-created")

#: Support dirs whose nested SKILL.md is data, not a skill (agent/skill_utils.py:50).
SKILL_SUPPORT_DIRS = frozenset({"references", "templates", "assets", "scripts", "tests"})

#: Dirs excluded from skill discovery (agent/skill_utils.py:27-44).
EXCLUDED_SKILL_DIRS = frozenset({".git", ".hub", ".archive", ".venv", "venv",
                                 "node_modules", "site-packages", "__pycache__",
                                 ".curator_backups", ".restore-backups", "_org"})


@dataclass
class HashSemantics:
    separator: str = "posix"     # posix|nt — rel-path separator flavor
    collation: str = "posix"     # posix (byte sort) | nt (casefolded sort)

    def to_json(self) -> dict:
        return {"separator": self.separator, "collation": self.collation}

    @classmethod
    def for_os(cls, os_name: str) -> "HashSemantics":
        if os_name == "windows":
            return cls(separator="nt", collation="nt")
        return cls()


def dir_hash(directory: Path, semantics: Optional[HashSemantics] = None) -> str:
    """`tools/skills_sync._dir_hash` mirrored, parameterized by OS semantics (R-DIFF-02)."""
    semantics = semantics or HashSemantics()
    sep = "\\" if semantics.separator == "nt" else "/"
    entries: List[Tuple[str, Path]] = []
    directory = Path(directory)
    for fpath in directory.rglob("*"):
        if fpath.is_file():
            rel = fpath.relative_to(directory).as_posix().replace("/", sep)
            entries.append((rel, fpath))
    if semantics.collation == "nt":
        entries.sort(key=lambda item: item[0].casefold())
    else:
        entries.sort(key=lambda item: item[0])
    hasher = hashlib.md5()
    for rel, fpath in entries:
        hasher.update(rel.encode("utf-8"))
        hasher.update(fpath.read_bytes())
    return hasher.hexdigest()


# --------------------------------------------------------------------------- readers

def read_bundled_manifest(skills_dir: Path) -> Dict[str, str]:
    """`.bundled_manifest` — `<frontmatter-name>:<md5>` per line; '' hash = v1 untracked."""
    path = Path(skills_dir) / ".bundled_manifest"
    result: Dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            name, _, digest = line.rpartition(":")
            if name:
                result[name] = digest.strip()
    except OSError:
        pass
    return result


def read_hub_lock(skills_dir: Path) -> Dict[str, dict]:
    path = Path(skills_dir) / ".hub" / "lock.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
        installed = data.get("installed", {})
        return installed if isinstance(installed, dict) else {}
    except (OSError, ValueError):
        return {}


def read_usage(skills_dir: Path) -> Dict[str, dict]:
    path = Path(skills_dir) / ".usage.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def read_org_baselines(skills_dir: Path) -> Dict[str, dict]:
    """Union of `_org/<id>/.org-baseline.json` skill fingerprints (flag-only use)."""
    out: Dict[str, dict] = {}
    org_root = Path(skills_dir) / "_org"
    if not org_root.is_dir():
        return out
    for org_dir in sorted(org_root.iterdir()):
        baseline = org_dir / ".org-baseline.json"
        if not baseline.is_file():
            continue
        try:
            data = json.loads(baseline.read_text(encoding="utf-8-sig", errors="replace"))
        except (OSError, ValueError):
            continue
        skills = data.get("skills", data if isinstance(data, dict) else {})
        if isinstance(skills, dict):
            for name, record in skills.items():
                out[name] = record if isinstance(record, dict) else {}
    return out


def parse_frontmatter_name(skill_md: Path) -> Optional[str]:
    """The frontmatter `name:` — the manifest key (NOT the directory name).

    Mirrors upstream's tolerant read: BOM stripped, naive `key: value` fallback.
    """
    try:
        text = skill_md.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return None
    if not text.startswith("---"):
        return None
    body = text.split("---", 2)
    if len(body) < 3:
        return None
    for line in body[1].splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            value = stripped[len("name:"):].strip()
            if value and value[0] == value[-1] and value[0] in "\"'" and len(value) >= 2:
                value = value[1:-1]
            return value or None
    return None


# --------------------------------------------------------------------------- discovery

def iter_skill_dirs(skills_dir: Path) -> List[Path]:
    """Every directory containing a SKILL.md, honoring support-dir and exclusion rules."""
    skills_dir = Path(skills_dir)
    found: List[Path] = []
    if not skills_dir.is_dir():
        return found

    def walk(directory: Path, inside_skill: bool) -> None:
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        is_skill = (directory / "SKILL.md").is_file() and directory != skills_dir
        if is_skill and not inside_skill:
            found.append(directory)
        for child in children:
            if not child.is_dir():
                continue
            name = child.name
            if name in EXCLUDED_SKILL_DIRS or name.startswith(".") and directory == skills_dir:
                continue
            if is_skill and name in SKILL_SUPPORT_DIRS:
                continue  # nested SKILL.md under support dirs is data
            walk(child, inside_skill or is_skill)

    walk(skills_dir, False)
    return found


# --------------------------------------------------------------------------- tagging

@dataclass
class SkillProvenance:
    directory: str               # skills-root-relative POSIX path
    name: str                    # frontmatter name (manifest key)
    tag: str                     # one of TAGS
    seeded_hash: Optional[str] = None
    current_hash: Optional[str] = None
    usage: Dict = field(default_factory=dict)
    hub: Dict = field(default_factory=dict)
    detail: str = ""

    def to_json(self) -> dict:
        return {"directory": self.directory, "name": self.name, "tag": self.tag,
                "seeded_hash": self.seeded_hash, "current_hash": self.current_hash,
                "detail": self.detail,
                "created_by": self.usage.get("created_by"),
                "use_count": self.usage.get("use_count")}


def classify_skills(skills_dir: Path,
                    semantics: Optional[HashSemantics] = None) -> List[SkillProvenance]:
    """Provenance-tag every skill under ``skills_dir`` (R-DIFF-01)."""
    semantics = semantics or HashSemantics()
    skills_dir = Path(skills_dir)
    manifest = read_bundled_manifest(skills_dir)
    hub = read_hub_lock(skills_dir)
    usage = read_usage(skills_dir)
    org = read_org_baselines(skills_dir)

    results: List[SkillProvenance] = []
    seen_names: set = set()
    for skill_path in iter_skill_dirs(skills_dir):
        rel = skill_path.relative_to(skills_dir).as_posix()
        name = parse_frontmatter_name(skill_path / "SKILL.md") or skill_path.name
        seen_names.add(name)
        record = SkillProvenance(directory=rel, name=name, tag="user-created",
                                 usage=usage.get(name, {}))
        if name in manifest:
            seeded = manifest[name]
            record.seeded_hash = seeded
            if not seeded:
                record.tag = "stock-modified"
                record.detail = "v1 manifest entry (no hash) — modification not tracked"
            else:
                current = dir_hash(skill_path, semantics)
                record.current_hash = current
                record.tag = "stock-pristine" if current == seeded else "stock-modified"
        elif name in hub:
            record.tag = "hub-installed"
            record.hub = hub[name]
        elif name in org:
            record.tag = "org"
        elif usage.get(name, {}).get("created_by") == "agent":
            record.tag = "agent-created"
        else:
            record.tag = "user-created"
        results.append(record)

    for name, seeded in manifest.items():
        if name not in seen_names:
            results.append(SkillProvenance(
                directory="", name=name, tag="stock-deleted", seeded_hash=seeded,
                detail="in .bundled_manifest but absent on disk — deletion respected "
                       "by upstream sync"))
    return results


def rebaseline_manifest(manifest: Dict[str, str], provenances: List[SkillProvenance],
                        skills_dir: Path, target_semantics: HashSemantics) -> Dict[str, str]:
    """Cross-OS rebaseline (D14): recompute hashes for stock-PRISTINE skills only.

    Modified skills keep their seed-time hash (any mismatch still reads "modified" —
    correct); deleted entries are preserved.
    """
    out = dict(manifest)
    for prov in provenances:
        if prov.tag == "stock-pristine" and prov.directory:
            out[prov.name] = dir_hash(Path(skills_dir) / prov.directory, target_semantics)
    return out


def write_bundled_manifest(skills_dir: Path, manifest: Dict[str, str]) -> None:
    path = Path(skills_dir) / ".bundled_manifest"
    lines = [f"{name}:{digest}" for name, digest in manifest.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
