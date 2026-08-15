# C2 — Cross-Platform & Correctness Adversary: Committee Critique

Role: attack feasibility and correctness of P1–P4 across Windows / macOS / Linux / Termux, the
stdlib-only promise, the 3.9 floor, zipapp constraints, and multi-GB performance.

Method: all four proposals and all eight research docs read in full; contested claims
spot-verified against the hermes-agent clone. Verified in source this session:
`tools/skills_sync.py:254-266` (`_dir_hash` hashes `str(relative_to)` over `sorted(Path)`),
`cron/jobs.py::save_job_output` (timestamps `%Y-%m-%d_%H-%M-%S`, colon-free),
`agent/curator_backup.py:143` (backup dir names use `isoformat()` → colons),
`gateway/status.py:741` + `gateway/run.py:10710` (upstream's own warning that `os.kill(pid, 0)`
on Windows is NOT a no-op; they use ctypes `OpenProcess`). Also demonstrated in a live
interpreter: `sorted([PureWindowsPath('B/x'), PureWindowsPath('a/x')])` orders case-insensitively
and `str()` yields backslashes — both diverge from POSIX.

Overall: the four proposals are strong and mutually reinforcing on transaction mechanics, SQLite,
and machine-bound hygiene. But **all four are silent on filesystem *name* portability** (reserved
names, case-fold collisions, >260-char paths, NFC/NFD), one flagship P2 claim is provably wrong
cross-OS (`.bundled_manifest` reuse), one P3 preflight check is unimplementable as written on
stdlib Windows (IANA timezone comparison), and one naive implementation of PF-01 would *kill the
user's gateway*. Exit codes and schema-acceptance rules contradict across proposals and must be
unified before any code lands.

## Verdict table

