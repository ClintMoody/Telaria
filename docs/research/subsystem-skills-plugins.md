# Subsystem Report: Skills & Plugins (Migration/Diffing Reference)

All paths repo-relative to `hermes-agent` (HEAD `cb47f59ff`, `pyproject.toml:5` version `0.20.1`,
tags `v2026.8.13` etc.).

## TL;DR for the migration tool

The single most important fact: **the repo's `skills/` directory is a seed, not a runtime path.**
The agent reads **only** `$HERMES_HOME/skills/` (default `~/.hermes/skills/`) plus configured
`skills.external_dirs`. There is **no overlay** — repo skills are *copied* into the state dir once
and then diverge.

Stock-vs-modified is already solved in-tree by `~/.hermes/skills/.bundled_manifest` (`name:md5`
per line). Reuse it — do not invent a new hash scheme.

## 1. Skill anatomy

### Directory shape

Documented in `tools/skills_tool.py:14-27`. A skill is a directory containing:

| Path | Required | Notes |
|---|---|---|
| `SKILL.md` | **yes** | The only marker of "this dir is a skill" |
| `references/` | no | Progressive-disclosure docs |
| `templates/` | no | |
| `assets/` | no | agentskills.io standard |
| `scripts/` | no | Executable helpers (`.py`, `.sh`) |
| `tests/` | no | e.g. `skills/productivity/docx/tests/test_docx_skill.py` |
| `LICENSE` | no | |
| `.skillignore` / `.clawhubignore` | no | Excludes paths from the security scanner — `tools/skills_guard.py:1046` |

Categories are *plain parent directories* with optional `DESCRIPTION.md`. Category = first path
segment under the skills root (`tools/skills_tool.py:566-576`).

**Critical for a packager:** `references/`, `templates/`, `assets/`, `scripts/` are *support
dirs*. A `SKILL.md` nested inside one of them is **data, not a skill** — `agent/skill_utils.py:50`
(`SKILL_SUPPORT_DIRS`) and `:122-148` (`is_skill_support_path`). The curator legitimately archives
whole old skill packages under `references/`, so a naive `rglob("SKILL.md")` over-counts. Also
prune `agent/skill_utils.py:27-44` (`EXCLUDED_SKILL_DIRS`: `.git`, `.hub`, `.archive`, `.venv`,
`node_modules`, `site-packages`, `__pycache__`, caches).

Counts at HEAD: 82 `SKILL.md` under `skills/`, 115 under `optional-skills/`, 485 files under `skills/`.

### Frontmatter parsing

`agent/skill_utils.py:174-220` (`parse_frontmatter`). YAML via CSafeLoader, with a **naive
`key: value` fallback on YAML parse failure** (:212-218) — a malformed skill silently yields a
degraded flat dict. Leading UTF-8 BOM stripped (:193-195) — real Windows bug class.

### Complete frontmatter field inventory (from all 197 shipped SKILL.md files)

**Top-level:**

| Field | Count | Meaning / consumer |
|---|---|---|
| `name` | 197 | Skill identity. **Manifest key, not the directory name** — `tools/skills_sync.py:199-218`. Max 64 chars (`tools/skills_tool.py:31`). |
| `description` | 197 | Max 1024 chars; **truncated to 60 in system prompt** (`agent/skill_utils.py:849`); agent-authored skills rejected over 60 (`tools/skill_manager_tool.py:1608-1614`). |
| `version` | 197 | Semver string. **Advisory only** — updates are hash-driven. |
| `author` | 197 | Free string/mapping. |
| `license` | 197 | Advisory. |
| `platforms` | 197 | **Hard gate.** `[macos, linux, windows]` → `sys.platform` via `PLATFORM_MAP` (`agent/skill_utils.py:21-25`). Termux accepts `linux` (:243-247). Absent = all. |
| `metadata` | 191 | Only `metadata.hermes.*` read. |
| `dependencies` | 42 | Pip names. **Documentation-only — no code reads it.** |
| `prerequisites` | 28 | See below. |
| `tags` | 7 | Top-level variant. |
| `triggers` | 4 | Advisory. |
| `required_environment_variables` | 3 | **Enforced.** See below. |
| `category` | 3 | Advisory (path is authoritative). |
| `title` | 2 | Advisory. |
| `environments` | 2 | Offer-time filter `[kanban|docker|s6]` (`agent/skill_utils.py:351-387`); unknown tags fail open. |
| `setup` | 2 | `{help, collect_secrets:[{env_var,prompt,provider_url}]}` — folded into required env vars (`tools/skills_tool.py:392-399`). |
| `toolsets` | 2 | Advisory. |
| `required_credential_files` | 1 | |
| `compatibility` | 1 | agentskills.io free text. |
| `requires` | 1 | |
| `authors` | 1 | Plural variant. |

