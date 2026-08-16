"""Reports: one data model → json / md / html renderers, redaction-first (ARCH §11).

The redaction layer transforms the DATA MODEL before any renderer runs, so every surface
(HTML prose, JSON appendix, CLI text) shows the identical redacted truth; a belt pass
masks secret-shaped strings in the final artifact (R-SEC-10). HTML output is a single
self-contained file: inline CSS, restrictive CSP meta, print styles, light/dark.
"""

from __future__ import annotations

import html
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from talaria import __version__
from talaria.model.secrets_registry import mask_secret_values

REPORT_SCHEMA_VERSION = 1


@dataclass
class ReportData:
    kind: str                                   # overview|migration
    run: Dict = field(default_factory=dict)     # id, tool_version, command, mode, exit_code
    source_system: Dict = field(default_factory=dict)
    target_system: Dict = field(default_factory=dict)
    artifacts: List[dict] = field(default_factory=list)
    provenance: List[dict] = field(default_factory=list)
    dependencies: List[dict] = field(default_factory=list)
    touchpoints: List[dict] = field(default_factory=list)
    rewrites: List[dict] = field(default_factory=list)
    exclusions: List[dict] = field(default_factory=list)
    scrubs: List[dict] = field(default_factory=list)
    conflicts: List[dict] = field(default_factory=list)
    checks: List[dict] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    actions: List[dict] = field(default_factory=list)
    checklist: List[dict] = field(default_factory=list)
    counts: Dict = field(default_factory=dict)
    soul_quote: str = ""
    redaction: str = "default"                  # default|none|strict

    def to_json(self) -> dict:
        return {
            "schema_version": REPORT_SCHEMA_VERSION,
            "kind": self.kind, "run": self.run,
            "source_system": self.source_system, "target_system": self.target_system,
            "artifacts": self.artifacts, "provenance": self.provenance,
            "dependencies": self.dependencies, "touchpoints": self.touchpoints,
            "rewrites": self.rewrites, "exclusions": self.exclusions,
            "scrubs": self.scrubs, "conflicts": self.conflicts, "checks": self.checks,
            "failures": self.failures, "actions": self.actions,
            "checklist": self.checklist, "counts": self.counts,
            "soul_quote": self.soul_quote, "redaction": {"mode": self.redaction},
        }


# --------------------------------------------------------------------------- redaction

def redact(data: ReportData, mode: str = "default") -> ReportData:
    """Transform the data model in place-copy; identical for every renderer."""
    if mode == "none":
        data.redaction = "none"
        return data
    payload = json.dumps(data.to_json())
    home = str(Path.home())
    user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
    payload = payload.replace(json.dumps(home)[1:-1], "~")
    if user and len(user) > 1:
        payload = re.sub(re.escape(user), "‹user›", payload)
    payload = mask_secret_values(payload)
    restored = json.loads(payload)
    out = ReportData(kind=restored["kind"])
    out.run = restored["run"]
    out.source_system = restored["source_system"]
    out.target_system = restored["target_system"]
    out.artifacts = restored["artifacts"]
    out.provenance = restored["provenance"]
    out.dependencies = restored["dependencies"]
    out.touchpoints = restored["touchpoints"]
    out.rewrites = restored["rewrites"]
    out.exclusions = restored["exclusions"]
    out.scrubs = restored["scrubs"]
    out.conflicts = restored["conflicts"]
    out.checks = restored["checks"]
    out.failures = restored["failures"]
    out.actions = restored["actions"]
    out.checklist = restored["checklist"]
    out.counts = restored["counts"]
    out.soul_quote = "" if mode == "strict" else restored.get("soul_quote", "")
    out.redaction = mode
    return out


# --------------------------------------------------------------------------- builders

def build_overview(scan_result, provenances: List[dict], dep_findings: List[dict],
                   config_diff: Optional[dict] = None) -> ReportData:
    """The System Overview — the brief's 'comprehensive overview' (R-REPORT-02)."""
    ident = scan_result.identity
    data = ReportData(kind="overview")
    data.run = {"id": f"overview-{int(time.time())}", "tool_version": __version__,
                "mode": "overview", "generated_at": time.strftime("%Y-%m-%d %H:%M")}
    data.source_system = ident.to_json()
    data.artifacts = [a.to_json() for a in scan_result.artifacts]
    data.provenance = provenances
    data.dependencies = dep_findings
    data.touchpoints = [t.to_json() for t in scan_result.touchpoints]
    data.exclusions = [{"id": k, "count": v}
                       for k, v in sorted(scan_result.excluded_counts.items())]
    if config_diff:
        data.counts["config_diff"] = config_diff

    total = len(scan_result.artifacts)
    unexplained = sum(1 for a in scan_result.artifacts
                      if a.kind == "unrecognized" and not a.reasons)
    data.counts.update({
        "artifacts": total,
        "files": scan_result.scanned_files,
        "bytes": scan_result.scanned_bytes,
        "unexplained": unexplained,
        "profiles": 1 + len(ident.profiles),
        "warnings": len(scan_result.warnings),
    })
    soul = Path(ident.root) / "SOUL.md"
    try:
        for line in soul.read_text(encoding="utf-8-sig",
                                   errors="replace").splitlines():
            line = line.strip().lstrip("# ")
            if line:
                data.soul_quote = line[:120]
                break
    except OSError:
        pass
    return data


