"""GUI job engine: one worker, queue depth 1, cancellable, shared event log (D28).

Jobs emit the same Event records the CLI prints as ndjson — one stream, two frontends.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from talaria.events import EventLog


@dataclass
class Job:
    id: str
    kind: str
    thread: threading.Thread
    cancel_flag: threading.Event
    result: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    done: bool = False


class JobEngine:
    def __init__(self, events: EventLog):
        self.events = events
        self._lock = threading.Lock()
        self._current: Optional[Job] = None
        self._jobs: Dict[str, Job] = {}

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._current is not None and not self._current.done

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def submit(self, kind: str, fn: Callable[[threading.Event], Any]) -> Optional[str]:
        """Run ``fn(cancel_flag)`` on the worker; returns job id, or None when busy."""
        with self._lock:
            if self._current is not None and not self._current.done:
                return None
            job_id = uuid.uuid4().hex[:8]
            cancel_flag = threading.Event()

            def runner() -> None:
                job = self._jobs[job_id]
                try:
                    job.result = fn(cancel_flag)
                except BaseException as exc:  # noqa: BLE001 — reported to the UI
                    job.error = str(exc)
                    job.error_code = getattr(exc, "code", None)
                    detail = getattr(exc, "fix", "") or ""
                    self.events.emit("error", kind,
                                     f"{exc}" + (f" — {detail}" if detail else ""))
                    if not isinstance(exc, Exception):
                        traceback.print_exc()
                finally:
                    job.done = True
                    self.events.emit("done", kind, "finished" if job.error is None
                                     else "failed")

            thread = threading.Thread(target=runner, daemon=True, name=f"job-{kind}")
            job = Job(id=job_id, kind=kind, thread=thread, cancel_flag=cancel_flag)
            self._jobs[job_id] = job
            self._current = job
            thread.start()
            return job_id

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if job is None or job.done:
            return False
        job.cancel_flag.set()
        self.events.emit("warn", job.kind, "cancel requested")
        return True
