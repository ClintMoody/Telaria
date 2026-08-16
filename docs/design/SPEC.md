# Talaria — Binding Product Specification (v1)

Status: **BINDING**. This document supersedes the four proposals (P1–P4). Committee verdicts
(C1 security, C2 cross-platform, C3 scope) are incorporated as written; where critics conflicted,
the arbitration is recorded in the Decisions table. Research citations use the shorthand of the
proposals: `digest`, `state`, `skills`, `cron`, `integ`, `install`, `backup`, `comp` →
`docs/research/*.md`. Companion document: `docs/design/ARCHITECTURE.md` (binding technical design).

---

## 1. Product identity

- **Name:** **Talaria** (final; all four proposals and the committee converge). CLI command
  `talaria`; bundle extension `.hermespack`; PyPI distribution `talaria-migration`, import
  package `talaria`.
- **Tagline (descriptor lock — the name never appears in an H1, masthead, or `--help` line 1
  without it):** *"Talaria — moves your Hermes agent to a new computer."*
- **Non-affiliation line (README + About):** *"Community tool. Not affiliated with Nous Research."*
- **Definition:** Talaria packages a Hermes Agent installation — soul, memories, skills (including
  the ones the agent wrote itself), scheduled jobs, conversations, pairings, and configuration —
  from one machine into a single self-contained `.hermespack` file, and restores it on another
  machine across Linux/macOS/Windows/WSL/Termux. It understands what every file *is* (typed
  inventory with stock-vs-modified provenance), what every job and skill *needs* (dependency
  verdicts per target OS, including "impossible here"), keeps credentials out of the bundle by
  default (Secrets Handoff Checklist; opt-in encrypted vault), captures read-only, applies
  transactionally with automatic rollback, and ends with a verified result, a finish checklist,
  and a shareable report. Default bundle filename: `hermes-<hostname>-<YYYY-MM-DD>.hermespack`.
- **The Three Promises** (verbatim, on every data-touching screen and in the README; product law):
  1. "Nothing on this computer is changed or deleted." (read-only capture)
  2. "Anything we change on the new computer can be undone." (transactional apply + rollback)
  3. "Anything we can't move automatically goes on your checklist. Nothing silently vanishes."

## 2. Decisions table

Every contested point, with ruling and one-line rationale. CH = committee change honored.