**`metadata.hermes.*`:** `tags` (191), `related_skills` (120), `category` (40), `homepage` (24),
`requires_toolsets` (10, **conditional activation** — `agent/skill_utils.py:681-695`),
`fallback_for_toolsets` (2), plus one-offs. Extractor also reads `fallback_for_tools`/`requires_tools`.

**`prerequisites.*`** (`tools/skills_tool.py:313-323`): `commands` (25, **advisory only** — :38),
`env_vars` (7, legacy — normalized into `required_environment_variables` at :403-405), `pip` (1, advisory).

**`required_environment_variables[]`** — the only genuinely enforced dependency mechanism
(`tools/skills_tool.py:340-405`). Entries: `name`/`env_var`, `prompt`, `help`/`provider_url`/`url`,
`required_for`, `optional` (excluded from gate at :520-522). Resolution: `~/.hermes/.env` first,
then `os.environ` (:500-505). Missing → `SkillReadinessStatus.SETUP_NEEDED`;
`tools/env_passthrough.py:3-12` auto-registers for subprocess passthrough.

**Also:** `metadata.hermes.config[]` — `{key, description, default, prompt}` declaring config.yaml
settings stored under `skills.config.<key>` (`agent/skill_utils.py:701-757, 802`;
`discover_all_skill_config_vars()` :760). **Values live in config.yaml, not with the skill.**

**Not declarable:** MCP dependencies (prose only; portable Agent Plugins declare MCP structurally —
`hermes_cli/agent_plugins.py:21` MCP_SCHEMA_V1).

## 2. WHERE skills live at runtime

- **Bundled (stock) source:** `<repo>/skills/` via `get_bundled_skills_dir()` —
  `hermes_constants.py:243-256`. Override `$HERMES_BUNDLED_SKILLS`.
- **Runtime (active):** `get_skills_dir()` = `get_hermes_home()/"skills"` (`hermes_constants.py:1314-1316`).
- `get_hermes_home()` (`hermes_constants.py:114-138`): context override → `$HERMES_HOME` →
  `~/.hermes` POSIX / `%LOCALAPPDATA%\hermes` Windows. **Profiles** at `<root>/profiles/<name>`
  (:171-207) — each with its own complete `skills/` tree.

### There is NO overlay

`get_all_skills_dirs()` (`agent/skill_utils.py:582-590`) = `[get_skills_dir()] + external_dirs`.
Repo dir absent. Discovery (`tools/skills_tool.py:673-780`) walks exactly these; name collisions
**first-wins, silent** (:741-742). **Shipping the repo alone restores nothing** — carry
`~/.hermes/skills/`.

### Seeding: repo → state dir

`tools/skills_sync.py::sync_skills()` (:675). Invoked from setup-hermes.sh:407,
`hermes_cli/main.py:936-938, 2542-2544` (update), `hermes_cli/setup.py:3329-3333`,
`gateway/run.py:29303-29304`, per-profile via `hermes_cli/profiles.py:1244-1251`. Destination
preserves category structure (`_compute_relative_dest` :245-252). `setup-hermes.sh:411-412` has a
raw `cp -rn` fallback that can copy `skills/index-cache/` into the state dir — treat as junk.

### WHERE the agent writes improved/created skills

**In place, in the state dir.** `tools/skill_manager_tool.py:638-660`. `skill_manage(patch|edit|
write_file)` **overwrites the seeded copy**. The only divergence record is the `.bundled_manifest`
hash mismatch. External dirs are read-only to autonomous maintenance (`agent/skill_utils.py:658-675`,
`tools/skill_usage.py:448-453`).

### Full `~/.hermes/skills/` metadata inventory

