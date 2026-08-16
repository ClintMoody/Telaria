"""Encrypted vault: scrypt → HKDF subkeys → AES-256-GCM streaming members (D12, R-SEC-04).

`cryptography` supplies BOTH Scrypt and AESGCM — one probe, one honest refusal (never a
fallback cipher, never home-rolled crypto). Member framing (`vault/<seq>`):

    magic  b"TLV1"
    nonce_prefix  8 random bytes
    chunks: [u32 big-endian ciphertext length][ciphertext || 16-byte GCM tag]
        nonce = nonce_prefix || BE32(chunk_index)
        AAD   = bundle_id|schema|home_rel|chunk_index|last_flag

The manifest's vault section records per-member plain hash/size and an HMAC-SHA256 over
its canonicalized JSON (anti-transplant).
"""

from __future__ import annotations

import hashlib
import hmac as hmac_mod
import json
import os
import secrets
import struct
import zipfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from talaria.errors import Refusal, TalariaError

MAGIC = b"TLV1"
CHUNK_PLAIN = 8 * 1024 * 1024
SCRYPT_N = 2 ** 17
SCRYPT_R = 8
SCRYPT_P = 1
SALT_LEN = 16
MEMBER_CEILING = 2 ** 20   # max vault members asserted


def crypto_available() -> bool:
    # BaseException on purpose: a broken install (e.g. missing _cffi_backend under a
    # Rust-backed build) raises pyo3 PanicException, which does NOT derive from
    # Exception on all versions. The honest-refusal path must survive that too.
    try:
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt  # noqa: F401
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # noqa: F401
        return True
    except BaseException:
        return False


def require_crypto() -> None:
    if not crypto_available():
        raise Refusal(
            "TAL-205",
            "vault mode needs the 'cryptography' package and it is not installed",
            fix="install it with `pip install cryptography`, or use checklist mode — "
                "your keys then move by hand, never in the bundle")


def _derive_keys(passphrase: str, salt: bytes) -> Tuple[bytes, bytes]:
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    if not passphrase:
        raise Refusal("TAL-206", "an empty vault passphrase is refused")
    master = Scrypt(salt=salt, length=64, n=SCRYPT_N, r=SCRYPT_R,
                    p=SCRYPT_P).derive(passphrase.encode("utf-8"))
    enc_key = _hkdf_sha256(master, b"talaria-enc", 32)
    mac_key = _hkdf_sha256(master, b"talaria-mac", 32)
    return enc_key, mac_key


def _hkdf_sha256(key_material: bytes, info: bytes, length: int) -> bytes:
    prk = hmac_mod.new(b"\x00" * 32, key_material, hashlib.sha256).digest()
    out = b""
    block = b""
    counter = 1
    while len(out) < length:
        block = hmac_mod.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        out += block
        counter += 1
    return out[:length]


def _aad(bundle_id: str, schema: int, home_rel: str, chunk_index: int, last: bool) -> bytes:
    return f"{bundle_id}|{schema}|{home_rel}|{chunk_index}|{int(last)}".encode("utf-8")


def write_vault_members(zf: zipfile.ZipFile, entries, passphrase: str, bundle_id: str,
                        schema: int, scope: str,
                        progress: Optional[Callable[[int], None]] = None
                        ) -> Tuple[dict, int]:
    """Encrypt ``entries`` into vault/<seq>; returns (vault manifest section, bytes done)."""
    require_crypto()
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if len(entries) > MEMBER_CEILING:
        raise TalariaError("TAL-205", "vault member ceiling exceeded")
    salt = secrets.token_bytes(SALT_LEN)
    enc_key, mac_key = _derive_keys(passphrase, salt)
    aead = AESGCM(enc_key)

    members: List[dict] = []
    done = 0
    for seq, entry in enumerate(entries):
        member_name = f"vault/{seq:06d}"
        nonce_prefix = secrets.token_bytes(8)
        plain_hasher = hashlib.sha256()
        plain_size = 0
        zinfo = zipfile.ZipInfo(member_name)
        zinfo.compress_type = zipfile.ZIP_STORED  # ciphertext doesn't compress
        with open(entry.source, "rb") as src, zf.open(zinfo, "w") as out:
            out.write(MAGIC)
            out.write(nonce_prefix)
            chunk_index = 0
            chunk = src.read(CHUNK_PLAIN)
            while True:
                nxt = src.read(CHUNK_PLAIN)
                last = not nxt
                plain_hasher.update(chunk)
                plain_size += len(chunk)
                nonce = nonce_prefix + struct.pack(">I", chunk_index)
                ct = aead.encrypt(nonce, chunk,
                                  _aad(bundle_id, schema, entry.home_rel, chunk_index,
                                       last))
                out.write(struct.pack(">I", len(ct)))
                out.write(ct)
                done += len(chunk)
                if progress is not None:
                    progress(done)
                if last:
                    break
                chunk = nxt
                chunk_index += 1
        members.append({
            "member": member_name, "home_rel": entry.home_rel,
            "root_rel": entry.root_rel, "profile": entry.artifact.profile,
            "plain_sha256": plain_hasher.hexdigest(), "plain_size": plain_size,
            "mode": entry.mode, "artifact_id": entry.artifact.id,
            "secrecy": entry.artifact.secrecy,
        })

    section = {
        "present": True, "scope": scope,
        "kdf": {"name": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
                "salt": salt.hex(), "dklen": 64},
        "cipher": "aes-256-gcm", "chunk_bytes": CHUNK_PLAIN,
        "members": members,
    }
    section["mac"] = _section_mac(section, mac_key)
    return section, done


