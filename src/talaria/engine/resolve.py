"""HERMES_HOME, profile, and install-identity resolution (ARCHITECTURE §4.1).

Encodes hermes_constants.py:53-59/114-210 (home precedence, profile split), the Windows
HKCU fallback (GUI apps miss post-login setx — install §4), and the install-identity
detection: version triple, install method, git state, config version, lazy features.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from talaria.platform.winreg_compat import read_hkcu_env


def default_home_for(platform: str, home_dir: str, localappdata: Optional[str] = None) -> str:
    """Default HERMES_HOME for a platform (hermes_constants.py:53-59)."""
    if platform.startswith("win"):
        base = localappdata.strip() if localappdata and localappdata.strip() else None
        if base:
            return base.rstrip("\\/") + "\\hermes"
        return home_dir.rstrip("\\/") + "\\AppData\\Local\\hermes"
    return home_dir.rstrip("/") + "/.hermes"


def resolve_home(env: Optional[Dict[str, str]] = None,
                 platform: Optional[str] = None) -> Path:
    """Live HERMES_HOME: $HERMES_HOME → HKCU (Windows) → platform default (R-SCAN-01)."""
    env = os.environ if env is None else env
    platform = platform or sys.platform
    override = (env.get("HERMES_HOME") or "").strip()
    if override:
        return Path(override).expanduser()
    if platform.startswith("win"):
        reg = read_hkcu_env("HERMES_HOME")
        if reg:
            return Path(reg)
        return Path(default_home_for(platform, str(Path.home()), env.get("LOCALAPPDATA")))
    if _is_container():
        candidate = Path("/opt/data")
        if (candidate / "config.yaml").exists() or (candidate / "skills").is_dir():
            return candidate
    return Path.home() / ".hermes"


def _is_container() -> bool:
    if os.environ.get("HERMES_CONTAINER"):
        return True
    return Path("/.dockerenv").exists()


def resolve_root_and_profile(home: Path) -> Tuple[Path, Optional[str]]:
    """(root, active-profile) from a home path; profile homes are <root>/profiles/<name>."""
    home = Path(home)
    if home.parent.name == "profiles":
        return home.parent.parent, home.name
    return home, None


def profile_homes(root: Path) -> Dict[str, Path]:
    """All state homes: {"": root, "<name>": root/profiles/<name>} (R-SCAN-02).

    Symlinked profile directories are skipped — following them would pack whatever the
    link points at (outside HERMES_HOME), violating the never-follow-symlinks rule
    (R-SCAN-05). Skipped profiles are recorded in ``profile_homes.skipped`` for the caller.
    """
    homes: Dict[str, Path] = {"": Path(root)}
    profiles_dir = Path(root) / "profiles"
    if profiles_dir.is_dir():
        for child in sorted(profiles_dir.iterdir()):
            if child.name.startswith("."):
                continue
            if child.is_symlink():
                continue  # never follow — would pack the link's target (R-SCAN-05)
            if child.is_dir():
                homes[child.name] = child
    return homes


def symlinked_profiles(root: Path) -> List[str]:
    """Names of profile entries that are symlinks (skipped by profile_homes)."""
    profiles_dir = Path(root) / "profiles"
    if not profiles_dir.is_dir():
        return []
    return [c.name for c in sorted(profiles_dir.iterdir())
            if c.is_symlink() and not c.name.startswith(".")]


def looks_like_hermes_home(path: Path) -> bool:
    """Marker heuristic mirroring upstream backup validation {config.yaml,.env,state.db}."""
    path = Path(path)
    markers = ("config.yaml", ".env", "state.db", "SOUL.md", "skills")
    return sum(1 for m in markers if (path / m).exists()) >= 2


# --------------------------------------------------------------------------- identity

@dataclass
class InstallIdentity:
    hermes_home: str
    root: str
    active_profile: Optional[str]
    profiles: List[str]
    hermes_version: Optional[str] = None
    release_date: Optional[str] = None
    build_sha: Optional[str] = None
    install_method: str = "unknown"
    install_dir: Optional[str] = None
    git_head: Optional[str] = None
    git_tag: Optional[str] = None
    git_branch: Optional[str] = None
    git_dirty: bool = False
    git_untracked: List[str] = field(default_factory=list)
    config_version: Optional[int] = None
    python: Optional[str] = None
    lazy_features: Optional[List[str]] = None
    layout_family: str = "posix"
    os_name: str = "linux"
    notes: List[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


_VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')
_RELDATE_RE = re.compile(r'__release_date__\s*=\s*"([^"]+)"')


def find_install_dir(root: Path, env: Optional[Dict[str, str]] = None) -> Optional[Path]:
    """The code checkout: $HERMES_INSTALL_DIR → <root>/hermes-agent → system paths."""
    env = os.environ if env is None else env
    override = (env.get("HERMES_INSTALL_DIR") or "").strip()
    candidates = []
    if override:
        candidates.append(Path(override))
    candidates += [Path(root) / "hermes-agent",
                   Path("/usr/local/lib/hermes-agent"), Path("/opt/hermes")]
    for cand in candidates:
        if (cand / "pyproject.toml").is_file() or (cand / "hermes_cli" / "__init__.py").is_file():
            return cand
    return None


def detect_install_method(install_dir: Optional[Path]) -> str:
    """The upstream 7-step detection, transcribed (install §4; config.py:412-513)."""
    if install_dir is None:
        return "unknown"
    marker = install_dir / ".install_method"
    if marker.is_file():
        try:
            value = marker.read_text(encoding="utf-8").strip().lower()
            if value:
                return value
        except OSError:
            pass
    if (install_dir / ".hermes_build_sha").is_file():
        return "docker"
    if (install_dir / ".git").exists():
        return "git"
    if "/nix/store/" in str(install_dir):
        return "nix"
    if (install_dir / "venv").is_dir() or (install_dir / ".venv").is_dir():
        return "git"
    return "unknown"


def _git(install_dir: Path, *args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git", "-C", str(install_dir), *args],
                             capture_output=True, text=True, timeout=15, check=False)
        if out.returncode == 0:
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def detect_identity(home: Path, env: Optional[Dict[str, str]] = None,
                    run_venv_probe: bool = True) -> InstallIdentity:
    """Full install identity (R-SCAN-08); every probe degrades gracefully."""
    env = os.environ if env is None else env
    home = Path(home)
    root, active = resolve_root_and_profile(home)
    profiles = [p for p in profile_homes(root) if p]
    ident = InstallIdentity(
        hermes_home=str(home), root=str(root), active_profile=active, profiles=profiles,
        os_name=("windows" if sys.platform == "win32"
                 else "macos" if sys.platform == "darwin" else "linux"),
        layout_family="windows" if sys.platform == "win32" else "posix",
    )
    active_file = root / "active_profile"
    if ident.active_profile is None and active_file.is_file():
        try:
            name = active_file.read_text(encoding="utf-8").strip()
            if name and name != "default":
                ident.active_profile = name
        except OSError:
            pass

    install_dir = find_install_dir(root, env)
    if install_dir is None:
        ident.notes.append("no Hermes code checkout found (state-only scan)")
    else:
        ident.install_dir = str(install_dir)
        ident.install_method = detect_install_method(install_dir)
        init_py = install_dir / "hermes_cli" / "__init__.py"
        try:
            text = init_py.read_text(encoding="utf-8")
            m = _VERSION_RE.search(text)
            if m:
                ident.hermes_version = m.group(1)
            m = _RELDATE_RE.search(text)
            if m:
                ident.release_date = m.group(1)
        except OSError:
            pass
        if ident.hermes_version is None:
            try:
                pyproject = (install_dir / "pyproject.toml").read_text(encoding="utf-8")
                m = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.M)
                if m:
                    ident.hermes_version = m.group(1)
            except OSError:
                pass
        sha_file = install_dir / ".hermes_build_sha"
        if sha_file.is_file():
            try:
                ident.build_sha = sha_file.read_text(encoding="utf-8").strip()[:40] or None
            except OSError:
                pass
        if (install_dir / ".git").exists():
            ident.git_head = _git(install_dir, "rev-parse", "HEAD")
            ident.git_branch = _git(install_dir, "rev-parse", "--abbrev-ref", "HEAD")
            ident.git_tag = _git(install_dir, "describe", "--tags", "--exact-match") or \
                _git(install_dir, "describe", "--tags", "--abbrev=0")
            porcelain = _git(install_dir, "status", "--porcelain")
            if porcelain:
                ident.git_dirty = any(not l.startswith("??") for l in porcelain.splitlines())
                ident.git_untracked = [l[3:] for l in porcelain.splitlines()
                                       if l.startswith("?? ")]
        if run_venv_probe:
            ident.lazy_features = _probe_lazy_features(install_dir)
            if ident.lazy_features is None:
                ident.notes.append("lazy-extras probe unavailable (no venv python)")

    config = home / "config.yaml"
    if config.is_file():
        ident.config_version = _read_config_version(config)
    ident.python = f"{sys.version_info[0]}.{sys.version_info[1]}.{sys.version_info[2]}"
    return ident


def _read_config_version(config_path: Path) -> Optional[int]:
    """`_config_version: N` — line-scan, no YAML parser in the stdlib core."""
    try:
        with open(config_path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                m = re.match(r"^_config_version:\s*(\d+)", line)
                if m:
                    return int(m.group(1))
    except OSError:
        return None
    return None


def _venv_python(install_dir: Path) -> Optional[Path]:
    for rel in ("venv/bin/python", "venv/Scripts/python.exe",
                ".venv/bin/python", ".venv/Scripts/python.exe"):
        cand = install_dir / rel
        if cand.is_file():
            return cand
    return None


def _probe_lazy_features(install_dir: Path) -> Optional[List[str]]:
    """Enrichment probe of tools.lazy_deps.active_features() via the source venv."""
    py = _venv_python(install_dir)
    if py is None:
        return None
    code = ("import json;import tools.lazy_deps as l;"
            "print(json.dumps(sorted(l.active_features())))")
    try:
        out = subprocess.run([str(py), "-c", code], capture_output=True, text=True,
                             timeout=30, check=False, cwd=str(install_dir))
        if out.returncode == 0 and out.stdout.strip().startswith("["):
            return list(json.loads(out.stdout.strip()))
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return None
