# P4 — Product & Release Lens: Ship the Thing People Tell Their Friends About

Author: product/release advocate (champion of the launch; sworn enemy of X3N064/Hermes-Agent-Converter).
Citation legend (all in `docs/research/`): **digest** = hermes-internals-digest.md ·
**state** = subsystem-state-layout.md · **skills** = subsystem-skills-plugins.md ·
**cron** = subsystem-cron.md · **integ** = subsystem-integrations.md ·
**install** = subsystem-install-update.md · **backup** = hermes-backup-precedent.md ·
**comp** = competitor-teardown.md · **m2c1** = m2c1-adoption.md. Sibling proposals: **P1**, **P2**.

---

## 1. Product truth in one sentence

**"Your agent — soul, memory, and chores — moves to its new home, and nothing is lost without
being named."** Hermes is *the self-improving agent*: the install mutates itself by design
(digest §0), so what the user is moving is not files, it is accumulated identity — SOUL.md,
memories, agent-authored skills, cron habits (state §2.1, skills §5, cron §1). Every release
artifact below (name, README, reports, checklists, screenshots) is judged against that sentence.
The competitor is a zip button (comp Verdict); we are a moving company with a manifest, insurance,
and a handover ceremony.

## 2. Naming decision — commit to **Talaria**

Assessment of the working name against real alternatives:

| Candidate | Myth fit | Typability / CLI | Says what it does | Collision risk | Verdict |
|---|---|---|---|---|---|
| **Talaria** | Perfect — the winged sandals are *how Hermes travels between worlds* | `talaria`, 7 chars, pronounceable | No (fixable, below) | An e-moto brand; zero collision in dev tooling / PyPI | **COMMIT** |
| Caduceus | Hermes' staff — symbol of office, not travel | Hard to spell/say | No | Medical orgs everywhere | Reject |
| Psychopomp | Gorgeous concept (guides souls between worlds — literally migrates SOUL.md) | Long, alarming, hard to type | No | Low | Reject; keep as copy flavor only (§13) |
| Portage | Great metaphor (carrying a vessel overland) | Easy | Vaguely | **Fatal:** Gentoo's package manager | Reject |
| `hermes-mover` / `hermes-pack` | None | Easy | Yes | Implies official status we don't have; brand confusion with Nous Research's product | Reject |

Decision rationale, beyond the table:

1. **Affiliation safety.** We are a community tool, not Nous Research. A name led by "Hermes"
   invites "is this official?" support load and trademark awkwardness. "Talaria" references
   without impersonating. The README carries an explicit non-affiliation line (§3).
2. **Discoverability is already solved by the extension.** Constraint 5 fixes `.hermespack` —
   the searchable term "hermes" lives in the file extension, the repo name
   (`hermes-migration-tool`), and the README H1 descriptor. We do not need it in the brand.
3. **P1 independently reached "keep Talaria + descriptor lock."** Two lenses converging without
   coordination is signal. I adopt P1's rule and harden it into product law: **the name never
   appears without its descriptor** in H1s, mastheads, app store-ish listings, and `--help` line 1:

   > **Talaria — moves your Hermes agent to a new computer.**

4. CLI = `talaria`. Bundle = `.hermespack`. Default bundle filename =
   `hermes-<hostname>-<YYYY-MM-DD>.hermespack` (self-describing at rest in a Downloads folder).

## 3. README / landing structure

The README is the landing page (GitHub is where users arrive). Structure, in order, each block
with its job:

1. **H1 + descriptor + badges** (CI, Python 3.9+, zero required deps, license). One line under it:
   *"Community tool. Not affiliated with Nous Research."*
2. **The 90-second pitch** — the Three Promises verbatim from P1 §1 (read-only source; undoable
   target; nothing silently lost). These are also product law in-app; README and app must never
   drift apart. (Grounded in constraint 7 and digest §5 finding 6.)
3. **Hero media** — 20-second GIF of a pack on the fixture install (§9), <3 MB.
4. **Quick start** — two copy-pasteable blocks, one per machine, real filenames:

   ```
   # Old computer
   python3 talaria.pyz pack           # wizard; add --yes for defaults
   # → hermes-vps1-2026-08-15.hermespack + its Secrets Handoff Checklist

   # New computer (after copying the file over)
   python3 talaria.pyz apply hermes-vps1-2026-08-15.hermespack
   ```

   Plus the Windows double-click note (the py launcher registers `.pyz`; constraint 4) and the
   headless/SSH note front and center — most installs live on a VPS (comp W15).
