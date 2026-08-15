"""Tests for the YAML-subset reader against realistic Hermes config shapes."""

from __future__ import annotations

from talaria.engine import yamlmini


REALISTIC = """# Hermes Agent CLI Configuration
_config_version: 36
timezone: America/Chicago

model:
  default: "anthropic/claude-opus-4.6"
  provider: "auto"
  base_url: "https://openrouter.ai/api/v1"

database:
  journal_mode: "wal"

skills:
  creation_nudge_interval: 15
  disabled:
    - social-media-poster
  external_dirs:
    - ~/.agents/skills
    - /home/shared/team-skills

plugins:
  enabled:
    - disk-cleanup

mcp_servers:
  linear:
    url: "https://mcp.linear.app/mcp"
    auth: oauth
    enabled: true
  local-files:
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/alice/.hermes/mcp-data"]
    enabled: true
  n8n:
    command: "/home/alice/.hermes/mcp-installs/n8n/.venv/bin/python"
    env:
      N8N_API_KEY: "${MCP_N8N_API_KEY}"

terminal:
  backend: local
  cwd: "/home/alice/projects/main"

cron:
  provider: builtin

memory:
  memory_enabled: true
  provider: null
"""


class TestParse:
    def test_top_level_scalars(self):
        cfg = yamlmini.parse(REALISTIC)
        assert cfg["_config_version"] == 36
        assert cfg["timezone"] == "America/Chicago"

    def test_nested_maps(self):
        cfg = yamlmini.parse(REALISTIC)
        assert cfg["model"]["default"] == "anthropic/claude-opus-4.6"
        assert cfg["database"]["journal_mode"] == "wal"
        assert cfg["memory"]["provider"] is None
        assert cfg["memory"]["memory_enabled"] is True

    def test_block_lists(self):
        cfg = yamlmini.parse(REALISTIC)
        assert cfg["skills"]["disabled"] == ["social-media-poster"]
        assert cfg["skills"]["external_dirs"] == ["~/.agents/skills", "/home/shared/team-skills"]

    def test_flow_lists(self):
        cfg = yamlmini.parse(REALISTIC)
        args = cfg["mcp_servers"]["local-files"]["args"]
        assert args == ["-y", "@modelcontextprotocol/server-filesystem",
                        "/home/alice/.hermes/mcp-data"]

    def test_deep_nesting_and_env_refs(self):
        cfg = yamlmini.parse(REALISTIC)
        assert cfg["mcp_servers"]["n8n"]["env"]["N8N_API_KEY"] == "${MCP_N8N_API_KEY}"
        assert cfg["mcp_servers"]["linear"]["enabled"] is True

    def test_get_path(self):
        cfg = yamlmini.parse(REALISTIC)
        assert yamlmini.get_path(cfg, "terminal.cwd") == "/home/alice/projects/main"
        assert yamlmini.get_path(cfg, "cron.provider") == "builtin"
        assert yamlmini.get_path(cfg, "nope.deep.key", "dflt") == "dflt"

    def test_comments_and_quotes(self):
        cfg = yamlmini.parse('key: "value # not comment"  # real comment\nother: \'a\'\n')
        assert cfg["key"] == "value # not comment"
        assert cfg["other"] == "a"

    def test_windows_paths(self):
        cfg = yamlmini.parse('terminal:\n  cwd: "C:\\\\Users\\\\bob\\\\projects"\n')
        assert cfg["terminal"]["cwd"] == "C:\\Users\\bob\\projects"

    def test_garbage_degrades_not_raises(self):
        assert yamlmini.parse("") == {}
        assert isinstance(yamlmini.parse("just words\nno structure"), dict)
        assert isinstance(yamlmini.parse("a:\n\tb: tabbed"), dict)

    def test_list_of_maps(self):
        cfg = yamlmini.parse("items:\n  - name: a\n    v: 1\n  - name: b\n    v: 2\n")
        assert cfg["items"] == [{"name": "a", "v": 1}, {"name": "b", "v": 2}]
