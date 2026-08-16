#!/usr/bin/env python3
"""Render the Talaria hero banner (SVG → PNG) with the bundled Chromium.

Produces docs/img/banner.png (1280×320 @2x). Pure local render, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "banner.png"

FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="320" viewBox="0 0 1280 320">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0"   stop-color="#07070d"/>
      <stop offset="0.6" stop-color="#0b0b14"/>
      <stop offset="1"   stop-color="#0f0f18"/>
    </linearGradient>
    <linearGradient id="wing" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffe14d"/>
      <stop offset="1" stop-color="#e6a700"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.4" r="0.6">
      <stop offset="0" stop-color="#ffd700" stop-opacity="0.24"/>
      <stop offset="1" stop-color="#ffd700" stop-opacity="0"/>
    </radialGradient>
    <filter id="soft"><feGaussianBlur stdDeviation="0.5"/></filter>
  </defs>

  <rect width="1280" height="320" fill="url(#bg)"/>
  <rect width="1280" height="320" fill="url(#glow)"/>

  <!-- dotted flight path: old machine -> new machine -->
  <path d="M 250 232 C 470 232, 520 150, 760 150" stroke="#ffd700" stroke-width="2.25"
        stroke-dasharray="1.5 11" stroke-linecap="round" fill="none" opacity="0.65"/>
  <circle cx="250" cy="232" r="5.5" fill="#3a3520"/>
  <circle cx="760" cy="150" r="5.5" fill="#ffd700"/>

  <!-- winged sandal glyph -->
  <g transform="translate(120,120)" filter="url(#soft)">
    <path d="M8 74 q40 -14 92 -8 q-6 20 -34 24 q-30 4 -58 -16 z" fill="url(#wing)"/>
    <path d="M18 58 q34 -12 78 -7 q-5 16 -28 20 q-26 4 -50 -13 z" fill="url(#wing)" opacity="0.72"/>
    <path d="M28 44 q28 -9 62 -5 q-4 12 -22 16 q-22 3 -40 -11 z" fill="url(#wing)" opacity="0.46"/>
    <path d="M30 78 l70 0 l-8 16 l-54 0 z" fill="#efe9d8"/>
    <path d="M36 94 l50 0 l-4 8 l-42 0 z" fill="#9a968e"/>
  </g>

  <text x="300" y="150" font-family="__FONT__"
        font-size="86" font-weight="700" fill="#f2efe6" letter-spacing="-1.5">Talaria</text>
  <text x="304" y="196" font-family="__FONT__"
        font-size="26" font-weight="500" fill="#ffd700">moves your Hermes agent to a new computer</text>
  <text x="304" y="238" font-family="__FONT__"
        font-size="17" font-weight="400" fill="#9a968e">one file · every platform · verified · undoable</text>

  <!-- machine glyphs -->
  <g opacity="0.95">
    <rect x="212" y="210" width="70" height="46" rx="5" fill="none" stroke="#3f3b2a" stroke-width="2.25"/>
    <rect x="236" y="256" width="22" height="7" rx="2" fill="#3f3b2a"/>
    <rect x="726" y="128" width="70" height="46" rx="5" fill="none" stroke="#ffd700" stroke-width="2.25"/>
    <rect x="750" y="174" width="22" height="7" rx="2" fill="#e6a700"/>
    <text x="761" y="157" font-family="__FONT__" font-size="25" fill="#ffd700"
          text-anchor="middle">&#10524;</text>
  </g>
</svg>
""".replace("__FONT__", FONT)


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = f"<!DOCTYPE html><html><body style='margin:0'>{SVG}</body></html>"
    candidates = sorted(Path("/opt/pw-browsers").glob("chromium*/chrome-linux/chrome"))
    exe = str(candidates[-1]) if candidates else None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe,
                                     args=["--no-sandbox"] if exe else [])
        page = browser.new_page(viewport={"width": 1280, "height": 320},
                                device_scale_factor=2)
        page.set_content(html)
        page.locator("svg").screenshot(path=str(OUT))
        browser.close()
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