| Path | Written by | Purpose |
|---|---|---|
| `<category>/<skill>/` | sync + agent | The skills |
| `.bundled_manifest` | `tools/skills_sync.py:166` | **`name:md5` stock baseline — the diffing key** |
| `.usage.json` | `tools/skill_usage.py:85` | Curator telemetry + provenance |
| `.usage.json.lock` | `tools/skill_usage.py:90` | Lockfile — do **not** migrate |
| `.curator_suppressed` | `tools/skill_usage.py:271` | Curator-pruned built-ins; blocks re-seeding (`tools/skills_sync.py:726-732`) |
| `.archive/<skill>/` | `tools/skill_usage.py:126` | Curator-archived skills, flat layout, recoverable |
| `.curator_backups/<utc-iso>/skills.tar.gz` | `agent/curator_backup.py:5` | Pre-run rollback tarballs (keep 5) |
| `.restore-backups/official-optional-<ts>/` | `tools/skills_sync.py:364` | repair-official backups |
| `.hub/lock.json` | `tools/skills_hub.py:79` | **Hub install provenance** |
| `.hub/taps.json` | `tools/skills_hub.py:93` | Custom GitHub sources |
| `.hub/audit.log` | `tools/skills_hub.py:88` | Install audit trail |
| `.hub/quarantine/` | `tools/skills_hub.py:83` | Pre-scan staging — regeneratable |
| `.hub/index-cache/*.json` | `tools/skills_hub.py:97` | Remote catalog cache, 1h TTL — regeneratable |
| `.hub/.ignore` | `tools/skills_hub.py:3644-3650` | ripgrep guard for unvetted text |
| `_org/.active_org` | `tools/skills_sync_client.py:1996` | Org marker |
| `_org/<id>/.org-provenance.json` | `:2008` | Org HEAD provenance |
| `_org/<id>/.org-baseline.json` | `:1949` | **Per-skill upstream fingerprints (org equivalent of .bundled_manifest)** |
| `.sync_state` (legacy `.sync_manifest`) | `:947,951` | `{head, skills:{name:{tree,commit}}}` |
| `.sync_device_id` | `:686` | Device label — **regenerate per-machine, don't copy** |
| `<skill>.bak` | `tools/skills_sync.py:873` | Transient update backup; orphan-recovered :461-471 |

Adjacent: `$HERMES_HOME/skill-bundles/*.yaml` (slash-command bundles, `agent/skill_bundles.py:10-24,75`;
bundles win over same-named skills :26-31); `$HERMES_HOME/plugin-data/<ns>/state.json`;
`$HERMES_HOME/.no-bundled-skills`; config.yaml `skills.disabled` / `skills.platform_disabled` /
`skills.external_dirs` / `skills.config.*` / `plugins.*`.

## 3. `skills/index-cache` — two unrelated things

**(a) `<repo>/skills/index-cache/*.json` — checked-in, DEPRECATED, runtime-irrelevant.** Snapshots
of remote third-party catalogs. Only consumer: website build legacy fallback
(`website/scripts/extract-skills.py:16,34,103,446,631`). **Ignore entirely.**

**(b) `~/.hermes/skills/.hub/index-cache/*.json` — runtime, ephemeral.** 1h-TTL hub search cache
(`tools/skills_hub.py:54,97-99,1153,3632,3639,3826`). **Safe to drop.**

**(c) Real published catalog:** `website/static/api/skills-index.json` via
`scripts/build_skills_index.py` (INDEX_VERSION 1). Not local state.

**No local installed-skills index file exists.** System-prompt index built live per scan; in-process
cache 30s TTL (`tools/skills_tool.py:100-120`). **Nothing to regenerate after migration.**

## 4. optional-skills — enablement

`optional-skills/` (115 skills, 22 categories) ships in repo, **never seeded**
(`tools/skills_hub.py:3272-3280`). Resolved by `get_optional_skills_dir()`
(`hermes_constants.py:213-224`, `$HERMES_OPTIONAL_SKILLS`).

Enable via Skills Hub: `hermes skills install official/<category>/<skill>`
(`hermes_cli/subcommands/skills.py:87-116`); source falls back to live GitHub for newer skills
(`tools/skills_hub.py:3321-3341`).

