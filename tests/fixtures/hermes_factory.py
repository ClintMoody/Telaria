"""Synthetic Hermes Agent install factory for tests.

Builds a realistic ``HERMES_HOME`` tree modeled directly on the research findings in
``docs/research/`` (state layout, skills seeding, cron store, backup exclusions). Tests use it to
exercise the scanner, diff, dependency, pack, and apply engines against installs we fully control,
including a native-Windows-layout variant that lets Linux CI test cross-platform translation.

Fidelity notes (each mirrors a documented upstream behavior):

- ``skills/.bundled_manifest`` lines are ``<frontmatter-name>:<md5>`` where the hash is MD5 over
  ``sorted(dir.rglob("*"))`` of ``str(rel_path)`` + file bytes — the exact ``_dir_hash`` algorithm
  from hermes ``tools/skills_sync.py``. The rel-path string uses the OS-native separator, so a
  manifest written on Windows hashes differently than on POSIX for identical content; the factory
  supports emulating that with ``sep_override``.
- SQLite stores are real databases created in WAL mode; stray ``-wal``/``-shm`` sidecars can be
  simulated to test that captures exclude them.
- Machine-bound runtime files (``gateway_state.json``, pids, locks) match the names hermes'
  own backup filters on both sides.
- The code checkout is a real (tiny) git repo when ``with_git=True`` so install-method detection
  and dirty-diff logic can be tested; otherwise a bare directory with ``.install_method``.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath


STOCK_SKILL_BODY = """---
name: {name}
description: {description}
version: 1.0.0
author: Nous Research
license: MIT
metadata:
  hermes:
    tags: [{tags}]
---

# {title}

Stock instructions for {name}.

## Steps

1. Do the thing.
2. Report the result.
"""

AGENT_SKILL_BODY = """---
name: {name}
description: Learned from experience on {topic}
version: 0.1.0
author: hermes
license: MIT
---

# {name}

The agent wrote this after a complex task about {topic}.
"""


def skills_dir_hash(directory: Path, sep_override: str | None = None) -> str:
    """Bit-exact reimplementation of hermes ``tools/skills_sync._dir_hash``.

    ``sep_override`` lets tests emulate a manifest produced on another OS ("\\\\" for Windows).
    """
    hasher = hashlib.md5()
    for fpath in sorted(directory.rglob("*")):
        if fpath.is_file():
            rel = str(fpath.relative_to(directory))
            if sep_override and os.sep != sep_override:
                rel = rel.replace(os.sep, sep_override)
            hasher.update(rel.encode("utf-8"))
            hasher.update(fpath.read_bytes())
    return hasher.hexdigest()


@dataclass
class FakeInstallSpec:
    """Knobs for the synthetic install."""

    layout: str = "posix"  # "posix" | "windows" — controls path *content* inside configs
    version: str = "0.20.1"
    release_date: str = "2026.8.13"
    config_version: int = 36
    home_in_configs: str | None = None  # absolute HERMES_HOME as it appears inside config text
    username: str = "alice"
    with_git: bool = False  # real git repo for the checkout (requires git binary)
    with_dirty_checkout: bool = False  # modify a repo file after commit (needs with_git)
    with_profile: str | None = None  # name of one nested profile to create
    with_wal_sidecars: bool = True  # leave fake -wal/-shm files next to state.db
    with_machine_bound: bool = True
    with_whatsapp_session: bool = True
    with_secrets: bool = True
    with_external_skill_dir: Path | None = None  # referenced in skills.external_dirs
    session_cwds: tuple[str, ...] = ()  # extra cwd rows for state.db sessions
    timezone: str = "America/Chicago"

    def default_home_str(self) -> str:
        if self.home_in_configs:
            return self.home_in_configs
        if self.layout == "windows":
            return f"C:\\Users\\{self.username}\\AppData\\Local\\hermes"
        return f"/home/{self.username}/.hermes"

    def join(self, *parts: str) -> str:
        """Join path parts in the spec's layout flavor (for path strings inside configs)."""
        base = self.default_home_str()
        if self.layout == "windows":
            return str(PureWindowsPath(base, *parts))
        return "/".join([base, *parts])


@dataclass
class FakeHermesInstall:
    """A built synthetic install. ``home`` is the on-disk root (always a real local dir)."""

    home: Path
    spec: FakeInstallSpec
    stock_hashes: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------------ helpers
    @property
    def code_dir(self) -> Path:
        return self.home / "hermes-agent"

    @property
    def skills(self) -> Path:
        return self.home / "skills"


