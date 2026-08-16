# Subsystem Report: Installation & Update Mechanics

Repo: NousResearch/hermes-agent @ v0.20.1 (`hermes_cli/__init__.py:17`, `pyproject.toml:3`).

## 0. TL;DR — what "a Hermes install" physically is

Hermes is **not** a pip package. It is a **git checkout + a venv inside that checkout + shell
shims + a separate data directory**. `setup.py` blocks wheel/sdist builds outside Nix
(`setup.py:32-74`): "pip/PyPI and Homebrew are no longer supported distribution methods."

| Concept | Var | POSIX default | Windows default |
|---|---|---|---|
| Data root | `$HERMES_HOME` | `~/.hermes` | `%LOCALAPPDATA%\hermes` |
| Code root | `$HERMES_INSTALL_DIR` | `$HERMES_HOME/hermes-agent` | `%LOCALAPPDATA%\hermes\hermes-agent` |

Resolution: `hermes_constants.py:53-59, 114-136`; `scripts/install.sh:48, 413-454`;
`scripts/install.ps1:33-34`. **macOS uses `~/.hermes`, NOT ~/Library/Application Support**
(load-bearing invariant, `apps/bootstrap-installer/src-tauri/src/paths.rs:8-18`).

## 1. Install methods per platform

### POSIX — scripts/install.sh (3467 lines)

Pipeline (`:3421-3457`): detect_os → resolve_install_layout → install_uv → check_python/git/node →
install_system_packages → clone_repo → setup_venv → install_deps → node deps → browser/computer-use
drivers → setup_path → copy_config_templates → run_setup_wizard → maybe_start_gateway →
print_success → write_bootstrap_marker → `echo "git" > $INSTALL_DIR/.install_method`.

Layouts (`:413-454`): Termux → `$HERMES_HOME/hermes-agent` + `$PREFIX/bin`; Linux root (fresh) →
`/usr/local/lib/hermes-agent` (FHS) + `/usr/local/bin` (uv python redirected to
`/usr/local/share/uv/python` `:442-443`); default → `$HERMES_HOME/hermes-agent` + `~/.local/bin`.

Code lands via **git clone**, single-branch (`:1291-1295` — repo has thousands of branches).
Venv = `$INSTALL_DIR/venv`, uv-created, Python 3.11 pinned (`:1417-1459`). **setup_venv destroys
an existing venv** (`rm -rf venv`, :1441).

### Windows — scripts/install.ps1 (222 KB)

