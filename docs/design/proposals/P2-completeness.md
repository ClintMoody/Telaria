# Proposal P2 — The Completeness Lens (Cockos Reaper)

Author: completeness/power-user advocate. Scope: full feature surface — artifact taxonomy,
selection UI, diff viewer, dependency matrix, profiles, rewrite editor, bundle inspector, CLI,
config files, expert toggles. Priorities: **P0** ship-blocking / **P1** should / **P2** later.

Citations reference `docs/research/*` (file § section).

## 1. Philosophy: everything visible, nothing silent, defaults you never have to touch

Reaper's covenant is: the default session works for a novice, and *every* behavior is inspectable
and overridable for the expert. Translated to Talaria:

1. **Every byte the scanner sees appears somewhere in the UI** — as a selectable item, a
   record-only entry, or an "Unrecognized" bucket. The competitor silently drops `sessions/`,
   `logs/`, `cache/` wholesale (competitor-teardown.md W4); Hermes' own backup uses fixed,
   invisible exclusion sets (hermes-backup-precedent.md "What it does NOT do" #5). We do neither.
2. **Defaults encode the research, not opinion.** Each default carries a one-line reason and a
   citation, shown on hover/`--explain`. E.g. "gateway_state.json: excluded — restoring it
   cross-machine broke hosted gateways (NS-508)" (hermes-internals-digest.md §2).
3. **Some invariants are not toggles.** Transactional apply, read-only capture, SQLite via
   `sqlite3.backup()`, secret modes 0600, both-sides machine-bound filtering — these are
   correctness, not preference (subsystem-state-layout.md §10; hermes-backup-precedent.md).
   Reaper lets you customize everything *except* the parts that would corrupt your project file.

## 2. The artifact taxonomy — master model (P0)

The scanner models **20 artifact families, ~70 leaf artifact types**. Class legend (adopted from
subsystem-integrations.md §0): **(a)** copy verbatim · **(b)** copy + rewrite paths/hosts ·
**(c)** machine-bound, re-create on target · **(d)** secret material. Classes compose: an item is
`{class, secret: bool, machine_bound: bool, default: on|off|record-only|never}`. "record-only"
means captured as metadata in the manifest, never as payload. "never" items are excluded on
capture AND filtered on apply — both-sides defense, because archives predate hygiene
(hermes-backup-precedent.md, NS-508 lesson).

All families repeat **per profile** under `profiles/<name>/` (subsystem-state-layout.md §1.3);
ROOT-level exceptions called out inline (kanban.db, shared/nous_auth.json — §10 trap 9).

### 2.1 Identity & Memory — class (a), default ON

| Artifact | Notes | Cite |
|---|---|---|
| `SOUL.md` | must-migrate; compare against `default_soul.py` to mark customized vs stock | state-layout §2.1; install-update §8 |
| `memories/MEMORY.md`, `memories/USER.md` | §-split entries | state-layout §2.1 |
| Root MD set: `MEMORY.md`, `USER.md`, `todo.json`, `system_prompt.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `desktop.json` | upstream's own portable set | state-layout §2.1 (profiles.py:240-251) |
| `skins/*.yaml`, `dashboard-themes/` | | state-layout §2.1 |

### 2.2 Configuration

| Artifact | Class | Default | Notes | Cite |
|---|---|---|---|---|
| `config.yaml` | (a) + (b) keys + (d) keys | ON | ~70 top-level keys; (b): `terminal.cwd`, `mcp_servers[].command/args/cwd`, `model.base_url`, browser/lsp paths, `prefill_messages_file`, dashboard bind; (d): inline `api_key`/`client_secret`/`extra_headers`. Gate: warn if `_config_version < 12` (floor) | state-layout §3 |
| `active_profile` | (a) | ON | re-verify profile exists on target | state-layout §2.1 |
| `mcp.json` (per-profile) | (a)/(b) | ON | | state-layout §2.6 |
| `skill-bundles/*.yaml` | (a) | ON | bundles win over same-named skills | skills-plugins §2 |
| `.no-bundled-skills` | (a) | ON if present | seeding opt-out marker | digest §1 |
| `context_length_cache.yaml`, `config.yaml.corrupt.*.bak` | (c) | never / OFF | regeneratable / debris | state-layout §2.1 |

### 2.3 Secrets — class (d), default = Handoff Checklist; payload only with vault (P0)

`.env` (~40 secret-bearing of ~125 vars), `.op.env`, `auth.json`, `.anthropic_oauth.json`,
`shared/nous_auth.json` (**ROOT-level**), `mcp-tokens/*` (`.client.json` also (b): embeds loopback
port), `webhook_subscriptions.json`, `google_token.json` + 4 Google siblings,
`google_chat_user_*`, `slack_tokens.json`, `credentials/`, `honcho.json`/`mem0.json`/
`hindsight/config.json`/`byterover/`, proxy key (pid/nonce/audit are (c) never). Locks
(`auth.lock`) never. `cache/bws_cache*` never — regenerated from Bitwarden.
(state-layout §2.2; integrations §7(d)). Scanner MUST use the three canonical secret classifier
lists from Hermes source as its seed dictionary (`file_safety.py`, `_ROOT_CREDENTIAL_FILES`,
`_SECRET_FILE_NAMES` — state-layout §2.2) so unknown files matching those patterns classify (d).

### 2.4 Skills — class (a) with provenance subclasses (P0)

| Artifact | Default | Notes | Cite |
|---|---|---|---|
| `skills/<cat>/<skill>/` | ON | provenance computed per §3; support-dir rule: `SKILL.md` inside `references/templates/assets/scripts` is data, not a skill | skills-plugins §1 |
| `.bundled_manifest` | ON (forced with skills) | THE stock baseline (`name:md5`) | skills-plugins §5 |
| `.usage.json` | ON (forced) | agent-vs-user provenance; losing it freezes curation | skills-plugins §5 |
| `.curator_suppressed` | ON, **coupled** with `.archive/` | restore one without the other = resurrection or permanent loss | skills-plugins §8 |
| `.archive/` | ON | curator-archived, restorable value | skills-plugins §8 |
| `.hub/{lock.json,taps.json,audit.log}` | ON | install provenance; modified hub skills orphan without it | skills-plugins §4 |
| `_org/**`, `.sync_state` | ON if present | org baselines | skills-plugins §5 |
| `.sync_device_id` | never | regenerate per machine | skills-plugins §2 |
| `.hub/index-cache`, `.hub/quarantine`, `.curator_backups`, `.restore-backups`, `*.bak`, `.usage.json.lock`, `.skills_prompt_snapshot.json`, `.termux_bundled_sync_stamp` | never/OFF | regeneratable or machine-local | skills-plugins §2, "Drop" list |
| `skills.external_dirs` trees | ON, staged under `_external/` | reference-chased; rewrite the config pointer | digest §2; state-layout §2.2 |

### 2.5 Plugins

`plugins/<name>/` user plugins (a, ON) with embedded `venv/`/`node_modules/` subtrees stripped to
(c) + "reinstall" flag; `plugin-data/<ns>/state.json` (a, ON — namespace is
`agent-plugin-<slug>-<sha256[:8]>`, not guessable: map with the same hash function);
`plugins.*` config incl. `entries.<id>.granted_capabilities` (a). Missing `$HH/plugins/` silently
degrades `cron.provider` to builtin — coupling rule in §4.3. (skills-plugins §7; cron §2.3)

### 2.6 Automations (cron) — per profile, never global (P0)

| Artifact | Class/Default | Notes | Cite |
|---|---|---|---|
| `cron/jobs.json` | (a)+(b), ON | scrub `run_claim`/`fire_claim`/`preflight_alerted`/`drift_alerted`; KEEP `last_run_at` (interval anchor), `repeat.completed` (re-fire guard); (b): `workdir`, absolute `script`, absolute `skills` | cron §1.3, §3.1 |
| `cron/notepad.db` | (a), ON | per-job durable KV; stateful jobs restart from scratch without it | cron §3.3 |
| `cron/suggestions.json` | (a), ON | holds dismissal latches | cron §1.2 |
| `cron/output/**` + `monitor_last_output.txt` | (a), ON | `context_from` reads these; monitor hash+baseline must move together | cron §1.2, §7 |
| `cron/executions.db` | (a), OFF by default | audit only; drop non-terminal rows on restore | cron §3.2 |
| `$HH/scripts/**` | (a)/(b), ON (forced with jobs that reference scripts) | hard dependency, outside `cron/` | cron §5 |
| heartbeats, `.tick.lock`, pids, tmp, `inflight_forced_releases.jsonl` | never | machine liveness | cron §1.2 |
| config `cron.*` + `timezone` | (a), ON | TZ is the biggest correctness risk — carry + warn | cron §6 |

### 2.7 Conversations & History

`state.db` (a + content-sensitive; snapshot via backup API, integrity_check capped at 2 GiB —
30 GB instances exist; machine columns `sessions.cwd/git_repo_root` flagged for §8),
legacy `sessions/` + `sessions.json` + `saved/`, `session-exports/` — all (a) ON.
`response_store.db`, `memory_store.db`, `verification_evidence.db`, `retaindb_queue.db`,
`discord_message_recovery.db` (a) ON. `state-snapshots/`, `moa-traces/`, `spawn-trees/` (a) OFF
(forensic). `checkpoints/store/` **never** — keys are `sha256(abs_path)`, unrecoverable
cross-machine. (state-layout §2.3–2.4, §7)

### 2.8 Boards & Projects

`kanban.db` (**ROOT-level**), `kanban/boards/<slug>/{kanban.db,board.json}`, `projects.db` — (a)
ON with (b) path fields (attachments roots, project paths). (state-layout §2.3, §10 trap 9)

### 2.9 Messaging platforms (the (c)/(d) heartland)

| Artifact | Class | Default | Notes | Cite |
|---|---|---|---|---|
| `pairing/` + `platforms/pairing/` | (a)+(d) | ON | merge dual layouts on capture | integrations §1.3, §0 |
| `channel_directory.json`, `channel_aliases.json`, sticker/threads/feishu maps | (a) | ON | user routing | state-layout §2.7 |
| `whatsapp/session/creds.json` | (c)/(d) | OFF → re-pair checklist | expert opt-in copy with loud warning (device-slot fight) | integrations §1.2 |
| `scripts/whatsapp-bridge/` node_modules | (c) | record-only | `npm install` on target; doctor checks it | integrations §1.2 |
| signal-cli store (`~/.local/share/signal-cli`) | (c) | record-only | outside HERMES_HOME; re-link QR; expert copy (single-device) | integrations §1.2 |
| Matrix `store/` + `crypto.db` | (c)/(d) | OFF | expert: wholesale move valid only if source stops (Olm corruption) | integrations §1.2 |
| `weixin/accounts/*` | (c) | never → re-scan | QR-login artifacts | integrations §1.2 |
| `gateway_state.json`, pids, locks, `processes.json`, `dead_targets.json`, `restart_loop.json`, `pending_messages/`, `runtime/` | never | both-sides filtered | NS-508 | state-layout §2.7 |

### 2.10 MCP / Providers / Browser / Dashboard / Observability

- MCP: `mcp_servers` entries classified **per entry** by the deterministic recipe — url→portable,
  command→runtime dep, `${VAR}` interpolation→(a), literal abs path→(b), `mcp-installs/` path→(c)
  reinstall (integrations §2.4). `mcp-installs/` never (reinstall via `hermes mcp install`).
- Providers: config (a); env keys (d); localhost base_urls (b)/(c); `~/.aws`, GCP ADC, Entra —
  **foreign-owned, record-only + checklist**, never copied (integrations §3).
  Caches (`cache/model_catalog.json` etc.) never.
- Browser: cloud-backend keys (a)/(d); `chrome-debug/` OFF (OS-keyring-encrypted; expert same-OS
  copy); **Camoufox user_id auto-captured and pinned** on target via `browser.camofox.user_id` —
  silent total login loss otherwise (integrations §5).
- Dashboard: config (a); `public_url` (b); `basic_auth.secret` (d) with keep-sessions vs rotate
  toggle; OAuth client registration (c) → `hermes dashboard register` checklist; build stamps never
  (integrations §4).
- Observability: `hooks.outbound` (a) + `secret_env` resolution check; otlp endpoint (b);
  **`monitoring.install_id` keep-vs-rotate decision surfaced, default keep on replace** (integrations §6).

### 2.11 Code & runtime — record-only family (P0)

Captured as manifest metadata, never as payload: git branch/HEAD/tag, `status --porcelain`,
dirty diff as patch + untracked list, stash presence; `.install_method` (7-step detection
algorithm reproduced exactly); version triple (`__version__`, release date, `.hermes_build_sha`);
**lazy-extras feature list via source-venv probe of `active_features()`** — nothing else records
them (install-update §4, §9, §12). Never packed: venv, `node/`, `bin/`, `lib/libfts5_cjk.so`
(native), `lsp/bin/`, `git/`, `gateway-service/`, `hermes-agent/` checkout (re-clone at same
commit; prune at ROOT level only — `skills/**/hermes-agent/` is data, state-layout §10 trap 2).
`$HH/hooks/` IS user content — (a) ON (state-layout §7 MUST list).

### 2.12 OS integration — regenerate family

systemd units / launchd plists / schtasks + `.vbs` / `.desktop` / HKCU registry entries / shims /
profile wrapper scripts / rc-file PATH lines: (c) record-only → target regenerates via
`hermes gateway install`; units bake HERMES_HOME + interpreter paths (integrations §1.4;
state-layout §7). We *record* their existence so preflight knows a gateway service was configured.

### 2.13 External, Desktop, Managed, Unrecognized

- External state: `~/.honcho`, `~/.hindsight`, `~/.openviking/ovcli.conf` (a) via `_external/`
  home-relative encoding (state-layout §2.2, §9). Foreign creds (`~/.claude`, `~/.codex`,
  `~/.qwen`, gh) **never** — surfaced in the checklist as "re-auth these tools".
- Desktop (Electron userData): `connection.json` (b), `active-profile.json`, `updates.json` (a) ON;
  `desktop-installation.json` installationId + `window-state.json` (c) never (install-update §5).
- Managed scope `/etc/hermes/*`: never touch; detect `.managed` and refuse/adapt plain restore
  onto managed installs (state-layout §8 NixOS).
- **Unrecognized bucket (P0)**: any path not matched by the model is listed under "Unrecognized",
  default ON if outside never-zones and not secret-pattern-matched, (d)-quarantined if it matches
  the canonical secret dictionaries. Forward-compat: future Hermes versions must not silently leak
  or silently drop (competitor W16 answer).

## 3. Provenance subclassification (P0)

Every skill gets one of six provenance tags, computed exactly as upstream does
(skills-plugins §5): **stock-pristine** (dir-hash == `.bundled_manifest` entry),
**stock-modified** (mismatch; diffable), **hub-installed** (in `.hub/lock.json`),
**org** (in `_org/*/.org-baseline.json`), **agent-created** (`.usage.json created_by=="agent"`),
**user-created** (none of the above). Reuse the MD5 dir-hash algorithm bit-exactly (sorted rglob,
relpath+bytes); do NOT mix with the hub's SHA-256/16 or org fingerprints — three incompatible
digest schemes coexist (skills-plugins §5 "Second hash scheme"). Config provenance: diff
config.yaml against `DEFAULT_CONFIG` extracted from the source install's venv (§13 enrichment),
so the selection tree shows "17 of 70 sections customized". Checkout provenance: git
status/diff (digest §1 fast path).

## 4. Selection model (P0)

### 4.1 Tree structure

Functional grouping first (what users think in), location view as a toggle (what disks think in):

```
▸ Profile: default (root)                      ▸ Profile: coder
  ▸ Identity & Memory          ▸ Skills (82 stock, 3 modified, 7 custom, 2 agent)
  ▸ Configuration              ▸ Plugins
  ▸ Automations (14 jobs)      ▸ Conversations & History (2.1 GB)
  ▸ Boards & Projects          ▸ Messaging platforms
  ▸ MCP servers (6)            ▸ Providers & model auth
  ▸ Browser                    ▸ Dashboard & webhooks
  ▸ Secrets (→ checklist/vault)▸ External state
  ▸ Code & runtime (record)    ▸ OS integration (record)
  ▸ Desktop app                ▸ Unrecognized (3 items)
```

Each node: tri-state checkbox (on/off/mixed), size + file count, class badge (a/b/c/d), secret
badge, machine-bound badge, provenance chip, "why this default" tooltip with citation. Leaf =
artifact; skills expand to per-skill; cron expands to per-job.

### 4.2 Tri-state + search/filter

Space toggles; parent reflects children (mixed). Search box filters by name/path; filter chips:
class, provenance, secret, machine-bound, size >N, default-changed, "has warnings". Reaper-style
`/` focus-search, arrow navigation. Bulk ops: "select all agent-created skills",
"deselect everything over 1 GB".

### 4.3 Coupling rules engine (P0 — my hill to die on)

Selections have semantic dependencies; the engine enforces them as **hard couples** (auto-include,
shown as lock icon) or **soft warnings**:

| If selected | Requires | Kind | Cite |
|---|---|---|---|
| any skill | `.bundled_manifest`, `.usage.json` | hard | skills-plugins §5 |
| `.curator_suppressed` | `.archive/` (and vice-versa warn) | hard | skills-plugins §8 |
| cron job with `script` | `$HH/scripts/<script>` | hard | cron §5 |
| cron job with `context_from` | referenced jobs + their `output/` dirs | hard | cron §4 |
| cron job `monitor_state` | `output/<id>/monitor_last_output.txt` | hard | cron §7 |
| `cron.provider != builtin` | `plugins/<provider>/` | hard | cron §2.3 |
| job `skills: [x]` | skill x (or warn: preflight will flag) | soft | cron §4 |
| hub-modified skill | `.hub/lock.json` | hard | skills-plugins §4 |
| MCP entry with `${VAR}` | var listed in Secrets Checklist | soft | integrations §2.4 |
| skill with `required_environment_variables` | vars in checklist | soft | skills-plugins §6 |
| `memory.provider = honcho/...` | external dir + provider config | hard | state-layout §2.2 |

Deselecting a hard-required item forces deselecting its dependents (with explanation) — never a
silently broken bundle.

### 4.4 Presets (P0) + Migration Intent switch (P0)

**Intent switch — `replace` vs `clone` — is the first question the tool asks** and flips defaults
globally. Research warns repeatedly that the failure mode of two live copies is account unlinking
and split messages, not startup errors (integrations §8): Telegram polling 409s, WhatsApp device
slot fights, Matrix Olm corruption, relay gatewayId collision. `replace` (default): keep
`monitoring.install_id`, keep platform tokens, checklist says "stop old gateway first". `clone`:
rotate install_id, exclude single-consumer platform credentials (Telegram/WhatsApp/Signal/Matrix/
relay) with per-item override, keep skills/config/memory.

Presets (claw-migrate precedent: presets + include/exclude escape hatch, install-update §7):
1. `everything-portable` (default): all (a)+(b), (d)→checklist, (c)→record+checklist.
2. `essentials`: identity, config, skills, plugins, cron, memory dirs; no history DBs.
3. `identity-only`: SOUL.md, memories/, USER.md, skins.
4. `full-forensic`: everything incl. logs, executions.db, snapshots, traces (record-only stays
   record-only).
5. `vaulted-full`: everything-portable + encrypted secrets vault.
6. Custom presets: saved to config file (§11), shareable.

## 5. Diff viewer (P0 CLI / P1 GUI polish)

Three diff surfaces, one UI:
1. **Skills stock-vs-modified**: reuse upstream semantics bit-exactly (`list-modified` +
   `diff_bundled_skill`: per-file unified diff, status modified/added/removed/binary via NUL
   detection — skills-plugins §5). Baseline = `.bundled_manifest`; cross-version stock
   reconstruction via `git checkout <tag> -- skills/` when the checkout is present (skills-plugins
   §5 "Reconstructing"). Side-by-side + unified toggle; per-hunk copy.
2. **Config vs defaults**: config.yaml against extracted `DEFAULT_CONFIG` (§13), rendered as a
   key-tree with changed/added/default badges; secrets values masked. Warn markers on (b)/(d) keys.
3. **Checkout dirty diff**: the recorded git patch, viewable per file.

GUI: monospace side-by-side with intra-line highlights; CLI: `talaria diff skills [name]`,
`talaria diff config`, `talaria diff checkout`, all with `--json`.

## 6. Dependency matrix (P0 engine + CLI; P1 full GUI grid)

**Rows** = dependent artifacts: each cron job, each skill (enabled), each MCP server, each
platform, each provider, each plugin, dashboard, browser engines.
**Columns** = requirement kinds: OS gate (`platforms[]` — the only hard skill gate), env
var/secret (`required_environment_variables` — enforced), binary (`prerequisites.commands` —
advisory; bash-for-`.sh` on Windows), Python pkg / lazy extra, Node runtime, network endpoint
(localhost/LAN/public), OS service (gateway, LM Studio, ollama, signal-cli, Docker daemon),
credential file/token, cross-artifact refs (`context_from`, skill refs, MCP toolset refs),
config keys (`skills.config.*`). (skills-plugins §6; cron §4; integrations §2.4, §3)

**Verdict vocabulary (per cell, per target OS)**: `OK` / `OK-AFTER-REWRITE` / `ACTION`
(re-pair, reauth, reinstall, npm install) / `MISSING-INSTALLABLE` / `IMPOSSIBLE` /
`UNKNOWN-OFFLINE`. Examples of IMPOSSIBLE: skill `platforms: [macos]` → Linux target;
BlueBubbles without a reachable macOS server; `.sh` cron script on bash-less Windows;
Termux target = no OS-registered ticker, jobs run only while foreground gateway lives (cron §6).

**Two evaluation modes**: (i) *predictive* at pack/inspect time against a declared target OS
(columns for linux/macos/windows/termux side by side); (ii) *live preflight* at apply time,
probing the real machine — mirroring Hermes' own cron preflight signals
(`missing_required_environment_variables`, `missing_required_commands`,
`missing_credential_files` — cron §4) and doctor's sectioned OK/WARN/FAIL + accumulated
manual-action list UX (digest §3). Cell click → evidence (which file, which line/key) +
remediation command. Extra P0 checks surfaced here: model/provider snapshot drift (fails closed
with `[drift_skip]` — cron §4), croniter presence, version skew source↔target (digest §6.8),
`_config_version` floor, soon-past one-shot jobs (>120s grace — a migration taking >2 min makes
them un-resumable; cron §6), WAL-on-network-home journal fallback (state-layout §2.3).

## 7. Profiles (P0)

- Scanner anchors at `get_default_hermes_root()` equivalent, walks root + every
  `profiles/<name>/` as a full sub-universe (own .env, auth.json, mcp-tokens, whatsapp session,
  cron store — cron §1.1; integrations §0). ROOT-level singletons handled once (kanban.db,
  shared/nous_auth.json).
- Selection tree: one top-level node per profile; per-profile presets allowed.
- **Apply-time profile mapping (P1)**: migrate source profile `coder` → target profile `work`;
  root→profile and profile→root promotions with path/reference adjustment; collision detection.
- Profile aliases (`~/.local/bin/<profile>` wrappers) are machine-specific — regenerated on
  target, mirroring upstream import (state-layout §1.3).
- Partial migration: pack only selected profiles (`--profile coder --profile default`).

## 8. Path-rewrite plan editor (P0 plan+preview; P1 GUI editor)

Rewrites are **computed on the target at apply time** (only there are real target paths known),
from anchors recorded at pack time: source HERMES_HOME, source $HOME, username, OS family,
path separator. Auto-generated mapping rules: home-prefix, hermes-home-prefix, username swap,
POSIX↔Windows separator + `%LOCALAPPDATA%\hermes` ↔ `~/.hermes` layout translation
(install-update §0).

**The plan is a first-class, editable document** (`rewrite-plan.json`): one entry per rewrite =
{file, locator, before, after, rule, confidence}. Locator is structural, never regex-over-bytes
(competitor W7 answer): YAML key-path for config.yaml (`mcp_servers.figma.cwd`), JSON pointer for
jobs.json (`/jobs/3/workdir`), env-var name for .env values that are paths, `db.table.column@rowid`
for opted-in SQLite rewrites. Known rewrite sites enumerated from research: config.yaml (b)-keys;
`jobs.json` `workdir`/`script`/absolute `skills` (rewrite absolute script → relative, upstream
blocks foreign-home absolutes — cron §5); `skills.external_dirs`; MCP `command/args/cwd/
ssl_verify/client_cert/client_key`; kanban/projects path fields; desktop `connection.json`;
`${userHome}`/`${env:VAR}` interpolations pass through untouched (already portable —
integrations §2.1). `state.db` `sessions.cwd`/`git_repo_root` rewrites are OFF by default
(historical data; dangling enumerated in report per `hermes_state_portability`), expert opt-in.

UI: table of rewrites with per-row before→after preview in context (3 lines), accept/reject/edit
per row, add custom mapping rule, "apply rule to N similar". CLI: `talaria plan rewrites`,
`--accept-all`, `--edit plan.json`, and every apply dry-run renders the full plan as a diff.
Custom regex rules exist but are expert-gated and preview-mandatory.

## 9. Bundle inspector (P0)

`talaria inspect bundle.hermespack` and GUI "Open bundle" work **without any Hermes install** —
pure stdlib on Python 3.9 (constraint 2 — this is why the floor matters: the target box has no
Hermes yet). Features:
- Manifest view: schema version, source system snapshot (OS/arch/HERMES_HOME/version
  triple/install method/git ref/lazy features), selection record, intent (replace/clone),
  creation time, tool version.
- Tree browser with the same functional grouping + per-file SHA-256 verify (`--verify` full
  re-hash; exit non-zero on mismatch).
- View any text member (`--cat member`), extract single artifacts (`--extract PATH -o dir`).
- Secrets Handoff Checklist render; vault status (sealed/unlocked; names only while sealed).
- Predictive dependency matrix re-evaluated against any `--target-os`.
- **Diff-against-install (P1)**: bundle vs live install — "what would change if applied here",
  per-artifact add/overwrite/conflict.
- **Bundle-vs-bundle compare (P2)**: drift between two snapshots of the same agent.
- Degraded ingestion (P1): open a plain `hermes backup` zip, classify best-effort, allow
  apply-with-reduced-intelligence (hermes-backup-precedent.md "Interop decisions").

## 10. CLI surface (P0 = full parity; every command has `--json`)

```
talaria scan      [--home PATH] [--profile NAME]... [--all-profiles] [--deep]
                  [--refresh] [--explain ARTIFACT] [--json]
talaria diff      skills [NAME] | config | checkout   [--json] [--side-by-side]
talaria deps      [--target-os linux|macos|windows|termux]... [--live] [--json]
talaria select    [--preset NAME] [--intent replace|clone] [--include GLOB]...
                  [--exclude GLOB]... [--set artifact=on|off] [--save selection.json]
talaria pack      -o out.hermespack [--selection FILE | --preset NAME] [--intent ...]
                  [--vault [--vault-passphrase-file F]] [--profile NAME]...
                  [--comment TEXT] [--allow-live|--wait-lock] [--json] [--progress ndjson]
talaria inspect   BUNDLE [--verify] [--list] [--cat MEMBER] [--extract GLOB -o DIR]
                  [--deps --target-os X] [--checklist] [--json]
talaria preflight BUNDLE [--home PATH] [--json]        # live target checks, doctor-style
talaria plan      BUNDLE [--map-home P] [--map-user U] [--target-profile M]
                  [--out plan.json] [--json]           # rewrite plan generation/edit
talaria apply     BUNDLE [--dry-run] [--plan plan.json] [--conflict keep|overwrite|rename|ask]
                  [--only GROUP]... [--skip GROUP]... [--unlock-vault]
                  [--yes] [--json] [--progress ndjson]
talaria verify    [--home PATH] [--last | --report FILE] [--json]   # post-apply re-hash + checks
talaria report    [--last] [--format md|html|json] [-o FILE]
talaria checklist BUNDLE|--home PATH [-o FILE]         # Secrets Handoff Checklist
talaria genskill  [-o DIR]                             # observation skill for the agent (§13)
talaria presets   list|show|save|delete NAME
talaria gui       [--port N] [--no-browser]
```

Conventions: global `--home`, `--config FILE`, `--quiet/--verbose`, `--no-color`,
`--non-interactive` (never prompts; missing decisions = error 3). `--json` outputs a single
schema-versioned document; `--progress ndjson` streams event records — **the GUI consumes the
identical event stream from the same job engine** (one engine, two frontends; competitor W14/W15
answer). Exit codes: 0 ok · 1 error · 2 verification failed · 3 blocked by preflight/needs
decision · 4 user abort · 5 completed-with-warnings. Apply-time re-narrowing: the bundle carries
the captured superset + selection record; `apply --only/--skip` narrows further without repacking
(the bundle is a menu, not a fait accompli).

## 11. Config file — repeatable migrations (P1)

Format: **JSON, not TOML** — `tomllib` is 3.11+ and the core must run on 3.9 (constraint 2), and
selection records/plans are already JSON. `talaria.json` (cwd, then `~/.config/talaria/`):

```json
{ "schema": 1,
  "jobs": { "weekly-vps": {
      "home": "~/.hermes", "preset": "everything-portable", "intent": "replace",
      "profiles": ["default", "coder"],
      "overrides": { "cron/executions.db": "on" },
      "output": "~/backups/hermes-{date}.hermespack", "vault": false } } }
```

`talaria pack --config talaria.json --job weekly-vps` → scriptable cron-able migrations for the
"$5 VPS" population (competitor W15). Saved custom presets live here too. Post-run hooks (P2)
run only with explicit `"allow_hooks": true` per job.

## 12. Expert toggles worth having (each with citation-backed default)

| Toggle | Default | Rationale | Pri |
|---|---|---|---|
| Copy WhatsApp session | OFF | device-slot fight; research endorses opt-in with loud warning (integrations §1.2) | P0 |
| Copy Matrix store+crypto.db | OFF | valid only if source stops (integrations §1.2) | P1 |
| Copy chrome-debug profile (same-OS only) | OFF | OS-keyring encryption (integrations §5) | P1 |
| Copy signal-cli store | OFF | single-device; outside home (integrations §1.2) | P1 |
| `monitoring.install_id` keep/rotate | keep (replace) / rotate (clone) | integrations §6 | P0 |
| dashboard `basic_auth.secret` keep/rotate | keep | rotating logs everyone out (integrations §4) | P1 |
| Carry `executions.db` / logs / traces | OFF | audit-only value (cron §3.2) | P1 |
| Rewrite `state.db` cwd columns | OFF | historical; report dangling instead (state-layout §2.3) | P1 |
| Integrity-check size cap | 2 GiB | upstream's own cap; 30 GB DBs exist (state-layout §2.3) | P1 |
| Replay checkout dirty patch on target | ON if patch exists | autostash on next `hermes update` otherwise (install-update §3) | P0 |
| Pin Camoufox user_id on target | ON | silent login loss otherwise (integrations §5) | P0 |
| Pack while gateway live | honor `.backup.lock`, snapshot DBs | backup-precedent "Do not fight their lock" | P0 |
| History trimming (sessions before date X) | OFF | size control for 30 GB DBs; sqlite-level export | P2 |
| Custom regex rewrite rules | OFF, preview-mandatory | competitor W7 cautionary tale | P1 |

Not toggles (invariants): transactional apply + rollback; read-only capture; both-sides
machine-bound filtering; sqlite3.backup() snapshots; 0600 secret restoration; symlink
non-following; zip-slip containment; no venv/node cross-machine copy (install-update §9 traps).

## 13. Usage discovery — the "what does it actually touch" answer (P0/P1)

Layered, trust-ranked evidence; each layer feeds the same reference-chasing scanner pass:
1. **Static references (P0, trusted)**: config paths, cron scripts/workdirs, external skill dirs,
   MCP cwd/args, kanban/projects paths — parsed structurally.
2. **Recorded behavior (P0, trusted)**: `state.db` cwd enumeration (upstream ships the enumerator
   — state-layout §2.3), `.usage.json` skill telemetry, cron `output/`, hub audit.log.
3. **Venv enrichment (P0, trusted)**: shell out to the source install's venv for
   `active_features()`, `DEFAULT_CONFIG`, `list_user_modified_bundled_skills()` when present;
   degrade gracefully when absent (constraint 2).
4. **Agent self-report (P1, untrusted)**: `talaria genskill` emits an observation skill/prompt the
   user hands to their Hermes agent ("list projects, repos, external dirs, services you use").
   Every agent-reported path is **corroborated on disk by the scanner before entering the
   inventory**, tagged `agent-reported+verified`; unverifiable claims go to the report's "agent
   mentioned, not found" appendix. This honors the owner's distrust of self-reports while
   harvesting their recall.

## 14. GUI screen inventory (P0 skeleton, P1 polish)

Wizard spine: Detect → Intent → Inventory (selection tree) → Review (diffs · deps matrix ·
secrets checklist · rewrite plan preview) → Pack (progress + report). Apply side: Open bundle →
Inspect → Preflight → Plan (rewrites/conflicts) → Dry-run → Apply → Verify → Report + Post-restore
checklist. Every screen has an "export JSON" affordance; background job engine streams progress
(no frozen UI — competitor W14). The post-restore checklist is generated from findings: re-pair
WhatsApp, `hermes mcp reauth --all`, `hermes gateway install`, `hermes gateway enroll`,
`hermes dashboard register`, npm install bridge, `hermes doctor` (integrations §8; digest §5.6).

## 15. Priority rollup

- **P0 (ship-blocking)**: full taxonomy scanner (all 20 families, both layout generations, legacy
  dual dirs, unrecognized bucket); provenance engine; tri-state selection tree + coupling rules +
  presets + intent switch; secrets checklist (+vault when `cryptography` present); pack/apply
  transactional with dry-run; rewrite plan with preview (CLI); dependency engine + live preflight
  + predictive per-OS verdicts (CLI table); bundle inspector core (list/verify/cat/manifest/
  checklist); per-profile capture; version-skew + `_config_version` gates; post-restore checklist;
  full CLI with `--json` everywhere; GUI wizard skeleton with tree, deps list, progress.
- **P1**: GUI diff viewer side-by-side + full matrix grid + rewrite plan editor; profile mapping;
  diff-against-install; degraded `hermes backup` zip ingestion; config-file jobs + saved presets;
  genskill observation loop; expert toggles marked P1 above.
- **P2**: bundle-vs-bundle compare; history trimming; post-run hooks; delta/incremental bundles;
  bundle signing; TUI frontend.

## 16. Constraint challenges

**None.** All eight constraints survive contact with the research. Two consequences to lock in
(not challenges): (1) config files and all records are JSON because 3.9 lacks `tomllib`
(constraint 2); (2) zip64 must be enabled and packing must stream — real 30 GB `state.db`
instances exist (state-layout §2.3), so constraint 5's one-file bundle implies never buffering
members in memory and hashing on the fly.

## 17. Name

Keep **Talaria**. It is distinctive, thematic (the sandals that move Hermes), short, and
`talaria` is an unclaimed, typo-resistant command name. No better candidate found; renaming
energy is better spent on the taxonomy.
