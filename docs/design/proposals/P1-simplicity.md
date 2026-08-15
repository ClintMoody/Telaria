# P1 — Simplicity Lens: The Apple-Migration-Assistant Experience for Talaria

Author: Simplicity lens (champion of the novice).
Citation legend (all in `docs/research/`): **digest** = hermes-internals-digest.md ·
**state** = subsystem-state-layout.md · **skills** = subsystem-skills-plugins.md ·
**cron** = subsystem-cron.md · **integ** = subsystem-integrations.md ·
**install** = subsystem-install-update.md · **backup** = hermes-backup-precedent.md ·
**comp** = competitor-teardown.md.

---

## 1. North star and the Three Promises

The novice's mental model is not "state directory migration." It is: *my agent lives in this
computer; I want it to live in that computer, with its memory, its habits, and its chores intact.*
Everything below serves that sentence.

Three promises appear (verbatim, in a footer strip) on every screen that can touch data. They are
product law, not marketing, and each maps to a hard constraint:

1. **"Nothing on this computer is changed or deleted."** (Capture is strictly read-only —
   constraint 7; the competitor's own best signal, comp §Signals.)
2. **"Anything we change on the new computer can be undone."** (Transactional apply with
   automatic rollback — constraint 7.)
3. **"Anything we can't move automatically goes on your checklist. Nothing silently vanishes."**
   (The applier must emit a post-restore action checklist — digest §5 headline finding 6; the
   direct answer to the competitor silently dropping session history, comp W4, and forgetting
   errors, comp W13.)

Promise 3 is the load-bearing one. Apple's Migration Assistant earns trust not because it moves
everything, but because it never *loses* anything without saying so. Hermes has a documented set
of things that genuinely cannot travel (device-linked WhatsApp sessions, OS-keyring browser
profiles, machine-enrolled relays — integ §1.2, §5). The simple UX is not to hide these; it is to
convert every one of them into a checklist card with a one-minute fix.

## 2. Measurable simplicity targets

Vague "easy to use" is unfalsifiable. These are acceptance criteria for the GUI happy path:

- **Source side: at most 2 decisions** — (1) how to handle keys and passwords, (2) where to save
  the file. Everything else is defaulted (defaults grounded in §6).
- **Target side: at most 2 decisions** — (1) press "Move everything in" after preflight, (2) work
  the finish checklist. (A third appears only if the target already has a lived-in Hermes: §10.4.)
- **Zero questions the user cannot answer.** Never ask "Include WAL sidecars?" Ask nothing; do the
  right thing (state §2.3) and record it in the report.
- **First screen to finished bundle in under 3 minutes** on a typical install (excluding disk I/O
  time for multi-GB history, which gets an honest progress bar — §14).
- **No documentation required.** Every concept is explained in ≤2 sentences where it appears.
- **Full CLI parity for the same path** (constraint 3; most installs are headless VPS — comp W15):
  `talaria` with no arguments runs the identical wizard as numbered text prompts.

## 3. Naming note (constraint 8)

Keep **Talaria** for the project and the `talaria` command. But novices should never have to know
Greek mythology to know what the window does: the GUI masthead and the README first line read
**"Talaria — moves your Hermes agent to a new computer."** Display-name-with-descriptor, command
stays short. No better name proposed; the descriptor rule is the fix.

## 4. Launch experience and role detection (Screen S0)

`python talaria.pyz` (double-click on Windows — the py launcher registers `.pyz`) starts a
localhost-only stdlib web server on a random high port with a one-time token in the URL (a VPS is
multi-user; localhost is not private), then opens the default browser. On headless boxes it prints
the URL, an `ssh -L` forwarding hint, and the offer to continue in text mode.

Talaria decides which side it is on so the user does not have to:

- **Hermes found, no bundle nearby** → lead with "Pack up this Hermes". Detection follows the
  real resolver order, not guesses: `$HERMES_HOME` env → `HKCU\Environment\HERMES_HOME` on Windows
  (GUI apps miss post-login setx — install §4 traps) → `~/.hermes` / `%LOCALAPPDATA%\hermes`
  (state §1.1). Never hardcode `~/.hermes` (state §1.1 cites AGENTS.md's own hard rule).
- **A `.hermespack` found nearby, Hermes weak/absent** → lead with restore, bundle pre-selected.
  Search order: directory containing the .pyz → cwd → `~/Downloads` → `~/Desktop`.
- **Both** → two equal buttons. **Neither** → friendly explainer + "Point me at it" folder picker.

```
+----------------------------------------------------------------------+
|  Talaria — moves your Hermes agent to a new computer        [?]      |
|                                                                      |
|   We found Hermes on this computer.                                  |
|   v0.20.1 (Aug 13) - ~/.hermes - about 4.8 GB of memory, skills,     |
|   conversations and scheduled tasks.                                 |
|                                                                      |
|   +--------------------------------------------------------------+   |
|   |  ->  Pack up this Hermes                                     |   |
|   |      Makes one file you can carry to the new computer.       |   |
|   +--------------------------------------------------------------+   |
|                                                                      |
|   Setting up the NEW computer instead?   [ Open a .hermespack… ]     |
|                                                                      |
|   Nothing on this computer is changed or deleted.                    |
+----------------------------------------------------------------------+
```

## 5. Source wizard, step 1 — Scan (S1)

Scan starts immediately on click. No options screen first — options live behind "Customize" on
the *next* screen (§15). Scan is metadata-only (stat + classify, no hashing — hashing happens
during pack so scan finishes in seconds even beside a 30 GB `state.db`, which really exists:
state §2.3). Scan is read-only and honors a live install: SQLite is later snapshotted via the
backup API, never file-copied (state §2.3; backup §What-it-does), and we respect `.backup.lock`
if Hermes is mid-backup (backup §Interop).

Progress is a *narrative*, not a file spew — each line is a discovery the user cares about:

```
+----------------------------------------------------------------------+
|  Looking around…                                                     |
|                                                                      |
|   [ok] Personality & memories        SOUL.md + 214 memory entries    |
|   [ok] Skills                        47 skills — 12 you made,        |
|                                      6 the agent improved itself     |
|   [ok] Scheduled tasks               9 tasks, incl. "Morning brief"  |
|   [..] Conversations                 reading history… 2.1 GB so far  |
|   [  ] Connections                                                   |
|   [  ] Settings & projects                                           |
|                                                                      |
|   ( scanning is read-only — nothing is being changed )               |
+----------------------------------------------------------------------+
```

The "12 you made, 6 the agent improved itself" line is free intelligence: it comes straight from
`.bundled_manifest` + `.usage.json` provenance (skills §5) and instantly tells the user this tool
understands their agent better than a zip button does (comp W12).

## 6. Source wizard, step 2 — Review and the smart defaults (S2)

One screen, human categories, everything precious pre-checked. The user's job is to *glance and
confirm*, like Apple's "Applications / Documents / Settings" list — except every row is grounded
in the research and carries its hidden metadata silently.

```
+----------------------------------------------------------------------+
|  Here's what will move                                    ~3.4 GB    |
|                                                                      |
|  [x] Personality & memories                 1.2 MB   (what's this?)  |
|  [x] Skills & plugins            47 skills   38 MB   (what's this?)  |
|  [x] Scheduled tasks               9 tasks    2 MB   (what's this?)  |
|  [x] Conversations & history               3.1 GB   (what's this?)   |
|  [x] Connections & pairings                  4 MB   (what's this?)   |
|  [x] Settings, projects & boards            11 MB   (what's this?)   |
|                                                                      |
|  Keys & passwords:  ( ) Locked vault (passphrase)                    |
|                     (o) Checklist — re-enter them on the new machine |
|                                                        [ Why? ]     |
|                                                                      |
|  Won't travel (3) — WhatsApp link, browser logins, local runtime     |
|      … each has a 1-minute fix on the new computer.  [ See why ]     |
|                                                                      |
|  [ Customize in detail ]                        [ Pack it up  -> ]   |
+----------------------------------------------------------------------+
```

### 6.1 The default selection, row by row, with grounding

| Category (user-facing) | What it actually carries | Default | Why (citation) |
|---|---|---|---|
| Personality & memories | `SOUL.md`, `memories/`, root MD set (`MEMORY.md`, `USER.md`, `todo.json`, `system_prompt.md`, `AGENTS.md`, `CLAUDE.md`, `.cursorrules`), external memory dirs (`~/.honcho`, `~/.hindsight`, `~/.openviking/ovcli.conf`) via `_external/`-style home-relative encoding | ON | "must migrate" set, state §2.1; external paths via `MemoryProvider.backup_paths()` precedent, state §2.2, backup §External-state |
| Skills & plugins | `skills/**` incl. `.archive/`, `.usage.json`, `.bundled_manifest`, `.curator_suppressed`, `.hub/{lock.json,taps.json,audit.log}`, `_org/**`, `.sync_state`, `skill-bundles/`, `plugins/`, `plugin-data/`; drop `.hub/index-cache`, `.hub/quarantine`, `.curator_backups`, `*.bak`, locks; regenerate `.sync_device_id` per machine | ON (metadata non-optional within the category) | recommended capture set, skills §Recommended; losing `.usage.json` freezes curation, skills §5; restoring skills without `.curator_suppressed` resurrects pruned built-ins, skills §8 |
| Scheduled tasks | `cron/jobs.json`, `notepad.db`, `suggestions.json`, `output/**` (incl. `monitor_last_output.txt`), `executions.db` (terminal rows), `$HH/scripts/**` | ON | derived checklist, cron §Derived; notepad loss restarts stateful jobs from scratch, cron §3.3; monitor baseline loss re-alerts, cron §1.2; scripts are a hard dependency outside `cron/`, cron §5 |
| Conversations & history | `state.db` (+ `response_store.db`, `memory_store.db`, `verification_evidence.db`) via `sqlite3.backup()` snapshots, sidecars excluded; `sessions/`, `sessions/saved/`, `session-exports/` | ON | dropping history is the competitor's worst sin (comp W4); DB handling rules, state §2.3; cron run history lives in `state.db`, cron §3.4 |
| Connections & pairings | `pairing/` + `platforms/pairing/` (both layouts merged — integ §0), `channel_directory.json`, `channel_aliases.json`, platform state judged per integ §1.2/§1.3 (a)-class only, `mcp_servers` config | ON | pairing is the authoritative grant record, integ §1.3; channel routing is user data, state §2.7 |
| Settings, projects & boards | `config.yaml` (inline secrets extracted to the Keys step, placeholder left), `skins/`, `dashboard-themes/`, `hooks/`, `kanban.db` + `kanban/boards/` (root-level! state §10 trap 9), `projects.db` | ON | must-migrate list, state §7; inline `api_key`/`client_secret` are (d)-class, integ §7 |
| Keys & passwords | `.env`, `auth.json`, `.anthropic_oauth.json`, `shared/nous_auth.json`, `mcp-tokens/`, platform token files, `webhook_subscriptions.json`, inline config secrets | **Checklist mode** (default) or opt-in vault | constraint 6; ~40 secret-bearing vars incl. `SUDO_PASSWORD`, digest §2; all plaintext, no OS keyring, state §2.2 |
| Won't travel (shown, not checked) | `whatsapp/session/` (device-linked), signal-cli store, Matrix `crypto.db`, Weixin QR sessions, `chrome-debug/` (OS-keyring encrypted), relay enrollment, msgraph subscriptions, venv/node/bin/native libs, caches, logs, locks, PIDs, `gateway_state.json`, checkpoints, machine markers | OFF | machine-bound is a first-class category with real incidents (NS-508, device unlinking, Camoufox orphaning) — digest §5 finding 3; per-item classes, integ §1.2, §5; `checkpoints/` keys are path-hashed and unrecoverable, state §7 |

Multiple profiles are included automatically and mentioned in one line ("Includes both profiles:
default, coder") — the scanner anchors at the root like the native backup does (state §10 trap 1;
cron stores are per-profile, cron §1.1).

### 6.2 What a category toggle does NOT expose

The novice never sees `.bundled_manifest` or `notepad.db`. Unchecking "Scheduled tasks" removes
the whole coherent unit (jobs + notepad + outputs + scripts) because partial units create the
exact breakage the research documents (monitor hash without baseline, jobs without scripts —
cron §7, §5). Sub-item surgery exists only in "Customize in detail" (§15), where each sub-item
shows its consequence sentence before it can be unchecked.

## 7. The Keys & passwords step (S3)

This is the one real decision on the source side, so it gets first-class copy:

- **Checklist (default, recommended):** "Your keys and passwords stay out of the bundle, so the
  file is safe to carry on a USB stick or send over the network. We make you a checklist; on the
  new computer you'll paste each key back in (we'll show you exactly where each one is used)."
  The checklist is generated from `.env` + `auth.json` + inline config keys + per-skill
  `required_environment_variables` (the only enforced skill dependency — skills §6), each item
  annotated with what uses it ("Telegram bot", "OpenAI models") and the provider URL where the
  skill metadata declares one (skills §1 `setup.collect_secrets`).
- **Locked vault (opt-in):** passphrase twice + strength meter, scrypt + AES-256-GCM via
  `cryptography` (constraint 6). If `cryptography` is missing, honest refusal in plain words:
  *"This computer is missing the piece we use to lock vaults (the Python 'cryptography'
  add-on). We never pack passwords unprotected. [Show the one command to add it] [Use the
  checklist instead]."* No home-rolled crypto, ever.
