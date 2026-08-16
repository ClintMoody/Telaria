"""Import-guarded HKCU reads (Windows only): HERMES_HOME and LongPathsEnabled.

GUI-launched apps miss post-login `setx` environment changes; the registry is the durable
source for a user-set HERMES_HOME on Windows (install research §4).
"""

from __future__ import annotations

from typing import Optional


def read_hkcu_env(name: str) -> Optional[str]:
    """HKCU\\Environment\\<name>, or None off-Windows / when absent."""
    try:  # pragma: no cover - Windows only
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            value, _kind = winreg.QueryValueEx(key, name)
            return str(value) if value else None
    except (ImportError, OSError):
        return None


def long_paths_enabled() -> Optional[bool]:
    """HKLM LongPathsEnabled; None when unknown/off-Windows."""
    try:  # pragma: no cover - Windows only
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\FileSystem",
        ) as key:
            value, _kind = winreg.QueryValueEx(key, "LongPathsEnabled")
            return bool(value)
    except (ImportError, OSError):
        return None
