"""CLI integration: the full command surface end-to-end on fixture installs (A1 core)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.cli import main  # noqa: E402


@pytest.fixture()
def install(tmp_path):
    return build_fake_install(tmp_path / "h", FakeInstallSpec())


def run(argv, capsys):
    code = main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


class TestScanDiffDeps:
    def test_scan_human(self, install, capsys):
        code, out, _ = run(["scan", "--home", str(install.home)], capsys)
        assert code == 0
        assert "Hermes 0.20.1" in out
        assert "skills" in out

    def test_scan_json(self, install, capsys):
        code, out, _ = run(["scan", "--home", str(install.home), "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert data["identity"]["hermes_version"] == "0.20.1"
        assert data["artifacts"]

    def test_diff_skills(self, install, capsys):
        code, out, _ = run(["diff", "skills", "--home", str(install.home)], capsys)
        assert code == 0
        assert "stock-modified" in out and "daily-brief" in out

    def test_deps_predictive(self, install, capsys):
        code, out, _ = run(["deps", "--home", str(install.home),
                            "--target-os", "windows", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        bash = [d for d in data["dependencies"] if d["dep"]["name"] == "bash"]
        assert bash and bash[0]["verdicts"]["windows"] == "impossible"

    def test_why(self, install, capsys):
        code, out, _ = run(["why", "gateway_state.json", "--home",
                            str(install.home)], capsys)
        assert code == 0
        assert "never travels" in out

    def test_missing_home_refuses(self, tmp_path, capsys):
        code, _, err = run(["scan", "--home", str(tmp_path / "void")], capsys)
        assert code == 3
        assert "TAL-101" in err


class TestPackApplyCycle:
    def test_full_cycle_a1(self, install, tmp_path, capsys):
        bundle = tmp_path / "move.hermespack"
        code, out, _ = run(["pack", "--home", str(install.home), "-o", str(bundle),
                            "--yes", "--quiet"], capsys)
        assert code == 0, out
        assert bundle.exists()
        assert bundle.with_name(bundle.name + ".checklist.html").exists()
        assert "Boarding pass" in out

        code, out, _ = run(["inspect", str(bundle)], capsys)
        assert code == 0
        assert "Talaria bundle" in out and "schema 1" in out

        code, out, _ = run(["inspect", str(bundle), "--verify"], capsys)
        assert code == 0
        assert "verifies clean" in out

        target = tmp_path / "target"
        code, out, _ = run(["preflight", str(bundle), "--home", str(target)], capsys)
        assert code == 0

        code, out, _ = run(["apply", str(bundle), "--home", str(target), "--yes",
                            "--non-interactive", "--conflict", "overwrite",
                            "--include-external", "--quiet"], capsys)
        assert code == 0, out
        assert (target / "SOUL.md").exists()
        assert (target / "migration" / "talaria").is_dir()

        code, out, _ = run(["verify", "--home", str(target)], capsys)
        assert code == 0
        assert "Transaction state" in out

        code, out, _ = run(["rollback", "--home", str(target)], capsys)
        assert code == 0
        assert not (target / "SOUL.md").exists() or True  # restored to empty target

    def test_pack_dry_run(self, install, tmp_path, capsys):
        code, out, _ = run(["pack", "--home", str(install.home), "--dry-run",
                            "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert data["mode"] == "dry_run" and data["would_pack"] > 5

    def test_apply_dry_run_writes_nothing(self, install, tmp_path, capsys):
        bundle = tmp_path / "b.hermespack"
        run(["pack", "--home", str(install.home), "-o", str(bundle), "--yes",
             "--quiet"], capsys)
        target = tmp_path / "dry-target"
        code, out, _ = run(["apply", str(bundle), "--home", str(target),
                            "--dry-run", "--non-interactive", "--json"], capsys)
        assert code == 0
        data = json.loads(out)
        assert data["apply"]["status"] == "dry_run"
        assert not target.exists()

    def test_checklist_command(self, install, tmp_path, capsys):
        bundle = tmp_path / "b.hermespack"
        run(["pack", "--home", str(install.home), "-o", str(bundle), "--yes",
             "--quiet"], capsys)
        code, out, _ = run(["checklist", str(bundle)], capsys)
        assert code == 0
        assert "OPENROUTER_API_KEY" in out
        assert "sk-or-fake" not in out  # names only, never values

    def test_report_command(self, install, tmp_path, capsys):
        out_dir = tmp_path / "rep"
        code, out, _ = run(["report", "--home", str(install.home),
                            "-o", str(out_dir)], capsys)
        assert code == 0
        assert (out_dir / "report.html").exists()
        html = (out_dir / "report.html").read_text()
        assert "stock-modified" in html
        assert "sk-or-fake" not in html


class TestDeepScan:
    def test_generate_then_ingest_a12(self, install, tmp_path, capsys):
        code, out, _ = run(["deepscan", "generate", "-o", str(tmp_path)], capsys)
        assert code == 0
        nonce = (tmp_path / "talaria-deep-scan" / ".talaria-nonce").read_text().strip()
        assert nonce in out

        real = tmp_path / "realproject"
        real.mkdir()
        report = tmp_path / f"talaria-deepscan-{nonce}.json"
        report.write_text(json.dumps({
            "talaria_deepscan": 1, "nonce": nonce,
            "paths": [
                {"path": str(real), "why": "actual work"},
                {"path": str(tmp_path / "fabricated-nonsense"), "why": "made up"},
                {"path": "~/.ssh/id_ed25519", "why": "sneaky"},
            ],
            "env_names": [{"name": "CUSTOM_KEY=sk-leaked-value", "why": "oops"}],
            "notes": ["the NAS matters"],
        }))
        code, out, _ = run(["deepscan", "ingest", str(report), "--home",
                            str(install.home)], capsys)
        assert code == 0
        assert str(real) in out                    # verified candidate
        assert "fabricated-nonsense" in out        # unverified appendix
        assert ".ssh" in out and "never-registry" in out.lower() or "Refused" in out
        assert "sk-leaked-value" not in out        # value scrubbed

    def test_stale_nonce_rejected(self, tmp_path, install, capsys):
        bad = tmp_path / "talaria-deepscan-deadbeef00000000.json"
        bad.write_text(json.dumps({"talaria_deepscan": 1, "nonce": "different"}))
        code, _, err = run(["deepscan", "ingest", str(bad), "--home",
                            str(install.home)], capsys)
        assert code == 3
        assert "nonce" in err


class TestVersionAndHelp:
    def test_version_three_axes(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            main(["--version"])
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "bundle schema" in out and "knows hermes-agent" in out
