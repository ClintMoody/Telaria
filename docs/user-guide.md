# Talaria User Guide

Talaria moves a Hermes Agent installation from one computer to another. This guide walks
both sides of a move, then the power surface.

## Before you start

- Works on Linux, macOS, native Windows, WSL, and Termux, in any direction.
- The tool must be installed on **both** machines (`pipx install talaria-migration`, or
  carry the single-file `talaria.pyz`).
- You do NOT need Hermes installed on the new machine first — Talaria places the state
  and Hermes adopts it when installed. Installing Hermes first is also fine.
- Migration is calmest with the gateway stopped (`hermes gateway stop`), but a live
  capture works and is clearly labeled.

## Side one: the old computer

Run `talaria` (or `talaria gui` for the browser). The wizard:

1. **Finds your Hermes** — shows version, install method, profiles, size. Read-only.
2. **Reads everything** — a few seconds; databases are not hashed or copied yet.
3. **Shows what travels** — six plain categories, all pre-selected: personality &
   memories, skills & plugins, scheduled tasks, conversations & history, connections &
   pairings, settings & boards. Plus what *won't* travel (machine-specific files) and
   why — nothing silently vanishes.
4. **Asks your one real question — keys & passwords:**
   - **Checklist (default).** Keys stay out of the bundle. You get
     `<bundle>.checklist.html` listing every key by NAME with where-it's-used and the
     provider's dashboard link. On the new machine you paste values in.
   - **Locked vault.** Keys travel inside the bundle, encrypted with a passphrase
     (scrypt, AES-256-GCM). Requires `pip install cryptography`. "Lock everything"
     additionally encrypts private content (conversations, memories).
5. **Packs** — live progress, then a boarding pass: the bundle path, its size, the
   checklist file, and transfer coaching.

Copy **both files** (bundle + checklist) to the new machine any way you like.

### CLI equivalent

```bash
talaria pack                          # wizard defaults, 2 questions
talaria pack --yes -o /mnt/usb/move.hermespack     # zero questions
talaria pack --vault                  # encrypted keys (prompts for passphrase)
talaria pack --preset essentials      # identity+skills+tasks+credentials+boards
talaria pack --exclude "cron-output@" # drop one artifact group (couples enforced)
talaria scan / diff / deps / report   # look before you pack
```

`talaria why <path>` explains any file's fate. `talaria report` writes the System
Overview — the full picture of what your install is and touches — without packing
anything.

## Side two: the new computer

Run `talaria` next to the bundle (or `talaria apply <bundle>`):

1. **Opens the bundle** — provenance card: where it's from, which Hermes, when, vault
   or not. A plain `hermes backup` zip is recognized and redirected to `hermes import`.
2. **Preflight** — this machine is probed and every finding lands in one of four
   groups: *Ready to move in*, *We'll fix these automatically* (path rewrites, shown
   individually), *Needs you afterwards* (checklist items), *Can't come along* (with
   the honest three sentences: what, why, what happens instead). Blockers (gateway
   running, version downgrade, managed install) stop here — nothing touched.
3. **One consent** — "Move everything in" covers the disclosed lists (executable
   content, unrecognized files, outside-home files).
4. **Applies transactionally** — safety copy → move in → make-at-home fixes → verify.
   Cancel or crash mid-way? Automatic rollback; the machine is byte-identical to
   before.
5. **Finish** — verified counts, the keys paste-back (values land in `.env` at 0600),
   re-pair cards (WhatsApp/Signal are device-linked — one minute each), `hermes
   gateway install` to register services, `hermes doctor` last. **Turn the old
   machine's gateway off before starting the new one** — they share accounts.

`talaria verify --watch` waits for the scheduler heartbeat — proof your agent is alive
on the new machine.

### CLI equivalent

```bash
talaria preflight move.hermespack             # verdicts only, no changes
talaria apply move.hermespack --dry-run       # full report, zero writes
talaria apply move.hermespack                 # interactive conflicts + consent
talaria apply move.hermespack --yes --conflict overwrite   # scripted
talaria apply move.hermespack --only soul-md@ --only memories-dir@   # narrow (never widens)
talaria rollback                              # undo the last apply
talaria verify --watch                        # health + heartbeat
```

## Lived-in targets (the machine already has Hermes data)

The wizard offers **replace with a safety copy** (recommended — the old data is backed
up in the transaction area and restorable) or cancel. The CLI has per-conflict
policies: `--conflict keep|overwrite|rename|ask`. Every decision is recorded in the
Migration Report.

## Profiles

Named profiles (`profiles/<name>/`) travel automatically with all their own skills,
cron jobs, and configs; ROOT-level singletons (kanban, shared auth) are handled once.

## The Deep-Scan (optional, advisory)

Your agent knows what it touches outside `~/.hermes` — repos it works in, tools it
calls, services it relies on. `talaria deepscan generate` writes a one-time observation
skill; your Hermes runs it and produces a JSON report (names, never values);
`talaria deepscan ingest <file>` verifies every claim. Verified paths become
*suggestions you approve* (`talaria pack --include ...`); sensitive paths (`~/.ssh`
etc.) are refused outright; fabrications land in an "agent said, unverified" appendix.
The capture set never changes without you.

## Clone vs replace

Default intent is **replace** (the old machine retires). `--intent clone` records that
both installs will live on — the finish gate then makes you acknowledge the hazards
(shared Telegram bots answer on both machines; device-linked chats can only pair one).

## Every command

```
talaria                 wizard (auto-detects direction)
talaria scan            typed inventory of the install
talaria diff skills|config|checkout     stock-vs-yours
talaria deps [--target-os X] [--live]   dependency verdicts
talaria pack            build the bundle (+ checklist HTML)
talaria inspect B       provenance card | --list --cat --extract --verify
                        --deps --checklist --salvage
talaria preflight B     check THIS machine against a bundle
talaria apply B         transactional restore
talaria verify          re-verify; --watch for the heartbeat
talaria rollback        undo the last apply (safety copy retained)
talaria report          System Overview (html/md/json, redacted by default)
talaria checklist B     the keys handoff list
talaria deepscan        generate | ingest
talaria why PATH        what is this file, does it travel, and why
talaria gui             the browser wizard
```

Every command takes `--json`; mutating commands take `--dry-run` and
`--progress ndjson`. Exit codes: 0 ok · 3 refused-nothing-modified · 4 capture failed ·
5 apply rolled back · 6 rollback needs attention · 8 version-skew block · 9 unreadable
bundle. Only 5/6 mean the target was touched.
