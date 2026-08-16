# Adversarial Security Review — Findings & Fixes

After the implementation passed its 267-test suite, a hostile bug-hunt workflow swept the
finished code: four adversarial finders (security, engine-correctness, transactional
safety, wiring/spec) proposed defects, and independent skeptic agents tried to *refute*
each one — only findings that survived refutation (most with an executed proof-of-concept)
are listed. Eleven were confirmed and every one is now fixed with a regression test that
reproduces the original vulnerability. This is the record.

## Critical

| # | Finding | Impact | Fix | Test |
|---|---------|--------|-----|------|
| 1 | **Vault member `root_rel` arbitrary write** (`engine/apply.py`) | A hostile `.hermespack` whose passphrase the recipient holds could place a decrypted member at any path (`../.bashrc`, absolute paths) — past the never-registry and PF-18 consent, mode 0600 → code execution on next login. The section MAC was no defense: the attacker owns the passphrase and re-signs. | Validate `root_rel` (name legality + resolved containment under HERMES_HOME) before staging; `verify_structure` rejects hostile vault `root_rel` up front. | `TestVaultArbitraryWrite` (forged re-MAC'd traversal + absolute bundles) |
| 2 | **Memory-provider bundles unappliable** (`engine/pack.py`) | Synthetic external-state artifacts never entered `manifest['artifacts']`, so `verify_structure` rejected the *entire* bundle for any user with `memory.provider` set + a provider dir. Total migration failure; D16 consent dead. | Emit a manifest record per synthetic external artifact. | `TestExternalStateBundle` |
| 3 | **Rollback DB WAL data loss + crashed op** (`engine/apply.py`) | DB backup was main-file-only while sidecars were unlinked un-journaled → a rollback lost committed-but-un-checkpointed transactions; and rollback keyed on `op.done` skipped the one op that crashed mid-write, leaving a half-applied file. | Back up databases via WAL-folding snapshot; clear sidecars on restore; roll back every op that reached `op.intent`. | `TestRollbackDbIntegrity` (WAL row survives; crashed op reverts) |

## High

| # | Finding | Impact | Fix |
|---|---------|--------|-----|
| 4 | Wrong vault passphrase → `rolled_back` (exit 5) | Violated A4's "clean error, zero partial writes." | Stage/backup failures now propagate as a clean refusal (exit 3), txn torn down. |
| 5 | `is_never_path` `~/..` bypass | `~/../.ssh` escaped the home + never-registry gate (deepscan could surface protected paths). | `os.path.normpath` before every prefix check. |
| 6 | `monitor_script` recorded under `.script` locator | A rewrite would inject a bogus `script` field into a monitor job. | Distinct locators for `script` vs `monitor_script`. |
| 7 | Cross-OS rebaseline never executed | `_rebaseline_cross_os` only logged intent — stock skills' hashes stayed under source-OS semantics and froze upstream updates on a cross-OS target. | `_rebaseline_placed` runs post-placement on the real skills trees. |
| 8 | Symlinked profile dirs followed | `profile_homes` packed a symlinked profile's target (outside HERMES_HOME). | Skip symlinked profiles with a warning. |
| 9 | Apply-side coupling narrowing neutered | `--skip scripts-dir` could strand a cron job's script. | Load jobs.json + config from the bundle and enforce couples before any write. |
| 10 | `apply --emit-plan` did a full live apply | The look-before-you-leap flag mutated the target. | `--emit-plan` now implies dry-run. |

## Medium

Redaction now masks bare high-entropy `KEY=` assignments; apply tightens new credential
directories to 0700; skill artifacts carry provenance (the hub-lock couple was dead code);
one unified "Move everything in" consent discloses executable/external/unrecognized lists
(the text wizard no longer silently auto-consents to external writes and no longer runs
per-file conflict prompts — D8); the GUI gained a vault-passphrase field and unrecognized
consent; PF-01 liveness checks profile homes too.

## Why the first suite missed these

The 267 tests exercised the *intended* paths thoroughly (round-trips, honest conflicts,
crash-at-random-op). They did not model an **attacker who owns the vault passphrase**, a
**cross-OS** apply's rebaseline, a **live target database with un-checkpointed WAL**, or
**selection narrowing that strands a couple**. The adversarial pass exists precisely to
find the paths the author's own tests assume away — and it did.
