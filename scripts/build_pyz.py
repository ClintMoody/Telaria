#!/usr/bin/env python3
"""Build the single-file talaria.pyz (R-DIST-01).

Pure stdlib: copies the package into a staging tree (no __pycache__, no tests) and
zips it with a launcher. The result runs with `python talaria.pyz` on any Python —
older interpreters get the friendly floor message from the 2.7-parseable stub.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "talaria"
OUT = ROOT / "dist" / "talaria.pyz"


def main() -> int:
    if not SRC.is_dir():
        print("src/talaria not found", file=sys.stderr)
        return 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "app"
        pkg = stage / "talaria"
        shutil.copytree(SRC, pkg, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", "*.pyo"))
        # Top-level __main__ mirrors the package stub (2.7-parseable floor message).
        shutil.copy2(SRC / "__main__.py", stage / "__main__.py")
        zipapp.create_archive(stage, OUT, interpreter="/usr/bin/env python3",
                              compressed=True)
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    (OUT.parent / "talaria.pyz.sha256").write_text(f"{digest}  talaria.pyz\n")
    size = OUT.stat().st_size / 1024
    print(f"built {OUT} ({size:,.0f} KiB)")
    print(f"sha256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