- OAuth-ish tokens that are cheap to re-mint (mcp-tokens — "recovery cheap", integ §2.2) are not
  worth vaulting in checklist mode; they become a single checklist card: "Reconnect cloud tools —
  run `hermes mcp reauth --all`."

## 8. Pack and the transfer moment (S4)

Destination picker defaults to `~/Desktop/hermes-move-<host>-<date>.hermespack`. Before packing
starts, Talaria pre-checks the destination: free space vs the estimate from scan, and the FAT32
4 GB file cap (common USB stick format) — failing at 99% is a betrayal, so we fail at 0%.
Staging for DB snapshots happens on the destination filesystem, never `/tmp` (tmpfs truncation
incident — state §10 trap 5).

Done screen — the transfer is where novices get lost, so it is explicit:

```
+----------------------------------------------------------------------+
|   Your Hermes is packed.                                 [checkmark] |
|                                                                      |
|   hermes-move-atlas-2026-08-15.hermespack        3.38 GB  [Show it]  |
|                                                                      |
|   Carry BOTH files to the new computer (USB stick, network drive,    |
|   or:  scp talaria.pyz *.hermespack you@new-machine: )               |
|                                                                      |
|      1)  talaria.pyz            <- this app                          |
|      2)  hermes-move-….hermespack  <- your Hermes                    |
|                                                                      |
|   On the new computer:  run talaria.pyz. It will find the bundle     |
|   sitting next to it and take it from there.                         |
|                                                                      |
|   Your Hermes here is untouched and still running. One rule:         |
|   turn it OFF before you start the new one. We'll remind you.        |
|                                                                      |
|   [ Save the keys checklist (PDF/HTML) ]        [ Done ]             |
+----------------------------------------------------------------------+
```

