"""Tests for the dependency engine: extraction + predictive/live feasibility."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine import deps  # noqa: E402
from talaria.engine.scan import scan  # noqa: E402


@pytest.fixture(scope="module")
def scanned(tmp_path_factory):
    root = tmp_path_factory.mktemp("deps")
    inst = build_fake_install(root / "h", FakeInstallSpec())
    return inst, scan(inst.home)


@pytest.fixture(scope="module")
def findings(scanned):
    inst, result = scanned
    return deps.collect_all(result, inst.skills)


class TestExtraction:
    def test_cron_bash_dependency(self, findings):
        bash = [f for f in findings if f.dependency.kind == "binary"
                and f.dependency.name == "bash"]
        assert bash and bash[0].dependency.enforced

    def test_cron_croniter(self, findings):
        assert any(f.dependency.name == "croniter" for f in findings)

    def test_delivery_env_vars(self, findings):
        tokens = {f.dependency.name for f in findings if f.dependency.kind == "env_var"}
        assert "TELEGRAM_BOT_TOKEN" in tokens   # deliver: telegram job
        assert "EMAIL_PASSWORD" in tokens       # deliver: email job

    def test_drift_guard_flagged(self, findings):
        drift = [f for f in findings if f.dependency.kind == "config_key"
                 and f.dependency.detail.get("model_snapshot")]
        assert drift and "drift" in drift[0].remediation

    def test_context_from_coupling(self, findings):
        refs = {f.dependency.name for f in findings if f.dependency.kind == "artifact_ref"}
        assert "cron-output/a1b2c3d4e5f6" in refs

    def test_script_artifact_ref(self, findings):
        refs = {f.dependency.name for f in findings if f.dependency.kind == "artifact_ref"}
        assert "scripts/check_site.sh" in refs

    def test_mcp_node_and_abs_paths(self, findings):
        node = [f for f in findings if f.dependency.kind == "node"]
        assert node  # npx server
        abs_bins = [f for f in findings if f.dependency.kind == "binary"
                    and f.dependency.detail.get("absolute")]
        assert abs_bins  # n8n venv python

    def test_mcp_env_cross_check(self, findings):
        n8n_env = [f for f in findings if f.dependency.kind == "env_var"
                   and f.dependency.name == "MCP_N8N_API_KEY"]
        assert n8n_env and "present in source .env" in n8n_env[0].remediation


class TestFrontmatter:
    def test_skill_frontmatter_extraction(self, tmp_path):
        d = tmp_path / "skill"
        d.mkdir()
        (d / "SKILL.md").write_text("""---
name: mailer
platforms: [macos, linux]
required_environment_variables:
  - name: SMTP_PASSWORD
    prompt: Your SMTP password
    provider_url: https://mail.example.com
  - name: OPTIONAL_THING
    optional: true
prerequisites:
  commands:
    - ffmpeg
dependencies:
  - requests
---
# Mailer
""")
        found = deps.skill_dependencies(d, "skill-dir@/mailer")
        kinds = {(f.dependency.kind, f.dependency.name): f for f in found}
        assert ("platform", "macos,linux") in kinds
        assert kinds[("platform", "macos,linux")].dependency.enforced
        assert kinds[("env_var", "SMTP_PASSWORD")].dependency.enforced
        assert not kinds[("env_var", "OPTIONAL_THING")].dependency.enforced
        assert not kinds[("binary", "ffmpeg")].dependency.enforced
        assert ("python_pkg", "requests") in kinds


class TestPredictive:
    def test_bash_impossible_on_windows(self, findings):
        deps.evaluate_predictive(findings, "windows")
        bash = next(f for f in findings if f.dependency.name == "bash")
        assert bash.verdicts["windows"] == "impossible"

    def test_bash_ok_on_linux(self, findings):
        deps.evaluate_predictive(findings, "linux")
        bash = next(f for f in findings if f.dependency.name == "bash")
        assert bash.verdicts["linux"] != "impossible"

    def test_platform_gate(self, tmp_path):
        d = tmp_path / "s"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: mac-only\nplatforms: [macos]\n---\n")
        found = deps.skill_dependencies(d, "x")
        deps.evaluate_predictive(found, "windows")
        deps.evaluate_predictive(found, "macos")
        deps.evaluate_predictive(found, "termux")
        plat = found[0]
        assert plat.verdicts["windows"] == "impossible"
        assert plat.verdicts["macos"] == "ok"
        assert plat.verdicts["termux"] == "impossible"

    def test_termux_accepts_linux_skills(self, tmp_path):
        d = tmp_path / "s"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: lin\nplatforms: [linux]\n---\n")
        found = deps.skill_dependencies(d, "x")
        deps.evaluate_predictive(found, "termux")
        assert found[0].verdicts["termux"] == "ok"

    def test_env_vars_are_actions(self, findings):
        deps.evaluate_predictive(findings, "linux")
        env_findings = [f for f in findings if f.dependency.kind == "env_var"]
        assert env_findings
        assert all(f.verdicts["linux"] == "action" for f in env_findings)

    def test_windows_member_legality(self):
        out = deps.evaluate_members_for_windows(
            ["payload/home/skills/CON/SKILL.md", "payload/home/ok.txt"])
        assert len(out) == 1
        assert out[0].verdicts["windows"] == "impossible"


class TestLive:
    def test_live_probe_this_machine(self, findings):
        deps.evaluate_live(findings)
        bash = next(f for f in findings if f.dependency.name == "bash")
        # This CI box is Linux with bash present.
        assert bash.verdicts["linux"] == "ok"

    def test_live_env_missing(self, findings, monkeypatch):
        monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
        deps.evaluate_live(findings)
        tel = next(f for f in findings if f.dependency.name == "TELEGRAM_BOT_TOKEN")
        assert tel.verdicts["linux"] == "action"
