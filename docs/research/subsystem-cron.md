# Subsystem Report: Cron / Scheduling (Migration Analysis)

All paths are repo-relative to the `hermes-agent` checkout. `$HH` = the **active profile's**
`HERMES_HOME` (default `~/.hermes`; profile `coder` = `~/.hermes/profiles/coder`).

## 1. On-Disk Persistence

### 1.1 The store is **per-profile**, not global

`cron/jobs.py:68-85`:

```python
HERMES_DIR = get_hermes_home().resolve()   # jobs.py:80  — ACTIVE PROFILE home
CRON_DIR   = HERMES_DIR / "cron"           # jobs.py:84
JOBS_FILE  = CRON_DIR / "jobs.json"        # jobs.py:85
```

The comment at `cron/jobs.py:68-79` warns that anchoring at the shared root instead of the profile
home "leaks config/credentials/skills across profiles". **A migration tool must walk every profile**
(`$HH/profiles/*/cron/`), not just the root.

### 1.2 Complete file inventory under `$HH/cron/`

| Path | Format | Written by | Migrate? |
|---|---|---|---|
| `cron/jobs.json` | JSON `{"jobs":[...], "updated_at": ISO}` | `cron/jobs.py:1293-1298` | **YES — the core artifact** |
| `cron/executions.db` | SQLite (WAL) | `cron/executions.py:20,40-62` | Optional (audit only) |
| `cron/notepad.db` | SQLite (WAL) | `cron/notepad.py:34,52-60` | **YES — job state** |
| `cron/suggestions.json` | JSON | `cron/suggestions.py:49,93-112` | **YES — holds dismissal latches** |
| `cron/output/<job_id>/<ts>.md` | Markdown | `cron/jobs.py:3067-3095` | Recommended (`context_from` reads these) |
| `cron/output/<job_id>/monitor_last_output.txt` | Text | `cron/monitor.py:51,102-108` | **YES — or monitors re-alert** |
| `cron/ticker_heartbeat` | epoch float text | `cron/jobs.py:91,886-895` | **NO — machine liveness** |
| `cron/ticker_last_success` | epoch float text | `cron/jobs.py:94` | **NO** |
| `cron/usage_audit.jsonl` | JSONL | `cron/scheduler.py:1088-1112` | Optional |
| `cron/inflight_forced_releases.jsonl` | JSONL | `cron/scheduler.py:716` | **NO — process diagnostics** |
| `cron/.jobs.lock`, `cron/.tick.lock` | flock files | `cron/jobs.py:265-311`, `scheduler.py:1163-1167` | **NO** |
| `cron/.jobs_*.tmp`, `.hb_*`, `.output_*` | transient mkstemp | various | **NO** |
| `$HH/cron.pid` | pid | — | **NO** (in `hermes_cli/backup.py:95,126` exclusions) |
| `$HH/scripts/` | user job scripts | — | **YES — hard dependency, see §5** |

Counter/error-marker files also written into `CRON_DIR` by `record_catch_up_occurrence`
(`cron/jobs.py:977`), `record_ticker_error` (`:990`), `clear_ticker_error` (`:1034`) — machine-local
liveness, skip. Both `executions.db` and `notepad.db` run in WAL mode (`cron/executions.py:37`,
`cron/notepad.py:51`) — snapshot via `sqlite3.backup()` or ship WAL+SHM consistently.

### 1.3 Full job-record schema

Authoritative source: the literal built in `create_job` at **`cron/jobs.py:1737-1785`**.

