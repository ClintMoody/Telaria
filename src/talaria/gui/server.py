"""Hardened localhost GUI server (ARCH §12; R-GUI-01/02; D15).

Security package: literal 127.0.0.1 bind on a random port; one-time URL bootstrap token
exchanged for a ≥128-bit session token sent as X-Talaria-Token (constant-time compare);
strict Host and Origin validation; no-referrer/frame-deny/nosniff/CSP headers; secrets
only in POST bodies; token never logged; single active session; shutdown endpoint and
idle timeout. Assets load via importlib.resources (zip-safe from the .pyz).
"""

from __future__ import annotations

import hmac
import json
import secrets as secrets_mod
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, Optional

from talaria import __version__
from talaria.errors import EXIT_OK, Refusal, TalariaError
from talaria.events import EventLog
from talaria.gui.jobs import JobEngine

try:
    from importlib.resources import files as _res_files
except ImportError:  # pragma: no cover
    _res_files = None

IDLE_TIMEOUT_SECONDS = 30 * 60


class WizardState:
    """Server-side wizard model shared across requests."""

    def __init__(self, home: Path):
        self.home = Path(home)
        self.events = EventLog()
        self.jobs = JobEngine(self.events)
        self.scan_result = None
        self.pack_result = None
        self.apply_outcome = None
        self.preflight = None
        self.bundle_checklist: list = []
        self.bundle_vault_present = False
        self.bundle_path: Optional[Path] = None
        self.vault_passphrase: Optional[str] = None
        self.selection_excludes: set = set()
        self.lock = threading.Lock()

    # ---- state snapshot for GET /api/state
    def snapshot(self) -> dict:
        from talaria.engine.bundle import BundleKind, detect_kind
        from talaria.engine.resolve import looks_like_hermes_home

        hermes_here = self.home.is_dir() and looks_like_hermes_home(self.home)
        bundles = []
        for candidate_dir in {Path.cwd(), Path.home(), Path.home() / "Desktop",
                              Path.home() / "Downloads"}:
            if candidate_dir.is_dir():
                for b in sorted(candidate_dir.glob("*.hermespack")):
                    if detect_kind(b)[0] == BundleKind.TALARIA:
                        bundles.append(str(b))
        state = {
            "tool_version": __version__,
            "home": str(self.home),
            "hermes_here": hermes_here,
            "bundles_found": bundles[:5],
            "busy": self.jobs.busy,
            "last_seq": self.events.last_seq,
        }
        if self.scan_result is not None:
            r = self.scan_result
            families: Dict[str, dict] = {}
            for art in r.artifacts:
                f = families.setdefault(art.family, {"count": 0, "bytes": 0,
                                                     "travel": 0, "artifacts": []})
                f["count"] += 1
                f["bytes"] += art.total_size
                if art.travels:
                    f["travel"] += 1
                if len(f["artifacts"]) < 200:
                    f["artifacts"].append({
                        "id": art.id, "kind": art.kind, "selected": art.selected,
                        "secrecy": art.secrecy, "default": art.default,
                        "bytes": art.total_size,
                        "reason": art.reasons[0] if art.reasons else ""})
            state["scan"] = {
                "identity": r.identity.to_json(),
                "families": families,
                "warnings": r.warnings,
                "capture_mode": r.capture_mode,
                "files": r.scanned_files,
                "bytes": r.scanned_bytes,
                "excluded": r.excluded_counts,
            }
        if self.pack_result is not None:
            state["pack"] = {
                "bundle": str(self.pack_result.bundle_path),
                "bytes": self.pack_result.bytes_written,
                "checklist_items": self.pack_result.manifest.get(
                    "checklist", {}).get("items", []),
            }
        if self.preflight is not None:
            state["preflight"] = self.preflight.to_json()
            state["bundle"] = str(self.bundle_path)
            state["checklist"] = self.bundle_checklist
            state["vault_present"] = bool(self.bundle_vault_present)
        if self.apply_outcome is not None:
            state["apply"] = self.apply_outcome.to_json()
        return state


