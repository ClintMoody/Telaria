"""Talaria command line (ARCHITECTURE §13; R-CLI-*).

Every command supports --json (one schema-versioned document on stdout); mutating
commands support --dry-run and --progress ndjson; exit codes follow the D3 table —
only 5/6/7 mean the target machine was touched.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Optional

from talaria import BUNDLE_FORMAT_VERSION, __version__
from talaria.errors import (
    EXIT_INTERNAL,
    EXIT_OK,
    EXIT_USAGE,
    Refusal,
    TalariaError,
)
from talaria.events import EventLog, human_sink, ndjson_sink

HERMES_KNOWLEDGE = "hermes-agent 0.20.1 / v2026.8.13"


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if not argv:
        from talaria import wizard_cli

        return wizard_cli.run_wizard()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return EXIT_USAGE
    try:
        return args.func(args) or EXIT_OK
    except (Refusal, TalariaError) as exc:
        if getattr(args, "json", False):
            print(json.dumps({"schema_version": 1, "error": exc.to_json()}))
        else:
            print(exc.render(), file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("\ninterrupted — nothing further was changed", file=sys.stderr)
        return EXIT_INTERNAL
    except Exception as exc:  # noqa: BLE001 — last-resort TAL-801 wrapper
        print(f"[TAL-801] internal error: {exc}\n  this is a bug in talaria — re-run "
              "with --verbose and file an issue", file=sys.stderr)
        if getattr(args, "verbose", False):
            raise
        return EXIT_INTERNAL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="talaria",
        description="Talaria — moves your Hermes agent to a new computer.",
        epilog="Run with no arguments for the guided wizard. Docs: docs/user-guide.md")
    parser.add_argument("--version", action="version",
                        version=(f"talaria {__version__} · bundle schema ≤"
                                 f"{BUNDLE_FORMAT_VERSION} · knows {HERMES_KNOWLEDGE}"))
    sub = parser.add_subparsers(dest="command")

    def common(p, mutating=False):
        p.add_argument("--home", help="HERMES_HOME to operate on (default: detected)")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        p.add_argument("--quiet", action="store_true")
        p.add_argument("--verbose", action="store_true")
        p.add_argument("--non-interactive", action="store_true",
                       help="never prompt; missing decisions exit 3")
        if mutating:
            p.add_argument("--dry-run", action="store_true",
                           help="report everything, change nothing")
            p.add_argument("--progress", choices=["ndjson"], default=None)
            p.add_argument("--yes", action="store_true",
                           help="accept defaults (secret-affecting steps still gated)")

    p = sub.add_parser("scan", help="inventory a Hermes install")
    common(p)
    p.add_argument("--all-profiles", action="store_true", default=True)
    p.set_defaults(func=cmd_scan)

    p = sub.add_parser("diff", help="stock-vs-yours comparisons")
    common(p)
    p.add_argument("what", choices=["skills", "config", "checkout"])
    p.add_argument("name", nargs="?", help="skill name for `diff skills`")
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("deps", help="dependency matrix with per-OS verdicts")
    common(p)
    p.add_argument("--target-os", action="append", dest="target_oses",
                   choices=["linux", "macos", "windows", "termux"],
                   help="predictive verdicts for this OS (repeatable)")
    p.add_argument("--live", action="store_true", help="probe THIS machine")
    p.set_defaults(func=cmd_deps)

    p = sub.add_parser("pack", help="pack the install into one .hermespack file")
    common(p, mutating=True)
    p.add_argument("-o", "--output", help="output file (default: hermes-<host>-<date>"
                                          ".hermespack)")
    p.add_argument("--preset", default="everything-portable",
                   choices=["everything-portable", "essentials", "identity-only"])
    p.add_argument("--include", action="append", default=[],
                   help="artifact id to force-include (repeatable)")
    p.add_argument("--exclude", action="append", default=[],
                   help="artifact id to force-exclude (repeatable)")
    p.add_argument("--selection", help="selection JSON file")
    p.add_argument("--intent", choices=["replace", "clone"], default="replace")
    p.add_argument("--vault", action="store_true",
                   help="encrypt credentials into the bundle (needs `cryptography`)")
    p.add_argument("--lock-everything", action="store_true",
                   help="also encrypt private content (with --vault)")
    p.add_argument("--vault-passphrase-file",
                   help="read the passphrase from this file (never argv)")
    p.add_argument("--require-quiesced", action="store_true")
    p.add_argument("--db-cap", type=float, default=8.0, metavar="GiB")
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("inspect", help="look inside a bundle without applying it")
    common(p)
    p.add_argument("bundle")
    p.add_argument("--verify", action="store_true", help="full hardening + hash sweep")
    p.add_argument("--list", action="store_true", dest="list_members")
    p.add_argument("--cat", metavar="MEMBER")
    p.add_argument("--extract", metavar="GLOB")
    p.add_argument("-o", "--output-dir", default=".")
    p.add_argument("--deps", action="store_true")
    p.add_argument("--target-os", action="append", dest="target_oses",
                   choices=["linux", "macos", "windows", "termux"])
    p.add_argument("--checklist", action="store_true")
    p.add_argument("--salvage", action="store_true")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("preflight", help="check a bundle against THIS machine")
    common(p)
    p.add_argument("bundle")
    p.set_defaults(func=cmd_preflight)

    p = sub.add_parser("apply", help="move a bundle into this machine (transactional)")
    common(p, mutating=True)
    p.add_argument("bundle")
    p.add_argument("--conflict", choices=["keep", "overwrite", "rename", "ask"],
                   default="ask")
    p.add_argument("--only", action="append", default=[], metavar="ARTIFACT_ID")
    p.add_argument("--skip", action="append", default=[], metavar="ARTIFACT_ID")
    p.add_argument("--intent", choices=["replace", "clone"], default="replace")
    p.add_argument("--include-unrecognized", action="store_true")
    p.add_argument("--include-external", action="store_true",
                   help="consent to files restoring outside HERMES_HOME")
    p.add_argument("--accept-url-changes", action="store_true")
    p.add_argument("--force-skew", action="store_true")
    p.add_argument("--vault-passphrase-file")
    p.add_argument("--emit-plan", metavar="FILE",
                   help="write the rewrite plan JSON and exit")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("verify", help="re-verify the last apply on this machine")
    common(p)
    p.add_argument("--watch", action="store_true",
                   help="wait for the Hermes heartbeat (proof of life)")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("rollback", help="undo the last apply")
    common(p, mutating=True)
    p.add_argument("--txn", help="transaction id (default: latest unfinished/committed)")
    p.set_defaults(func=cmd_rollback)

    p = sub.add_parser("report", help="generate the System Overview report")
    common(p)
    p.add_argument("--format", choices=["json", "md", "html", "all"], default="all")
    p.add_argument("-o", "--output-dir")
    p.add_argument("--no-redact", action="store_true")
    p.add_argument("--redact-strict", action="store_true")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("checklist", help="print the handoff checklist for a bundle")
    common(p)
    p.add_argument("bundle")
    p.set_defaults(func=cmd_checklist)

    p = sub.add_parser("deepscan", help="agent-assisted discovery (advisory evidence)")
    common(p)
    dssub = p.add_subparsers(dest="ds_command", required=True)
    g = dssub.add_parser("generate", help="write the observation skill for your agent")
    g.add_argument("-o", "--output-dir", default=".")
    g.set_defaults(func=cmd_deepscan_generate, json=False)
    i = dssub.add_parser("ingest", help="ingest the agent's report (never trusted)")
    i.add_argument("file")
    i.add_argument("--home")
    i.add_argument("--json", action="store_true")
    i.set_defaults(func=cmd_deepscan_ingest)

    p = sub.add_parser("why", help="what is this file and does it travel?")
    common(p)
    p.add_argument("path")
    p.set_defaults(func=cmd_why)

    p = sub.add_parser("gui", help="open the browser wizard")
    common(p)
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--no-browser", action="store_true")
    p.set_defaults(func=cmd_gui)
    return parser


# --------------------------------------------------------------------------- helpers

def _resolve_home(args) -> Path:
    from talaria.engine.resolve import resolve_home

    if getattr(args, "home", None):
        return Path(args.home).expanduser()
    return resolve_home()


def _event_log(args) -> EventLog:
    if getattr(args, "progress", None) == "ndjson":
        return EventLog(sink=ndjson_sink())
    if getattr(args, "quiet", False) or getattr(args, "json", False):
        return EventLog()
    return EventLog(sink=human_sink(verbose=getattr(args, "verbose", False)))


def _emit(args, payload: dict, human: str = "") -> int:
    if getattr(args, "json", False):
        print(json.dumps({"schema_version": 1, **payload}, indent=1,
                         ensure_ascii=False))
    elif human:
        print(human)
    return EXIT_OK


def _scan_home(args, log: Optional[EventLog] = None):
    from talaria.engine.resolve import looks_like_hermes_home
    from talaria.engine.scan import scan

    home = _resolve_home(args)
    if not home.is_dir() or not looks_like_hermes_home(home):
        raise Refusal("TAL-101",
                      f"no Hermes installation at {home}",
                      fix="point me at it with --home PATH, or install Hermes first")
    return scan(home)


# --------------------------------------------------------------------------- commands

def cmd_scan(args) -> int:
    result = _scan_home(args)
    families = {}
    for art in result.artifacts:
        families.setdefault(art.family, []).append(art)
    if args.json:
        return _emit(args, {
            "identity": result.identity.to_json(),
            "capture_mode": result.capture_mode,
            "warnings": result.warnings,
            "artifacts": [a.to_json() for a in result.artifacts],
            "excluded_counts": result.excluded_counts,
            "touchpoints": [t.to_json() for t in result.touchpoints],
        })
    ident = result.identity
    print(f"Hermes {ident.hermes_version or '?'} ({ident.install_method}) at "
          f"{ident.hermes_home}")
    print(f"  profiles: root" + ("".join(", " + p for p in ident.profiles)))
    print(f"  {result.scanned_files:,} files, "
          f"{result.scanned_bytes / (1024*1024):,.1f} MiB, capture mode: "
          f"{result.capture_mode}")
    for warning in result.warnings:
        print(f"  ! {warning}")
    print()
    for family in sorted(families):
        arts = families[family]
        travel = sum(1 for a in arts if a.travels)
        size = sum(a.total_size for a in arts) / (1024 * 1024)
        print(f"  {family:24s} {len(arts):4d} item(s)  {size:9,.1f} MiB  "
              f"{travel} travel")
    return EXIT_OK


def cmd_diff(args) -> int:
    result = _scan_home(args)
    root = Path(result.identity.root)
    if args.what == "skills":
        from talaria.engine.provenance import classify_skills
        from talaria.engine.diffs import diff_modified_stock_skill

        provs = classify_skills(root / "skills")
        if args.name:
            prov = next((p for p in provs if p.name == args.name), None)
            if prov is None:
                raise Refusal("TAL-101", f"no skill named {args.name!r}")
            install_dir = Path(result.identity.install_dir) \
                if result.identity.install_dir else None
            diffs, status = diff_modified_stock_skill(install_dir, root / "skills",
                                                      prov.directory)
            if args.json:
                return _emit(args, {"skill": prov.to_json(), "status": status,
                                    "files": [d.to_json() for d in diffs]})
            print(f"{prov.name}: {prov.tag} ({status})")
            for d in diffs:
                print(d.diff or f"  {d.status}: {d.path}")
            return EXIT_OK
        if args.json:
            return _emit(args, {"skills": [p.to_json() for p in provs]})
        for p in sorted(provs, key=lambda x: (x.tag, x.name)):
            print(f"  {p.tag:16s} {p.name}")
        return EXIT_OK
    if args.what == "config":
        from talaria.engine.diffs import diff_config, extract_default_config

        install_dir = result.identity.install_dir
        defaults = extract_default_config(Path(install_dir)) if install_dir else None
        cfg_diff = diff_config(result.config.get("", {}), defaults)
        if args.json:
            return _emit(args, {"config": cfg_diff.to_json()})
        if cfg_diff.status != "ok":
            print("customized keys unknown — no Hermes venv to read defaults from")
            return EXIT_OK
        print(f"{cfg_diff.sections_customized} of {cfg_diff.sections_total} config "
              "sections customized:")
        for key, pair in sorted(cfg_diff.customized.items()):
            print(f"  {key}: {pair['default']!r} → {pair['current']!r}")
        return EXIT_OK
    from talaria.engine.diffs import checkout_state

    state = checkout_state(root)
    if args.json:
        return _emit(args, {"checkout": state.to_json()})
    print(f"checkout: {state.status}")
    if state.untracked:
        print("  untracked: " + ", ".join(state.untracked[:20]))
    if state.patch:
        print(state.patch)
    return EXIT_OK


def cmd_deps(args) -> int:
    from talaria.engine import deps as deps_engine

    result = _scan_home(args)
    findings = deps_engine.collect_all(result, Path(result.identity.root) / "skills")
    for target_os in (args.target_oses or []):
        deps_engine.evaluate_predictive(findings, target_os)
    if args.live:
        deps_engine.evaluate_live(findings)
    if args.json:
        return _emit(args, {"dependencies": [f.to_json() for f in findings]})
    for f in findings:
        verdicts = " ".join(f"{k}:{v}" for k, v in sorted(f.verdicts.items()))
        print(f"  {f.dependency.kind:14s} {f.dependency.name:32s} {verdicts}")
        if f.remediation and args.verbose:
            print(f"      → {f.remediation}")
    return EXIT_OK


def cmd_pack(args) -> int:
    import socket

    from talaria.engine.pack import PackOptions, pack
    from talaria.model.selection import Selection

    log = _event_log(args)
    result = _scan_home(args)

    selection = Selection(preset=args.preset, include=set(args.include),
                          exclude=set(args.exclude))
    if args.selection:
        selection = Selection.from_json(
            json.loads(Path(args.selection).read_text(encoding="utf-8")))

    passphrase = None
    if args.vault:
        from talaria.engine.vault import require_crypto

        require_crypto()
        if args.vault_passphrase_file:
            passphrase = Path(args.vault_passphrase_file).read_text(
                encoding="utf-8").strip()
        elif args.non_interactive:
            raise Refusal("TAL-206", "--vault needs a passphrase; pass "
                          "--vault-passphrase-file in non-interactive mode")
        else:
            passphrase = getpass.getpass("Vault passphrase (never stored): ")
            confirm = getpass.getpass("Once more: ")
            if passphrase != confirm:
                raise Refusal("TAL-206", "passphrases did not match; nothing packed")

    out = args.output or (f"hermes-{socket.gethostname()}-"
                          f"{time.strftime('%Y-%m-%d')}.hermespack")
    out_path = Path(out).expanduser()
    if getattr(args, "dry_run", False):
        from talaria.model.selection import apply_selection

        apply_selection(result.artifacts, selection)
        travel = [a for a in result.artifacts if a.travels]
        return _emit(args, {
            "mode": "dry_run", "would_pack": len(travel),
            "bytes_estimate": sum(a.total_size for a in travel),
            "output": str(out_path)},
            f"dry run: would pack {len(travel)} artifact group(s) to {out_path}")

    options = PackOptions(selection=selection, intent=args.intent,
                          vault_passphrase=passphrase,
                          lock_everything=args.lock_everything,
                          db_cap_bytes=int(args.db_cap * (1024 ** 3)),
                          require_quiesced=args.require_quiesced)
    pres = pack(result, out_path, options, log)

    from talaria.engine import checklist as cl
    from talaria.engine import report as rpt

    cards = cl.secrets_cards(pres.checklist)
    checklist_html = out_path.with_name(out_path.name + ".checklist.html")
    _write_checklist_html(checklist_html, cards, pres.manifest)

    size_mib = pres.bytes_written / (1024 * 1024)
    if args.json:
        return _emit(args, {"bundle": str(pres.bundle_path),
                            "bytes": pres.bytes_written,
                            "checklist": str(checklist_html),
                            "manifest_counts": pres.manifest.get("counts", {}),
                            "warnings": pres.warnings})
    print(f"\n  Boarding pass ─────────────────────────────")
    print(f"  bundle    {pres.bundle_path}")
    print(f"  size      {size_mib:,.1f} MiB · "
          f"{pres.manifest['counts']['files']:,} files · "
          f"{pres.manifest['counts']['artifacts']} groups")
    print(f"  checklist {checklist_html.name} (keys to re-provide on the new machine)")
    print(f"  next      copy both files over, install talaria there, run:")
    print(f"            talaria apply {pres.bundle_path.name}")
    print(f"  promise   nothing on this computer was changed or deleted")
    return EXIT_OK


def _write_checklist_html(path: Path, cards, manifest: dict) -> None:
    from talaria.engine import report as rpt

    data = rpt.ReportData(kind="migration")
    data.run = {"mode": "capture", "generated_at": time.strftime("%Y-%m-%d %H:%M")}
    data.source_system = manifest.get("source", {})
    data.actions = [c.to_json() for c in cards]
    data.checklist = manifest.get("checklist", {}).get("items", [])
    html = rpt.render_html(rpt.redact(data))
    fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(html)


def cmd_inspect(args) -> int:
    import fnmatch

    from talaria.engine.bundle import BundleReader

    with BundleReader(Path(args.bundle)) as reader:
        manifest = reader.manifest
        if args.salvage:
            report = reader.salvage_report()
            ok = sum(1 for v in report.values() if v == "ok")
            if args.json:
                return _emit(args, {"salvage": report})
            for member, verdict in report.items():
                mark = "✓" if verdict == "ok" else "✗"
                print(f"  {mark} {member}: {verdict}")
            print(f"\n{ok}/{len(report)} members verify; `--extract` recovers the "
                  "intact ones")
            return EXIT_OK
        if args.verify:
            problems = reader.verify_structure()
            hash_report = reader.salvage_report()
            bad = {m: v for m, v in hash_report.items() if v != "ok"}
            if args.json:
                return _emit(args, {"structure_problems": problems,
                                    "hash_failures": bad})
            if not problems and not bad:
                print(f"✓ bundle verifies clean ({len(hash_report)} members)")
                return EXIT_OK
            for p in problems:
                print(f"  ✗ {p}")
            for m, v in bad.items():
                print(f"  ✗ {m}: {v}")
            return 9
        if args.cat:
            blob = reader.read_meta(args.cat) if args.cat.startswith("meta/") else None
            if blob is None:
                assert reader.zf is not None
                try:
                    blob = reader.zf.read(args.cat)
                except KeyError:
                    raise Refusal("TAL-301", f"no member named {args.cat}")
            sys.stdout.write(blob.decode("utf-8", errors="replace"))
            return EXIT_OK
        if args.extract:
            out_dir = Path(args.output_dir)
            count = 0
            for rec in reader.iter_payload():
                if fnmatch.fnmatch(rec.member, args.extract) or \
                        fnmatch.fnmatch(rec.home_rel, args.extract):
                    reader.extract_member(rec.member, out_dir / rec.home_rel)
                    count += 1
            print(f"extracted {count} member(s) to {out_dir}")
            return EXIT_OK
        if args.deps:
            from talaria.engine import deps as deps_engine

            findings = deps_engine.evaluate_members_for_windows(
                [r.home_rel for r in reader.iter_payload()])
            preds = (manifest.get("predictive") or {})
            if args.json:
                return _emit(args, {"predictive": preds,
                                    "member_findings": [f.to_json() for f in findings]})
            for target in (args.target_oses or ["windows"]):
                print(f"— {target} —")
                if target == "windows":
                    illegal = preds.get("windows", {}).get("illegal_names", [])
                    for item in illegal:
                        print(f"  impossible: {item['member']} "
                              f"({'; '.join(item['problems'])})")
                    if not illegal:
                        print("  all member names legal")
            return EXIT_OK
        if args.checklist:
            items = manifest.get("checklist", {}).get("items", [])
            if args.json:
                return _emit(args, {"checklist": items})
            for item in items:
                print(f"  {item['name']}  (used by {item.get('file', '?')})")
            return EXIT_OK
        if args.list_members:
            for rec in reader.iter_payload():
                print(f"  {rec.size:>12,}  {rec.member}")
            return EXIT_OK
        # Default: the provenance card.
        header = reader.header
        source = manifest.get("source", {})
        counts = manifest.get("counts", {})
        if args.json:
            return _emit(args, {"header": header.to_json() if header else {},
                                "counts": counts,
                                "vault": manifest.get("vault", {}).get("present"),
                                "intent": manifest.get("intent")})
        print(f"Talaria bundle · schema {header.schema_version if header else '?'}")
        print(f"  from      {source.get('hostname', '?')} "
              f"({source.get('os', '?')}, Hermes {source.get('hermes_version', '?')})")
        print(f"  created   {header.created_at if header else '?'} by talaria "
              f"{header.created_by_tool_version if header else '?'}")
        print(f"  contents  {counts.get('files', 0):,} files · "
              f"{counts.get('artifacts', 0)} groups · "
              f"{manifest.get('bytes', {}).get('payload', 0) / (1024*1024):,.1f} MiB")
        print(f"  vault     {'yes' if manifest.get('vault', {}).get('present') else 'no'}"
              f" · intent {manifest.get('intent', 'replace')}")
        return EXIT_OK


def cmd_preflight(args) -> int:
    from talaria.engine.bundle import BundleReader
    from talaria.engine.preflight import run_preflight

    home = _resolve_home(args)
    with BundleReader(Path(args.bundle)) as reader:
        problems = reader.verify_structure()
        if problems:
            raise Refusal("TAL-303", "bundle failed hardening: " + problems[0])
        report = run_preflight(reader, home)
    if args.json:
        return _emit(args, {"preflight": report.to_json()})
    groups = {"ok": [], "warn": [], "consent": [], "refuse": []}
    for gate in report.gates:
        groups[gate.status].append(gate)
    for status, title in (("refuse", "✗ Blocks the move"),
                          ("consent", "? Needs your OK"),
                          ("warn", "! Worth knowing"),
                          ("ok", "✓ Ready")):
        gates = groups[status]
        if not gates:
            continue
        print(f"\n{title}")
        for g in gates:
            print(f"  [{g.id}] {g.title}" + (f" — {g.detail}" if g.detail else ""))
            if g.fix and status in ("refuse", "consent"):
                print(f"        fix: {g.fix}")
    return 3 if report.refusals else EXIT_OK


def cmd_apply(args) -> int:
    from talaria.engine.apply import ApplyOptions, apply_bundle
    from talaria.engine import checklist as cl
    from talaria.engine import report as rpt
    from talaria.engine.bundle import BundleReader
    from talaria.engine.verify import functional_checks

    home = _resolve_home(args)
    log = _event_log(args)

    passphrase = None
    if args.vault_passphrase_file:
        passphrase = Path(args.vault_passphrase_file).read_text(
            encoding="utf-8").strip()
    else:
        with BundleReader(Path(args.bundle)) as peek:
            has_vault = (peek.manifest.get("vault") or {}).get("present")
        if has_vault and not args.non_interactive and not args.dry_run:
            passphrase = getpass.getpass(
                "This bundle has a locked vault. Passphrase (Enter to skip — "
                "credentials then stay on the checklist): ") or None

    ask = None
    if args.conflict == "ask" and not args.non_interactive:
        def ask(path: str) -> str:
            while True:
                answer = input(f"  {path} already exists here — keep yours, take "
                               "theirs, or keep both? [keep/take/both]: ").strip().lower()
                if answer in ("keep", "k"):
                    return "keep"
                if answer in ("take", "t", "overwrite"):
                    return "overwrite"
                if answer in ("both", "b", "rename"):
                    return "rename"
    elif args.conflict == "ask":
        args.conflict = "keep"  # non-interactive default: never clobber silently

    # One unified "Move everything in" consent discloses every gated list (executable
    # content, files that restore outside HERMES_HOME, and unrecognized files) — D9/D16/
    # SEC-09: a single yes covers them, matching the GUI's one consent moment. Nothing is
    # auto-consented silently.
    consent_exec = args.yes
    consent_external = args.include_external
    consent_unrecognized = args.include_unrecognized
    if not args.yes and not args.non_interactive and not args.dry_run:
        from talaria.engine.preflight import run_preflight

        with BundleReader(Path(args.bundle)) as peek:
            peek.verify_structure()
            pf = run_preflight(peek, home)
        disclosures = []
        exec_summary = {k: v for k, v in pf.executable_summary.items() if v}
        if exec_summary:
            disclosures.append("  • runs on this machine: " +
                               ", ".join(f"{v} {k}" for k, v in exec_summary.items()))
        externals = [g for g in pf.gates if g.id == "PF-18"]
        if externals:
            disclosures.append(f"  • {externals[0].detail}")
        unrec = [g for g in pf.gates if g.id == "PF-17"]
        if unrec:
            disclosures.append(f"  • {unrec[0].detail}")
        print("Applying a bundle installs software this machine will run (skills, "
              "scripts, plugins, MCP commands).")
        for line in disclosures:
            print(line)
        answer = input("Move everything in? [y/N]: ").strip().lower()
        if answer not in ("y", "yes"):
            raise Refusal("TAL-407", "you declined the consent prompt")
        consent_exec = True
        consent_external = consent_external or bool(externals)
        consent_unrecognized = consent_unrecognized or bool(unrec)

    # --emit-plan is a look-before-you-leap: build the rewrite plan and write it WITHOUT
    # mutating the target. It implies dry-run so `apply --emit-plan` never applies.
    emit_only = bool(args.emit_plan)

    options = ApplyOptions(
        conflict_policy=args.conflict if args.conflict != "ask" or ask is None
        else "ask",
        ask=ask, only=tuple(args.only), skip=tuple(args.skip),
        include_unrecognized=consent_unrecognized or args.dry_run or emit_only,
        accept_url_changes=args.accept_url_changes,
        intent=args.intent, dry_run=args.dry_run or emit_only,
        force_skew=args.force_skew,
        vault_passphrase=passphrase,
        consent_executable=consent_exec or args.dry_run or emit_only,
        consent_external=consent_external or args.dry_run or emit_only)

    outcome = apply_bundle(Path(args.bundle), home, options, log)

    if args.emit_plan and outcome.plan is not None:
        Path(args.emit_plan).write_text(
            json.dumps(outcome.plan.to_json(), indent=1), encoding="utf-8")
        if emit_only:
            return _emit(args, {"emitted_plan": args.emit_plan,
                                "entries": len(outcome.plan.entries)},
                         f"✓ rewrite plan written to {args.emit_plan} "
                         f"({len(outcome.plan.entries)} entries); nothing was applied")

    with BundleReader(Path(args.bundle)) as reader:
        manifest = reader.manifest
    checks = [c.to_json() for c in functional_checks(home)] \
        if outcome.status == "committed" else []
    cards = cl.post_restore_cards(manifest, outcome.to_json()) + \
        cl.secrets_cards(manifest.get("checklist", {}).get("items", []))
    report_dir = home / "migration" / "talaria" / time.strftime("%Y%m%d-%H%M%S")
    if outcome.status != "dry_run":
        data = rpt.build_migration(outcome.to_json(), manifest, checks,
                                   [c.to_json() for c in cards])
        rpt.write_reports(data, report_dir)
        cl.save_state(report_dir / "checklist.json", cards)

    if args.json:
        return _json_apply_result(args, outcome, report_dir)
    if outcome.status == "committed":
        print(f"\n  ✓ Moved in and double-checked ({len(outcome.placed)} files)")
        print(f"  report   {report_dir / 'report.html'}")
        print(f"  undo     talaria rollback   (any time until you trust the result)")
        print("\n  Before you start Hermes here:")
        for card in cards[:8]:
            cmd = f"  →  {card.command}" if card.command else ""
            print(f"   [ ] {card.verb}: {card.title}{cmd}")
        print("\n  Turn the OLD machine's gateway off before starting it here "
              "(they share accounts).")
    elif outcome.status == "rolled_back":
        print("\n  ✗ Something failed — everything was rolled back; this machine is "
              "unchanged.")
        for failure in outcome.failures:
            print(f"    cause: {failure}")
    elif outcome.status == "needs_attention":
        print("\n  ✗✗ Rollback incomplete — NOTHING was deleted.")
        print(f"    safety copy: {outcome.backup_dir}")
        print(f"    journal:     {outcome.journal_path}")
    elif outcome.status == "dry_run":
        print("\n  dry run — nothing was written. Rewrite plan preview:")
        if outcome.plan:
            for entry in outcome.plan.entries[:20]:
                print("   " + entry.preview().replace("\n", "\n   "))
    return outcome.exit_code


def _json_apply_result(args, outcome, report_dir) -> int:
    print(json.dumps({"schema_version": 1, "apply": outcome.to_json(),
                      "report_dir": str(report_dir)}, indent=1, ensure_ascii=False))
    return outcome.exit_code


def cmd_verify(args) -> int:
    from talaria.engine.verify import verify_last_apply, watch_heartbeat

    home = _resolve_home(args)
    checks = verify_last_apply(home)
    if args.watch:
        checks.append(watch_heartbeat(home))
    if args.json:
        return _emit(args, {"checks": [c.to_json() for c in checks]})
    worst = EXIT_OK
    for c in checks:
        mark = {"ok": "✓", "warn": "!", "fail": "✗", "info": "·"}.get(c.status, "·")
        print(f"  {mark} {c.title}" + (f" — {c.detail}" if c.detail else ""))
        if c.status == "fail":
            worst = 1
    return worst


def cmd_rollback(args) -> int:
    from talaria.engine.apply import (
        TXN_DIRNAME,
        Journal,
        find_unfinished_txn,
        rollback_journal,
    )

    home = _resolve_home(args)
    txn_dir = None
    if args.txn:
        candidate = home / TXN_DIRNAME / "txn" / args.txn
        if (candidate / "journal.jsonl").is_file():
            txn_dir = candidate
    else:
        txn_dir = find_unfinished_txn(home)
        if txn_dir is None:
            txn_root = home / TXN_DIRNAME / "txn"
            if txn_root.is_dir():
                for cand in sorted(txn_root.iterdir(), reverse=True):
                    if (cand / "journal.jsonl").is_file():
                        txn_dir = cand
                        break
    if txn_dir is None:
        raise Refusal("TAL-503", "no transaction to roll back here")
    if args.dry_run:
        records = Journal.read_all(txn_dir / "journal.jsonl")
        ops = [r for r in records if r.get("event") == "op.done"
               and r.get("kind") in ("replace_file", "db_place", "delete_stale")]
        return _emit(args, {"mode": "dry_run", "txn": txn_dir.name,
                            "would_restore": len(ops)},
                     f"dry run: would restore {len(ops)} file(s) from txn "
                     f"{txn_dir.name}")
    restored = rollback_journal(txn_dir / "journal.jsonl", home)
    with open(txn_dir / "journal.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"seq": 999999, "ts": time.time(),
                             "event": "rollback.done", "ok": True,
                             "via": "talaria rollback"}) + "\n")
    return _emit(args, {"rolled_back": restored, "txn": txn_dir.name},
                 f"✓ restored {len(restored)} path(s) from transaction {txn_dir.name}; "
                 "the safety copy remains in place")


def cmd_report(args) -> int:
    from talaria.engine import deps as deps_engine
    from talaria.engine import report as rpt
    from talaria.engine.diffs import diff_config, extract_default_config
    from talaria.engine.provenance import classify_skills

    result = _scan_home(args)
    root = Path(result.identity.root)
    provs = [p.to_json() for p in classify_skills(root / "skills")] \
        if (root / "skills").is_dir() else []
    findings = deps_engine.collect_all(result, root / "skills")
    for target_os in ("linux", "macos", "windows"):
        deps_engine.evaluate_predictive(findings, target_os)
    install_dir = result.identity.install_dir
    defaults = extract_default_config(Path(install_dir)) if install_dir else None
    cfg_diff = diff_config(result.config.get("", {}), defaults)

    data = rpt.build_overview(result, provs, [f.to_json() for f in findings],
                              cfg_diff.to_json())
    redaction = "none" if args.no_redact else \
        "strict" if args.redact_strict else "default"
    out_dir = Path(args.output_dir) if args.output_dir else \
        root / "migration" / "talaria" / time.strftime("%Y%m%d-%H%M%S")
    outputs = rpt.write_reports(data, out_dir, redaction)
    return _emit(args, {"outputs": {k: str(v) for k, v in outputs.items()}},
                 f"✓ System Overview written:\n  {outputs['html']}\n  "
                 f"{outputs['md']}\n  {outputs['json']}")


def cmd_checklist(args) -> int:
    from talaria.engine import checklist as cl
    from talaria.engine.bundle import BundleReader

    with BundleReader(Path(args.bundle)) as reader:
        manifest = reader.manifest
    cards = cl.secrets_cards(manifest.get("checklist", {}).get("items", []))
    if args.json:
        return _emit(args, {"cards": [c.to_json() for c in cards]})
    print("Keys and passwords to re-provide on the new machine (values never "
          "travel in the bundle):")
    for card in cards:
        url = f"  ({card.url})" if card.url else ""
        print(f"  [ ] {card.title}{url}")
        if card.detail:
            print(f"      {card.detail}")
    return EXIT_OK


def cmd_deepscan_generate(args) -> int:
    from talaria.engine.deepscan import generate_skill

    out_dir = Path(args.output_dir)
    skill_dir, nonce = generate_skill(out_dir)
    print(f"✓ observation skill written to {skill_dir}")
    print(f"  1. copy it into the OLD machine's ~/.hermes/skills/productivity/")
    print(f"  2. ask your Hermes: \"run the talaria deep-scan skill\"")
    print(f"  3. it writes talaria-deepscan-{nonce}.json — bring that file here and run:")
    print(f"     talaria deepscan ingest talaria-deepscan-{nonce}.json")
    print("  The agent's report is advisory evidence only — it can suggest, never "
          "decide.")
    return EXIT_OK


def cmd_deepscan_ingest(args) -> int:
    from talaria.engine.deepscan import ingest_report

    home = Path(args.home).expanduser() if args.home else _resolve_home(args)
    result = ingest_report(Path(args.file), home)
    if getattr(args, "json", False):
        return _emit(args, {"deepscan": result.to_json()})
    print(f"✓ ingested (nonce ok, schema ok, {result.scrubbed} value(s) scrubbed)")
    if result.candidates:
        print("\nVerified candidates (opt in with `talaria pack --include ...`):")
        for c in result.candidates:
            print(f"  + {c['path']}  ({c['note']})")
    if result.refused:
        print("\nRefused by the never-registry (shown for transparency, never offered):")
        for r in result.refused:
            print(f"  ✗ {r['path']}  ({r['reason']})")
    if result.unverified:
        print("\nAgent said, unverified (no such path here):")
        for u in result.unverified:
            print(f"  ? {u}")
    return EXIT_OK


def cmd_why(args) -> int:
    from talaria.model.catalog import classify

    home = _resolve_home(args)
    raw = Path(args.path)
    try:
        rel = raw.resolve().relative_to(home.resolve()).as_posix() \
            if raw.is_absolute() else args.path
    except ValueError:
        rel = args.path
    cls = classify(str(rel))
    travels = {"on": "travels by default", "off": "stays unless selected",
               "record_only": "recorded in the report, not carried",
               "never": "never travels"}[cls.default]
    if args.json:
        return _emit(args, {"path": str(rel), "kind": cls.kind, "family": cls.family,
                            "portability": cls.portability, "secrecy": cls.secrecy,
                            "default": cls.default, "reason": cls.reason})
    print(f"{rel}")
    print(f"  what:   {cls.kind} ({cls.family})")
    print(f"  moves?  {travels}"
          + (" — credential handling applies" if cls.secrecy == "credential" else ""))
    if cls.reason:
        print(f"  why:    {cls.reason}")
    return EXIT_OK


def cmd_gui(args) -> int:
    from talaria.gui.server import serve

    return serve(port=args.port, open_browser=not args.no_browser,
                 home=_resolve_home(args))


if __name__ == "__main__":
    sys.exit(main())
