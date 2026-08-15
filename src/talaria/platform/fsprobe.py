"""Filesystem behavior probes and metadata (R-XPLAT-03/08, R-PACK-07).

Behavior is probed, never assumed: case sensitivity and unicode normalization are tested
with real probe files in a scratch directory (the txn dir on apply). Filesystem *type*
detection is per-OS and 'unknown' is a legal answer.
"""

from __future__ import annotations

import os
import shutil
import sys
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

FAT_FILE_CAP = 4 * 1024 * 1024 * 1024 - 1  # 4 GiB minus one byte
FAT_TYPES = {"vfat", "fat", "fat32", "exfat", "msdos"}
WAL_HOSTILE_TYPES = {"nfs", "nfs4", "cifs", "smbfs", "smb2", "fuse", "sshfs", "9p", "virtiofs"}


@dataclass
class FsBehavior:
    case_insensitive: bool
    normalizes_unicode: bool


def probe_behavior(scratch_dir: Path) -> FsBehavior:
    """Create probe files in ``scratch_dir`` to learn real case/normalization behavior."""
    scratch = Path(scratch_dir)
    scratch.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    lower = scratch / f".probe-{tag}-case"
    upper = scratch / f".PROBE-{tag}-CASE"
    case_insensitive = False
    try:
        lower.write_text("a", encoding="utf-8")
        case_insensitive = upper.exists()
    finally:
        try:
            lower.unlink()
        except OSError:
            pass
    accent_nfc = unicodedata.normalize("NFC", "cafe\u0301")   # composed e-acute
    accent_nfd = unicodedata.normalize("NFD", "caf\u00e9")    # e + combining accent
    nfc = scratch / (".probe-" + tag + "-" + accent_nfc)
    nfd = scratch / (".probe-" + tag + "-" + accent_nfd)
    normalizes = False
    try:
        nfc.write_text("a", encoding="utf-8")
        normalizes = nfd.exists()
    finally:
        try:
            nfc.unlink()
        except OSError:
            pass
    return FsBehavior(case_insensitive=case_insensitive, normalizes_unicode=normalizes)


def fs_type_of(path: Path) -> str:
    """Best-effort filesystem type name for the volume holding ``path``; 'unknown' is legal."""
    path = Path(path).resolve()
    if sys.platform.startswith("linux"):
        return _fs_type_linux(path)
    if sys.platform == "darwin":  # pragma: no cover - macOS runner
        return _fs_type_macos(path)
    if sys.platform == "win32":   # pragma: no cover - Windows runner
        return _fs_type_windows(path)
    return "unknown"


def _fs_type_linux(path: Path) -> str:
    best = ("", "unknown")
    try:
        with open("/proc/self/mounts", "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mount, fstype = parts[1], parts[2]
                mount_unescaped = mount.replace("\\040", " ").replace("\\011", "\t")
                try:
                    if str(path).startswith(mount_unescaped.rstrip("/") or "/") and \
                            len(mount_unescaped) > len(best[0]):
                        best = (mount_unescaped, fstype)
                except Exception:
                    continue
    except OSError:
        return "unknown"
    return best[1]


def _fs_type_macos(path: Path) -> str:  # pragma: no cover
    try:
        import subprocess

        out = subprocess.run(["/usr/sbin/diskutil", "info", str(path)],
                             capture_output=True, text=True, timeout=10, check=False)
        for line in out.stdout.splitlines():
            if "Type (Bundle)" in line or "File System Personality" in line:
                return line.split(":", 1)[1].strip().lower()
    except Exception:
        pass
    return "unknown"


def _fs_type_windows(path: Path) -> str:  # pragma: no cover
    try:
        import ctypes

        drive = os.path.splitdrive(str(path))[0] + "\\"
        buf = ctypes.create_unicode_buffer(64)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(drive), None, 0, None, None, None, buf, 64)
        if ok:
            return buf.value.lower()
    except Exception:
        pass
    return "unknown"


def is_fat_like(fs_type: str) -> bool:
    return fs_type.lower() in FAT_TYPES


def is_wal_hostile(fs_type: str) -> bool:
    low = fs_type.lower()
    return any(low.startswith(t) for t in WAL_HOSTILE_TYPES)


def free_bytes(path: Path) -> int:
    target = Path(path)
    probe = target
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return shutil.disk_usage(probe).free


def volume_key(path: Path) -> object:
    """A key grouping paths by destination volume (st_dev on POSIX, drive on Windows)."""
    if sys.platform == "win32":  # pragma: no cover
        return os.path.splitdrive(str(Path(path).resolve()))[0].lower()
    probe = Path(path)
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    return os.stat(probe).st_dev


def group_by_volume(paths: Iterable[Path]) -> Dict[object, List[Path]]:
    groups: Dict[object, List[Path]] = {}
    for p in paths:
        groups.setdefault(volume_key(p), []).append(p)
    return groups