```jsonc
{
  "id":                "a1b2c3d4e5f6",   // uuid4().hex[:12]. IMMUTABLE (jobs.py:378);
                                          // filesystem path component, traversal-validated (:381-394)
  "name":              "Daily briefing",  // defaults to prompt[:50]
  "prompt":            "...",             // "" for no_agent jobs
  "skills":            ["google-workspace"],   // canonical list
  "skill":             "google-workspace",     // LEGACY mirror = skills[0] (jobs.py:414-420)
  "model":             null,              // per-job pin, or null = follow global
  "provider":          null,              // per-job pin
  "provider_snapshot": "openai",          // drift guard, computed jobs.py:1484-1526
  "model_snapshot":    "gpt-5",           // null when pinned / no_agent / resolution failed
  "base_url":          null,              // trailing slash stripped (jobs.py:1670)
  "script":            "watch_feed.sh",   // relative to $HH/scripts/ — see §5
  "no_agent":          false,             // true => script IS the job, no LLM
  "monitor_script":    null,              // mutually exclusive with monitor_url
  "monitor_url":       null,              // http(s) only
  "monitor_state":     null,              // {"last_output_hash": sha256, "last_changed_at": ISO}
  "context_from":      ["<job_id>", ...], // reads OTHER jobs' output dirs
  "schedule": {                            // parse_schedule(), jobs.py:612-709
     "kind": "cron"|"interval"|"once",
     "expr": "0 9 * * *",                 // kind=cron
     "minutes": 30,                       // kind=interval
     "run_at": "2026-08-15T14:00:00+05:30",// kind=once (TZ-AWARE, see §6)
     "display": "0 9 * * *"
  },
  "schedule_display":  "0 9 * * *",
  "repeat":  { "times": 1|null, "completed": 0 },  // null = forever
  "enabled":           true,               // the SCHEDULER-honoured flag
  "state":             "scheduled",        // scheduled|paused|completed|error
  "paused_at":         null,
  "paused_reason":     null,
  "created_at":        "ISO",
  "next_run_at":       "ISO"|null,
  "last_run_at":       "ISO"|null,
  "last_status":       "ok"|"error"|"blocked_config"|null,
  "last_error":        null,
  "last_delivery_error": null,
  "deliver":           "origin",           // see §4.4
  "origin":            {"platform":"telegram","chat_id":"-100…","thread_id":"17"},
  "enabled_toolsets":  ["web","file"]|null,
  "workdir":           "/abs/path"|null,   // ABSOLUTE ONLY (jobs.py:1398-1428)
  "attach_to_session": true                // only present when explicitly set (jobs.py:1784-1785)
}
```

**Runtime-added fields present on live installs:**

| Field | Written at | Meaning | Migrate? |
|---|---|---|---|
| `run_claim` | `cron/jobs.py:2996-3003` | `{"at": ISO, "by": _machine_id()}` in-flight lock | **STRIP** |
| `fire_claim` | `cron/jobs.py:2523` | external-provider CAS | **STRIP** |
| `preflight_alerted` | `cron/jobs.py:2102-2114` | alert-once dedup bit | Strip |
| `drift_alerted` | `cron/jobs.py:2117-2124` | alert-once dedup bit | Strip |

`_machine_id()` (`cron/jobs.py:2460-2474`) = `HERMES_MACHINE_ID` env else `hostname:pid` —
**machine-local; both claim fields must be nulled on restore** or a fresh stale claim (< TTL)
suppresses the first fire (`cron/jobs.py:2795-2808`, `2508-2522`).

### 1.4 Write mechanics + permissions

- Atomic write: mkstemp same-dir → json.dump(indent=2) → fsync → atomic_replace (`cron/jobs.py:1288-1340`).
- `_secure_dir` 0700 / `_secure_file` 0600, **no-op on Windows** (`cron/jobs.py:523-537`) —
  Windows→Linux restore must re-apply modes.
