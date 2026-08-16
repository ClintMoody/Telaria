"""Digest schemes used by Hermes and by Talaria bundles.

Three schemes coexist upstream and must never be mixed (research:
subsystem-skills-plugins.md §5):

- ``bundled_dir_hash`` — MD5 over ``sorted(rglob("*"))`` of rel-path-string + file bytes,
  mirroring ``tools/skills_sync._dir_hash``. The rel-path string uses the *writing* OS's
  separator, so ``.bundled_manifest`` values are platform-flavored; ``sep`` lets us compute
  either flavor when comparing a manifest written on another OS.
- ``hub_content_hash`` — ``sha256:<16hex>`` over POSIX-sorted rel paths, mirroring
  ``tools/skills_guard.content_hash`` (their #62310: native sort broke Windows).
- ``file_sha256`` — full streaming SHA-256; Talaria's own bundle payload checksum.

MD5 here is inherited fingerprinting for change detection, not a security boundary; bundle
integrity uses SHA-256.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional

_CHUNK = 1024 * 1024


def bundled_dir_hash(directory: Path, sep: Optional[str] = None) -> str:
    """MD5 dir-hash exactly as hermes ``tools/skills_sync._dir_hash`` computes it."""
    use_sep = sep or os.sep
    hasher = hashlib.md5()
    for fpath in sorted(Path(directory).rglob("*")):
        if fpath.is_file():
            rel = str(fpath.relative_to(directory))
            if os.sep != use_sep:
                rel = rel.replace(os.sep, use_sep)
            hasher.update(rel.encode("utf-8"))
            hasher.update(fpath.read_bytes())
    return hasher.hexdigest()


def hub_content_hash(path: Path) -> str:
    """``sha256:<16hex>`` content digest with POSIX-path sorting (hub lock.json scheme).

    Byte-symmetric with hermes ``tools/skills_guard._content_digest`` — rel-posix + NUL +
    bytes per file, entries sorted by rel-posix string; a bare file hashes its bytes alone.
    """
    path = Path(path)
    hasher = hashlib.sha256()
    if path.is_dir():
        entries = sorted(
            (fpath.relative_to(path).as_posix(), fpath)
            for fpath in path.rglob("*")
            if fpath.is_file()
        )
        for rel, fpath in entries:
            hasher.update(rel.encode("utf-8") + b"\x00")
            hasher.update(fpath.read_bytes())
    else:
        hasher.update(path.read_bytes())
    return "sha256:" + hasher.hexdigest()[:16]


def file_sha256(path: Path) -> str:
    """Streaming SHA-256 of one file (bundle payload checksums)."""
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(_CHUNK)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()
