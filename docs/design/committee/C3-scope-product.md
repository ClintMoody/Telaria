# C3 — Scope & Product Adversary: Critique of P1–P4

Reviewer charter: the northstar is BOTH "stupidly simple" AND "insanely comprehensive."
I attack every place a proposal buys one with the other, every contradiction between proposals,
and every gram of v1 gold-plating. Priority vocabulary used below: **v1** (ships), **v1.1**
(first follow-up), **v2** (later). Citations: proposals P1–P4; research as `docs/research/*`.

Overall: the four proposals are unusually compatible — one engine, three lenses (P1 §15) is the
right spine, and P2/P3 supply the engine that makes P1's simplicity honest. But they ship **three
error-code systems, two exit-code tables, two wizard spines, two installer stances, and a secrets
definition that contradicts two default-ON categories.** Those must be settled before code.

## 1. Verdict table

| # | Element | Source | Verdict | Required change |
|---|---|---|---|---|
| 1 | Name = Talaria + descriptor lock ("moves your Hermes agent to a new computer") + non-affiliation line | P1 §3, P2 §17, P4 §2 | **ADOPT (settled, final)** | All four converge. Default filename per P4: `hermes-<host>-<date>.hermespack` (drop P1's `hermes-move-` variant). |
| 2 | Two-decisions-per-side budget; all other choices defaulted | P1 §2, §6.1 | **ADOPT** | Becomes an acceptance criterion (see §3 audit). Any new wizard question must name a user who answers it better than the research does. |
| 3 | Migration Intent (replace/clone) as **the first wizard question** | P2 §4.4 | **MODIFY** | Keep the switch in the engine, manifest, CLI (`--intent`) and Customize. Remove it from the wizard: default `replace` silently. A novice cannot answer "replace vs clone," and it busts the P1 budget P4 (M5) also adopts. Clone stays v1 (it is a filter set + install_id rotation, and it prevents the worst silent-failure class), reachable by the users who can name it. |
| 4 | Wizard spine `Detect → Intent → Inventory tree → Review → Pack` | P2 §14 | **REJECT (as novice path)** | P1's S0–S4/T1–T4 is the only spine. P2's Inventory/Review screens become the "Customize in detail" drawer (P1 §15 lens 2) and `inspect` surfaces. P2 §14 rewritten to match. |
| 5 | 20-family / ~70-leaf taxonomy + composite class model + Unrecognized bucket | P2 §2 | **ADOPT** | Engine-level truth. Must ship with an explicit N:1 mapping onto P1's six wizard categories (nothing unmapped). |
| 6 | Coupling-rules engine | P2 §4.3 | **ADOPT (P0 shared infra)** | P1's "indivisible category" promise is only true because of this engine; it must also gate apply-time `--only/--skip` re-narrowing (P2 #8), or apply can strip `notepad.db` from under a job. State this in the spec. |
| 7 | Bundle "carries superset; apply narrows" | P2 §10 | **MODIFY** | Ambiguous and privacy-hostile as worded. Spec language: **pack writes exactly the pack-time selection; apply may narrow, never widen.** "Superset" means superset of later apply narrowing only. |
| 8 | Secrets = checklist default, vault opt-in, honest refusal | P1 §7, P2 §2.3, P4 M5 | **ADOPT** | With finding §2.1's two-tier definition (credential vs sensitive-content) written into the spec — constraint 6 is currently self-contradictory with two default-ON categories. |
| 9 | "Safe to carry on a USB stick" checklist-mode copy | P1 §7 | **MODIFY** | Overclaim: the bundle still holds conversations + pairing grants (class (d) content, integ §7). Ship: "no keys or passwords inside." |
| 10 | Keys checklist saved as **PDF**/HTML | P1 §8 | **REJECT (PDF)** | Stdlib cannot write PDF (constraint 1). HTML only, print-to-PDF via the browser. P4 M6's `<bundle>.checklist.html` auto-write + button is the merge. |
| 11 | "Install Hermes for me" executes official installer | P1 §10.1 | **DEFER to v1.1** | Adopt P4 M8 for v1: print/copy the commit-pinned command, poll for Hermes appearing so the user never clicks "check again." Executing a 3,467-line third-party installer inside our tool means owning its every failure on machines we don't control (P4 handoff 4). Not a decision removed — only an execution moved. |
| 12 | Transactional apply, WAL journal, auto-rollback, both-sides registry, SQLite protocol, skew classes | P3 §2–§9 | **ADOPT** | Core v1. |
| 13 | Crash **resume-and-continue** (`apply --resume`) | P3 §2.4 | **DEFER continue-path to v1.1** | v1: journal replay offers **rollback only** (safe, satisfies A5). The hash-based idempotent continue is real engineering for a rare path; the journal format already supports adding it later. |
| 14 | `--strict-verify` / withheld commit / `talaria commit` (exit 7) | P3 §4.3 | **DEFER to v1.1** | Two-phase interactive commit is a power feature in the reliability path. Reserve exit code 7 now so numbering never shifts. F16 v1 behavior: advisory checks always commit + report. |
| 15 | Exit-code table 0–5 | P2 §10 | **REJECT** | Collides with P3 §13 at codes 2/3/4/5 with different meanings — fatal for scripts. P3's 0–9 wins (it encodes "only 5/6/7 touched the target"). P2 adopts it. |
| 16 | Error IDs: `WA-DEVICE-LINK` (P1 §13) + F01–F22 (P3 §12) + TAL-xxx (P4 §6) | all | **MODIFY — one registry** | Single user-facing namespace **TAL-xxx** with P4's troubleshooting anchors; P3's F-catalog maps 1:1 into it (internal ids allowed in code); P1's mnemonics become searchable aliases in docs at most. No error ships without a TAL code (P4 gate adopted). |
| 17 | Preflight verdict vocabulary (OK/OK-AFTER-REWRITE/ACTION/MISSING-INSTALLABLE/IMPOSSIBLE/UNKNOWN-OFFLINE) | P2 §6 | **ADOPT** | Engine emits P2 vocabulary; wizard renders P1 §10's who-acts groups via a **fixed mapping table** (OK→Ready; OK-AFTER-REWRITE→Fixed automatically; ACTION+MISSING-INSTALLABLE+UNKNOWN-OFFLINE→Needs you; IMPOSSIBLE→Can't come along). Mapping goes in the spec, or GUI and CLI drift. |
| 18 | Full dependency-matrix **GUI grid** | P2 §6, §15 | **DEFER to v1.1** | v1: CLI table + who-acts groups + per-row "why" drilldown. Grid is presentation, not capability. |
| 19 | Predictive per-target-OS deps at pack/inspect time | P2 §6 mode (i) | **ADOPT (v1)** | Brief-verbatim ("flag what is impossible on the target system") — and currently has **no acceptance scenario**; see §4 gap G2. |
| 20 | Diff surfaces: skills (upstream semantics), config-vs-DEFAULT_CONFIG, checkout | P2 §5 | **ADOPT (CLI + report v1)** | Brief-verbatim stock-vs-custom. GUI side-by-side viewer defers to v1.1 (P2 already says so). Config diff degrades honestly when no venv. |
| 21 | Deep-Scan agent assist (generate + nonce/schema ingest + corroborate; advisory-by-construction) | P3 §10.3, P2 §13.4, P4 M4 | **ADOPT (v1, CLI-first)** | Settles the P2("P1 priority") vs P4(in-wizard) tension: the brief names this the hardest problem, so v1 ships `talaria deepscan generate|ingest` + P3's trust model; the GUI card is a dismissible non-decision (P4 M4). Needs an acceptance scenario (§4 gap G3). |
| 22 | Log-mining evidence layer (32 MiB tail scans) | P3 §10.2 | **DEFER to v1.1** | Static refs + state.db/`.usage.json`/cron-output mining + Deep-Scan already triangulate day-to-day usage. Log grep is the lowest-signal, highest-noise layer. |
| 23 | Device-linked force-includes (WhatsApp session, Matrix store, signal-cli, chrome-debug) | P2 §12 (P0/P1), P1 §15 | **DEFER all to v1.1** | v1 excludes device-linked stores, period; checklist re-pair is a 1-minute, always-correct path (integ §1.2). The upside of copying is minutes saved; the downside is account unlinking/Olm corruption we cause at launch. Cuts a whole hazard class and the scariest warning UI from v1. |
| 24 | Expert toggles marked P1 in P2 §12 (basic_auth rotate, executions.db carry, state.db cwd rewrite, cap override, custom regex rules) | P2 §12 | **DEFER as marked** | Keep P0-marked ones except WhatsApp copy (see #23). Camoufox pin, install_id keep/rotate, dirty-patch replay, live-pack lock honor: v1. |
| 25 | Degraded `hermes backup` zip **apply** | P1 §9, P2 §9 (P1), P3 §9.3 | **DEFER apply to v1.1** | v1: detect the format, say what it is, and point at upstream's own `hermes import` (it exists on the freshly installed target) plus our checklist knowledge. Full degraded ingestion is a second input format with its own test matrix. Revisit if implementation shows >70% scanner reuse. |
| 26 | CLI surface: 15 subcommands + presets + config-file jobs | P2 §10–§11 | **MODIFY** | v1 set in §6. Cut `select`/`presets`/`plan` as commands (fold: selection files + `--include/--exclude`; plan = `apply --dry-run --emit-plan` then `apply --plan`). Built-in presets: 3 (`everything-portable`, `essentials`, `identity-only`). `vaulted-full` REJECT — redundant with `--vault`; `full-forensic` defer. Config-file jobs (`talaria.json`) v1.1. |
| 27 | Reports: P3 report.json schema; P4 two HTML reports w/ JSON appendix; P2 `report --format` | P3 §14, P4 §8 | **ADOPT — one data model, three renderers** | Single schema (P3) renders to json/md/html. Overview report is the brief's "comprehensive overview" and runs without packing (P4 M3) — v1 mandatory. Migration report also on rollback. Unify path: `$HERMES_HOME/migration/talaria/<ts>/` (P1 §12 drops its variant). |
| 28 | Eternal header + golden-bundle read-forever CI + salvage | P4 §10 | **ADOPT (ratify before packer code)** | Salvage = flag on `inspect` (per-file SHA-256 makes it nearly free). `talaria convert` defers to v2 (P4 itself: never required for reading). |
| 29 | Old-machine-off: pack-time retire coaching (P4 M7) + finish-screen hard gate (P1 §12) + hazard-gated start (P3 §11) | P1/P3/P4 | **ADOPT merged** | One canonical sequencing sentence in spec: old gateway may run through apply+verify; it must be OFF before target gateway starts. Gate copy adapts under `--intent clone` (acknowledge-hazards instead of require-off) — otherwise the gate contradicts clone mode. `talaria decommission` as a command defers to v1.1; v1 ships its content as checklist cards. |
| 30 | Proof-of-life heartbeat watch; arrival stats; boarding pass; `talaria why`; honesty covenant; TAL-gated release checklist | P4 §4, §7, §11–§13 | **ADOPT** | Cheap, grounded, and the reason people evangelize. `why` reads the registry we already ship. Set expectation in copy that the first heartbeat can take ~60 s (60 s ticker, cron §2.1). |
| 31 | Bundle-vs-bundle compare, history trimming, delta bundles, signing, TUI, post-run hooks | P2 §9/§11/§15 | **DEFER v2** | As P2 itself marks. Post-run hooks also a security surface — keep out until sandboxing story exists. |
| 32 | Constraint-4 wording ("any Python launches it; 3.9+ runs it", 2.7-parseable stub) | P4 §10.5 | **ADOPT** | Wording precision, not a challenge. |

## 2. Cross-proposal contradictions (the ones that break coherence)

**2.1 The secrets definition is self-contradictory — my strongest finding.** Constraint 6 says
"secrets excluded by default." Integ §7 classifies **pairing stores and `state.db` conversations
as (d)** — yet P1 §6.1 and P2 §2.9/§2.7 default both ON (correctly: grants and history ARE the
migration). So either the defaults violate the constraint or "secrets" is undefined. Required
change: the spec defines two tiers inside secret-flagged items — **SECRET-CREDENTIAL** (env keys,
tokens, auth.json, mcp-tokens, inline config keys… seeded from Hermes' own classifier lists,
state §2.2) → excluded → checklist/vault; **SENSITIVE-CONTENT** (conversation DBs, pairing
grants, memories) → travels by default, named in the report as private content. P2's composite
`{class, secret, machine_bound}` model already almost expresses this — add `secret_kind`.
Then fix P1's USB copy (verdict #9). Without this, A3's canary test passes while the bundle
still ships private data under a "safe" label.

**2.2 Installer execution.** P1 §10.1 runs the installer; P4 M8 refuses to. Resolved verdict #11
(P4 wins v1; auto-poll removes the friction P1 feared).

**2.3 Exit codes and error IDs.** Two incompatible exit tables (P2 §10 vs P3 §13) and three error
namespaces (P1/P3/P4). Resolved verdicts #15/#16. This is the kind of drift that later costs a
major version — settle now.

**2.4 Wizard vs tree.** P2 §14 puts Intent + Inventory + Review into the spine; P1 makes them a
drawer. Resolved verdicts #3/#4. The measurable rule: the novice path renders **six category
rows**, never the 20-family tree; the tree exists one click away, pre-scrolled from every
"what's this?" link (P1 §15).

**2.5 Preflight presentation.** Three renderings of the same data (P1 who-acts, P2 verdict grid,
P4 doctor-style). Resolved verdict #17 with the mandatory mapping table — this was the likeliest
spot for GUI/CLI to show different truths.

**2.6 Deep-Scan priority.** P2 defers what P4 puts in the wizard and the owner calls the hardest
problem. Resolved verdict #21: v1, CLI-first, advisory-by-construction, non-blocking card in GUI.

**2.7 Minor unifications.** Report/checklist path (verdict #27); default bundle filename
(verdict #1); checklist auto-write + save button (verdict #10); heartbeat expectation copy
(verdict #30).

**2.8 The missing map: P1's six categories ↔ P2's 20 families.** Verdict #5 demands it; here is
the starting table the spec must finalize (every P2 family maps somewhere; nothing double-maps
as payload):

| P1 wizard category | P2 families absorbed |
|---|---|
| Personality & memories | Identity & Memory; External state (memory-provider dirs) |
| Skills & plugins | Skills; Plugins; skill-bundles |
| Scheduled tasks | Automations (cron) incl. `$HH/scripts/` |
| Conversations & history | Conversations & History (state.db, response/memory/verification DBs, sessions, exports) |
| Connections & pairings | Messaging platforms (a)-class; MCP servers; pairing; channel routing |
| Settings, projects & boards | Configuration; Boards & Projects; Dashboard/webhooks/observability config; Desktop app JSONs |
| Keys & passwords (mode chooser, not a checkbox) | Secrets family (SECRET-CREDENTIAL tier per §2.1) |
| Won't travel (informational) | OS integration; Code & runtime (record-only); machine-bound + device-linked registry |
| (invisible, always-on) | Unrecognized bucket — carried under quarantine prefix, listed in report (P3 F22) |

Two families deliberately have no checkbox anywhere in the wizard: record-only Code & runtime
(it is metadata) and Unrecognized (silently dropping it would be the W16 sin; silently asking
about it would be a question no novice can answer — carry + report is the only coherent default).

**2.9 Coupling engine must bind apply, not just pack.** P2 §4.3 specifies the rules in the
selection tree; P2 §10 separately allows `apply --only/--skip`. Nothing says the narrowing passes
through the same engine. Without that sentence, `apply --skip 'cron/notepad.db'` builds at the
target exactly the silently-broken partial unit the coupling engine exists to prevent. One
engine, both sides, stated in the spec (and a test: apply-narrowing that violates a hard couple
exits 3 with the couple named).

## 3. Happy-path decision audit (the ≤6 gate)

Counting **meaningful decisions** (a screen where the novice must choose among options, not a
single-CTA click-through) across the merged design, source to target:

| # | Moment | Decision? | Notes |
|---|---|---|---|
| — | S0 "Pack up this Hermes" | no | single CTA; role auto-detected (P1 §4) |
| — | S1 scan | no | starts immediately, no options screen (P1 §5) |
| — | S2 review | no | glance-and-confirm; all boxes pre-checked from research defaults |
| 1 | S3 secrets mode | **yes** | checklist (default) vs vault — the one real source choice |
| 2 | S4 save location | **yes (weak)** | sane default offered; counts, barely |
| — | T1 open bundle | no | auto-found, provenance card |
| — | T2 preflight | no | verdicts grouped by who-acts; no choices embedded |
| 3 | T2→T3 "Move everything in" | **yes** | the consent moment |
| c1 | lived-in target | conditional | replace-with-safety-copy vs cancel (P1 §10.4) |
| c2 | vault passphrase | conditional | only if vault chosen at #1 |
| 4 | T4 old-machine-off tick | **yes** | the hard gate (P1 §12) |
| — | T4 checklist work | no | actions, not choices; each card one verb |

**Typical path: 4 decisions. Worst case: 6. PASS** — but only because verdicts #3 and #4 strip
P2's Intent question and Inventory/Review wizard steps. With P2 §14 as written the typical path
is 7+ and opens with "replace or clone?" — the one question in the whole design a novice
genuinely cannot answer, sitting in position one. The deepscan card (P4 M4) must remain
dismissible-without-choice or it silently becomes decision 5; same rule for any future "helpful"
card — the budget is a gate, not a guideline (G6 makes it executable).

## 4. Owner's-brief coverage audit (verbatim → scenario)

| Brief phrase | Covered by | Gap |
|---|---|---|
| "single self-contained bundle … restores it" | A1; constraint 5 | — |
| "across Windows/macOS/Linux" | A2 + A1 on 3-OS CI (P4 §12) | — |
| "compare stock vs user/agent-customized content" | A7 (skills only) | **G1: extend A7** to config.yaml-vs-DEFAULT_CONFIG sections and SOUL.md-vs-`default_soul.py` (install §8) — "content" is more than skills. |
| "list dependencies for crons and everything else and flag what is impossible on the target system" | A8 (fidelity), A2 (.sh flag) | **G2: new scenario A11** — pack on Linux, `inspect --deps --target-os windows|macos` yields correct IMPOSSIBLE/ACTION verdicts **with no target machine present** (predictive mode has zero test coverage today). |
| "comprehensive overview of everything the install touches" | P4 §8.1 + A10 | **G4 (minor):** assert Overview content on the fixture — zero-unexplained counter = 0, all planted touchpoints listed. |
| "works on any system" (before Hermes exists) | P2 §9 inspector claim | **G5: CI job** running `inspect`/`preflight`/`checklist` on bare `python:3.9` with no Hermes — the claim is currently untested. |
| "agent-assisted discovery … self-reports can't be fully trusted" | P3 §10.3 design only | **G3: new scenario A12** — agent report with one real path, one fabricated path, one stale nonce → real corroborated, fabricated quarantined to "agent said, unverified," stale rejected, capture set byte-identical. |
| "stupidly simple" | none | **G6 (cheap):** transcript test — `talaria pack` interactive with all-Enter answers asks ≤2 questions and produces a bundle. Turns P1 §2 from prose into a regression gate. |

## 5. CLI/GUI parity — realistic, with one honest caveat

Parity holds because there is one job engine and one event stream (P2 §10: GUI consumes the same
ndjson the CLI prints) and one failure catalog (P3 §12). Realistic: linear wizard as numbered
prompts (P1 §16), secrets paste-back via `getpass`-style no-echo prompts writing `.env` 0600,
checklist resume, heartbeat watch (`verify --watch`). **Not realistic and must be said out loud:
the Customize tri-state tree has no interactive text equivalent without curses** (P2 rightly
parks TUI at v2). Spec sentence required: *parity is capability parity — every GUI action has a
flag/JSON-selection equivalent — not interaction parity for the tree.* This prevents a
half-curses tree creeping into v1 under the "parity" banner.

## 6. The v1 cutline

**v1 ships (exact list):**
- Engine: resolver-order detection; per-profile scan, both layout generations; P2 taxonomy +
  Unrecognized bucket; provenance (bundled_manifest/.usage.json/lock.json/org; config-vs-default;
  SOUL-vs-default; checkout git); coupling-rules engine (pack AND apply narrowing); machine-bound
  registry both-sides + scrubs; SQLite protocol (P3 §5); deps engine — predictive per-OS +
  live preflight; structural rewrite engine with preview/needs_review (P3 §8); transactional
  apply w/ journal + auto-rollback + post-commit `rollback` (resume-continue deferred);
  two-phase verify (advisory never blocks); skew classes; zip64 streaming bundle, schema 1,
  eternal header, selection record; intent replace/clone (engine+CLI only); vault via
  `cryptography` + honest refusal.
- CLI: `talaria` (wizard), `scan`, `diff` (skills|config|checkout), `deps`, `pack`, `inspect`
  (--verify/--cat/--extract/--deps --target-os/--checklist/--salvage), `preflight`, `apply`
  (--dry-run/--emit-plan/--plan/--only/--skip/--intent/--yes), `verify`, `rollback`, `report`,
  `checklist`, `deepscan generate|ingest`, `why`, `gui`; `--json` everywhere; ndjson progress.
- GUI: P1 screens S0–S4/T1–T4 + Customize drawer (tri-state tree, consequence sentences, plain
  search) + persisted checklist + paste-back + heartbeat proof-of-life.
- Product: two HTML reports (one data model); TAL-xxx registry + troubleshooting doc; README per
  P4 §3; golden-bundle CI; honesty covenant; A1–A10 **plus A11/A12 and the G1/G5/G6 additions**.

**v1 explicit non-goals (say so in README):** device-linked store copying (re-pair is the path);
degraded `hermes backup` zip apply (detect + guide to `hermes import`); installer execution;
profile mapping/rename; named custom presets + config-file jobs; GUI diff viewer / deps grid /
rewrite-plan editor; crash resume-continue; `--strict-verify` deferred commit; log mining;
`decommission` command; `convert`; managed/NixOS and in-container Docker **targets** (detect +
refuse with guidance, per P3 PF-05); Termux target = supported with the ticker caveat card;
bundle-vs-bundle, trimming, deltas, signing, TUI, post-run hooks (v2).

**Deferral rationale + the v1 fallback each one stands on** (no deferral may strand a user):

| Deferred item | Why it is gold-plating for v1 | v1 fallback that works today |
|---|---|---|
| Device-linked store copy (#23) | Saves ~1–5 min per platform; failure mode is account unlink / Olm corruption *we* caused, at launch, invisibly delayed (integ §1.2, §8) | Checklist re-pair cards with exact commands; always correct |
| Degraded backup-zip apply (#25) | Second input format, own edge matrix (prefix stripping, no hashes, secrets inside) | Detect + name it + point at upstream `hermes import` on the target |
| Installer execution (#11) | We own every failure of a 3,467-line script on machines we don't control | Copy-button pinned command + auto-poll until Hermes appears |
| Crash resume-continue (#13) | Idempotent replay engineering for a rare path; rollback already makes crashes safe | Journal-driven rollback offer on next run (A5 covers it) |
| `--strict-verify` deferred commit (#14) | Interactive two-phase state machine for experts | Advisory checks report; `talaria rollback` post-commit exists |
| Log mining (#22) | Lowest-signal evidence layer; three other layers triangulate | Static refs + DB mining + Deep-Scan skill |
| Profile mapping (P2 §7) | Rename/promote is surgery with reference rewrites | Same-name restore; profiles carried verbatim |
| Config-file jobs + custom presets (#26) | Convenience wrapper | `pack --yes --include/--exclude -o` is already cron-able |
| GUI diff/grid/plan editors (#18, #20) | Presentation over existing capability | CLI + report render the same data |
| Decommission command (#29) | Command wrapper around printed guidance | The guidance ships as finish-checklist cards |

Every deferral keeps its data model in v1 where retrofit would be breaking (intent in the
manifest, exit 7 reserved, journal fields for resume) — deferrals are cuts of surface, not of
schema.

## 7. Constraint challenges

None raised here. Two spec-level clarifications adopted instead of challenges: P4 §10.5's
constraint-4 wording, and the §2.1 two-tier secrets definition, which is the committee *honoring*
constraint 6 by defining it precisely enough to be testable.

## 8. What I will hold the line on in plenary

1. **Verdicts #3/#4** — the wizard never grows a question or a tree; that is the product.
2. **§2.1 two-tier secrets** — without it we ship a bundle labeled "safe" that carries a user's
   entire conversation history.
3. **One exit-code table, one TAL registry** — settled before the first `sys.exit()` is written.
4. **The cutline in §6** — every v1.1 item has a working v1 fallback path today; nothing deferred
   strands a user.