| # | Element | Source | Verdict | Required change (summary) |
|---|---|---|---|---|
| 1 | Filename-portability gate (reserved names, invalid chars, trailing dot/space) | absent from all | **REJECT (omission)** | New pack-time predictive + apply-time gating check; rename/skip decisions recorded (F1) |
| 2 | Windows >260-char path handling | absent from all | **REJECT (omission)** | `\\?\`-prefixed absolute paths for every FS op on Windows, both pack and apply; stage-prefix length math in preflight (F2) |
| 3 | Case-fold + Unicode-normalization collision detection | absent from all | **REJECT (omission)** | Pack-time casefold/NFC collision scan recorded in manifest; apply-time target-FS probe; normalized conflict matching (F3) |
| 4 | PF-01 gateway liveness probe | P3 §3 | **MODIFY** | Mechanism must be specified: ctypes `OpenProcess`/`tasklist` on Windows — naive `os.kill(pid,0)` terminates the gateway (F4) |
| 5 | "Reuse `.bundled_manifest` MD5 bit-exactly" for provenance | P2 §3, P1 §5 | **MODIFY** | Hash is OS-dependent (separator + sort order). Compute provenance on source only; add apply-side manifest **rebaseline op** for pristine skills on cross-OS moves (F5) |
| 6 | PF-10 timezone comparison | P3 §3, P1 §10.1 | **MODIFY** | IANA zone names are unavailable via stdlib on Windows (no tzdata, no local-zone name). Record zone name + UTC offset at pack; compare offsets as fallback (F6) |
| 7 | JSON/dotenv/YAML rewrite editors | P3 §8.3 | **MODIFY** | Must read `utf-8-sig` (BOM'd jobs.json breaks `json.loads`), preserve CRLF/LF per file (`newline=''`), match upstream `ensure_ascii` (F7) |
| 8 | T1 rollback on first op error | P3 §2.4 | **MODIFY** | Bounded retry (3×, backoff) on Windows sharing violations / EACCES before triggering full rollback — AV/indexer locks are transient (F8) |
| 9 | Zipapp asset loading | P1 §4, P2 §14 (implied) | **MODIFY** | Explicit contract: all assets/templates via `importlib.resources.files()`/`pkgutil.get_data`; no `__file__`-relative reads anywhere (F9) |
| 10 | Streaming zip writes for multi-GB members | P2 §16 | **ACCEPT + SPEC** | `ZipFile.open(name,'w',force_zip64=True)` for unknown-size streams; hash while streaming; zip64 always on (F9) |
| 11 | Python 3.9 floor | all | **ACCEPT + SPEC** | Ban PEP 604 unions, `match`, `tomllib`, `hashlib.file_digest`; CI floor-check (vermin) per P4 §12 (F10) |
| 12 | FAT32-cap and WAL-hostile-FS detection | P1 §8, P3 PF-08 | **ACCEPT + SPEC** | Specify per-OS mechanism: `/proc/mounts`, `mount` subprocess, ctypes `GetVolumeInformationW`; estimate is uncompressed upper bound (F11) |
| 13 | Disk-space math ×2.2 inside HERMES_HOME | P3 PF-04 | **MODIFY** | Count bundle location when same FS; use hardlink backups (POSIX+NTFS) with copy fallback to avoid 3× multi-GB cost (F12) |
| 14 | `sqlite3.backup()` on live 30 GB DB | P1 §17, P3 §5 | **ACCEPT + SPEC** | Use `pages=N` + progress callback + retry budget; document restart-on-write livelock risk and quiesce escape (F13) |
| 15 | "Install Hermes for me" executes installer | P1 §10.1 | **REJECT** | Adopt P4 M8: print/copy the commit-pinned command, wait with re-check. Contradicts "no network, ever" (P4 §7) and failure ownership (F14) |
| 16 | Exit codes | P2 §10 vs P3 §13 | **REJECT (P2's)** | Adopt P3's 0–9 set verbatim (encodes "only 5/6/7 touched the target"); P2's 0–5 collides at code 5 (F15) |
| 17 | Bundle schema acceptance N/N−1 | P3 §9.3 | **REJECT** | Contradicts P4 §10.3 read-forever + golden bundles. Read all ≤ N forever; refuse only newer (F15) |
| 18 | Intent switch as "first question" | P2 §4.4 | **MODIFY** | Keep the switch, default `replace` silently in wizard (P1/P4's 2-decision budget); `clone` lives in Customize/CLI (F16) |
| 19 | `executions.db` default | P1 §6.1 ON vs P2 §2.6 OFF | **MODIFY** | Pick one: ON with terminal-row scrub (P1+P3 §5.2) is fine; record the decision in both docs (F16) |
| 20 | Mode-bit provenance Windows→POSIX | P3 §2.3 (partial) | **MODIFY** | Manifest records POSIX modes when source is POSIX; classification registry supplies the 0600/0700 floor when source is Windows (no modes exist) (F17) |
| 21 | Old-machine-off gate | P1 §12 vs P4 M7 | **MODIFY** | Make the hard gate platform-conditional (device-linked platforms configured ⇒ hard; else soft warning), per P4's more correct timing (F16) |
| 22 | `.pyz` double-click on Windows | P1 §4, P4 M1 | **MODIFY** | True only for python.org-installer py launcher; Store Python doesn't associate `.pyz`. Copy must lead with the `python talaria.pyz` command (F18) |
| 23 | Deep-Scan naming (`genskill` vs `deepscan generate`) | P2 §10 vs P3 §10.3 | **MODIFY** | One name. Keep P3's trust model verbatim (F16) |
| 24 | Journaled txn, WAL-style resume, both-sides registry | P3 §2, §7 | **ACCEPT** | Add pre-uid/gid to chown journal records for reversibility; scope dir-fsync to POSIX (already done) |
| 25 | Rewrite plan structural-locator-only, apply-side | P2 §8, P3 §8 | **ACCEPT** | Add existence-gating on auto home-remaps (auto only if target path exists, else needs_review) |
| 26 | Per-file SHA-256, eternal header, salvage | P4 §10 | **ACCEPT** | Ratify before packer code (P4 handoff 2 — seconded) |
| 27 | CRLF `.sh` scripts POSIX-ward | absent | **MODIFY (add)** | Flag-not-rewrite: preflight warns "CRLF line endings; bash will fail" (F18) |
| 28 | GUI localhost server token | P1 §4 | **ACCEPT + SPEC** | Token required on every POST (CSRF), not just in URL; bind 127.0.0.1 only (F18) |

## Detailed findings

### F1 — Windows filename validity: the missing gate (all proposals) — REQUIRED

**Broken scenario.** A bundle packed on Linux contains any of: a file named `aux.md`, `con.py`,
`nul` (agent-created skills can be named anything); a name with `< > : " | ? *` or control chars;
a name ending in `.` or space (silently stripped by Win32, so the applied file's path no longer
matches the manifest path → post-apply hash lookup fails → confusing auto-rollback). Verified
concrete instance: `.curator_backups/<isoformat>/` directories contain colons
(`agent/curator_backup.py:143`) — excluded by default, but P2's Customize lens lets a power user
force-include them, and `sessions/saved/` + `session-exports/` carry user/agent-chosen names with
no character guarantee. Result as proposed: apply fails midway on `OSError`/`ValueError`, rollback
fires, user gets F13 with no explanation of *why* — or worse, Win32 name-stripping produces a
silent path mismatch.