def build_migration(outcome_json: dict, manifest: dict, checks: List[dict],
                    actions: List[dict]) -> ReportData:
    data = ReportData(kind="migration")
    data.run = {"id": outcome_json.get("txn_id", ""), "tool_version": __version__,
                "mode": outcome_json.get("status", ""),
                "exit_code": outcome_json.get("exit_code", 0),
                "generated_at": time.strftime("%Y-%m-%d %H:%M")}
    data.source_system = manifest.get("source", {})
    data.artifacts = manifest.get("artifacts", [])
    data.rewrites = (outcome_json.get("plan") or {}).get("entries", [])
    data.conflicts = outcome_json.get("conflicts", [])
    data.scrubs = outcome_json.get("scrubs", [])
    data.failures = outcome_json.get("failures", [])
    data.checks = checks
    data.actions = actions
    data.checklist = manifest.get("checklist", {}).get("items", [])
    data.counts = {
        "placed": len(outcome_json.get("placed", [])),
        "skipped": len(outcome_json.get("skipped", [])),
        "conflicts": len(outcome_json.get("conflicts", [])),
    }
    data.exclusions = [
        {"id": s.get("reason", ""), "path": s.get("path", "")}
        for s in outcome_json.get("skipped", [])]
    return data


# --------------------------------------------------------------------------- renderers

def render_json(data: ReportData) -> str:
    return json.dumps(data.to_json(), indent=1, ensure_ascii=False)


def render_md(data: ReportData) -> str:
    lines = [f"# Talaria {data.kind.title()} Report",
             "",
             f"Generated by talaria {__version__} — {data.run.get('generated_at', '')}",
             ""]
    if data.kind == "migration":
        lines += [f"**Outcome:** {data.run.get('mode', '')} "
                  f"(exit {data.run.get('exit_code', 0)})", ""]
    counts = data.counts
    if counts:
        lines.append("## At a glance")
        for key, value in counts.items():
            if isinstance(value, dict):
                continue
            lines.append(f"- **{key}**: {value:,}" if isinstance(value, int)
                         else f"- **{key}**: {value}")
        lines.append("")
    if data.provenance:
        lines.append("## Skills by provenance")
        by_tag: Dict[str, List[str]] = {}
        for p in data.provenance:
            by_tag.setdefault(p.get("tag", "?"), []).append(p.get("name", "?"))
        for tag, names in sorted(by_tag.items()):
            lines.append(f"- **{tag}** ({len(names)}): " + ", ".join(sorted(names)[:12])
                         + (" …" if len(names) > 12 else ""))
        lines.append("")
    if data.checks:
        lines.append("## Checks")
        for c in data.checks:
            mark = {"ok": "✓", "warn": "!", "fail": "✗"}.get(c.get("status"), "·")
            lines.append(f"- {mark} {c.get('title')}: {c.get('detail', '')}")
        lines.append("")
    if data.actions:
        lines.append("## Your checklist")
        for a in data.actions:
            cmd = f" — `{a.get('command')}`" if a.get("command") else ""
            lines.append(f"- [ ] **{a.get('verb')}**: {a.get('title')}{cmd}")
        lines.append("")
    if data.failures:
        lines.append("## Failures")
        for f in data.failures:
            lines.append(f"- {f}")
        lines.append("")
    return "\n".join(lines)


