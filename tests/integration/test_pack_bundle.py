"""Integration: scan → pack → hardened read-back, vault round-trip, hostile bundles."""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "fixtures"))
from hermes_factory import FakeInstallSpec, build_fake_install  # noqa: E402

from talaria.engine import vault as vault_mod  # noqa: E402
from talaria.engine.bundle import (  # noqa: E402
    BundleKind,
    BundleReader,
    MANIFEST_NAME,
    STUB_NAME,
    detect_kind,
)
from talaria.engine.pack import PackOptions, pack  # noqa: E402
from talaria.engine.scan import scan  # noqa: E402
from talaria.errors import Refusal  # noqa: E402
from talaria.model.selection import Selection  # noqa: E402


@pytest.fixture(scope="module")
def packed(tmp_path_factory):
    root = tmp_path_factory.mktemp("packint")
    inst = build_fake_install(root / "h", FakeInstallSpec(with_profile="coder"))
    result = scan(inst.home)
    out = root / "out" / "hermes-test.hermespack"
    out.parent.mkdir()
    pres = pack(result, out, PackOptions())
    return inst, result, pres


class TestPack:
    def test_bundle_published_and_detected(self, packed):
        _inst, _scan, pres = packed
        assert pres.bundle_path.exists()
        kind, _detail = detect_kind(pres.bundle_path)
        assert kind == BundleKind.TALARIA
        assert not list(pres.bundle_path.parent.glob("*.partial"))

    def test_stub_first_manifest_last(self, packed):
        _inst, _scan, pres = packed
        with zipfile.ZipFile(pres.bundle_path) as zf:
            names = zf.namelist()
            assert names[0] == STUB_NAME
            assert names[-1] == MANIFEST_NAME
            stub = json.loads(zf.read(STUB_NAME))
            assert stub["schema_version"] == 1
            assert stub["source"]["hermes_version"] == "0.20.1"

    def test_no_plaintext_credentials_in_payload(self, packed):
        """The A3 core assertion: credential canaries appear in zero members."""
        _inst, _scan, pres = packed
        with zipfile.ZipFile(pres.bundle_path) as zf:
            for name in zf.namelist():
                blob = zf.read(name)
                assert b"sk-or-fake-1234567890" not in blob, name
                assert b"FAKE-telegram-token" not in blob, name
                assert b"fake-refresh-token" not in blob, name
                assert b"fake-mcp-oauth" not in blob, name
                assert b"fake-email-secret" not in blob, name

    def test_checklist_names_only(self, packed):
        _inst, _scan, pres = packed
        names = {i["name"] for i in pres.manifest["checklist"]["items"]}
        assert "OPENROUTER_API_KEY" in names
        assert "TELEGRAM_BOT_TOKEN" in names
        # Non-secret env vars are not checklist items.
        assert "HERMES_TIMEZONE" not in names
        blob = json.dumps(pres.manifest)
        assert "sk-or-fake" not in blob

    def test_machine_bound_absent(self, packed):
        _inst, _scan, pres = packed
        with zipfile.ZipFile(pres.bundle_path) as zf:
            names = zf.namelist()
        for banned in ("gateway_state.json", "gateway.pid", "cron.pid", "state.db-wal",
                       "creds.json", "ticker_heartbeat"):
            assert not any(banned in n for n in names), banned

    def test_content_travels(self, packed):
        _inst, _scan, pres = packed
        with zipfile.ZipFile(pres.bundle_path) as zf:
            names = set(zf.namelist())
        assert "payload/home/state.db" in names
        assert "payload/home/SOUL.md" in names
        assert "payload/home/cron/jobs.json" in names
        assert "payload/home/profiles/coder/SOUL.md" in names
        assert "payload/home/skills/.bundled_manifest" in names

    def test_wal_content_snapshotted(self, packed):
        """state.db in the bundle must be a valid standalone database."""
        import sqlite3
        import tempfile

        _inst, _scan, pres = packed
        with zipfile.ZipFile(pres.bundle_path) as zf, \
                tempfile.TemporaryDirectory() as td:
            out = Path(td) / "state.db"
            out.write_bytes(zf.read("payload/home/state.db"))
            conn = sqlite3.connect(out)
            try:
                count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
                assert count >= 1
            finally:
                conn.close()

    def test_reader_verifies_clean(self, packed):
        _inst, _scan, pres = packed
        with BundleReader(pres.bundle_path) as reader:
            problems = reader.verify_structure()
            assert problems == []
            assert reader.header is not None
            assert reader.header.schema_version == 1
            assert len(reader.members) > 20

    def test_salvage_all_ok(self, packed):
        _inst, _scan, pres = packed
        with BundleReader(pres.bundle_path) as reader:
            report = reader.salvage_report()
        assert report and all(v == "ok" for v in report.values())

    def test_meta_members(self, packed):
        _inst, _scan, pres = packed
        with BundleReader(pres.bundle_path) as reader:
            prov = json.loads(reader.read_meta("provenance.json"))
            tags = {s["name"]: s["tag"] for s in prov["skills"]}
            assert tags["daily-brief"] == "stock-modified"
            refs = json.loads(reader.read_meta("machine_refs.json"))
            assert any(r["locator"] == "terminal.cwd" for r in refs)