**Required change.** (1) Pack time: scanner computes a per-target-OS *name portability verdict*
per path (reserved device names CON/PRN/AUX/NUL/COM1-9/LPT1-9 as stem, invalid chars, trailing
dot/space, path-component length) and records it in the manifest; P2's predictive dependency
matrix gains a "name-portability" column. (2) Apply time: preflight re-checks against the real
target; each offending member gets an explicit decision — auto-rename with recorded mapping
(e.g. `aux.md → aux_.md` + report row), or skip-with-reason. Never reach the mid-APPLY OSError.
(3) The renamer must run *before* hashes become "expected apply hashes" so verification uses the
renamed path. Cost: one pure-string check pass; zero new deps.

### F2 — MAX_PATH: >260-char paths break stage before they break final — REQUIRED

**Broken scenario.** `%LOCALAPPDATA%\hermes\` + `skills/<cat>/<skill>/references/...` +
session-export names routinely approaches 260 chars. P3's stage tree *adds*
`.talaria/txn/<txn_id>/stage/` (~35 extra chars), so staging fails with `FileNotFoundError`/
`OSError 206` even when final paths would fit. Python does not opt out of MAX_PATH unless the
user's registry LongPathsEnabled is set (it usually is not).

**Required change.** On Windows, every filesystem call (pack walk, stage extract, backup copy,
`os.replace`, hashing) goes through a single path-normalization helper that produces
`\\?\C:\...` extended-length absolute paths (and `\\?\UNC\...` for shares). Preflight computes
`len(target_home) + max(member_relpath) + txn_prefix` and reports it. 8.3 short forms (HKCU may
hold `RUNNER~1` shapes — install §1) are resolved via `os.path.realpath` before comparison, so
`HERMES_HOME` equality checks don't false-negative.

### F3 — Case-fold and NFC/NFD collisions: silent data loss on macOS/Windows targets — REQUIRED

**Broken scenario.** Linux source legitimately contains `skills/notes/Foo/SKILL.md` and
`skills/notes/foo/SKILL.md` (hub discovery is silent-first-wins, so upstream never prevents
this — skills §2). Applied to macOS (APFS case-insensitive-preserving default) or Windows NTFS:
the second extraction *overwrites* the first inside stage; each member's write-time hash passes
individually, but the final tree has one survivor. Post-apply integrity re-hash then fails for
one path (case-insensitive lookup returns the survivor's bytes) → auto-rollback with a cryptic
hash-mismatch — the best case. Worst case (two files identical in content) it *passes* and the
user silently lost a skill. Sibling issue: NFC vs NFD — a bundle packed on macOS carries NFD
names (`é` = `e`+combining); on a Linux target with an existing NFC-named file, conflict
detection string-compares raw names, misses the match, and the user ends up with two
visually-identical files.

**Required change.** (1) Pack time: single pass computing `relpath.casefold()` and
`unicodedata.normalize('NFC', relpath)` collision sets; collisions recorded in the manifest and
shown at review ("these two items cannot coexist on Windows/macOS"). (2) Apply preflight: probe
target-FS case sensitivity empirically (create `probe_a`/`PROBE_A` inside the txn dir) rather
than assuming by OS — APFS can be case-sensitive, NTFS dirs can be flagged case-sensitive.
Collisions on an insensitive target require a recorded decision (rename/skip) exactly like F1.
(3) Conflict matching against lived-in targets compares NFC-normalized, casefolded keys on
insensitive filesystems. All stdlib (`unicodedata`).

### F4 — PF-01 as naively implemented kills the gateway on Windows — REQUIRED (spec, not intent)

P3 PF-01 says "gateway.pid liveness probe" without a mechanism. The obvious implementation —
`os.kill(pid, 0)` — is documented *by upstream itself* as a Windows footgun: any signal other
than the CTRL events unconditionally `TerminateProcess`es the target
(`gateway/status.py:741-756`, `gateway/run.py:10710-10719`, which use ctypes
`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + exit-code check). A "read-only preflight"
that terminates the user's running gateway is the single worst correctness violation available
to this tool. **Required:** the design doc must pin the mechanism — POSIX `os.kill(pid, 0)`
(EPERM counts as alive); Windows ctypes `OpenProcess`+`GetExitCodeProcess` with `tasklist`
fallback. Same helper reused for `.backup.lock`/update-lock staleness checks and the mid-apply
gateway re-probe (T5), which would otherwise repeatedly fire the same footgun.