_CSS = """
:root { --bg:#f4f1e9; --fg:#1b1a17; --muted:#726e64; --line:#e2ddd0; --card:#fbfaf6;
        --raised:#f0ece1; --ok:#1a7f37; --warn:#9a6700; --fail:#c0392f;
        --gold:#8a6508; --gold-soft:rgba(138,101,8,0.09); color-scheme:light; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#07070d; --fg:#e8e4dc; --muted:#9a968e; --line:#1e1e30; --card:#0f0f18;
          --raised:#14142a; --ok:#46c26a; --warn:#d9a62e; --fail:#ef5f57;
          --gold:#ffd700; --gold-soft:rgba(255,215,0,0.10); color-scheme:dark; } }
@font-face { font-family:'Inter'; font-weight:400 700; font-display:swap;
             src:local('Inter'); }
* { box-sizing: border-box; }
:root { --display:'Collapse','Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
body { margin:0;
       background:radial-gradient(1000px 420px at 82% -6%,var(--gold-soft),transparent 70%),var(--bg);
       color:var(--fg);
       font:15px/1.6 'Inter',-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
       -webkit-font-smoothing:antialiased; }
main { max-width: 60rem; margin: 0 auto; padding: 2.5rem 1.25rem 5rem; }
header.masthead { border-bottom:1px solid var(--line); padding-bottom:1.25rem;
                  margin-bottom:2rem; }
h1 { font-family:var(--display); font-size:1.75rem; font-weight:700; letter-spacing:.01em;
     line-height:1.1; margin:0 0 .3rem; }
h1 .wing { color:var(--gold); font-family:'Inter',sans-serif; }
.sub { color:var(--muted); margin:0; }
h2 { font-size:1.1rem; font-weight:600; margin:2.2rem 0 .8rem;
     border-bottom:1px solid var(--line); padding-bottom:.4rem; }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(9.5rem,1fr));
         gap:.75rem; margin:1.2rem 0; }
.tile { background:var(--raised); border:1px solid var(--line); border-radius:10px;
        padding:.85rem .95rem; }
.tile b { display:block; font-size:1.35rem; font-weight:700; font-variant-numeric:tabular-nums; }
.tile span { color:var(--muted); font-size:.82rem; }
table { border-collapse:collapse; width:100%; font-size:.88rem; }
th,td { text-align:left; padding:.42rem .6rem; border-bottom:1px solid var(--line);
        vertical-align:top; }
th { color:var(--muted); font-weight:600; }
.wrap { overflow-x:auto; }
.ok { color:var(--ok); } .warn { color:var(--warn); } .fail { color:var(--fail); }
.badge { display:inline-block; border:1px solid var(--line); border-radius:999px;
         padding:.02rem .55rem; font-size:.76rem; color:var(--muted); }
code { font-family:'JetBrains Mono','SFMono-Regular','Cascadia Code','DejaVu Sans Mono',monospace;
       background:var(--raised); border:1px solid var(--line); border-radius:5px;
       padding:.08rem .38rem; font-size:.84em; }
.quote { font-style:italic; color:var(--muted); border-left:2px solid var(--gold);
         padding-left:.8rem; margin:.9rem 0; }
footer { color:var(--muted); font-size:.8rem; margin-top:3rem;
         border-top:1px solid var(--line); padding-top:1rem; }
@media print { body { background:#fff; color:#000; } .tiles { break-inside:avoid; } }
"""


def _collapse_face() -> str:
    """Embed the Collapse brand display face (Bold) as a base64 data URI so the report's
    Talaria wordmark keeps the Nous/Hermes look while staying a single self-contained file.
    Falls back to '' (→ Inter via the --display stack) if the bundled font can't be read."""
    import base64

    try:
        from importlib.resources import files as _files
        blob = (_files("talaria.gui") / "assets" / "fonts"
                / "Collapse-Bold.woff2").read_bytes()
    except Exception:
        return ""
    b64 = base64.b64encode(blob).decode()
    return ("@font-face{font-family:'Collapse';font-weight:700;font-style:normal;"
            "font-display:swap;src:url(data:font/woff2;base64," + b64 + ") format('woff2');}")


