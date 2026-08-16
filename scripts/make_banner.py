#!/usr/bin/env python3
"""Render the Talaria hero banner (SVG → PNG) with the bundled Chromium.

Produces docs/img/banner.png (1280×320 @2x). Pure local render, no network.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "banner.png"

SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="320" viewBox="0 0 1280 320">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0"   stop-color="#12101d"/>
      <stop offset="0.55" stop-color="#1a1330"/>
      <stop offset="1"   stop-color="#0d1b2e"/>
    </linearGradient>
    <linearGradient id="wing" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#b79bff"/>
      <stop offset="1" stop-color="#6a3de8"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#6a3de8" stop-opacity="0.55"/>
      <stop offset="1" stop-color="#6a3de8" stop-opacity="0"/>
    </radialGradient>
    <filter id="soft"><feGaussianBlur stdDeviation="0.6"/></filter>
  </defs>

  <rect width="1280" height="320" fill="url(#bg)"/>
  <circle cx="205" cy="160" r="190" fill="url(#glow)"/>

  <!-- dotted flight path old machine -> new machine -->
  <path d="M 250 232 C 470 232, 520 150, 760 150" stroke="#6a3de8" stroke-width="2.5"
        stroke-dasharray="2 12" stroke-linecap="round" fill="none" opacity="0.7"/>
  <circle cx="250" cy="232" r="6" fill="#3a3358"/>
  <circle cx="760" cy="150" r="6" fill="#b79bff"/>

  <!-- winged sandal glyph -->
  <g transform="translate(120,120)" filter="url(#soft)">
    <path d="M8 74 q40 -14 92 -8 q-6 20 -34 24 q-30 4 -58 -16 z" fill="url(#wing)"/>
    <path d="M18 58 q34 -12 78 -7 q-5 16 -28 20 q-26 4 -50 -13 z" fill="url(#wing)" opacity="0.75"/>
    <path d="M28 44 q28 -9 62 -5 q-4 12 -22 16 q-22 3 -40 -11 z" fill="url(#wing)" opacity="0.5"/>
    <path d="M30 78 l70 0 l-8 16 l-54 0 z" fill="#e8ecf1"/>
    <path d="M36 94 l50 0 l-4 8 l-42 0 z" fill="#98a1ad"/>
  </g>

  <text x="300" y="150" font-family="Segoe UI, Roboto, system-ui, sans-serif"
        font-size="88" font-weight="800" fill="#f2f0fb" letter-spacing="-1">Talaria</text>
  <text x="304" y="196" font-family="Segoe UI, Roboto, system-ui, sans-serif"
        font-size="27" font-weight="400" fill="#b79bff">moves your Hermes agent to a new computer</text>
  <text x="304" y="240" font-family="Segoe UI, Roboto, system-ui, sans-serif"
        font-size="18" font-weight="400" fill="#8d96a0">one file · every platform · verified · undoable</text>

  <!-- machine glyphs -->
  <g opacity="0.9">
    <rect x="212" y="210" width="70" height="46" rx="5" fill="none" stroke="#4b4468" stroke-width="2.5"/>
    <rect x="236" y="256" width="22" height="7" rx="2" fill="#4b4468"/>
    <rect x="726" y="128" width="70" height="46" rx="5" fill="none" stroke="#7d63d6" stroke-width="2.5"/>
    <rect x="750" y="174" width="22" height="7" rx="2" fill="#7d63d6"/>
    <text x="761" y="157" font-family="system-ui" font-size="26" fill="#b79bff"
          text-anchor="middle">⤞</text>
  </g>
</svg>
"""


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
