# Competitor Teardown: X3N064/Hermes-Agent-Converter

Reviewed at commit head, 2026-08-15. The competitor is a single 480-line Tkinter script
(`hermes coverter.py` — the filename typo is real) plus a README. This document catalogs its
weaknesses so the design committee can guarantee we beat it on every axis, and records the few
signals worth keeping.

## What it is

A GUI that zips `~/.hermes` (excluding a hardcoded set of directory names), optionally regex-rewrites
absolute paths in text files, and on import extracts the zip over the target after an optional
`copytree` backup. Two directions only: Linux/WSL ↔ macOS.

## Cataloged weaknesses

| # | Weakness | Consequence | Our answer |
|---|----------|-------------|------------|
| W1 | Tkinter hard dependency | Fails on headless servers, many minimal Linux distros, Termux — this very build container has no tkinter | Stdlib-only core; GUI is a localhost web app (zero deps); full CLI parity for headless |
| W2 | No Windows support (two directions only) | Hermes natively supports Windows (`%LOCALAPPDATA%\hermes`) — unusable for a huge user segment | First-class Win/macOS/Linux/WSL/Termux matrix, including layout translation between `%LOCALAPPDATA%\hermes` and `~/.hermes` |
| W3 | Blind tree copy; no inventory or semantics | Doesn't know what a cron job, skill, or session DB *is*; can't make per-artifact decisions | Typed scanner: every artifact classified (kind, portability, secrets, machine-boundness) |
| W4 | Wholesale excludes `sessions`, `logs`, `cache` | Silently drops conversation history and session search DBs — the "learning loop" the user cares most about | Everything is a visible, individually selectable item with informed defaults; nothing silently dropped |
| W5 | Copies secrets in plaintext (`.env`, keys) into the zip | ~40 secret-bearing env vars (incl. `SUDO_PASSWORD`, `TERMINAL_SSH_KEY`) travel unencrypted | Secrets excluded by default; Secrets Handoff Checklist generated; opt-in encrypted vault (scrypt + AES-GCM when `cryptography` is present, honest refusal otherwise) |
| W6 | Copies machine-bound state verbatim | WhatsApp/Signal device-linked sessions, locks, PIDs, host-bound registrations break or conflict on the target | Machine-bound artifacts flagged `re-pair on target`; excluded from apply with explanation and re-setup instructions |
| W7 | Blind regex path rewriting across `.py`, `.js`, `.json`, `.env` | Rewrites `/home/<anyuser>` even inside code, docs, and unrelated strings; corrupts escaped JSON paths; hardcodes author's username `x3n064` as a default | Structured rewrite engine: path fields identified per file type via schema knowledge; previewable dry-run diff of every rewrite; JSON/YAML-aware editing; no blanket regex over source code |
| W8 | `extractall` over the live install | No merge strategy, no conflict resolution; partial failure leaves a corrupted half-restore | Transactional apply: stage → backup → apply → verify → commit, with automatic rollback on failure and a merge/overwrite/keep decision per conflict |
| W9 | Zip-slip guard uses `str.startswith` on resolved paths | `/target-evil` passes a `/target` prefix check; symlink members unhandled | Path-component-safe containment check (`os.path.commonpath` semantics), symlink and absolute-member rejection, plus bundle checksums |
| W10 | Copies live SQLite DBs file-by-file | Hermes runs WAL journaling; copying a hot DB without checkpointing corrupts it (`-wal`/`-shm` torn state) | SQLite-aware capture: `sqlite3 .backup`-equivalent snapshot via Python API, WAL checkpoint, integrity_check before packing |
| W11 | No dependency analysis | Crons/skills/MCPs silently broken on target (missing binaries, node, ffmpeg, platform-only tools) | Dependency extraction per artifact + target feasibility matrix with per-OS verdicts and remediation hints |
| W12 | No stock-vs-modified detection | Hermes is *self-improving* — skills mutate by design; blind copy can't distinguish user value from stale stock | Three-way provenance engine: stock-pristine / stock-modified (with diff) / custom, against a version-pinned upstream hash manifest |
| W13 | No verification of the result | "SKIPPED file: exc" strings are appended *into the copied-files list* and forgotten | Checksummed manifest for every payload file; post-apply verification pass; human-readable migration report |
| W14 | GUI work runs on the Tk main thread | UI freezes for the entire export of a multi-GB state dir | Background job engine with progress streaming to the GUI; cancellable operations |
| W15 | No CLI, no automation | Unusable over SSH — where most Hermes installs live ("run it on a $5 VPS") | Full CLI parity (`snapshot`, `diff`, `deps`, `pack`, `apply`, `verify`, `report`), machine-readable JSON output, scriptable |
| W16 | Guessed layout markers (`config.yaml`, `SOUL.md`, `MEMORY.md`) | Heuristic validation only; no version awareness | Layout knowledge derived from hermes-agent source (documented per finding), version detection, and graceful handling of unknown/future artifacts |
| W17 | No tests, no CI, no docs beyond a README | Unverifiable claims | Full pytest suite (unit + integration round-trip + cross-platform simulation + GUI), CI-ready, complete docs |
| W18 | Single-file bundle is a bare zip with a text-file manifest | No schema, no versioning, no integrity, no compat metadata | Versioned bundle format: JSON manifest (schema-versioned), per-file SHA-256, source-system snapshot, compat requirements, selection record |

## Signals worth keeping

- `~/.hermes` as the Unix state dir and the presence of `SOUL.md` / `MEMORY.md` / `config.yaml` / `skills/` (confirmed against hermes-agent source).
- "Original source is never modified" as a hard invariant for export — we keep and strengthen this (read-only scan; capture to staging).
- Backup-before-import instinct — we keep it, but make it transactional rather than best-effort.

## Verdict

The competitor is a zip button with a path-regex footgun. Every one of W1–W18 is addressed
by name in our spec (`docs/design/SPEC.md`), and the comparison table in the README is kept
honest against this list.
