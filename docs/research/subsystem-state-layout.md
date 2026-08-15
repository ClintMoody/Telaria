# Subsystem Report: On-Disk Persistent State — Definitive Map

Source: NousResearch/hermes-agent @ 0.20.1. All code citations repo-relative.

## 1. The State Root: HERMES_HOME

### 1.1 Canonical resolver — `hermes_constants.py` (hard rule in AGENTS.md:1247-1258: "NEVER hardcode ~/.hermes")

`hermes_constants.py:53-59`:

```python
def _get_platform_default_hermes_home() -> Path:
    if sys.platform == "win32":
        local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local_appdata) if local_appdata else Path.home() / "AppData" / "Local"
        return base / "hermes"
    return Path.home() / ".hermes"
```

| Platform | Default HERMES_HOME |
|---|---|
| Linux | `~/.hermes` |
| macOS | `~/.hermes` (deliberately NOT ~/Library/Application Support) |
| Windows | `%LOCALAPPDATA%\hermes` (fallback `~\AppData\Local\hermes`) |
| Termux | `/data/data/com.termux/files/home/.hermes` |
| Docker | `/opt/data` (Dockerfile:378, VOLUME :422) |
| NixOS | `${stateDir}/.hermes`, default `/var/lib/hermes/.hermes` (nix/nixosModules.nix:251-252,665) |

**NO appdirs/platformdirs/XDG for agent state.** XDG only used by the Electron desktop and .desktop entries.

### 1.2 Resolution precedence (`hermes_constants.py:114-139`)

1. context-local override (`set_hermes_home_override()`, ContextVar :17-19,30-50)
2. `$HERMES_HOME` env (:71-74)
3. platform default (:53-59)

`get_process_hermes_home()` (:154-170) skips step 1 (dashboard themes/plugin manifests). Unset
HERMES_HOME + non-default `active_profile` triggers a one-shot stderr warning (:77-111).

### 1.3 Profiles — `get_default_hermes_root()` (:173-210)

- Classic: home=~/.hermes → root=~/.hermes; Profile: home=<root>/profiles/<name> → root=<root>
  (detected via `env_path.parent.name == "profiles"` :206). Sticky file: `<root>/active_profile`
  (`hermes_cli/profiles.py:296-298`). Profile aliases = wrapper scripts `~/.local/bin/<profile>`
  (:301-303) — machine-specific, regenerated on import (`hermes_cli/backup.py:1016-1055`).

### 1.4 Path-overriding env vars

`HERMES_HOME`, `HERMES_HOME_MODE` (dir mode, default 0700), `HERMES_MANAGED`/`.managed`,
`HERMES_MANAGED_DIR` (default /etc/hermes), `HERMES_OPTIONAL_SKILLS`, `HERMES_OPTIONAL_MCPS`,
`HERMES_BUNDLED_SKILLS`, `HERMES_KANBAN_HOME`, `HERMES_KANBAN_DB`,
`HERMES_KANBAN_WORKSPACES_ROOT`, `HERMES_KANBAN_ATTACHMENTS_ROOT`, `HERMES_SHARED_AUTH_DIR`
(default <root>/shared/), `HERMES_WRITE_SAFE_ROOT`, `HERMES_LAZY_INSTALL_TARGET`,
`HERMES_UID`/`HERMES_GID`, `HERMES_CONTAINER`/`HERMES_SKIP_CHMOD`, `HERMES_GIT_BASH_PATH`,
`HERMES_GATEWAY_LOCK_DIR`, `HERMES_RPC_DIR`, `HERMES_TUI_DIR`, `HERMES_BUNDLES_DIR`,
`HERMES_PREFILL_MESSAGES_FILE`, `HERMES_DESKTOP_READY_FILE`, `HERMES_MEET_OUT_DIR`,
`HERMES_PYTHON_SRC_ROOT`, `HERMES_REAL_HOME`, `HERMES_PROFILE`/`HERMES_PROFILE_NAME`, `LOCALAPPDATA`.

## 2. Contents of $HERMES_HOME — Full Inventory

Skeleton created on every load_config (`hermes_cli/config.py:869-916`): `cron, sessions, logs,
logs/curator, memories, pairing, hooks, image_cache, audio_cache, skills` + SOUL.md seeded
(:841-860). Managed variant only verifies (:919-938). Dirs 0700, secret files 0600 (:824-839) —
both skipped in containers/managed.

