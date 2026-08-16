# C2 — Cross-Platform & Correctness Adversary Review

Reviewer: Cross-platform & correctness lens. Inputs: all four proposals (P1–P4), all eight
research docs, spot-verification against the hermes-agent clone where a claim is load-bearing
(cited as `verified: <file:line>`). Verdicts: **ACCEPT** (sound) · **MODIFY** (workable but the
stated design breaks a real scenario; change required) · **REJECT** (unimplementable/incorrect as
proposed; replacement given) · **GAP** (no proposal covers it; new requirement).

Severity: findings C2-01..C2-04 are ship-blockers; C2-05..C2-12 are correctness bugs that will
occur in the field; the rest are precision fixes.

## Verdict table

| # | Element | Source | Verdict | Required change (summary — details below) |
|---|---|---|---|---|
| 1 | Skill provenance via `.bundled_manifest` MD5, recompute/reuse "bit-exactly" | P2 §3, P1 §5, P4 §8.1 | **MODIFY** | C2-01: the hash is OS-dependent (separator + sort collation). Parameterize by source-OS semantics at pack; **rebaseline manifest entries for stock-pristine skills in stage on cross-OS apply** |
| 2 | Pid-liveness probes (PF-01, stale locks, mid-apply gateway re-probe) | P3 §3, §6.3 | **MODIFY** | C2-02: `os.kill(pid, 0)` **terminates** the process on Windows. Specify ctypes `OpenProcess`/`GetExitCodeProcess` probe; POSIX-only `os.kill(pid,0)` |
| 3 | STAGE extraction / bundle member handling | P3 §2.1 | **MODIFY** | C2-03: no case-fold or NFC/NFD collision detection → silent overwrite on NTFS/APFS. Namelist collision scan + runtime fs-behavior probe + refuse-with-rename-plan |
| 4 | Filename legality on Windows targets | all (GAP) | **GAP** | C2-04: reserved names, `<>:"|?*`, trailing dot/space. Predictive IMPOSSIBLE verdicts at pack; consented rename map at apply; **never** create via `\\?\` |
| 5 | Long-path handling (>260) with txn root inside HERMES_HOME | P3 §2.1 | **MODIFY** | C2-05: `\\?\`-prefix helper for all Win fs ops; short txn dir names; preflight row for longest *final* path vs `LongPathsEnabled` |
| 6 | "Same-filesystem atomic os.replace by construction" | P3 §2.1/§2.3 | **MODIFY** | C2-06: false for `_external/` targets (~/.honcho may be another volume). Per-destination-volume staging; EXDEV fallback protocol |
| 7 | Apply op error → immediate rollback (T1) | P3 §2.4 | **MODIFY** | C2-07: Windows AV/indexer sharing violations are transient; bounded retry-with-backoff before T1 |
| 8 | Python 3.9 floor: timestamp parsing, zoneinfo | P2 §6, P3 PF-09/10 | **MODIFY** | C2-08: 3.9 `fromisoformat` rejects `Z`; zoneinfo has **no data on Windows** without pip tzdata. Own RFC3339 parser; offset-based TZ compare; embedded Windows→IANA table if we pin `timezone:` |
| 9 | GUI assets in zipapp; localhost server | P1 §4, constraint 3 | **MODIFY** | C2-09: mandate `importlib.resources.files()` (no `__file__`), bind `127.0.0.1` literally, soften "double-click .pyz" claim (Store Python lacks the launcher association) |
| 10 | Streaming pack + hashing; walk pruning; FAT32 precheck | P1 §18, P2 §16, P4 §11 A9 | **MODIFY** | C2-10: mandate single-read hash-while-write via `ZipFile.open(name,'w')`; prune excluded dirs at descent; name the fs-type detection method per OS |
| 11 | SQLite snapshot of hot multi-GB DBs | P3 §5 | **ACCEPT+** | C2-11: specify `backup(pages=-1)` single-pass (stepped backup can livelock on a hot 30 GB DB); rest of §5 is correct |
| 12 | dotenv / YAML structural editors | P3 §8.3 | **MODIFY** | C2-12/13: preserve per-line CRLF and BOM byte-exactly; deterministic quoting rule for replacement scalars; refuse-list extended (flow style, merge keys, tabs) |
| 13 | Zip-slip guard (`commonpath` semantics) | P3 §2.1, comp W9 | **MODIFY** | C2-14: also reject backslash-bearing member names, drive letters; `normcase` before containment on Windows; degraded-input strips `__MACOSX/`, tolerates cp437 names |
| 14 | A3 "zero canaries in bundle byte-scan" | P4 §11 | **MODIFY** | C2-15: conversation DBs legitimately contain typed secrets; scope A3 to credential stores + disclose in security.md, or the test is unpassable/dishonest |
| 15 | Inline config secrets → "placeholder left" | P1 §6.1 | **MODIFY** | C2-16: `${VAR}` interpolation is only documented for `mcp_servers`; default = omit key + checklist, not invented placeholders |
| 16 | "Install Hermes for me" vs "print the pinned command" | P1 §10.1 vs P4 M8 | **CONTRADICTION** | C2-17: committee must pick one; either way neutralize installer's `maybe_start_gateway` (explicit `hermes gateway stop` before preflight) |
| 17 | Exit codes | P2 §10 vs P3 §13 | **CONTRADICTION** | C2-18: P2's 5=warnings collides with P3's 5=rolled-back. Adopt P3's table verbatim; P2 defers |
| 18 | Error-ID namespaces (WA-DEVICE-LINK / F01-F22+PF / TAL-xxx) | P1 §13, P3 §12, P4 §6 | **CONTRADICTION** | C2-18: one registry; TAL-xxx user-facing, others become internal aliases in the registry |
| 19 | Lived-in-target conflict UX | P1 §10.4 vs P2 §10 vs P4 A6/M10 | **CONTRADICTION** | C2-19: wizard = replace-with-safety-copy only; per-conflict cards live in Customize/CLI; A6 re-scoped to that path |
| 20 | `skills.external_dirs` "staged under `_external/`" | P2 §2.4 | **MODIFY** | C2-20: `_external/` encoding is home-relative only (upstream skips non-$HOME). Non-home externals: record-only + checklist by default; opt-in re-home under `$HH` + config rewrite |
| 21 | PDF checklist export; Desktop default path; `~/.config/talaria` | P1 §8/§12, P2 §11 | **MODIFY** | C2-21: no stdlib PDF — HTML with print CSS; save-path fallback chain for headless/Termux; `%APPDATA%\talaria` on Windows |
| 22 | chown mirror of #68483; secret modes | P3 §2.3 | **ACCEPT+** | POSIX-only import guards (`pwd`, `os.chown`); Windows already declared no-op — keep |
| 23 | WAL-hostile fs detection (PF-08) | P3 §3 | **MODIFY** | Name the method: `/proc/self/mounts` fstype (Linux), `statfs.f_fstypename` via ctypes (macOS), `GetDriveTypeW==DRIVE_REMOTE` (Windows); "unknown" is a legal, reported answer |
| 24 | Vault crypto sourcing | P1 §7, constraint 6 | **ACCEPT+** | Use `cryptography`'s Scrypt **and** AESGCM (one probe, one failure mode); do not mix `hashlib.scrypt` (absent on some LibreSSL builds) |
| 25 | Txn root `.talaria/` inside HERMES_HOME | P3 §2.1 | **ACCEPT+** | Correct call; add: upstream `hermes backup` will happily zip `.talaria/` into *its* archives — document, keep a README marker inside, self-exclude on capture |
| 26 | Both-sides machine-bound registry; journal+resume; read-only capture | P3 §2, §7 | **ACCEPT** | Sound; the strongest engineering in the packet |
| 27 | Rewrites computed target-side, structural locators only | P2 §8, P3 §8 | **ACCEPT** | Correct and consistent across proposals; add C2-12/13 editor rules |
| 28 | Eternal header + golden-bundle CI; 2.7-parseable stub | P4 §10 | **ACCEPT** | Adopt the "any Python launches it, 3.9+ runs it" wording precision |

## Ship-blocking findings

### C2-01 — `.bundled_manifest` hashes are not portable across OS; cross-OS migration silently freezes every stock skill
`verified: tools/skills_sync.py:254-265` — `_dir_hash()` feeds `str(fpath.relative_to(directory))`
into MD5. On Windows that string uses backslashes; on POSIX, slashes. Additionally
`sorted(directory.rglob("*"))` sorts `Path` objects, whose collation is casefolded on Windows and
case-sensitive on POSIX, so multi-file ordering differs too. The neighboring `_skill_file_list`
(line 282-285) deliberately uses `.as_posix()` — upstream fixed exactly this bug class in the hub
digest (issue #62310, cited in skills research §5) but **not** in `_dir_hash`.

Broken scenario: Linux → Windows migration carries `.bundled_manifest` verbatim (P2 §2.4 marks it
ON/forced; P1 §6.1 same). On the target, `sync_skills()` recomputes the user copy's hash with
Windows semantics → mismatch vs the carried origin hash → **every bundled skill classifies
"user-modified" → permanently skipped for updates** (skills §5 three-way table), silently. P2 §3's
"reuse the MD5 dir-hash bit-exactly" makes our own provenance engine wrong in the same move:
recomputing on the target yields "stock-modified" for pristine skills.

Required change (both sides):
1. **Pack**: provenance hashing is parameterized by *source-OS semantics* (separator + collation)
   and the manifest records which semantics produced each hash. Our engine never compares hashes
   computed under different semantics.
2. **Apply (cross-OS only)**: in stage, rewrite `.bundled_manifest`: for every skill whose
   pack-time provenance was stock-pristine, recompute the entry with **target-OS** semantics.
   Entries for genuinely modified skills are left alone (any mismatch still reads "modified" —
   correct). Same audit for `_org/*/.org-baseline.json` (separate fingerprint scheme — flag if
   present, do not guess).
3. New acceptance scenario (P4 §11): pack Linux fixture with 1 genuinely modified stock skill →
   apply on Windows → `hermes skills list-modified` reports exactly that one skill.

### C2-02 — Windows pid probe as designed will kill the gateway
Python on Windows implements `os.kill(pid, sig)` for any sig other than the two console-control
events by calling `TerminateProcess(pid, sig)`. `os.kill(pid, 0)` — the canonical POSIX liveness
probe — **unconditionally terminates the target process with exit code 0** on Windows. P3 PF-01
("gateway.pid liveness probe"), the stale-`.talaria/lock` probe (§2.1), the `.backup.lock`
freshness check, and the mid-apply gateway re-probe (§6.3) all need a probe; none specifies one.
A straight port murders the process it is checking — on the *target*, possibly mid-someone-else's
work, from a tool whose first promise is "we don't touch anything without a journal".

Required change: spec the probe as a named helper: POSIX = `os.kill(pid, 0)` catching
`ProcessLookupError`/`PermissionError`; Windows = ctypes
`OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` + `GetExitCodeProcess == STILL_ACTIVE(259)`,
fallback `tasklist /FI "PID eq N"`. Add a unit test asserting no call path reaches `os.kill` with
sig 0 on win32.

### C2-03 — Case-insensitivity and Unicode normalization: silent data loss during STAGE
Broken scenarios: (a) bundle packed on ext4 contains `session-exports/Notes.md` and `notes.md`
(legal, distinct); STAGE extraction on NTFS or APFS writes both to one file — last write wins,
hash verification of the *first* member then fails **after** its bytes are gone, or worse, both
hash-check individually during streaming and the loss is never detected. (b) A macOS source stores
a filename in NFD; a config reference typed in NFC resolves on APFS (normalization-insensitive
lookups) but dangles on ext4 after migration — no error, just a skill/script that "isn't there".

Required change:
1. STAGE pre-scan of the full namelist before any extraction: group by
   `unicodedata.normalize("NFC", name).casefold()`; also an NFD-fold pass. Collisions on an
   insensitive/normalizing stage filesystem → refuse with a rename plan (consented), never
   last-write-wins.
2. Filesystem behavior is *probed*, not assumed from `sys.platform` (Linux can mount ciopfs/SMB;
   macOS can mount case-sensitive APFS): create `probe.A`/`probe.a` and NFC/NFD probe names inside
   the txn dir and observe.
3. Pack-time predictive matrix rows (P2 §6): case-fold and NFC/NFD collision counts per declared
   target OS.
4. Preflight reference resolution runs both byte-exact and normalization/case-insensitive
   matching; anything that resolves only under the forgiving mode is flagged with the exact pair.

### C2-04 — Windows filename legality (reserved names, illegal characters) — no proposal covers it
POSIX filenames may contain `: * ? " < > |`, end in dots/spaces, or be `aux.md`, `con`, `nul.txt`,
`COM3.log`. All are uncreatable through the Win32 layer. The realistic cases in a Hermes home:
ISO-timestamped export/snapshot names with colons, agent-created skill assets with arbitrary
names. Creating them via the `\\?\` prefix "works" but produces files that Explorer, git,
PowerShell 5.1 and **Hermes itself** then cannot reliably open — strictly worse than failing.

Required change: (1) pack-time predictive verdict IMPOSSIBLE-ON-WINDOWS per offending member with
the exact offending character; (2) apply-time deterministic, manifest-recorded rename map
(percent-encoding of illegal chars + reserved-name suffixing), applied only with consent and fully
listed in the Migration Report; refuse silent munging; (3) rename map re-checked against C2-03
collision logic (a rename can newly collide).

## Field-bug findings

### C2-05 — Long paths (>260) on Windows
Stage inflates depth: `C:\Users\<u>\AppData\Local\hermes\.talaria\txn\<id>\stage\profiles\coder\
skills\<cat>\<skill>\references\...` exceeds MAX_PATH for real skill trees (485 files in stock
`skills/` alone). Required: single Windows path helper applying `\\?\` to absolute paths for all
tool I/O; txn ids ≤12 chars, stage/backup dirs named `s/`,`b/`; **final** paths are additionally
length-audited in preflight because Hermes' own runtime must open them — read
`HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled` to grade the warning (WARN
when 0 and any final path >260; the tool can still place the file, Hermes may not read it).

### C2-06 — EXDEV: external-state destinations break the "same-filesystem by construction" claim
P3 §2.1 stages everything inside target HERMES_HOME, then `os.replace`s to final. `_external/`
artifacts restore to `~/.honcho`, `~/.hindsight` — `$HOME` and `$HERMES_HOME` are routinely
different filesystems on VPSes (mounted volume for the data dir) and always different when
HERMES_HOME is a network mount. `os.replace` across devices raises `EXDEV` → spurious rollback of
an otherwise healthy apply. Required: staging is **per destination volume** (`st_dev` grouping):
external destinations get `<dest_parent>/.talaria.stage.<txn>/`; when a sibling stage dir cannot
be created, fall back to copy → fsync → `os.replace` within the destination directory. The journal
records the strategy per op; rollback understands both.

### C2-07 — Transient Windows sharing violations must not trigger rollback
Defender/Search Indexer briefly open freshly created files; `os.replace` then raises
`PermissionError` (ERROR_SHARING_VIOLATION/ACCESS_DENIED). P3 T1 as written converts a 200 ms AV
scan into a full rollback. Required: on Windows, every journaled fs op retries bounded
(6 attempts, exponential backoff to ~2.5 s total) on PermissionError before declaring T1. Document
that PF-01's gateway gate does not quiesce AV. (Same retry wraps `delete_stale` sidecar removal.)

### C2-08 — Python 3.9 floor: timestamps and timezones
(a) `datetime.fromisoformat` on 3.9 rejects `Z` and some offsets (fixed only in 3.11). Cron
`run_at`, manifest timestamps, journal timestamps from other producers must go through a small
tolerant RFC3339 parser we own. (b) `zoneinfo` (3.9 stdlib) has **no tz database on Windows**
without the third-party `tzdata` wheel — `ZoneInfo("Europe/Paris")` raises. Therefore: PF-10 TZ
comparison must not require ZoneInfo — record `(tz_name, utc_offset_now, dst_flag)` at pack;
compare names textually and offsets numerically on target; use ZoneInfo only opportunistically.
(c) Pinning `timezone:` into config.yaml from a Windows *source* requires Windows→IANA mapping
(registry `TimeZoneKeyName` → CLDR table, ~140 entries) — embed the table as data or degrade to
"pin manually" guidance; never write a Windows display name into config. (d) Ratify P4's vermin
CI gate; ban `match`, `X | Y` annotations at runtime, 3.10+ APIs.

### C2-09 — Zipapp/GUI mechanics
All asset loads via `importlib.resources.files(package)` (3.9-safe) — `__file__`-relative paths
do not exist inside a `.pyz`; add a CI test that runs the GUI server *from the built .pyz*, not
the repo. Bind and print `127.0.0.1:<port>` literally (avoid `localhost` → `::1` mismatch).
P1 §4's "double-click on Windows — the py launcher registers `.pyz`": true for python.org
installs, **false for Microsoft Store Python** (no launcher, no `.pyz` association) — soften copy
and keep the `python talaria.pyz` command primary. Test `.pyz` paths containing spaces/Unicode.

### C2-10 — Performance mechanics must be specified, not implied
(1) Hash-while-write: stream each payload file once through `ZipFile.open(name, "w")` in chunks,
updating SHA-256 in the same pass (P2 §16's "hashing on the fly" made concrete). The mandated full
re-reads are: pack self-verify, stage extract, post-apply verify — a 30 GB DB already costs 4 full
passes; forbid accidental extras (no separate "hash pass"). (2) Scanner prunes excluded dirs at
descent (`os.scandir`, skip before recursion) — filtering after enumeration re-creates the
426,543-file stall inside `node_modules`/caches. (3) FAT32/exFAT 4 GiB precheck: name the
detection — Windows `GetVolumeInformationW`, Linux `/proc/self/mounts`, macOS `statfs` via ctypes;
when undetectable and estimate >4 GiB, warn "removable-drive formats may cap files at 4 GiB".
(4) Free-space check via `shutil.disk_usage` against the *destination volume of each stage root*
(follows C2-06).

### C2-11 — Hot-DB backup convergence
`sqlite3.Connection.backup` with stepped `pages=N` restarts whenever a writer intervenes — on a
busy 30 GB `state.db` it can livelock. Use `pages=-1` (single-pass, page-streamed; holds a read
snapshot, which WAL tolerates), keep P3's retry/fail-closed ladder, and let progress reporting for
DB snapshots be file-size-based rather than page-callback-based.

### C2-12 / C2-13 — Editor byte-fidelity rules
Both structural editors (dotenv, YAML) must: split with `splitlines(keepends=True)` and re-emit
each untouched line byte-identically; preserve the file's BOM state (jobs.json is read
`utf-8-sig` upstream; a dropped/added BOM is a diff and can break naive consumers); use each
file's dominant terminator for any *inserted* line. YAML replacement scalars follow a
deterministic quoting rule: emit single-quoted (doubling embedded quotes) unless the value is
plain-safe under YAML 1.1; extend the refuse-to-edit list with flow mappings on the target line,
merge keys (`<<:`), and tab-indented documents. Windows drive paths (`C:\Users\bob`) are
plain-unsafe in some positions — the quoting rule covers them uniformly.

### C2-14 — Bundle-name hygiene beyond W9
Reject member names that are absolute, contain `..` segments, contain backslashes (hostile or
Windows-made zips; do not "helpfully" treat them as separators), or start with a drive letter.
Containment check `normcase`s both sides on Windows. Degraded `hermes backup`/hand-made zip
ingestion strips `__MACOSX/` and `.DS_Store`, and tolerates cp437-flagged (non-UTF-8) names by
reporting mojibake rather than crashing.

### C2-15 — The canary test vs conversation content
`state.db` legitimately contains secrets the user typed into chats. A3's "byte-level scan of the
bundle finds zero canaries" fails the moment a canary is also planted in a fixture conversation —
and if fixtures avoid it, the README claim overstates. Scope A3 to credential stores (the
canonical secret lists), and add to security.md: "conversation history may contain secrets you
typed; the vault option or history exclusion covers that risk."

### C2-16 — Inline config secret placeholders
`${VAR}` interpolation is documented for `mcp_servers` entries only (integ §2.1). Writing
`api_key: ${OPENAI_API_KEY}` into arbitrary config keys hands Hermes a literal string and produces
a confusing auth failure far from the migration. Default = drop the key in stage + checklist card
("re-add model.api_key"); placeholder strategy only for keys verified interpolation-aware
(venv-assisted check when available).

### C2-17 — Installer execution contradiction has a correctness core
P1 §10.1 *executes* the official installer; P4 M8 prints it and waits. Beyond product taste:
install.sh's pipeline ends in `maybe_start_gateway` (install §1), so either path can leave a
**running gateway** on the target that P3 PF-01 then refuses on — a guaranteed first-run stumble.
Whichever stance the committee ratifies, the flow must (a) pass whatever flag suppresses gateway
start if one exists, verified against the pinned installer revision, else (b) always run
`hermes gateway stop` between install and preflight, and say so on screen.

### C2-18 / C2-19 — Unifications (contradictions found)
Exit codes: P2 §10 (5 = completed-with-warnings) vs P3 §13 (5 = rolled back) — adopt P3's table
verbatim; P2's statuses live in `--json` bodies. Error IDs: three namespaces (P1 mnemonic strings,
P3 F/PF codes, P4 TAL-xxx) — one registry, TAL-xxx user-facing, others become aliases. Conflict
UX: P1 wizard offers replace-or-cancel only; P2/P4 promise per-conflict decisions — resolve as:
wizard = replace-with-safety-copy; per-conflict merge only in Customize/CLI (`--conflict`);
P4 A6 re-scoped to that path. All three must be settled before any UI or exit-code lands in code.

### C2-20 — Non-home external dirs
`_external/` encoding is home-relative by design; upstream *skips* non-$HOME paths
(state §2.2). P2 §2.4 stages arbitrary `skills.external_dirs` without a placement story for
`/opt/shared-skills`-style paths. Required policy: home-relative externals restore home-relative;
non-home externals default record-only + checklist; opt-in re-home under `$HH/external/<name>/`
with the `skills.external_dirs` pointer rewritten by the structural editor.

### C2-21 — Small platform truths
No stdlib PDF: P1 §8's "checklist (PDF/HTML)" becomes HTML with print CSS ("Save as PDF from your
browser"). Default save path `~/Desktop` doesn't exist headless/Termux — fallback chain Desktop →
home → cwd. P2 §11's `~/.config/talaria/` → `%APPDATA%\talaria` on Windows. Termux: `~/Downloads`
may not exist (needs `termux-setup-storage`) — tolerate; `webbrowser.open` may no-op — print URL +
`termux-open-url` hint. `os.chown`/`pwd` imports guarded POSIX-only (the #68483 chown mirror is
right; it just must not import-crash on Windows). Post-checklist secret paste-back (P1 §12) writes
`.env` after COMMIT — journal it as a micro-op with a `.env` backup, preserving EOL style (C2-12).

## Constraint compliance audit (stdlib-only / 3.9 / zipapp)

No proposal secretly requires a third-party package at runtime. Verified feasible in stdlib:
`winreg` (HKCU), ctypes probes (C2-02/05/10/23), `shutil.disk_usage`, `zipfile` zip64 + streaming
entry writes (3.6+), `sqlite3` ro-URI + `backup()` (3.7+), `importlib.resources.files` (3.9),
`graphlib` for coupling-rule ordering (3.9), `hashlib` SHA-256. The two places the constraint
genuinely bites — YAML editing and Windows→IANA tz mapping — are solved structurally (P3 §8.3 +
C2-13) and with embedded data (C2-08c) respectively. Vault: use `cryptography` for both Scrypt and
AES-GCM (C2-24 in table) so capability equals one import probe. Playwright (P4 §9) is dev-only —
acceptable. Mermaid appears only in docs. **CONSTRAINT CHALLENGES: none.** Adopt P4 §10.5's
wording precision ("any Python launches it; 3.9+ runs it") — the 2.7-parseable stub must itself be
lint-gated (no f-strings in `__main__.py`).

## Non-negotiable required changes (summary)

1. **C2-01** provenance hash OS-parameterization + stock-pristine rebaseline on cross-OS apply.
2. **C2-02** platform-correct pid probe; ban `os.kill(pid, 0)` on win32 by test.
3. **C2-03** case/NFC-NFD collision scan + fs probe + refuse-with-rename before extraction.
4. **C2-04** Windows filename-legality verdicts at pack, consented rename map at apply.
5. **C2-05/06/07** `\\?\` helper; per-volume staging with EXDEV fallback; Windows retry-before-rollback.
6. **C2-08** RFC3339 parser; offset-based TZ compare; no zoneinfo dependency for correctness.
7. **C2-10** hash-while-write single pass; prune-at-descent; named fs-type detection.
8. **C2-18/19** one exit-code table (P3's), one error registry (TAL-xxx), one conflict-UX story —
   ratified before code.