def _write(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if mode is not None and os.name == "posix":
        os.chmod(path, mode)


def _make_sqlite(path: Path, schema: str, rows: list[tuple[str, tuple]] | None = None,
                 wal: bool = True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        if wal:
            conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(schema)
        for sql, params in rows or []:
            conn.execute(sql, params)
        conn.commit()
        # Checkpoint so the .db file itself is complete; sidecar simulation is separate.
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _seed_skill(root: Path, category: str, dirname: str, name: str, description: str,
                tags: str = "test", extra_files: dict[str, str] | None = None) -> Path:
    skill_dir = root / category / dirname
    _write(skill_dir / "SKILL.md", STOCK_SKILL_BODY.format(
        name=name, description=description, tags=tags, title=name.replace("-", " ").title()))
    for rel, content in (extra_files or {}).items():
        _write(skill_dir / rel, content)
    return skill_dir


def build_fake_install(root: Path, spec: FakeInstallSpec | None = None) -> FakeHermesInstall:
    """Create a synthetic Hermes install under ``root`` (which becomes HERMES_HOME)."""
    spec = spec or FakeInstallSpec()
    home = root
    home.mkdir(parents=True, exist_ok=True)
    install = FakeHermesInstall(home=home, spec=spec)

    _build_config(install)
    _build_identity_files(install)
    _build_skills(install)
    _build_cron(install)
    _build_state_db(install)
    _build_integrations(install)
    _build_code_checkout(install)
    _build_runtime_junk(install)
    if spec.with_profile:
        _build_nested_profile(install, spec.with_profile)
    return install


# --------------------------------------------------------------------------- sections

def _build_config(inst: FakeHermesInstall) -> None:
    s = inst.spec
    mcp_stdio_cmd = "npx" if s.layout == "posix" else "npx.cmd"
    abs_script = s.join("mcp-installs", "n8n", ".venv",
                        "bin/python" if s.layout == "posix" else "Scripts\\python.exe")
    external_dirs = ""
    if s.with_external_skill_dir is not None:
        external_dirs = f"\n  external_dirs:\n    - {s.with_external_skill_dir}\n"
    config = f"""# Hermes Agent CLI Configuration
_config_version: {s.config_version}
timezone: {s.timezone}

model:
  default: "anthropic/claude-opus-4.6"
  provider: "auto"
  base_url: "https://openrouter.ai/api/v1"

database:
  journal_mode: "wal"

memory:
  memory_enabled: true
  provider: null

skills:
  creation_nudge_interval: 15
  disabled:
    - social-media-poster{external_dirs}
plugins:
  enabled:
    - disk-cleanup

cron:
  provider: builtin
  model_drift_guard: true

terminal:
  backend: local
  cwd: "{s.join('..', 'projects', 'main') if s.layout == 'posix' else s.join('projects')}"

mcp_servers:
  linear:
    url: "https://mcp.linear.app/mcp"
    auth: oauth
    enabled: true
  local-files:
    command: "{mcp_stdio_cmd}"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "{s.join('mcp-data')}"]
    enabled: true
  n8n:
    command: "{abs_script}"
    args: ["{s.join('mcp-installs', 'n8n', 'server.py')}"]
    env:
      N8N_BASE_URL: "http://127.0.0.1:5678"
      N8N_API_KEY: "${{MCP_N8N_API_KEY}}"
    enabled: true

dashboard:
  public_url: "http://old-box.local:8642"

monitoring:
  install_id: "inst-4f2a9c"

onboarding:
  seen:
    busy_input_prompt: true
"""
    _write(inst.home / "config.yaml", config)

    if s.with_secrets:
        env = f"""# Hermes environment
OPENROUTER_API_KEY=sk-or-fake-1234567890
TELEGRAM_BOT_TOKEN=1234567890:FAKE-telegram-token
TELEGRAM_HOME_CHANNEL=-1002223334445
MCP_N8N_API_KEY=n8n-fake-key
EMAIL_ADDRESS={s.username}@example.com
EMAIL_PASSWORD=fake-email-secret
HERMES_TIMEZONE={s.timezone}
"""
        _write(inst.home / ".env", env, mode=0o600)
        _write(inst.home / "auth.json", json.dumps({
            "active_provider": "openrouter",
            "providers": {"nous": {"auth_type": "device_code",
                                   "refresh_token": "fake-refresh-token"}},
        }, indent=2), mode=0o600)
        _write(inst.home / "mcp-tokens" / "linear.json",
               json.dumps({"access_token": "fake-mcp-oauth", "expires_at": 1900000000}),
               mode=0o600)
        _write(inst.home / "mcp-tokens" / "linear.client.json",
               json.dumps({"client_id": "fake-client", "redirect_uri": "http://127.0.0.1:43110/cb"}),
               mode=0o600)


def _build_identity_files(inst: FakeHermesInstall) -> None:
    _write(inst.home / "SOUL.md", "# Soul\n\nYou are Alice's Hermes. Be kind, be curious.\n")
    _write(inst.home / "memories" / "MEMORY.md",
           "Alice prefers metric units.\n§\nThe home NAS is at 10.0.0.5.\n")
    _write(inst.home / "memories" / "USER.md", "Alice: musician, night owl.\n")
    _write(inst.home / "active_profile", "default\n")


def _build_skills(inst: FakeHermesInstall) -> None:
    s = inst.spec
    root = inst.skills
    manifest_lines: list[str] = []

    # 1. Pristine stock skill — hash in manifest matches current content.
    d = _seed_skill(root, "research", "web-search", "web-search",
                    "Search the web and cite sources", tags="research, web",
                    extra_files={"references/engines.md": "Use good engines.\n"})
    h = skills_dir_hash(d)
    manifest_lines.append(f"web-search:{h}")
    inst.stock_hashes["web-search"] = h

    # 2. Stock skill the user/agent MODIFIED after seeding — manifest keeps the seed-time hash.
    d = _seed_skill(root, "productivity", "daily-brief", "daily-brief",
                    "Morning summary of calendar and inbox", tags="productivity")
    h_seeded = skills_dir_hash(d)
    manifest_lines.append(f"daily-brief:{h_seeded}")
    inst.stock_hashes["daily-brief"] = h_seeded
    skill_md = d / "SKILL.md"
    skill_md.write_text(
        skill_md.read_text(encoding="utf-8")
        + "\n## Alice's tweak\n\nAlways include the weather for Austin.\n",
        encoding="utf-8")

    # 3. Stock skill DELETED by the user — manifest entry with no directory.
    manifest_lines.append("social-media-poster:0123456789abcdef0123456789abcdef")

    # 4. Agent-created skill — absent from manifest, created_by=agent in .usage.json.
    agent_dir = root / "creative" / "playlist-curator"
    _write(agent_dir / "SKILL.md",
           AGENT_SKILL_BODY.format(name="playlist-curator", topic="mood playlists"))
    _write(agent_dir / "scripts" / "curate.py", "#!/usr/bin/env python3\nprint('curating')\n")

    # 5. Hub-installed optional skill — recorded in .hub/lock.json, not in .bundled_manifest.
    hub_dir = _seed_skill(root, "finance", "budget-watch", "budget-watch",
                          "Watch spending against budgets", tags="finance")
    _write(root / ".hub" / "lock.json", json.dumps({
        "version": 1,
        "installed": {
            "budget-watch": {
                "source": "official",
                "identifier": "official/finance/budget-watch",
                "trust_level": "builtin",
                "scan_verdict": "clean",
                "content_hash": "sha256:" + hashlib.sha256(b"budget").hexdigest()[:16],
                "install_path": "finance/budget-watch",
                "files": ["SKILL.md"],
                "metadata": {},
                "scan_provenance": {},
                "installed_at": "2026-07-01T12:00:00Z",
                "updated_at": "2026-07-01T12:00:00Z",
            }
        },
    }, indent=2))
    assert hub_dir.exists()

    # 6. Curator archive + suppression.
    _write(root / ".archive" / "old-notes-skill" / "SKILL.md",
           AGENT_SKILL_BODY.format(name="old-notes-skill", topic="note keeping"))
    _write(root / ".curator_suppressed", "unused-builtin-skill\n")

    _write(root / ".bundled_manifest", "\n".join(manifest_lines) + "\n")
    _write(root / ".usage.json", json.dumps({
        "web-search": {"created_by": None, "use_count": 42, "state": "active"},
        "daily-brief": {"created_by": None, "use_count": 17, "patch_count": 3,
                        "state": "active"},
        "playlist-curator": {"created_by": "agent", "use_count": 5, "state": "active"},
        "budget-watch": {"created_by": "installed", "use_count": 2, "state": "active"},
    }, indent=2))
    _write(root / ".sync_device_id", "quiet-falcon-7\n")
    # Regeneratable hub cache that captures should drop.
    _write(root / ".hub" / "index-cache" / "official.json", "[]")

    if s.with_external_skill_dir is not None:
        ext = s.with_external_skill_dir
        _seed_skill(ext, "shared", "team-standup", "team-standup",
                    "Summarize the team standup thread")


def _build_cron(inst: FakeHermesInstall) -> None:
    s = inst.spec
    cron = inst.home / "cron"
    workdir = (f"/home/{s.username}/projects/site" if s.layout == "posix"
               else f"C:\\Users\\{s.username}\\projects\\site")
    jobs = {
        "jobs": [
            {
                "id": "a1b2c3d4e5f6",
                "name": "Morning brief",
                "prompt": "Prepare the morning brief and send it.",
                "skills": ["daily-brief"],
                "skill": "daily-brief",
                "model": None, "provider": None,
                "provider_snapshot": "openrouter",
                "model_snapshot": "anthropic/claude-opus-4.6",
                "schedule": {"kind": "cron", "expr": "0 7 * * *", "display": "0 7 * * *"},
                "schedule_display": "0 7 * * *",
                "repeat": {"times": None, "completed": 0},
                "enabled": True, "state": "scheduled",
                "created_at": "2026-06-01T12:00:00+00:00",
                "next_run_at": "2026-08-15T12:00:00+00:00",
                "last_run_at": "2026-08-14T12:00:04+00:00",
                "last_status": "ok", "last_error": None,
                "deliver": "telegram",
                "origin": {"platform": "telegram", "chat_id": "-1002223334445"},
                "enabled_toolsets": ["web", "linear"],
                "workdir": None,
                # Machine-scoped runtime claims that a migration must scrub:
                "run_claim": {"at": "2026-08-14T12:00:00+00:00", "by": "old-box:4242"},
            },
            {
                "id": "b2c3d4e5f6a7",
                "name": "Site health check",
                "prompt": "",
                "skills": [], "skill": None,
                "no_agent": True,
                "script": "check_site.sh",
                "schedule": {"kind": "interval", "minutes": 30, "display": "every 30m"},
                "repeat": {"times": None, "completed": 0},
                "enabled": True, "state": "scheduled",
                "created_at": "2026-06-02T12:00:00+00:00",
                "next_run_at": "2026-08-15T12:30:00+00:00",
                "last_run_at": "2026-08-15T12:00:00+00:00",
                "last_status": "ok",
                "deliver": "local",
                "workdir": workdir,
                "monitor_url": "http://127.0.0.1:8080/health",
                "monitor_state": {"last_output_hash": "ab" * 32,
                                  "last_changed_at": "2026-08-10T00:00:00+00:00"},
            },
            {
                "id": "c3d4e5f6a7b8",
                "name": "Weekly digest",
                "prompt": "Digest the week using earlier outputs.",
                "skills": [f"{inst.spec.join('skills', 'research', 'web-search')}"],
                "schedule": {"kind": "cron", "expr": "0 18 * * 5", "display": "0 18 * * 5"},
                "repeat": {"times": None, "completed": 0},
                "enabled": True, "state": "scheduled",
                "created_at": "2026-06-03T12:00:00+00:00",
                "context_from": ["a1b2c3d4e5f6"],
                "deliver": "email",
            },
        ],
        "updated_at": "2026-08-15T00:00:00+00:00",
    }
    _write(cron / "jobs.json", json.dumps(jobs, indent=2), mode=0o600)

    _write(inst.home / "scripts" / "check_site.sh",
           "#!/usr/bin/env bash\ncurl -fsS http://127.0.0.1:8080/health\n")

    _make_sqlite(cron / "notepad.db",
                 "CREATE TABLE notepad (job_id TEXT, key TEXT, value TEXT,"
                 " PRIMARY KEY (job_id, key));",
                 [("INSERT INTO notepad VALUES (?, ?, ?)",
                   ("b2c3d4e5f6a7", "last_ok", "2026-08-15T12:00:00Z"))])
    _make_sqlite(cron / "executions.db",
                 "CREATE TABLE executions (id TEXT PRIMARY KEY, job_id TEXT NOT NULL,"
                 " source TEXT NOT NULL, process_id TEXT NOT NULL, pid INTEGER NOT NULL,"
                 " process_started_at INTEGER, status TEXT, claimed_at TEXT NOT NULL,"
                 " started_at TEXT, finished_at TEXT, error TEXT);",
                 [("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   ("e1", "a1b2c3d4e5f6", "ticker", "p1", 4242, 1755100000, "completed",
                    "2026-08-14T12:00:00Z", "2026-08-14T12:00:01Z", "2026-08-14T12:00:04Z", None)),
                  ("INSERT INTO executions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                   ("e2", "b2c3d4e5f6a7", "ticker", "p2", 4243, 1755100000, "running",
                    "2026-08-15T12:00:00Z", "2026-08-15T12:00:01Z", None, None))])

    out = cron / "output" / "a1b2c3d4e5f6"
    _write(out / "2026-08-14_07-00-04.md", "# Morning brief\n\nAll calm.\n")
    _write(cron / "output" / "b2c3d4e5f6a7" / "monitor_last_output.txt", "OK\n")
    _write(cron / "ticker_heartbeat", "1755248400.0\n")
    _write(cron / "usage_audit.jsonl", '{"job":"a1b2c3d4e5f6","tokens":1234}\n')


