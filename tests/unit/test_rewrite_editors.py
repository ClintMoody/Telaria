"""Byte-fidelity tests for the structural rewrite editors (R-XPLAT-07, R-APPLY-08)."""

from __future__ import annotations

from talaria.engine.rewrite import dotenv_edit, json_edit, yaml_edit


class TestDotenv:
    def test_set_preserves_everything_else(self):
        text = "# comment\r\nA=1\r\n\r\nexport B=old\nC=3\n"
        out, replaced = dotenv_edit.set_value(text, "B", "new")
        assert replaced
        assert out == "# comment\r\nA=1\r\n\r\nexport B=new\nC=3\n"

    def test_append_uses_dominant_eol(self):
        text = "A=1\r\nB=2\r\n"
        out, replaced = dotenv_edit.set_value(text, "NEW", "x")
        assert not replaced
        assert out.endswith("NEW=x\r\n")

    def test_no_partial_key_match(self):
        text = "TELEGRAM_BOT_TOKEN_OLD=a\nTELEGRAM_BOT_TOKEN=b\n"
        out, _ = dotenv_edit.set_value(text, "TELEGRAM_BOT_TOKEN", "c")
        assert "TELEGRAM_BOT_TOKEN_OLD=a" in out
        assert "TELEGRAM_BOT_TOKEN=c" in out

    def test_get_and_remove(self):
        text = "A=1\nB=2\n"
        assert dotenv_edit.get_value(text, "B") == "2"
        out, removed = dotenv_edit.remove_key(text, "A")
        assert removed and out == "B=2\n"

    def test_bom_preserved(self):
        text = "\ufeffA=1\n"
        out, replaced = dotenv_edit.set_value(text, "A", "2")
        assert replaced and out == "\ufeffA=2\n"


class TestJson:
    def test_round_trip_matches_hermes_style(self):
        original = '{\n  "jobs": [\n    {\n      "id": "abc"\n    }\n  ]\n}\n'
        data = json_edit.load(original)
        assert json_edit.dumps_like_hermes(data, original) == original

    def test_pointer_set(self):
        data = {"jobs": [{"id": "a", "workdir": "/old"}]}
        old = json_edit.pointer_set(data, ["jobs", 0, "workdir"], "/new")
        assert old == "/old" and data["jobs"][0]["workdir"] == "/new"

    def test_find_job(self):
        jobs = [{"id": "a"}, {"id": "b"}]
        assert json_edit.find_job_index(jobs, "b") == 1


YAML_SAMPLE = """# Hermes config
_config_version: 36

model:
  default: "anthropic/claude-opus-4.6"
  base_url: "https://openrouter.ai/api/v1"   # provider endpoint

terminal:
  backend: local
  cwd: "/home/alice/projects/main"

dashboard:
  public_url: "http://old-box.local:8642"
"""


class TestYaml:
    def test_set_scalar_preserves_rest(self):
        out = yaml_edit.set_scalar(YAML_SAMPLE, "terminal.cwd", "/home/bob/projects/main")
        assert out.ok
        assert "cwd: /home/bob/projects/main" in out.text  # plain-safe stays unquoted
        assert out.old_value == "/home/alice/projects/main"
        # Only one line changed.
        diff_lines = [(a, b) for a, b in zip(YAML_SAMPLE.splitlines(),
                                             out.text.splitlines()) if a != b]
        assert len(diff_lines) == 1

    def test_comment_on_line_preserved(self):
        out = yaml_edit.set_scalar(YAML_SAMPLE, "model.base_url", "https://x.example/v1")
        assert out.ok
        assert "# provider endpoint" in out.text

    def test_windows_value_quoted(self):
        out = yaml_edit.set_scalar(YAML_SAMPLE, "terminal.cwd",
                                   "C:\\Users\\bob\\projects")
        assert out.ok
        assert "'C:\\Users\\bob\\projects'" in out.text

    def test_missing_path(self):
        out = yaml_edit.set_scalar(YAML_SAMPLE, "nope.deep", "x")
        assert not out.ok and "not found" in out.reason

    def test_refuses_anchor(self):
        text = "a:\n  b: &anchor value\n"
        out = yaml_edit.set_scalar(text, "a.b", "new")
        assert not out.ok and "anchors" in out.reason

    def test_refuses_flow_collection(self):
        text = "a:\n  b: [1, 2, 3]\n"
        out = yaml_edit.set_scalar(text, "a.b", "new")
        assert not out.ok and "flow" in out.reason

    def test_refuses_tabs(self):
        out = yaml_edit.set_scalar("a:\n\tb: 1\n", "a.b", "x")
        assert not out.ok and "tabs" in out.reason

    def test_refuses_duplicate_keys(self):
        text = "a:\n  b: 1\n  b: 2\n"
        out = yaml_edit.set_scalar(text, "a.b", "x")
        assert not out.ok and "duplicate" in out.reason

    def test_crlf_preserved(self):
        text = "a:\r\n  b: old\r\n"
        out = yaml_edit.set_scalar(text, "a.b", "new")
        assert out.ok and out.text == "a:\r\n  b: new\r\n"

    def test_remove_key_line_comments_out(self):
        text = "model:\n  api_key: sk-secret\n  default: m\n"
        out = yaml_edit.remove_key_line(text, "model.api_key")
        assert out.ok
        assert "sk-secret" not in out.text
        assert "removed by talaria" in out.text
        assert "default: m" in out.text
        assert out.old_value == "sk-secret"

    def test_same_key_name_at_different_depths(self):
        text = "cwd: /top\nterminal:\n  cwd: /nested\n"
        out = yaml_edit.set_scalar(text, "terminal.cwd", "/new")
        assert out.ok
        assert "cwd: /top" in out.text
        assert "/new" in out.text
