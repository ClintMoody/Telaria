"""Tests for talaria.engine.resolve — home/profile/identity resolution."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine import resolve  # noqa: E402


class TestHomes:
    def test_default_homes(self):
        assert resolve.default_home_for("linux", "/home/a") == "/home/a/.hermes"
        assert resolve.default_home_for("darwin", "/Users/a") == "/Users/a/.hermes"
        assert resolve.default_home_for(
            "win32", "C:\\Users\\a", "C:\\Users\\a\\AppData\\Local"
        ) == "C:\\Users\\a\\AppData\\Local\\hermes"

    def test_env_override(self):
        assert resolve.resolve_home({"HERMES_HOME": "/srv/h"}, "linux") == Path("/srv/h")

    def test_profile_split(self):
        assert resolve.resolve_root_and_profile(Path("/h/.hermes")) == (Path("/h/.hermes"), None)
        root, prof = resolve.resolve_root_and_profile(Path("/h/.hermes/profiles/coder"))
        assert (root, prof) == (Path("/h/.hermes"), "coder")

    def test_profile_homes(self, tmp_path):
        (tmp_path / "profiles" / "coder").mkdir(parents=True)
        homes = resolve.profile_homes(tmp_path)
        assert set(homes) == {"", "coder"}

    def test_looks_like_hermes_home(self, tmp_path):
        assert not resolve.looks_like_hermes_home(tmp_path)
        (tmp_path / "config.yaml").write_text("x")
        (tmp_path / "skills").mkdir()
        assert resolve.looks_like_hermes_home(tmp_path)


class TestIdentity:
    @pytest.fixture()
    def install(self, tmp_path):
        return build_fake_install(tmp_path / "hermes", FakeInstallSpec(with_git=True,
                                                                       with_profile="coder"))

    def test_identity_full(self, install):
        ident = resolve.detect_identity(install.home, run_venv_probe=False)
        assert ident.hermes_version == "0.20.1"
        assert ident.release_date == "2026.8.13"
        assert ident.install_method == "git"
        assert ident.git_head and len(ident.git_head) == 40
        assert ident.git_tag == "v2026.8.13"
        assert ident.config_version == 36
        assert ident.profiles == ["coder"]

    def test_dirty_detection(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(with_git=True,
                                                                  with_dirty_checkout=True))
        ident = resolve.detect_identity(inst.home, run_venv_probe=False)
        assert ident.git_dirty

    def test_no_checkout_degrades(self, tmp_path):
        (tmp_path / "config.yaml").write_text("_config_version: 36\n")
        ident = resolve.detect_identity(tmp_path, run_venv_probe=False)
        assert ident.install_method == "unknown"
        assert ident.hermes_version is None
        assert any("state-only" in n for n in ident.notes)

    def test_install_method_marker(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec(with_git=False))
        ident = resolve.detect_identity(inst.home, run_venv_probe=False)
        assert ident.install_method == "git"  # from .install_method marker file
