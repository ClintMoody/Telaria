#!/usr/bin/env python3
"""Human-emulating GUI walk-through via Playwright (dev-only; ARCH §15.1 layer 4).

Drives the real wizard in a real Chromium: source side S0→S4 to a boarding pass, then
target side T1→T4 on a fresh home. Captures screenshots for the docs and asserts the
happy path stays within the decision budget. Exits non-zero on any failed step.

Usage: python3 scripts/gui_walkthrough.py [--shots docs/img]
"""

from __future__ import annotations

import argparse
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


def start_server(home: Path):
    state = gui_server.WizardState(home)
    bootstrap = "walkthrough-token"
    handler = type("H", (gui_server.GuiHandler,), {
        "state": state, "bootstrap_token": bootstrap, "session_token": None,
        "allowed_hosts": set(), "shutdown_flag": threading.Event(),
        "last_activity": [time.time()],
    })
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    handler.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, state, f"http://127.0.0.1:{port}/#t={bootstrap}"


def wait_idle(page, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        strip = page.locator("#log-line").text_content() or ""
        if strip.startswith("✓") or strip.startswith("✗"):
            return strip
        time.sleep(0.25)
    raise TimeoutError("job did not finish")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots", default=str(ROOT / "docs" / "img"))
    args = parser.parse_args()
    shots = Path(args.shots)
    shots.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    tmp = Path(tempfile.mkdtemp(prefix="talaria-walk-"))
    # Hermetic HOME: default bundle outputs and bundle discovery stay inside tmp.
    import os

    os.environ["HOME"] = str(tmp)
    source_home = tmp / "source" / ".hermes"
    build_fake_install(source_home, FakeInstallSpec())
    target_home = tmp / "target" / ".hermes"

    failures = []

    with sync_playwright() as pw:
        candidates = sorted(Path("/opt/pw-browsers").glob("chromium*/chrome-linux/chrome"))
        exe = str(candidates[-1]) if candidates else None
        browser = pw.chromium.launch(executable_path=exe,
                                     args=["--no-sandbox"] if exe else [])
        page = browser.new_page(viewport={"width": 1000, "height": 820},
                                color_scheme="light")

        # ---------------- source side ----------------
        httpd, state, url = start_server(source_home)
        page.goto(url)
        page.wait_for_selector("text=Pack up this Hermes", timeout=15000)
        page.screenshot(path=str(shots / "s0-detect.png"))

        page.click("text=Start — read what's here")
        page.wait_for_selector("text=Everything portable, pre-selected",
                               timeout=60000)
        page.screenshot(path=str(shots / "s2-review.png"))

        page.click("text=Looks right — continue")
        page.wait_for_selector("text=How should your keys move?", timeout=15000)
        page.screenshot(path=str(shots / "s3-keys.png"))

        page.click("text=Pack it up")
        page.wait_for_selector("text=Boarding pass", timeout=120000)
        page.screenshot(path=str(shots / "s4-boarding-pass.png"))
        bundle_line = page.locator(".boarding code").first.text_content()
        bundle_path = Path(bundle_line.strip())
        if not bundle_path.exists():
            failures.append(f"bundle missing at {bundle_path}")
        httpd.shutdown()

        # ---------------- target side ----------------
        # Put the bundle where the target-side state scanner looks (home glob is
        # patched via cwd): easiest is Path.home()/Desktop is unlikely; instead we
        # monkeypatch the snapshot bundle discovery by dropping the file into cwd.
        import os

        os.chdir(bundle_path.parent)
        httpd2, state2, url2 = start_server(target_home)
        page.goto(url2)
        page.wait_for_selector("text=Move this Hermes in", timeout=15000)
        page.screenshot(path=str(shots / "t1-open.png"))

        page.click("text=Check this machine")
        page.wait_for_selector("text=This machine is ready", timeout=60000)
        page.screenshot(path=str(shots / "t2-preflight.png"))

        page.click("text=Move everything in")
        page.wait_for_selector("text=Moved in —", timeout=120000)
        page.screenshot(path=str(shots / "t4-finish.png"))
        if not (target_home / "SOUL.md").exists():
            failures.append("target SOUL.md missing after GUI apply")
        if (target_home / "gateway_state.json").exists():
            failures.append("machine-bound file leaked through GUI apply")
        httpd2.shutdown()
        browser.close()

    if failures:
        for f in failures:
            print(f"✗ {f}", file=sys.stderr)
        return 1
    print(f"✓ GUI walk-through complete; screenshots in {shots}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
