# C1 — Security & Privacy Adversary Review of P1–P4

Reviewer: hostile security/privacy lens. Inputs: all four proposals + all eight research docs.
Severity: **CRIT** (exploitable or breaks a stated promise) · **HIGH** (real attack surface or
spec hole that will be built wrong) · **MED** (hardening/contract gap) · **LOW** (hygiene).
Verdicts: ACCEPT · ACCEPT+CH (accept with required changes) · MODIFY (redesign the element) ·
REJECT (replace the element; alternative given). Citations: research as `state §`, `integ §`,
etc.; proposals as `P1 §`…

## Verdict table

| # | Element | Source | Verdict | Required change (detail in finding) |
|---|---|---|---|---|
| SEC-01 | Conversation/history DBs plaintext in default bundle + "safe to carry on a USB stick" copy | P1 §7/§6.1, P2 §2.7 | **REJECT copy / MODIFY handling** | Split (d) into d-cred/d-content; honest copy; opt-in "lock everything"; bundle file 0600 |
| SEC-02 | A3 secret-canary acceptance test scope | P4 §11 A3 | MODIFY | Plant canaries in state.db rows, response_store.db, sessions JSONL, cron output, notepad — not just .env |
| SEC-03 | Unrecognized bucket "default ON if … not secret-pattern-matched" | P2 §2.13; P3 F22 | MODIFY | Content-scan gate; unknown dotfiles & `*.bak/*.old/*~` of secret files ⇒ (d); apply placement consent-gated (adopt P4 §10.3.2) |
| SEC-04 | config.yaml inline-secret extraction ("placeholder left") | P1 §6.1, P2 §2.2 | ACCEPT+CH | Enumerated key list from Hermes' own classifiers; structural YAML edit; placeholder spec; re-inject path defined |
| SEC-05 | `.env` all-or-nothing vs split | P1 §6.1/§7 | ACCEPT+CH | Deny-by-default for unknown vars if any split ships; non-secret vars re-created via checklist, never by copying .env |
| SEC-06 | Secrets Handoff Checklist + paste-back | P1 §7/§12, P4 M6 | ACCEPT+CH | Names/hints only ever; checklist.json stores state not values; O_EXCL-0600 .env writes; no value echo/logging |
| SEC-07 | `_external/` home-relative restore | P1 §6.1, P2 §2.13, backup precedent | **MODIFY (CRIT)** | Allowlist of known provider paths; everything else consent-per-path with absolute destination shown; external skill dirs relocate into HERMES_HOME by default |
| SEC-08 | Zip extraction / bundle parsing hardening | P3 §2.1 STAGE, P2 §9 | ACCEPT+CH | Add dup-member, case-fold/Unicode-collision, mode-bit clamp (no setuid/world-write), bomb caps, Windows device/drive/UNC rejection, manifest↔zip bijection; same checks in `inspect --extract/--cat` |
| SEC-09 | "Applying a bundle installs code" trust boundary | all (implicit) | MODIFY | Executable-content consent summary (plugins, hooks, cron scripts, skill scripts, MCP stdio) at apply; threat-model doc states it |
| SEC-10 | MCP entry re-validation on restore | P1 §17.13, P2 §2.10, P3 §4.2-8 | ACCEPT+CH | Validate *before write* and gate, not just report; entries Hermes would silently drop are surfaced as decisions |
| SEC-11 | Bundle integrity vs authenticity | P2 §15 (signing P2-later), P4 §10 | ACCEPT+CH | Threat model states SHA-256 ≠ tamper-proof; vault members AAD-bound to manifest+path; optional signing stays roadmap |
| SEC-12 | Rewrite plan `--accept-all` / editable plan.json | P2 §8, P3 §8 | ACCEPT+CH | Host/URL-changing and secret-file rewrites excluded from `--accept-all`; non-rule-derived values always needs_review (bind P2 to P3 §8.2) |
| SEC-13 | Vault crypto design (params unspecified anywhere) | P1 §7, P2 §4.4, P3 F18 | MODIFY | Full spec required (KDF params, salt, nonce, AAD, passphrase channel) — provided in SEC-V1 |
| SEC-14 | GUI localhost server (token-in-URL only) | P1 §4, P4 M1 | **MODIFY (CRIT)** | 127.0.0.1 bind, ≥128-bit token as header, strict Host/Origin checks (DNS-rebinding/CSRF), no-referrer, frame-deny, CSP, shutdown on completion |
| SEC-15 | Deep-Scan trust model | P3 §10.3, P2 §13.4 | ACCEPT+CH | Best element in the packet. Add: hard capture-denylist so verified-but-sensitive paths are never offered; names-not-values rule + ingest value-scrub |
| SEC-16 | Untrusted strings rendered in GUI/reports/CLI | P4 §8, P2 §9 | MODIFY | HTML-escape every bundle-/agent-/filesystem-derived string; CSP meta in reports; ANSI-strip in CLI |
| SEC-17 | Report redaction scope | P4 §8, A10 | ACCEPT+CH | Redaction must cover rewrite before/after previews, JSON appendix, touchpoint ledger; secret-pattern masking pass over the final rendered doc; reports/checklists 0600 |
| SEC-18 | "Install Hermes for me" executes installer | P1 §10.1 vs P4 M8 | REJECT (P1 variant) | Adopt P4: print pinned `--commit` command, never execute; contradiction must be ruled once |
| SEC-19 | Both-sides machine-bound registry; advisory-only agent evidence; honest vault refusal; never-auto-start gateway; read-only lock handling | P3 §7/§10.3/F18/§11, §6.1 | **ACCEPT** | None — these are the security backbone; ratify as invariants |
| SEC-20 | Txn root/backup dir inside HERMES_HOME | P3 §2.1 | ACCEPT+CH | `.talaria/` 0700; backups are secrets-at-rest — document retention + `gc`; excluded from capture (P3 already says so) |
| SEC-21 | Apply-time re-narrowing `--only/--skip` | P2 §10 | ACCEPT+CH | Coupling-rules engine must re-run on the narrowed set (else curator/`.archive` pairs etc. break at apply) |

