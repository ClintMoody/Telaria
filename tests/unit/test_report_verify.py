"""Tests for verify checks, checklist cards, and the report pipeline (redaction, A10)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine import checklist as cl  # noqa: E402
from talaria.engine import report as rpt  # noqa: E402
from talaria.engine import verify as vfy  # noqa: E402
from talaria.engine.scan import scan  # noqa: E402


class TestVerify:
    def test_functional_checks_on_fixture(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(with_machine_bound=False))
        checks = vfy.functional_checks(inst.home)
        by_id = {}
        for c in checks:
            by_id.setdefault(c.id, []).append(c)
        assert by_id["V-03"][0].status == "ok"          # no machine-bound leftovers
        assert any(c.status == "ok" for c in by_id.get("V-04", []))  # state.db healthy

    def test_machine_bound_leftovers_warn(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(with_machine_bound=True))
        checks = vfy.functional_checks(inst.home)
        v3 = next(c for c in checks if c.id == "V-03")
        assert v3.status == "warn" and "gateway_state.json" in v3.detail

    def test_no_txn_verify(self, tmp_path):
        checks = vfy.verify_last_apply(tmp_path)
        assert checks[0].status == "info"

    def test_heartbeat_watch_timeout(self, tmp_path):
        check = vfy.watch_heartbeat(tmp_path, timeout_seconds=1, poll_seconds=0.2)
        assert check.status == "warn"

    def test_heartbeat_watch_detects(self, tmp_path):
        hb = tmp_path / "cron" / "ticker_heartbeat"
        hb.parent.mkdir(parents=True)
        hb.write_text("1")
        import threading, time as _t

        def beat():
            _t.sleep(0.3)
            hb.write_text("2")

        threading.Thread(target=beat, daemon=True).start()
        check = vfy.watch_heartbeat(tmp_path, timeout_seconds=5, poll_seconds=0.1)
        assert check.status == "ok"


class TestChecklist:
    def test_secret_cards_have_urls_not_values(self):
        items = [{"name": "OPENROUTER_API_KEY", "file": ".env", "secret": True},
                 {"name": "HERMES_TIMEZONE", "file": ".env", "secret": False},
                 {"name": "auth.json", "file": "auth.json", "secret": True}]
        cards = cl.secrets_cards(items)
        names = {c.title for c in cards}
        assert "OPENROUTER_API_KEY" in names
        assert "HERMES_TIMEZONE" not in names
        router = next(c for c in cards if c.title == "OPENROUTER_API_KEY")
        assert router.url and "openrouter.ai" in router.url

    def test_post_restore_cards_keyed_to_findings(self):
        manifest = {"source": {"lazy_features": ["provider.anthropic"],
                               "git_dirty": True},
                    "artifacts": [{"kind": "mcp-tokens", "files": [{"m": 1}]}],
                    "checklist": {"items": []}, "capture_mode": "live"}
        outcome = {"skipped": [
            {"path": "platforms/whatsapp/session/creds.json",
             "reason": "machine-bound (device-linked) — filtered"},
            {"path": "scripts/whatsapp-bridge/node_modules/x",
             "reason": "capture excluded"}]}
        cards = cl.post_restore_cards(manifest, outcome)
        ids = {c.id for c in cards}
        assert {"gateway-install", "whatsapp-pair", "mcp-reauth", "lazy-features",
                "bridge-npm", "live-capture", "checkout-patch", "doctor"} <= ids
        for card in cards:
            assert " " not in card.verb  # one verb per card

    def test_state_round_trip(self, tmp_path):
        cards = [cl.Card("a", "Do", "Thing A"), cl.Card("b", "Do", "Thing B")]
        cards[0].done = True
        cl.save_state(tmp_path / "checklist.json", cards)
        fresh = [cl.Card("a", "Do", "Thing A"), cl.Card("b", "Do", "Thing B")]
        cl.load_state(tmp_path / "checklist.json", fresh)
        assert fresh[0].done and not fresh[1].done


class TestReports:
    @pytest.fixture()
    def overview(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        result = scan(inst.home)
        from talaria.engine.provenance import classify_skills

        provs = [p.to_json() for p in classify_skills(inst.skills)]
        return rpt.build_overview(result, provs, [])

    def test_html_self_contained_and_escaped(self, overview, tmp_path):
        outputs = rpt.write_reports(overview, tmp_path / "out")
        html_text = outputs["html"].read_text()
        assert "Content-Security-Policy" in html_text
        assert "http://" not in html_text.replace("http-equiv", "")  # no external refs
        assert "https://" not in html_text
        assert "<script src" not in html_text
        assert "talaria-data" in html_text  # JSON appendix
        import stat

        assert stat.S_IMODE(outputs["html"].stat().st_mode) == 0o600

    def test_redaction_masks_home_and_user(self, overview, tmp_path):
        outputs = rpt.write_reports(overview, tmp_path / "out", redaction="default")
        blob = outputs["json"].read_text()
        home = str(Path.home())
        if home != "/":
            assert home not in blob
        assert "sk-or-fake" not in blob

    def test_no_redact_keeps_paths(self, overview, tmp_path):
        outputs = rpt.write_reports(overview, tmp_path / "out2", redaction="none")
        blob = outputs["json"].read_text()
        assert "hermes" in blob  # real paths retained locally

    def test_strict_drops_soul_quote(self, overview, tmp_path):
        assert overview.soul_quote
        redacted = rpt.redact(overview, "strict")
        assert redacted.soul_quote == ""

    def test_hostile_names_escaped(self, tmp_path):
        data = rpt.ReportData(kind="migration")
        data.run = {"mode": "committed", "exit_code": 0,
                    "generated_at": "2026-08-15"}
        data.failures = ["<script>alert(1)</script>"]
        html_text = rpt.render_html(rpt.redact(data))
        assert "<script>alert(1)</script>" not in html_text
        assert "&lt;script&gt;" in html_text

    def test_markdown_render(self, overview):
        md = rpt.render_md(rpt.redact(overview))
        assert "# Talaria Overview Report" in md
        assert "stock-modified" in md
