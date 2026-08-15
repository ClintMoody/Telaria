# Changelog

## 1.0.0 — 2026-08-15

First release. Talaria moves a Hermes Agent installation between machines — any
direction across Linux, macOS, native Windows, WSL, and Termux — as one verified,
undoable `.hermespack` file.

- Typed scanner over the real Hermes on-disk model (40+ artifact kinds, per-profile,
  both directory layout generations, reference chasing into configs/jobs/plugins).
- Six-tag skill provenance via Hermes' own mechanisms, with per-file stock diffs,
  config-vs-defaults and SOUL-vs-default comparison, checkout ref+patch capture.
- Dependency engine: enforced vs advisory extraction (skills, cron, MCP, providers)
  with per-target-OS verdicts, fully offline predictive mode, live probes.
- Streaming packer: single-pass hash+write, WAL-safe SQLite snapshots, atomic 0600
  publish with self-verify, FAT/space prechecks, machine-bound exclusion belt.
- Bundle format schema 1: eternal header, per-file SHA-256, selection record,
  predictive verdicts, salvage; full reader hardening (traversal, symlinks,
  collisions, bombs, reserved names).
- Optional vault: scrypt + HKDF + AES-256-GCM with AAD binding and section HMAC;
  honest refusal without `cryptography`; "lock everything" extends to content.
- Transactional applier: 18 preflight gates, write-ahead journal, per-file safety
  copies, structural rewrite engine (yaml/json/dotenv editors with byte fidelity and
  refuse-lists), cron claim scrubs, cross-OS provenance rebaselining, conflict
  policies, verified placement, automatic rollback, NEEDS_ATTENTION double-fault
  freeze that deletes nothing.
- Deep-Scan: nonce-bound observation skill for the user's agent + fully distrusting
  ingest (verify/refuse/appendix; values scrubbed; capture set never auto-expands).
- Reports: System Overview and Migration Report from one redacted data model —
  self-contained HTML (CSP, print CSS, light/dark), markdown, JSON.
- Interfaces: 15-subcommand CLI (--json everywhere, D3 exit codes, dry-run), text
  wizard within a 2-decision budget, hardened localhost GUI wizard (token bootstrap,
  Host/Origin checks, job engine, paste-back).
- Distribution: pip package + 141 KiB single-file `talaria.pyz` (Python 3.9 floor,
  2.7-parseable stub).
- 260+ tests: unit, integration round-trips, crash-injection rollback, hostile
  bundles, GUI endpoint security, real-browser walkthrough.
