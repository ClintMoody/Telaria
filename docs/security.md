# Talaria Security Model

## What a bundle is

**A `.hermespack` bundle is software.** It contains skills, scripts, hooks, plugins,
and MCP command lines that Hermes on the new machine will eventually *run*. Apply only
bundles you created yourself or trust completely — the same rule as any installer.
Talaria shows an executable-content summary at preflight and requires consent, but
consent is not a sandbox.

**Checksums are integrity, not authenticity.** Every payload file carries a SHA-256
and the whole bundle self-verifies — that proves the file wasn't corrupted in transit,
not who made it. v1 bundles are not signed.

## Where your secrets are

- **By default, credential material never travels.** `.env` values, `auth.json`, OAuth
  token stores, webhook secrets, pairing stores — excluded from the payload; you get a
  names-only checklist. The tests plant canary values and assert zero members contain
  them.
- **Conversation history is sensitive content and DOES travel by default** — your
  state.db contains everything you ever typed to your agent, possibly including
  secrets you pasted into chats. Treat the bundle like a private notebook. The
  "lock everything" vault option encrypts this content too.
- **The vault** (opt-in): scrypt (N=2¹⁷, r=8, p=1, 16-byte random salt) → HKDF-SHA256
  subkeys → AES-256-GCM per member with fresh 96-bit nonces; AAD binds bundle id,
  member path, and chunk index (no member transplants); an HMAC covers the vault
  manifest section. Both primitives come from the `cryptography` package — without it
  Talaria refuses vault mode honestly rather than substituting weaker crypto. An empty
  passphrase is refused. The passphrase is never accepted via argv, never logged, and
  never stored.
- **Reports and checklists are redacted by default** — home paths and usernames
  masked, secret-shaped strings scrubbed at the data-model layer before any renderer,
  plus a belt pass over the final artifact. `--no-redact` exists for local use.
  All outputs are written mode 0600.

## The apply-side trust boundary

A hostile bundle must not escape the Hermes home. The single reader path enforces:
manifest↔zip bijection; member-name legality (absolute paths, `..`, backslashes, drive
letters, reserved device names rejected); duplicate and case-fold/NFC-NFD collision
detection; symlink members rejected; per-member decompressed-size caps against the
manifest (bomb guard); mode-bit clamping with credential files forced 0600. Files
restoring outside HERMES_HOME (`payload/external/`) are limited to a small allowlist
of memory-provider paths; everything else needs per-path consent, and a hard
never-list (`~/.ssh`, `~/.gnupg`, `~/.aws`, shell rc files, autostart, anything
outside home) is refused even with consent.

The machine-bound exclusion registry filters **both** capture and apply — a bundle
carrying `gateway_state.json` (hand-built or from an older tool) still can't plant it.

## The agent is not trusted

The Deep-Scan skill asks your own Hermes to report what it touches. That report is
untrusted input: exactly one nonce-named file is read (no globbing), capped at 1 MiB,
schema-validated, nonce-checked; every string is scrubbed with the secret patterns;
each path is lstat-probed only; the never-registry gates candidates *before* they are
offered; and nothing in the report can expand the capture set, alter exclusions, or
mark anything safe — only you can, by opting in. Fabricated paths land in a clearly
labeled "agent said, unverified" appendix.

## The GUI

Localhost only (literal 127.0.0.1 bind, random port). The launch URL carries a
single-use bootstrap token exchanged for a 256-bit session token sent as a request
header and compared constant-time; the Host and Origin headers are validated (DNS
rebinding, CSRF); responses carry `X-Frame-Options: DENY`, `nosniff`,
`Referrer-Policy: no-referrer`, and a restrictive CSP; secrets travel only in POST
bodies and are never echoed back or logged; one session may drive a migration; the
server shuts down when done or idle.

## Reporting a vulnerability

Open a GitHub issue with the `security` label, or if the issue is sensitive, contact
the maintainer privately. Talaria is a community tool; response is best-effort.
