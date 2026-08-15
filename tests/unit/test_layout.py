"""Tests for talaria.layout — the encoded state-layout knowledge."""

from __future__ import annotations

from pathlib import Path

from talaria import layout


class TestRoots:
    def test_default_home_posix(self):
        assert layout.default_home_for("linux", "/home/alice") == "/home/alice/.hermes"
        assert layout.default_home_for("darwin", "/Users/alice") == "/Users/alice/.hermes"

    def test_default_home_windows_localappdata(self):
        got = layout.default_home_for("win32", "C:\\Users\\alice",
                                      localappdata="C:\\Users\\alice\\AppData\\Local")
        assert got == "C:\\Users\\alice\\AppData\\Local\\hermes"

    def test_default_home_windows_fallback(self):
        got = layout.default_home_for("win32", "C:\\Users\\alice", localappdata="  ")
        assert got == "C:\\Users\\alice\\AppData\\Local\\hermes"

    def test_resolve_home_env_override(self):
        assert layout.resolve_home({"HERMES_HOME": "/srv/h"}) == Path("/srv/h")

    def test_root_and_profile_split(self):
        root, prof = layout.resolve_root_and_profile(Path("/home/a/.hermes"))
        assert (root, prof) == (Path("/home/a/.hermes"), None)
        root, prof = layout.resolve_root_and_profile(Path("/home/a/.hermes/profiles/coder"))
        assert (root, prof) == (Path("/home/a/.hermes"), "coder")

    def test_profile_homes(self, tmp_path: Path):
        (tmp_path / "profiles" / "coder").mkdir(parents=True)
        (tmp_path / "profiles" / "writer").mkdir()
        (tmp_path / "profiles" / ".hidden").mkdir()
        homes = layout.profile_homes(tmp_path)
        assert set(homes) == {None, "coder", "writer"}
        assert homes["coder"] == tmp_path / "profiles" / "coder"


class TestPredicates:
    def test_machine_bound_names(self):
        for name in ("gateway_state.json", "gateway.pid", "cron.pid", ".update_check",
                     ".restart_gateway.json", ".sync_device_id"):
            assert layout.is_machine_bound_name(name), name
        for name in ("config.yaml", "state.db", "SOUL.md", "jobs.json"):
            assert not layout.is_machine_bound_name(name), name

    def test_sidecars(self):
        assert layout.is_sqlite_sidecar("state.db-wal")
        assert layout.is_sqlite_sidecar("notepad.db-shm")
        assert not layout.is_sqlite_sidecar("state.db")

    def test_secret_paths(self):
        for rel in (".env", "auth.json", "mcp-tokens/linear.json",
                    "platforms/pairing/telegram.json", "profiles/coder/.env",
                    "platforms/whatsapp/session/creds.json", "shared/nous_auth.json"):
            assert layout.is_secret_path(rel), rel
        for rel in ("config.yaml", "skills/research/web-search/SKILL.md", "state.db"):
            assert not layout.is_secret_path(rel), rel

    def test_device_bound(self):
        assert layout.is_device_bound("platforms/whatsapp/session/creds.json")
        assert not layout.is_device_bound("platforms/pairing/telegram.json")

    def test_env_parsing_and_secret_names(self):
        text = """# comment
OPENROUTER_API_KEY=sk-123
export TELEGRAM_HOME_CHANNEL=-100
EMAIL_ADDRESS=a@b.c
BROKEN LINE
"""
        names = layout.iter_env_var_names(text)
        assert names == ["OPENROUTER_API_KEY", "TELEGRAM_HOME_CHANNEL", "EMAIL_ADDRESS"]
        assert layout.is_secret_env_name("OPENROUTER_API_KEY")
        assert layout.is_secret_env_name("EMAIL_PASSWORD")
        assert not layout.is_secret_env_name("TELEGRAM_HOME_CHANNEL")
        assert not layout.is_secret_env_name("HERMES_TIMEZONE")


class TestPruning:
    def test_vendored_roots_pruned_at_root_only(self):
        assert layout.should_prune_dir(("hermes-agent",))
        assert layout.should_prune_dir(("node",))
        assert layout.should_prune_dir(("logs",))
        # The famous trap: a skill vendoring hermes-agent examples is real data.
        assert not layout.should_prune_dir(("skills", "autonomous-ai-agents", "hermes-agent"))

    def test_regeneratable_anywhere(self):
        assert layout.should_prune_dir(("skills", "x", "__pycache__"))
        assert layout.should_prune_dir(("plugins", "p", "node_modules"))
        assert layout.should_prune_dir(("skills", "cat", "skill", ".venv"))

    def test_checkpoints_root_only(self):
        assert layout.should_prune_dir(("checkpoints",))
        assert not layout.should_prune_dir(("skills", "x", "checkpoints"))

    def test_skills_drop_subpaths(self):
        assert layout.should_prune_dir(("skills", ".hub", "index-cache"))
        assert layout.should_prune_dir(("skills", ".curator_backups"))
        assert not layout.should_prune_dir(("skills", ".hub"))
        assert not layout.should_prune_dir(("skills", ".archive"))

    def test_profile_subtrees_not_confused(self):
        # A profile's own skills caches prune the same way.
        assert layout.should_prune_dir(("profiles", "coder", "skills", ".hub", "index-cache"))
        assert not layout.should_prune_dir(("profiles", "coder", "skills"))
