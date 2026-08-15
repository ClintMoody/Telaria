"""Hermes install layout knowledge: where things live and what they are.

This module is data-first: it encodes the ground truth mined from hermes-agent source
(docs/research/subsystem-state-layout.md and friends) so every engine shares one vocabulary.
Nothing here touches the network; resolution functions accept explicit parameters so tests
and cross-platform simulation never depend on the host machine.

Citations in comments are repo-relative paths into NousResearch/hermes-agent @ 0.20.1.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

# --------------------------------------------------------------------------- roots

#: Layout families. POSIX covers Linux, macOS, WSL2, Termux; WINDOWS is native Windows.
POSIX = "posix"
WINDOWS = "windows"


def default_home_for(platform: str, home_dir: str, localappdata: Optional[str] = None) -> str:
    """Default HERMES_HOME for a platform, mirroring hermes_constants.py:53-59.

    ``platform`` is a ``sys.platform``-style string; ``home_dir`` the user's home directory
    as a string in that platform's flavor.
    """
    if platform.startswith("win"):
        base = localappdata.strip() if localappdata and localappdata.strip() else None
        if base:
            return base.rstrip("\\/") + "\\hermes"
        return home_dir.rstrip("\\/") + "\\AppData\\Local\\hermes"
    return home_dir.rstrip("/") + "/.hermes"


def resolve_home(env: Optional[Dict[str, str]] = None) -> Path:
    """Resolve the live machine's HERMES_HOME: $HERMES_HOME else platform default.

    Mirrors hermes_constants.py:114-139 (minus the in-process context override, which
    cannot apply to an external tool).
    """
    env = os.environ if env is None else env
    override = (env.get("HERMES_HOME") or "").strip()
    if override:
        return Path(override).expanduser()
    if sys.platform == "win32":
        return Path(
            default_home_for("win32", str(Path.home()), env.get("LOCALAPPDATA"))
        )
    return Path.home() / ".hermes"


def resolve_root_and_profile(home: Path) -> Tuple[Path, Optional[str]]:
    """Split a HERMES_HOME into (root, active-profile-name).

    A profile home looks like ``<root>/profiles/<name>`` (hermes_constants.py:173-210).
    The scanner must anchor at the ROOT so every profile is captured (backup.py:583).
    """
    home = Path(home)
    if home.parent.name == "profiles":
        return home.parent.parent, home.name
    return home, None


def profile_homes(root: Path) -> Dict[Optional[str], Path]:
    """All state homes under a root: ``{None: root, "name": root/profiles/name, ...}``."""
    homes: Dict[Optional[str], Path] = {None: Path(root)}
    profiles_dir = Path(root) / "profiles"
    if profiles_dir.is_dir():
        for child in sorted(profiles_dir.iterdir()):
            if child.is_dir() and not child.name.startswith("."):
                homes[child.name] = child
    return homes


# --------------------------------------------------------------------------- classifications

#: Machine-bound runtime files — never captured, and filtered again on apply even when an
#: old bundle contains them (both-sides defense; backup.py:95-129, container_boot.py:75).
MACHINE_BOUND_NAMES = frozenset({
    "gateway_state.json",
    "gateway.pid",
    "cron.pid",
    "gateway.lock",
    "processes.json",
    "auth.lock",
    ".backup.lock",
    ".tick.lock",
    ".jobs.lock",
    ".mcp-discovery.lock",
    ".usage.json.lock",
    "install.lock",
    ".dispatcher.lock",
    ".clean_shutdown",
    "ticker_heartbeat",
    "ticker_last_success",
    ".update_check",
    ".sync_device_id",
    ".termux_bundled_sync_stamp",
    ".container-mode",
    ".managed",
    ".gateway-launchd-unsupported",
    "web-ui-build-stamp.json",
    "desktop-build-stamp.json",
})

#: File-name prefixes that are machine-bound (restart markers, transient temp files).
MACHINE_BOUND_PREFIXES = (".restart_", ".jobs_", ".hb_", ".output_", ".update_pending")

#: SQLite sidecars — a snapshot plus a stale sidecar is a torn restore (backup.py:78-89).
SQLITE_SIDECAR_SUFFIXES = (".db-wal", ".db-shm", ".db-journal", "-wal", "-shm", "-journal")

#: Directory names (matched at any depth) that are regeneratable dependency/cache trees.
#: One special case handled in code, not here: ``hermes-agent`` prunes at ROOT level only —
#: skills/autonomous-ai-agents/hermes-agent/ is real content (backup.py:39-42,297-319).
REGENERATABLE_DIR_NAMES = frozenset({
    "__pycache__",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "site-packages",
    ".cache",
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "backups",
    "checkpoints",       # session-hash-keyed to absolute paths; meaningless off-machine
})

#: Root-relative directories that are vendored runtimes / caches — never packed.
#: (state-layout §2.8-2.9; each is regenerated by installer or first run.)
VENDORED_ROOT_DIRS = frozenset({
    "hermes-agent",      # the code checkout — recorded as a CodeCheckout artifact instead
    "bin",               # managed uv / tirith / bws binaries
    "node",              # managed Node.js
    "git",               # Windows portable MinGit
    "lib",               # native libs (libfts5_cjk.so)
    "lsp",               # LSP server binaries
    "gateway-service",
    "packages",
    "agent-browser",
    "lazy-packages",
    ".worktrees",
    "logs",
    "cache",
    "image_cache",
    "audio_cache",
    "document_cache",
    "video_cache",
    "images",
    "browser_screenshots",
    "browser_recordings",
    "chrome-debug",
    "sandboxes",
    "pastes",
    "disk-cleanup",
    "tmp",
    "state-snapshots",
    "session-exports",   # user-triggered exports; offered as optional extras, not defaults
    "mcp-installs",      # node_modules/venv trees; re-provisioned from config on target
    "runtime",
    "pending_messages",
    "moa-traces",
    "spawn-trees",
    "proxy",             # iron proxy keys/pids/nonces — machine-local security material
    "telemetry",
})

#: Path fragments under skills/ that are regeneratable (skills report §8 capture set).
SKILLS_DROP_SUBPATHS = (
    ".hub/index-cache",
    ".hub/quarantine",
    ".curator_backups",
    ".restore-backups",
)

#: Files whose content is secret material (plaintext on disk — Hermes has no keyring).
#: Names matched by basename; directories by trailing slash. state-layout §2.2.
SECRET_BASENAMES = frozenset({
    ".env",
    ".op.env",
    "auth.json",
    ".anthropic_oauth.json",
    "nous_auth.json",
    "google_token.json",
    "google_client_secret.json",
    "google_oauth_pending.json",
    "google_oauth.json",
    "slack_tokens.json",
    "webhook_subscriptions.json",
    "creds.json",            # whatsapp/session/creds.json (also device-bound)
    "honcho.json",
    "mem0.json",
})

#: Directories (root-relative or basename) that hold secret material entirely.
SECRET_DIR_NAMES = frozenset({
    "mcp-tokens",
    "pairing",
    "credentials",
})

#: Env var name patterns that mark a value as secret (for .env classification and the
#: Secrets Handoff Checklist).
SECRET_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS", "CREDENTIAL", "AUTH")

#: Device-bound state: copying it while the source machine still runs fights for the
#: device slot (WhatsApp Baileys session; integrations report). Captured only with an
#: explicit override; default is re-pair on target.
DEVICE_BOUND_SUBPATHS = (
    "whatsapp/session",
    "platforms/whatsapp/session",
    "signal-cli",
)

#: Known SQLite stores by root-relative path (state-layout §2.3). Others are discovered
#: by header sniffing during the walk.
KNOWN_DATABASES = (
    "state.db",
    "kanban.db",
    "projects.db",
    "response_store.db",
    "memory_store.db",
    "verification_evidence.db",
    "retaindb_queue.db",
    "cron/executions.db",
    "cron/notepad.db",
    "gateway/discord_message_recovery.db",
)

#: Root-level files/dirs that form the portable identity/config core.
IDENTITY_FILES = (
    "config.yaml",
    "SOUL.md",
    "MEMORY.md",
    "USER.md",
    "todo.json",
    "system_prompt.md",
    "AGENTS.md",
    "CLAUDE.md",
    ".cursorrules",
    "desktop.json",
    "active_profile",
    "mcp.json",
    "channel_directory.json",
    "channel_aliases.json",
    ".no-bundled-skills",
)

#: External-to-home state declared by memory providers (captured under _external/,
#: home-relative — backup.py:134-139).
EXTERNAL_HOME_DIRS = ("~/.honcho", "~/.hindsight", "~/.openviking/ovcli.conf")

#: config.yaml keys whose values are absolute paths or machine-local endpoints
#: (rewrite-or-warn list; state-layout §7).
CONFIG_PATH_KEYS = (
    "terminal.cwd",
    "skills.external_dirs",
    "prefill_messages_file",
    "lsp",
    "browser",
)

#: Config schema floor: below this, upstream migrations refuse (config_migrations.py:52).
CONFIG_VERSION_FLOOR = 12


# --------------------------------------------------------------------------- predicates

def is_machine_bound_name(name: str) -> bool:
    if name in MACHINE_BOUND_NAMES:
        return True
    return any(name.startswith(p) for p in MACHINE_BOUND_PREFIXES)


def is_sqlite_sidecar(name: str) -> bool:
    return name.endswith(SQLITE_SIDECAR_SUFFIXES)


def is_secret_path(rel_posix: str) -> bool:
    """Secret classification for a home-relative POSIX path."""
    parts = rel_posix.split("/")
    if parts and parts[-1] in SECRET_BASENAMES:
        return True
    return any(part in SECRET_DIR_NAMES for part in parts[:-1])


def is_device_bound(rel_posix: str) -> bool:
    return any(sub in rel_posix for sub in DEVICE_BOUND_SUBPATHS)


def is_secret_env_name(var_name: str) -> bool:
    upper = var_name.upper()
    return any(marker in upper for marker in SECRET_ENV_MARKERS)


def iter_env_var_names(env_text: str) -> List[str]:
    """Names assigned in a dotenv-style file (comment- and export-tolerant)."""
    names: List[str] = []
    for raw in env_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        if "=" not in line:
            continue
        name = line.split("=", 1)[0].strip()
        if name and all(c.isalnum() or c == "_" for c in name):
            names.append(name)
    return names


def should_prune_dir(rel_parts: Tuple[str, ...]) -> bool:
    """Directory-walk pruning: vendored roots at depth 1, regeneratable names anywhere.

    ``rel_parts`` is the home-relative path split into parts, ending with the directory
    name under consideration. The root-level-only ``hermes-agent`` rule lives here.
    """
    name = rel_parts[-1]
    if len(rel_parts) == 1:
        if name in VENDORED_ROOT_DIRS:
            return True
    elif name == "hermes-agent":
        # Nested hermes-agent dirs are real data (e.g. a skill vendoring examples).
        return False
    if name in REGENERATABLE_DIR_NAMES:
        # checkpoints/ prunes only at root (a skill may legitimately have one).
        if name in ("checkpoints", "backups") and len(rel_parts) > 1:
            return False
        return True
    rel_posix = "/".join(rel_parts)
    if rel_posix.startswith("skills/") or "/skills/" in rel_posix:
        for drop in SKILLS_DROP_SUBPATHS:
            if rel_posix.endswith(drop):
                return True
    return False
