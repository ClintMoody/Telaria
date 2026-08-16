#!/usr/bin/env python3
"""Capture Talaria GUI screenshots (light + dark) for the docs.

Builds a realistically-sized synthetic install so the review/preflight/finish screens
show believable counts and sizes, drives the real wizard through both flows in a headless
Chromium, and writes retina PNGs to docs/img/. Hermetic: HOME is redirected to a temp dir.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402
from talaria.gui import server as gui_server  # noqa: E402

IMG = ROOT / "docs" / "img"
SKILL_CATALOG = [
    ("research", ["web-search", "arxiv-digest", "competitor-watch", "fact-check"]),
    ("productivity", ["daily-brief", "inbox-triage", "meeting-notes", "weekly-review"]),
    ("creative", ["playlist-curator", "cover-art", "story-outliner"]),
    ("devops", ["deploy-watch", "log-triage", "cost-report", "backup-audit"]),
    ("finance", ["budget-watch", "invoice-parser", "portfolio-digest"]),
    ("communication", ["standup-summary", "slack-digest", "reply-drafter"]),
    ("data-science", ["notebook-runner", "chart-builder"]),
    ("home", ["thermostat-tuner", "grocery-list", "plant-care"]),
]

SKILL_BODY = """---
name: {name}
description: {desc}
version: 1.2.0
author: {author}
license: MIT
metadata:
  hermes:
    tags: [{cat}]
---

# {title}

{desc}. This skill was refined over many runs.

