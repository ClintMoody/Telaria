"""Core dataclasses of the artifact model (ARCHITECTURE §2.1).

Portability classes (integ research §0): "a" = copy verbatim, "b" = copy with rewriting,
"c" = machine-bound (recreate on target). The research's "(d) secret material" class became
the orthogonal ``secrecy`` axis (D2): "credential" never travels in plaintext, "content" is
private-but-travels.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

VERDICTS = ("ok", "ok_after_rewrite", "action", "missing_installable",
            "impossible", "unknown_offline")

#: Verdict → wizard who-acts group (SPEC §7.3, binding single mapping — R-DEPS-05).
WHO_ACTS = {
    "ok": "Ready to move in",
    "ok_after_rewrite": "We'll fix these automatically",
    "action": "Needs you afterwards",
    "missing_installable": "Needs you afterwards",
    "unknown_offline": "Needs you afterwards",
    "impossible": "Can't come along",
}

TARGET_OSES = ("linux", "macos", "windows", "termux")


@dataclass
class FileEntry:
    home_rel: str                 # POSIX, relative to the profile ROOT
    size: int
    mode: int
    mtime: float
    sha256: Optional[str] = None  # filled during pack (scan is metadata-only, R-SCAN-06)
    is_symlink: bool = False      # recorded, never followed (R-SCAN-05)
    is_sqlite: bool = False       # captured via snapshot protocol when True

    def to_json(self) -> dict:
        record = {"home_rel": self.home_rel, "size": self.size, "mode": self.mode,
                  "mtime": self.mtime}
        if self.sha256:
            record["sha256"] = self.sha256
        if self.is_symlink:
            record["is_symlink"] = True
        if self.is_sqlite:
            record["is_sqlite"] = True
        return record


@dataclass
class Dependency:
    kind: str        # os|env_var|binary|python_pkg|lazy_feature|node|network|service|
                     # credential_file|artifact_ref|config_key|platform
    name: str
    enforced: bool = False   # True only for env vars + platforms[] (skills research §6)
    detail: Dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"kind": self.kind, "name": self.name, "enforced": self.enforced,
                "detail": self.detail}


@dataclass
class Touchpoint:
    """One entry of the discovery ledger (R-DISC-01)."""

    path: str
    provenance: List[str]     # config-ref|cron-ref|skill-ref|plugin-ref|db-mined|agent-reported
    confidence: str           # verified|corroborated|advisory
    verdict: str = ""         # portability note ("outside-home", "missing", ...)
    exists: Optional[bool] = None
    inside_home: Optional[bool] = None

    def to_json(self) -> dict:
        return {"path": self.path, "provenance": self.provenance,
                "confidence": self.confidence, "verdict": self.verdict,
                "exists": self.exists, "inside_home": self.inside_home}


@dataclass
class Artifact:
    id: str                   # "<kind>@<profile>[/<discriminator>]"
    kind: str
    family: str
    profile: str              # "" = root profile
    files: List[FileEntry] = field(default_factory=list)
    portability: str = "a"    # a|b|c
    secrecy: str = "none"     # none|credential|content
    machine_bound: bool = False
    default: str = "on"       # on|off|record_only|never
    provenance: Dict = field(default_factory=dict)
    dependencies: List[Dependency] = field(default_factory=list)
    feasibility: Dict[str, str] = field(default_factory=dict)   # target-os -> verdict
    selected: bool = True
    couples: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def travels(self) -> bool:
        return self.default not in ("never", "record_only") and self.selected

    def to_json(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "family": self.family, "profile": self.profile,
            "class": self.portability, "secrecy": self.secrecy,
            "machine_bound": self.machine_bound, "default": self.default,
            "selected": self.selected, "provenance": self.provenance,
            "deps": [d.to_json() for d in self.dependencies],
            "feasibility": self.feasibility, "couples": self.couples,
            "reasons": self.reasons, "files": [f.to_json() for f in self.files],
        }


def artifact_id(kind: str, profile: str, discriminator: str = "") -> str:
    base = f"{kind}@{profile}"
    return f"{base}/{discriminator}" if discriminator else base
