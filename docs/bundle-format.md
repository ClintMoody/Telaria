# The `.hermespack` bundle format (schema 1)

One zip file (zip64 always enabled), fully self-describing.

## Layout

```
manifest.stub.json         FIRST member, stored uncompressed — the eternal header
payload/home/<path>        install files, POSIX separators, relative to the Hermes ROOT
                           (profiles under payload/home/profiles/<name>/…)
payload/external/home/<p>  files that live outside HERMES_HOME, home-relative
                           (memory-provider state; allowlisted on restore)
meta/provenance.json       per-skill provenance tags + hash semantics
meta/machine_refs.json     machine-specific references found inside carried data
meta/touchpoints.json      the discovery ledger
meta/checkout.json/.patch  code-checkout state and the user's local patch
vault/<seq>                encrypted members when the vault is used
manifest.json              LAST member, stored uncompressed — the complete manifest
```

## The eternal header (frozen forever)

Whatever schema changes come, these five keys keep their meaning in every future
version, so any tool vintage can identify any bundle and print the right message:

```json
{
  "schema_version": 1,
  "min_reader_tool_version": "1.0.0",
  "created_by_tool_version": "1.0.0",
  "created_at": "2026-08-15T18:42:03Z",
  "source": { "hermes_version": "0.20.1", "os": "linux", "hostname": "atlas", ... }
}
```

## The manifest body (schema 1, additive-only)

- `bundle_id` — 16-hex id; binds vault AAD.
- `intent` — replace | clone.
- `profiles`, `counts`, `bytes`.
- `artifacts[]` — the typed inventory: id, kind, family, portability class, secrecy,
  machine_bound, default, selection state, provenance, dependencies, and `files[]`
  where each file carries `member`, `home_rel`, `size`, **`sha256`**, `mode`, `mtime`.
  That table IS the integrity scheme.
- `selection` — the pack-time selection record (apply may narrow, never widen).
- `rewrite_anchors` — source home / hermes-home / user / separator, for target-side
  path translation.
- `predictive` — pack-time per-OS verdicts (e.g. Windows-illegal names).
- `checklist.items[]` — credential NAMES with where-used. Never values.
- `unrecognized[]` — members that passed the pack-time content gates; applying them is
  a disclosed consent.
- `vault` — when present: scrypt parameters, cipher, per-member plain hash/size, and
  an HMAC over the section.
- `hash_semantics` — the separator/collation the skill dir-hashes were computed under
  (cross-OS rebaselining needs it).
- `capture_mode` — quiesced | live.

## Reading rules (what every reader enforces)

- Refuse schemas newer than the reader (exit 9, "upgrade talaria"); read every schema
  ≤ its own forever (golden-bundle tests).
- Ignore unknown manifest keys; treat unknown artifact kinds as opaque, placed only
  with explicit consent.
- The hardening sweep before any extraction: manifest↔zip bijection, member-name
  legality (no absolute/`..`/backslash/drive/reserved names), duplicate +
  casefold/NFC-NFD collision detection, symlink-member rejection, per-member
  decompressed-size caps, manifest size/entry caps before parse.
- Modes are clamped to {0600, 0644, 0700, 0755}; credential files forced 0600.

## Vault member framing

```
"TLV1" · 8-byte nonce_prefix · repeat: [u32 ct_len][AES-256-GCM ciphertext‖tag]
nonce  = nonce_prefix ‖ BE32(chunk_index)          (8 MiB plaintext chunks)
AAD    = bundle_id | schema | home_rel | chunk_index | last_flag
```

Key: scrypt(N=2¹⁷, r=8, p=1, 16-byte salt, dklen=64) → HKDF-SHA256 labels
`talaria-enc` / `talaria-mac`. The mac key HMACs the manifest's vault section
(anti-transplant). Truncation is detected by the last-flag AAD.

## Related formats

A zip whose members match upstream's backup markers (`config.yaml`, `.env`,
`state.db`, with archive-prefix tolerance) is recognized as a plain `hermes backup`
archive and routed to upstream's `hermes import` — Talaria neither mangles nor
impersonates it.
