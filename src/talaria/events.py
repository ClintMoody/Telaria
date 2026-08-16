"""Progress events shared by the CLI (`--progress ndjson`) and the GUI job engine (D28).

One event stream, two frontends: the CLI prints these records as ndjson lines; the GUI job
engine appends them to an in-memory log the browser polls with `GET /api/events?after=seq`.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

KINDS = ("phase", "item", "progress", "warn", "error", "done")


@dataclass
class Event:
    seq: int
    ts: float
    kind: str                      # phase|item|progress|warn|error|done
    phase: str                     # scan|snapshot|pack|preflight|stage|backup|apply|verify|...
    detail: str = ""
    bytes_done: Optional[int] = None
    bytes_total: Optional[int] = None

    def to_json(self) -> dict:
        record = {"seq": self.seq, "ts": self.ts, "kind": self.kind, "phase": self.phase,
                  "detail": self.detail}
        if self.bytes_total is not None:
            record["bytes_done"] = self.bytes_done
            record["bytes_total"] = self.bytes_total
        return record


class EventLog:
    """Thread-safe append-only event log with monotonic sequence numbers."""

    def __init__(self, sink: Optional[Callable[[Event], None]] = None):
        self._events: List[Event] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._sink = sink

    def emit(self, kind: str, phase: str, detail: str = "",
             bytes_done: Optional[int] = None, bytes_total: Optional[int] = None) -> Event:
        with self._lock:
            self._seq += 1
            ev = Event(self._seq, time.time(), kind, phase, detail, bytes_done, bytes_total)
            self._events.append(ev)
        if self._sink is not None:
            self._sink(ev)
        return ev

    def since(self, after: int, limit: int = 500) -> List[Event]:
        with self._lock:
            return [e for e in self._events if e.seq > after][:limit]

    @property
    def last_seq(self) -> int:
        with self._lock:
            return self._seq


def ndjson_sink(stream=None) -> Callable[[Event], None]:
    """A sink that prints each event as one ndjson line (CLI --progress ndjson)."""
    out = stream or sys.stdout

    def sink(ev: Event) -> None:
        out.write(json.dumps(ev.to_json(), separators=(",", ":")) + "\n")
        out.flush()

    return sink


def human_sink(stream=None, verbose: bool = False) -> Callable[[Event], None]:
    """A sink that narrates progress for humans (default CLI output)."""
    out = stream or sys.stderr

    def sink(ev: Event) -> None:
        if ev.kind == "phase":
            out.write(f"==> {ev.detail or ev.phase}\n")
        elif ev.kind == "warn":
            out.write(f"  ! {ev.detail}\n")
        elif ev.kind == "error":
            out.write(f"  ✗ {ev.detail}\n")
        elif ev.kind == "done":
            out.write(f"  ✓ {ev.detail or ev.phase}\n")
        elif ev.kind == "item" and verbose:
            out.write(f"    {ev.detail}\n")
        out.flush()

    return sink
