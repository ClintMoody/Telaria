"""Canonical secret knowledge (ARCHITECTURE §2.3; R-SEC-02).

Seeded from Hermes' own lists — `agent/file_safety.py`, `gateway/platforms/base.py`
`_ROOT_CREDENTIAL_FILES/_DIRS`, `hermes_cli/backup.py` `_SECRET_FILE_NAMES` — plus the inline
config credential keys (D29) and content patterns for unrecognized-file gating (R-SCAN-10).
The never-registry (D16/SEC-15.1) guards both `_external/` restores and Deep-Scan candidates.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, List, Optional, Tuple

#: Basenames whose content is credential material wherever they appear.
CREDENTIAL_BASENAMES = frozenset({
    ".env", ".op.env", "auth.json", ".anthropic_oauth.json", "nous_auth.json",
    "google_token.json", "google_client_secret.json", "google_oauth_pending.json",
    "google_oauth.json", "slack_tokens.json", "webhook_subscriptions.json",
    "creds.json", "honcho.json", "mem0.json", ".git-credentials",
})

#: Directory names that hold credential material entirely (any depth).
CREDENTIAL_DIR_NAMES = frozenset({"mcp-tokens", "pairing", "credentials"})

#: Home-relative prefixes that are credential stores.
CREDENTIAL_PREFIXES = ("mcp-tokens/", "pairing/", "platforms/pairing/", "credentials/",
                       "shared/nous_auth", "hindsight/config.json", "byterover/")

#: config.yaml key paths whose VALUES are credentials (D29: omit + checklist).
CONFIG_CREDENTIAL_KEYS = (
    "model.api_key",
    "providers.*.api_key",
    "openrouter.api_key",
    "dashboard.basic_auth.password",
    "dashboard.basic_auth.username",
    "monitoring.drain_secret",
    "*.client_secret",
    "*.extra_headers.Authorization",
)

#: Env var name markers that classify a variable as secret.
SECRET_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "PASS", "CREDENTIAL", "AUTH",
                      "PRIVATE")

#: Env var names that look secret by marker but are publicly-shaped settings.
ENV_MARKER_EXCEPTIONS = frozenset({
    "HERMES_AUTH_MODE",
})

#: Content patterns for the unrecognized-file secret gate (R-SCAN-10).
CONTENT_PATTERNS: Tuple[Tuple[str, re.Pattern], ...] = (
    ("pem-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-akia", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("openai-sk", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b")),
    ("slack-xox", re.compile(r"\bxox[bps]-[A-Za-z0-9-]{10,}\b")),
    ("github-pat", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{5,}\b")),
    ("telegram-bot", re.compile(r"\b\d{8,10}:[A-Za-z0-9_-]{30,}\b")),
)

_HIGH_ENTROPY_ASSIGN = re.compile(
    r"^[A-Z][A-Z0-9_]*(KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*\s*=\s*(\S{16,})\s*$", re.M)

#: Never-registry: paths Talaria refuses to place or offer, even with consent (D16, SEC-15.1).
NEVER_REGISTRY_PREFIXES = (
    "~/.ssh", "~/.gnupg", "~/.aws", "~/.kube", "~/.docker/config.json",
    "~/.config/autostart", "~/.bashrc", "~/.bash_profile", "~/.zshrc", "~/.profile",
    "~/.claude", "~/.codex", "~/.qwen", "~/.config/gh",
)

#: External-restore allowlist: the three memory-provider dirs (D16).
EXTERNAL_ALLOWLIST = ("~/.honcho", "~/.hindsight", "~/.openviking/ovcli.conf")


def is_credential_path(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    if parts and parts[-1] in CREDENTIAL_BASENAMES:
        return True
    if any(part in CREDENTIAL_DIR_NAMES for part in parts[:-1]):
        return True
    return any(rel_posix.startswith(p) for p in CREDENTIAL_PREFIXES)


def is_secret_env_name(name: str) -> bool:
    if name in ENV_MARKER_EXCEPTIONS:
        return False
    upper = name.upper()
    return any(marker in upper for marker in SECRET_ENV_MARKERS)


def is_credential_variant_name(name: str) -> bool:
    """`.env.bak`, `auth.json.old`, `.env~`… — sibling variants of credential names (SEC-03)."""
    for suffix in (".bak", ".old", ".orig", "~", ".swp", ".save", ".backup"):
        if name.endswith(suffix):
            stripped = name[: -len(suffix)]
            if stripped in CREDENTIAL_BASENAMES or stripped.rstrip(".") in CREDENTIAL_BASENAMES:
                return True
    return False


def scan_text_for_secrets(text: str) -> List[str]:
    """Which secret content patterns match ``text`` (names only, values never returned)."""
    hits = [name for name, pattern in CONTENT_PATTERNS if pattern.search(text)]
    for m in _HIGH_ENTROPY_ASSIGN.finditer(text):
        if _entropy(m.group(2)) >= 3.5:
            hits.append("high-entropy-assignment")
            break
    return hits


def mask_secret_values(text: str) -> str:
    """Mask any secret-shaped values inside ``text`` (report belt pass, R-SEC-10)."""
    out = text
    for name, pattern in CONTENT_PATTERNS:
        if name == "pem-key":
            continue  # multi-line; handled by never embedding key files at all
        out = pattern.sub("•••", out)
    out = re.sub(r"([?&](?:token|key|secret|password|auth)=)[^&\s\"']+", r"\1•••", out,
                 flags=re.I)
    # High-entropy KEY=/TOKEN=/SECRET=/PASSWORD= assignments — the same shape
    # scan_text_for_secrets flags. Masking the patterns above misses a bare
    # `MY_KEY=8f3a9c2b1d...`, which would otherwise survive into a report verbatim.
    def _mask_assign(m):
        whole, value = m.group(0), m.group(2)
        if _entropy(value) < 3.5:
            return whole
        cut = m.start(2) - m.start(0)
        return whole[:cut] + "•••"

    out = _HIGH_ENTROPY_ASSIGN.sub(_mask_assign, out)
    return out


def is_never_path(path: str, home: str) -> Optional[str]:
    """Why ``path`` is refused by the never-registry (None = allowed).

    ``path`` may be absolute or ~-relative; ``home`` is the user's home directory.
    The path is NORMALIZED before every check so ``~/../.ssh`` or ``~/foo/../../.ssh``
    cannot slip past the home-prefix and protected-prefix gates by walking up with
    ``..`` (the naive ``~``→home substitution left that hole open).
    """
    import os as _os

    if path.startswith("~"):
        expanded = home.rstrip("/\\") + path[1:]
    else:
        expanded = path
    norm = _os.path.normpath(expanded).replace("\\", "/")
    home_norm = _os.path.normpath(home).replace("\\", "/").rstrip("/")
    if norm != home_norm and not norm.startswith(home_norm + "/"):
        return "outside the home directory"
    rel = "~" + norm[len(home_norm):]
    for prefix in NEVER_REGISTRY_PREFIXES:
        if rel == prefix or rel.startswith(prefix + "/"):
            return f"protected path ({prefix})"
    return None


def _entropy(s: str) -> float:
    if not s:
        return 0.0
    counts = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())