"Copy both files" makes the tool self-transporting — the target machine needs only a Python, which
is exactly why the core is stdlib-on-3.9+ (constraints 1–2, 4).

## 9. Target wizard, step 1 — Open bundle (T1)

Auto-found bundle shows a provenance card before anything else, from the manifest (constraint 5):

```
|  Found: hermes-move-atlas-2026-08-15.hermespack   [ Not this one? ] |
|  Packed yesterday 18:42 on "atlas" (Linux) - Hermes v0.20.1         |
|  47 skills - 9 scheduled tasks - 3.1 GB of conversations            |
|  Keys: checklist mode (no passwords inside)                         |
|                                            [ Check this computer ]  |
```

A plain `hermes backup` zip is accepted as a degraded input with one honest sentence ("This is a
plain Hermes backup, not a Talaria bundle — we can restore it, but without the smart checks") —
interop decision, backup §Interop.

## 10. Target wizard, step 2 — Preflight (T2)

Preflight is modeled on `hermes doctor` — sectioned OK/WARN/FAIL with accumulated manual actions
(digest §3), and it literally mirrors the cron scheduler's own preflight signals
(`missing_required_environment_variables`, delivery checks, provider keys — cron §4). The crown
rule: **verdicts are grouped by who has to act**, not by subsystem:

```
+----------------------------------------------------------------------+
|  Checking this computer…                                   done      |
|                                                                      |
|  Ready to move in (34)                                    [show]     |
|                                                                      |
|  We'll fix these automatically (12)                       [show]     |
|    e.g. 2 scheduled tasks point at old folder locations — we'll      |
|    update them.  Services will be re-registered for this computer.   |
|                                                                      |
|  Needs you afterwards (5)                     -> goes on checklist   |
|    WhatsApp re-link (1 min) - 14 keys to paste - reconnect 2 cloud   |
|    tools - re-login browser sites - pick model for 1 task            |
|                                                                      |
|  Can't come along (2)                                     [why?]     |
|    Browser logins (locked to old computer) - old computer's local    |
|    model server (LM Studio) — task "nightly-summarize" will need it  |
|    installed here or a different model.                              |
|                                                                      |
|  [ Customize ]     Nothing changes until you press ->                |
|                                        [ Move everything in  -> ]    |
+----------------------------------------------------------------------+
```

### 10.1 Checks behind the groups (each grounded)

- **Is Hermes here?** If absent: "Install Hermes for me (recommended)" runs the official
  installer pinned to the bundle's commit (`--commit <sha> --skip-setup` / `-Commit`) — the
  research's own restore recipe (install §12). Talaria never reimplements installation.
- **Version skew:** bundle tag/commit vs target `__version__`+git HEAD (install §4); gate with
  "Update Hermes here (recommended) / Continue anyway" (digest §6.8). Bundles with
  `_config_version` < 12 get the support-floor warning verbatim logic (state §3).
- **Room to work:** free space ≥ payload + safety copy + staging (~2.2×), checked up front
  (the native updater's *1.2 precheck precedent, install §3).
- **Cross-OS realities:** POSIX↔Windows path family translation planned per file-type schema (no
  blanket regex — comp W7); `.sh` cron scripts on a Windows target flagged per the scheduler's own
  bash rule (cron §4); mode bits re-applied 0600/0700 because zip drops them and Windows chmod
  no-ops (state §10 trap 10; cron §1.4).
- **Per-task feasibility:** missing `workdir`s, `croniter`, delivery platforms, model/provider
  drift (fails closed upstream as `[drift_skip]` — we surface it as a choice, cron §4), MCP
  toolset references, `context_from` closure (cron §Flag list).
- **MCP runtimes:** url vs command classification; npx→Node, uvx→uv, docker→daemon presence
  (integ §2.4 recipe); entries re-validated before write because unvalidated entries are silently
  dropped at spawn (integ §2.4 step 7).
- **Skill platform gates:** `platforms: [macos]` skills on a Linux target → "Needs you / won't
  run here" per the hard gate (skills §1).
- **Managed/immutable targets:** `.managed`/NixOS detected → adapt (migrate $HERMES_HOME only,
  never fight activation — state §8; install §1 Nix).
- **Timezone:** compare Hermes-zone (env → config → server local); the carried `timezone` config
  keeps schedules meaningful; a source that relied on server-local time gets the loud warning the
  research demands (cron §6).

### 10.2 "Can't come along" wording — the honesty contract

Every red/grey item = 3 sentences max: what, why in human terms, what happens instead. §13 has
the worked examples.

### 10.3 One-shot timers due mid-move

Hermes rejects one-shots >2 minutes past due (cron §6), and a migration takes longer than that by
definition. Preflight lists them: *"2 one-time reminders were due during the move ('Call the
plumber', Fri 15:00). We paused them so they don't fire late by surprise. [Pick new times]
[Dismiss them]."*

### 10.4 Target already has a lived-in Hermes

The only extra decision the wizard may ever add: **"Replace it (we keep a dated safety copy — you
can undo this)"** vs **"Cancel"**. Field-level merge is real complexity and lives only in
Customize; a novice merge is how you corrupt two installs into one (the native import is
overlay-with-confirm precisely because merge is hard — backup §What-it-does-NOT).

## 11. Target wizard, step 3 — Apply (T3)

Stage → backup → apply → verify → commit under the hood (constraint 7); on screen, five
plain-named stages. Failure at any stage = automatic rollback + "This computer is unchanged."

```
+----------------------------------------------------------------------+
|  Moving your Hermes in…                                              |
|                                                                      |
|   [ok] Getting ready        bundle checked — 1,412 files intact      |
|   [ok] Safety copy          this computer's Hermes saved first       |
|   [>>] Moving in            ############------------  58%  1.9 GB    |
|   [  ] Making it at home    (paths, permissions, services, add-ons)  |
|   [  ] Double-checking      (every file re-verified + hermes doctor) |
|                                                                      |
|   If anything goes wrong, everything is put back automatically.      |
|                                                    [ Cancel ]        |
+----------------------------------------------------------------------+
```

"Making it at home" is the silent-competence stage (full inventory in §17): claim-scrubbing,
path rewrites, permission restoration, `hermes gateway install` (never copying service units —
digest §5 finding 4), WhatsApp bridge `npm install` (integ §1.2), lazy provider extras
re-provisioned from the recorded `active_features()` list (the unrecorded-extras gap — install
§9), Camoufox `user_id` pinned so browser identity survives the path change (integ §5).

## 12. Verify and the finish screen (T4)

Verification is not a vibe; it is numbers: every applied file re-hashed against the manifest
(constraint 5), `hermes --version` through the launcher (upstream's own smoke test — install §10),
then `hermes doctor` with its sectioned results folded in (digest §3).

```
+----------------------------------------------------------------------+
|   Your Hermes has moved in.                              [checkmark] |
|   1,412 files verified - doctor: 24 checks passed, 5 waiting on you  |
|                                                                      |
|   Done for you:  services registered - WhatsApp bridge reinstalled   |
|   - 3 provider packs reinstalled - permissions locked down - paths   |
|   updated in 2 scheduled tasks - safety copy kept (undo anytime)     |
|                                                                      |
|   Your checklist (5):                                                |
|   [ ] Paste your keys (14) ………………………………  [ Enter them now ]          |
|   [ ] Re-link WhatsApp (scan QR, ~1 min) …  [ Show me how ]          |
|   [ ] Reconnect cloud tools ……………………………    hermes mcp reauth --all   |
|   [ ] Log back into websites in the agent browser                    |
|   [ ] "Morning brief" needs a model choice   [ Decide ]              |
|                                                                      |
|   [x] I've turned OFF Hermes on the old computer     <- required     |
|                                                                      |
|   [ Save report ]   [ Undo everything ]   [ Start Hermes  -> ]       |
+----------------------------------------------------------------------+
```

Checklist mechanics:

- **"Enter them now"** opens inline paste fields per key (name, what uses it, provider link where
  known — skills §1/§6), written straight to `.env` with 0600. Pasting beats "go edit a dotfile."
- Each card carries the exact command in a copy button for the SSH crowd.
- Checklist state persists (`$HERMES_HOME/migration/<ts>/checklist.json`, mirroring the OpenClaw
  migration's report layout precedent — install §7) so reopening Talaria resumes it.
- **The gate:** "Start Hermes" stays disabled until the old-machine checkbox is ticked. This is
  opinionated on purpose: the documented failure mode of running both is account unlinking and
  split messages, not an error dialog (integ §8 — "warn loudly"; Telegram 409 conflicts,
  integ §1.2).
- **"Undo everything"** restores the safety copy — visible until the user dismisses it, because a
  reversible decision is an easy decision.

## 13. Language rulebook (with worked examples)

Rules for every user-facing string:

1. Lead with what happened in the user's vocabulary; the subsystem name comes second if at all.
2. **Always state whether their stuff is safe** — every error answers it explicitly.
3. Exactly one recommended next action, phrased as a verb ("Pick new times", never "OK").
4. Paths, exit codes, stack traces live behind "Technical details"; every message carries a
   stable ID (e.g. `WA-DEVICE-LINK`, `T-APPLY-041`) for support and for the report.
5. Warnings are amber cards inline; errors are full-stop screens; never mix the registers.
6. Round numbers ("about 2 GB"); no blame; no exclamation marks in errors.
7. Every red screen has [Copy full report].

Worked examples (these exact strings ship):

- **WhatsApp (`WA-DEVICE-LINK`):** *"WhatsApp needs a quick re-link on the new computer.
  WhatsApp ties itself to one computer at a time, like linking a phone — that link can't be
  copied, and trying to would disconnect both machines. Your chats and settings are safe. On the
  new computer you'll scan a QR code once (about a minute); we'll remind you at the right
  moment."* (Device-linked Baileys session; concurrent run gets the device unlinked —
  integ §1.2. The opt-in verbatim copy with its loud warning exists only in Customize.)
- **Signal:** *"Signal links each computer as a companion device, like Signal Desktop. Companion
  links can't move between machines, so the new computer will pair itself with your phone once."*
  (Store lives outside HERMES_HOME; single-device rule — integ §1.2.)
- **Browser logins (`BR-KEYRING`):** *"Websites the agent was logged into keep their logins
  locked to the old computer — that's a security feature of the browser itself. The agent will
  log in fresh here."* (chrome-debug cookies encrypted with the OS keyring — integ §5.)
- **Local model server (`PR-LOCALHOST`):** *"Your old computer ran a local model server
  (LM Studio) that this bundle's settings point at. This computer doesn't have it. Tasks using it
  will wait until you install LM Studio here or pick a different model. [Pick a model]
  [I'll install it]"* (localhost base_url hazard — integ §3.)
- **Model drift (`CR-DRIFT`):** *"'Morning brief' was created when GPT-5 was the default model;
  this computer defaults to a different one. Hermes pauses tasks rather than switch models behind
  your back. [Keep GPT-5 for this task] [Use the new default]"* (drift guard fails closed —
  cron §4.)
- **Damaged transfer (`BN-HASH`):** *"The bundle didn't arrive perfectly — 3 files failed their
  fingerprint check, which usually means the copy to USB glitched. Nothing was changed on this
  computer. Copy the file across again and reopen it."*
- **Rollback (`T-ROLLBACK`):** *"Something went wrong while moving in (details below), so we put
  everything back the way it was. This computer is unchanged. [Copy full report] [Try again]"*
- **Busy source (`SRC-LOCK`):** *"Hermes is in the middle of its own backup. We'll wait — packing
  will start the moment it finishes."* (Honor `.backup.lock` — backup §Interop.)

## 14. Progress display spec

- **Phases as a vertical checklist** (see S1/T3): done phases keep their result line as a
  receipt; the active phase animates; pending phases are visible so the user knows the shape of
  the whole job. No log scroll on the main surface; "Show details" streams the real log.
- **Byte-weighted determinate bar** for pack/apply (sizes known from scan/manifest); count-based
  spinner for scan. Time-remaining appears only after 10s of stable throughput, as "about".
- Any single item >30s shows its name and size ("Packing conversations — state.db, 2.1 GB…"), so
  a 30 GB history (state §2.3) reads as *working*, not *hung*.
- GUI work runs in a background thread; the page polls a `/status` JSON endpoint — the UI never
  freezes (the competitor blocks its Tk main thread for entire multi-GB exports, comp W14).
- Everything is cancellable. Cancel on source = nothing happened (read-only). Cancel during
  apply = automatic rollback with the `T-ROLLBACK` copy.
- CLI renders the same phases as lines with `\r` in a TTY, plain sequential lines when piped.

## 15. Progressive disclosure — hidden but reachable (Reaper under the Apple shell)

One engine, one selection model, three lenses:

1. **Wizard lens (default):** categories, 2 decisions, everything above.
2. **Customize lens:** "Customize in detail" opens a drawer over the same screen — the full typed
   artifact tree (every item: kind, size, portability class (a)/(b)/(c)/(d) from integ §7,
   provenance, per-item toggle). Sub-item unchecks show their consequence sentence first
   ("Without the task notepad, stateful tasks restart from scratch" — cron §3.3). Force-include
   of default-excluded items (WhatsApp session, chrome-debug same-OS) lives here behind its loud
   warning. Every "what's this?" and "why?" expander ends with a "Full details" link into this
   lens, pre-scrolled to the item — curiosity is the on-ramp, never a cliff.
3. **CLI/JSON lens:** the identical model as `talaria scan --json`, `pack --include/--exclude`,
   selection files, `--dry-run` everywhere (constraint 7). The wizard writes its selection record
   into the bundle (constraint 5), so a GUI-made bundle is reproducible from the CLI verbatim.

```
|  Customize in detail                                    [ close ] |
|  v Scheduled tasks (9)                          2.1 MB  [x]       |
|     [x] jobs (9)            [x] task notepad (notepad.db)         |
|     [x] outputs (412 files) [x] scripts (7)  [ ] run log (audit)  |
|     ! unchecking the notepad: stateful tasks restart from scratch |
|  v Won't travel                                                   |
|     [ ] WhatsApp device link   force-include: [ I understand… ]   |
```

The mode is remembered per machine, so a power user lands in Customize next time — and a novice
never sees it.

## 16. CLI parity of the simple path

`talaria` with no arguments = the same wizard as numbered prompts (pure stdin/stdout, no curses):
same category cards, same defaults, same three promises, same finish checklist rendered as text +
saved HTML. `talaria pack --yes` / `talaria apply x.hermespack --yes` are the one-shot forms that
accept every default non-interactively (for scripts and for the "just do it" user). Guided ≠ GUI:
the VPS-over-SSH user (comp W15) is a first-class novice too.

## 17. Silent competence — what the happy path absorbs without asking

Every one of these is invisible in the wizard and enumerated in the saved report:

1. SQLite snapshotted via backup API, sidecars never packed; integrity check size-capped at 2 GiB
   with the O(1) probe above it; zeroed-DB detection (state §2.3, §10 traps 4–7).
2. Symlinks never followed on either side (exfiltration vector — state §10 trap 3).
3. `hermes-agent` pruned at root only — `skills/**/hermes-agent/` is real data (state §10 trap 2).
4. Machine-bound set excluded at capture AND filtered again at apply — never trust the archive's
   own hygiene (backup §What-it-does, NS-508).
5. Code checkout never packed: record ref + dirty diff, re-clone at the same commit on target,
   offer patch replay (digest §6.4; install §12).
6. cron `run_claim`/`fire_claim` nulled, alert bits dropped, non-terminal execution rows dropped
   (cron §1.3, §3.2); absolute `script`/skill refs rewritten relative (cron §5, §4).
7. Restored-as-root files chowned to the gateway user (upstream incident #68483 — cron §6).
8. 0600/0700 restored explicitly post-extract (state §10 trap 10).
9. Empty legacy dirs never created (shadowing trap — state §10 trap 8); dual old/new layout dirs
   merged on read (integ §0).
10. Camoufox `user_id` captured and pinned via config on target — otherwise every browser login
    silently vanishes with no error (integ §5).
11. Lazy provider extras probed from the source venv (`active_features()`), re-ensured on target
    (install §9 — "unrecorded" is the key finding).
12. Service units/plists/schtasks regenerated via `hermes gateway install`, never copied
    (units bake absolute paths — integ §1.4).
13. MCP entries re-validated before write (silently dropped at spawn otherwise — integ §2.4).
14. Network-filesystem homes get the WAL→DELETE journal reality surfaced instead of silent mode
    change (state §2.3).
15. `.update_check` cleared; profile wrapper scripts regenerated (state §10 trap 12).

This list is the product's soul: Apple-simple *because* Reaper-thorough, not instead of it.

## 18. Constraint challenges and one flagged risk

**No constraint challenges.** All eight constraints actively serve the novice (stdlib core makes
"copy both files" work on a bare machine; the browser GUI beats tkinter's absence on servers —
comp W1; one-file bundle matches the mental model "my Hermes is this file").

One flagged risk inside constraint 4, with mitigation, not a challenge: a bare Windows target may
lack Python entirely, and "install Python first" is the least Apple moment of the journey. Mitigate
in-scope: the pack-done screen's transfer card includes the python.org link with the "check Add to
PATH" note for Windows, and the README's first section is the two-line target bootstrap. (A signed
native launcher is out of scope for v1 and would violate the single-file .pyz simplicity.)

Also flagged for the committee (bundle format, constraint 5): require zip64 from day one —
conversation histories alone exceed 4 GB routinely (a real 30 GB `state.db` exists — state §2.3),
and the FAT32 warning in §8 only helps if the format itself doesn't cap us.

## 19. The three decisions I will defend hardest

1. **Two decisions per side, everything else defaulted** (§2, §6) — the defaults table is
   research-grounded row by row; if a committee member wants a new wizard question, they must
   show a user who can answer it better than the research can.
2. **The finish-screen gate on "old computer is off"** (§12) — the only hard block in the whole
   flow, because the failure mode it prevents (WhatsApp unlink, split Telegram delivery, Matrix
   Olm corruption — integ §8) is invisible, delayed, and blames the product.
3. **Checklist-by-default for secrets with inline paste-back on the target** (§7, §12) — safer
   than any vault by construction, and *faster* than the vault for the common case because
   `hermes mcp reauth --all` regenerates half the items anyway (integ §2.2).