class TestForeignZips:
    def test_hermes_backup_detected(self, tmp_path):
        z = tmp_path / "hermes-backup.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("config.yaml", "x: 1")
            zf.writestr(".env", "A=1")
            zf.writestr("state.db", "fake")
        kind, _ = detect_kind(z)
        assert kind == BundleKind.HERMES_BACKUP
        with pytest.raises(Refusal) as exc_info:
            BundleReader(z).open()
        assert exc_info.value.code == "TAL-304"

    def test_hermes_backup_with_prefix(self, tmp_path):
        z = tmp_path / "pfx.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("backup-2026/config.yaml", "x: 1")
            zf.writestr("backup-2026/.env", "A=1")
        assert detect_kind(z)[0] == BundleKind.HERMES_BACKUP

    def test_random_zip_refused(self, tmp_path):
        z = tmp_path / "random.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("whatever.txt", "hi")
        assert detect_kind(z)[0] == BundleKind.FOREIGN_ZIP

    def test_not_a_zip(self, tmp_path):
        p = tmp_path / "nope.hermespack"
        p.write_text("not a zip")
        assert detect_kind(p)[0] == BundleKind.NOT_ZIP


class TestHostileBundles:
    def _mk_bundle(self, tmp_path, members):
        """Minimal talaria-shaped bundle with the given payload members."""
        z = tmp_path / "hostile.hermespack"
        manifest = {
            "schema_version": 1, "min_reader_tool_version": "1.0.0",
            "created_by_tool_version": "1.0.0",
            "created_at": "2026-08-15T00:00:00Z", "source": {},
            "artifacts": [{"id": "x@", "kind": "unrecognized", "files": [
                {"member": m, "home_rel": m.split("payload/home/")[-1], "size": 4,
                 "sha256": "", "mode": 420, "mtime": 0.0} for m in members]}],
        }
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(STUB_NAME, json.dumps(manifest))
            for m in members:
                zf.writestr(m, "evil")
            zf.writestr(MANIFEST_NAME, json.dumps(manifest))
        return z

    def test_traversal_member(self, tmp_path):
        z = self._mk_bundle(tmp_path, ["payload/home/../../etc/passwd"])
        with BundleReader(z) as reader:
            problems = reader.verify_structure()
        assert any("traversal" in p for p in problems)

    def test_absolute_member(self, tmp_path):
        z = self._mk_bundle(tmp_path, ["/etc/passwd"])
        with BundleReader(z) as reader:
            assert any("absolute" in p for p in reader.verify_structure())

    def test_backslash_and_drive(self, tmp_path):
        z = self._mk_bundle(tmp_path, ["payload/home/a\\b", "C:evil"])
        with BundleReader(z) as reader:
            problems = reader.verify_structure()
        assert any("backslash" in p for p in problems)
        assert any("drive" in p for p in problems)

    def test_casefold_collision(self, tmp_path):
        z = self._mk_bundle(tmp_path, ["payload/home/Foo.md", "payload/home/foo.md"])
        with BundleReader(z) as reader:
            assert any("collision" in p for p in reader.verify_structure())

    def test_reserved_name(self, tmp_path):
        z = self._mk_bundle(tmp_path, ["payload/home/CON"])
        with BundleReader(z) as reader:
            assert any("reserved" in p for p in reader.verify_structure())

    def test_unmanifested_member(self, tmp_path):
        z = tmp_path / "extra.hermespack"
        manifest = {"schema_version": 1, "min_reader_tool_version": "1.0.0",
                    "created_by_tool_version": "1.0.0",
                    "created_at": "2026-08-15T00:00:00Z", "source": {}, "artifacts": []}
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(STUB_NAME, json.dumps(manifest))
            zf.writestr("payload/home/sneaky.txt", "boo")
            zf.writestr(MANIFEST_NAME, json.dumps(manifest))
        with BundleReader(z) as reader:
            assert any("not in manifest" in p for p in reader.verify_structure())

    def test_symlink_member(self, tmp_path):
        z = tmp_path / "sym.hermespack"
        manifest = {"schema_version": 1, "min_reader_tool_version": "1.0.0",
                    "created_by_tool_version": "1.0.0",
                    "created_at": "2026-08-15T00:00:00Z", "source": {},
                    "artifacts": [{"id": "x@", "kind": "unrecognized", "files": [
                        {"member": "payload/home/link", "home_rel": "link", "size": 10,
                         "sha256": "", "mode": 420, "mtime": 0.0}]}]}
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(STUB_NAME, json.dumps(manifest))
            zinfo = zipfile.ZipInfo("payload/home/link")
            zinfo.external_attr = (0o120777 << 16)
            zf.writestr(zinfo, "/etc/passwd")
            zf.writestr(MANIFEST_NAME, json.dumps(manifest))
        with BundleReader(z) as reader:
            assert any("symlink" in p for p in reader.verify_structure())

    def test_schema_from_the_future(self, tmp_path):
        z = tmp_path / "future.hermespack"
        manifest = {"schema_version": 99, "min_reader_tool_version": "99.0.0",
                    "created_by_tool_version": "99.0.0",
                    "created_at": "2126-01-01T00:00:00Z", "source": {}}
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr(STUB_NAME, json.dumps(manifest))
            zf.writestr(MANIFEST_NAME, json.dumps(manifest))
        with pytest.raises(Refusal) as exc_info:
            BundleReader(z).open()
        assert exc_info.value.code == "TAL-302"

    def test_bomb_guard(self, tmp_path):
        """A member whose decompressed size exceeds its manifest declaration is refused."""
        z = tmp_path / "bomb.hermespack"
        big = b"\x00" * (1024 * 1024)
        manifest = {"schema_version": 1, "min_reader_tool_version": "1.0.0",
                    "created_by_tool_version": "1.0.0",
                    "created_at": "2026-08-15T00:00:00Z", "source": {},
                    "artifacts": [{"id": "x@", "kind": "unrecognized", "files": [
                        {"member": "payload/home/small.bin", "home_rel": "small.bin",
                         "size": 10, "sha256": "", "mode": 420, "mtime": 0.0}]}]}
        with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(STUB_NAME, json.dumps(manifest))
            zf.writestr("payload/home/small.bin", big)  # lies: manifest says 10 bytes
            zf.writestr(MANIFEST_NAME, json.dumps(manifest))
        with BundleReader(z) as reader:
            with pytest.raises(Refusal) as exc_info:
                reader.extract_member("payload/home/small.bin", tmp_path / "out.bin")
            assert "bomb" in str(exc_info.value.message)
            assert not (tmp_path / "out.bin").exists()