- `_preserve_file_ownership` (`cron/jobs.py:540-575`): root-restored `jobs.json` must be chowned to
  the gateway user (their issue #68483 — root-owned file silently locks out the ticker).
- Read is BOM-tolerant (`utf-8-sig`) with corruption auto-repair (`cron/jobs.py:1061-1122`).

## 2. How Scheduling Executes

### 2.1 **No OS cron/launchd/schtasks integration for jobs**

No `crontab`/`launchctl`/`systemctl`/`schtasks` call ever registers an individual job. Default
engine: **in-process 60-second daemon-thread ticker** inside the gateway process:

- `cron/__init__.py:14-15` — gateway ticks every 60s; file lock prevents duplicates.
- `InProcessCronScheduler.start()` — `cron/scheduler_provider.py:186-271`.
- `TICKER_INTERVAL_SECONDS = 60` — `cron/jobs.py:99`.
- `cron.scheduler.tick()` — `cron/scheduler.py:5451-5770`: flock `.tick.lock`, ESTOP check, due
  jobs, batch next_run advance, then sequential pool (jobs with `workdir` — they mutate global
  TERMINAL_CWD) vs parallel pool (`:5594-5601`).
- Multiplex mode ticks each served profile with `set_hermes_home_override()` + `use_cron_store()`
  (`cron/scheduler_provider.py:273-367`).

### 2.2 What IS OS-registered: the **gateway service** (re-register, never copy)

| Platform | Artifact | Code |
|---|---|---|
| Linux (user) | `~/.config/systemd/user/hermes-gateway[-<profile>].service` | `hermes_cli/gateway.py:1864-1868` |
| Linux (system) | `/etc/systemd/system/hermes-gateway[-<profile>].service` | `hermes_cli/gateway.py:1867` |
| macOS | `~/Library/LaunchAgents/ai.hermes.gateway[-<suffix>].plist` | `hermes_cli/gateway.py:2622-2630, 3808-3811` |
| Windows | Task Scheduler `Hermes_Gateway[_<suffix>]` (schtasks /SC ONLOGON) + Startup-folder `.vbs` fallback | `hermes_cli/gateway_windows.py:5-21, 58, 302-347, 590, 648` |

- Service names are profile-scoped by a suffix derived from `HERMES_HOME` (`gateway.py:1851-1861`).
- Systemd units **embed HERMES_HOME** (`gateway.py:943-1030`); launchd plists embed absolute
  venv/interpreter paths (`gateway.py:2633-2650`). A copied unit silently runs the wrong store.
- **Regenerate on target via `hermes gateway install`.**

### 2.3 Scheduler providers (`cron/scheduler_provider.py:1-19`)

1. **builtin** `InProcessCronScheduler` (`:172-367`) — never removable fallback.
2. **chronos** (`plugins/cron_providers/chronos/__init__.py`) — NAS-mediated managed cron for
   scale-to-zero; `reconcile()` converges armed one-shots (`:194-224`); needs `portal_url` +
   `callback_url` + Nous token (`:64-88`). **Migration: callback_url changes; source machine's
   armed one-shots become orphans — flag.**
3. **User-installed providers** discovered from `$HH/plugins/<name>/` by text scan for
   `register_cron_scheduler`/`CronScheduler` (`plugins/cron_providers/__init__.py:69-144`).
   **Carry `$HH/plugins/` or `cron.provider` silently degrades to builtin.**

Selection: `resolve_cron_scheduler()` reads `cron.provider` from config.yaml; unknown → warn +
builtin (`cron/scheduler_provider.py:132-169`).

### 2.4 At-most-once machinery (migration-hostile)

`advance_next_runs()` (`cron/jobs.py:2406-2440`); `claim_dispatch()` pre-increments
`repeat.completed` (`:2292-2371`); `run_claim` TTL = `HERMES_CRON_TIMEOUT × 3` floor 1800s
(`:197-236`); `claim_job_for_fire()` cross-machine CAS 300s TTL (`:2477-2531`); `.jobs.lock` flock
with 30s bounded acquisition (`:107-114, 328-349`); shrink-merge guard (`:1186-1246`).

## 3. Execution History / Bookkeeping

### 3.1 In `jobs.json`
`next_run_at`, `last_run_at`, `last_status`, `last_error`, `last_delivery_error`,
`repeat.completed`, `state`, `paused_*`, `monitor_state` — written by `mark_job_run`
(`cron/jobs.py:2127-2245`). **Migrate all** — dropping `last_run_at` breaks interval anchoring
(`compute_next_run`, `cron/jobs.py:841-877`); dropping `repeat.completed` re-fires exhausted
one-shots.

### 3.2 `cron/executions.db` — attempt ledger
Schema `cron/executions.py:40-62`: `executions(id, job_id, source, process_id, pid,
process_started_at, status CHECK IN (claimed,running,completed,failed,unknown), claimed_at,
started_at, finished_at, error)`. Capped 1000 (`:21`).
**Hazard:** `recover_interrupted_executions()` (`:199-233`) probes pid liveness and *fails safe to
alive* (`:116`) — on a new machine stale non-terminal rows linger. **Drop non-terminal rows on
restore** (audit noise only, never a retry queue — docstring `:1-6`).

### 3.3 `cron/notepad.db` — per-job durable KV
`cron/notepad.py:52-60`, PK `(job_id,key)`, caps 16KB/value, 64KB/job (`:35-37`). Cursors,
watermarks, watchlists; prompt-injected via `render_notepad_section` (`:167-187`). **Must migrate**
or stateful jobs restart from scratch. Cleared on job removal (`cron/jobs.py:2064-2071`).

### 3.4 Elsewhere
Cron runs write agent sessions into `$HH/state.db` with session id `cron_{job_id}_{ts}`
(`cron/scheduler.py:4057`; `hermes_state.py:71-116`). Migrating `state.db` preserves run history in
UI.

## 4. Job Dependencies — Static Extraction

The scheduler's own **preflight** (`cron/scheduler.py:3695-3725`) is a ready-made "will this job
work here?" checker.

- **Skills** (`job["skills"]`/`job["skill"]`): may be **absolute paths** (resolved against
  `$HH/skills` or `skills.external_dirs`, `agent/skill_utils.py:593-633`). Extractor exists:
  `referenced_skill_names()` (`cron/jobs.py:3129-3158`); bulk rewriter exists:
  `rewrite_skill_refs()` (`:3161-3271`). `_preflight_check_skills` (`cron/scheduler.py:3639-3692`)
  surfaces `missing_required_environment_variables`, `missing_required_commands`,
  `missing_credential_files` — mirror this signal.
- **Provider/model**: `_preflight_check_provider_key` (`cron/scheduler.py:3537-3582`). Drift guard
  `cron.model_drift_guard` default True (`hermes_cli/config_defaults.py:2310-2314`): unpinned job
  whose `model_snapshot` ≠ target default **fails closed** with `[drift_skip]`. **Flag mismatch.**
- **Binaries**: `.sh`/`.bash` needs bash — Windows returns explicit error
  (`cron/scheduler.py:2985-2999`). Other scripts run under `sys.executable` with a Windows uv-venv
  workaround (`:2862-2901`). `croniter` required for `kind:"cron"`; missing → job `state:"error"`
  (`cron/jobs.py:650-651, 856-864, 2219-2235`).
- **Delivery**: `deliver` ∈ local|origin|platform|platform:target|combos.
  `_KNOWN_DELIVERY_PLATFORMS` (`cron/scheduler.py:394-399`): telegram, discord, slack, whatsapp,
  signal, matrix, mattermost, homeassistant, dingtalk, feishu, wecom, weixin, sms, email, webhook,
  bluebubbles, qqbot, yuanbao (+ plugin platforms via `cron_deliver_env_var`, `:1571-1600`).
  Home-channel env vars `_HOME_TARGET_ENV_VARS` (`:403-420`) e.g. `TELEGRAM_HOME_CHANNEL`;
  resolution env → legacy env → config `home_channel` (`:1656-1669`).
  `_preflight_check_delivery` (`:3585-3636`) is the checker. `origin.chat_id` is account-scoped —
  survives if the same bot credentials move.
- **Network**: `monitor_url` bounded GET, http(s), 30s/256KiB (`cron/monitor.py:48-49, 111-125`).
- **MCP**: not on the record; globally-enabled MCP servers union into `enabled_toolsets` unless
  `"no_mcp"` (`cron/scheduler.py:329-357`). **Any `enabled_toolsets` entry naming an MCP server is
  a hard dependency on that `mcp_servers` config entry.** `messaging`, `clarify`, `memory`,
  `cronjob` always stripped (`:295-326`).
- **Workdir**: absolute, validated at create-time only; missing at run time = warning + run without
  (`cron/scheduler.py:3800-3806`). **Top migration flag** (OS path forms).
- **Job-to-job**: `context_from` = other 12-hex job IDs (`cron/scheduler.py:3212-3259`); missing
  output = silent skip. **Migrate referenced jobs + output dirs together.**
- **Catalogs**: `cron/blueprint_catalog.py` `AutomationBlueprint` (`:82-99`) declares
  `skills=(...)` per blueprint (`morning-brief`→google-workspace `:138`, `important-mail`→
  email-inbox-triage `:169`, etc.). `cron/suggestion_catalog.py` `classify_items_script_path()`
  (`:27-29`) returns an **absolute path** — scan prompts for baked-in copies.

## 5. `$HH/scripts/` — the migration-critical script home

`_run_job_script` (`cron/scheduler.py:2904-3058`): scripts dir = `$HH/scripts` (`:2944`); absolute
paths accepted but **hard-contained** to `$HH/scripts` via `relative_to` check (`:2958-2971`).

1. **Package `$HH/scripts/`** — outside `cron/`, easy to miss.
2. Absolute `script` values (e.g. `/home/alice/.hermes/scripts/x.py`) get **blocked** on a target
   with a different home — **rewrite to relative on restore.**
3. Interpreter chosen by extension; shebang ignored (`:2980-2983`).
4. Script cwd = workdir or scripts-dir parent (`:3022`).
5. Subprocess env strips provider credentials (`build_subprocess_env`, `:3007,3016`; SECURITY.md
   §2.3) — scripts needing keys read `$HH/.env` explicitly.
6. Timeout 3600s default; `HERMES_CRON_SCRIPT_TIMEOUT` / `cron.script_timeout_seconds`
   (`:2813-2843`).

Repo `cron/scripts/` (only `classify_items.py`) ships with the package — moves with the install.

## 6. Platform / OS Nuances

- **Timezone (biggest correctness risk):** all cron time flows through `hermes_time.now()`
  (`hermes_time.py:122-133`): `HERMES_TIMEZONE` env → config `timezone` → server local. One-shot
  `run_at` stored TZ-aware anchored to the Hermes zone (`cron/jobs.py:664-687`, incident #51021).
  Naive legacy timestamps interpreted as system-local (`_ensure_aware`, `:712-728`) — meaning
  shifts across machines. TZ-migration repair path exists (`_get_due_jobs_locked`,
  `cron/jobs.py:2854-2891`) but can't distinguish TZ move from DST. **Carry the timezone setting or
  warn loudly.**
- **Wake/catch-up:** no OS wake integration; grace = half period clamped [120s, 7200s]
  (`cron/jobs.py:786-817`); missed runs collapse to one fire (`:2893-2928`). One-shots:
  `ONESHOT_GRACE_SECONDS=120` (`:116`); >120s-past one-shots rejected on create/update
  (`:1724-1735, 1935-1955, 2007-2012`) — **a migration taking >2 min makes pending one-shots
  un-resumable; surface this.**
- **Windows:** fcntl→msvcrt→in-process-only lock fallback (`cron/jobs.py:26-33, 350-351`;
  `scheduler.py:5482-5485`); chmod no-ops; `creationflags=windows_hide_flags()` + utf-8/replace
  (`scheduler.py:3010-3015`).
- **macOS:** plist under real account home via pwd, not `$HOME` (`gateway.py:2611-2619`); domain
  probing gui/<uid> then user/<uid> (`:3819-3828`).
- **Termux:** `is_termux()` (`hermes_constants.py:1172-1179`); no systemd — **gateway (and ticker)
  cannot be OS-registered; jobs only run while a foreground gateway is alive.**
- **Docker/root:** #68483 — restore-as-root must chown to the gateway user.

## 7. lifecycle_guard.py and monitor.py

- **`cron/lifecycle_guard.py` persists nothing** — creation-time validator blocking
  gateway-suicide commands (`hermes gateway restart`, `launchctl kickstart ai.hermes.gateway`,
  etc., pattern `:56-82`; #30719). **Asymmetry:** direct `jobs.json` copy bypasses it; restoring
  via `create_job` may reject previously-legal jobs — restore by file copy or handle
  `GatewayLifecycleBlocked`.
- **`cron/monitor.py` persists two things that must move together** (`:21-26`):
  `job["monitor_state"]` (hash gate) and `cron/output/<job_id>/monitor_last_output.txt` (diff
  baseline). Hash without baseline = no diff; neither = noisy-but-safe first-run re-baseline.

## Derived Migration Checklist

**Package:** `$HH/cron/{jobs.json, notepad.db, suggestions.json, output/**}`, `$HH/scripts/**`,
`$HH/plugins/**` (if `cron.provider` set), config `cron.*` + `timezone` + `mcp_servers`, `.env`
home-channel vars, optional `executions.db` (terminal rows) + `state.db`. Repeat per profile.

**Scrub on restore:** `run_claim`/`fire_claim` → null; `preflight_alerted`/`drift_alerted` → drop;
non-terminal executions rows → drop. Skip heartbeats, locks, pids, tmp, jsonl diagnostics.

**Rewrite:** absolute `script`/`monitor_script` → relative; absolute `skills` → names;
`cron.chronos.callback_url`.

**Flag:** missing/foreign `workdir`; `.sh` on bash-less Windows; unconnected `deliver` platform;
skill readiness failures; model/provider snapshot drift vs target; MCP toolset refs absent on
target; croniter absence; `context_from` outside migration set; TZ mismatch; soon-past one-shots;
Termux target ticker caveat.

**Re-register on target:** gateway service via `hermes gateway install`.
