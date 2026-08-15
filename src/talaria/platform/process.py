"""Process liveness, platform-correct (R-XPLAT-02).

``os.kill(pid, 0)`` is banned on win32 (it terminates the process on some Python builds and
does not answer liveness); a CI test asserts no win32 path reaches it. Windows uses ctypes
OpenProcess/GetExitCodeProcess with a `tasklist` fallback.
"""

from __future__ import annotations

import subprocess
import sys

STILL_ACTIVE = 259
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def pid_alive(pid: int) -> bool:
    """Best-effort liveness for a pid; False for invalid pids."""
    if pid <= 0:
        return False
    if sys.platform == "win32":  # pragma: no cover - exercised on Windows runners
        return _pid_alive_windows(pid)
    return _pid_alive_posix(pid)


def _pid_alive_posix(pid: int) -> bool:
    import errno
    import os

    try:
        os.kill(pid, 0)
        return True
    except OSError as exc:
        if exc.errno == errno.EPERM:  # exists, owned by someone else
            return True
        return False


def _pid_alive_windows(pid: int) -> bool:  # pragma: no cover - Windows only
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            try:
                code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        # OpenProcess failure may mean access denied (alive) or gone; fall through.
    except Exception:
        pass
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH", "/FO", "CSV"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        return f'"{pid}"' in (out.stdout or "")
    except Exception:
        return False
