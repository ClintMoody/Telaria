# Troubleshooting — every TAL code

Every Talaria error carries a stable `TAL-xxx` code, a one-line fix, and an anchor
here. Bands: 1xx scan · 2xx pack · 3xx bundle · 4xx preflight · 5xx apply · 6xx verify
· 7xx GUI · 8xx internal.

### TAL-101 — No Hermes installation found {#tal-101}
Talaria looked at `$HERMES_HOME`, the platform default (`~/.hermes`,
`%LOCALAPPDATA%\hermes`), and found no install markers. Point it explicitly:
`talaria scan --home /path/to/.hermes`. Docker data volumes usually mount at
`/opt/data`.

### TAL-102 — Hermes update in progress {#tal-102}
A fresh `.hermes-update-in-progress` marker exists. Let `hermes update` finish (or, if
it crashed >20 minutes ago, the marker goes stale and packing proceeds).

### TAL-103 — Config schema too old {#tal-103}
Your `_config_version` predates upstream's migration floor (12). Run `hermes setup` on
the OLD machine to modernize it, then re-pack.

### TAL-104 — Unreadable state file {#tal-104}
Permissions. Run Talaria as the user who owns the Hermes home.

### TAL-201 — A database would not snapshot safely {#tal-201}
The SQLite store stayed locked or failed its integrity check across retries. Stop the
gateway (`hermes gateway stop`) so writes quiesce, then re-pack. If it persists, the
database may be corrupt — `hermes doctor` first. Databases over the cap need
`--db-cap` raised deliberately.

### TAL-202 — Not enough space to write the bundle {#tal-202}
The destination volume can't hold the estimate. Free space or pick another `-o` path;
the fallback chain is Desktop → home → current directory.

### TAL-203 — Destination can't hold a file this large {#tal-203}
FAT32/exFAT caps files at 4 GiB. Save to another drive, or shrink the selection
(conversations are usually the bulk: `--exclude "state-db@"` — they stay safe on the
old machine).

### TAL-204 — Pack self-check failed {#tal-204}
The finished archive didn't re-verify; the unpublished `.partial` was deleted. Usually
a failing disk or a file that changed mid-pack (live gateway). Quiesce and retry.

### TAL-205 — Vault unavailable {#tal-205}
`pip install cryptography`, or use checklist mode — fully supported, keys then move by
hand. Talaria never substitutes weaker crypto.

### TAL-206 — Empty vault passphrase {#tal-206}
Deliberate refusal. Pick a real passphrase.

### TAL-207 — Another backup is running {#tal-207}
Hermes' own `hermes backup` holds `.backup.lock`. Talaria waits rather than fighting;
retry in a minute.

### TAL-208 — Selection breaks a hard couple {#tal-208}
Some things only work together (a cron job and its script; skills and their provenance
files; a monitor and its baseline). The message names the couple. Re-include the named
item or drop its dependents. `talaria why` explains any member.

### TAL-301 — Bundle is damaged {#tal-301}
Checksum or structure failure. `talaria inspect <bundle> --salvage` lists exactly which
members still verify and `--extract` recovers them. Re-transfer the file if you can.

### TAL-302 — Bundle schema newer than this tool {#tal-302}
The bundle was made by a newer Talaria. Upgrade here: `pipx upgrade talaria-migration`.
(Older bundles always open in newer tools — read-forever policy.)

### TAL-303 — Hostile bundle refused {#tal-303}
A member tried path traversal, symlinks, name collisions, or lied about its size.
Nothing was written. Don't apply this file.

### TAL-304 — This is a plain `hermes backup` zip {#tal-304}
Different format, same goal. Restore it with upstream's own `hermes import <zip>` on
the target machine.

### TAL-305 — Wrong vault passphrase {#tal-305}
Nothing was written. Retype it. Ten wrong guesses cost nothing but time — but if the
passphrase is lost, vaulted members are unrecoverable by design; the checklist path
still works.

### TAL-401 — Hermes gateway is running {#tal-401}
Apply needs a stopped Hermes: `hermes gateway stop`, then retry.

### TAL-402 — Version skew blocks this apply {#tal-402}
The target's Hermes is OLDER than the source's — downgrading state is refused. Run
`hermes update` on the target. Unknown versions can proceed with `--force-skew`
(recorded in the report).

### TAL-403 — Managed or containerized target {#tal-403}
NixOS-managed (`.managed`) and in-container installs are configured by their platform;
Talaria refuses rather than fighting the activation system. Migrate the data volume /
Nix configuration instead.

### TAL-404 — Not enough disk space on the target {#tal-404}
Apply needs ~2.2× the payload (stage + safety copy). Free the printed amount.

### TAL-405 / TAL-406 — Filename collisions / Windows-illegal names {#tal-405}
This filesystem folds case/accents, or Windows forbids the name. Talaria proposes a
deterministic rename plan; accept it and the files land renamed (recorded in the
report), or exclude them.

### TAL-407 — Consent required {#tal-407}
A gate needs your explicit OK (executable content, unrecognized files, outside-home
files). Re-run and answer the prompt, or pass the named flag
(`--yes`, `--include-unrecognized`, `--include-external`).

### TAL-501 — Apply failed; everything was rolled back {#tal-501}
The target is back to its pre-apply state (verified by re-hash). The Migration Report
names the cause; fix and re-apply.

### TAL-503 — Interrupted apply detected {#tal-503}
A previous apply died mid-flight (power loss?). `talaria rollback` restores the
pre-apply state; then apply again.

### TAL-502 — Rollback incomplete — needs attention {#tal-502}
The rare double-fault. **Nothing was deleted**: the full pre-apply safety copy and the
journal paths are printed. Each journal line names a file and its backup; restore
manually or re-run `talaria rollback` after fixing the underlying problem (usually
disk-full or permissions).

### TAL-504 — Another talaria apply is running {#tal-504}
Wait for it; if it crashed, `talaria rollback`.

### TAL-505 — Rewrite needs your review {#tal-505}
A config value couldn't be rewritten mechanically (YAML anchors, list values, URLs).
`talaria apply --emit-plan plan.json` shows every entry; fix flagged ones by hand
after apply — each carries instructions.

### TAL-601 — Re-pair this device-linked connection {#tal-601}
WhatsApp/Signal/Matrix sessions are registered to a machine; copying them fights for
the account's device slot. Run the printed command (`hermes whatsapp` …) — about a
minute.

### TAL-602 — Verification found problems {#tal-602}
See the report's checks section. `talaria rollback` remains available; nothing is
deleted by verification.

### TAL-701 / TAL-702 — GUI session rejected / no browser {#tal-701}
Use the EXACT URL the terminal printed (it carries the one-time key; one browser may
drive a migration). Over SSH: `ssh -L PORT:127.0.0.1:PORT host`, then open it locally.
Termux: `termux-open-url`.

### TAL-801 — Internal error {#tal-801}
A bug in Talaria. Re-run with `--verbose` and file an issue with the output.