def render_html(data: ReportData) -> str:
    e = html.escape
    title = ("System Overview" if data.kind == "overview" else "Migration Report")
    parts: List[str] = []
    parts.append("<!DOCTYPE html><html lang='en'><head><meta charset='utf-8'>")
    # data: is needed for the base64-embedded Collapse face; no network origins are allowed.
    parts.append("<meta http-equiv='Content-Security-Policy' content=\"default-src "
                 "'none'; style-src 'unsafe-inline'; font-src data:\">")
    parts.append("<meta name='viewport' content='width=device-width,initial-scale=1'>")
    parts.append(f"<title>Talaria — {e(title)}</title>")
    parts.append(f"<style>{_collapse_face()}{_CSS}</style></head><body><main>")
    parts.append("<header class='masthead'>")
    parts.append(f"<h1><span class='wing'>⤞</span> Talaria — {e(title)}</h1>")
    parts.append("<p class='sub'>Talaria moves your Hermes agent to a new computer · "
                 f"generated {e(str(data.run.get('generated_at', '')))} · "
                 f"tool {e(__version__)} · redaction: {e(data.redaction)}</p>")
    parts.append("</header>")

    if data.soul_quote:
        parts.append(f"<p class='quote'>“{e(data.soul_quote)}”</p>")

    if data.kind == "migration":
        status = str(data.run.get("mode", ""))
        cls = "ok" if status == "committed" else "fail" if "attention" in status \
            else "warn"
        parts.append(f"<p><b class='{cls}'>Outcome: {e(status)}</b> "
                     f"(exit {e(str(data.run.get('exit_code', 0)))})</p>")

    tiles = []
    for key in ("artifacts", "files", "profiles", "placed", "skipped", "conflicts",
                "unexplained", "warnings"):
        if key in data.counts and not isinstance(data.counts[key], dict):
            value = data.counts[key]
            shown = f"{value:,}" if isinstance(value, int) else str(value)
            tiles.append(f"<div class='tile'><b>{e(shown)}</b>"
                         f"<span>{e(key)}</span></div>")
    if "bytes" in data.counts:
        mib = data.counts["bytes"] / (1024 * 1024)
        tiles.append(f"<div class='tile'><b>{mib:,.1f} MiB</b><span>total size"
                     "</span></div>")
    if tiles:
        parts.append("<div class='tiles'>" + "".join(tiles) + "</div>")

    src = data.source_system
    if src:
        parts.append("<h2>Source system</h2><div class='wrap'><table>")
        rows = [("Hermes", src.get("hermes_version")),
                ("Released", src.get("release_date")),
                ("Install method", src.get("install_method")),
                ("OS / layout", f"{src.get('os', src.get('os_name', ''))} / "
                                f"{src.get('layout_family', '')}"),
                ("HERMES_HOME", src.get("hermes_home")),
                ("Git", (src.get("git_tag") or "") +
                 (" (locally modified)" if src.get("git_dirty") else "")),
                ("Config schema", src.get("config_version")),
                ("Capture mode", src.get("capture_mode"))]
        for label, value in rows:
            if value not in (None, "", " / "):
                parts.append(f"<tr><th>{e(label)}</th><td>{e(str(value))}</td></tr>")
        parts.append("</table></div>")

    if data.provenance:
        by_tag: Dict[str, List[dict]] = {}
        for p in data.provenance:
            by_tag.setdefault(p.get("tag", "?"), []).append(p)
        parts.append("<h2>Skills — stock vs yours</h2><div class='wrap'><table>"
                     "<tr><th>Provenance</th><th>Count</th><th>Skills</th></tr>")
        order = ["stock-pristine", "stock-modified", "stock-deleted", "hub-installed",
                 "org", "agent-created", "user-created"]
        for tag in order + [t for t in by_tag if t not in order]:
            if tag not in by_tag:
                continue
            names = ", ".join(sorted(p.get("name", "?") for p in by_tag[tag]))
            parts.append(f"<tr><td><span class='badge'>{e(tag)}</span></td>"
                         f"<td>{len(by_tag[tag])}</td><td>{e(names)}</td></tr>")
        parts.append("</table></div>")

    if data.dependencies:
        parts.append("<h2>Dependencies & feasibility</h2><div class='wrap'><table>"
                     "<tr><th>Needs</th><th>Kind</th><th>For</th>"
                     "<th>Verdicts</th><th>What to do</th></tr>")
        for dep in data.dependencies[:200]:
            d = dep.get("dep", {})
            verdicts = dep.get("verdicts", {})
            vs = " ".join(
                f"<span class='{_verdict_class(v)}'>{e(k)}:{e(v)}</span>"
                for k, v in sorted(verdicts.items()))
            parts.append(
                f"<tr><td><code>{e(str(d.get('name', '')))}</code></td>"
                f"<td>{e(str(d.get('kind', '')))}</td>"
                f"<td>{e(str(dep.get('artifact', '')))}</td>"
                f"<td>{vs}</td><td>{e(str(dep.get('remediation', '')))}</td></tr>")
        parts.append("</table></div>")

    if data.checks:
        parts.append("<h2>Checks</h2><div class='wrap'><table>")
        for c in data.checks:
            cls = _verdict_class(c.get("status", ""))
            mark = {"ok": "✓", "warn": "!", "fail": "✗", "info": "·"}.get(
                c.get("status"), "·")
            parts.append(f"<tr><td class='{cls}'>{mark}</td>"
                         f"<td>{e(str(c.get('title', '')))}</td>"
                         f"<td>{e(str(c.get('detail', '')))}</td></tr>")
        parts.append("</table></div>")

    if data.actions:
        parts.append("<h2>Your checklist</h2><div class='wrap'><table>")
        for a in data.actions:
            cmd = f"<code>{e(a['command'])}</code>" if a.get("command") else ""
            parts.append(f"<tr><td><b>{e(str(a.get('verb', '')))}</b></td>"
                         f"<td>{e(str(a.get('title', '')))}</td><td>{cmd}</td>"
                         f"<td>{e(str(a.get('detail', '')))}</td></tr>")
        parts.append("</table></div>")

    if data.checklist:
        parts.append("<h2>Keys to re-provide (names only — values never travel)"
                     "</h2><div class='wrap'><table>")
        for item in data.checklist:
            parts.append(f"<tr><td><code>{e(str(item.get('name', '')))}</code></td>"
                         f"<td>{e(str(item.get('file', '')))}</td></tr>")
        parts.append("</table></div>")

    if data.scrubs:
        parts.append("<h2>Scrubbed for this machine</h2><div class='wrap'><table>")
        for s in data.scrubs:
            parts.append(f"<tr><td><code>{e(str(s.get('file', '')))}</code></td>"
                         f"<td>{e(str(s.get('reason', '')))}</td></tr>")
        parts.append("</table></div>")

    if data.conflicts:
        parts.append("<h2>Conflicts</h2><div class='wrap'><table>"
                     "<tr><th>Path</th><th>Decision</th><th>Detail</th></tr>")
        for c in data.conflicts:
            parts.append(f"<tr><td><code>{e(str(c.get('path', '')))}</code></td>"
                         f"<td>{e(str(c.get('decision', '')))}</td>"
                         f"<td>{e(str(c.get('detail', '')))}</td></tr>")
        parts.append("</table></div>")

    if data.failures:
        parts.append("<h2 class='fail'>Failures</h2><ul>")
        for f in data.failures:
            parts.append(f"<li>{e(str(f))}</li>")
        parts.append("</ul>")

    if data.touchpoints:
        parts.append("<h2>Everything this install touches</h2><div class='wrap'><table>"
                     "<tr><th>Path</th><th>Seen via</th><th>Confidence</th>"
                     "<th>Note</th></tr>")
        for t in data.touchpoints[:300]:
            parts.append(
                f"<tr><td><code>{e(str(t.get('path', '')))}</code></td>"
                f"<td>{e(', '.join(t.get('provenance', [])))}</td>"
                f"<td>{e(str(t.get('confidence', '')))}</td>"
                f"<td>{e(str(t.get('verdict', '')))}</td></tr>")
        parts.append("</table></div>")

    if data.exclusions:
        parts.append("<h2>Left behind — and why</h2><div class='wrap'><table>")
        for x in data.exclusions[:200]:
            label = x.get("id") or x.get("reason", "")
            extra = x.get("path", "") or (f"{x.get('count')} file(s)"
                                          if x.get("count") else "")
            parts.append(f"<tr><td>{e(str(label))}</td><td>{e(str(extra))}</td></tr>")
        parts.append("</table></div>")

    appendix = json.dumps(data.to_json(), ensure_ascii=False).replace("</", "<\\/")
    parts.append("<footer>Nothing on the old computer was changed. Anything Talaria "
                 "changed here can be undone (<code>talaria rollback</code>). Anything "
                 "that couldn't move automatically is on the checklist above. "
                 "Print to PDF from your browser for a permanent copy.</footer>")
    parts.append(f"<script type='application/json' id='talaria-data'>{appendix}"
                 "</script>")
    parts.append("</main></body></html>")
    return "".join(parts)


def _verdict_class(verdict: str) -> str:
    if verdict in ("ok",):
        return "ok"
    if verdict in ("impossible", "fail"):
        return "fail"
    return "warn"


# --------------------------------------------------------------------------- output

def write_reports(data: ReportData, out_dir: Path, redaction: str = "default"
                  ) -> Dict[str, Path]:
    """Write report.json / summary.md / report.html (0600) under ``out_dir``."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    redacted = redact(data, redaction)
    outputs = {"json": out_dir / "report.json", "md": out_dir / "summary.md",
               "html": out_dir / "report.html"}
    renders = {"json": render_json(redacted), "md": render_md(redacted),
               "html": render_html(redacted)}
    for key, path in outputs.items():
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(renders[key])
    return outputs
