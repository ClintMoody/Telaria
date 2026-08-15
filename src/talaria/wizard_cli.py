"""The text wizard: the identical S0–S4 / T1–T4 flow as numbered prompts (R-CLI-03).

Pure stdin/stdout — no curses. Answering every prompt with Enter completes the happy
path within the decision budget (R-UX-01: ≤2 source-side decisions).
"""

from __future__ import annotations

import getpass
import sys
import time
from pathlib import Path
from typing import List, Optional

from talaria.errors import EXIT_OK, EXIT_USAGE, Refusal, TalariaError
from talaria.events import EventLog, human_sink

PROMISES = (
    "Nothing on this computer is changed or deleted.",
    "Anything we change on the new computer can be undone.",
    "Anything we can't move automatically goes on your checklist. "
    "Nothing silently vanishes.",
)


def _say(text: str = "") -> None:
    print(text)


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def run_wizard() -> int:
    from talaria.engine.bundle import BundleKind, detect_kind
    from talaria.engine.resolve import looks_like_hermes_home, resolve_home

    _say()
    _say("  ⤞ Talaria — moves your Hermes agent to a new computer")
    _say("  " + "─" * 58)

    home = resolve_home()
    hermes_here = home.is_dir() and looks_like_hermes_home(home)
    bundles = sorted(Path.cwd().glob("*.hermespack")) + \
        sorted((Path.home() / "Desktop").glob("*.hermespack")
               if (Path.home() / "Desktop").is_dir() else [])
    bundles = [b for b in bundles if detect_kind(b)[0] == BundleKind.TALARIA]

    if hermes_here and not bundles:
        return _wizard_pack(home)
    if bundles and not hermes_here:
        return _wizard_apply(bundles[0], home)
    if hermes_here and bundles:
        _say(f"\n  Found BOTH a Hermes install ({home}) and a bundle "
             f"({bundles[0].name}).")
        choice = _ask("  Pack this machine (p) or apply the bundle here (a)?", "p")
        if choice.lower().startswith("a"):
            return _wizard_apply(bundles[0], home)
        return _wizard_pack(home)
    _say("\n  No Hermes install and no .hermespack bundle found here.")
    _say("  • To pack: run me on the machine where Hermes lives.")
    _say("  • To apply: put the .hermespack file next to me (or pass it: "
         "talaria apply FILE).")
    _say("  • Install Hermes first? Official command (copy it — I never run "
         "installers):")
    _say("      curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash")
    return EXIT_USAGE


# --------------------------------------------------------------------------- pack side