### 2.1 Config & identity

| Path | Format | Secrets? | Portable? |
|---|---|---|---|
| `config.yaml` | YAML | possibly (`model.api_key`, `providers.<n>.api_key`) | mostly; contains `terminal.cwd`, `mcp_servers[].command/args` abs paths |
| `config.yaml.corrupt.<ts>.bak` | YAML | same | debris — skip |
| `SOUL.md` | MD | no | **must migrate** |
| `MEMORY.md`, `USER.md`, `todo.json`, `system_prompt.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `desktop.json` | text | no | portable root-level set (`hermes_cli/profiles.py:240-251`) |
| `memories/MEMORY.md`, `memories/USER.md` | MD (§-split entries; `agent/learning_mutations.py:30-33`) | no | **must migrate** |
| `active_profile` | text | no | portable; re-verify profiles |
| `skins/*.yaml`, `dashboard-themes/` | YAML | no | portable |
| `context_length_cache.yaml` | YAML | no | regeneratable |

### 2.2 Credentials & secrets (ALL sensitive)

| Path | Contents | Code |
|---|---|---|
| `.env` | all provider keys (~114 documented) | `hermes_cli/config.py:700-702`; loader `hermes_cli/env_loader.py:485-497` |
| `.op.env` | 1Password bootstrap token | env_loader.py:512-514 |
| `auth.json` (0600) | OAuth/device-code credential pool, active_provider | `hermes_cli/auth.py:1038-1058`; atomic O_EXCL 0600 :1326-1345 |
| `auth.lock` | lock | :1127-1128 |
| `.anthropic_oauth.json` | PKCE tokens | `agent/anthropic_adapter.py:1515` |
| `shared/nous_auth.json` (ROOT-level) | shared Nous OAuth across profiles | `hermes_cli/auth.py:5299-5330` |
| `mcp-tokens/<server>.json`, `.client.json` | MCP OAuth bearer + client creds | `tools/mcp_oauth.py:184-193` |
| `webhook_subscriptions.json` (0600) | per-route HMAC secrets | `hermes_cli/webhook.py:26-70` |
| `google_token.json`, `google_client_secret.json`, `google_oauth_pending.json`, `auth/google_oauth.json` | Google OAuth | `gateway/platforms/base.py:1390-1394` |
| `google_chat_user_*` | Google Chat OAuth | plugins/platforms/google_chat/oauth.py |
| `slack_tokens.json` | Slack tokens | grep |
| `whatsapp/session/creds.json` | **Baileys device session — device-bound** | `hermes_cli/gateway.py:5685` |
| `pairing/`, `platforms/pairing/` | user grants, hashed codes | `gateway/pairing.py:18,59` |
| `cache/bws_cache{.json,.enc.json}` (0600/0700) | Bitwarden cache | `agent/secret_sources/bitwarden.py:95-101` |
| `credentials/` | platform allowlists | grep |
| `honcho.json`, `mem0.json`, `hindsight/config.json`, `byterover/` | memory-provider keys | plugins/memory/* |
| `proxy/` (key, pidfile, nonce, audit; 0600) | Iron proxy | `agent/proxy_sources/iron_proxy.py:362,781-869,1322-1348,2019-2072` |

**Canonical secret lists for the scanner:** `agent/file_safety.py:28-71` (write-deny), `:327-338`
(read-block), `:354-375` (mcp-tokens prefix); `gateway/platforms/base.py:1379-1410`
(`_ROOT_CREDENTIAL_FILES`/`_DIRS`); `hermes_cli/backup.py:132` (`_SECRET_FILE_NAMES`).

**Keyring: NONE.** All secrets are plaintext files (`agent/secret_sources/__init__.py:29-31` —
OS keystores "under discussion").

**External credential files Hermes READS (foreign-owned, don't migrate):**
`~/.claude/.credentials.json` / `~/.claude.json`, `~/.codex/auth.json`, `~/.qwen/oauth_creds.json`,
`gh` CLI (`agent/credential_sources.py:203-436`). Persist-allowed sources into auth.json only:
(anthropic,hermes_pkce), (minimax-oauth,oauth), (nous,device_code), (openai-codex,device_code),
(xai-oauth,device_code) (`agent/credential_persistence.py:19-25`); everything else "borrowed" and
stripped at disk boundary (:99-109).

**Memory-provider external paths** via `MemoryProvider.backup_paths()`: `~/.honcho/`
(honcho/__init__.py:265-276), `~/.hindsight/` (hindsight/__init__.py:732-740),
`~/.openviking/ovcli.conf` (openviking/__init__.py:2193-2204). Official backup stages under
`_external/` home-relative (`hermes_cli/backup.py:134-139,221-294`); non-$HOME paths skipped (:656-673).

### 2.3 Databases (SQLite)

| Path | Purpose | Code |
|---|---|---|
| `state.db` (+wal/shm) | THE session store: sessions, messages, FTS, routing | `hermes_state.py:348, 378-395` |
| `kanban.db` (ROOT-level) | default kanban board | `hermes_cli/kanban_db.py:713-735` |
| `kanban/boards/<slug>/kanban.db` + `board.json` | other boards | :597,700-735 |
| `projects.db` | per-profile projects | `hermes_cli/projects_db.py:50` |
| `response_store.db` | gateway conv history/tool payloads | `gateway/platforms/api_server.py:834` |
| `memory_store.db` | holographic memory | `plugins/memory/holographic/store.py:124` |
| `verification_evidence.db` (schema v1) | verification audit | `agent/verification_evidence.py:31,60` |
| `cron/executions.db`, `cron/notepad.db` | cron | cron/executions.py:20, cron/notepad.py:34 |
| `gateway/discord_message_recovery.db` (0600) | Discord replay | plugins/platforms/discord/recovery.py:18,30-46 |
| `telemetry/shared_metrics/` (store "2") | metrics | hermes_cli/observability/shared_metrics.py:28-29,55 |
| `retaindb_queue.db` | retaindb plugin | plugins/memory/retaindb/__init__.py:544 |
| `hermes_state.db` | legacy name | exclusion lists only |

**state.db schema** (`hermes_state_common.py:249+`): schema_version, system_prompts, sessions,
messages, session_model_usage, state_meta, gateway_routing, compression_locks, async_delegations,
session_turn_leases; FTS5 messages_fts + trigram (+cjk variant); 18 indexes.
**Machine-specific columns:** sessions.cwd, git_branch, git_repo_root (absolute host paths;
`hermes_state_portability.py:41-68` enumerates cwds — dangle after migration).

**WAL portability:**
- Sidecars excluded from backup (`backup.py:78-89`) — snapshot + stale WAL = torn restore.
- Copy via `sqlite3.connect(f"file:{src}?mode=ro", uri=True)` + `conn.backup(dst)`, fail closed
  (`backup.py:342-369`).
- `verify_sqlite_integrity` (:416-552): header magic + PRAGMA integrity_check **only under 2 GiB**
  (:413; real 30GB state.db exists :411); else O(1) schema probe.
- Zeroed-DB detection (:372-396, issue #68474).
- WAL unavailable on NFS/SMB/FUSE/WSL1 → auto-fallback DELETE (`hermes_state.py:520-545`);
  config `database.journal_mode`. **Migration onto network home changes journal mode silently.**

### 2.4 Session data (non-DB)

`sessions/` (legacy JSONL + index), `sessions/sessions.json` (legacy index, still written unless
`gateway.write_sessions_json: false` — gateway/config.py:939-946,1259), `sessions/saved/`
(/save exports, cli.py:9175-9182), `session-exports/` (hermes_cli/sessions_cmd.py:546,636),
`state-snapshots/<ts>/` + manifest.json (quick snapshots, keep 20), `backups/` (excluded from
backups), `checkpoints/store/` (**machine-specific**: project key sha256(abs_path)[:16],
tools/checkpoint_manager.py:204), `moa-traces/`, `spawn-trees/`.

### 2.5 Cron

`cron/jobs.json` (0600, cron/jobs.py:85,535), `cron/output/<job>/`, executions.db, notepad.db,
usage_audit.jsonl, inflight_forced_releases.jsonl, `.tick.lock` (machine-local), `cron.pid` (excluded).

### 2.6 Skills / plugins / MCP

`skills/<cat>/<skill>/`, `skills/.archive/` (KEEP), `.usage.json` (user data), `.hub/` (cache
read-blocked, regeneratable), `.curator_state`, `.curator_backups`, `.termux_bundled_sync_stamp`
(machine marker), `.no-bundled-skills`, `.skills_prompt_snapshot.json`, `skill-bundles/`,
`plugins/<name>/` (user plugins — may contain venvs), `plugins/hermes-achievements/*.json`,
`plugin-data/<ns>/`, `mcp-installs/` (node_modules/venvs — regeneratable), `mcp.json` (per-profile
MCP config, `hermes_cli/agent_plugins.py:443`), `.mcp-discovery.lock`, `hooks/`, `scripts/`,
`scripts/whatsapp-bridge/`.

### 2.7 Gateway / platform runtime

DO NOT migrate: `gateway_state.json` (NS-508), `gateway.pid`, `cron.pid`, `gateway.lock`,
`processes.json` (`container_boot.py:75` `_STALE_RUNTIME_FILES`), `.clean_shutdown`,
`.restart_*.json`, `gateway/dead_targets.json`, `gateway/restart_loop.json`, `gateway-starts.log`,
diag logs, `.gateway-launchd-unsupported`, `.container-mode`, `pending_messages/` (shutdown
flush), `runtime/`.
Migrate: `channel_directory.json`, `channel_aliases.json` (user routing;
gateway/channel_directory.py:21), feishu pairing/rules (not seen-ids), assorted platform state
(judge individually).

### 2.8 Logs & caches (regeneratable)

`logs/*` (agent.log INFO+, errors.log WARNING+, gateway.log — hermes_logging.py:8-10,304,320-344;
curator/, dashboard-auth.log, live.pipe), `.hermes_history` (readline, cli.py:4834), `cache/*`
(15+ subdirs incl. model catalogs, probes, stamps), legacy `image_cache/ audio_cache/
document_cache/ video_cache/ images/ browser_screenshots/ browser_recordings/ chrome-debug/
sandboxes/ pastes/ disk-cleanup/ tmp/`.

**Legacy-dir trap:** `get_hermes_dir(new, old)` (`hermes_constants.py:259-294`) — non-empty
legacy wins; empty legacy ignored (issue #27602). **Creating empty legacy dirs on the target
shadows real data.**

### 2.9 Vendored runtimes (do NOT migrate)

`hermes-agent/` (checkout+venv), `.worktrees/`, `node/`, `node_modules/`, `bin/` (uv/tirith/bws),
`lib/libfts5_cjk.so` (native!), `lsp/bin/`, `git/` (Windows), `gateway-service/`, `packages/`,
`agent-browser/`, `photon/sidecar`, `lazy-packages/`. Note `iter_hermes_node_dirs()`
(`hermes_constants.py:297-314`) probes both node layout shapes on every platform to support
migrated installs.

## 3. config.yaml — real file & layering

Real file: `get_hermes_home()/"config.yaml"` (`hermes_cli/config.py:696-698`). Layering (high→low):
`/etc/hermes/config.yaml` managed scope (per-leaf-key, `hermes_cli/managed_scope.py`) → user
config.yaml → `DEFAULT_CONFIG` deep-merge (`hermes_cli/config_defaults.py`).

Top-level keys: model, providers, fallback_providers, credential_pool_strategies, toolsets,
database, runtime, max_concurrent_sessions, max_live_sessions, agent, terminal, web, browser,
checkpoints, context_file_max_chars, file_read_max_chars, mcp_discovery_timeout*, mcp,
tool_output, tool_loop_guardrails, compression, prompt_caching, openrouter, bedrock, auxiliary,
display, dashboard, privacy, tts, stt, voice, wake_word, human_delay, context, memory, delegation,
prefill_messages_file, goals, loops, moa, skills, curator, honcho, timezone, slack, discord,
whatsapp, telegram, mattermost, matrix, approvals, command_allowlist, quick_commands,
platform_hints, hooks, hooks_auto_accept, personalities, security, cron, kanban, code_execution,
tools, logging, model_catalog, model_overrides, models_dev, network, monitoring, gateway,
streaming, sessions, onboarding, telemetry, doctor, updates, lsp, x_search, secrets,
paste_collapse_*, computer_use, proxy, desktop, vertex, `_config_version`.

**`_config_version: 36`** (`config_defaults.py:3396`); migrations table-driven
(`hermes_cli/config_migrations.py`); **SUPPORT_FLOOR_VERSION = 12** (:52) — below 12 untouched +
"run hermes setup" (:57-66). **Migration tool must warn on _config_version < 12.**

Machine-specific keys: terminal.cwd/backend, mcp_servers[].command/args/cwd, model.base_url
(localhost), browser/lsp binary paths, proxy endpoints, prefill_messages_file, dashboard bind.

## 4. Secrets pipeline

Load order (`hermes_cli/env_loader.py:470-537`): `$HH/.env` override=True → scrub known keys
absent from profile .env (:498-500, `_PROFILE_MANAGED_ENV_KEYS` :76-83) → `.op.env`
override=False → project .env fill-only → external secret sources (bitwarden/onepassword/command,
`agent/secret_sources/`) → managed /etc/hermes/.env → terminal-config bridge re-wins.

## 5. Version stamps

| Stamp | Location | Value |
|---|---|---|
| App version | code only (`hermes_cli/__init__.py:17`) | 0.20.1 — **no on-disk state stamp exists (gap our manifest fills)** |
| Config schema | config.yaml `_config_version` | 36; floor 12 |
| Install method | `<install>/.install_method` (authoritative) | docker/nix/nixos/git/unknown |
| Build SHA | `<install>/.hermes_build_sha` (Docker) | 40-char |
| Update cache | `$HH/.update_check` | {ts,rev,ver,behind} — don't migrate |
| state.db | schema_version + state_meta | fts_storage_version etc. |
| Build stamps | web-ui-build-stamp.json, desktop-build-stamp.json | machine-specific — don't migrate |
| Managed | `.managed` | NixOS |

## 6. Reference implementation in-tree

`hermes_cli/backup.py` (see hermes-backup-precedent.md) — anchors at **root** (all profiles, :583),
symlinks skipped entirely (:329-330 — zipfile.write follows them = exfiltration), stage DB temp
files on destination filesystem not /tmp (:705-710), archive-prefix tolerance (:828-849),
validation markers {config.yaml,.env,state.db} (:811), quick-state list `_QUICK_STATE_FILES`
(:1096-1127), post-import regenerates profile wrappers + `ensure_gateway_service(context="import")`
(:1016-1082). Also `hermes_cli/profiles.py` curated lists: `_CLONE_ALL_DEFAULT_EXCLUDE_ROOT`
(:100-106), `_CLONE_ALL_HISTORY_EXCLUDE_ROOT` (:122-130), `_DEFAULT_EXPORT_EXCLUDE_ROOT`
(:207-229, credential-free portable export), `_DEFAULT_EXPORT_INCLUDE_ROOT` (:240-251);
`hermes_cli/profile_distribution.py:99-120` `USER_OWNED_EXCLUDE`.

## 7. Migrate vs Do-Not-Migrate

### MUST migrate
config.yaml, .env, .op.env, auth.json, .anthropic_oauth.json, shared/nous_auth.json, mcp-tokens/,
webhook_subscriptions.json, google_*/slack_tokens.json, pairing/ + platforms/pairing/,
credentials/, SOUL.md, memories/, root MD set (MEMORY/USER/todo/system_prompt/AGENTS/CLAUDE/
.cursorrules), skills/ (incl .archive, .usage.json), plugins/, plugin-data/, cron/jobs.json +
output/, cron/executions.db, state.db, kanban.db + kanban/boards/, projects.db, response_store.db,
memory_store.db, verification_evidence.db, discord_message_recovery.db, sessions/ (+saved/),
session-exports/, skins/, hooks/, scripts/, mcp.json, channel_directory.json +
channel_aliases.json, profiles/* (recursive), external memory dirs (~/.honcho, ~/.hindsight,
~/.openviking/ovcli.conf).

### MUST NOT migrate verbatim
PIDs/registries (gateway.pid, cron.pid, processes.json, gateway_state.json, proxy pid+nonce);
locks (gateway.lock, auth.lock, .backup.lock, cron/.tick.lock, .mcp-discovery.lock, install.lock,
kanban/.dispatcher.lock); SQLite sidecars; path-hashed caches (checkpoints/, sandboxes/,
chrome-debug/); host-shape markers (.container-mode, .managed, .install_method,
.gateway-launchd-unsupported, .termux_bundled_sync_stamp, build stamps, .update_check,
.update_pending*, .clean_shutdown, .restart_*); native/arch binaries (node/, node_modules/, bin/,
lib/libfts5_cjk.so, lsp/bin/, git/, gateway-service/, venv/, site-packages/, mcp-installs/ trees,
hermes-agent/); logs & caches; **device registrations** (whatsapp/session/creds.json — moving
while old machine runs fights for the device slot); shell/OS integration (shims, rc-file PATH
lines — hermes_cli/uninstall.py:39-43,115-117, systemd units, launchd plists, HKCU\Environment).
Units/plists bake HERMES_HOME + interpreter paths (`hermes_cli/gateway.py:3171,3111-3117`) →
**regenerate, never copy**.

### Absolute-path references INSIDE migrated data (rewrite or warn)
state.db sessions.cwd/git_repo_root; config.yaml terminal.cwd, mcp_servers[].command/args/cwd,
lsp.*, browser.*, prefill_messages_file; cron/jobs.json workdir/script; projects.db; kanban paths
+ attachments; checkpoints keys (unrecoverable — drop); Linux .desktop Exec=.

## 8. Platform nuances

- **Windows:** state root = install root parent; HKCU HERMES_HOME/HERMES_GIT_BASH_PATH/PATH
  additions (uninstall.py:311-329); PortableGit + Node under root (~200MB regeneratable);
  8.3 short names; msvcrt locking.
- **macOS:** ~/.hermes; launchd `ai.hermes.gateway[-profile].plist`; /Applications/Hermes.app;
  Docker-on-mac virtiofs = WAL-unsafe → journal_mode delete.
- **Linux:** systemd user/system units; .desktop under ~/.local/share/applications.
- **Termux:** app-private storage prefix (all abs paths differ); $PREFIX/bin/hermes;
  `.termux_bundled_sync_stamp`; constraints-termux.txt.
- **Docker:** /opt/data home, immutable /opt/hermes code, UID/GID chown, `_is_container()`
  disables chmods, boot sweeps stale runtime files per profile (`container_boot.py:75,417-418` —
  migration tool should do the same), `is_container()` detects Docker/Podman/k8s (:1248-1290);
  HERMES_HOME==cwd flips profile export to allow-list mode (profiles.py:231-251).
- **NixOS:** tmpfiles create dirs mode **2770** setgid, files 0660, config.yaml from Nix store
  (nixosModules.nix:711-780); managed mode refuses mkdir, no-op chmods, umask 0o007
  (config.py:898-938). **Restoring plain-mode backup onto managed install fights activation —
  detect .managed and refuse/adapt.**

## 9. State outside $HERMES_HOME

Foreign (don't migrate): ~/.claude/*, ~/.codex/auth.json, ~/.qwen/oauth_creds.json, gh CLI.
Migrate via _external/: ~/.honcho/, ~/.hindsight/, ~/.openviking/ovcli.conf.
Regenerate: ~/.local/bin shims + profile wrappers, systemd/launchd units, rc-file PATH lines,
HKCU\Environment, desktop apps (/Applications/Hermes.app, %LOCALAPPDATA%\Programs\Hermes,
.desktop entries — `hermes_cli/gui_uninstall.py:111-156`).
Admin scope (never touch): /etc/hermes/{config.yaml,.env}.
Electron userData (optional; connection.json host-specific): ~/Library/Application Support/Hermes,
%APPDATA%\Hermes, ~/.config/Hermes (`gui_uninstall.py:24-31,70-87`).

## 10. Twelve traps for a scanner engine

1. Anchor at `get_default_hermes_root()` not `get_hermes_home()` (all profiles; backup.py:583).
2. Prune `hermes-agent` at ROOT level only — `skills/autonomous-ai-agents/hermes-agent/` is real
   data (backup.py:39-42,297-319).
3. Never follow symlinks either side (backup.py:279-294,329-330).
4. Never byte-copy live `.db` — sqlite3.backup(), fail closed (backup.py:342-369).
5. Stage DB temps on destination filesystem, not /tmp (tmpfs truncation; backup.py:705-710).
6. Cap integrity_check by size (2GiB; 30GB state.db exists; backup.py:405-413).
7. Detect zeroed DBs (backup.py:372-396, #68474).
8. Don't create empty legacy dirs (get_hermes_dir semantics; #27602).
9. `kanban.db` and `shared/nous_auth.json` are ROOT-level, not per-profile.
10. Restore secret modes explicitly (0600) — archives drop them (backup.py:132,976-978).
11. Test harnesses MUST set HERMES_HOME to tmp — SessionDB refuses production state.db under
    pytest (hermes_state.py:466-512); auth path raises (auth.py:1045-1057).
12. Post-restore: regenerate profile wrappers + gateway services, clear .update_check, never
    restore gateway_state.json/PIDs (backup.py:104-129,1016-1082).