Params `:15-75`: -NoVenv -SkipSetup -Branch -Commit -Tag -ForceCommit -HermesHome -InstallDir
-Manifest -Stage -NonInteractive -Json -ShowResolvedPaths -Ensure -PostInstall -IncludeDesktop.
User-scoped, no admin. Provisions `%LOCALAPPDATA%\hermes\`: `hermes-agent\` (checkout),
`hermes-agent\venv\`, `hermes-agent\bin\` (hermes.exe copies), `bin\uv.exe`, `git\`
(PortableGit/MinGit ~45-57MB), `node\` (portable Node 22), `gateway-service\`, `bootstrap-cache\`.

**PATH design** (`:2699-2712`): expose ONLY launcher exes — `venv\Scripts` on PATH would hijack
`python` machine-wide (#83797). **Registry writes** (`:2732-2755`; enumerated in
`hermes_cli/uninstall.py:305-333`): `HKCU\Environment\Path` (+ git/node dirs),
`HKCU\Environment\HERMES_HOME`, `HKCU\Environment\HERMES_GIT_BASH_PATH` (:1459). Shortcuts only
with desktop build (`New-DesktopShortcuts` :3772-3830).

**8.3 short-path normalization** (`:106-350`): profiles with spaces/dots get 8.3 aliases that break
PS; TEMP/TMP/LOCALAPPDATA/APPDATA/USERPROFILE expanded via GetLongPathNameW.
`-ShowResolvedPaths` prints resolved paths as JSON without touching anything — use it.

### Termux

`is_termux()` (`install.sh:395`). No uv (`:556-561`); stdlib venv + pip. Tiered constrained
install (`:1608-1620`): `.[termux-all]` -c constraints-termux.txt → `.[termux]` → `.`.
psutil sdist patch (`scripts/install_psutil_android.py`, `:1596-1605`). Command dir `$PREFIX/bin`.
Node/browser skipped (`:2296-2302`).

### Docker

`/opt/hermes` code (root-owned, read-only), `/opt/hermes/.venv`, `HERMES_HOME=/opt/data` (VOLUME),
`/opt/hermes/bin/hermes` shim, `.install_method` = `docker` (Dockerfile:302), `.hermes_build_sha`
40-char commit (:333), `HERMES_DISABLE_LAZY_INSTALLS=1`, lazy target `/opt/data/lazy-packages`.
`docker-compose.yml:36-37` bind-mounts `~/.hermes:/opt/data`. `.dockerignore` excludes `.git` →
`hermes update` impossible in-container (`hermes_cli/config.py:602-640`).

### Nix

uv2nix sealed venv from uv.lock. Wrappers inject `HERMES_BUNDLED_SKILLS`, `HERMES_OPTIONAL_SKILLS`,
`HERMES_BUNDLED_PLUGINS`, `HERMES_BUNDLED_LOCALES`, `HERMES_OPTIONAL_MCPS`, `HERMES_WEB_DIST`,
`HERMES_TUI_DIR`, `HERMES_PYTHON`, `HERMES_NODE`, `HERMES_REVISION`
(`nix/hermes-agent.nix:186-203`). `HERMES_NIX_BUILD=1` bypasses the wheel guard. NixOS module sets
`HERMES_MANAGED` / `$HERMES_HOME/.managed`. **Nix installs are immutable — migrate $HERMES_HOME
only; user re-installs code via nix on target.**

## 2. uv — the blessed installer

- Hermes owns its own uv at `$HERMES_HOME/bin/uv[.exe]` (`install.sh:555-616`;
  `hermes_cli/managed_uv.py:53-73`). No `uv tool install`, no ~/.local/bin/uv.
- uv-managed Python: default store, FHS override, or runtime-repair generations at
  `<checkout>/.hermes-runtime/python` (`managed_uv.py:10-18, 44, 76-79`).
- **uv.lock = supply-chain verification** (`install.sh:1560-1571`): Tier 0 `uv sync --extra all
  --locked` (hash-verified) → Tier 1 `uv pip install -e '.[all]'` → Tier 2 minus broken extras →
  Tier 3 core. `--extra all`, never `--all-extras` (:1593-1600). `UV_NO_CONFIG=1` (:32);
  `UV_PYTHON` pinned to venv (:1450-1456). pyproject `exclude-newer = "14 days"` (:384).

## 3. Updates

### hermes update

Gates (`hermes_cli/main.py:9396-9421`): managed → error; docker/nix → refusal message.
Sequence (`hermes_cli/update_cmd.py`, 5942 lines): update lock → pre-update backup
(off/quick/full, :2617,2661) → pause Windows gateways (:3307) → discard lockfile churn (:3728) →
**autostash local changes** (:1137-1234, stash name `hermes-update-autostash-<ts>`) →
fetch/checkout/pull --ff-only (reset to origin on divergence) → restore-or-discard stash
(:1295,1422; non-interactive consults `updates.non_interactive_local_changes`; failed update
leaves stash + instructions :4413-4418) → clear __pycache__ + bytecode fingerprint (:4438-4443) →
refresh bootstrap-cache scripts (:3580) → `.update-incomplete` breadcrumb → update managed uv →
`uv pip install -e '.[all]'` with fallback ladder (:4453-4512) → refresh lazy features (§9) →
refresh memory provider deps (:1893) → validate imports (:225) → node deps if lockfile moved
(:2067) → resume gateways.

**Migration relevance:** restored checkouts with local edits get autostashed on next update —
commit intentional patches or expect a stash.

### Windows ZIP fallback

`_update_via_zip` (`update_cmd.py:776+`): downloads main.zip when git I/O broken; preserve set
(line 851) = `{"venv", "node_modules", ".git", ".env"}` — canonical "install state, not code".
Two-phase staged replace + rollback + disk-space precheck (need*1.2).

### Update lock

`$HERMES_HOME/.hermes-update-in-progress`, body `<pid>\n<started_at_unix>`; shared by Python
(`hermes_cli/update_lock.py`), Tauri (`update.rs:87-90,128` — max age 20min), Electron
(`update-marker.ts`), and `scripts/desktop-update/*`. Exit code 2 = venv held by another process.

### Recovery breadcrumbs

`$INSTALL_DIR/.update-incomplete`, `.lazy-refresh-incomplete`, `.bytecode-fingerprint`;
`_recover_from_interrupted_install()` (`main.py:8008+`) finishes interrupted jobs at launch.

## 4. Version & install detection — external-tool cheat sheet

### Version

| Signal | Path |
|---|---|
| `__version__` = "0.20.1" | `hermes_cli/__init__.py:17` (most reliable static read) |
| `__release_date__` = "2026.8.13" | `hermes_cli/__init__.py:18` |
| pyproject `[project].version` | kept in sync by `scripts/release.py:2188-2207` |
| Desktop `apps/desktop/package.json` 0.17.0 | independent version — don't conflate |
| `.hermes_build_sha` | Docker only (`hermes_cli/build_info.py:36-51`) |
| Live git | `git -C <root> rev-parse HEAD` |

`hermes --version` → "Hermes Agent v0.20.1 (2026.8.13)" (`hermes_cli/_startup_fast.py:186`);
`hermes dump` full summary. Parse `__version__` with `re.search(r'__version__\s*=\s*"([^"]+)"')`
(`scripts/release.py:2157`).

### Install method — reproduce `hermes_cli/config.py:412-513` exactly

```
1. <install tree>/.install_method              ← authoritative code-scoped stamp
2. $HERMES_HOME/.install_method                ← legacy; "docker" ignored unless containerized
3. HERMES_MANAGED env / $HERMES_HOME/.managed  → "nixos"
4. code path under /nix/store/                 → "nix"
5. <install tree>/.git dir                     → "git"
6. <install tree>/.git file "gitdir:"          → "git" (worktree)
7. else                                        → "unknown"
```

Code-scoped vs home-scoped rationale (`config.py:425-455`): a containerized gateway and host
install share one bind-mounted $HERMES_HOME. Contract test:
`tests/test_install_sh_install_method_stamp.py:29-40`.

### Install root (external walk)

1. `$HERMES_HOME` env — on Windows ALSO `HKCU\Environment\HERMES_HOME` (GUI apps miss post-login
   setx; `apps/desktop/electron/main.ts:597-610`)
2. Platform default `~/.hermes` / `%LOCALAPPDATA%\hermes`
3. Install root = `<home>/hermes-agent`; fallbacks `/usr/local/lib/hermes-agent`, `/opt/hermes`
4. Confirm: `hermes_cli/__init__.py` + `pyproject.toml` + `.git`

### Entry-point shims

POSIX: three generated bash shims (`hermes`, `hermes-agent`, `hermes-acp`) in `~/.local/bin` /
`/usr/local/bin` / `$PREFIX/bin` (`setup_path`, `install.sh:1714-1934`):
`exec "$INSTALL_DIR/venv/bin/python" "$INSTALL_DIR/hermes" "$@"` (with PYTHONPATH/PYTHONHOME
unset). Not uv console scripts (macOS lacks realpath, :1750-1753); `rm -f` before write (#21454
symlink stomp). Windows: `$InstallDir\bin\hermes.exe`, `hermes-acp.exe` copied from venv\Scripts
(:2711-2718). Console scripts declared `pyproject.toml:364-367`. Editable install →
`hermes_agent-0.20.1.dist-info` in venv site-packages with `__editable__` finder.

## 5. Desktop app (apps/desktop) — Electron

electron 40.10.2, React 19, Vite 8; product `Hermes`, appId com.nousresearch.hermes; protocol
`hermes://`; mac dmg+zip notarized, win nsis+msi per-user, linux AppImage+deb+rpm.

**Wraps the same CLI**: `ACTIVE_HERMES_ROOT = HERMES_HOME/hermes-agent` (`main.ts:634-640`);
spawns `hermes [--profile <name>] dashboard` (`main.ts:3853-3870`).

**Persisted state:** Electron userData (`%APPDATA%\Hermes` / `~/Library/Application Support/Hermes`
/ `~/.config/Hermes`; overridable `HERMES_DESKTOP_USER_DATA_DIR`, `main.ts:288`):
`connection.json` (:654), `desktop-installation.json` (installationId, 0600 — **machine identity,
regenerate on target**) (:655), `updates.json` (:656), `window-state.json` (:657 — display-geometry,
self-heals via onScreen()), `active-profile.json` (:664), `native-theme.json`,
`translucency.json`, `zoom-state.json`, `default-project-dir`, `backend-ready/`.
Under HERMES_HOME: `logs/desktop.log`, bootstrap marker, update marker.
**Migrate:** connection.json, active-profile.json, updates.json. **Don't:** installation id,
window geometry.

## 6. apps/bootstrap-installer — Tauri 2 GUI wrapper

Binary `Hermes-Setup[.exe]`. **Installs nothing itself** — drives install.ps1/install.sh
stage-by-stage via `-Manifest` / `-Stage NAME -NonInteractive -Json` (bootstrap.rs:1-14; 3
attempts/stage). **Stage manifest** (`install.sh:321-333`, protocol_version 1):
prerequisites, repository, venv, python-deps, node-deps, path, config, setup*, gateway*,
[desktop], complete (* = needs_user_input). Writes: logs, bootstrap-cache/install-<ref>.{ps1,sh}
(commit pins immutable-cached; branch pins refreshed), self-copy `$HERMES_HOME/hermes-setup[.exe]`,
update marker. PATH/shortcuts done by the scripts, not the binary.

## 7. optional-skills/migration — read in full

Only ONE migration exists: **OpenClaw → Hermes** (`openclaw-migration/SKILL.md` 299 lines +
`scripts/openclaw_to_hermes.py` 3286 lines; CLI `hermes claw migrate` in `hermes_cli/claw.py`).
**No Hermes→Hermes machine transfer exists — our tool fills a real gap.**

Architecture worth stealing:
- **26 migration categories** (`MIGRATION_OPTION_METADATA` :46+): soul, workspace-agents, memory,
  user-profile, messaging-settings, secret-settings, command-allowlist, skills, tts-assets,
  discord/slack/whatsapp/signal-settings, provider-keys, model-config, tts-config, shared-skills,
  daily-memory, archive, mcp-servers, plugins-config, cron-jobs, hooks-config, agent-config…
- **Presets**: `user-data` (no secrets) and `full` (+ secret-settings); --include/--exclude as
  advanced escape hatch (SKILL.md:202-225).
- **Stable status vocabulary** (:236-243): migrated/archived/skipped/conflict/error/planned +
  stable reason strings. `ItemResult{kind, source, destination, status, reason, details,
  sensitive}` (:247-255).
- **Output layout** (:849-854): `$HERMES_HOME/migration/openclaw/<ts>/{report.json, summary.md,
  MIGRATION_NOTES.md, archive/, backups/, overflow/}`.
- **Dry-run by default; --execute to write** (:3118). Conflict short-circuit for config.yaml
  writes (:857-862). Secret allowlist of 6 env vars, only with --migrate-secrets (:37-44).
  Skill conflict modes skip|overwrite|rename (:36). Char caps with overflow/ export (:30-31).
- 13 post-run reporting rules preventing over-claiming success (SKILL.md:184-201).

## 8. First-run onboarding

`agent/onboarding.py` writes only `config.yaml onboarding.seen.<flag>` markers (:216-248).
Real first-run writers: `copy_config_templates` (`install.sh:1937-2010`):
`mkdir -p $HERMES_HOME/{cron,sessions,logs,pairing,hooks,image_cache,audio_cache,memories,skills}`;
`.env` from example + chmod 600 (:1958); `config.yaml` from example; `SOUL.md` default persona
(must match `hermes_cli/default_soul.py` or treated as never-customized, :1972-1976); skill seed.
Runtime idempotent equivalent: `ensure_hermes_home` (`hermes_cli/config.py:869-917`, + logs/curator).
Markers: `.managed`, `.no-bundled-skills`, `active_profile` (`hermes_constants.py:88`),
legacy `.install_method`.

## 9. tools/lazy_deps.py — lazy provider extras (KEY FINDING)

`[all]` = only 9 extras (cron, pty, mcp, homeassistant, sms, acp, google, web, youtube). All other
43 extras (anthropic, bedrock, vertex, exa, firecrawl, otlp, matrix, slack, voice, honcho, mem0,
modal, daytona, fal, teams…) are **lazy-installed and UNRECORDED** — no manifest exists.

`active_features()` (`lazy_deps.py:1102-1120`) infers installed features by probing the venv for
each feature's **anchor package** (`LAZY_DEPS[feature][0]`). Feature keys: `provider.anthropic`,
`search.exa`, `export.otlp`, `platform.matrix`…

**Migration strategy:** record `active_features()` on source (shell out to
`<install>/venv/bin/python`); on target re-`ensure(feature)` per feature or
`refresh_active_features(prompt=False)` (returns `{feature: current|refreshed|failed:<r>|
skipped:<r>}`, never raises, :1123-1166). **Never copy the venv cross-OS** (ABI wheels, absolute
paths). Gates: `security.allow_lazy_installs`, `HERMES_DISABLE_LAZY_INSTALLS`,
`HERMES_LAZY_INSTALL_TARGET` (appended to sys.path, ABI stamp guard :411-450); allowlist-only
specs, `;` rejected (:554).

## 10. Install tests & CI — canonical layout documentation

- `tests/install/install-update-e2e.sh`: canonical layout `/home/hermes/.hermes/hermes-agent`
  (:71); smoke test = `hermes --version` through the venv launcher (:239-246); version-tolerance
  helpers `update_supports`/`installer_supports` (:150-178).
- `install-e2e.yml`: matrix over release tags (newest/oldest/spread, default 5), every 12h.
- `installer-tests.yml`: install.ps1 under pwsh 7 AND PowerShell 5.1 (what Windows ships).
- 28 `tests/test_install_*.py` contract tests: `.install_method` code-scoped; bootstrap marker
  schemaVersion 1 + pinnedCommit; macOS realpath-free launcher; symlink stomp #21454; FHS uv
  path; ASCII-only ps1; git edge cases (diverged, autostash conflict, unmerged index, no initial
  commit, lockfile churn); Docker immutability.

## 11. hermes backup / import + uninstall as footprint maps

(See hermes-backup-precedent.md for the full study.) `hermes_cli/uninstall.py` (979 lines) is the
**complete install footprint enumerated for deletion**: shim paths (:110-135), node symlinks
(:137-193), Windows registry + portable tooling (:305-333, :352-430). Also
`hermes_state_portability.py` (30KB) for state-DB portability; `scripts/docker_config_migrate.py`.

## 12. Actionable summary

### Detect (source)
1. install_root ← config.py:398-410 + §4 walk; 2. install_method ← config.py:412-513 (7 steps);
3. version ← `__version__` + git HEAD + `.hermes_build_sha`; 4. hermes_home ← env | HKCU | defaults;
5. profiles ← `$HERMES_HOME/profiles/*`; 6. lazy features ← venv python → `active_features()`;
7. desktop state ← electron userData JSONs; 8. git state ← branch, HEAD, status --porcelain, stash.

### Package
- `$HERMES_HOME` minus backup.py exclusions; SQLite via backup API; selected desktop JSONs (not
  installation id); manifest {version, method, branch, HEAD, features, OS/arch, layout family};
  checkout dirty diff as patch + untracked list.

### Restore (target)
1. Platform installer with `--commit <sha>` / `-Commit <sha>` to land on the SAME commit
   (`--skip-setup`, optional `--no-skills`).
2. Overlay $HERMES_HOME (chmod 600 .env).
3. Re-provision lazy extras from manifest feature list.
4. Reapply checkout patch if any.
5. Verify: `hermes --version` (upstream's own smoke test), then `hermes doctor`.

### Traps
| Trap | Where |
|---|---|
| `.install_method` is code-scoped | config.py:425-455 |
| macOS = `~/.hermes`, not App Support | paths.rs:8-18 |
| Windows: read HKCU HERMES_HOME, not just env | main.ts:597-610 |
| Windows 8.3 short paths | install.ps1:106-350 |
| setup_venv deletes existing venv | install.sh:1440-1442 |
| Never PATH venv\Scripts | install.ps1:2699-2712 |
| .env chmod 600 | install.sh:1958 |
| Nix/Docker: migrate $HERMES_HOME only | config.py:545-552 |
| Lazy extras unrecorded | lazy_deps.py:1102 |
| Shared $HERMES_HOME across surfaces | docker-compose.yml:37 |
| Cross-OS venv copy impossible | lazy_deps.py:411-450 |
| checkpoints/ session-hash-keyed | backup.py:59-60 |
| Profile homes never auto-mkdir'd | config.py:889-897 |