5. **What travels / what can't** — an honest 2-column table: travels (memories, skills incl.
   agent-authored, cron jobs + their scripts + notepads, sessions/history, pairing grants, config)
   vs. re-do on arrival (WhatsApp/Signal device links, OS service registrations, browser profiles,
   relay enrollment — integ §1.2, §1.4, §5). Honesty here is the trust move Apple makes; the
   competitor hides drops (comp W4).
6. **Comparison table** (§7) — vs. the competitor, `hermes backup`, and DIY scp.
7. **Security model** — secrets excluded by default; checklist generated; vault opt-in
   (scrypt + AES-256-GCM via `cryptography`, honest refusal without it — constraint 6); no
   telemetry, no network, ever.
8. **Compatibility matrix** — OS×OS grid (Linux/macOS/Windows/WSL/Termux/Docker→ same set), with
   footnotes for the genuinely asymmetric cells (e.g. `.sh` cron scripts onto bash-less Windows —
   cron §4; Termux ticker caveat — cron §6).
9. **Docs index, FAQ link, bundle-format link** ("What is a .hermespack file?" — §6), CHANGELOG,
   license, and the support policy (§12 day-0 kit).

## 4. First-run experience — "I downloaded a file" → "migration done"

The full two-machine journey, as numbered moments. GUI and CLI follow the identical script
(constraint 3; P1 §2's "CLI parity" target — same wizard, numbered text prompts).

### Source machine

- **M0 — Acquire.** GitHub Releases: `talaria.pyz` + `talaria.pyz.sha256`. Also `pip install
  talaria-migration` (constraint 4). The release page body repeats the quick start.
- **M1 — Launch.** `python3 talaria.pyz` (or double-click). On Python <3.9 the stub prints a
  plain-English version message, never a traceback (§10.5). GUI: localhost-only, random port,
  one-time token URL, opens browser; headless: prints URL + `ssh -L` hint + "press t for text
  mode" (P1 §4; constraint 3).
- **M2 — Detect & greet.** Resolver-order detection ($HERMES_HOME → HKCU on Windows → platform
  default — state §1.1-1.2, install §4 traps). Copy: *"Found your Hermes agent: v0.20.1
  (v2026.8.13), installed with git, 2 profiles, ~3.1 GB."* Identity facts come from the install
  §4 cheat sheet. The read-only promise is on screen from the first pixel.
- **M3 — Overview scan.** Progress with real counts ("reading skills… 41 found"). Ends on the
  overview screen: family cards with counts/sizes and provenance badges (stock / modified / yours
  / written-by-your-agent — skills §5). Button: **"Save this as a report"** → the System Overview
  HTML (§8.1) — the brief's "comprehensive overview" deliverable, available *without* packing.
- **M4 — Optional Deep-Scan assist.** One card: *"Want your agent to help take inventory?
  (optional, ~2 min)"* — generates the skill/prompt file for the user's running Hermes (m2c1
  §Adapted). Product framing is fixed: **evidence, not testimony** — agent answers are marked
  "unverified" until the scanner corroborates them (owner's brief: self-reports can't be trusted).
  Skipping it changes nothing about the happy path.
- **M5 — The two decisions** (P1 §2 budget): (1) secrets — default "Checklist, no secrets in the
  file" vs. opt-in vault with passphrase (constraint 6); (2) where to save. Everything else is
  informed defaults with visible `why` (P2 §1).
- **M6 — Pack.** Progress with cancel; SQLite snapshots via backup API (state §2.3); atomic
  output (backup precedent). Ends with the **boarding pass** (§13.2): bundle name, size,
  fingerprint, contents summary, and the Secrets Handoff Checklist saved alongside
  (`<bundle>.checklist.html` — names and where-to-find hints only, never values; needed on the
  *old* machine while gathering secrets, which is why it also lives outside the bundle).