| ID | Ruling | Rationale |
|---|---|---|
| D1 | Name **Talaria** final; descriptor lock; non-affiliation line; filename `hermes-<host>-<date>.hermespack` | All four proposals converge; extension owns the "hermes" search term (P4 §2; C3 #1) |
| D2 | Secrets split into **SECRET-CREDENTIAL** (excluded → checklist/vault) and **SENSITIVE-CONTENT** (travels, labeled private); P1's "safe to carry on a USB stick" copy DELETED, replaced by the "private notebook" copy | Constraint 6 was self-contradictory with integ §7's (d) classing of conversation DBs (C1 SEC-01, C3 §2.1) |
| D3 | One exit-code table: **P3 §13 (0–9) verbatim**; P2's 0–5 dropped; exit 7 reserved (unused v1) | Codes 5/6/7 encode "only these touched the target"; collision at 2–5 is fatal for scripts (C2-18, C3 #15) |
| D4 | One error registry: **TAL-xxx** user-facing; P3 F/PF codes and P1 mnemonics become internal aliases; no error ships without a TAL code + troubleshooting anchor | Three namespaces = drift (C2-18, C3 #16; P4 §6 gate adopted) |
| D5 | Wizard spine = **P1 S0–S4 / T1–T4**; P2's Intent/Inventory/Review screens become the Customize drawer + `inspect` surfaces; the 6-category ↔ 20-family mapping table (§7.3) is binding | Novice path renders six rows, never the 20-family tree (C3 #3/#4/§2.8) |
| D6 | Migration Intent (replace/clone) **leaves the wizard**: default `replace` silently; `clone` reachable via `--intent clone` and Customize; intent recorded in manifest | The one question a novice cannot answer, removed from position one (C3 #3) |
| D7 | Installer: **print the commit-pinned official command, never execute it**; auto-poll until Hermes appears; always interpose `hermes gateway stop` between install and preflight | Failure ownership + supply-chain optics (C1 SEC-18, C3 #11); installer's `maybe_start_gateway` would trip PF-01 (C2-17) |
| D8 | Conflict UX: wizard = **replace-with-safety-copy or cancel** only; per-conflict policies (`--conflict keep|overwrite|rename|ask`) live in CLI/Customize; scenario A6 covers that path | Novice merge corrupts two installs into one (C2-19, C3 verdict; P1 §10.4) |
| D9 | Unrecognized files: capture gated by content scan + secret-variant name rules (suspicious ⇒ credential handling; large/binary ⇒ record-only); carried items are applied only under **disclosed consent** — GUI: listed row inside the existing "Move everything in" consent; CLI: `--yes` alone skips them, `--include-unrecognized` places them | Arbitration of C1 SEC-03 (consent) with C3's decision budget (no new wizard question); P3 F22's default-carry wording replaced |
| D10 | Coupling-rules engine binds **pack AND apply narrowing**; pack writes exactly the pack-time selection; apply may narrow, never widen; a narrowing that violates a hard couple exits 3 naming the couple | Prevents apply from rebuilding the broken partial units the engine exists to prevent (C1 SEC-21, C3 #6/#7/§2.9) |
| D11 | Preflight: engine emits P2's verdict vocabulary (OK / OK-AFTER-REWRITE / ACTION / MISSING-INSTALLABLE / IMPOSSIBLE / UNKNOWN-OFFLINE); wizard renders P1's who-acts groups via the fixed mapping in §8.2 | One data model, two renderings, no GUI/CLI drift (C3 #17) |
| D12 | Vault: full C1 SEC-13 spec (scrypt N=2^17/r=8/p=1, 16 B salt, HKDF subkeys, AES-256-GCM, 96-bit nonces, AAD binding, manifest MAC, no argv/URL/log passphrase, empty refused). **Crypto sourcing arbitration: `cryptography` provides BOTH Scrypt and AESGCM** (C2-24 over C1's `hashlib.scrypt` note) | One import probe = one honest failure mode; `hashlib.scrypt` is absent on some LibreSSL builds |
| D13 | Canary test (A3) arbitration: adopt C1 SEC-02's member-scoped assertions (credential canaries absent everywhere; content canaries only inside members labeled SENSITIVE-CONTENT; lock-everything ⇒ zero plaintext anywhere; reports/checklists ⇒ zero) **plus** C2-15's `docs/security.md` disclosure | The two critiques are compatible: C1's formulation never asserts zero canaries bundle-wide in default mode |
| D14 | Skill provenance hashes are **OS-parameterized** and the semantics recorded; on cross-OS apply, `.bundled_manifest` entries for stock-pristine skills are rebaselined with target-OS semantics in stage | `_dir_hash` uses OS-dependent separators/collation; unfixed, cross-OS apply freezes every stock skill's updates (C2-01, verified skills_sync.py:254-265) |
| D15 | GUI server hardening package: 127.0.0.1 literal bind, one-time URL bootstrap token exchanged for a ≥128-bit header token, strict Host+Origin validation, no-referrer/frame-deny/nosniff/CSP, secrets only in POST bodies, no token in logs, shutdown on completion | Token-in-URL alone is CSRF-able and DNS-rebindable (C1 SEC-14) |
| D16 | `_external/` restore: allowlist = the three known memory-provider paths; anything else consent-per-path with absolute destination shown; hard never-list (`~/.ssh`, `~/.gnupg`, `~/.aws`, autostart, shell rc, outside-$HOME); external skill dirs relocate **into** `$HERMES_HOME/external/<n>/` by default with the config pointer rewritten; non-home externals record-only by default | A hostile bundle writing `_external/.ssh/authorized_keys` is RCE-by-migration (C1 SEC-07; C2-20) |
| D17 | Deep-Scan ships **v1, CLI-first** (`talaria deepscan generate|ingest`) with P3 §10.3's trust model + C1 SEC-15 hardening (never-registry gates candidates before they are offered; names-not-values; ingest value-scrub; exact-file read, no glob); GUI card is dismissible, never a decision | Owner calls discovery the hardest problem; agent evidence proposes/corroborates, never decides (C3 #21) |
| D18 | Reports: **one data model (P3 §14 schema)** → json/md/html renderers; two HTML reports v1 (System Overview, Migration Report); unified path `$HERMES_HOME/migration/talaria/<ts>/`; redaction applied at the data-model layer before any renderer; artifacts written 0600 | One truth, three renderings (C3 #27; C1 SEC-17) |
| D19 | Applying a bundle is installing code: preflight shows an executable-content summary (plugins/hooks/cron scripts/skill scripts/MCP stdio) as a consent row; MCP entries are validated **before** config write and failures become explicit decisions | Hermes silently drops invalid MCP entries at spawn; bundles carry code Hermes will execute (C1 SEC-09/10) |
| D20 | "Lock everything" opt-in: the vault passphrase may additionally encrypt SENSITIVE-CONTENT members; constraint 6 extended, not challenged | The bundle's biggest secret channel is conversation content (C1 SEC-01.3) |
| D21 | v1 cutline = C3 §6 adopted verbatim (deferral table + non-goals in §5–§6 below); every deferral keeps its schema fields in v1 | No deferral may strand a user; cuts are surface, not schema (C3 §6) |
| D22 | Plain `hermes backup` zip: v1 **detects + names it + points at `hermes import`** on the target; degraded apply is v1.1 | Second input format with its own edge matrix (C3 #25; backup §Interop preserved as roadmap) |
| D23 | Device-linked stores (WhatsApp session, Matrix store, signal-cli, chrome-debug, weixin): **excluded in v1, no force-include toggles**; checklist re-pair is the path | Failure mode is account unlinking/Olm corruption we cause at launch; re-pair is 1 minute and always correct (C3 #23 overrides P2 §12) |
| D24 | Old-machine sequencing (one canonical sentence): *the old gateway may keep running through apply+verify; it must be OFF before the target gateway starts.* Pack-time retire coaching (P4 M7) + finish-screen hard gate (P1 §12) + hazard-gated start (P3 §11); under `--intent clone` the gate becomes acknowledge-hazards | Merges three compatible mechanisms; clone would otherwise contradict the gate (C3 #29) |
| D25 | Crash recovery v1 = journal-driven **rollback only**; hash-based resume-continue is v1.1; journal format carries the fields for it now | Rare path, real engineering; rollback already makes crashes safe (C3 #13) |
| D26 | No PDF anywhere: checklists/reports are self-contained HTML with print CSS ("Save as PDF from your browser") | stdlib has no PDF writer (C2-21, C3 #10; constraint 1) |
| D27 | CLI/GUI parity = **capability parity** (every GUI action has a flag/JSON-selection equivalent), not interaction parity; no curses tree in v1 | Prevents a half-curses tree creeping in under the "parity" banner (C3 §5) |
| D28 | GUI progress transport = **polling** (`GET /api/events?after=seq`) over the same ndjson event stream the CLI prints; SSE not used in v1 | Simplest robust stdlib mechanism; one event stream, two frontends (P2 §10) |
| D29 | Inline config.yaml credential values: **omit the key in stage + checklist card**; `${env:VAR}` promotion only where interpolation is documented (`mcp_servers`) or venv-verified | Placeholders in non-interpolated keys hand Hermes a literal string and a distant auth failure (C2-16 over C1 SEC-04's placeholder option) |
| D30 | Constraint challenges: **none** from any proposal or critic. Adopted wording precisions: constraint 4 reads "any Python launches it (2.7-parseable stub message); 3.9+ runs it"; constraint 6 extended per D20 | All eight constraints survived adversarial review (P1 §18, P2 §16, P3 §15, P4 §14, C1/C2/C3) |
| D31 | Manifest placement (implementation arbitration): `manifest.stub.json` (eternal header only, STORED) is the FIRST member; the complete `manifest.json` (STORED) is the LAST member. Readers use the central directory; stream/salvage tooling reads the stub off the front | ARCH §3.1's "manifest first" and R-PACK-01's "hash in the same zip-write pass" are mutually exclusive with stdlib zipfile — full manifest content (hashes) exists only after payload streaming. The stub preserves both intents: eternal header up front, single-pass hashing intact |

## 3. Requirements

Priorities: **P0** = v1 ship-blocking (the v1 cutline), **P1** = v1.1, **P2** = later.
Each requirement is testable; "MUST" binds implementation. Citations name the governing research.

### R-SCAN — Scanner & inventory

- **R-SCAN-01 (P0)** The tool MUST resolve HERMES_HOME by the real precedence: `$HERMES_HOME` env
  → `HKCU\Environment\HERMES_HOME` on Windows → platform default (`~/.hermes` POSIX/macOS/Termux,
  `%LOCALAPPDATA%\hermes` Windows, `/opt/data` containers), never hardcoding a path (state §1.1–1.2,
  install §4).
- **R-SCAN-02 (P0)** The scanner MUST anchor at the profile ROOT and walk the root plus every
  `profiles/<name>/` as a full sub-universe, handling ROOT-level singletons (`kanban.db`,
  `shared/nous_auth.json`) exactly once (state §10.1/.9; cron §1.1).
- **R-SCAN-03 (P0)** Both directory-layout generations MUST be handled and merged on read (legacy
  flat names vs `platforms/…`), and empty legacy dirs MUST never be created (integ §0; state §10.8).
- **R-SCAN-04 (P0)** Every path under the root MUST classify into the artifact catalog
  (ARCHITECTURE §2); anything unmatched lands in the Unrecognized family — never silently dropped,
  never silently included (comp W16; D9).
- **R-SCAN-05 (P0)** The walk MUST prune excluded directories at descent (never enumerate-then-
  filter), never follow symlinks on either side, and prune `hermes-agent` at ROOT level only
  (backup §426k incident; state §10.2–3; C2-10).
- **R-SCAN-06 (P0)** The scan phase MUST be metadata-only (stat + classify, no hashing) and finish
  in seconds beside a 30 GB `state.db`; hashing happens during pack (P1 §5; state §2.3).
- **R-SCAN-07 (P0)** The scanner MUST chase references out of configs (machine-specific keys,
  `skills.external_dirs`), cron jobs (`script`, `workdir`, absolute `skills`, `context_from`,
  `monitor_url`), MCP entries, plugin manifests, and memory-provider `backup_paths()`, producing a
  per-reference portability verdict (digest §6.6; cron §4–5; integ §2.4).
- **R-SCAN-08 (P0)** The tool MUST detect install identity: version triple (`__version__`, release
  date, `.hermes_build_sha`), install method via the exact 7-step algorithm, git branch/HEAD/dirty/
  stash, `_config_version`, and lazy-extras feature list via a source-venv probe of
  `active_features()`, degrading gracefully when no venv exists (install §4, §9, §12).
- **R-SCAN-09 (P0)** Capture MUST be strictly read-only: `.backup.lock` is detected and waited on,
  never taken; a fresh `.hermes-update-in-progress` refuses capture; a running gateway produces the
  live-capture warning and `capture_mode` is recorded (P3 §6.1; backup §Interop).
- **R-SCAN-10 (P0)** Unrecognized files MUST pass the secret gates before default-ON: any dotfile
  and any `*.bak|*.old|*.orig|*~|*.swp` sibling of a credential-class name classifies credential;
  small text files get a content scan (PEM/AKIA/`sk-`/`xox[bps]-`/`ghp_`/JWT/high-entropy `KEY=`);
  hits quarantine to credential handling; larger/binary unknowns default record-only (C1 SEC-03).

### R-DIFF — Provenance & diffing

- **R-DIFF-01 (P0)** Every skill MUST get one of six provenance tags — stock-pristine,
  stock-modified, hub-installed, org, agent-created, user-created — computed with upstream's own
  mechanisms (`.bundled_manifest`, `.hub/lock.json`, `_org/*/.org-baseline.json`,
  `.usage.json.created_by`), never a new hash scheme, and never mixing the three incompatible
  digest schemes (skills §5).
- **R-DIFF-02 (P0)** Directory hashes MUST be parameterized by source-OS semantics (separator +
  collation), the semantics recorded in the manifest, and hashes computed under different
  semantics never compared; on cross-OS apply, stock-pristine `.bundled_manifest` entries MUST be
  rebaselined with target-OS semantics in stage (D14; C2-01).
- **R-DIFF-03 (P0)** Stock-modified skills MUST be diffable per file (unified diff; binary via NUL
  detection), mirroring `diff_bundled_skill` semantics (skills §5).
- **R-DIFF-04 (P0)** config.yaml MUST be diffed against `DEFAULT_CONFIG` extracted from the source
  venv when present ("17 of 70 sections customized"), degrading to an honest "customized keys
  unknown — no Hermes venv" (P2 §3; C3 G1).
- **R-DIFF-05 (P0)** SOUL.md MUST be compared against the shipped default persona to mark
  customized-vs-stock (install §8; C3 G1).
- **R-DIFF-06 (P0)** The code checkout MUST never be packed; the tool records ref + dirty diff as
  a patch + untracked list, and offers patch replay on target (digest §6.4; install §12).
- **R-DIFF-07 (P1)** `hermes skills list-modified --json` output SHOULD be used for cross-checking
  when the venv is available (enrichment, never a dependency).

### R-DEPS — Dependency engine & feasibility

- **R-DEPS-01 (P0)** The engine MUST extract dependencies from: skill frontmatter
  (`required_environment_variables` — enforced; `platforms[]` — hard gate; `prerequisites.*` +
  `dependencies[]` — advisory), cron jobs (script interpreter, workdir, delivery platform, model/
  provider snapshots, croniter, `context_from`, MCP toolset refs), MCP entries (url vs command;
  npx→Node, uvx→uv, docker→daemon; `${VAR}` cross-check against .env), plugin `requires_env`,
  provider env keys and localhost base_urls, and the lazy-features list (skills §6; cron §4;
  integ §2.4, §3; install §9).
- **R-DEPS-02 (P0)** Every dependency cell MUST carry one verdict from: OK · OK-AFTER-REWRITE ·
  ACTION · MISSING-INSTALLABLE · IMPOSSIBLE · UNKNOWN-OFFLINE (P2 §6; D11).
- **R-DEPS-03 (P0)** Predictive mode MUST evaluate verdicts against a declared `--target-os`
  (linux|macos|windows|termux) with **no target machine present** — including Windows filename
  legality and case/NFC collision counts (C3 #19/G2; C2-03/04).
- **R-DEPS-04 (P0)** Live preflight MUST probe the real target, mirroring the cron scheduler's own
  preflight signals and `hermes doctor`'s sectioned OK/WARN/FAIL + accumulated manual-action UX
  (cron §4; digest §3).
- **R-DEPS-05 (P0)** The engine-verdict → wizard-group mapping in §8.2 is fixed and MUST be the
  only translation used by any frontend (D11).
- **R-DEPS-06 (P0)** These named checks MUST exist: model/provider snapshot drift (`[drift_skip]`),
  croniter presence, bash-for-`.sh` on Windows, TZ mismatch (offset-based), one-shot >120 s grace,
  version skew class, `_config_version ≥ 12` floor, WAL-hostile filesystem, Termux ticker caveat,
  MCP runtime presence (cron §4/§6; state §2.3/§3; C2-08).

### R-DISC — Discovery & Deep-Scan

- **R-DISC-01 (P0)** All evidence MUST merge into one touchpoint ledger; each entry carries
  `provenance ∈ {config-ref, cron-ref, skill-ref, plugin-ref, db-mined, agent-reported}` and
  `confidence ∈ {verified, corroborated, advisory}` (P3 §10).
- **R-DISC-02 (P0)** Layer 1 (static reference chasing) MUST be deterministic and structural
  (R-SCAN-07 feeds it).
- **R-DISC-03 (P0)** Layer 2 MUST mine read-only recorded behavior: distinct `sessions.cwd`/
  `git_repo_root` from state.db, `.usage.json` last-used telemetry, cron `output/` recency —
  each candidate stat-verified before entering the ledger (state §2.3; skills §5).
- **R-DISC-04 (P0)** `talaria deepscan generate` MUST emit a self-contained observation skill with
  a minted run nonce and a JSON output schema; `ingest` MUST read exactly the nonce-named file
  (never glob), schema-validate, size-cap (1 MiB), and nonce-check (P3 §10.3; C1 SEC-15).
- **R-DISC-05 (P0)** Agent-reported items MUST never silently expand the capture set, mark
  anything machine-safe, or alter exclusions/scrubs; probe-confirmed items become candidates the
  **user** opts in; unconfirmable items render only in the "agent said, unverified" appendix;
  Layer-1/2 findings absent from the report are tagged `agent-blind` (P3 §10.3).
- **R-DISC-06 (P0)** Candidates MUST pass the never-registry (system paths, key material, foreign
  credential stores) **before** being offered as capture checkboxes; denylisted hits render only
  in the advisory appendix as refused; the skill text demands names-not-values and ingest runs the
  secret-pattern scrub over every string (C1 SEC-15.1–2).
- **R-DISC-07 (P1)** Bounded log-tail mining (last 32 MiB) SHOULD be added as a further advisory
  layer (deferred; C3 #22).

### R-PACK — Capture & packing

- **R-PACK-01 (P0)** Packing MUST stream each payload file exactly once, hashing SHA-256 in the
  same pass as the zip write (`ZipFile.open(name,'w')`), with zip64 always enabled (C2-10; P2 §16).
- **R-PACK-02 (P0)** SQLite MUST be captured via the snapshot protocol: read-only URI open,
  `conn.backup(dst, pages=-1)`, sidecars never packed, zeroed-file detection, integrity check
  size-capped at 2 GiB (O(1) probe above), snapshot temps staged on the destination filesystem,
  bounded retries then fail-closed with quiesce guidance (state §2.3, §10.4–7; C2-11; comp W10).
- **R-PACK-03 (P0)** Output MUST be atomic: write `<name>.hermespack.partial` (0600), publish via
  `os.replace` only after self-verify; a crash leaves only a `.partial`, offered for deletion
  (backup §atomic; C1 SEC-01.4).
- **R-PACK-04 (P0)** Pack self-verify MUST re-read the finished archive and re-hash every member
  against the manifest before publish (P3 §4.1).
- **R-PACK-05 (P0)** Pack MUST write exactly the pack-time selection (validated by the coupling
  engine); the bundle records the selection; apply may narrow, never widen (D10).
- **R-PACK-06 (P0)** The machine-bound EXCLUSION_REGISTRY MUST filter capture, and pack MUST
  assert none slipped in (belt) (P3 §7; backup NS-508).
- **R-PACK-07 (P0)** Destination prechecks MUST run before writing: free space vs estimate, FAT32/
  exFAT 4 GiB file cap with per-OS detection named, fallback save path chain Desktop → home → cwd
  (P1 §8; C2-10/21).
- **R-PACK-08 (P0)** Pack MUST record predictive per-OS verdicts (including Windows-illegal member
  names and collision counts) into the manifest (R-DEPS-03).
- **R-PACK-09 (P0)** Pack MUST record the source-system snapshot, rewrite anchors (source home,
  HERMES_HOME, username, OS, layout family, TZ name+offset), intent, and capture mode (P3 §9.1).
- **R-PACK-10 (P0)** Packing on a live install MUST honor `.backup.lock` by waiting, warn about
  cross-file skew, and offer `--require-quiesced` (P3 §6.1–2).

### R-BND — Bundle format

- **R-BND-01 (P0)** A bundle is ONE `.hermespack` zip with a schema-versioned `manifest.json`
  (first member, stored uncompressed) carrying per-file SHA-256, source snapshot, selection record,
  and compat requirements (constraint 5).
- **R-BND-02 (P0)** The eternal header — `schema_version`, `min_reader_tool_version`,
  `created_by_tool_version`, `created_at`, `source` — is frozen forever across schema majors; any
  tool version can read these five and print the correct message (P4 §10.2).
- **R-BND-03 (P0)** Payload addressing MUST be POSIX-separated, root-relative under
  `payload/home/`, home-relative under `payload/external/home/` (ARCHITECTURE §3).
- **R-BND-04 (P0)** Read-forever: tool N opens every schema ≤ N (golden-bundle CI); readers ignore
  unknown manifest keys; unknown artifact kinds are opaque items placed only with explicit consent
  (P4 §10.3; D9).
- **R-BND-05 (P0)** A plain `hermes backup` zip MUST be detected (marker heuristics + archive-
  prefix tolerance) and named, with guidance to run upstream `hermes import` on the target
  (backup §Interop; D22).
- **R-BND-06 (P0)** `talaria inspect --salvage` MUST report exactly which members of a damaged
  bundle verify and extract the intact ones (P4 §10.3.5).
- **R-BND-07 (P0)** Every surface that reads a bundle (STAGE, `inspect --list/--cat/--extract`,
  salvage) MUST enforce the hardening set: manifest↔zip bijection; duplicate-member refusal;
  case-fold + NFC/NFD collision detection; absolute/`..`/backslash/drive-letter member rejection;
  Windows reserved-name rejection; mode-bit clamp to {0600,0644,0700,0755} with setuid/setgid/
  sticky/world-write stripped and credential files forced 0600; per-member and total decompression
  caps from the manifest; manifest size/entry-count caps before parse (C1 SEC-08; C2-03/04/14).
- **R-BND-08 (P1)** Degraded apply of a `hermes backup` zip SHOULD ship in v1.1 with explicit
  "no provenance / no preflight intelligence" warnings.

### R-APPLY — Transactional apply

- **R-APPLY-01 (P0)** Apply MUST run the state machine INIT → PREFLIGHT → STAGE → BACKUP → APPLY →
  VERIFY → COMMIT with a write-ahead JSONL journal fsynced before each described action; the txn
  root lives inside the target HERMES_HOME (`.talaria/`, 0700, self-excluded from capture, README
  marker inside) (P3 §2; C2-25; C1 SEC-20).
- **R-APPLY-02 (P0)** Any op error, integrity failure, SIGINT, mid-apply gateway start, or
  unexplained target content MUST trigger automatic rollback (reverse-journal restore, re-hash
  verified); rollback failure freezes as NEEDS_ATTENTION (exit 6) deleting nothing; the pre-apply
  backup is never deleted by any failure path (P3 §2.4, I3).
- **R-APPLY-03 (P0)** After a crash, the next run MUST detect the unterminated journal and offer
  **rollback** (v1); the journal format carries the fields for v1.1 resume-continue (D25).
- **R-APPLY-04 (P0)** The preflight gate table PF-01..PF-18 (ARCHITECTURE §9.2) MUST run before
  STAGE; process liveness probes MUST use the platform-correct helper — `os.kill(pid, 0)` is
  banned on win32 by test (C2-02).
- **R-APPLY-05 (P0)** Staging MUST be per destination volume (`st_dev` grouping) so every final
  move is same-filesystem `os.replace`; EXDEV fallback = sibling stage dir or copy+fsync+replace,
  strategy journaled; on Windows every journaled fs op retries bounded (6 attempts, ~2.5 s total)
  on sharing violations before declaring rollback trigger T1 (C2-06/07).
- **R-APPLY-06 (P0)** Both-sides defense: the EXCLUSION_REGISTRY filters apply regardless of
  bundle contents; stale runtime files on the target are swept as container boot does; cron
  `run_claim`/`fire_claim` nulled and alert bits dropped in stage; executions.db non-terminal rows
  dropped; desktop installationId regenerated (P3 §7; cron §1.3; state §8).
- **R-APPLY-07 (P0)** Conflict handling per D8: wizard replace-with-safety-copy; CLI
  `--conflict keep|overwrite|rename|ask`; every conflict decision recorded in the report.
- **R-APPLY-08 (P0)** All content rewrites MUST go through the structural rewrite engine
  (JSON pointer / dotenv line / YAML key-path scalar / parameterized SQLite UPDATE), previewable,
  individually skippable, `needs_review` on any ambiguity; blanket regex over file bytes is banned
  (P3 §8; comp W7).
- **R-APPLY-09 (P0)** Modes MUST be restored explicitly (0600 secret files, 0700 dirs); when
  running as root with a different gateway user, restored files are chowned to that user (POSIX
  only, import-guarded) (state §10.10; cron §1.4 #68483).
- **R-APPLY-10 (P0)** OS-registered artifacts (units/plists/schtasks/.vbs/.desktop/registry) MUST
  never be copied; the checklist directs `hermes gateway install` regeneration (integ §1.4).
- **R-APPLY-11 (P0)** MCP entries MUST be validated before config write; failures become explicit
  decisions (fix / carry-disabled / drop), never silent writes (integ §2.4 step 7; D19).
- **R-APPLY-12 (P0)** Preflight MUST show the executable-content summary (counts + expandable
  list); it is a consent gate for bundles whose source differs from the current machine's capture
  history (C1 SEC-09).
- **R-APPLY-13 (P0)** `_external/` placement follows D16 (allowlist / consent-per-path /
  never-list / re-home default for skill dirs).
- **R-APPLY-14 (P0)** Unrecognized placement follows D9 (disclosed consent; `--include-unrecognized`).
- **R-APPLY-15 (P0)** `apply --only/--skip` narrowing MUST re-run the coupling engine; violations
  exit 3 naming the couple (D10).
- **R-APPLY-16 (P0)** Post-apply "make it at home" MUST: re-ensure lazy features from the recorded
  list via the target venv, pin `browser.camofox.user_id` to the source-derived uuid, regenerate
  profile wrapper scripts, clear `.update_check`, emit the WhatsApp-bridge `npm install` card, and
  generate the finish checklist + Secrets Handoff state (install §9; integ §5, §8; state §10.12).
- **R-APPLY-17 (P0)** Apply MUST never start the gateway; the finish screen's "start" action is
  gated behind the hazard list and (replace intent) the old-machine-off checkbox; proof-of-life =
  watching for a fresh `cron/ticker_heartbeat` with the ~60 s expectation set in copy (P3 §11;
  P4 M12; D24).
- **R-APPLY-18 (P0)** Windows-illegal or colliding names are placed only via a consented,
  manifest-recorded, deterministic rename map (re-checked for new collisions), listed in the
  report; never created via `\\?\` as final paths (C2-04).
- **R-APPLY-19 (P0)** Version-skew classes (EXACT / FORWARD-OK / FLOOR-BREACH / BLOCKED-DOWNGRADE
  / UNKNOWN) MUST gate per P3 §9.2; downgrade refused (exit 8) with the pinned `--commit`
  remediation printed.
- **R-APPLY-20 (P0)** Managed (NixOS `.managed`) and in-container Docker targets MUST be detected
  and refused with specific guidance (state §8; C3 non-goals).
- **R-APPLY-21 (P1)** `apply --resume` (continue path) and `--strict-verify`/`talaria commit`
  (exit 7) SHOULD ship in v1.1 (exit 7 reserved now).

### R-VERIFY — Verification

- **R-VERIFY-01 (P0)** Integrity verification is gating: every applied path re-hashed against its
  expected (post-rewrite) hash; DB `PRAGMA quick_check` size-capped at 2 GiB; failure ⇒ automatic
  rollback (P3 §4).
- **R-VERIFY-02 (P0)** Functional verification is advisory and MUST NOT block commit in v1:
  `hermes --version` smoke test, `hermes doctor` folded into the checklist, cron-preflight mirror
  re-run, secret-mode audit, machine-bound absence sweep, legacy-dir shadow audit; each a report
  `checks[]` entry (P3 §4.2–3; C3 #14).
- **R-VERIFY-03 (P0)** `talaria verify` MUST be re-runnable standalone against the last apply, and
  `verify --watch` watches for the heartbeat (P4 M12).

### R-SEC — Secrets & security

- **R-SEC-01 (P0)** Two-tier model (D2): SECRET-CREDENTIAL never travels as plaintext payload
  (checklist always; vault opt-in); SENSITIVE-CONTENT travels by default, labeled private in UI
  and reports, and drives the "private notebook" copy.
- **R-SEC-02 (P0)** The classifier MUST seed from Hermes' own canonical lists (`file_safety.py`,
  `_ROOT_CREDENTIAL_FILES/_DIRS`, `_SECRET_FILE_NAMES`) plus the enumerated inline config keys
  (`model.api_key`, `providers.*.api_key`, `*.client_secret`, `extra_headers`,
  `dashboard.basic_auth.*`, drain secret, token-bearing URLs) and the R-SCAN-10 variant/content
  heuristics (state §2.2; C1 SEC-04).
- **R-SEC-03 (P0)** Checklist artifacts contain names + where-used + provider URLs only, never
  values; `checklist.json` stores check-state only; GUI paste-back POSTs values over the
  token-authed session and writes `.env` via create-exclusive 0600, never echoed, logged, or
  rendered back; CLI reads via no-echo prompt, never argv (C1 SEC-06).
- **R-SEC-04 (P0)** Vault per D12: scrypt(N=2^17, r=8, p=1, 16 B random salt, params stored),
  HKDF-SHA256 subkeys ("enc", "mac"), AES-256-GCM per member with fresh 96-bit nonces, AAD =
  {bundle_id, member path, schema_version, chunk index}, HMAC over the manifest vault section,
  member ceiling < 2^20; both primitives from `cryptography` (one probe).
- **R-SEC-05 (P0)** "Lock everything" opt-in encrypts SENSITIVE-CONTENT members with the same
  machinery (D20); UI states plainly that the default vault locks keys, not conversations, and
  that member names/shape remain visible while sealed.
- **R-SEC-06 (P0)** Without `cryptography`, vault mode MUST refuse honestly (exact message with the
  install command + checklist alternative); no fallback cipher, no home-rolled crypto; wrong
  passphrase on apply = clean typed error, zero partial writes (constraint 6; F18).
- **R-SEC-07 (P0)** Inline config credentials follow D29 (omit key + checklist; interpolation
  promotion only where documented/verified).
- **R-SEC-08 (P0)** `.env` is never partially copied; if any split ever ships, unknown var names
  are secret until proven otherwise against a versioned allowlist (C1 SEC-05).
- **R-SEC-09 (P0)** Every bundle-, agent-, or filesystem-derived string MUST be HTML-escaped in
  GUI and reports and ANSI/control-stripped in the CLI; reports carry a restrictive CSP meta
  (C1 SEC-16).
- **R-SEC-10 (P0)** One redaction layer operates on the report data model before any renderer,
  covering rewrite before/after previews, the JSON appendix, and the touchpoint ledger, plus a
  secret-pattern masking pass over the final artifact; bundles, `.partial`s, reports, checklists,
  and `report.json` are written 0600 (C1 SEC-17, SEC-01.4).
- **R-SEC-11 (P0)** `apply --yes`/`--accept-all` MUST never auto-accept host/URL-changing rewrites
  or rewrites touching credential-class files; those need individual ack or
  `--accept-url-changes` with the full before→after printed; previews mask embedded `?token=`
  (C1 SEC-12).
- **R-SEC-12 (P0)** `docs/security.md` MUST state: hashes are integrity not authenticity; a bundle
  is software — apply only bundles you created or trust; conversation history may contain secrets
  you typed (vault/lock-everything covers that risk) (C1 SEC-11; C2-15).

### R-GUI — Localhost web GUI

- **R-GUI-01 (P0)** Server: stdlib `http.server`, bound literally to `127.0.0.1` on a random high
  port; browser opened via `webbrowser`; headless boxes get the printed URL + `ssh -L` hint + text
  wizard offer (constraint 3; C2-09/21).
- **R-GUI-02 (P0)** Full D15 hardening: one-time URL bootstrap token exchanged for a ≥128-bit
  session token sent as `X-Talaria-Token` header (constant-time compare); strict Host and Origin
  validation; `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, CSP `default-src 'self'`; secrets only in POST bodies; token
  never logged; single active session; shutdown on completion or idle timeout.
- **R-GUI-03 (P0)** One background job engine drives all long operations; the GUI polls
  `/api/events?after=seq` consuming the identical ndjson event stream the CLI prints; all jobs are
  cancellable; the UI never freezes (comp W14; D28).
- **R-GUI-04 (P0)** Screens = S0–S4 / T1–T4 (§8) + the Customize drawer (tri-state tree with
  consequence sentences, class/provenance badges, search); the wizard never renders the 20-family
  tree (D5) and never exceeds the decision budget (R-UX-01).
- **R-GUI-05 (P0)** All assets load via `importlib.resources` (zip-safe); a CI test runs the GUI
  from the built `.pyz`; zero network, zero CDN (C2-09; constraint 3).
- **R-GUI-06 (P0)** Deep-Scan appears as a dismissible card (skippable without choice); dismissing
  it changes nothing about the happy path (P4 M4; C3 §3).
- **R-GUI-07 (P1)** GUI diff viewer, dependency grid, and rewrite-plan editor SHOULD ship in v1.1
  (CLI + reports render the same data in v1).

### R-CLI — Command line

- **R-CLI-01 (P0)** v1 subcommands: `talaria` (wizard), `scan`, `diff` (skills|config|checkout),
  `deps`, `pack`, `inspect` (`--verify/--list/--cat/--extract/--deps --target-os/--checklist/
  --salvage`), `preflight`, `apply` (`--dry-run/--emit-plan/--plan/--only/--skip/--conflict/
  --intent/--include-unrecognized/--yes`), `verify` (`--watch`), `rollback`, `report`,
  `checklist`, `deepscan generate|ingest`, `why`, `gui` (C3 §6; ARCHITECTURE §13).
- **R-CLI-02 (P0)** Every command supports `--json` (single schema-versioned document) and
  mutating commands support `--progress ndjson` (comp W15).
- **R-CLI-03 (P0)** `talaria` with no arguments runs the identical wizard as numbered text prompts
  (pure stdin/stdout, no curses); parity is capability parity per D27.
- **R-CLI-04 (P0)** Exit codes are P3 §13's table verbatim (D3); only 5/6/7 imply the target was
  touched.
- **R-CLI-05 (P0)** Every mutating command has `--dry-run` producing the identical report JSON
  with `mode:"dry_run"` and zero side effects (constraint 7).
- **R-CLI-06 (P0)** `--non-interactive` never prompts (missing decision ⇒ exit 3); `--yes` accepts
  defaults but honors the R-SEC-11 and D9 carve-outs.
- **R-CLI-07 (P0)** `talaria why <path>` answers what a file is, whether it travels, and the cited
  reason, from the shipped registry (P4 §13.5).
- **R-CLI-08 (P0)** No secret value is ever accepted via argv; passphrase via prompt or
  `--vault-passphrase-file` only (C1 SEC-13).

### R-REPORT — Reports & checklists

- **R-REPORT-01 (P0)** One report data model (P3 §14 schema, v1) renders to json/md/html; the
  claw-migrate status vocabulary and 13 anti-overclaiming rules apply (install §7).
- **R-REPORT-02 (P0)** The System Overview report runs with or without packing and is the brief's
  "comprehensive overview" deliverable, including the zero-unexplained counter, provenance,
  integration surface, cron fleet, secrets census (names only), machine-bound register, and
  outside-HERMES_HOME reach (P4 §8.1).
- **R-REPORT-03 (P0)** A Migration Report is written on every apply outcome including rollback and
  dry-run (comp W13).
- **R-REPORT-04 (P0)** HTML reports are single-file, inline CSS, zero external requests,
  printable, light/dark, with a `<script type="application/json">` appendix (P4 §8).
- **R-REPORT-05 (P0)** Reports are redacted by default (`--no-redact` for local full detail);
  redaction covers every surface per R-SEC-10.
- **R-REPORT-06 (P0)** Reports, checklists, and persisted checklist state live under
  `$HERMES_HOME/migration/talaria/<ts>/`; capture-side copies sit beside the bundle
  (`<bundle>.checklist.html` auto-written) (D18; P4 M6).
- **R-REPORT-07 (P0)** Delight set: boarding pass, arrival stats (real scanner numbers), SOUL
  first-line quote (honoring redaction modes), proof-of-life status (P4 §13).

### R-XPLAT — Cross-platform correctness

- **R-XPLAT-01 (P0)** Layout translation `~/.hermes` ↔ `%LOCALAPPDATA%\hermes` and POSIX↔Windows
  path-family translation apply only to rule-addressed path fields (install §0; P3 §8.5).
- **R-XPLAT-02 (P0)** Process liveness uses the named helper (POSIX `os.kill(pid,0)` with
  exception mapping; Windows ctypes `OpenProcess`+`GetExitCodeProcess`, `tasklist` fallback);
  a CI test asserts no win32 code path calls `os.kill` with sig 0 (C2-02).
- **R-XPLAT-03 (P0)** Case-fold + NFC/NFD collision detection runs over the full namelist before
  extraction; target fs behavior is probed (probe files in the txn dir), not assumed; collisions
  on a forgiving fs refuse with a consented rename plan; preflight reference resolution flags
  pairs that resolve only case/normalization-insensitively (C2-03).
- **R-XPLAT-04 (P0)** Windows filename legality (reserved names, `<>:"|?*`, trailing dot/space)
  yields pack-time IMPOSSIBLE-ON-WINDOWS verdicts and apply-time consented rename maps (C2-04).
- **R-XPLAT-05 (P0)** A single Windows path helper applies `\\?\` for tool I/O; txn ids ≤12 chars
  with `s/`/`b/` stage/backup names; preflight audits longest final path against
  `LongPathsEnabled` (C2-05).
- **R-XPLAT-06 (P0)** Timestamps go through an owned tolerant RFC3339 parser (3.9 `fromisoformat`
  rejects `Z`); TZ comparison is (name, utc_offset, dst) based, never requiring zoneinfo data;
  pinning `timezone:` from a Windows source uses the embedded Windows→IANA table (C2-08).
- **R-XPLAT-07 (P0)** Structural editors preserve per-line CRLF/LF and BOM byte-exactly
  (`splitlines(keepends=True)`; jobs.json read `utf-8-sig`), use the file's dominant terminator
  for insertions, and follow the deterministic YAML quoting rule; the YAML refuse-list includes
  anchors/aliases, block scalars, flow collections on the target line, merge keys, duplicate keys,
  tabs (C2-12/13; P3 §8.3).
- **R-XPLAT-08 (P0)** Filesystem-type detection is named per OS (`/proc/self/mounts`; `statfs`
  via ctypes; `GetVolumeInformationW`/`GetDriveTypeW`); "unknown" is a legal reported answer
  (C2-10/23).
- **R-XPLAT-09 (P0)** Python floor: core runs on 3.9 stdlib-only; `__main__.py` stub is
  2.7-parseable and prints the friendly floor message; vermin (or equivalent) gates CI; no 3.10+
  APIs at runtime (constraint 1–2; P4 §10.5; C2-08d).
- **R-XPLAT-10 (P0)** Degraded/foreign zip reading strips `__MACOSX/`/`.DS_Store`, tolerates
  cp437-flagged names (reporting mojibake), and `normcase`s containment checks on Windows (C2-14).
- **R-XPLAT-11 (P0)** Termux: tolerate missing `~/Downloads`/Desktop, print URL when
  `webbrowser` no-ops (`termux-open-url` hint), and surface the foreground-gateway ticker caveat
  (cron §6; C2-21).

### R-UX — Wizard & product behavior

- **R-UX-01 (P0)** Decision budget: ≤2 decisions source-side, ≤2 target-side (+2 conditional),
  enforced by a transcript test — interactive `talaria pack` answered with all-Enter asks ≤2
  questions and produces a bundle (P1 §2; C3 §3/G6).
- **R-UX-02 (P0)** The Three Promises appear verbatim on every data-touching screen; the secrets
  copy is D2's "private notebook" text; README and app never drift (P4 §3).
- **R-UX-03 (P0)** Language rules bind: agent-vocabulary first, every warning ships its fix, ≤2
  sentences per concept, stable TAL id on every error, technical detail behind expanders, one
  exclamation mark product-wide (P1 §13; P4 §5).
- **R-UX-04 (P0)** The old-machine-off gate follows D24, including the clone-intent adaptation.
- **R-UX-05 (P0)** Category rows are indivisible in the wizard; sub-item surgery lives in
  Customize where every uncheck shows its consequence sentence first (P1 §6.2/§15).
- **R-UX-06 (P0)** Finish checklist cards each carry one verb, the exact command with a copy
  button, and persisted state that survives closing the tool (P1 §12; P4 M11).

### R-DIST — Distribution & release

- **R-DIST-01 (P0)** Ship a single-file `talaria.pyz` (runnable by any Python with the floor stub)
  and a pip-installable package; SHA-256 sums published beside artifacts (constraint 4).
- **R-DIST-02 (P0)** `talaria --version` prints the three axes: tool SemVer · bundle schema
  (reads ≤N) · hermes knowledge stamp (P4 §10.1).
- **R-DIST-03 (P0)** Docs set per P4 §6 (README, user-guide, faq, troubleshooting keyed by TAL
  code, comparison with W1–W18 receipts, security, bundle-format, generated cli.md, CHANGELOG);
  the honesty covenant is release law: every claim traces to a teardown line or a passing
  scenario (P4 §7).
- **R-DIST-04 (P0)** Release gates: A1–A12 green on the 3-OS matrix; golden bundles open+apply;
  README quick-start executed by CI; screenshots regenerated from fixtures (P4 §12).

## 4. P0 tally

R-SCAN 10 · R-DIFF 6 (+1 P1) · R-DEPS 6 · R-DISC 6 (+1 P1) · R-PACK 10 · R-BND 7 (+1 P1) ·
R-APPLY 20 (+1 P1) · R-VERIFY 3 · R-SEC 12 · R-GUI 6 (+1 P1) · R-CLI 8 · R-REPORT 7 ·
R-XPLAT 11 · R-UX 6 · R-DIST 4. **Total P0: 122.**

## 5. Explicit non-goals (v1) — stated in the README

Each deferral has a working v1 fallback (C3 §6):

| Non-goal (v1) | v1 fallback |
|---|---|
| Device-linked store copying (WhatsApp/Signal/Matrix/chrome-debug/weixin) | Checklist re-pair cards with exact commands — always correct |
| Degraded `hermes backup` zip **apply** | Detect + name it + point at upstream `hermes import` |
| Executing the Hermes installer | Copy-button pinned command + auto-poll until Hermes appears |
| Crash resume-continue | Journal-driven rollback offer on next run |
| `--strict-verify` / deferred commit (exit 7 reserved) | Advisory checks report; post-commit `talaria rollback` exists |
| Log-tail mining | Static refs + DB mining + Deep-Scan triangulate |
| Profile mapping/rename/promotion | Same-name restore; profiles carried verbatim |
| Config-file jobs, named custom presets (`vaulted-full` rejected outright) | `pack --yes --include/--exclude -o` is already cron-able |
| GUI diff viewer / deps grid / rewrite-plan editor | CLI + reports render the same data |
| `talaria decommission` as a command | Content ships as finish-checklist cards |
| `talaria convert` | Never required for reading (read-forever) |
| Managed-NixOS / in-container-Docker **targets** | Detect + refuse with specific guidance |
| Bundle-vs-bundle compare, history trimming, delta bundles, signing, TUI, post-run hooks | v2 roadmap |

Termux target IS supported, with the ticker caveat card. Built-in presets v1:
`everything-portable` (default), `essentials`, `identity-only`.

## 6. Wizard flows

### 6.1 Source side (Pack) — 2 decisions

| Step | Screen | What happens | Decision? |
|---|---|---|---|
| S0 | Detect & greet | Role auto-detected (Hermes found / bundle found / both / neither); identity card (version, install method, profiles, size); read-only promise on screen | no — single CTA "Pack up this Hermes" |
| S1 | Scan | Starts immediately; narrative progress (memories, skills with provenance counts, tasks, conversations, connections); metadata-only, seconds | no |
| S2 | Review | Six category rows, all pre-checked with sizes; "Won't travel (N)" info row; Deep-Scan dismissible card; `Customize in detail` opens the drawer | no — glance-and-confirm |
| S3 | Keys & passwords | Checklist mode (default) vs Locked vault (passphrase; optional "Lock everything") — the honest private-notebook copy shown either way | **Decision 1** |
| S4 | Pack & boarding pass | Save-location picker (defaulted); destination prechecks; pack with cancel; boarding pass + `<bundle>.checklist.html` + transfer coaching + retire plan | **Decision 2** (weak — location) |

### 6.2 Target side (Apply) — 2 decisions + 2 conditionals

| Step | Screen | What happens | Decision? |
|---|---|---|---|
| T1 | Open bundle | Auto-found bundle; provenance card from eternal header; hermes-backup zips detected and redirected to guidance; no Hermes ⇒ pinned install command + auto-poll (+ `hermes gateway stop` interposed) | no |
| T2 | Preflight | Who-acts groups (Ready / We'll fix automatically / Needs you afterwards / Can't come along); executable-content row; unrecognized-files disclosure row; skew gate | no — verdicts, not choices |
| T2→T3 | Consent | "Move everything in" — the consent moment covering the disclosed lists | **Decision 3** |
| c1 | Lived-in target (conditional) | Replace-with-safety-copy vs Cancel | conditional |
| c2 | Vault (conditional) | Passphrase entry | conditional |
| T3 | Apply | Five plain stages (ready / safety copy / moving in / making it at home / double-checking); cancel ⇒ rollback | no |
| T4 | Finish | Verified counts + doctor summary; checklist cards (paste-back, re-pair, reauth…); old-machine-off hard gate; "Start Hermes" + heartbeat proof-of-life; Save report / Undo everything | **Decision 4** (the gate tick) |

Typical path: 4 decisions; worst case 6. Gate: R-UX-01.

## 7. Category model

### 7.1 The six wizard categories (defaults per P1 §6.1, amended by D2/D23)

Personality & memories · Skills & plugins · Scheduled tasks · Conversations & history (labeled
private content) · Connections & pairings (labeled private content) · Settings, projects & boards
— all default ON. Plus: **Keys & passwords** (mode chooser, not a checkbox) and **Won't travel**
(informational; device-linked + machine-bound + runtime).

### 7.2 Binding 6-category ↔ 20-family mapping (C3 §2.8)

| Wizard category | Families absorbed |
|---|---|
| Personality & memories | identity-memory; external-state (memory-provider dirs) |
| Skills & plugins | skills; plugins; skill-bundles |
| Scheduled tasks | automations (cron) incl. `$HH/scripts/` |
| Conversations & history | conversations-history (state.db, response/memory/verification DBs, sessions, exports) |
| Connections & pairings | platforms-messaging (a)-class; mcp; pairing; channel routing |
| Settings, projects & boards | configuration (incl. hooks/); boards-projects; dashboard-observability; browser config; providers config; desktop-app JSONs |
| Keys & passwords (chooser) | credentials (SECRET-CREDENTIAL tier) |
| Won't travel (info) | os-integration; code-runtime (record-only); runtime-ephemera; device-linked stores; managed-scope |
| (invisible, always handled) | unrecognized (D9 gates); code-runtime metadata records |

### 7.3 Preflight verdict → who-acts mapping (binding; D11)

OK → "Ready to move in" · OK-AFTER-REWRITE → "We'll fix these automatically" ·
ACTION, MISSING-INSTALLABLE, UNKNOWN-OFFLINE → "Needs you afterwards" (→ checklist) ·
IMPOSSIBLE → "Can't come along" (3-sentence honesty rule: what, why in human terms, what happens
instead).

## 8. Acceptance scenarios (binding; traceable)

- **A1 — The $5 VPS move.** GIVEN a fixture Linux install (memories, 3 modified + 1 agent-created
  skill, 4 cron jobs incl. script+workdir+notepad, sessions DB, pairing) WHEN packed over CLI
  answering every prompt with Enter (≤2 questions asked) and applied on a clean Linux target with
  defaults THEN every selected family restores, all hashes verify, cron claims are scrubbed, the
  checklist contains exactly the fixture's machine-bound items, and exit codes are 0.
  [R-UX-01, R-CLI-01..05, R-PACK-*, R-APPLY-*, R-VERIFY-01]
- **A2 — Cross-layout Linux → Windows.** GIVEN the A1 source with 1 genuinely modified stock
  skill WHEN applied on a Windows-layout target THEN path fields translate structurally (no
  blanket regex), the `.sh` cron job is flagged with the bash explanation, per-platform mode
  handling applies, the report lists every rewrite, AND the rebaselined `.bundled_manifest` makes
  `hermes skills list-modified` report exactly the one modified skill.
  [R-XPLAT-01/04/07, R-APPLY-08/18, R-DIFF-02, R-DEPS-06]
- **A3 — Secrets containment (D13 scope).** GIVEN canary values planted in `.env`/auth/inline
  config AND inside state.db messages, response_store payloads, a session JSONL, cron output, and
  notepad WHEN packed with defaults THEN credential canaries appear in zero members; content
  canaries appear only in members labeled SENSITIVE-CONTENT (exactly the UI-labeled set); the
  checklist names all planted credentials with provider URLs where declared; WHEN packed with
  --vault --lock-everything THEN zero plaintext canaries anywhere; AND redacted reports/checklists
  contain zero canaries. [R-SEC-01/02/03/05/10, R-REPORT-05]
- **A4 — Vault round-trip and honest refusal.** GIVEN `cryptography` present WHEN vault-packed and
  applied with the passphrase THEN credentials restore 0600 and hashes verify; GIVEN it absent
  THEN pack refuses vault mode with the exact honest message and offers checklist mode; a wrong
  passphrase on apply is a clean TAL-4xx error with zero partial writes. [R-SEC-04/06, R-CLI-08]
- **A5 — Power loss mid-apply.** GIVEN an apply killed at a randomized point after staging WHEN
  the tool next runs THEN it offers rollback, and after rollback the target equals its pre-apply
  state byte-for-byte, with a Migration Report saying "rolled back" and the cause.
  [R-APPLY-01/02/03, R-REPORT-03]
- **A6 — The lived-in target (CLI/Customize path).** GIVEN a target with its own skills (one
  name-colliding), memories, and cron jobs WHEN applied with `--conflict ask`/per-item policies
  THEN nothing is overwritten without a recorded decision, "keep yours" is honored, and the
  report's conflict section matches reality; the GUI wizard offers only
  replace-with-safety-copy/cancel. [R-APPLY-07, D8]
- **A7 — Provenance tells the truth.** GIVEN fixtures for all four skill classes plus a customized
  config.yaml section and a customized SOUL.md THEN the Overview classifies 4/4 skills correctly,
  the modified skill's diff matches the planted edit, the config diff names the customized
  sections, and SOUL.md is marked customized. [R-DIFF-01..05, R-REPORT-02]
- **A8 — Cron fidelity under time.** GIVEN jobs incl. an interval job with `last_run_at`, a
  monitor with state+baseline, a `context_from` chain, and a one-shot due mid-move THEN on target:
  claims null, interval anchoring preserved, monitor does not false-alert, the chain moved
  together, and the expired one-shot is surfaced for a decision — never silently dropped or
  re-fired. [R-APPLY-06, R-DEPS-06, coupling rules]
- **A9 — Hostile and huge inputs.** GIVEN (a) bundles with traversal members, absolute paths,
  symlink entries, duplicate/case-fold/NFC-colliding names, a decompression bomb, and an
  `_external/.ssh/authorized_keys` member; (b) a >2 GiB SQLite; (c) a 400k-file cache tree; (d)
  out-of-home symlinks THEN every hostile bundle is refused with a TAL-3xx before any target
  write (the `_external` member requires the D16 consent path and `~/.ssh` is refused even with
  consent), the big DB uses the capped integrity strategy, the cache tree is pruned without a
  scan stall, and symlinks are never followed. [R-BND-07, R-APPLY-13, R-PACK-02, R-SCAN-05]
- **A10 — Reports stand alone and stay redacted.** GIVEN generated reports THEN they open from
  `file://` with zero external requests, print cleanly, contain the JSON appendix, the redacted
  default contains no secret values and no raw usernames (JSON appendix included), the
  zero-unexplained counter is 0 on the fixture, and every planted touchpoint is listed.
  [R-REPORT-04/05, R-SEC-09/10, C3 G4]
- **A11 — Predictive verdicts with no Hermes anywhere.** GIVEN a bundle on a bare `python:3.9` box
  with no Hermes installed WHEN `talaria inspect --deps --target-os windows` (and macos) runs
  THEN correct IMPOSSIBLE/ACTION verdicts render (`.sh`-on-Windows, macos-only skill,
  Windows-illegal filenames), entirely offline. [R-DEPS-03, R-BND-01, C3 G2/G5]
- **A12 — The agent is not trusted.** GIVEN a Deep-Scan report containing one real path, one
  fabricated path, one sensitive path (`~/.ssh/id_ed25519`), and one stale-nonce file THEN the
  real path is corroborated into the ledger, the fabricated one renders only in "agent said,
  unverified", the sensitive one is refused by the never-registry (advisory appendix only), the
  stale-nonce file is rejected, and the capture set is byte-identical to a run without the report.
  [R-DISC-04/05/06, C3 G3]

## 9. Competitor-beating checklist (W1–W18 → requirements)

| W | Weakness (comp) | Defeated by |
|---|---|---|
| W1 | Tkinter hard dependency | R-GUI-01/05, R-CLI-03 (stdlib web GUI + full CLI) |
| W2 | No Windows support | R-XPLAT-01..08, R-SCAN-01, A2 |
| W3 | Blind tree copy, no semantics | R-SCAN-04/07, artifact catalog (ARCH §2) |
| W4 | Silently drops sessions/logs/cache | R-SCAN-04 (nothing silent), R-UX Promise 3, conversations default-ON (§7.1) |
| W5 | Secrets in plaintext zip | R-SEC-01..08, A3; D2 honest copy |
| W6 | Machine-bound state copied verbatim | R-PACK-06, R-APPLY-06 (both-sides registry), D23 |
| W7 | Blind regex path rewriting | R-APPLY-08, R-XPLAT-07 (structural editors, preview, needs_review) |
| W8 | `extractall` over live install | R-APPLY-01/02/07 (transactional, conflicts, rollback) |
| W9 | Broken zip-slip guard | R-BND-07 (containment + full hardening set), A9 |
| W10 | Live SQLite file-copies | R-PACK-02 (snapshot protocol) |
| W11 | No dependency analysis | R-DEPS-01..06, A11 |
| W12 | No stock-vs-modified detection | R-DIFF-01..05, A7 |
| W13 | No verification or report | R-VERIFY-01..03, R-REPORT-01..03, A5/A10 |
| W14 | GUI freezes on main thread | R-GUI-03 (job engine + polling) |
| W15 | No CLI, no automation | R-CLI-01..07 (--json, ndjson, exit codes) |
| W16 | Guessed layout markers | R-SCAN-01/03/08 (source-derived knowledge, version detection), R-BND-04 (unknown-kind grace) |
| W17 | No tests/CI/docs | R-DIST-03/04, ARCHITECTURE §15, A1–A12 |
| W18 | Bare zip, no schema/integrity | R-BND-01/02/04/06/07 (versioned manifest, per-file SHA-256, eternal header, salvage) |
