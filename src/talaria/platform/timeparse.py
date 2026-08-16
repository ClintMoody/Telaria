"""Owned tolerant RFC3339 parsing and timezone comparison (R-XPLAT-06).

Python 3.9's ``datetime.fromisoformat`` rejects a trailing ``Z``; Hermes writes both ``Z``
and offset forms. TZ equivalence is compared as (name, utc_offset_minutes, dst) so no
zoneinfo database is ever required at runtime; the Windows→IANA table ships as data.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

try:
    from importlib.resources import files as _res_files
except ImportError:  # pragma: no cover
    _res_files = None

_RFC3339 = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})"
    r"[Tt ]"
    r"(?P<time>\d{2}:\d{2}:\d{2})(?P<frac>\.\d+)?"
    r"(?P<tz>[Zz]|[+-]\d{2}:?\d{2})?$"
)


def parse_rfc3339(text: str) -> Optional[datetime]:
    """Parse an RFC3339-ish timestamp tolerantly; returns aware-or-naive datetime, or None."""
    if not isinstance(text, str):
        return None
    m = _RFC3339.match(text.strip())
    if not m:
        return None
    frac = m.group("frac") or ""
    micro = int(round(float(frac or "0") * 1_000_000)) if frac else 0
    try:
        base = datetime.strptime(m.group("date") + " " + m.group("time"), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    base = base.replace(microsecond=min(micro, 999_999))
    tz = m.group("tz")
    if not tz:
        return base  # naive — caller decides interpretation (upstream treats as local)
    if tz in ("Z", "z"):
        return base.replace(tzinfo=timezone.utc)
    sign = 1 if tz[0] == "+" else -1
    hh = int(tz[1:3])
    mm = int(tz[-2:])
    return base.replace(tzinfo=timezone(sign * timedelta(hours=hh, minutes=mm)))


def format_rfc3339(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tz_signature(name: Optional[str], utc_offset_min: Optional[int],
                 dst: Optional[bool]) -> Tuple[Optional[str], Optional[int], Optional[bool]]:
    return (name, utc_offset_min, dst)


def tz_mismatch(source: Tuple, target: Tuple) -> Optional[str]:
    """Human explanation of a TZ mismatch, or None when equivalent.

    Offset-based first (names may differ legitimately, e.g. alias zones).
    """
    s_name, s_off, s_dst = source
    t_name, t_off, t_dst = target
    if s_off is None or t_off is None:
        return None
    if s_off == t_off:
        return None
    delta = (t_off - s_off) / 60.0
    return (f"the old machine ran at UTC{_fmt(s_off)} ({s_name or 'unknown'}), this one at "
            f"UTC{_fmt(t_off)} ({t_name or 'unknown'}) — scheduled times shift by "
            f"{abs(delta):g} hour(s) unless the timezone is pinned")


def _fmt(minutes: int) -> str:
    sign = "+" if minutes >= 0 else "-"
    minutes = abs(minutes)
    return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}"


_WINDOWS_ZONES = None


def windows_to_iana(windows_name: str) -> Optional[str]:
    """Map a Windows timezone display id to an IANA zone via the shipped CLDR subset."""
    global _WINDOWS_ZONES
    if _WINDOWS_ZONES is None:
        raw = None
        if _res_files is not None:
            try:
                raw = (_res_files("talaria") / "data" / "windows_zones.json").read_text("utf-8")
            except (FileNotFoundError, TypeError, OSError):
                raw = None
        _WINDOWS_ZONES = json.loads(raw) if raw else {}
    return _WINDOWS_ZONES.get(windows_name)