@pytest.mark.skipif(not vault_mod.crypto_available(), reason="cryptography missing")
class TestVault:
    def test_vault_round_trip(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        result = scan(inst.home)
        out = tmp_path / "v.hermespack"
        pres = pack(result, out, PackOptions(vault_passphrase="correct horse",
                                             hold_secrets=False))
        assert pres.manifest["vault"]["present"]
        with zipfile.ZipFile(out) as zf:
            for name in zf.namelist():
                blob = zf.read(name)
                assert b"sk-or-fake-1234567890" not in blob, name
            vr = vault_mod.open_vault(pres.manifest, "correct horse")
            envs = [m for m in vr.members() if m["home_rel"] == ".env"]
            assert envs
            dest = tmp_path / "restored.env"
            vr.decrypt_member(zf, envs[0], dest)
            text = dest.read_text()
            assert "OPENROUTER_API_KEY=sk-or-fake-1234567890" in text
            import stat

            assert stat.S_IMODE(dest.stat().st_mode) == 0o600

    def test_wrong_passphrase_clean_error(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        result = scan(inst.home)
        out = tmp_path / "v.hermespack"
        pres = pack(result, out, PackOptions(vault_passphrase="right"))
        with pytest.raises(Refusal) as exc_info:
            vault_mod.open_vault(pres.manifest, "wrong")
        assert exc_info.value.code == "TAL-305"

    def test_empty_passphrase_refused(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        result = scan(inst.home)
        with pytest.raises(Refusal) as exc_info:
            pack(result, tmp_path / "x.hermespack", PackOptions(vault_passphrase=""))
        assert exc_info.value.code == "TAL-206"

    def test_tampered_vault_section(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        result = scan(inst.home)
        pres = pack(result, tmp_path / "v.hermespack", PackOptions(vault_passphrase="p"))
        tampered = json.loads(json.dumps(pres.manifest))
        tampered["vault"]["members"][0]["home_rel"] = "evil"
        with pytest.raises(Refusal):
            vault_mod.open_vault(tampered, "p")


class TestRefusals:
    def test_update_in_progress_refuses_pack(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        (inst.home / ".hermes-update-in-progress").write_text("")
        result = scan(inst.home)
        with pytest.raises(Refusal) as exc_info:
            pack(result, tmp_path / "x.hermespack")
        assert exc_info.value.code == "TAL-102"

    def test_require_quiesced(self, tmp_path):
        import os

        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        (inst.home / "gateway.pid").write_text(str(os.getpid()))
        result = scan(inst.home)
        with pytest.raises(Refusal) as exc_info:
            pack(result, tmp_path / "x.hermespack",
                 PackOptions(require_quiesced=True))
        assert exc_info.value.code == "TAL-401"

    def test_coupling_violation_refuses(self, tmp_path):
        inst = build_fake_install(tmp_path / "h", FakeInstallSpec())
        result = scan(inst.home)
        sel = Selection(exclude={"scripts-dir@"})
        with pytest.raises(Refusal) as exc_info:
            pack(result, tmp_path / "x.hermespack", PackOptions(selection=sel))
        assert exc_info.value.code == "TAL-208"
        assert "job-script" in str(exc_info.value.message)
