"""Bundle format: manifest model, hardened reader, foreign-zip detection (ARCH §3).

One code path (BundleReader) serves STAGE, `inspect`, and salvage (R-BND-07). Layout:

    manifest.stub.json   FIRST member, STORED — the eternal header alone, known before
                         payload streaming begins (D31: the stub satisfies "cheap reads
                         from the front" while single-pass hashing fills the full manifest)
    payload/home/...     POSIX-separated, root-relative (profiles under profiles/<n>/)
    payload/external/home/...  home-relative external state
    meta/*.json          provenance, deps, touchpoints, capture report, checkout patch
    vault/<seq>          encrypted members when the vault is present
    manifest.json        LAST member, STORED — the complete schema-1 manifest

Readers use the central directory (manifest.json); stream/salvage tooling can read the
stub off the front of a truncated file.
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, IO, Iterator, List, Optional, Set, Tuple

from talaria import BUNDLE_FORMAT_VERSION, __version__
from talaria.errors import EXIT_BUNDLE_UNREADABLE, Refusal, TalariaError
from talaria.hashes import file_sha256
from talaria.platform.paths import casefold_key, find_collisions, member_name_problems

MANIFEST_NAME = "manifest.json"
STUB_NAME = "manifest.stub.json"
PAYLOAD_HOME = "payload/home/"
PAYLOAD_EXTERNAL = "payload/external/home/"
META_PREFIX = "meta/"
VAULT_PREFIX = "vault/"

MANIFEST_MAX_BYTES = 64 * 1024 * 1024
MANIFEST_MAX_ENTRIES = 2 ** 20
MEMBER_SIZE_SLACK = 4096
MODE_CLAMP = (0o600, 0o644, 0o700, 0o755)

#: Upstream `hermes backup` validation markers (backup.py:811).
HERMES_BACKUP_MARKERS = ("config.yaml", ".env", "state.db")


@dataclass
class EternalHeader:
    """Frozen forever across schema majors (R-BND-02)."""

    schema_version: int
    min_reader_tool_version: str
    created_by_tool_version: str
    created_at: str
    source: dict

    def to_json(self) -> dict:
        return {"schema_version": self.schema_version,
                "min_reader_tool_version": self.min_reader_tool_version,
                "created_by_tool_version": self.created_by_tool_version,
                "created_at": self.created_at, "source": self.source}

    @classmethod
    def from_json(cls, data: dict) -> "EternalHeader":
        return cls(schema_version=int(data.get("schema_version", 0)),
                   min_reader_tool_version=str(data.get("min_reader_tool_version", "")),
                   created_by_tool_version=str(data.get("created_by_tool_version", "")),
                   created_at=str(data.get("created_at", "")),
                   source=data.get("source", {}) or {})


class BundleKind:
    TALARIA = "talaria-bundle"
    HERMES_BACKUP = "hermes-backup-zip"
    FOREIGN_ZIP = "foreign-zip"
    NOT_ZIP = "not-zip"


def detect_kind(path: Path) -> Tuple[str, str]:
    """(kind, detail) — talaria bundle, plain `hermes backup` zip, foreign, or not a zip."""
    path = Path(path)
    if not zipfile.is_zipfile(path):
        return BundleKind.NOT_ZIP, "not a zip file"
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if MANIFEST_NAME in names or STUB_NAME in names:
                return BundleKind.TALARIA, "talaria manifest present"
            prefix = _common_prefix(names)
            stripped = [n[len(prefix):] for n in names]
            hits = sum(1 for marker in HERMES_BACKUP_MARKERS if marker in stripped)
            if hits >= 2:
                detail = "matches hermes backup validation markers"
                if prefix:
                    detail += f" (archive prefix {prefix!r})"
                return BundleKind.HERMES_BACKUP, detail
            return BundleKind.FOREIGN_ZIP, "zip without talaria or hermes-backup markers"
    except (OSError, zipfile.BadZipFile) as exc:
        return BundleKind.NOT_ZIP, f"unreadable zip: {exc}"


def _common_prefix(names: List[str]) -> str:
    """Single-directory archive prefix, mirroring backup.py:828-849 tolerance."""
    tops = {n.split("/", 1)[0] for n in names if "/" in n}
    only_dirs = all("/" in n for n in names)
    if len(tops) == 1 and only_dirs:
        return next(iter(tops)) + "/"
    return ""


@dataclass
class MemberRecord:
    member: str
    home_rel: str
    size: int
    sha256: str
    mode: int
    mtime: float
    artifact_id: str = ""

    def to_json(self) -> dict:
        return {"member": self.member, "home_rel": self.home_rel, "size": self.size,
                "sha256": self.sha256, "mode": self.mode, "mtime": self.mtime}


class BundleReader:
    """Hardened reader — the single code path for stage/inspect/salvage (R-BND-07)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.zf: Optional[zipfile.ZipFile] = None
        self.manifest: dict = {}
        self.header: Optional[EternalHeader] = None
        self.members: Dict[str, MemberRecord] = {}
        self.problems: List[str] = []

    # -- lifecycle
    def __enter__(self) -> "BundleReader":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def open(self) -> "BundleReader":
        kind, detail = detect_kind(self.path)
        if kind == BundleKind.NOT_ZIP:
            raise Refusal("TAL-301", f"{self.path.name}: {detail}",
                          exit_code=EXIT_BUNDLE_UNREADABLE)
        if kind == BundleKind.HERMES_BACKUP:
            raise Refusal("TAL-304",
                          f"{self.path.name} is a plain `hermes backup` archive, not a "
                          f"Talaria bundle ({detail})",
                          fix="restore it with `hermes import` on the target machine")
        if kind == BundleKind.FOREIGN_ZIP:
            raise Refusal("TAL-301", f"{self.path.name}: {detail}",
                          exit_code=EXIT_BUNDLE_UNREADABLE)
        self.zf = zipfile.ZipFile(self.path)
        self._load_manifest()
        return self

    def close(self) -> None:
        if self.zf is not None:
            self.zf.close()
            self.zf = None

    # -- manifest
    def _load_manifest(self) -> None:
        assert self.zf is not None
        names = self.zf.namelist()
        source = MANIFEST_NAME if MANIFEST_NAME in names else STUB_NAME
        info = self.zf.getinfo(source)
        if info.file_size > MANIFEST_MAX_BYTES:
            raise Refusal("TAL-301", "manifest exceeds the size cap",
                          exit_code=EXIT_BUNDLE_UNREADABLE)
        raw = self.zf.read(source)
        try:
            self.manifest = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise Refusal("TAL-301", f"manifest is not valid JSON: {exc}",
                          exit_code=EXIT_BUNDLE_UNREADABLE)
        self.header = EternalHeader.from_json(self.manifest)
        if self.header.schema_version > BUNDLE_FORMAT_VERSION:
            raise Refusal(
                "TAL-302",
                f"bundle schema {self.header.schema_version} is newer than this tool "
                f"(reads ≤ {BUNDLE_FORMAT_VERSION}); it was created by talaria "
                f"{self.header.created_by_tool_version}",
                fix="upgrade talaria on this machine, then retry",
                exit_code=EXIT_BUNDLE_UNREADABLE)
        entries = 0
        for art in self.manifest.get("artifacts", []):
            for f in art.get("files", []):
                entries += 1
                if entries > MANIFEST_MAX_ENTRIES:
                    raise Refusal("TAL-301", "manifest entry count exceeds the cap",
                                  exit_code=EXIT_BUNDLE_UNREADABLE)
                rec = MemberRecord(
                    member=f.get("member", ""), home_rel=f.get("home_rel", ""),
                    size=int(f.get("size", 0)), sha256=f.get("sha256", ""),
                    mode=int(f.get("mode", 0o644)), mtime=float(f.get("mtime", 0.0)),
                    artifact_id=art.get("id", ""))
                self.members[rec.member] = rec

    # -- hardening
    def verify_structure(self) -> List[str]:
        """The full R-BND-07 hardening sweep; returns problem strings (empty = clean)."""
        assert self.zf is not None
        problems: List[str] = []
        names = self.zf.namelist()
        payload_names = [n for n in names if n.startswith(("payload/", "vault/"))]

        seen: Set[str] = set()
        for name in names:
            if name in seen:
                problems.append(f"duplicate member: {name}")
            seen.add(name)

        # Name legality over EVERY member and every manifest-declared member — a hostile
        # name outside payload/ must be flagged for its name, not only as a bookkeeping
        # mismatch (A9).
        allowed_top = {MANIFEST_NAME, STUB_NAME}
        for name in set(names) | set(self.members):
            for issue in member_name_problems(name):
                problems.append(f"{name}: {issue}")
            if name not in allowed_top and not name.startswith(
                    ("payload/", "meta/", "vault/")):
                problems.append(f"unexpected member outside known zones: {name}")

        for group in find_collisions(payload_names):
            problems.append("case/normalization collision: " + " <-> ".join(group))

        manifest_set = set(self.members)
        zip_payload = {n for n in payload_names}
        for missing in sorted(manifest_set - zip_payload):
            problems.append(f"manifest lists absent member: {missing}")
        vault_members = {v.get("member") for v in
                         (self.manifest.get("vault", {}) or {}).get("members", [])}
        for stray in sorted(zip_payload - manifest_set):
            if stray in vault_members:
                continue
            problems.append(f"zip member not in manifest: {stray}")

        # Vault members carry a manifest-declared destination (`root_rel`) that the
        # decrypt path — not the zip name — writes to. It is untrusted (a hostile author
        # owns the passphrase they share), so its legality is checked HERE, up front, the
        # same as any payload name; the applier double-checks containment at stage time.
        for vault_member in (self.manifest.get("vault", {}) or {}).get("members", []):
            root_rel = vault_member.get("root_rel") or vault_member.get("home_rel", "")
            for issue in member_name_problems("payload/home/" + str(root_rel)):
                problems.append(f"vault member root_rel {root_rel!r}: {issue}")

        for name in payload_names:
            info = self.zf.getinfo(name)
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                problems.append(f"symlink member rejected: {name}")
            rec = self.members.get(name)
            if rec and info.file_size > rec.size + MEMBER_SIZE_SLACK:
                problems.append(
                    f"{name}: zip size {info.file_size} exceeds manifest size {rec.size}")
        self.problems = problems
        return problems

    # -- reads
    def read_meta(self, name: str) -> Optional[bytes]:
        assert self.zf is not None
        full = META_PREFIX + name if not name.startswith(META_PREFIX) else name
        try:
            return self.zf.read(full)
        except KeyError:
            return None

    def iter_payload(self) -> Iterator[MemberRecord]:
        return iter(sorted(self.members.values(), key=lambda r: r.member))

    def extract_member(self, member: str, dest: Path, verify: bool = True) -> str:
        """Stream one member to ``dest`` (containment-checked); returns its sha256."""
        assert self.zf is not None
        import hashlib

        rec = self.members.get(member)
        problems = member_name_problems(member)
        if problems:
            raise Refusal("TAL-303", f"hostile member {member}: {'; '.join(problems)}")
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        hasher = hashlib.sha256()
        expected = rec.size if rec else None
        written = 0
        with self.zf.open(member) as src, open(dest, "wb") as out:
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if expected is not None and written > expected + MEMBER_SIZE_SLACK:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise Refusal("TAL-303",
                                  f"{member}: decompressed past declared size "
                                  f"({written} > {expected}) — refusing (bomb guard)")
                hasher.update(chunk)
                out.write(chunk)
        digest = hasher.hexdigest()
        if verify and rec and rec.sha256 and digest != rec.sha256:
            dest.unlink(missing_ok=True)
            raise Refusal("TAL-301", f"{member}: checksum mismatch against manifest",
                          exit_code=EXIT_BUNDLE_UNREADABLE)
        return digest

    def salvage_report(self) -> Dict[str, str]:
        """Per-member verdicts for `inspect --salvage` (R-BND-06): ok|corrupt|missing."""
        assert self.zf is not None
        import hashlib

        out: Dict[str, str] = {}
        for member, rec in sorted(self.members.items()):
            try:
                hasher = hashlib.sha256()
                with self.zf.open(member) as src:
                    while True:
                        chunk = src.read(1024 * 1024)
                        if not chunk:
                            break
                        hasher.update(chunk)
                if rec.sha256 and hasher.hexdigest() != rec.sha256:
                    out[member] = "corrupt (checksum mismatch)"
                else:
                    out[member] = "ok"
            except KeyError:
                out[member] = "missing from zip"
            except (OSError, zipfile.BadZipFile) as exc:
                out[member] = f"unreadable ({exc})"
        return out


def clamp_mode(mode: int, is_credential: bool) -> int:
    """Clamp a manifest mode to the safe set; credentials forced 0600 (R-BND-07)."""
    if is_credential:
        return 0o600
    mode = mode & 0o777
    if mode & 0o111:
        return 0o700 if not (mode & 0o044) else 0o755
    return 0o600 if not (mode & 0o044) else 0o644