## Steps
1. Gather the inputs.
2. Do the work carefully.
3. Deliver a crisp result and cite sources.
"""


def enrich(inst) -> None:
    """Add skills, memories, cron jobs, and a chunky session DB for realistic numbers."""
    home = inst.home
    manifest_lines = (home / "skills" / ".bundled_manifest").read_text().splitlines()

    # More skills across categories (a few marked modified/agent to show provenance).
    from hermes_factory import skills_dir_hash

    for cat, names in SKILL_CATALOG:
        for i, name in enumerate(names):
            d = home / "skills" / cat / name
            if d.exists():
                continue
            author = "hermes" if (i == 0 and cat in ("creative", "devops")) else "Nous Research"
            (d).mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(SKILL_BODY.format(
                name=name, desc=f"Handle {name.replace('-', ' ')} tasks end to end",
                title=name.replace("-", " ").title(), cat=cat, author=author))
            (d / "references").mkdir(exist_ok=True)
            (d / "references" / "notes.md").write_text("# Notes\n\n" + ("detail. " * 40))
            if author == "Nous Research":
                manifest_lines.append(f"{name}:{skills_dir_hash(d)}")
    (home / "skills" / ".bundled_manifest").write_text("\n".join(manifest_lines) + "\n")

    # Fuller memories.
    (home / "memories" / "MEMORY.md").write_text(
        "Alice prefers metric units and terse summaries.\n§\n"
        "The home NAS is at 10.0.0.5; media lives under /volume1.\n§\n"
        "Ship reports as Markdown, not PDF.\n§\n"
        "Standup is 09:30 Europe/Paris.\n")

    # A chunky state.db so Conversations shows real MiB.
    db = home / "state.db"
    conn = sqlite3.connect(db)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        blob = "The agent and the user discussed the migration plan in detail. " * 60
        conn.executemany(
            "INSERT INTO messages (id, session_key, role, content) VALUES (?,?,?,?)",
            [(f"pad{i}", f"sess-{i % 12}", "user" if i % 2 else "assistant",
              blob + str(i)) for i in range(1, 4000)])
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()

    # A few more cron jobs.
    jobs_file = home / "cron" / "jobs.json"
    data = json.loads(jobs_file.read_text())
    for i, (name, expr, deliver) in enumerate([
        ("Weekly cost report", "0 9 * * 1", "slack"),
        ("Nightly backup audit", "0 3 * * *", "email"),
        ("Portfolio digest", "0 8 * * 1-5", "telegram"),
    ]):
        data["jobs"].append({
            "id": f"extra{i:08x}", "name": name, "prompt": f"Run {name}.",
            "skills": [], "schedule": {"kind": "cron", "expr": expr, "display": expr},
            "repeat": {"times": None, "completed": 0}, "enabled": True,
            "state": "scheduled", "deliver": deliver,
            "created_at": "2026-07-01T00:00:00+00:00"})
    jobs_file.write_text(json.dumps(data, indent=2))


def start_server(home: Path):
    state = gui_server.WizardState(home)
    bootstrap = "shots-token"
    handler = type("H", (gui_server.GuiHandler,), {
        "state": state, "bootstrap_token": bootstrap, "session_token": None,
        "allowed_hosts": set(), "shutdown_flag": threading.Event(),
        "last_activity": [time.time()]})
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    handler.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, state, f"http://127.0.0.1:{port}/#t={bootstrap}"


def wait_text(page, text, timeout=90000):
    page.wait_for_selector(f"text={text}", timeout=timeout)
    page.wait_for_timeout(350)  # settle animations/layout


def main() -> int:
    from playwright.sync_api import sync_playwright

    IMG.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="talaria-shots-"))
    os.environ["HOME"] = str(tmp)
    src = tmp / "source" / ".hermes"
    inst = build_fake_install(src, FakeInstallSpec(with_profile="coder"))
    enrich(inst)
    target = tmp / "newmac" / ".hermes"

    candidates = sorted(Path("/opt/pw-browsers").glob("chromium*/chrome-linux/chrome"))
    exe = str(candidates[-1]) if candidates else None

    shots = []

    def run_flow(theme: str):
        suffix = "" if theme == "light" else "-dark"
        with sync_playwright() as pw:
            browser = pw.chromium.launch(executable_path=exe,
                                         args=["--no-sandbox"] if exe else [])
            page = browser.new_page(viewport={"width": 1180, "height": 900},
                                    device_scale_factor=2, color_scheme=theme)

            # ---- source side (clean any bundle a prior flow left in HOME so the
            # greet always shows the pack flow, not the both-found branch)
            for stray in Path(os.environ["HOME"]).glob("*.hermespack*"):
                stray.unlink()
            os.chdir(ROOT)
            httpd, state, url = start_server(src)
            page.goto(url)
            wait_text(page, "Pack up this Hermes")
            # If both a hermes install and a bundle are detected, click into pack first.
            both = page.locator("button:has-text('Pack up this Hermes')")
            if both.count() > 0:
                both.first.click()
                wait_text(page, "read what's here")
            _shot(page, f"s0-detect{suffix}", shots)
            page.click("button:has-text(\"read what's here\")")
            wait_text(page, "Everything portable, pre-selected")
            _shot(page, f"s2-review{suffix}", shots)
            page.click("button:has-text(\"Looks right\")")
            wait_text(page, "How should your keys move?")
            _shot(page, f"s3-keys{suffix}", shots)
            page.click("button:has-text(\"Pack it up\")")
            wait_text(page, "Boarding pass")
            _shot(page, f"s4-boarding-pass{suffix}", shots)
            httpd.shutdown()

            # ---- target side (bundle now sits in tmp/HOME)
            os.chdir(tmp)
            httpd2, state2, url2 = start_server(target)
            page.goto(url2)
            wait_text(page, "Move this Hermes in")
            _shot(page, f"t1-open{suffix}", shots)
            page.click("button:has-text(\"Check this machine\")")
            wait_text(page, "This machine is ready")
            _shot(page, f"t2-preflight{suffix}", shots)
            page.click("button:has-text(\"Move everything in\")")
            wait_text(page, "Moved in")
            _shot(page, f"t4-finish{suffix}", shots)
            httpd2.shutdown()
            browser.close()

    run_flow("light")
    # reset target for a clean dark run
    import shutil as _sh
    _sh.rmtree(target.parent, ignore_errors=True)
    run_flow("dark")

    print(f"✓ captured {len(shots)} screenshots into {IMG}")
    for s in shots:
        print(f"   {s}")
    return 0


def _shot(page, name, shots):
    path = IMG / f"{name}.png"
    page.screenshot(path=str(path))
    shots.append(path.name)


if __name__ == "__main__":
    sys.exit(main())