**Recorded in `~/.hermes/skills/.hub/lock.json`** (`HubLockFile.record_install`,
`tools/skills_hub.py:3696-3728`): `{version:1, installed:{<name>:{source, identifier, trust_level,
scan_verdict, content_hash: "sha256:<16hex>", install_path, files[], metadata{}, scan_provenance{},
installed_at, updated_at}}}`. `install_path` shape-validated (:234-257; rmtree-escape fix).

Files copied into `~/.hermes/skills/<category>/<skill>/` — **installed optional skill is
location-indistinguishable from bundled**; only lock.json vs .bundled_manifest membership
differentiates (`tools/skill_usage.py:427-446`).

**Provenance backfill:** `_backfill_optional_provenance()` (`tools/skills_sync.py:455-565`, run on
every sync :936): byte-identical active skill absent from lock.json gets retroactive entry
(`scan_verdict: "backfilled"`). Modified one does NOT (`_dir_hash` mismatch :571) — orphan with no
provenance. **Carry lock.json.**

Disabling (orthogonal): config `skills.disabled[]`, `skills.platform_disabled{}` — read
`agent/skill_utils.py:436-471` (global ∪ platform).

## 5. Stock identification — authoritative mechanism

### `.bundled_manifest` (v2)

Format `<frontmatter-name>:<md5>` per line. Docs `tools/skills_sync.py:9-21`; read :113-137;
written atomically :166-196. Hash = `_dir_hash()` (:254-265):

```python
hasher = hashlib.md5()
for fpath in sorted(directory.rglob("*")):
    if fpath.is_file():
        hasher.update(str(fpath.relative_to(directory)).encode("utf-8"))
        hasher.update(fpath.read_bytes())
```

**Semantics:** MD5 of the *bundled* skill **as of last seed** — an origin/baseline hash.

### Three-way comparison (`sync_skills()` :823-916; doc :14-21)

| State | Condition | Action |
|---|---|---|
| No update | bundled == origin | skip without hashing user copy (:838-841) |
| **User-modified** | origin != "" and user != origin | **SKIP — never overwrite** (:862-867) |
| Safe update | user == origin and bundled != origin | move→`.bak`, copytree, rebaseline (:869-891) |
| User-deleted | in manifest, absent on disk | respected (:914-916) |
| Removed upstream | in manifest, gone from repo | manifest cleaned (:918-921) |

Predicate `_is_tracked_user_modification` (:1099-1108); v1 hashless entries not tracked.

### Ready-made APIs — use, don't reimplement

- **`list_user_modified_bundled_skills()`** (`tools/skills_sync.py:1111-1145`) →
  `[{"name","dest","bundled_src"}]`.
- **`diff_bundled_skill(name)`** (:1167-1252) → unified diff per file, status
  modified/added/removed/binary (NUL detection :1148-1165).
- CLI: `hermes skills list-modified [--json]`, `hermes skills diff <name>`
  (`hermes_cli/subcommands/skills.py:182-207`), `hermes skills reset <name> [--restore]` (:158-180).

### Second hash scheme (hub) — don't mix

`content_hash()` (`tools/skills_guard.py:867-878`) = `sha256:<16hex>`; `_content_digest` (:699-723)
sorts by **POSIX rel-path strings** (issue #62310: Windows Path-sort made every hub skill report
update_available forever). Three incompatible digests coexist: MD5 dir-hash (.bundled_manifest),
SHA-256/16 (lock.json), org fingerprints (`tools/skills_sync_client.py:1915`).

### Reconstructing "stock at version X"

No shipped stock-hash manifest; skills-index.json has no hashes. Best options:
1. **Carry `.bundled_manifest` in the bundle** — it IS the baseline; no network needed.
2. **Git tag checkout** (`git checkout <tag> -- skills/`), recompute `_dir_hash`. Tags are
   date-versioned; ≠ pyproject `0.20.1`.
3. **Docker:** `<project_root>/.hermes_build_sha` = 40-char build commit
   (`hermes_cli/build_info.py:33-51`).
4. **Org skills:** `_org/<id>/.org-baseline.json`; `org_skill_is_locally_modified()`
   (`tools/skills_sync_client.py:1958-1969`) — **fails open when no baseline** (:1966-1968).

### Provenance classification (`.usage.json`)

Schema (`tools/skill_usage.py:644-659`): `{created_by: null|"agent"|"installed", use_count,
view_count, last_used_at, last_viewed_at, patch_count, patch_generation,
last_reused_patch_generation, last_patched_at, created_at, state: active|stale|archived, pinned,
archived_at}`.

