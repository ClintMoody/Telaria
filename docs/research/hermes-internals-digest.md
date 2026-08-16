# Hermes Agent Internals — Research Digest (Migration Perspective)

Ground truth for the design phase. Compiled from direct source reading of
NousResearch/hermes-agent @ v2026.8.13 (tag list ends v2026.8.13; pyproject version 0.20.1)
plus five subsystem research sweeps. Repo-relative citations throughout.

## 0. Identity & versions

- Product: "The self-improving AI agent" — creates skills from experience, improves them during
  use (pyproject.toml description). This is why stock-vs-modified detection is a core migration
  feature, not a nicety: *the agent mutates its own install by design*.
- Python: `requires-python = ">=3.11,<3.14"` (pyproject.toml — upper bound is load-bearing; uv
  refuses 3.14). `.python-version` = 3.11.
- Dependencies exact-pinned (supply-chain incident 2026-05-12 documented in pyproject comments);
  provider-specific extras lazy-installed via `tools/lazy_deps.py`.
- Version tags: `vYYYY.M.D` scheme (e.g. v2026.8.13).

## 1. Install topology (verified in scripts/install.sh)

| Piece | Default location | Notes |
|---|---|---|
| Data home (`HERMES_HOME`) | `~/.hermes` (Linux/macOS/WSL2/Termux); `%LOCALAPPDATA%\hermes` (native Windows) | Env override `HERMES_HOME`; install.sh:48 |
| Code | `$HERMES_HOME/hermes-agent` — a **git clone** | install.sh:403–453; checks for `.git` at :429; override `HERMES_INSTALL_DIR`/`--dir` |
| Managed uv | `$HERMES_HOME/bin/uv` | install.sh:562–594 |
| Managed Node.js | `$HERMES_HOME/node/` (bin symlinks; npm prefix pinned via `$HERMES_HOME/node/etc/npmrc`) | install.sh:478–492, 952–974 |
| Windows extras | Portable MinGit at `%LOCALAPPDATA%\hermes\git`; installer bundles uv, Python 3.11, Node, ripgrep, ffmpeg | README Quick Install |
| Skills opt-out marker | `$HERMES_HOME/.no-bundled-skills` | install.sh:175 |
| Root installs | Code may live outside home while data stays at `/root/.hermes` | install.sh:64 |

Consequence: **stock diffing has a fast path** — the install dir is usually a git checkout, so
`git status`/`git diff` against the checked-out ref is exact. Fallback for gitless installs: a
version-pinned hash manifest.

## 2. State home contents (verified so far; see subsystem reports for full map)

- `config.yaml` — 23+ top-level sections (database, runtime, model, kanban, terminal, browser,
  tool_loop_guardrails, compression, prompt_caching, memory, session_reset, streaming, skills,
  agent, platform_toolsets, stt, code_execution, delegation, display, telemetry, updates,
  max_concurrent_sessions, group_sessions_per_user) plus `mcp_servers` (validated by
  `hermes_cli/doctor.py` "MCP Server Security" section).
- `.env` — ~125 documented env vars (~40 secret-bearing: provider keys, `SUDO_PASSWORD`,
  `TERMINAL_SSH_KEY`, `EMAIL_PASSWORD`, bot tokens, webhook secrets…). `.env.example` is the catalog.
- `skills/` — user/agent-created skills; **skill creation always writes here**
  (cli-config.yaml.example `skills:` section). `skills/.archive/` = curator-archived restorable
  skills (hermes_cli/backup.py exclusion comments). `skills.external_dirs` config can mount
  read-only skill dirs from arbitrary paths — migration must chase these references.
- `profiles/<name>/…` — named profiles duplicate state subtrees (backup.py basename-matching).
- SQLite DBs in WAL mode by default (`database.journal_mode`), with documented WAL-on-network-fs
  hazards; `state.db` named in backup.py `_SECRET_FILE_NAMES`.
- Machine-bound runtime files: `gateway_state.json`, `gateway.pid`, `cron.pid`, `gateway.lock`,
  `processes.json` (backup.py `_IMPORT_SKIP_NAMES` — restoring these cross-machine caused real
  incidents, their NS-508).
- External-to-home state: memory providers may store at e.g. `~/.honcho`, `~/.hindsight`, declared
  via `MemoryProvider.backup_paths()` (backup.py `_collect_memory_provider_external_paths`).

## 3. Native tooling precedents (full study: hermes-backup-precedent.md)

- `hermes backup` / `hermes import`: same-machine zip with SQLite `sqlite3.backup()` snapshots,
  atomic publish, `.backup.lock`, fixed exclusions, overlay restore. No cross-platform, no
  selection, no provenance, no dependency intel.
- `hermes doctor`: sectioned OK/WARN/FAIL checks with `--fix` and accumulated manual-action list —
  our preflight UX model. Includes security advisories and MCP stdio-command validation
  (`hermes_cli/mcp_security.py`).