def _wizard_pack(home: Path) -> int:
    import socket

    from talaria.engine.pack import PackOptions, pack
    from talaria.engine.scan import scan
    from talaria.engine.vault import crypto_available
    from talaria.engine import checklist as cl
    from talaria.cli import _write_checklist_html

    # S0 — detect & greet
    _say(f"\n  S0 · Found your Hermes at {home}")
    for promise in PROMISES[:1]:
        _say(f"       promise: {promise}")
    _say("\n  S1 · Reading what's here (nothing is modified)…")
    result = scan(home)
    ident = result.identity
    if result.refusals:
        raise Refusal("TAL-102", result.refusals[0])

    # S1 — scan narrative
    fam = {}
    for art in result.artifacts:
        if art.travels:
            fam.setdefault(art.family, [0, 0])
            fam[art.family][0] += 1
            fam[art.family][1] += art.total_size
    _say(f"       Hermes {ident.hermes_version or '?'} · "
         f"{result.scanned_files:,} files · "
         f"{result.scanned_bytes / (1024*1024):,.1f} MiB"
         + (f" · profiles: {', '.join(ident.profiles)}" if ident.profiles else ""))
    for warning in result.warnings:
        _say(f"       ! {warning}")

    # S2 — review (six category rows, informational)
    _say("\n  S2 · What travels (everything portable is pre-selected):")
    labels = {
        "identity-memory": "Personality & memories",
        "skills": "Skills", "plugins": "Plugins",
        "automations": "Scheduled tasks",
        "conversations-history": "Conversations & history (private content)",
        "platforms-messaging": "Connections & pairings (private content)",
        "configuration": "Settings", "boards-projects": "Projects & boards",
        "credentials": "Keys & passwords (handled next)",
        "unrecognized": "Other files (safety-scanned)",
    }
    for family, (count, size) in sorted(fam.items()):
        label = labels.get(family, family)
        _say(f"       [x] {label:44s} {count:4d} item(s) "
             f"{size / (1024*1024):9,.1f} MiB")
    wont = sum(v for k, v in result.excluded_counts.items())
    _say(f"       (i) Won't travel: {wont} machine-specific file(s) — services, "
         "device pairings, caches; the checklist covers re-creating them")
    _say("       (fine-grained selection: `talaria pack --include/--exclude`; "
         "`talaria why PATH` explains any file)")

    # S3 — keys & passwords (DECISION 1)
    _say("\n  S3 · Keys & passwords — your keys are like the keys in your pocket:")
    _say("       they move with YOU, not with the moving boxes.")
    _say("       1. Checklist (default): keys stay OUT of the bundle; you paste them "
         "on the new machine from a generated checklist.")
    if crypto_available():
        _say("       2. Locked vault: keys travel encrypted (scrypt + AES-256-GCM) "
             "under a passphrase you choose.")
    else:
        _say("       2. Locked vault: unavailable — `pip install cryptography` to "
             "enable. Checklist mode works fully without it.")
    choice = _ask("       Your choice", "1")
    passphrase = None
    if choice.strip() == "2" and crypto_available():
        while True:
            passphrase = getpass.getpass("       Vault passphrase (never stored): ")
            if not passphrase:
                _say("       An empty passphrase is refused.")
                continue
            if getpass.getpass("       Once more: ") == passphrase:
                break
            _say("       Didn't match — again.")

    # S4 — pack (DECISION 2, weak: location)
    default_out = str(Path.home() / f"hermes-{socket.gethostname()}-"
                      f"{time.strftime('%Y-%m-%d')}.hermespack")
    out = Path(_ask("\n  S4 · Save the bundle to", default_out)).expanduser()
    log = EventLog(sink=human_sink())
    pres = pack(result, out, PackOptions(vault_passphrase=passphrase), log)
    cards = cl.secrets_cards(pres.checklist)
    checklist_html = out.with_name(out.name + ".checklist.html")
    _write_checklist_html(checklist_html, cards, pres.manifest)

    _say("\n  ✓ Boarding pass")
    _say(f"    bundle     {pres.bundle_path}")
    _say(f"    size       {pres.bytes_written / (1024*1024):,.1f} MiB")
    _say(f"    checklist  {checklist_html}")
    _say("    next steps 1. copy BOTH files to the new computer (USB, scp, drive)")
    _say("               2. install talaria there (pipx install talaria-migration)")
    _say(f"               3. run: talaria apply {pres.bundle_path.name}")
    _say("    retiring?  leave this machine's Hermes OFF once the new one starts —")
    _say("               they share the same accounts and pairings.")
    return EXIT_OK


# --------------------------------------------------------------------------- apply side

def _wizard_apply(bundle: Path, home: Path) -> int:
    from talaria.cli import cmd_apply

    _say(f"\n  T1 · Found bundle {bundle.name}")

    class _Args:
        pass

    args = _Args()
    args.bundle = str(bundle)
    args.home = str(home)
    args.json = False
    args.quiet = False
    args.verbose = False
    args.non_interactive = False
    args.dry_run = False
    args.progress = None
    args.yes = False
    args.conflict = "ask"
    args.only = []
    args.skip = []
    args.intent = "replace"
    args.include_unrecognized = False
    args.include_external = True
    args.accept_url_changes = False
    args.force_skew = False
    args.vault_passphrase_file = None
    args.emit_plan = None
    return cmd_apply(args)
