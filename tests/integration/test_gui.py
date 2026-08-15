"""GUI server tests over http.client: token exchange, hardening, job engine (R-GUI-02/03)."""

from __future__ import annotations

import http.client
import json
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.gui import server as gui_server  # noqa: E402


@pytest.fixture()
def gui(tmp_path):
    """A live GUI server bound to an ephemeral port, with its bootstrap token."""
    inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
    state = gui_server.WizardState(inst.home)
    bootstrap = "test-bootstrap-token"
    shutdown_flag = threading.Event()
    handler = type("H", (gui_server.GuiHandler,), {
        "state": state, "bootstrap_token": bootstrap, "session_token": None,
        "allowed_hosts": set(), "shutdown_flag": shutdown_flag,
        "last_activity": [time.time()],
    })
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = httpd.server_address[1]
    handler.allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield {"port": port, "bootstrap": bootstrap, "handler": handler, "state": state,
           "home": inst.home}
    httpd.shutdown()


def request(port, method, path, body=None, headers=None, host=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    all_headers = {"Content-Type": "application/json"}
    if host:
        all_headers["Host"] = host
    if headers:
        all_headers.update(headers)
    conn.request(method, path, json.dumps(body) if body is not None else None,
                 all_headers)
    res = conn.getresponse()
    data = res.read()
    conn.close()
    try:
        return res.status, json.loads(data)
    except ValueError:
        return res.status, data


def get_token(gui):
    status, data = request(gui["port"], "POST", "/api/session",
                           {"bootstrap": gui["bootstrap"]})
    assert status == 200
    return data["token"]


class TestSecurity:
    def test_bootstrap_single_use(self, gui):
        token = get_token(gui)
        assert token
        status, _ = request(gui["port"], "POST", "/api/session",
                            {"bootstrap": gui["bootstrap"]})
        assert status == 403  # burned after first use

    def test_wrong_bootstrap_rejected(self, gui):
        status, _ = request(gui["port"], "POST", "/api/session",
                            {"bootstrap": "nope"})
        assert status == 403

    def test_api_requires_token(self, gui):
        status, _ = request(gui["port"], "GET", "/api/state")
        assert status == 401

    def test_bad_token_rejected(self, gui):
        get_token(gui)
        status, _ = request(gui["port"], "GET", "/api/state",
                            headers={"X-Talaria-Token": "forged"})
        assert status == 401

    def test_bad_host_rejected(self, gui):
        """DNS-rebinding shape: correct port, hostile Host header."""
        status, _ = request(gui["port"], "GET", "/", host="evil.example.com")
        assert status == 403

    def test_bad_origin_rejected(self, gui):
        token = get_token(gui)
        status, _ = request(gui["port"], "POST", "/api/jobs",
                            {"kind": "scan", "args": {}},
                            headers={"X-Talaria-Token": token,
                                     "Origin": "https://evil.example.com"})
        assert status == 403

    def test_security_headers_present(self, gui):
        import http.client as hc

        conn = hc.HTTPConnection("127.0.0.1", gui["port"], timeout=10)
        conn.request("GET", "/", headers={"Host": f"127.0.0.1:{gui['port']}"})
        res = conn.getresponse()
        res.read()
        headers = dict(res.getheaders())
        conn.close()
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert "Content-Security-Policy" in headers
        assert headers.get("Referrer-Policy") == "no-referrer"

    def test_asset_traversal_blocked(self, gui):
        status, _ = request(gui["port"], "GET", "/assets/..%2f..%2fetc%2fpasswd")
        assert status in (403, 404)


class TestJobs:
    def test_scan_job_lifecycle(self, gui):
        token = get_token(gui)
        headers = {"X-Talaria-Token": token}
        status, data = request(gui["port"], "POST", "/api/jobs",
                               {"kind": "scan", "args": {}}, headers=headers)
        assert status == 200 and data["job_id"]
        deadline = time.time() + 30
        while time.time() < deadline:
            status, ev = request(gui["port"], "GET", "/api/events?after=0",
                                 headers=headers)
            if not ev["busy"]:
                break
            time.sleep(0.1)
        status, state = request(gui["port"], "GET", "/api/state", headers=headers)
        assert status == 200
        assert state["scan"]["identity"]["hermes_version"] == "0.20.1"
        assert state["scan"]["families"]

    def test_second_job_while_busy_409(self, gui):
        token = get_token(gui)
        headers = {"X-Talaria-Token": token}
        slow_started = threading.Event()

        def slow(cancel_flag):
            slow_started.set()
            time.sleep(1.0)
            return True

        gui["state"].jobs.submit("slow", slow)
        slow_started.wait(5)
        status, _ = request(gui["port"], "POST", "/api/jobs",
                            {"kind": "scan", "args": {}}, headers=headers)
        assert status == 409

    def test_unknown_job_kind(self, gui):
        token = get_token(gui)
        status, _ = request(gui["port"], "POST", "/api/jobs",
                            {"kind": "rm-rf", "args": {}},
                            headers={"X-Talaria-Token": token})
        assert status == 400


class TestSecrets:
    def test_paste_back_writes_env_0600(self, gui):
        import os
        import stat

        token = get_token(gui)
        status, data = request(gui["port"], "POST", "/api/secrets",
                               {"name": "NEW_API_KEY", "value": "sk-pasted"},
                               headers={"X-Talaria-Token": token})
        assert status == 200 and data["ok"]
        env = gui["home"] / ".env"
        assert "NEW_API_KEY=sk-pasted" in env.read_text()
        assert stat.S_IMODE(env.stat().st_mode) == 0o600

    def test_bad_names_rejected(self, gui):
        token = get_token(gui)
        for bad in ("has space", "semi;colon", "", "path/../up"):
            status, _ = request(gui["port"], "POST", "/api/secrets",
                                {"name": bad, "value": "x"},
                                headers={"X-Talaria-Token": token})
            assert status == 400, bad

    def test_empty_vault_passphrase_rejected(self, gui):
        token = get_token(gui)
        status, _ = request(gui["port"], "POST", "/api/vault-passphrase",
                            {"passphrase": ""},
                            headers={"X-Talaria-Token": token})
        assert status == 400