class GuiHandler(BaseHTTPRequestHandler):
    server_version = "talaria"
    sys_version = ""

    # injected by serve():
    state: WizardState
    bootstrap_token: str
    session_token: Optional[str]
    allowed_hosts: set
    shutdown_flag: threading.Event
    last_activity: list

    # ------------------------------------------------------------------ plumbing
    def log_message(self, fmt: str, *args) -> None:  # method+path only, no tokens
        pass

    def _security_check(self) -> bool:
        host = self.headers.get("Host", "")
        if host not in self.allowed_hosts:
            self._deny(403, "bad host")
            return False
        origin = self.headers.get("Origin")
        if origin is not None:
            allowed_origins = {f"http://{h}" for h in self.allowed_hosts}
            if origin not in allowed_origins:
                self._deny(403, "bad origin")
                return False
        return True

    def _authed(self) -> bool:
        token = self.headers.get("X-Talaria-Token", "")
        if self.session_token is None or not token:
            return False
        return hmac.compare_digest(token, self.session_token)

    def _deny(self, code: int, reason: str) -> None:
        body = json.dumps({"error": reason}).encode()
        self.send_response(code)
        self._common_headers("application/json", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _common_headers(self, ctype: str, length: int) -> None:
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:")
        self.send_header("Cache-Control", "no-store")

    def _json(self, payload: dict, code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(code)
        self._common_headers("application/json", len(body))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self, cap: int = 4 * 1024 * 1024) -> Optional[dict]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return None
        if length <= 0 or length > cap:
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (ValueError, OSError):
            return None

    # ------------------------------------------------------------------ routes
    def do_GET(self) -> None:  # noqa: N802
        if not self._security_check():
            return
        self.last_activity[0] = time.time()
        path = self.path.split("?", 1)[0]
        if path == "/":
            return self._serve_asset("index.html", "text/html; charset=utf-8")
        if path.startswith("/assets/"):
            name = path[len("/assets/"):]
            ctype = ("text/css" if name.endswith(".css")
                     else "application/javascript" if name.endswith(".js")
                     else "image/svg+xml" if name.endswith(".svg")
                     else "application/octet-stream")
            return self._serve_asset(name, ctype)
        if not self._authed():
            return self._deny(401, "session token required")
        if path == "/api/state":
            return self._json(self.state.snapshot())
        if path == "/api/events":
            after = 0
            if "after=" in self.path:
                try:
                    after = int(self.path.split("after=", 1)[1].split("&", 1)[0])
                except ValueError:
                    after = 0
            events = self.state.events.since(after, limit=500)
            return self._json({"events": [e.to_json() for e in events],
                               "last_seq": self.state.events.last_seq,
                               "busy": self.state.jobs.busy})
        if path == "/api/report/latest":
            return self._latest_report()
        return self._deny(404, "no such endpoint")

    def do_POST(self) -> None:  # noqa: N802
        if not self._security_check():
            return
        self.last_activity[0] = time.time()
        path = self.path.split("?", 1)[0]
        if path == "/api/session":
            body = self._read_body() or {}
            offered = str(body.get("bootstrap", ""))
            if not self.bootstrap_token or \
                    not hmac.compare_digest(offered, self.bootstrap_token):
                return self._deny(403, "bad or used bootstrap token")
            type(self).bootstrap_token = ""  # single use
            type(self).session_token = secrets_mod.token_urlsafe(32)
            return self._json({"token": self.session_token})
        if not self._authed():
            return self._deny(401, "session token required")
        if path == "/api/jobs":
            return self._start_job(self._read_body() or {})
        if path.startswith("/api/jobs/") and path.endswith("/cancel"):
            job_id = path[len("/api/jobs/"):-len("/cancel")]
            ok = self.state.jobs.cancel(job_id)
            return self._json({"cancelled": ok})
        if path == "/api/selection":
            body = self._read_body() or {}
            excludes = set(body.get("exclude", []))
            with self.state.lock:
                self.state.selection_excludes = excludes
                if self.state.scan_result is not None:
                    from talaria.model.selection import Selection, apply_selection

                    apply_selection(self.state.scan_result.artifacts,
                                    Selection(exclude=excludes))
            return self._json({"ok": True, "excluded": sorted(excludes)})
        if path == "/api/vault-passphrase":
            body = self._read_body() or {}
            phrase = body.get("passphrase")
            if phrase == "":   # typed-empty is refused; null means checklist mode
                return self._deny(400, "empty passphrase refused")
            with self.state.lock:
                self.state.vault_passphrase = phrase
            return self._json({"ok": True, "vault": phrase is not None})
        if path == "/api/secrets":
            return self._paste_secret(self._read_body() or {})
        if path == "/api/shutdown":
            self.shutdown_flag.set()
            return self._json({"bye": True})
        return self._deny(404, "no such endpoint")

    # ------------------------------------------------------------------ helpers
    def _serve_asset(self, name: str, ctype: str) -> None:
        if "/" in name or "\\" in name or name.startswith("."):
            return self._deny(404, "no")
        blob: Optional[bytes] = None
        if _res_files is not None:
            try:
                blob = (_res_files("talaria.gui") / "assets" / name).read_bytes()
            except (FileNotFoundError, OSError, TypeError):
                blob = None
        if blob is None:
            return self._deny(404, "asset missing")
        self.send_response(200)
        self._common_headers(ctype, len(blob))
        self.end_headers()
        self.wfile.write(blob)

    def _start_job(self, body: dict) -> None:
        kind = str(body.get("kind", ""))
        state = self.state
        args = body.get("args") or {}

        def scan_job(cancel_flag):
            from talaria.engine.scan import scan

            state.events.emit("phase", "scan", "Reading what's here (read-only)")
            result = scan(state.home,
                          on_item=lambda rel: state.events.emit("item", "scan", rel))
            with state.lock:
                state.scan_result = result
            state.events.emit("done", "scan",
                              f"{result.scanned_files:,} files inventoried")
            return True

        def pack_job(cancel_flag):
            import socket

            from talaria.engine.pack import PackOptions, pack
            from talaria.model.selection import Selection
            from talaria.cli import _write_checklist_html
            from talaria.engine import checklist as cl

            if state.scan_result is None:
                raise TalariaError("TAL-801", "scan first")
            out = Path(args.get("output") or
                       (Path.home() / f"hermes-{socket.gethostname()}-"
                        f"{time.strftime('%Y-%m-%d')}.hermespack"))
            options = PackOptions(
                selection=Selection(exclude=set(state.selection_excludes)),
                vault_passphrase=state.vault_passphrase,
                lock_everything=bool(args.get("lock_everything")))
            pres = pack(state.scan_result, out, options, state.events)
            cards = cl.secrets_cards(pres.checklist)
            _write_checklist_html(out.with_name(out.name + ".checklist.html"),
                                  cards, pres.manifest)
            with state.lock:
                state.pack_result = pres
            return str(pres.bundle_path)

        def preflight_job(cancel_flag):
            from talaria.engine.bundle import BundleReader
            from talaria.engine.preflight import run_preflight

            bundle = Path(args.get("bundle", ""))
            with BundleReader(bundle) as reader:
                problems = reader.verify_structure()
                if problems:
                    raise Refusal("TAL-303", "bundle failed hardening: " + problems[0])
                report = run_preflight(reader, state.home)
            with state.lock:
                state.preflight = report
                state.bundle_path = bundle
                state.bundle_checklist = (reader.manifest.get("checklist") or
                                          {}).get("items", [])
                state.bundle_vault_present = bool(
                    (reader.manifest.get("vault") or {}).get("present"))
            return report.to_json()

        def apply_job(cancel_flag):
            from talaria.engine.apply import ApplyOptions, apply_bundle

            if state.bundle_path is None:
                raise TalariaError("TAL-801", "preflight first")
            options = ApplyOptions(
                conflict_policy="overwrite",   # wizard = replace-with-safety-copy (D8)
                include_unrecognized=bool(args.get("include_unrecognized")),
                vault_passphrase=state.vault_passphrase,
                consent_executable=bool(args.get("consent")),
                consent_external=bool(args.get("consent")))
            outcome = apply_bundle(state.bundle_path, state.home, options,
                                   state.events)
            with state.lock:
                state.apply_outcome = outcome
            return outcome.status

        def rollback_job(cancel_flag):
            from talaria.cli import cmd_rollback

            class _A:
                txn = None
                home = str(state.home)
                json = True
                dry_run = False
                quiet = True
                verbose = False

            cmd_rollback(_A())
            state.events.emit("done", "rollback", "restored the pre-apply state")
            return True

        def deepscan_job(cancel_flag):
            from talaria.engine.deepscan import generate_skill

            out_dir = Path.home() / "talaria-deepscan"
            skill_dir, nonce = generate_skill(out_dir)
            state.events.emit("done", "deepscan",
                              f"observation skill at {skill_dir} (nonce {nonce})")
            return {"skill_dir": str(skill_dir), "nonce": nonce}

        handlers = {"scan": scan_job, "pack": pack_job, "preflight": preflight_job,
                    "apply": apply_job, "rollback": rollback_job,
                    "deepscan-generate": deepscan_job}
        handler = handlers.get(kind)
        if handler is None:
            return self._deny(400, f"unknown job kind {kind!r}")
        job_id = self.state.jobs.submit(kind, handler)
        if job_id is None:
            return self._deny(409, "a job is already running")
        return self._json({"job_id": job_id})

    def _paste_secret(self, body: dict) -> None:
        """Paste-back: write KEY=value into .env (create-exclusive 0600; R-SEC-03)."""
        import os

        from talaria.engine.rewrite import dotenv_edit

        name = str(body.get("name", "")).strip()
        value = str(body.get("value", ""))
        if not name or not all(c.isalnum() or c == "_" for c in name):
            return self._deny(400, "bad variable name")
        if not value or "\n" in value:
            return self._deny(400, "bad value")
        env_path = self.state.home / ".env"
        if env_path.exists():
            text = env_path.read_text(encoding="utf-8-sig", errors="replace")
            new_text, _replaced = dotenv_edit.set_value(text, name, value)
            env_path.write_text(new_text, encoding="utf-8")
        else:
            fd = os.open(env_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(f"{name}={value}\n")
        try:
            os.chmod(env_path, 0o600)
        except OSError:
            pass
        self.state.events.emit("item", "secrets", f"{name} saved to .env")
        return self._json({"ok": True, "name": name})

    def _latest_report(self) -> None:
        base = self.state.home / "migration" / "talaria"
        if not base.is_dir():
            return self._deny(404, "no reports yet")
        candidates = sorted(base.iterdir(), reverse=True)
        for candidate in candidates:
            html_file = candidate / "report.html"
            if html_file.is_file():
                blob = html_file.read_bytes()
                self.send_response(200)
                self._common_headers("text/html; charset=utf-8", len(blob))
                self.end_headers()
                self.wfile.write(blob)
                return
        return self._deny(404, "no reports yet")


def serve(port: int = 0, open_browser: bool = True,
          home: Optional[Path] = None) -> int:
    from talaria.engine.resolve import resolve_home

    state = WizardState(home or resolve_home())
    bootstrap = secrets_mod.token_urlsafe(16)
    shutdown_flag = threading.Event()
    last_activity = [time.time()]

    handler = type("BoundHandler", (GuiHandler,), {
        "state": state, "bootstrap_token": bootstrap, "session_token": None,
        "allowed_hosts": set(), "shutdown_flag": shutdown_flag,
        "last_activity": last_activity,
    })

    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    real_port = httpd.server_address[1]
    handler.allowed_hosts = {f"127.0.0.1:{real_port}", f"localhost:{real_port}",
                             f"[::1]:{real_port}"}
    url = f"http://127.0.0.1:{real_port}/#t={bootstrap}"
    print(f"\n  ⤞ Talaria wizard: {url}")
    print("    (this exact URL carries your one-time session key — do not share it)")
    print("    over SSH?  ssh -L {p}:127.0.0.1:{p} <host>  then open it locally"
          .format(p=real_port))

    if open_browser:
        try:
            opened = webbrowser.open(url)
            if not opened:
                print("    could not open a browser — copy the URL above "
                      "(Termux: termux-open-url)")
        except Exception:
            print("    could not open a browser — copy the URL above")

    def watchdog() -> None:
        while not shutdown_flag.is_set():
            if time.time() - last_activity[0] > IDLE_TIMEOUT_SECONDS:
                shutdown_flag.set()
                break
            time.sleep(5)

    threading.Thread(target=watchdog, daemon=True).start()

    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    try:
        while not shutdown_flag.is_set():
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    httpd.shutdown()
    print("  wizard closed")
    return EXIT_OK