def _build_state_db(inst: FakeHermesInstall) -> None:
    s = inst.spec
    cwds = list(s.session_cwds) or [
        f"/home/{s.username}/projects/site" if s.layout == "posix"
        else f"C:\\Users\\{s.username}\\projects\\site",
    ]
    rows = [("INSERT INTO sessions VALUES (?,?,?,?,?)",
             (f"sess-{i}", cwd, "main", cwd, "2026-08-01T00:00:00Z"))
            for i, cwd in enumerate(cwds)]
    rows.append(("INSERT INTO messages VALUES (?,?,?,?)",
                 ("m1", "sess-0", "user", "hello from the old machine")))
    _make_sqlite(inst.home / "state.db",
                 "CREATE TABLE sessions (session_key TEXT PRIMARY KEY, cwd TEXT,"
                 " git_branch TEXT, git_repo_root TEXT, created_at TEXT);"
                 "CREATE TABLE messages (id TEXT PRIMARY KEY, session_key TEXT,"
                 " role TEXT, content TEXT);"
                 "CREATE TABLE state_meta (key TEXT PRIMARY KEY, value TEXT);",
                 rows)
    if s.with_wal_sidecars:
        # Simulate leftover sidecars from a live process (content is irrelevant; presence is
        # what capture logic must handle — never ship them).
        (inst.home / "state.db-wal").write_bytes(b"\x00" * 32)
        (inst.home / "state.db-shm").write_bytes(b"\x00" * 32)

    _make_sqlite(inst.home / "kanban.db",
                 "CREATE TABLE tasks (id INTEGER PRIMARY KEY, title TEXT, status TEXT);",
                 [("INSERT INTO tasks VALUES (?,?,?)", (1, "Migrate to the new box", "doing"))])


