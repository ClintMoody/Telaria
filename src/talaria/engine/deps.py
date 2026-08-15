"""Dependency extraction and per-target-OS feasibility (ARCHITECTURE §6; R-DEPS-*).

Extraction sources and their authority (each mirrors an upstream mechanism):
- skill frontmatter: required_environment_variables (ENFORCED), platforms[] (HARD GATE),
  prerequisites.*/dependencies[] (advisory) — tools/skills_tool.py:340-530
- cron jobs: script interpreter, croniter, delivery platform, drift snapshots, workdir,
  context_from, MCP toolset refs — cron/scheduler.py preflight mirrors
- MCP entries: url vs command; npx→node, uvx→uv, docker→daemon; ${VAR} cross-check
- providers: env keys, localhost base_urls
- lazy features: recorded for target re-ensure

Predictive mode evaluates against a declared target OS with static knowledge only —
works on a bare Python 3.9 box, fully offline (A11).
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from talaria.engine import yamlmini
from talaria.model.artifact import Dependency, TARGET_OSES
from talaria.platform.paths import windows_path_problems

#: Delivery platforms the scheduler knows (cron/scheduler.py:394-399) and the env var that
#: must be present for home-channel delivery (cron §4).
KNOWN_DELIVERY_PLATFORMS = {
    "telegram": "TELEGRAM_BOT_TOKEN", "discord": "DISCORD_BOT_TOKEN",
    "slack": "SLACK_BOT_TOKEN", "whatsapp": None, "signal": None, "matrix": None,
    "mattermost": None, "homeassistant": "HASS_TOKEN", "dingtalk": None, "feishu": None,
    "wecom": None, "weixin": None, "sms": None, "email": "EMAIL_PASSWORD",
    "webhook": None, "bluebubbles": None, "qqbot": None, "yuanbao": None,
    "local": None, "origin": None,
}

#: skill frontmatter platforms[] → our target-os names (agent/skill_utils.py PLATFORM_MAP;
#: Termux accepts linux).
SKILL_PLATFORM_ACCEPTS = {
    "linux": {"linux", "termux"},
    "macos": {"macos"},
    "darwin": {"macos"},
    "windows": {"windows"},
}


@dataclass
class DepFinding:
    """One dependency with its per-OS verdicts and evidence."""

    artifact_id: str
    dependency: Dependency
    verdicts: Dict[str, str] = field(default_factory=dict)    # target os -> verdict
    evidence: str = ""                                        # file + locator
    remediation: str = ""

    def to_json(self) -> dict:
        return {"artifact": self.artifact_id, "dep": self.dependency.to_json(),
                "verdicts": self.verdicts, "evidence": self.evidence,
                "remediation": self.remediation}


# --------------------------------------------------------------------------- frontmatter

def parse_frontmatter(skill_md_text: str) -> dict:
    """Tolerant frontmatter read via the yamlmini subset (upstream falls back naively too)."""
    if not skill_md_text.startswith("---"):
        return {}
    parts = skill_md_text.split("---", 2)
    if len(parts) < 3:
        return {}
    return yamlmini.parse(parts[1])


def skill_dependencies(skill_dir: Path, artifact_id: str) -> List[DepFinding]:
    """Extract every declarable dependency from one skill (R-DEPS-01)."""
    findings: List[DepFinding] = []
    skill_md = Path(skill_dir) / "SKILL.md"
    try:
        fm = parse_frontmatter(skill_md.read_text(encoding="utf-8-sig", errors="replace"))
    except OSError:
        return findings
    evidence = f"{skill_md.name} frontmatter"

    platforms = fm.get("platforms")
    if isinstance(platforms, list) and platforms:
        findings.append(DepFinding(artifact_id, Dependency(
            "platform", ",".join(str(p) for p in platforms), enforced=True,
            detail={"platforms": platforms}), evidence=evidence))

    req_env = fm.get("required_environment_variables")
    if isinstance(req_env, list):
        for entry in req_env:
            if isinstance(entry, dict):
                name = entry.get("name") or entry.get("env_var")
                optional = bool(entry.get("optional"))
            else:
                name, optional = str(entry), False
            if name:
                findings.append(DepFinding(artifact_id, Dependency(
                    "env_var", str(name), enforced=not optional,
                    detail={"url": entry.get("provider_url") or entry.get("url")
                            if isinstance(entry, dict) else None}),
                    evidence=evidence,
                    remediation=f"add {name} to the new machine's .env (on your checklist)"))

    prereq = fm.get("prerequisites")
    if isinstance(prereq, dict):
        for cmd in prereq.get("commands") or []:
            findings.append(DepFinding(artifact_id, Dependency(
                "binary", str(cmd), enforced=False), evidence=evidence,
                remediation=f"install `{cmd}` on the new machine"))
        for var in prereq.get("env_vars") or []:
            findings.append(DepFinding(artifact_id, Dependency(
                "env_var", str(var), enforced=True), evidence=evidence))
        for pkg in prereq.get("pip") or []:
            findings.append(DepFinding(artifact_id, Dependency(
                "python_pkg", str(pkg), enforced=False), evidence=evidence))

    for pkg in fm.get("dependencies") or []:
        if isinstance(pkg, str):
            findings.append(DepFinding(artifact_id, Dependency(
                "python_pkg", pkg, enforced=False), evidence=evidence,
                remediation=f"pip install {pkg} (advisory — upstream never auto-installs)"))

    setup = fm.get("setup")
    if isinstance(setup, dict):
        for entry in setup.get("collect_secrets") or []:
            if isinstance(entry, dict) and entry.get("env_var"):
                findings.append(DepFinding(artifact_id, Dependency(
                    "env_var", str(entry["env_var"]), enforced=True,
                    detail={"url": entry.get("provider_url")}), evidence=evidence))
    return findings


# --------------------------------------------------------------------------- cron

def job_dependencies(job: dict, profile: str) -> List[DepFinding]:
    """Extract dependencies from one cron job record (cron research §4)."""
    jid = str(job.get("id", "?"))
    artifact = f"cron-jobs@{profile}"
    ev = f"cron/jobs.json jobs[id={jid}]"
    findings: List[DepFinding] = []

    schedule = job.get("schedule") or {}
    if schedule.get("kind") == "cron":
        findings.append(DepFinding(artifact, Dependency(
            "python_pkg", "croniter", enforced=True,
            detail={"job": jid}), evidence=ev,
            remediation="croniter ships with Hermes — reinstalling Hermes provides it"))

    script = job.get("script") or job.get("monitor_script")
    if isinstance(script, str) and script:
        ext = Path(script).suffix.lower()
        if ext in (".sh", ".bash"):
            findings.append(DepFinding(artifact, Dependency(
                "binary", "bash", enforced=True, detail={"job": jid, "script": script}),
                evidence=ev,
                remediation="shell scripts need bash — impossible on native Windows "
                            "(rewrite as .py, or run under WSL)"))
        findings.append(DepFinding(artifact, Dependency(
            "artifact_ref", f"scripts/{Path(script).name}", enforced=True,
            detail={"job": jid}), evidence=ev))

    deliver = str(job.get("deliver") or "origin")
    for target in re.split(r"[+,]", deliver):
        target = target.strip().split(":", 1)[0]
        if not target:
            continue
        if target not in KNOWN_DELIVERY_PLATFORMS:
            findings.append(DepFinding(artifact, Dependency(
                "service", f"delivery:{target}", enforced=False, detail={"job": jid}),
                evidence=ev, remediation=f"unknown delivery platform '{target}' — "
                                         "verify a plugin provides it"))
            continue
        env_var = KNOWN_DELIVERY_PLATFORMS[target]
        if env_var:
            findings.append(DepFinding(artifact, Dependency(
                "env_var", env_var, enforced=True,
                detail={"job": jid, "platform": target}), evidence=ev,
                remediation=f"{target} delivery needs {env_var} in .env"))
        elif target in ("whatsapp", "signal", "matrix", "weixin"):
            findings.append(DepFinding(artifact, Dependency(
                "service", f"pairing:{target}", enforced=True,
                detail={"job": jid, "platform": target}), evidence=ev,
                remediation=f"{target} is device-linked — re-pair on the new machine"))

    if job.get("model") is None and not job.get("no_agent") and job.get("model_snapshot"):
        findings.append(DepFinding(artifact, Dependency(
            "config_key", "model.default", enforced=False,
            detail={"job": jid, "model_snapshot": job.get("model_snapshot"),
                    "provider_snapshot": job.get("provider_snapshot")}), evidence=ev,
            remediation="drift guard: if the target's default model differs from this "
                        "snapshot the job fails closed ([drift_skip]) until re-approved"))

    workdir = job.get("workdir")
    if isinstance(workdir, str) and workdir:
        findings.append(DepFinding(artifact, Dependency(
            "artifact_ref", workdir, enforced=False, detail={"job": jid, "kind": "workdir"}),
            evidence=ev, remediation="create this directory on the new machine or edit "
                                     "the job's workdir"))

    for ref in job.get("context_from") or []:
        findings.append(DepFinding(artifact, Dependency(
            "artifact_ref", f"cron-output/{ref}", enforced=True, detail={"job": jid}),
            evidence=ev, remediation="the referenced job and its output travel together "
                                     "(coupling rule job-context)"))

    for toolset in job.get("enabled_toolsets") or []:
        if toolset in ("messaging", "clarify", "memory", "cronjob", "web", "file", "no_mcp"):
            continue
        findings.append(DepFinding(artifact, Dependency(
            "service", f"mcp:{toolset}", enforced=False, detail={"job": jid}), evidence=ev,
            remediation=f"toolset '{toolset}' may name an MCP server — it must exist in "
                        "mcp_servers on the target"))

    skills = job.get("skills") or ([job["skill"]] if job.get("skill") else [])
    for skill_ref in skills:
        if isinstance(skill_ref, str) and skill_ref:
            name = Path(skill_ref).name if ("/" in skill_ref or "\\" in skill_ref) \
                else skill_ref
            findings.append(DepFinding(artifact, Dependency(
                "artifact_ref", f"skill:{name}", enforced=False, detail={"job": jid}),
                evidence=ev))
    return findings


# --------------------------------------------------------------------------- mcp

def mcp_dependencies(config: dict, profile: str, env_names: Set[str]) -> List[DepFinding]:
    """MCP server requirements from config (integ §2.4 recipe, steps 1–8)."""
    artifact = f"mcp-json@{profile}" if profile else "config-yaml@"
    findings: List[DepFinding] = []
    servers = yamlmini.get_path(config, "mcp_servers", {}) or {}
    if not isinstance(servers, dict):
        return findings
    for name, entry in servers.items():
        if not isinstance(entry, dict):
            continue
        ev = f"config.yaml mcp_servers.{name}"
        url = entry.get("url")
        command = entry.get("command")
        if url and not command:
            if entry.get("auth") == "oauth":
                findings.append(DepFinding(artifact, Dependency(
                    "credential_file", f"mcp-tokens/{name}.json", enforced=False,
                    detail={"server": name}), evidence=ev,
                    remediation=f"OAuth tokens may need refresh: `hermes mcp reauth {name}`"))
            continue
        if not isinstance(command, str) or not command:
            continue
        base = Path(command.replace("\\", "/")).name.lower()
        if base in ("npx", "npx.cmd", "node", "node.exe"):
            findings.append(DepFinding(artifact, Dependency(
                "node", "node", enforced=True, detail={"server": name}), evidence=ev,
                remediation="Node.js is Hermes-managed — reinstalling Hermes provides it"))
        elif base in ("uvx", "uv", "uvx.exe", "uv.exe"):
            findings.append(DepFinding(artifact, Dependency(
                "binary", "uv", enforced=True, detail={"server": name}), evidence=ev,
                remediation="uv is Hermes-managed — reinstalling Hermes provides it"))
        elif base in ("docker", "docker.exe", "podman"):
            findings.append(DepFinding(artifact, Dependency(
                "service", "docker-daemon", enforced=True, detail={"server": name}),
                evidence=ev, remediation="install/start Docker on the new machine"))
        if "/" in command or "\\" in command:
            findings.append(DepFinding(artifact, Dependency(
                "binary", command, enforced=True,
                detail={"server": name, "absolute": True}), evidence=ev,
                remediation="absolute stdio command path — reinstall this MCP on the "
                            "target (`hermes mcp install`) or rewrite the path"))
        for env_map in (entry.get("env") or {},):
            for _key, value in env_map.items():
                m = re.fullmatch(r"\$\{([A-Z0-9_]+)\}", str(value))
                if m:
                    var = m.group(1)
                    findings.append(DepFinding(artifact, Dependency(
                        "env_var", var, enforced=True, detail={"server": name}),
                        evidence=ev,
                        remediation=(f"{var} referenced by mcp_servers.{name} "
                                     + ("(present in source .env)" if var in env_names
                                        else "(MISSING from source .env too)"))))
    return findings


# --------------------------------------------------------------------------- evaluation

_HERMES_MANAGED_BINARIES = {"node", "uv", "croniter", "rg", "ffmpeg"}


def evaluate_predictive(findings: Sequence[DepFinding], target_os: str,
                        env_available: Optional[Set[str]] = None) -> None:
    """Fill ``verdicts[target_os]`` on every finding using static knowledge only
    (R-DEPS-03; runs offline on a bare interpreter). Windows member-name legality is
    a separate sweep: :func:`evaluate_members_for_windows`.
    """
    for finding in findings:
        dep = finding.dependency
        verdict = "ok"
        if dep.kind == "platform":
            accepted: Set[str] = set()
            for plat in dep.detail.get("platforms", []):
                accepted |= SKILL_PLATFORM_ACCEPTS.get(str(plat).lower(), set())
            verdict = "ok" if target_os in accepted else "impossible"
        elif dep.kind == "binary":
            name = Path(str(dep.name).replace("\\", "/")).name.lower()
            if name in ("bash", "sh") and target_os == "windows":
                verdict = "impossible"
            elif dep.detail.get("absolute"):
                verdict = "action"
            elif name in _HERMES_MANAGED_BINARIES:
                verdict = "ok"
            else:
                verdict = "unknown_offline"
        elif dep.kind == "env_var":
            if env_available is not None and dep.name in env_available:
                verdict = "action"   # value must be re-provided (checklist), then OK
            else:
                verdict = "action"
        elif dep.kind == "python_pkg":
            verdict = "ok" if dep.name == "croniter" else "unknown_offline"
        elif dep.kind == "node":
            verdict = "ok"           # Hermes-managed runtime
        elif dep.kind == "service":
            if dep.name.startswith("pairing:"):
                verdict = "action"
            elif dep.name == "docker-daemon":
                verdict = "unknown_offline"
            else:
                verdict = "unknown_offline"
        elif dep.kind == "artifact_ref":
            if dep.detail.get("kind") == "workdir":
                verdict = "action"
            else:
                verdict = "ok"
        elif dep.kind == "config_key":
            verdict = "action" if dep.detail.get("model_snapshot") else "ok"
        finding.verdicts[target_os] = verdict


def evaluate_members_for_windows(member_paths: Sequence[str]) -> List[DepFinding]:
    """Windows-illegal member names as IMPOSSIBLE-ON-WINDOWS findings (R-XPLAT-04)."""
    out: List[DepFinding] = []
    for member in member_paths:
        problems = windows_path_problems(member)
        if problems:
            out.append(DepFinding(
                "bundle", Dependency("os", member, enforced=True,
                                     detail={"problems": problems}),
                verdicts={"windows": "impossible"}, evidence=member,
                remediation="cannot exist on Windows — applies only via a consented, "
                            "recorded rename (R-APPLY-18)"))
    return out


def evaluate_live(findings: Sequence[DepFinding], env: Optional[Dict[str, str]] = None
                  ) -> None:
    """Live preflight on THIS machine: probe PATH, env, interpreters (R-DEPS-04)."""
    env = os.environ if env is None else env
    import sys as _sys

    host = ("windows" if _sys.platform == "win32"
            else "macos" if _sys.platform == "darwin" else "linux")
    for finding in findings:
        dep = finding.dependency
        verdict = finding.verdicts.get(host, "ok")
        if dep.kind == "binary" and not dep.detail.get("absolute"):
            name = Path(str(dep.name)).name
            verdict = "ok" if shutil.which(name) else "missing_installable"
            if name in ("bash", "sh") and host == "windows":
                verdict = "impossible"
        elif dep.kind == "binary" and dep.detail.get("absolute"):
            verdict = "ok" if Path(dep.name).exists() else "action"
        elif dep.kind == "env_var":
            verdict = "ok" if env.get(dep.name) else "action"
        elif dep.kind == "node":
            verdict = "ok" if (shutil.which("node") or shutil.which("npx")) \
                else "missing_installable"
        elif dep.kind == "service" and dep.name == "docker-daemon":
            verdict = "ok" if shutil.which("docker") else "missing_installable"
        finding.verdicts[host] = verdict


def collect_all(scan_result, skills_root: Path) -> List[DepFinding]:
    """All dependency findings for a scan: skills + cron + MCP + providers."""
    findings: List[DepFinding] = []
    env_names: Set[str] = set()
    for profile, cfg in scan_result.config.items():
        prefix = Path(scan_result.identity.root)
        phome = prefix if not profile else prefix / "profiles" / profile
        env_file = phome / ".env"
        if env_file.is_file():
            from talaria.model.secrets_registry import is_secret_env_name  # noqa: F401
            try:
                for line in env_file.read_text(encoding="utf-8-sig",
                                               errors="replace").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        env_names.add(line.split("=", 1)[0].strip())
            except OSError:
                pass
        findings.extend(mcp_dependencies(cfg, profile, env_names))
    for profile, jobs in scan_result.cron_jobs.items():
        for job in jobs:
            findings.extend(job_dependencies(job, profile))
    for art in scan_result.artifacts:
        if art.kind == "skill-dir" and art.files:
            first = art.files[0].home_rel
            skill_rel = "/".join(first.split("/")[:3])
            prefix = Path(scan_result.identity.root)
            phome = prefix if not art.profile else prefix / "profiles" / art.profile
            findings.extend(skill_dependencies(phome / skill_rel, art.id))
    return findings