- `hermes claw migrate` (hermes_cli/claw.py): inbound migration from OpenClaw — evidence upstream
  values migration tooling; nothing exists for Hermes→Hermes cross-machine.
- `hermes update`: pre-update backups + `restore_cron_jobs_if_emptied` (update once wiped cron
  stores — regression they now guard).

## 4. Integration surface (headline facts; details in subsystem reports)

- Messaging gateway platforms: Telegram, Discord, Slack, WhatsApp, Signal, Email — one gateway
  process (README). WhatsApp/Signal imply device-linked session state (machine-bound; re-pair).
- Terminal backends: local, Docker, SSH, Singularity, Modal, Daytona, Vercel Sandbox (README) —
  configs reference remote endpoints/keys.
- Providers: 20+ (config example provider list) with per-provider env keys; local servers
  (LM Studio/ollama/vLLM) reference localhost URLs that may not exist on target.
- MCP servers: `mcp_servers` in config.yaml; `optional-mcps/` bundles (comfy-cloud, figma, linear,
  n8n, unreal-engine); stdio commands validated by doctor.
- Cron: built-in scheduler (`cron/` package: jobs, scheduler_provider, executions, monitor…) with
  delivery to platforms; `plugins/cron_providers/`.

## 5. Subsystem reports (all complete)

Deep-dive reports live alongside this digest — read them before designing any engine:

- `subsystem-state-layout.md` — definitive HERMES_HOME map, credentials matrix, DB handling,
  migrate/never-migrate lists, 12 scanner traps
- `subsystem-skills-plugins.md` — `.bundled_manifest` stock baseline, no-overlay seeding model,
  `.usage.json` provenance, hub lock.json, curator interactions, plugin state
- `subsystem-cron.md` — jobs.json schema incl. runtime claim fields to scrub, in-process ticker
  (no OS cron), gateway service re-registration, TZ trap, preflight mirrors
- `subsystem-integrations.md` — per-platform (a/b/c/d) classification, MCP enumeration recipe,
  Camoufox user_id trap, post-restore checklist actions
- `subsystem-install-update.md` — install layouts per platform, install-method detection
  algorithm, lazy-extras probing, restore recipe, traps table

Also: `hermes-backup-precedent.md`, `competitor-teardown.md`, `m2c1-adoption.md`.

### Headline cross-cutting findings

1. **Stock diffing is half-solved upstream**: `~/.hermes/skills/.bundled_manifest` (name:md5 of
   last-seeded bundled skill) is the baseline; `hermes skills list-modified --json` exists. The
   code checkout is a git clone → `git status`/`diff` is exact for repo files. Our tool adds:
   cross-version stock reconstruction, non-skill config diffing, and report UX.
2. **Nothing records lazy-installed provider extras** — must be probed from the source venv and
   re-provisioned on target.
3. **Machine-bound state is a first-class category** with documented incidents (gateway_state
   NS-508; WhatsApp device unlinking; Camoufox path-derived identity silently orphaning logins).
4. **Everything OS-registered (systemd/launchd/schtasks/.vbs/.desktop, registry) must be
   regenerated via `hermes gateway install`, never copied** — units bake absolute paths.
5. **Secrets are plaintext files everywhere** (no OS keyring): .env, auth.json, mcp-tokens/,
   platform token files, pairing stores — a coherent (d)-class handling policy is mandatory.
6. **The applier must emit a post-restore action checklist** (re-pair, reauth, re-enroll,
   re-register, reinstall MCPs, npm install bridge, hermes doctor) — some steps are inherently
   interactive (QR scans) and cannot be automated.

## 6. Hard requirements these facts impose on the tool

1. Two layout families (`~/.hermes` vs `%LOCALAPPDATA%\hermes`) + arbitrary `HERMES_HOME` — the
   scanner must *resolve*, never assume.
2. SQLite must be snapshotted via the backup API with integrity checks — never file-copied hot.
3. Machine-bound set must be excluded on capture AND filtered on apply (both-sides defense).
4. The code dir is a git clone — never packed wholesale; record ref + dirty-diff instead, restore
   by re-clone/checkout + patch replay for dirty stock files the user opts to keep.
5. Secrets are pervasive (.env + auth.json + tokens inside platform state) — redaction must be
   default-on with an explicit, visible opt-in vault.
6. Paths inside configs (external skill dirs, terminal backends, cron scripts) reach outside
   HERMES_HOME — the scanner needs a reference-chasing pass with per-reference portability verdicts.
7. Named profiles multiply every rule — all rules apply per-profile subtree.
8. Version skew between source and target Hermes must be detected (tag/commit + pyproject version)
   and gated with guidance (run `hermes update` first, or accept skew consciously).