def _build_integrations(inst: FakeHermesInstall) -> None:
    s = inst.spec
    if s.with_whatsapp_session:
        _write(inst.home / "platforms" / "whatsapp" / "session" / "creds.json",
               json.dumps({"noiseKey": "fake", "registered": True}), mode=0o600)
    _write(inst.home / "platforms" / "pairing" / "telegram-approved.json",
           json.dumps({"approved": ["111222333"]}), mode=0o600)
    _write(inst.home / "channel_directory.json", json.dumps({"telegram": {"-1002223334445": "Home"}}))
    _write(inst.home / "webhook_subscriptions.json",
           json.dumps({"routes": {"deploys": {"secret": "fake-hmac-secret"}}}), mode=0o600)
    # User plugin with data.
    _write(inst.home / "plugins" / "myplugin" / "plugin.yaml",
           "name: myplugin\nversion: 0.1.0\ndescription: Alice's helper\nkind: standalone\n")
    _write(inst.home / "plugins" / "myplugin" / "__init__.py",
           "def register(ctx):\n    pass\n")
    _write(inst.home / "plugin-data" / "agent-plugin-myplugin-deadbeef" / "state.json",
           json.dumps({"counter": 7}))
    # Skill bundle.
    _write(inst.home / "skill-bundles" / "focus.yaml",
           "name: focus\nskills:\n  - daily-brief\n  - web-search\n")
    # MCP catalog install (regeneratable tree).
    _write(inst.home / "mcp-installs" / "n8n" / "server.py", "print('n8n mcp')\n")
    _write(inst.home / "mcp-installs" / "n8n" / ".venv" / "pyvenv.cfg", "home = /usr\n")