def _section_mac(section: dict, mac_key: bytes) -> str:
    canon = json.dumps({k: v for k, v in section.items() if k != "mac"},
                       sort_keys=True, separators=(",", ":"))
    return hmac_mod.new(mac_key, canon.encode("utf-8"), hashlib.sha256).hexdigest()


def open_vault(manifest: dict, passphrase: str) -> "VaultReader":
    require_crypto()
    section = manifest.get("vault") or {}
    if not section.get("present"):
        raise TalariaError("TAL-305", "this bundle has no vault")
    kdf = section.get("kdf", {})
    salt = bytes.fromhex(kdf.get("salt", ""))
    enc_key, mac_key = _derive_keys(passphrase, salt)
    expected = section.get("mac", "")
    actual = _section_mac(section, mac_key)
    if not hmac_mod.compare_digest(expected, actual):
        raise Refusal("TAL-305", "wrong vault passphrase (or a tampered vault section)",
                      fix="nothing was written; check the passphrase and try again")
    return VaultReader(section, enc_key, manifest.get("bundle_id", ""),
                       int(manifest.get("schema_version", 1)))


class VaultReader:
    def __init__(self, section: dict, enc_key: bytes, bundle_id: str, schema: int):
        self.section = section
        self.bundle_id = bundle_id
        self.schema = schema
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        self.aead = AESGCM(enc_key)

    def members(self) -> List[dict]:
        return list(self.section.get("members", []))

    def decrypt_member(self, zf: zipfile.ZipFile, record: dict, dest: Path) -> str:
        """Decrypt one vault member to ``dest`` (0600); returns plain sha256."""
        import struct as _struct

        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        hasher = hashlib.sha256()
        fd = os.open(dest, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        try:
            with zf.open(record["member"]) as src, os.fdopen(fd, "wb") as out:
                if src.read(4) != MAGIC:
                    raise Refusal("TAL-301", f"{record['member']}: bad vault magic")
                nonce_prefix = src.read(8)
                chunk_index = 0
                header = src.read(4)
                saw_last = False
                while header:
                    (ct_len,) = _struct.unpack(">I", header)
                    ct = src.read(ct_len)
                    if len(ct) != ct_len:
                        raise Refusal("TAL-301",
                                      f"{record['member']}: truncated vault frame")
                    header = src.read(4)   # lookahead: empty => this frame is the last
                    last = not header
                    nonce = nonce_prefix + _struct.pack(">I", chunk_index)
                    try:
                        plain = self.aead.decrypt(
                            nonce, ct, _aad(self.bundle_id, self.schema,
                                            record["home_rel"], chunk_index, last))
                    except Exception:
                        raise Refusal(
                            "TAL-305",
                            f"{record['member']}: decryption failed — wrong passphrase, "
                            "a truncated member, or tampering")
                    hasher.update(plain)
                    out.write(plain)
                    saw_last = last
                    chunk_index += 1
                if not saw_last:
                    raise Refusal("TAL-301",
                                  f"{record['member']}: no terminal frame — truncated")
        except BaseException:
            try:
                dest.unlink()
            except OSError:
                pass
            raise
        digest = hasher.hexdigest()
        if record.get("plain_sha256") and digest != record["plain_sha256"]:
            dest.unlink(missing_ok=True)
            raise Refusal("TAL-301",
                          f"{record['member']}: decrypted content fails its checksum")
        return digest
