# Precedent Study: Hermes' Built-in `hermes backup` / `hermes import`

Source: `hermes_cli/backup.py` (1,915 lines) + `hermes_cli/subcommands/backup.py` in
NousResearch/hermes-agent @ v2026.8.13. This is the closest in-tree precedent to our tool. It is a
*same-machine, all-or-nothing* backup; we adopt its hard-won correctness knowledge and build the
cross-machine intelligence it deliberately does not attempt.

## What it does (and we must match or exceed)

- **SQLite safety**: never file-copies live DBs. Uses `sqlite3.backup()` snapshot per DB
  (`_safe_copy_db`, `copy_db_and_verify` with `verify_sqlite_integrity`, zero-page detection via
  `is_zeroed_sqlite_file`). Excludes `-wal`/`-shm`/`-journal` sidecars because a fresh snapshot plus
  stale sidecars = torn restore (comment at `_EXCLUDED_SUFFIXES`).
- **Atomic outputs**: writes `.name.pid-tid.partial` sibling then `os.replace` (`_atomic_output_path`).
- **Cross-process lock**: single backup slot via `.backup.lock` (fcntl/msvcrt, both platforms).
- **Machine-bound runtime state is excluded on backup AND filtered again on import**
  (`_IMPORT_SKIP_NAMES`: `gateway_state.json`, `gateway.pid`, `cron.pid`, `gateway.lock`,
  `processes.json`) — restoring a foreign `gateway_state.json` broke hosted gateways (their NS-508).
  Defense on both sides because *old archives predate the exclusions* — a lesson: never trust the
  archive's own hygiene.
- **Blast-radius exclusions** (`_EXCLUDED_DIRS`): `hermes-agent` repo (re-clone instead), venvs,
  `node_modules`, `site-packages`, caches, nested `.git`, prior `backups/`, session-hash-keyed
  `checkpoints/`. Motivated by a real "backup stuck for days / 426,543 files" incident. Note the
  deliberate *inclusion* of `skills/.archive/` (curator-archived user skills are restorable value).
- **Secrets modes**: on restore, tightens `.env`, `auth.json`, `state.db` to `0600` because
  `zipfile` drops Unix mode bits.
- **External state beyond HERMES_HOME**: the active memory provider declares extra paths
  (e.g. `~/.honcho`, `~/.hindsight`) via `MemoryProvider.backup_paths()`; archived under a reserved
  `_external/` prefix encoded home-relative, restored home-relative with traversal checks.
- **Profiles**: state can live under `profiles/<name>/…`; basename-matched rules cover both.
- **Import safety**: zip validation, archive prefix auto-detection/stripping, per-member
  `resolve().relative_to(root)` traversal rejection, overwrite confirmation unless `--force`.
- **Quick snapshots**: size-capped point-in-time snapshots under a snapshot root, pruned to N;
  pre-update and pre-migration backups with their own pruning; `restore_cron_jobs_if_emptied`
  (targeted repair when an update wipes cron jobs).

## What it does NOT do (our product's reason to exist)

1. **No cross-platform translation** — no `%LOCALAPPDATA%\hermes` ↔ `~/.hermes` mapping, no path
   rewriting, no line-ending/permission strategy per OS.
2. **No inventory or explanation** — no artifact-level model of what the install contains.
3. **No provenance** — cannot tell stock skills from user-modified from agent-self-improved.
4. **No dependency intelligence** — nothing verifies the target machine can run what's inside.
5. **No selection** — fixed exclusion sets; users cannot choose per-artifact.
6. **No preflight, dry-run, or per-conflict resolution** — import is overlay-with-confirm.
7. **No verification report** — errors print to stdout and are gone.
8. **No GUI, no guidance** — no re-pairing instructions for machine-bound integrations.
9. **No target-side compat model** — assumes same machine, same OS, same user.

## Interop decisions for our tool

- **Read compatibility**: our applier accepts a plain `hermes backup` zip as a degraded input
  (detected by marker/heuristics) so users can upgrade mid-flight, but our own bundle format carries
  the intelligence layer.
- **Mirror their exclusion knowledge as defaults, cite their reasons**, keep everything visible and
  overridable in the selection model (unlike their hardcoded sets).
- **Reuse their patterns**: sqlite3.backup snapshots, atomic publish, both-sides filtering,
  mode-bit restoration, `_external/`-style home-relative encoding for outside-HOME state.
- **Do not fight their lock**: honor `.backup.lock` when capturing from a live install.
