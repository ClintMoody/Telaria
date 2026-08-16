#!/usr/bin/env python3
"""Render the Talaria hero banner (SVG → PNG) with the bundled Chromium.

Produces docs/img/banner.png (1280×320 @2x). Pure local render, no network.
Palette: the Hermes desktop "nous"/Psyche identity — deep royal blue with warm
cream. The wordmark is set in Collapse (the Nous brand face) bold, uppercase and
wide-tracked, exactly as the Hermes hero uses it. Fonts are embedded as base64 so
the render is self-contained and reproducible.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "img" / "banner.png"
FONTS = ROOT / "src" / "talaria" / "gui" / "assets" / "fonts"


def _face(family: str, weight: int, filename: str) -> str:
    data = base64.b64encode((FONTS / filename).read_bytes()).decode()
    return (f"@font-face{{font-family:'{family}';font-weight:{weight};font-style:normal;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2');}}")


FONT_CSS = "".join([
    _face("Collapse", 700, "Collapse-Bold.woff2"),
    _face("Inter", 400, "Inter-400.woff2"),
    _face("Inter", 500, "Inter-500.woff2"),
    _face("Inter", 700, "Inter-700.woff2"),
])

DISPLAY = "Collapse, 'Inter', sans-serif"
BODY = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"

SVG = """
<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="320" viewBox="0 0 1280 320">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0"   stop-color="#0d2f86"/>
      <stop offset="0.55" stop-color="#0b2a78"/>
      <stop offset="1"   stop-color="#123a92"/>
    </linearGradient>
    <linearGradient id="wing" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#ffe6cb"/>
      <stop offset="1" stop-color="#e6b877"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.4" r="0.6">
      <stop offset="0" stop-color="#6d9bff" stop-opacity="0.30"/>
      <stop offset="1" stop-color="#6d9bff" stop-opacity="0"/>
    </radialGradient>
    <filter id="soft"><feGaussianBlur stdDeviation="0.5"/></filter>
  </defs>

  <rect width="1280" height="320" fill="url(#bg)"/>
  <rect width="1280" height="320" fill="url(#glow)"/>

  <!-- dotted flight path: old machine -> new machine -->
  <path d="M 250 236 C 470 236, 520 156, 760 156" stroke="#6d9bff" stroke-width="2.25"
        stroke-dasharray="1.5 11" stroke-linecap="round" fill="none" opacity="0.8"/>
  <circle cx="250" cy="236" r="5.5" fill="#2a4fa0"/>
  <circle cx="760" cy="156" r="5.5" fill="#ffe6cb"/>

  <!-- winged sandal glyph (talaria = Hermes' golden winged sandals) -->
  <g transform="translate(120,116)" filter="url(#soft)">
    <path d="M8 74 q40 -14 92 -8 q-6 20 -34 24 q-30 4 -58 -16 z" fill="url(#wing)"/>
    <path d="M18 58 q34 -12 78 -7 q-5 16 -28 20 q-26 4 -50 -13 z" fill="url(#wing)" opacity="0.72"/>
    <path d="M28 44 q28 -9 62 -5 q-4 12 -22 16 q-22 3 -40 -11 z" fill="url(#wing)" opacity="0.46"/>
    <path d="M30 78 l70 0 l-8 16 l-54 0 z" fill="#eef3ff"/>
    <path d="M36 94 l50 0 l-4 8 l-42 0 z" fill="#b5c7f3"/>
  </g>

  <text x="300" y="150" font-family="__DISPLAY__" font-size="82" font-weight="700"
        fill="#ffe6cb" letter-spacing="7" textLength="360" lengthAdjust="spacing">TALARIA</text>
  <text x="302" y="196" font-family="__BODY__"
        font-size="25" font-weight="500" fill="#8bb0ff">moves your Hermes agent to a new computer</text>
  <text x="302" y="238" font-family="__BODY__"
        font-size="16" font-weight="400" fill="#b5c7f3">one file · every platform · verified · undoable</text>

  <!-- machine glyphs -->
  <g opacity="0.95">
    <rect x="212" y="214" width="70" height="46" rx="5" fill="none" stroke="#2a4fa0" stroke-width="2.25"/>
    <rect x="236" y="260" width="22" height="7" rx="2" fill="#2a4fa0"/>
    <rect x="726" y="134" width="70" height="46" rx="5" fill="none" stroke="#6d9bff" stroke-width="2.25"/>
    <rect x="750" y="180" width="22" height="7" rx="2" fill="#8bb0ff"/>
    <text x="761" y="163" font-family="__BODY__" font-size="25" fill="#ffe6cb"
          text-anchor="middle">&#10524;</text>
  </g>
</svg>
""".replace("__DISPLAY__", DISPLAY).replace("__BODY__", BODY)


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.parent.mkdir(parents=True, exist_ok=True)
    html = (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
            f"<style>{FONT_CSS}</style></head>"
            f"<body style='margin:0'>{SVG}</body></html>")
    candidates = sorted(Path("/opt/pw-browsers").glob("chromium*/chrome-linux/chrome"))
    exe = str(candidates[-1]) if candidates else None
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=exe,
                                     args=["--no-sandbox"] if exe else [])
        page = browser.new_page(viewport={"width": 1280, "height": 320},
                                device_scale_factor=2)
        page.set_content(html)
        page.wait_for_timeout(300)  # let embedded @font-face faces load before shot
        page.locator("svg").screenshot(path=str(OUT))
        browser.close()
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