- **M7 — Transfer coaching.** Screen prints the exact command with the real filename
  (`scp hermes-vps1-2026-08-15.hermespack you@new-box:~/`), USB/cloud alternatives, and
  `talaria verify <file>` for the far side. **The retire plan is presented here, not at apply
  time:** keep the old machine running until the new one verifies — *except* device-linked
  platforms (WhatsApp/Signal/Matrix), which must stop before the target gateway starts or the
  account gets unlinked (integ §1.2, §8 — "failure mode is account unlinking, not a startup
  error"). This warning's timing is a product decision: the user chooses when to power down
  *now*, at pack time.

### Target machine

- **M8 — Launch + role flip.** Same `.pyz`. Bundle found nearby → restore leads (P1 §4 search
  order). No Hermes on the machine → Talaria does **not** curl|bash an installer itself; it
  prints/copies the exact official install command **pinned to the source commit**
  (`--commit <sha> --skip-setup` — install §12 restore recipe) and waits with a "Done — check
  again" button. Rationale: failure ownership and security optics; the installer is upstream's
  product, ours is the state.
- **M9 — Preflight.** The feasibility matrix, modeled on `hermes doctor`'s sectioned OK/WARN/FAIL
  with accumulated manual actions (digest §3): version skew gate (§10.4), per-cron dependency
  verdicts mirroring the scheduler's own preflight (cron §4), platform reachability, missing
  binaries, TZ mismatch (cron §6), config floor `_config_version ≥ 12` (state §3). Red rows say
  what to do, not just what's wrong. `talaria preflight <bundle>` runs it standalone.
- **M10 — Apply.** One button after preflight; transactional stage → backup → apply → verify →
  commit, auto-rollback (constraint 7). Conflict cards only if the target is lived-in (P1's
  third decision). Progress is per-family, cancellable.
- **M11 — Finish checklist.** Interactive check-off of the machine-bound re-dos, one card per
  item with its one-minute fix and exact command (`hermes gateway install`, `hermes whatsapp`,
  `hermes mcp reauth --all`, `npm install` for the WhatsApp bridge, Camoufox user_id pin —
  integ §8's enumerated post-restore actions, integ §5). Checklist state persists at
  `$HERMES_HOME/migration/talaria/<ts>/` — mirroring the claw-migrate output layout precedent
  (install §7) — so it survives closing the tool.
- **M12 — Proof of life + done.** After the user starts the gateway, Talaria watches for a fresh
  `cron/ticker_heartbeat` (a machine-local liveness file we deliberately did *not* migrate —
  cron §1.2) and flips the scheduler card green when the first tick lands. Offer `hermes doctor`
  (upstream's own smoke test culture — install §12). Then the success screen (§13.1) and the
  Migration Report (§8.2). Done means: verified, checklisted, and reported — not "extraction
  finished" (comp W13).

## 5. Onboarding copy tone

Rules (enforced by a copy review pass in the release checklist):

1. **Talk about the agent, not the filesystem.** "Your agent's memories" not "the memories/
   directory." Paths appear in expandable detail rows, never in headlines.
2. **Verbs first, calm always.** "Pack up this Hermes." "Check the new computer." No alarm
   styling except data-loss-risk moments (device-unlink warning, vault passphrase).
3. **Numbers over adjectives.** "41 skills — 6 written by your agent" beats "many skills."
   Every number is real scanner output.
4. **Every warning ships its fix.** A warning without a next step is a bug (doctor's
   manual-action pattern — digest §3).
5. **Never blame the user; never blame Hermes.** "This can't travel because WhatsApp links to
   one device" — cause, not fault.
6. **Two-sentence rule** (P1 §2): any concept explained where it appears, ≤2 sentences, no
   docs required for the happy path.
7. **One exclamation mark in the whole product** — on the final success screen.
8. **Jargon quarantine.** WAL, sidecar, provenance, zipapp never appear in the GUI happy path;
   they live in reports' technical appendices and docs.

Before → after examples:

| Raw engineering truth | Shipped copy |
|---|---|
| "gateway_state.json excluded (NS-508)" | "Runtime files stay behind — the new computer makes fresh ones. (Details in your report.)" |
| "WhatsApp Baileys creds.json is device-bound (c/d)" | "WhatsApp is linked to your old computer. After moving, scan the QR once — 1 minute. We put it on your checklist." |
| "sqlite3.backup() snapshot, WAL checkpoint" | "Taking a safe copy of your agent's conversation history (it can keep running)." |
| "one-shot run_at >120s past grace rejected" | "One scheduled task ('Reminder: renew domain') was due during the move. We'll ask before re-scheduling it." (cron §6) |

## 6. The docs set

All docs in-repo under `docs/`, plain Markdown, no site generator required (works on GitHub,
works offline — same self-containment ethos as constraint 3).

| Doc | Job | Key structure |
|---|---|---|
| `README.md` | Landing (§3) | as specified above |
| `docs/user-guide.md` | Task-oriented walkthrough | The two-machine journey (§4) with screenshots; headless/SSH chapter; profiles chapter (state §1.3); "lived-in target" chapter |
| `docs/faq.md` | Answers before questions are asked | Seeded from research (below) |
| `docs/troubleshooting.md` | Symptom → cause → fix | Keyed by error code: every error in the product prints `TAL-xxx` + one-line fix + deep link anchor (`#tal-503`). Categories: 1xx scan, 2xx pack, 3xx transfer/verify, 4xx preflight, 5xx apply, 6xx post-verify. Release gate: no error path without a code (§12) |
| `docs/comparison.md` | Full W1-W18 receipts | The README table (§7) links here; each row cites comp teardown |
| `docs/security.md` | Threat model | Secrets census method (state §2.2 canonical lists), vault format (scrypt params, AES-256-GCM), what the checklist contains, why no home-rolled crypto (constraint 6) |
| `docs/bundle-format.md` | The `.hermespack` spec | Opens with the SEO heading "What is a .hermespack file?"; eternal-header contract (§10.2); "bundles are archives, not lock-in — it's a zip; `unzip` works; the manifest is human-readable JSON" |
| `docs/cli.md` | Reference | Generated from argparse at build time; drift impossible |
| `CHANGELOG.md` | Keep-a-changelog | Bundle-schema changes get their own callout block per release |

FAQ seed list (each answer ≤5 lines, each grounded): Linux→Windows? (yes — layout translation,
digest §6.1) · Will WhatsApp keep working? (re-pair, integ §1.2) · Where are my API keys?
(checklist by default; vault opt-in) · Can I open the bundle by hand? (yes — zip) · Over SSH?
(yes — CLI parity, comp W15) · Both machines running? (retire plan, integ §8) · Different Hermes
versions? (§10.4 gate: update first — digest §6.8) · Is this official? (no) · My state.db is
30 GB (streams; size-capped integrity check — state §2.3) · Old `hermes backup` zip? (accepted,
degraded — backup precedent Interop).

## 7. The comparison table — and the honesty covenant

README shows ~10 user-meaningful rows collapsing W1-W18; `docs/comparison.md` carries all 18.
Columns: **Talaria · Hermes-Agent-Converter · `hermes backup` · DIY (scp the folder)**.

Rows (→ teardown items): Runs headless / over SSH (W1, W15) · Windows + full OS matrix (W2) ·
Knows what things *are* (W3, W16) · Keeps conversation history (W4 — they silently drop
`sessions/`) · Secrets safety (W5) · Device-linked & machine-bound intelligence (W6) · Path
rewriting that can't corrupt code (W7) · Transactional restore with rollback (W8, W9) ·
Live-database safety (W10) · "Will it work over there?" preflight (W11) · Stock vs. yours vs.
agent-written provenance (W12) · Verified result + shareable report (W13) · Tested & CI'd (W17) ·
Versioned bundle format (W18). `hermes backup` column is *respectful* — it's upstream's good
same-machine tool; we cite what it deliberately doesn't attempt (backup §"What it does NOT do").

**Honesty covenant (release law):** every competitor cell must trace to a teardown line; every
Talaria cell must trace to a passing acceptance scenario ID (§11). A claim without a test is
deleted before release — this is the mechanism behind the teardown's "kept honest" promise
(comp Verdict), enforced as a checklist item (§12).

## 8. Report deliverables — shareable single-file HTML

Both reports: one self-contained HTML file, inline CSS, zero external requests, printable,
light/dark. **Redacted by default so they are safe to attach to a support issue or share with a
teammate**; `--no-redact` for local full detail. Footer: tool version, bundle schema, hermes
knowledge stamp (§10.1), generation time. A raw-JSON `<script type="application/json">` appendix
makes every report machine-readable too (comp W15's scriptability, extended to reports).

### 8.1 System Overview Report — "everything your install touches"

Runs with or without packing (M3). Sections:

1. **Identity card** — Hermes version/tag/commit, install method (7-step detection — install §4),
   layout family, HERMES_HOME, profiles list, total size. Fills the "no on-disk state stamp"
   gap upstream has (state §5).
2. **The agent, in numbers** — memories count (§-split entries — state §2.1), skills by
   provenance (skills §5), cron jobs, sessions count, achievements (state §2.6).
3. **Inventory by family** — P2's taxonomy rendered: per-family counts, sizes, default
   disposition, expandable file lists. Includes the **"nothing unexplained" counter**: files not
   matching any rule appear under "Unrecognized" — target is 0 silent bytes (P2 §1).
4. **Provenance** — stock-pristine / stock-modified (with per-skill diff stats from the
   `.bundled_manifest` mechanism — skills §5) / hub-installed (lock.json) / agent-created
   (`.usage.json created_by` — skills §5).
5. **Integration surface** — per-platform/per-MCP/per-provider cards with class (a)/(b)/(c)/(d)
   (integ §7) translated to plain English ("travels" / "travels, needs address update" /
   "re-do on arrival" / "secret").
6. **Cron fleet** — per-job card: schedule, delivery route, script, workdir, skills used,
   dependency verdicts from the mirrored preflight (cron §4), notepad presence.
7. **Secrets census** — *names and locations only, never values* (state §2.2 canonical lists);
   count of the ~40 secret-bearing vars found (digest §2).
8. **Machine-bound register** — everything that will need re-doing, with its reason and its fix.
9. **Reaches outside HERMES_HOME** — external skill dirs, memory-provider homes, script/workdir
   references, with portability verdicts (digest §6.6, state §9).
10. **Health flags** — config floor, zeroed DBs, dangling references (state §2.3, §3).
11. **Technical appendix** — the jargon-quarantine zone: exact paths, hashes, rule citations.

### 8.2 Migration Report — the receipt

Generated at M12; also written on *failure* (a rollback produces a report saying so — the
anti-W13). Sections:

1. **Verdict banner** — Succeeded / Succeeded with checklist open / Rolled back (with cause).
2. **Source ↔ target identity cards** side by side (versions, OS, layout translation applied).
3. **What moved** — per-family counts + bytes, per-file SHA-256 verification totals
   (constraint 5).
4. **What was rewritten** — every path/host rewrite as before → after, grouped by file
   (the structured answer to W7's regex footgun).
5. **What was skipped and why** — using the stable status vocabulary adopted from claw-migrate:
   migrated/skipped/conflict/error/planned + stable reason strings (install §7).
6. **Conflicts and how they resolved** — kept-yours / took-bundle / merged, per item.
7. **Secrets Handoff Checklist state** — which of the named secrets have been re-provided
   (checked off), which remain.
8. **Finish checklist state** — the M11 cards with live status, incl. proof-of-life result
   (ticker heartbeat seen at HH:MM — cron §1.2).
9. **Verification** — hash pass/fail table, SQLite integrity results, `hermes doctor` summary if
   run.
10. **Rollback & undo** — where the pre-apply backup lives, exact restore command, retention.
11. **Timing** — per-phase durations (fuels the README's honest performance claims).
12. **Technical appendix + JSON.**

## 9. Screenshot plan

All screenshots are **fixture-generated, deterministic, and regenerated every release** — never
hand-taken, never from a real install (no leaked personal data; screenshots stay in sync with the
UI). Mechanism: `scripts/make_screenshots.py` drives the GUI via Playwright against the `demo-vps`
fixture install (m2c1 §Adopted: human-emulating Playwright testing), fixed clock, fixed hostname,
1600×1000, light + dark. Committed under `docs/img/`.

The canonical ten: S1 detect/greeting · S2 overview with family cards · S3 selection with
provenance badges · S4 secrets decision (checklist vs vault) · S5 pack progress → boarding pass ·
S6 target preflight matrix **with one honest red row** (a `.sh` cron on Windows — cron §4; we
market the red row, it is the product) · S7 apply progress · S8 finish checklist mid-checkoff ·
S9 success screen with agent stats · S10 the two HTML reports side by side. Plus the README hero
GIF (M6 pack loop, <3 MB). CLI gets three `<pre>`-styled "shots" in docs (pack, preflight, apply)
captured from the same fixture run.

## 10. Versioning & compatibility policy

### 10.1 Three version axes, printed together

`talaria --version` → `talaria 1.2.0 · bundle schema 1 (reads 1) · hermes knowledge v2026.8.13/0.20.1`.

- **Tool: SemVer**, promises defined in user terms: MAJOR = bundle schema major bump or CLI
  break; MINOR = new capability or new Hermes knowledge; PATCH = fixes. (Hermes itself is
  CalVer-tagged `vYYYY.M.D` — digest §0; we deliberately differ because our compat surface is
  contractual, not chronological.)
- **Bundle schema: single integer**, independent of tool version (constraint 5).
- **Hermes knowledge stamp**: the newest Hermes release whose internals this build understands —
  sets honest expectations when Hermes evolves faster than we ship.

### 10.2 The eternal header

`manifest.json` root keys frozen **forever**, across all future schema majors:
`schema_version` (int), `min_reader_tool_version` (semver string), `created_by_tool_version`,
`created_at`, `source` (hermes version/tag/commit/OS/layout). Any tool version — past or future —
can read these five and print the correct message. This is how a 1.0 tool tells the user
"this bundle needs Talaria ≥ 3.1" instead of a stack trace.

### 10.3 Compatibility rules (documented in bundle-format.md, enforced in CI)

1. **Read-forever:** tool N opens every schema ≤ its own, always. Enforced by **golden
   bundles**: `tests/fixtures/golden/schema-<v>/` is append-only; CI opens and applies every
   golden with the current tool on every commit. Old bundles are people's backups — refusing one
   years later is data loss.
2. **Additive-only within a major.** Readers ignore unknown manifest keys; appliers pass through
   unknown artifact kinds as *opaque items* placed only with explicit consent (the W16/W18
   answer, and digest §6's "graceful handling of unknown/future artifacts").
3. **`min_reader_tool_version` bumps are rare and justified** — only when older readers would
   corrupt data (e.g. a future vault v2). Prefer degrade-with-warning over refusal.
4. **`talaria convert`** re-packs an old-schema bundle to current (never required for reading).
5. **Salvage mode:** `talaria inspect --salvage <bundle>` uses the per-file SHA-256 record
   (constraint 5) to report exactly which members of a damaged bundle are intact and extract
   them. A migration tool's worst hour is a corrupted archive; we ship for that hour.
6. **Foreign-format grace:** a plain `hermes backup` zip is detected and accepted as a degraded
   input with explicit "no provenance / no preflight intelligence" warnings (backup §Interop).

### 10.4 Hermes-version skew policy (source ↔ target)

Preflight compares manifest `source.hermes` with the target install (digest §6.8): equal →
green · target newer → yellow ("Hermes will migrate your config forward on first run" —
table-driven config migrations, state §3) · target older → red gate ("update the new computer's
Hermes first: `hermes update`") · source `_config_version < 12` → red (upstream's own support
floor — state §3).

### 10.5 Runtime floor honesty

Constraint 4 says the zipapp is "runnable with any Python"; the truthful contract is **any Python
launches it, 3.9+ runs it**: `__main__.py` begins with a version check written in
ancient-compatible syntax so Python 2.7/3.5 print "Talaria needs Python 3.9 or newer — you have
2.7" instead of a SyntaxError. Not a constraint challenge — a wording precision we should adopt.

## 11. Test-of-truth acceptance scenarios

Ten end-to-end stories, phrased so the suite can encode them; each is the backing evidence for a
comparison-table claim (§7 covenant). "Fixture" = synthetic installs built by the test harness.

- **A1 — The $5 VPS move (canonical path).** Given a fixture Linux install with memories, 3
  modified skills, 1 agent-created skill, 4 cron jobs (one with script+workdir+notepad), sessions
  DB, and pairing state; when packed via CLI with defaults and applied on a clean Linux target
  entirely over CLI; then every family restores, per-file hashes verify, cron claims are
  scrubbed (cron §1.3), the checklist contains exactly the fixture's machine-bound items, and
  exit codes are 0. (comp W15; the primary persona.)
- **A2 — Cross-layout Linux → Windows.** Given the A1 source; when applied on a Windows target
  (`%LOCALAPPDATA%\hermes` — state §1.1); then path fields are translated per schema knowledge
  (never blanket regex — W7), the `.sh` cron job is flagged with the bash explanation (cron §4),
  secret files' 0600-equivalent handling is applied per platform (state §10.10), and the report's
  rewrite section lists every change.
- **A3 — Secrets never leak by default.** Given a source whose `.env`/auth files contain 40
  canary secret values planted under the known secret-bearing names (state §2.2 canonical lists);
  when packed with defaults; then a byte-level scan of the bundle finds zero canaries, and the
  Handoff Checklist names all 40 with provider URLs where declared
  (`setup.collect_secrets.provider_url` — skills §1).
- **A4 — Vault round-trip and honest refusal.** With `cryptography` present: vault packs,
  applies with passphrase, canaries restore 0600. Without it: pack refuses vault mode with the
  exact honest message (constraint 6) and offers checklist mode; wrong passphrase on apply is a
  clean TAL-4xx error, zero partial writes.
- **A5 — Power loss mid-apply.** Given an apply killed at a randomized point after staging;
  then the target equals its pre-apply state byte-for-byte (transactional rollback —
  constraint 7), and a Migration Report exists saying "rolled back" with the cause (§8.2).
- **A6 — The lived-in target.** Given a target with its own skills (one name-colliding),
  memories, and cron jobs; when applied; then nothing is overwritten without a recorded
  per-conflict decision, "keep yours" is honored, and the report's conflict section matches
  reality (W8).
- **A7 — Provenance tells the truth.** Given fixtures for all four skill classes (stock-pristine
  / stock-modified with known diff / hub-installed via lock.json / agent-created via
  `.usage.json`); then the Overview report classifies 4/4 correctly and the modified skill's
  diff matches the planted edit (skills §5 mechanisms, not reinvented hashes).
- **A8 — Cron fidelity under time.** Given jobs incl. an interval job with `last_run_at`, a
  monitor with `monitor_state` + baseline file, `context_from` chains, and a one-shot due during
  the move; then on target: claims null, interval anchoring preserved (cron §3.1), monitor does
  not false-alert (cron §7), the chain moved together, and the expired one-shot is surfaced for
  a decision, not silently dropped or re-fired (cron §6).
- **A9 — Hostile and huge inputs.** A >2 GiB SQLite uses the capped integrity strategy
  (state §2.3); a 400k-file cache tree is excluded by rule without scanning stall (backup
  precedent's 426,543-file incident); symlinks pointing outside HERMES_HOME are never followed
  (state §10.3); a crafted bundle with traversal members, absolute paths, or symlink entries is
  rejected with TAL-3xx (W9).
- **A10 — Reports stand alone.** Both HTML reports open from `file://` with zero external
  requests (asserted by parsing for refs), render printably, contain the JSON appendix, and the
  redacted default contains no secret values and no raw usernames in paths.

## 12. Release checklist

**Freeze & verify**
- [ ] A1–A10 green on the 3-OS CI matrix (Linux, macOS, Windows) + WSL smoke job.
- [ ] Python-floor check (vermin or equivalent) proves 3.9 compat; 2.7-stub message test (§10.5).
- [ ] Golden bundles for every past schema open + apply (§10.3.1); if schema changed this
      release: new golden committed, CHANGELOG callout written, `min_reader` decision recorded.
- [ ] Comparison-table audit: every cell traces to a teardown line or a passing A-scenario (§7).
- [ ] Copy pass: tone rules §5; no error without a TAL code + troubleshooting anchor; the one
      exclamation mark counted.

**Package**
- [ ] `talaria.pyz` built, byte-identical rebuild verified, runs the A1 pack on all 3 OSes from
      a *download* of the artifact (not the repo).
- [ ] pip package builds; `pip install` → `talaria --version` on 3.9 and current Python.
- [ ] SHA-256 sums published beside artifacts; release page body = quick start + promises.

**Docs & media**
- [ ] Screenshots + hero GIF regenerated from fixtures this release (§9); no stale UI.
- [ ] `docs/cli.md` regenerated from argparse; bundle-format.md matches the code's schema
      constants (asserted by a test, not by diligence).
- [ ] README quick-start commands executed verbatim by CI (doc-rot gate).

**Publish & day-0**
- [ ] Tag `v<semver>`; CHANGELOG section finalized; non-affiliation line present.
- [ ] Issue templates ask for the *redacted* Migration Report attachment (§8 makes this safe) —
      support quality is designed in.
- [ ] Known-issues doc seeded (e.g. Termux ticker caveat — cron §6).
- [ ] Post-release: fresh-VM download-and-run of A1 from the public release page.

## 13. What makes it massively rewarding — the delight details

Every item below is grounded; none is confetti.

1. **The arrival stats.** Success screen: *"Your agent arrived with: 214 memories, 41 skills —
   6 it wrote itself — 12 scheduled jobs, 1,842 conversations."* All real: §-split memory
   entries (state §2.1), `.usage.json created_by` (skills §5), jobs.json, state.db sessions
   (state §2.3). This is the moment the product is *about*; everything else exists so this
   screen can be true. The single permitted exclamation mark lives here.
2. **The boarding pass.** Pack ends with a luggage-tag card (GUI) / ASCII card (CLI): bundle
   name, date, source machine, contents one-liner, fingerprint. Users screenshot this; it is
   the shareable proof-of-care the competitor's "SKIPPED file: exc" list will never be (W13).
3. **The soul made the trip.** The Migration Report closes by quoting the first line of the
   restored SOUL.md. (The psychopomp idea from §2, spent where it belongs — in one line of copy.)
4. **Proof of life, not promise of life.** The scheduler card turns green only when the target's
   own fresh `ticker_heartbeat` appears (cron §1.2) — we watch the new heart start beating
   rather than asserting it will.
5. **`talaria why <path>`.** Instant answer for any file: what it is, whether it travels, and
   the cited reason ("gateway_state.json — stays: restoring it cross-machine broke hosted
   gateways, NS-508" — digest §2). P2's `--explain` surfaced as a first-class command; turns
   the research corpus into a user feature.
6. **The zero-unexplained counter.** Overview report proudly shows "0 unexplained files" (or
   honestly shows 3 and lists them). Comprehensiveness made visible and falsifiable (P2 §1).
7. **Streak preserved.** Achievements JSON migrates (state §2.6) and the success screen says so.
   Small, silly, deeply human.
8. **A checklist that finishes.** M11 cards check off with persisted state and the report
   updates live — the last item flipping the whole banner to "Migration complete" is the
   endorphin hit Apple's assistant ends on.
9. **Respect as delight:** no telemetry, no network, no account, reports redacted by default,
   bundles openable with `unzip`. Stated plainly in README §7. Trust is the feature users
   evangelize on the Hermes Discord.
10. **The honest red row.** Marketing screenshots include a FAIL row (§9 S6). Nothing builds
    faith in green like a product willing to show red.

## 14. Constraint challenges and committee handoffs

**CONSTRAINT CHALLENGES: none.** From the release lens the constraints are assets, and I will
defend them in committee: stdlib-only core (constraint 1) means zero dependency-hell support
tickets on machines that don't even have Hermes yet; 3.9 floor (2) covers aged VPS images;
browser GUI + CLI parity (3) matches where installs actually live (comp W1/W15); one-file bundle
(5) is the product; secrets-out-by-default (6) is the security story; transactional apply (7) is
promise 2. One wording precision to adopt, not a challenge: constraint 4's "any Python" should
read "any Python launches it with a friendly floor message; 3.9+ runs it" (§10.5).

**Handoffs for the committee:**
1. Ratify the naming lock (§2) across P1/P2/P4 — descriptor rule everywhere, `.hermespack`
   docs page owns the search term.
2. Ratify the eternal-header contract (§10.2) *before* any packer code lands — it cannot be
   retrofitted.
3. Ratify the §7 honesty covenant as release law binding on all future claims.
4. Confirm M8's "print the pinned installer command, don't execute it" stance against P1's
   simplicity budget (I hold: executing upstream's curl|bash inside our tool trades one click
   for owning every installer failure on machines we don't control).
5. Reports (§8) are the shared UI substrate — P2's taxonomy renders into §8.1's sections;
   engineering should treat report sections as a stable public interface with fixtures.