Helpers (:427-446): `is_bundled` (in .bundled_manifest), `is_hub_installed` (in lock.json),
`is_agent_created` (neither). `created_by=="agent"` set **only** in background self-improvement
fork (`tools/skill_manager_tool.py:1621-1631`; `tools/skill_provenance.py:75-78`); foreground
user-directed creation leaves null (curator never auto-curates user work).

**Lose `.usage.json` → agent-authored indistinguishable from hand-written; curation freezes**
(`list_agent_created_skill_names` :338-390 returns empty).

`PROTECTED_BUILTIN_SKILLS = {"plan"}` (:64-68).

## 6. Skill dependencies — enforcement summary

| Kind | Declared as | Enforced? |
|---|---|---|
| Env vars/secrets | `required_environment_variables[]`, legacy `prerequisites.env_vars`, `setup.collect_secrets` | **Yes** — readiness gate (`tools/skills_tool.py:340-530`) |
| Binaries | `prerequisites.commands` | No — advisory (:38) |
| Python packages | `dependencies[]`, `prerequisites.pip` | No — zero readers |
| OS | `platforms[]` | **Yes** — hard gate |
| Runtime env | `environments[]` | Offer-time filter |
| Toolsets | `metadata.hermes.{requires,fallback_for}_*` | Conditional activation |
| Config keys | `metadata.hermes.config[]` | Values in config.yaml `skills.config.*` |
| MCPs | not declarable for skills | — |

**Takeaway:** only env vars are machine-checkable and their values live in `~/.hermes/.env`.
Binaries/pip are prose → target-side reconciliation report.

## 7. Plugins

### Model (`hermes_cli/plugins.py:5-32`) — four sources, later wins:

1. `<repo>/plugins/<name>/` bundled (`get_bundled_plugins_dir()` :76-86, `$HERMES_BUNDLED_PLUGINS`;
   memory/ and context_engine/ excluded — own discovery)
2. `~/.hermes/plugins/<name>/` — **user**
3. `./.hermes/plugins/<name>/` — project (needs `HERMES_ENABLE_PROJECT_PLUGINS`)
4. pip entry-point group `hermes_agent.plugins` (:407-472)

Needs `plugin.yaml` + `__init__.py::register(ctx)`; portable "Agent Plugins v1" validated
declaratively, no import (`hermes_cli/agent_plugins.py:1-8`).

Bundled plugins: browser, context_engine, cron_providers, dashboard_auth, disk-cleanup,
google_meet, hermes-achievements, image_gen, kanban, memory, model-providers, observability,
platforms, security-guidance, spotify, teams_pipeline, video_gen, web.

### Manifest (`PluginManifest` :1028-1105)

`name, version, description, author, requires_env[], provides_tools[], provides_hooks[], source,
path, kind, key, portable, skill_namespace, capabilities[]` + v2 `manifest_version, api_version,
requires_plugins[], python_dependencies[], config_schema{}, license, homepage, tags[], emits[],
listens[]`. `kind` ∈ standalone|backend|exclusive|platform|model-provider (:622, :1043-1056).
Bundled backend/platform auto-load; user-installed gated by `plugins.enabled`. `key` is
path-derived (`image_gen/openai` :1058-1062). `python_dependencies` **never auto-installed**
(:1087-1089).

### Enablement — config.yaml

```yaml
plugins:
  enabled: [disk-cleanup, image_gen/openai]   # allow-list; None vs [] tri-state matters (:586-614)
  disabled: [...]                              # deny-list wins (:569-584)
  entries:
    <plugin_id>: {settings{}, granted_capabilities[], allow_tool_override,
                  allow_platform_actions, mcp_allowlist[], llm{}}
```

`migrate_config` grandfathers installed user plugins on upgrade (:596-600). Capability grants live
only in `entries.<id>.granted_capabilities` (:1069-1073).

### Plugin-owned state

**`$HERMES_HOME/plugin-data/<namespace>/state.json`** (`PluginState.data_dir` :1325-1332).
Namespace = `agent-plugin-<slug>-<sha256[:8]>` (`_plugin_data_namespace` :1258-1271,
`_portable_skill_namespace` :623-635) — **not human-guessable; map via the same function.**
Atomic + locked writes (:1280-1315), byte quota (:1362-1366), mode 0600. `${PLUGIN_DATA}` for
portable plugins (:4729, :4134).