def _build_code_checkout(inst: FakeHermesInstall) -> None:
    s = inst.spec
    code = inst.code_dir
    _write(code / "pyproject.toml",
           f'[project]\nname = "hermes-agent"\nversion = "{s.version}"\n')
    _write(code / "hermes_cli" / "__init__.py",
           f'__version__ = "{s.version}"\n__release_date__ = "{s.release_date}"\n')
    _write(code / "hermes", "#!/usr/bin/env python3\n# launcher\n")
    # A venv marker tree (never migrated).
    _write(code / "venv" / "pyvenv.cfg", "home = /usr\nversion = 3.11.9\n")
    _write(code / "venv" / "lib" / "python3.11" / "site-packages"
           / "hermes_agent-0.20.1.dist-info" / "METADATA",
           f"Metadata-Version: 2.1\nName: hermes-agent\nVersion: {s.version}\n")

    if s.with_git:
        env = {**os.environ,
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
               "HOME": str(code)}  # isolate from user gitconfig
        def git(*args: str) -> None:
            subprocess.run(["git", *args], cwd=code, check=True, env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        git("init", "-q", "-b", "main")
        git("add", "-A")
        git("commit", "-q", "-m", "seed")
        git("tag", f"v{s.release_date}")
        if s.with_dirty_checkout:
            launcher = code / "hermes"
            launcher.write_text(launcher.read_text() + "# local tweak\n", encoding="utf-8")
    else:
        _write(code / ".install_method", "git\n")

    # Managed tool dirs that must never be packed.
    _write(inst.home / "bin" / "uv", "#!/bin/sh\necho uv\n")
    _write(inst.home / "node" / "bin" / "node", "#!/bin/sh\necho node\n")


def _build_runtime_junk(inst: FakeHermesInstall) -> None:
    s = inst.spec
    if s.with_machine_bound:
        _write(inst.home / "gateway_state.json", json.dumps({"desired": "running"}))
        _write(inst.home / "gateway.pid", "4242\n")
        _write(inst.home / "cron.pid", "4243\n")
        _write(inst.home / "gateway.lock", "")
        _write(inst.home / "processes.json", json.dumps({"gateway": 4242}))
        _write(inst.home / ".update_check", json.dumps({"ver": s.version, "behind": 0}))
    _write(inst.home / "logs" / "agent.log", "2026-08-15 INFO hello\n")
    _write(inst.home / "logs" / "errors.log", "")
    _write(inst.home / "cache" / "model_catalog.json", "{}")
    _write(inst.home / "sessions" / "sessions.json", "{}")
    _write(inst.home / "checkpoints" / "store" / "deadbeefdeadbeef" / "ref", "abc123\n")
    (inst.home / "image_cache").mkdir(parents=True, exist_ok=True)
    (inst.home / "audio_cache").mkdir(parents=True, exist_ok=True)


def _build_nested_profile(inst: FakeHermesInstall, name: str) -> None:
    """A named profile with its own minimal state subtree."""
    p = inst.home / "profiles" / name
    _write(p / "config.yaml", f"_config_version: {inst.spec.config_version}\nmodel:\n"
           "  default: \"nous/hermes-4\"\n")
    _write(p / ".env", "OPENROUTER_API_KEY=sk-or-profile-key\n", mode=0o600)
    _write(p / "SOUL.md", f"# {name} soul\n")
    _write(p / "cron" / "jobs.json", json.dumps({"jobs": [], "updated_at": "2026-08-15T00:00:00+00:00"}))
    skill = p / "skills" / "research" / "profile-skill"
    _write(skill / "SKILL.md", STOCK_SKILL_BODY.format(
        name="profile-skill", description="profile-local", tags="p", title="Profile Skill"))
    _write(p / "skills" / ".bundled_manifest", f"profile-skill:{skills_dir_hash(skill)}\n")