### F5 — `.bundled_manifest` MD5 is OS-dependent; "bit-exact reuse" breaks cross-OS — REQUIRED

**Broken scenario.** Verified: `_dir_hash` (`tools/skills_sync.py:254-266`) hashes
`str(rel)` — `references\x.md` on Windows vs `references/x.md` on POSIX — over `sorted(Path)`,
whose ordering is case-insensitive on Windows (`['a\\x','B\\x']` vs POSIX `['B/x','a/x']`,
demonstrated live). Consequence of P2 §3's "reuse the MD5 dir-hash algorithm bit-exactly" +
P1 §6.1's "carry `.bundled_manifest`": after a Linux→Windows move, target-side Hermes
`sync_skills()` recomputes every skill's hash with Windows semantics, mismatches the carried
Linux-computed baseline, and classifies **every bundled skill as user-modified** — skill updates
freeze forever (sync never overwrites "modified" skills — skills §5), and Talaria's own
target-side provenance display shows garbage. Safe direction (no data loss), silently wrong
forever.

**Required change.** (1) Provenance verdicts are computed **on the source at pack time** (same
OS as wrote the manifest) and carried as data — never recomputed naively on the target. (2) New
apply-side op `rebaseline_bundled_manifest`: for skills the source verified **stock-pristine**,
rewrite their `.bundled_manifest` entries with target-OS-recomputed `_dir_hash` values (running
our faithful reimplementation with *target* Path semantics), so upstream sync keeps updating
them. Modified/user skills keep their carried entries (they are skip-listed either way).
Journaled, previewable, cited. (3) Contrast note for the spec: `.hub/lock.json` hashes are
already cross-OS stable (POSIX-sorted rel-path strings, upstream issue #62310) — carry verbatim,
no rebaseline. Same review applies to `_org/*/.org-baseline.json` fingerprints (third scheme).

### F6 — PF-10 timezone comparison is unimplementable as written on stdlib Windows — REQUIRED

`zoneinfo` (3.9) has **no timezone database on Windows** unless the third-party `tzdata` package
is installed — `ZoneInfo("Europe/Berlin")` raises. And there is no stdlib API to obtain the
local IANA zone *name* on Windows (`time.tzname` yields "W. Europe Standard Time"). PF-10
("bundle timezone unset AND source system TZ ≠ target system TZ") therefore cannot compare zone
identities on a Windows endpoint. **Required change:** at pack time record `{iana_name_best_effort,
utc_offset_now, utc_offset_jan1, utc_offset_jul1}` (offsets via `time.localtime`/
`datetime.now().astimezone()` — pure stdlib everywhere). PF-10 compares offsets (both winter and
summer to catch DST-rule differences) and treats name comparison as best-effort enrichment;
remediation stays the same (pin `timezone` in config — cron §6). If `tzdata` happens to be
importable, use it as an optional enhancement per constraint 1's graceful-degradation clause.
One-shot `run_at` values are TZ-aware strings (cron §1.3) and need no zone DB to compare —
state that explicitly so nobody "fixes" them with zoneinfo.

### F7 — Rewrite editors: BOM, CRLF, and writer fidelity — REQUIRED

- `json.loads` **rejects a UTF-8 BOM**; upstream deliberately reads jobs.json with `utf-8-sig`
  because Windows users edit it in Notepad (cron §1.4). P3 §8.3's JSON editor must read
  `utf-8-sig` and write BOM-less UTF-8 (matching upstream's writer), else a BOM'd store bricks
  the rewrite phase.
- The dotenv line editor and the YAML indentation editor must open with `newline=''` and
  preserve each file's existing line-ending flavor byte-for-byte; a CRLF `.env` rewritten LF
  churns every line and destroys the "only the targeted line changed" guarantee.
- `json.dumps(indent=2)` must also match upstream's `ensure_ascii` default (True) or non-ASCII
  job names change byte form — semantically harmless, but it breaks P3's pre/post-hash
  bookkeeping claims of minimal diffs and pollutes report diffs.

### F8 — Windows transient locks: retry before rollback — REQUIRED

Antivirus/Search Indexer briefly opens freshly-written files; `os.replace` then fails with
sharing violations (WinError 5/32). As proposed, T1 turns one transient AV probe into a full
rollback of a 30 GB apply. **Required:** bounded retry (3 attempts, 100/400/1600 ms backoff) on
`PermissionError`/`OSError` winerror 5/32 for `os.replace`, dir renames (`replace_tree` is
two renames and doubly exposed), and stage deletes — then T1. Journal records retry counts.
Same wrapper handles the `replace_tree` caveat that `os.rename` onto a non-empty dir fails on
every OS — the aside-then-in two-step in P3 §2.2 is correct; the retry wrapper makes it survive
Windows reality.

### F9 — Zipapp discipline: asset loading and >4 GiB members — REQUIRED (spec)

No proposal states how GUI assets, report templates, or the generated Deep-Scan skill templates
load from inside `talaria.pyz`. `__file__`-relative reads fail inside a zipapp. **Required
contract:** every embedded asset is a package resource read via `importlib.resources.files()`
(3.9-safe) or `pkgutil.get_data`; the stdlib HTTP server serves assets from memory, never from
disk paths; a CI test runs the GUI smoke test *from the built .pyz*, not the repo checkout
(P4 §12 already runs A1 from the artifact — extend it to cover one GUI asset fetch).
Pack-side: when streaming members of unknown final size, `ZipFile.open(name, 'w')` must pass
`force_zip64=True`, or a >4 GiB `state.db` snapshot raises at member close — after hours of
work. zip64 stays unconditionally on (P1 §18/P2 §16 agree; this is the mechanical detail that
makes it true).

### F10 — Python 3.9 floor: concrete bans

Consistent with P2 §16 (JSON-not-TOML) and P4 §10.5 (2.7-parseable stub — endorsed; note the
stub must contain no f-strings before the version check). Additional floor bans for the
implementation standard: PEP 604 `X | None` annotations (3.10), `match` (3.10),
`hashlib.file_digest` (3.11 — use chunked reads), `datetime.UTC` (3.11), `Path.walk` (3.12).
`zoneinfo`, `graphlib`, `importlib.resources.files`, `argparse.BooleanOptionalAction` are all
3.9-OK. Gate with vermin in CI per P4 §12.

### F11 — Filesystem-type detection needs a specified mechanism

PF-08 (WAL-hostile FS) and P1 §8 (FAT32 4 GB cap) are right to exist; neither names a method,
and `os.statvfs` carries no FS type on macOS. **Spec:** Linux/Termux — parse `/proc/mounts`
longest-prefix match (nfs/cifs/smb/fuse/vfat/exfat/9p); WSL1 detection via `/proc/version`
"Microsoft" + fs type; macOS — `subprocess mount` output parse (stdlib, no network); Windows —
ctypes `GetVolumeInformationW` (FAT32/exFAT/NTFS) + `GetDriveTypeW` (remote). All read-only.
FAT32 check compares against the *uncompressed* payload sum as the honest upper bound (the
compressed size is unknowable at 0%) and re-checks the actual size at publish.

### F12 — Space math and the 3× problem on lived-in targets

PF-04's ×2.2 inside `$HERMES_HOME` is directionally right but understates: a lived-in target
with its own 30 GB state.db needs stage (30 GB) + backup (30 GB) + slack, and if the
`.hermespack` sits on the same filesystem its 30 GB counts too. **Required:** (1) space formula
includes the bundle when co-located; (2) BACKUP uses `os.link` hardlinks where supported (POSIX
and NTFS both support them; FAT32/exFAT do not) with copy fallback — safe because apply never
edits files in place (always `os.replace`, which unlinks the name, leaving the backup hardlink
pointing at the original inode) — turning the backup of unchanged multi-GB files into O(1)
space. Journal records `backup_kind: link|copy` so rollback and NEEDS_ATTENTION instructions
stay truthful.

### F13 — Live-source `sqlite3.backup()` can livelock on a busy DB

`Connection.backup` with default `pages=-1` copies in one pass but blocks writers; with
`pages=N` it *restarts* when the source changes between steps — on a chatty gateway a 30 GB
state.db snapshot may never converge. Upstream shares the exposure, but our live-capture banner
(P3 §6.1) makes it our support ticket. **Spec:** `pages=1024` + progress callback (feeds the
GUI bar), a restart counter, and after ~3 restarts surface "this database is too busy to
snapshot live" with the quiesce screen (§6.2) rather than spinning silently. `busy_timeout`
5000 ms as proposed.

### F14 — Installer execution: P1 vs P4 contradiction — resolve toward P4

P1 §10.1 runs the official installer from inside Talaria; P4 M8 prints the pinned command and
waits; P4 §7's README promises "no network, ever." Running `install.sh`/`install.ps1` is a
network operation executed by our process on a machine we don't control — it breaks the promise
as worded and transfers installer failure ownership to us (P4's argument, which I second on
correctness grounds: the Windows path would mean invoking PowerShell with an execution-policy
bypass from Python — terrible optics and genuinely fragile). **Adopt:** print/copy the exact
pinned command (`--commit <sha> --skip-setup`), "Done — check again" loop. If the committee
keeps a run-it-for-me button, the README's network promise must be reworded to "the tool itself
never phones home", and the button must stream installer output verbatim and disclaim ownership.

### F15 — Exit codes and schema windows: hard contradictions — unify now

- **Exit codes.** P2 §10: `0 ok · 2 verification failed · 3 blocked · 4 abort · 5
  completed-with-warnings`. P3 §13: `5 = apply failed, rollback succeeded`. A script written
  against one is dangerous against the other (P2's "warnings" is P3's "your target was
  modified and restored"). Adopt **P3's 0–9 verbatim** — it encodes the load-bearing guarantee
  ("only 5/6/7 imply the target was touched") — and rewrite P2's CLI doc to match.
- **Schema acceptance.** P3 §9.3 accepts N and N−1; P4 §10.3 rule 1 is read-*forever* with
  append-only golden bundles ("old bundles are people's backups"). These cannot both ship.
  Adopt P4: the reader keeps migration shims for *all* past schemas, enforced by the golden
  corpus in CI; refuse only newer-than-N (with the eternal-header message). P3's N−1 window
  would make a two-year-old `.hermespack` unreadable — data loss by policy.

### F16 — Smaller cross-proposal conflicts (each needs one ruling)

1. **Intent switch placement.** P2 §4.4 makes replace-vs-clone "the first question"; P1 §2 and
   P4 M5 cap the wizard at two decisions that don't include it. Ruling proposed: wizard
   defaults to `replace` silently (the research's own default rationale — integ §6), the
   switch lives at the top of Customize and as `--intent`; preflight prints the active intent
   loudly. Keeps P2's engine, preserves P1's budget.
2. **`executions.db` default:** P1 §6.1 ON (terminal rows) vs P2 §2.6 OFF. Either is safe with
   P3 §5.2's scrub; pick ON for wizard parity with "Scheduled tasks" coherence and note P2's
   table as the deviation — or flip both. One line, but today the docs disagree.
3. **Old-machine-off gate:** P1 §12 hard-gates "Start Hermes" on a single checkbox; P4 M7
   correctly notes non-device-linked platforms tolerate overlap while the new machine verifies.
   Make the hard gate conditional on device-linked platforms (WhatsApp/Signal/Matrix/relay)
   actually configured in the bundle; otherwise it is a soft confirmation. P3 §11's per-platform
   hazard list already computes exactly this set — reuse it.
4. **Deep-Scan command name:** P2 `talaria genskill` vs P3 `talaria deepscan generate`. One
   name (recommend P3's — the skill is called Deep-Scan in both), P3's trust model verbatim.
5. **Report/checklist directory:** P1 `$HERMES_HOME/migration/<ts>/` vs P3/P4
   `$HERMES_HOME/migration/talaria/<ts>/`. Adopt the namespaced form; add it to the capture
   exclusion registry (it must never be packed into a later bundle).
6. **Unrecognized-bucket disposition:** P2 §2.13 default-ON capture, P3 F22 "carried under
   quarantine prefix", P4 §10.3 "placed only with explicit consent". Compatible if stated once:
   capture ON (quarantine prefix) → apply requires consent. Write it in the spec as one rule.

### F17 — Mode-bit provenance for Windows→POSIX moves

P3 restores 0600/0700 from the classification registry — necessary but not sufficient: a
POSIX→POSIX move should preserve the *user's actual* modes (e.g. a 0755 script under
`$HH/scripts/`). **Spec:** manifest records per-file POSIX mode when the source is POSIX;
apply uses recorded modes when present, registry floor always wins for secret classes; when the
source was Windows (no modes recorded), registry supplies everything and executable-bit
inference for `scripts/**` comes from extension + shebang sniff, reported per file. Windows
targets: note "NTFS ACLs not managed" (P3 already has this).

### F18 — Assorted required specs (short)

- **`.pyz` launch copy** (P1 §4, P4 M1): "double-click works" only when the python.org launcher
  owns `.pyz`. Lead with `python talaria.pyz`; keep double-click as a parenthetical.
- **CRLF `.sh` cron scripts** applied to POSIX targets: flag in preflight ("bash will fail on
  CRLF"), never rewrite user scripts (consistent with P3 §8.3's never-list).
- **Symlinked target subtrees:** a user may have symlinked e.g. `state.db`'s parent to another
  disk. `os.replace` over a symlink replaces the *link*, and same-FS atomicity assumptions
  break. Preflight: lstat every destination parent; symlinked components ⇒ WARN + treat that
  subtree as cross-FS (copy+fsync+rename inside the real target dir).
- **chown journal records** must include pre-op uid/gid or rollback of #68483-style chowns is
  unimplementable (P3 §2.3).
- **GUI POST authentication:** the one-time URL token must be required as a header on every
  mutating request (paste-back writes secrets into `.env` — P1 §12); bind 127.0.0.1 only.
- **`~/Downloads` bundle search** (P1 §4): on Windows the Downloads folder is a Known Folder
  and may be relocated (OneDrive). Best-effort via registry Known Folders read; failure to find
  is fine, wrong-folder search is just wasted IO — LOW severity, note only.
- **`os.path.commonpath` containment** (P3 STAGE): compare `os.path.normcase`d paths on
  Windows or containment checks false-negative on case differences.

## Constraint challenges

None. All findings are implementable within the eight constraints; F6 is the closest call and
is resolved *inside* constraint 1 by recording offsets at pack time (plus optional `tzdata`
enhancement under the graceful-degradation clause). Constraint 4's wording precision proposed by
P4 §10.5 ("any Python launches it; 3.9+ runs it") is endorsed.

## Priority of required changes

**P0 (before any packer/applier code):** F1, F2, F3 (name/path/collision gates — they change the
manifest schema), F5 (rebaseline op + provenance-at-pack), F15 (exit codes + read-forever),
F4/F6/F7 (spec pins), F9 (zipapp contract), F26/eternal header ratification (with P4).
**P1:** F8, F11, F12, F13, F17, F14 ruling, F16 rulings.
**P2:** F18 items.
