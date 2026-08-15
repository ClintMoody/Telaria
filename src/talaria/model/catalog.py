"""The artifact-kind catalog, exclusion registry, and coupling rules (ARCHITECTURE §2.2–2.4).

Everything the scanner needs to answer "what IS this path": ordered classification rules over
home-relative POSIX paths, the machine-bound EXCLUSION_REGISTRY enforced on BOTH capture and
apply (backup NS-508 lesson), and the hard/soft coupling rules the selection engine runs at
pack AND apply narrowing (D10).

Citations in rule ``reason`` fields point at docs/research/*; `talaria why` renders them.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from talaria.model.secrets_registry import (
    is_credential_path,
    is_credential_variant_name,
)

# --------------------------------------------------------------------------- exclusions

@dataclass(frozen=True)
class Exclusion:
    id: str
    globs: Tuple[str, ...]        # home-relative POSIX globs (fnmatch)
    scope: str                    # capture|apply|both
    reason: str
    citation: str


#: The machine-bound / regeneratable registry — one list, both sides (R-PACK-06, R-APPLY-06).
EXCLUSION_REGISTRY: Tuple[Exclusion, ...] = (
    Exclusion("gateway-runtime",
              ("gateway_state.json", "gateway.pid", "gateway.lock", "processes.json",
               ".clean_shutdown", ".restart_*", "gateway/dead_targets.json",
               "gateway/restart_loop.json", "gateway-starts.log", "pending_messages/**",
               "runtime/**", ".gateway-launchd-unsupported"),
              "both", "process/runtime state namespaced to the old machine; restoring "
              "gateway_state.json broke hosted gateways", "state §2.7; backup NS-508"),
    Exclusion("pids-locks",
              ("cron.pid", "auth.lock", ".backup.lock", "install.lock",
               "cron/.tick.lock", "cron/.jobs.lock", ".mcp-discovery.lock",
               "skills/.usage.json.lock", "kanban/.dispatcher.lock", "proxy/**"),
              "both", "locks, pids and proxy security material are machine-local",
              "state §2.2, §7"),
    Exclusion("sqlite-sidecars",
              ("**/*.db-wal", "**/*.db-shm", "**/*.db-journal", "*.db-wal", "*.db-shm",
               "*.db-journal"),
              "both", "a fresh snapshot plus stale sidecars is a torn restore",
              "backup.py sidecar rule; state §2.3"),
    Exclusion("cron-liveness",
              ("cron/ticker_heartbeat", "cron/ticker_last_success", "cron/usage_audit.jsonl",
               "cron/inflight_forced_releases.jsonl", "cron/.jobs_*.tmp", "cron/.hb_*",
               "cron/.output_*", "cron/catch_up_*", "cron/ticker_error*"),
              "both", "scheduler liveness/diagnostics; heartbeat absence is the "
              "proof-of-life signal after migration", "cron §1.2"),
    Exclusion("vendored-runtimes",
              ("hermes-agent/**", "bin/**", "node/**", "git/**", "lib/**", "lsp/**",
               "gateway-service/**", "packages/**", "agent-browser/**", "lazy-packages/**",
               ".worktrees/**", "photon/**"),
              "capture", "code and native binaries are re-provisioned per machine, never "
              "copied (arch-specific; the checkout is recorded as ref+patch instead)",
              "state §2.9; install §12"),
    Exclusion("logs-caches",
              ("logs/**", "cache/**", "image_cache/**", "audio_cache/**", "document_cache/**",
               "video_cache/**", "images/**", "browser_screenshots/**",
               "browser_recordings/**", "chrome-debug/**", "sandboxes/**", "pastes/**",
               "disk-cleanup/**", "tmp/**", ".hermes_history", "telemetry/**"),
              "capture", "regeneratable logs and caches (the 426k-file backup incident "
              "lived here)", "state §2.8; backup precedent"),
    Exclusion("snapshots-backups",
              ("backups/**", "state-snapshots/**", "checkpoints/**", ".talaria/**"),
              "both", "prior backups, path-hashed checkpoints, and Talaria's own txn area "
              "never nest into a bundle", "state §2.4; C2-25"),
    Exclusion("skills-caches",
              ("skills/.hub/index-cache/**", "skills/.hub/quarantine/**",
               "skills/.curator_backups/**", "skills/.restore-backups/**", "skills/**/*.bak",
               "skills/.skills_prompt_snapshot.json", "skills/index-cache/**"),
              "capture", "regeneratable skill-hub caches and transient update backups",
              "skills §8 drop list"),
    Exclusion("machine-markers",
              (".update_check", ".update_pending*", ".container-mode", ".managed",
               ".install_method", ".hermes_build_sha", ".termux_bundled_sync_stamp",
               "skills/.sync_device_id", "web-ui-build-stamp.json",
               "desktop-build-stamp.json", ".hermes-update-in-progress"),
              "both", "host-shape markers; wrong values on a new machine mislead Hermes",
              "state §5, §10.12"),
    Exclusion("device-linked",
              ("whatsapp/session/**", "platforms/whatsapp/session/**", "signal-cli/**",
               "matrix-store/**", "platforms/matrix/store/**", "weixin/**",
               "wechat-session/**"),
              "both", "device-registered sessions fight for the account's device slot when "
              "copied; re-pair on the new machine instead (about a minute)",
              "integ §1.2; D23"),
    Exclusion("bridge-node-modules",
              ("scripts/whatsapp-bridge/node_modules/**",),
              "capture", "npm dependency tree; `npm install` regenerates it on the target",
              "integ §1.2"),
    Exclusion("mcp-installs",
              ("mcp-installs/**",),
              "capture", "MCP server venvs/node trees; reinstalled from config on target",
              "integ §2.3"),
    Exclusion("cred-caches",
              ("cache/bws_cache*",),
              "both", "external secret-source caches are re-fetched at runtime",
              "state §2.2"),
    Exclusion("pycache",
              ("**/__pycache__/**", "**/*.pyc", "**/.venv/**", "**/venv/**",
               "**/node_modules/**", "**/site-packages/**", "**/.git/**"),
              "capture", "regeneratable dependency/bytecode trees inside carried dirs",
              "backup precedent excluded dirs"),
    Exclusion("config-debris",
              ("config.yaml.corrupt.*.bak",),
              "capture", "corruption debris upstream leaves behind", "state §2.1"),
)


def exclusion_for(rel_posix: str, scope: str) -> Optional[Exclusion]:
    """First exclusion whose glob matches ``rel_posix`` in ``scope`` (or 'both')."""
    for exc in EXCLUSION_REGISTRY:
        if exc.scope != "both" and exc.scope != scope:
            continue
        for pattern in exc.globs:
            if _match(rel_posix, pattern):
                return exc
    return None


def _match(rel: str, pattern: str) -> bool:
    if pattern.endswith("/**"):
        prefix = pattern[:-3]
        if "*" not in prefix:
            return rel == prefix or rel.startswith(prefix + "/")
        return fnmatch.fnmatch(rel, prefix) or fnmatch.fnmatch(rel, pattern.replace("/**", "/*")) \
            or any(fnmatch.fnmatch(part_join, prefix)
                   for part_join in _ancestors(rel))
    if "**" in pattern:
        # fnmatch has no true globstar; translate `**/x` to a segment-anywhere match.
        return re.fullmatch(_globstar_to_re(pattern), rel) is not None
    return fnmatch.fnmatch(rel, pattern)


def _ancestors(rel: str) -> List[str]:
    parts = rel.split("/")
    return ["/".join(parts[:i]) for i in range(1, len(parts))]


def _globstar_to_re(pattern: str) -> str:
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if pattern[i:i + 3] == "**/":
            out.append(r"(?:[^/]+/)*")
            i += 3
        elif pattern[i:i + 2] == "**":
            out.append(r".*")
            i += 2
        elif ch == "*":
            out.append(r"[^/]*")
            i += 1
        elif ch == "?":
            out.append(r"[^/]")
            i += 1
        else:
            out.append(re.escape(ch))
            i += 1
    return "".join(out)


# --------------------------------------------------------------------------- prune

#: Root-level directories never descended during the walk (capture side).
PRUNE_ROOT_DIRS = frozenset({
    "hermes-agent", "bin", "node", "git", "lib", "lsp", "gateway-service", "packages",
    "agent-browser", "lazy-packages", ".worktrees", "logs", "cache", "image_cache",
    "audio_cache", "document_cache", "video_cache", "images", "browser_screenshots",
    "browser_recordings", "chrome-debug", "sandboxes", "pastes", "disk-cleanup", "tmp",
    "state-snapshots", "mcp-installs", "runtime", "pending_messages", "moa-traces",
    "spawn-trees", "proxy", "telemetry", "backups", "checkpoints", ".talaria", "photon",
})

#: Directory names pruned at any depth (regeneratable dependency/cache trees).
PRUNE_ANY_DIRS = frozenset({
    "__pycache__", ".git", "node_modules", ".venv", "venv", "site-packages",
    ".cache", ".tox", ".nox", ".pytest_cache", ".mypy_cache", ".ruff_cache",
})

#: skills/-scoped prune suffixes.
PRUNE_SKILLS_SUBPATHS = (".hub/index-cache", ".hub/quarantine", ".curator_backups",
                         ".restore-backups", "index-cache")


def should_prune(rel_parts: Sequence[str]) -> bool:
    """Prune decision for a directory during descent (R-SCAN-05).

    ``rel_parts`` is the home-relative path of the directory, split. The root-level-only
    `hermes-agent` rule lives here: nested ones are data (state §10.2).
    """
    name = rel_parts[-1]
    depth = len(rel_parts)
    profile_local = list(rel_parts)
    if depth >= 3 and rel_parts[0] == "profiles":
        profile_local = list(rel_parts[2:])
        depth = len(profile_local)
        if depth == 0:
            return False
        name = profile_local[-1]
    if depth == 1:
        return name in PRUNE_ROOT_DIRS
    if name in PRUNE_ANY_DIRS:
        return True
    rel_posix = "/".join(profile_local)
    if rel_posix.startswith("skills/"):
        for sub in PRUNE_SKILLS_SUBPATHS:
            if rel_posix == f"skills/{sub}" or rel_posix.endswith("/" + sub):
                return True
    if name == "node_modules":
        return True
    return False


# --------------------------------------------------------------------------- catalog rules

@dataclass(frozen=True)
class KindRule:
    kind: str
    family: str
    patterns: Tuple[str, ...]       # home-relative POSIX globs; first match wins
    portability: str = "a"          # a|b|c
    secrecy: str = "none"           # none|credential|content
    default: str = "on"             # on|off|record_only|never
    machine_bound: bool = False
    root_only: bool = False         # ROOT-profile singleton (kanban.db, shared/)
    reason: str = ""
    group_dir: Optional[int] = None  # group files into one artifact per N leading segments


#: Ordered rules, specific → general (ARCHITECTURE §2.2 table transcribed).
KIND_RULES: Tuple[KindRule, ...] = (
    # 3 credentials (before general config/json rules)
    KindRule("env-file", "credentials", (".env", ".op.env"), "a", "credential",
             "on", reason="~40 secret vars live here; never partial-copied (R-SEC-08)"),
    KindRule("auth-stores", "credentials",
             ("auth.json", ".anthropic_oauth.json", "shared/nous_auth.json"),
             "a", "credential", "on", root_only=False,
             reason="OAuth/device-code pools (state §2.2)"),
    KindRule("mcp-tokens", "credentials", ("mcp-tokens/**",), "b", "credential", "on",
             group_dir=1, reason="MCP OAuth tokens; client.json embeds a loopback port"),
    KindRule("platform-tokens", "credentials",
             ("google_token.json", "google_client_secret.json", "google_oauth_pending.json",
              "auth/google_oauth.json", "google_chat_user_*", "slack_tokens.json",
              "webhook_subscriptions.json", "credentials/**"),
             "a", "credential", "on", reason="platform OAuth/webhook secrets (state §2.2)"),
    KindRule("memory-provider-keys", "credentials",
             ("honcho.json", "mem0.json", "hindsight/config.json", "byterover/**"),
             "a", "credential", "on", reason="memory-provider API keys (state §2.2)"),

    # 9 platforms-messaging (pairing before generic; device-linked handled by exclusions)
    KindRule("pairing-stores", "platforms-messaging",
             ("pairing/**", "platforms/pairing/**"), "a", "content", "on",
             reason="user grants and pairing codes; dual-layout merged on read (integ §0)"),
    KindRule("channel-routing", "platforms-messaging",
             ("channel_directory.json", "channel_aliases.json", "sticker_cache.json",
              "*_threads.json", "feishu_*.json"),
             "a", "none", "on", reason="user routing tables (state §2.7)"),
    KindRule("platform-state", "platforms-messaging", ("platforms/**",),
             "a", "content", "on", reason="per-platform state (judged individually upstream)"),

    # 1 identity-memory
    KindRule("soul-md", "identity-memory", ("SOUL.md",), "a", "none", "on",
             reason="the agent's persona; diffed against the shipped default (install §8)"),
    KindRule("memories-dir", "identity-memory", ("memories/**",), "a", "content", "on",
             reason="agent-curated memories (§-split entries)"),
    KindRule("root-md-set", "identity-memory",
             ("MEMORY.md", "USER.md", "todo.json", "system_prompt.md", "AGENTS.md",
              "CLAUDE.md", ".cursorrules", "desktop.json"),
             "a", "none", "on", reason="upstream's portable root set (state §2.1)"),
    KindRule("skins-themes", "identity-memory", ("skins/**", "dashboard-themes/**"),
             "a", "none", "on", reason="user theming"),

    # 2 configuration
    KindRule("config-yaml", "configuration", ("config.yaml",), "b", "none", "on",
             reason="machine-specific keys rewritten; inline credential keys omitted (D29)"),
    KindRule("active-profile", "configuration", ("active_profile",), "a", "none", "on",
             root_only=True, reason="sticky profile selector; re-verified on target"),
    KindRule("mcp-json", "configuration", ("mcp.json",), "b", "none", "on",
             reason="per-profile MCP config; entries re-validated before write (D19)"),
    KindRule("skill-bundles", "configuration", ("skill-bundles/**",), "a", "none", "on",
             reason="slash-command bundles; bundles win over same-named skills"),
    KindRule("hooks-dir", "configuration", ("hooks/**",), "a", "none", "on",
             reason="user hooks — executable content disclosed at preflight (SEC-09)"),
    KindRule("no-bundled-skills", "configuration", (".no-bundled-skills",), "a", "none",
             "on", reason="opt-out marker for bundled skill seeding"),

    # 4 skills
    KindRule("skills-metadata", "skills",
             ("skills/.bundled_manifest", "skills/.usage.json", "skills/.curator_suppressed",
              "skills/.archive/**"),
             "a", "none", "on",
             reason="stock baseline + provenance + curator state; losing .usage.json freezes "
                    "curation; .curator_suppressed without .archive resurrects pruned skills"),
    KindRule("hub-metadata", "skills",
             ("skills/.hub/lock.json", "skills/.hub/taps.json", "skills/.hub/audit.log",
              "skills/.hub/.ignore"),
             "a", "none", "on", reason="hub install provenance (backfill orphans otherwise)"),
    KindRule("org-sync", "skills", ("skills/_org/**", "skills/.sync_state"),
             "a", "none", "on", reason="org-skill baselines and sync state"),
    KindRule("skill-dir", "skills", ("skills/**",), "a", "none", "on", group_dir=3,
             reason="a skill = the directory holding SKILL.md; provenance per skill"),

    # 5 plugins
    KindRule("plugin-dir", "plugins", ("plugins/**",), "a", "none", "on", group_dir=2,
             reason="user plugins (cron providers live here); venvs stripped → reinstall"),
    KindRule("plugin-data", "plugins", ("plugin-data/**",), "a", "none", "on", group_dir=2,
             reason="plugin state.json under sha-derived namespaces"),

    # 6 automations
    KindRule("cron-jobs", "automations", ("cron/jobs.json",), "b", "none", "on",
             reason="the job store; runtime claims scrubbed, bookkeeping kept (cron §1.3)"),
    KindRule("cron-notepad", "automations", ("cron/notepad.db",), "a", "none", "on",
             reason="per-job durable KV; stateful jobs restart without it"),
    KindRule("cron-suggestions", "automations", ("cron/suggestions.json",), "a", "none",
             "on", reason="holds dismissal latches"),
    KindRule("cron-output", "automations", ("cron/output/**",), "a", "content", "on",
             group_dir=3, reason="context_from inputs + monitor baselines"),
    KindRule("cron-executions", "automations", ("cron/executions.db",), "a", "none", "off",
             reason="audit ledger; non-terminal rows dropped on restore"),
    KindRule("scripts-dir", "automations", ("scripts/**",), "b", "none", "on",
             reason="cron job scripts; hard-contained to $HH/scripts upstream"),

    # 7 conversations-history
    KindRule("state-db", "conversations-history", ("state.db",), "a", "content", "on",
             reason="THE session store; snapshot-captured; cwd columns are machine paths"),
    KindRule("aux-dbs", "conversations-history",
             ("response_store.db", "memory_store.db", "verification_evidence.db",
              "retaindb_queue.db", "gateway/discord_message_recovery.db"),
             "a", "content", "on", reason="gateway/memory/verification stores"),
    KindRule("sessions-legacy", "conversations-history",
             ("sessions/**", "session-exports/**"),
             "a", "content", "on", reason="legacy JSONL sessions and saved exports"),
    KindRule("forensic", "conversations-history", ("moa-traces/**", "spawn-trees/**"),
             "a", "content", "off", reason="debug traces; off by default"),

    # 8 boards-projects
    KindRule("kanban", "boards-projects", ("kanban.db", "kanban/**"), "b", "none", "on",
             root_only=True, reason="ROOT-level kanban store + boards (state §10.9)"),
    KindRule("projects-db", "boards-projects", ("projects.db",), "b", "none", "on",
             reason="projects registry with path fields"),

    # 13 dashboard/observability leftovers that are plain files
    KindRule("dashboard-auth-log", "dashboard-observability", ("dashboard-auth.log",),
             "c", "none", "never", machine_bound=True, reason="auth log; regenerates"),

    # 17 desktop-app
    KindRule("desktop-machine", "desktop-app",
             ("desktop-installation.json", "window-state.json"),
             "c", "none", "never", machine_bound=True,
             reason="desktop install identity; regenerated per machine"),

    # catch remaining known-noise
    KindRule("context-cache", "configuration", ("context_length_cache.yaml",), "c", "none",
             "never", machine_bound=True, reason="regeneratable model-context cache"),
)

UNRECOGNIZED_KIND = "unrecognized"


@dataclass
class Classification:
    kind: str
    family: str
    portability: str
    secrecy: str
    default: str
    machine_bound: bool
    reason: str
    group_key: str            # artifact grouping discriminator ("" = kind-level artifact)
    excluded: Optional[Exclusion] = None


def classify(rel_posix: str, profile: str = "") -> Classification:
    """Classify one home-relative POSIX path (R-SCAN-04). Exclusions win over rules."""
    exc = exclusion_for(rel_posix, "capture")
    if exc is not None:
        return Classification(
            kind=f"excluded:{exc.id}", family="runtime-ephemera", portability="c",
            secrecy="credential" if is_credential_path(rel_posix) else "none",
            default="never", machine_bound=True, reason=exc.reason, group_key=exc.id,
            excluded=exc)
    for rule in KIND_RULES:
        for pattern in rule.patterns:
            if _match(rel_posix, pattern):
                group_key = ""
                if rule.group_dir:
                    parts = rel_posix.split("/")
                    group_key = "/".join(parts[: rule.group_dir])
                secrecy = rule.secrecy
                if secrecy == "none" and is_credential_path(rel_posix):
                    secrecy = "credential"
                return Classification(rule.kind, rule.family, rule.portability, secrecy,
                                      rule.default, rule.machine_bound, rule.reason,
                                      group_key)
    name = rel_posix.rsplit("/", 1)[-1]
    secrecy = "credential" if (is_credential_path(rel_posix)
                               or is_credential_variant_name(name)) else "none"
    return Classification(UNRECOGNIZED_KIND, "unrecognized", "a", secrecy,
                          "record_only" if secrecy == "credential" else "on",
                          False, "not matched by the catalog — gated per D9", "")


# --------------------------------------------------------------------------- couples

@dataclass(frozen=True)
class CoupleRule:
    id: str
    hard: bool
    description: str


COUPLE_RULES: Dict[str, CoupleRule] = {r.id: r for r in (
    CoupleRule("skill-metadata", True,
               "any skill travels only with skills/.bundled_manifest and skills/.usage.json"),
    CoupleRule("curator-pair", True,
               "skills/.curator_suppressed and skills/.archive must travel together"),
    CoupleRule("job-script", True, "a cron job with a script needs scripts/<script>"),
    CoupleRule("job-context", True,
               "a job with context_from needs the referenced jobs and their output dirs"),
    CoupleRule("job-monitor", True,
               "a monitor job needs output/<id>/monitor_last_output.txt or it re-alerts"),
    CoupleRule("cron-provider-plugin", True,
               "cron.provider != builtin needs plugins/<provider> or it silently degrades"),
    CoupleRule("job-skill", False, "a job naming a skill wants that skill present"),
    CoupleRule("hub-lock", True, "a hub-installed skill travels with skills/.hub/lock.json"),
    CoupleRule("mcp-env", False, "an MCP ${VAR} reference wants that var on the checklist"),
    CoupleRule("skill-env", False, "a skill's required env vars go on the checklist"),
    CoupleRule("memory-provider", True,
               "memory.provider needs its external dir and provider config"),
)}