---

## 1. Secrets leakage paths

### SEC-01 (CRIT) — The default bundle is full of (d)-class content, and P1's copy denies it

The research itself classifies **state.db / memory_store.db / projects.db as (d) secret material
("conversation content")** — integ §7(d) — and upstream lists `state.db` in its own
`_SECRET_FILE_NAMES` 0600 set (digest §2, state §2.2). `response_store.db` stores "gateway conv
history/**tool payloads**" (state §2.3): terminal output the agent saw — which routinely includes
`cat .env`, tokens echoed by CLIs, SSH output. Sessions JSONL, `session-exports/`,
`cron/output/*.md`, and `cron/notepad.db` (cursors/watchlists) carry the same class of content.

All proposals default these ON as *plaintext payload* (correctly — moving them is the product),
but P1 §7 then ships this sentence: *"Your keys and passwords stay out of the bundle, **so the
file is safe to carry on a USB stick or send over the network**."* That claim is false in exactly
the way the competitor's W5 was: the bundle contains the user's entire private conversation
history, memories, and very likely literal secret values quoted inside messages. An attacker with
the bundle does not need `.env`.

**Required changes (all four are mandatory):**
1. **Taxonomy fix (P2):** split (d) into **(d-cred)** — credentials, → checklist/vault, never
   plaintext payload — and **(d-content)** — private content, travels as payload but is labeled
   sensitive, drives copy, report redaction, and file modes. Cite integ §7 for membership.
2. **Copy fix (P1 §7, §8, README §7):** delete "safe to carry." Replacement shipped string:
   *"Your keys and passwords stay out of the file. Your conversations and memories are inside
   it — anyone who gets the file can read them, so treat it like a private notebook."* Plus one
   checklist line: keys may also appear inside conversation history; rotating anything pasted
   into chat is listed as an optional checklist card.
3. **Opt-in "Lock everything":** when `cryptography` is present, the existing vault passphrase
   may optionally encrypt d-content payload members too (same SEC-V1 spec, streaming AES-GCM per
   member). Honest refusal without the lib, same as the vault. This is an extension of
   constraint 6, not a violation; default stays plaintext-content + checklist.
4. **Bundle at rest:** create the `.hermespack` and the `.partial` 0600; same for reports,
   checklist HTML, and `checklist.json`.

### SEC-02 (HIGH) — A3 proves the wrong theorem
P4's A3 plants 40 canaries only under known secret-bearing *names* (.env/auth). The test would
pass while state.db carries the same canaries in message rows — the biggest real channel is
unmeasured. **Required:** A3 additionally plants canary values inside state.db messages,
response_store.db payloads, a session JSONL, `cron/output/`, and notepad — then asserts
(a) default bundle: canaries absent from every member **except** d-content members, which must be
exactly the set the UI labeled sensitive; (b) "lock everything" mode: zero plaintext canaries
anywhere; (c) redacted reports/checklists: zero canaries.

### SEC-03 (HIGH) — Unrecognized bucket defaults ON: how the next .env ships
P2 §2.13: unknown paths default ON "if outside never-zones and not secret-pattern-matched." The
canonical lists match exact names; they will not match `.env.bak`, `.env.old`, `config.yaml~`,
`secrets-backup.txt`, editor swaps — files real users create, containing the same secrets. This
is the competitor's W5 with one indirection. **Required:** (1) name heuristics: any dotfile, and
any `*.bak|*.old|*.orig|*~|*.swp` sibling of a (d)-class name, classifies (d); (2) every
unrecognized file ≤ a size cap gets a content scan (PEM headers, `AKIA`, `sk-`, `xox[bps]-`,
`ghp_`, `eyJ` JWT shape, high-entropy `KEY=` lines) — hits quarantine to (d)/record-only with a
visible row; (3) larger/binary unknowns default **record-only**, ON only by explicit toggle.
Apply side: adopt P4 §10.3.2 (opaque items placed only with explicit consent) over P3 F22's
"default-carried" — the committee must pick one; security picks P4's.

### SEC-04 (MED) — Inline config secret extraction needs a spec, not a phrase
"Inline secrets extracted, placeholder left" (P1 §6.1) must be: key list = union of
`file_safety.py` lists, `_ROOT_CREDENTIAL_FILES/_DIRS`, `_SECRET_FILE_NAMES` (state §2.2) plus
config keys integ §7(d) names: `model.api_key`, `providers.*.api_key`, `*.client_secret`,
`extra_headers` (Cloudflare Access), `dashboard.basic_auth.password|secret`, drain secret, and
`browser.cdp_url`/`BROWSER_CDP_URL`-style URLs when they embed `?token=`. Extraction uses the
same structural YAML editor as P3 §8.3 (never regex); the placeholder is a comment-marked empty
scalar or `${env:VAR}` promotion (which also makes the entry migration-friendly per integ §2.1);
each extracted key becomes a checklist item, and target-side paste-back knows the exact key-path
to re-inject. Test: config canaries added to A3.

### SEC-05 (MED) — If `.env` is ever split, split deny-by-default
P1 treats `.env` as all-checklist (good). The moment anyone proposes carrying "non-secret" .env
lines (home-channel vars, feature flags — cron §4 depends on them), the classifier's false
negative becomes a leak. **Required policy:** unknown env var names are secret until proven
otherwise; the portable-var allowlist is explicit and versioned; everything else appears on the
checklist with its *name* and where it is used. Never ship "copy .env minus known-secrets."

### SEC-06 (MED) — Checklist/paste-back mechanics
Checklist artifacts contain names + provider URLs only — ratify P4 M6 wording as law, and:
`checklist.json` persists check-state only, never values; GUI paste-back POSTs values over the
token-authed localhost session (SEC-14), values are written to `.env` opened `O_CREAT|O_EXCL`
0600 (create-then-write, not write-then-chmod), never logged, never rendered back into the DOM,
never included in any report. CLI equivalent reads from prompt/stdin, never argv.

## 2. Bundle format and apply-side trust boundary

### SEC-07 (CRIT) — `_external/` is a sanctioned escape from HERMES_HOME
The backup-precedent `_external/` mechanism restores **outside** HERMES_HOME, home-relative. A
hostile bundle ships `_external/.ssh/authorized_keys` or `_external/.bashrc` — traversal checks
pass (no `..`), and the applier writes into $HOME. That is remote code execution by migration.
Constraint 7's transactionality does not help; the write is "legitimate."
**Required:** (1) apply-side allowlist for `_external/`: exactly the memory-provider paths the
tool knows (`~/.honcho`, `~/.hindsight`, `~/.openviking/ovcli.conf` — state §2.2/§9), versioned
with the knowledge stamp; (2) any other `_external/` member: never written silently — a consent
screen shows the absolute destination and requires per-path confirmation, with `~/.ssh`,
`~/.gnupg`, `~/.aws`, `~/.config/autostart`, shell rc files, and anything outside $HOME on a
hard **never** list (refuse even with consent; user can extract manually via `inspect`);
(3) `skills.external_dirs` trees captured under `_external/` restore by default **into**
`$HERMES_HOME/skills-external/<n>/` with the config pointer rewritten (P2 §2.4 already rewrites
the pointer) — restoring to the recorded foreign absolute path is opt-in with the same consent
screen. Add a hostile fixture to A9.

### SEC-08 (HIGH) — Extraction hardening beyond commonpath+symlink
P3 STAGE (commonpath semantics, absolute/symlink member rejection, hash-during-extract) is right
but incomplete. **Required additions, all sides that read a zip (STAGE, `inspect --extract`,
`--cat`, salvage):**
- **Manifest↔zip bijection before any extraction:** unmanifested members ⇒ refuse (or list-only);
  manifest entries missing from zip ⇒ refuse (F07 class).
- **Duplicate member names** (zip permits them; later entry silently wins) ⇒ refuse. Compare
  post-normalization, **case-folded and Unicode-normalized (NFC)** — `Config.yaml` vs
  `config.yaml` collides on Windows/macOS targets; NFD/NFC twins collide on macOS.
- **Windows path validity:** reject drive letters, UNC `\\`, reserved device names
  (CON/NUL/COM1…), trailing dots/spaces in components.
- **Mode-bit clamp:** stored modes are attacker input. Restore only from {0600,0644,0700,0755};
  strip setuid/setgid/sticky/world-writable always; secret-class files forced 0600 regardless of
  stored mode (state §10 trap 10 already forces this direction).
- **Decompression bombs:** stream-extract with a per-member cap = manifest size + slack and a
  total cap = manifest total + slack; abort on overrun (do not trust zip headers). Cap manifest
  JSON size and entry count before parsing. Extend A9 with a bomb fixture.
- `inspect --extract -o DIR` applies the same containment relative to DIR.

### SEC-09 (HIGH) — Say it plainly: applying a bundle is installing code
A .hermespack carries plugins (`__init__.py` executed by Hermes), `hooks/`, cron `scripts/`,
skill `scripts/`, MCP stdio command lines. Apply into a Hermes that will run them = arbitrary
code execution at next gateway start. All proposals treat this implicitly; none surfaces it.
**Required:** (1) preflight adds an **executable-content summary** row: "This bundle contains
things that run: N plugins, N hooks, N cron scripts, N skill scripts, N MCP commands" with an
expandable list; for a bundle whose manifest `source` machine/user differs from the current
user's history, the row is a consent gate; (2) `docs/security.md` threat model states "only
apply bundles you created or trust — a bundle is software"; (3) where cheap, mirror upstream's
scan verdicts (hub lock.json `scan_verdict` travels — surface it).

### SEC-10 (ACCEPT+CH) — MCP re-validation must gate, not narrate
Research: unvalidated `mcp_servers` entries are *silently dropped at spawn* (integ §2.4 step 7).
P3 runs validation in post-apply *advisory* verify — too late to be a control. **Required:**
validate at plan/stage time before config.yaml is written; entries failing
`validate_mcp_server_entry` semantics become explicit decisions (fix / carry-disabled / drop),
never silent writes that Hermes will silently discard. This is both a security control (suspicious
commands surfaced pre-install) and the only way the user learns their server didn't make it.

### SEC-11 (MED) — Integrity is not authenticity
Per-file SHA-256 defeats corruption, not tampering: whoever edits the bundle re-hashes the
manifest. P1's `BN-HASH` copy ("usually the copy glitched") is fine for accidents; the threat
model must state the limit. **Required:** (1) `docs/security.md`: hashes = integrity; treat a
bundle from an untrusted channel as untrusted software (ties to SEC-09); (2) in vault mode, each
encrypted member's AES-GCM AAD binds {bundle_id, member path, schema_version} so vault members
cannot be swapped/transplanted between bundles; (3) optional detached signature stays on the P2
roadmap — do not block v1 on it, do not claim tamper-proof anywhere.

### SEC-12 (MED) — The rewrite engine can be aimed at exfiltration
A plan.json entry rewriting `model.base_url`, an MCP `url`, or `hooks.outbound[].url` to an
attacker host turns first agent start into credential exfiltration. P3 §8.2 already demands
rule-derived values (`needs_review` otherwise) — **bind P2's editor to that rule** and add:
`--accept-all` (P2 §8) never auto-accepts (a) host/URL-changing ops, (b) ops touching
(d)-class files; those require individual ack or `--accept-url-changes` with the full before→after
printed. Rewrite previews render URLs with embedded `?token=` masked (feeds SEC-17).

## 3. Encrypted vault — SEC-13 (HIGH): the spec no proposal wrote

Constraint 6 names primitives; nobody fixed parameters, and GCM misuse is silent death.
**Required specification (v1):**
- KDF: scrypt, N=2^17, r=8, p=1 (fallback N=2^15 with maxmem note on small boxes), salt = 16B
  `secrets.token_bytes` per bundle, stored in manifest with the parameters (agility for later).
  `hashlib.scrypt` is stdlib; only AES-GCM needs `cryptography` — refusal message stays honest.
- Two subkeys derived from the scrypt output via HKDF-SHA256 (labels "enc", "mac"): AES-256-GCM
  key + a manifest-MAC key (HMAC over the manifest's vault section → SEC-11 binding).
- Encryption: per vault member, fresh 96-bit random nonce, AAD = {bundle_id, member path,
  schema_version}; nonce+tag stored per member; member count small enough that random nonces are
  safe — assert a hard ceiling anyway (<2^20 members).
- Passphrase channel: GUI = POST body on the token-authed session (never query string, never
  logged); CLI = prompt or `--vault-passphrase-file` (P2) — **no argv passphrase flag exists**.
  Empty passphrase refused; strength meter advisory. Python memory hygiene is best-effort —
  say so in security.md instead of pretending.
- Honest-refusal path (F18) ratified: no fallback cipher, no home-rolled anything; wrong
  passphrase = clean typed error, zero partial writes (A4 covers).
- UI truth: the vault "locks your keys." It does **not** lock conversations unless
  "lock everything" (SEC-01.3) is chosen — the sealed-bundle inspector shows secret *names*
  (P2 §9); state that names/shape are visible by design.

## 4. GUI security — SEC-14 (CRIT)

P1 §4's "random high port + one-time token in the URL" is necessary, not sufficient. The server
exposes state-changing endpoints (pack, apply, decommission, write .env). Two standard attacks
work today: **CSRF** (any website can `fetch`/form-POST to `http://127.0.0.1:PORT` — no CORS
needed to *send*) and **DNS rebinding** (attacker domain re-resolves to 127.0.0.1; the browser
happily talks to us with an attacker page's JS). **Required:**
1. Bind explicitly to `127.0.0.1` (and only optionally `::1`) — never 0.0.0.0, never hostname.
2. Session token ≥128 bits from `secrets`; the URL token is a one-time bootstrap that the page
   exchanges immediately; thereafter every request carries `X-Talaria-Token` as a **header**
   (cross-origin forms cannot set custom headers ⇒ CSRF dead). Constant-time compare.
3. Reject any request whose `Host` is not exactly `127.0.0.1:PORT`/`localhost:PORT`/`[::1]:PORT`
   (kills DNS rebinding) and any request bearing an `Origin` outside that set.
4. `Referrer-Policy: no-referrer` (checklist links open external provider consoles — the token
   must never ride a Referer), `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, CSP
   `default-src 'self'` with hashed/nonce'd inline assets.
5. Secret values (paste-back, vault passphrase) travel only in POST bodies; the server logs
   method+path only; the token appears in no log line.
6. Server shuts down when the wizard completes or on idle timeout; single active session; a
   second token-less connection gets a "session in use" page, not a second session.
7. On multi-user VPSes note the residual: any local user can *connect*; the token is the gate
   (P1 already says this — keep the sentence, implement 1–6).

SEC-16 applies to the GUI as renderer: every string that originated in a bundle, the filesystem,
or agent output is HTML-escaped at render (skill names, job names, paths, frontmatter). The
inspector renders *attacker* bundles — one unescaped `<script>` in a skill name is session-token
theft. Reports get the same escaping plus a CSP meta tag; CLI strips ANSI/control chars from
foreign strings (SEC-20).

## 5. Deep-Scan skill — SEC-15/SEC-19 (ACCEPT+CH)

P3 §10.3 is the strongest security design in the packet: nonce, schema validation, size caps,
advisory-only, can-corroborate-never-decide, `agent-blind` calibration. Ratify it as written.
Three residual holes to close:
1. **Lure-path laundering (HIGH):** "probe-confirmed ⇒ shown as a normal candidate the user may
   opt into capture" — an injected agent nominates `/etc/shadow` or `~/.ssh/id_ed25519`; lstat
   confirms existence; the UI now presents it as a plausible checkbox. **Required:** the
   capture-candidate path must pass the same never-registry as SEC-07 (system paths, key
   material, foreign credential stores — state §2.2 "foreign-owned" list) **before** it may be
   offered; denylisted hits render only in the advisory appendix, labeled "agent suggested a
   sensitive system path — refused." Outside-$HOME candidates additionally require typed-path
   confirmation.
2. **Values in the report (MED):** the skill text must demand *names, not values* for
   credentials; ingest runs the SEC-03 secret-pattern scrub over every string and redacts hits
   (the agent will paste a token eventually — by accident or by injection).
3. **Rendering (HIGH):** agent strings are untrusted in every surface — covered by SEC-16; the
   deep-scan JSON is the single most attacker-influenced input the product has.
Also: ingest reads exactly the nonce-named output file; never glob for candidate reports.

## 6. Reports & privacy — SEC-17 (MED)

P4 §8's redaction-by-default is right; scope it: the rewrite section prints before→after
absolute paths (usernames) and URLs (possible `?token=`), the JSON appendix duplicates
everything machine-readably, and the touchpoint ledger prints the agent's working directories.
**Required:** one redaction layer applied to the *data model* before any renderer (HTML, JSON
appendix, CLI) — not per-template; secret-pattern masking pass over the final artifact as belt;
A10 extended to assert the JSON appendix is as redacted as the prose; reports, checklist files,
and `report.json` written 0600 (they map the user's life); P4 §13.3's SOUL.md quote is fine but
must honor `--no-redact`'s inverse (a `--redact-strict` drops it).

## 7. Contradictions the committee must rule on (found by this review)

1. **P1 §10.1 "Install Hermes for me" (executes installer) vs P4 M8 (print pinned command,
   wait).** Security rules for P4: executing upstream's installer from inside our process is
   supply-chain surface + failure ownership we cannot honor. P1 keeps one-click *feel* via a
   copy-button and a "Done — check again" poll. (SEC-18)
2. **Unrecognized items:** P2 capture default-ON vs P3 F22 default-carry vs P4 consent-gated
   opaque placement. Ruling: SEC-03 capture policy + P4 apply policy.
3. **"Safe to carry on a USB stick" (P1) vs integ §7's own (d) classification of conversation
   DBs.** Ruling: SEC-01 — the research is right and the copy is wrong.
4. **A3's leak-proof claim (P4) vs what the bundle actually contains.** Ruling: SEC-02 test
   scope; the honesty covenant (P4 §7) makes this self-enforcing once the test exists.
5. **P2 `apply --only/--skip` re-narrowing vs P2's coupling engine** — narrowing must re-run
   coupling rules (SEC-21) or apply can build the "silently broken bundle" P2 §4.3 exists to
   prevent (curator pair, jobs-without-scripts), some with security consequences (pairing store
   without config = grants applied to the wrong bot config).
6. Endorsed, no change: P3's detect-don't-take `.backup.lock` (a *take* would be a source
   write), never-auto-start-gateway, exit-code honesty (only 5/6/7 touched the target), P1's
   old-machine-off gate (prevents credential-conflict states that read as compromise).

## Non-negotiable summary

The four proposals are strong on transactional integrity and honest failure; the security gaps
cluster where content is *assumed* benign (conversation DBs, unrecognized files, `_external/`,
rendered strings) and where specs stop at a phrase (vault, GUI server). With SEC-01, -02, -03,
-07, -08, -09, -13, -14, -15.1, -16 adopted, the design is credibly ahead of both the competitor
and `hermes backup` on every axis this reviewer attacks. Nothing reviewed is unimplementable
within the eight constraints; no constraint challenge is raised — constraint 6 is *extended*
(optional d-content encryption), not challenged.