Plugins can register skills **in-memory only** (:3353-3374, `_plugin_skills` :3411, cleared on
reload :3714) — nothing to migrate. Portable plugins register MCP servers as
`<skill_namespace>__<server_name>` (:4755).

Elsewhere: `plugins/memory/` providers (byterover, hindsight, holographic, honcho, mem0,
openviking, retaindb, supermemory; selected by `memory.provider`; state often remote);
kanban board = `$HERMES_HOME/kanban.db` (`tools/skills_sync.py:963-966` rmtree guard mention);
chronos cron state = `$HH/cron/*`.

## 8. Other migration-relevant facts

- **`hermes_cli/backup.py`** exclusions + `.archive` inclusion + root-level-only `hermes-agent`
  special-case (:40-43, :306, :631). `_QUICK_STATE_FILES` (:1100+): state.db, config.yaml, .env,
  auth.json, cron/jobs.json, cron/executions.db, gateway_state.json, channel_directory.json,
  channel_aliases.json… — quick snapshot deliberately excludes skills. See also
  `hermes_state_portability.py` (714 lines) for state-db portability.
- **`hermes skills snapshot` is NOT a skill backup** (`hermes_cli/skills_hub.py:1634-1671`):
  exports hub identifiers + taps only; hermes_version hardcoded "0.1.0" (:1646); import
  re-downloads (needs network, non-deterministic). Supplementary provenance only.
- **Index CI** (skills-index.yml twice daily; freshness watchdog every 4h) — remote only; no
  post-migration regeneration required.
- **Curator will bite:** `curator.prune_builtins` default **True**
  (`hermes_cli/config_defaults.py:1978-1990`), archive_after_days 90. **Restore skills without
  `.curator_suppressed` → pruned built-ins resurrect on next sync; restore the marker without
  `.archive/` files → those skills permanently absent.** Config: stale 30d, archive 90d, interval
  168h, min_idle 2h, backups keep 5.
- **Rename recovery** (`_recover_renamed_skill` `tools/skills_sync.py:609-673`): relocates only
  byte-identical copies; modified copies stay put ("will not receive updates"). Version-skewed
  restores can surface duplicate-name collisions — discovery is silent first-wins.
- **External-dirs shadowing:** sync defers to external dirs; deletes local shadow only if
  byte-identical (issue #28126; :775-812).
- **Safety guard worth mirroring:** `_rmtree_writable()` (:951-999) refuses deletes outside strict
  children of the skills root (issue #48200 — an incident wiped `~/.hermes`). Copy this guard.

## Recommended capture set

**Must carry (irreplaceable):**
```
$HERMES_HOME/skills/**                    (incl. .archive/; excl. .hub/quarantine,
                                           .hub/index-cache, .curator_backups, *.bak)
$HERMES_HOME/skills/.bundled_manifest     ← stock baseline
$HERMES_HOME/skills/.usage.json           ← agent-vs-user provenance
$HERMES_HOME/skills/.curator_suppressed
$HERMES_HOME/skills/.hub/{lock.json,taps.json,audit.log}
$HERMES_HOME/skills/_org/**               (if org sync)
$HERMES_HOME/skills/.sync_state
$HERMES_HOME/skill-bundles/*.yaml
$HERMES_HOME/plugin-data/**
$HERMES_HOME/plugins/**                   (user plugins)
$HERMES_HOME/config.yaml                  (skills.*, plugins.*)
$HERMES_HOME/.env                         (skill-required env vars)
$HERMES_HOME/.no-bundled-skills           (if present)
```

**Drop:** `.hub/index-cache/`, `.hub/quarantine/`, `.usage.json.lock`, `*.bak`, `__pycache__`,
`.venv`, `node_modules`, `<repo>/skills/index-cache/`.

**Regenerate per-machine:** `.sync_device_id`.

**Record in bundle:** git tag / `.hermes_build_sha` / pyproject version of source install.

**Diff strategy:** prefer calling `tools.skills_sync.list_user_modified_bundled_skills()` /
`diff_bundled_skill(name)` semantics (or reimplement bit-exactly: empty-hash v1 entries, hub-owned
paths, support-dir exclusion).
