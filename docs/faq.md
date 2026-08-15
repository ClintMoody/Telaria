# FAQ

**Do I need Hermes installed on the new machine first?**
No. Talaria places the state; Hermes adopts it when installed (before or after —
both orders work). Talaria prints the official install command but never runs
installers itself.

**Checklist or vault — which should I pick?**
Checklist, unless you have a reason. Keys stay out of the file entirely; pasting a
handful of values takes two minutes and every one gets a dashboard link. Pick the
vault when the transfer path itself is untrusted (mailing a drive, cloud relay) or
you have dozens of keys. Both are first-class.

**Is my conversation history in the bundle?**
Yes, by default — it's most of what makes your agent *yours*. It's labeled private
content throughout; treat the bundle like a private notebook, or use
`--vault --lock-everything` to encrypt it too, or `--exclude` the conversations
family (it stays safe on the old machine either way — capture never deletes).

**Why won't my WhatsApp session move?**
It's registered to the old machine (a device slot on your account). Copying it makes
the two machines fight and can unlink the account. Re-pairing on the new machine takes
about a minute and always works — the finish checklist has the exact command.

**Can both machines run my agent afterwards?**
Pack with `--intent clone` and read the hazard list: platform bots (Telegram etc.)
will answer from BOTH machines; device-linked chats pair with only one. Default intent
is replace — old gateway off once the new one starts.

**Old machine is Linux, new one is Windows (or the reverse) — really supported?**
Yes. Layouts translate (`~/.hermes` ↔ `%LOCALAPPDATA%\hermes`), path fields inside
configs and jobs are rewritten structurally (never by regex over file bytes),
Windows-illegal filenames are caught *at pack time* with verdicts, shell-script cron
jobs are flagged as impossible-on-Windows with the reason, and stock-skill provenance
hashes are rebaselined so `hermes skills list-modified` keeps telling the truth.

**What happens to my named profiles?**
They travel whole — each profile's skills, cron jobs, config, and env are their own
sub-universe, restored under `profiles/<name>/` with the same rules as the root.

**How big will the bundle be?**
Roughly your conversations + memories + skills; caches, logs, code, and node/venv
trees never travel (they're re-provisioned). The wizard shows the estimate before
packing and checks destination free space and FAT32 limits up front.

**Can I open a bundle without applying it?**
`talaria inspect <bundle>` — provenance card, `--list`, `--cat member`, `--extract`,
`--deps --target-os windows`, `--checklist`, `--verify`, and `--salvage` for damaged
files. All read-only.

**What if the apply goes wrong halfway?**
That's the tested path: automatic rollback restores the pre-apply state (verified by
re-hashing), and `talaria rollback` stays available afterwards too. The safety copy is
never deleted by a failure.

**Does it work on Termux?**
Yes, with one honest caveat the tool tells you: Android has no service manager, so
scheduled jobs only run while a foreground gateway is alive.

**I already made backups with `hermes backup` — useful?**
Yes: Talaria recognizes those zips and points you at upstream's own `hermes import`,
which is the right tool for them. Talaria bundles carry the extra intelligence
(provenance, verdicts, rewrites, rollback).

**Something in the bundle I didn't recognize?**
Unrecognized files are content-scanned at pack time (secret patterns quarantine to
credential handling; big/binary unknowns are recorded, not carried) and applying them
is a disclosed consent. `talaria why <path>` explains any file.

**Where are the reports?**
`$HERMES_HOME/migration/talaria/<timestamp>/` on the machine that ran the operation,
plus `<bundle>.checklist.html` beside the bundle at pack time. Single-file HTML,
redacted by default, print-to-PDF friendly.
