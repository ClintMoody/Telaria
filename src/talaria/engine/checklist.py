"""Checklists: the Secrets Handoff and the post-restore action cards (ARCH §11.3).

Names + where-used + provider URLs — never values (R-SEC-03). Card state persists in
checklist.json (check-state only) so progress survives closing the tool.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from talaria.model.secrets_registry import is_secret_env_name

#: Known provider URLs for common env keys (checklist convenience).
PROVIDER_URLS = {
    "OPENROUTER_API_KEY": "https://openrouter.ai/settings/keys",
    "OPENAI_API_KEY": "https://platform.openai.com/api-keys",
    "ANTHROPIC_API_KEY": "https://console.anthropic.com/settings/keys",
    "TELEGRAM_BOT_TOKEN": "https://t.me/BotFather",
    "DISCORD_BOT_TOKEN": "https://discord.com/developers/applications",
    "SLACK_BOT_TOKEN": "https://api.slack.com/apps",
    "GEMINI_API_KEY": "https://aistudio.google.com/apikey",
    "GROQ_API_KEY": "https://console.groq.com/keys",
    "HF_TOKEN": "https://huggingface.co/settings/tokens",
    "EXA_API_KEY": "https://dashboard.exa.ai/api-keys",
    "FIRECRAWL_API_KEY": "https://www.firecrawl.dev/app/api-keys",
    "FAL_KEY": "https://fal.ai/dashboard/keys",
    "ELEVENLABS_API_KEY": "https://elevenlabs.io/app/settings/api-keys",
    "GITHUB_TOKEN": "https://github.com/settings/tokens",
}


@dataclass
class Card:
    id: str
    verb: str                 # one verb per card (R-UX-06)
    title: str
    command: Optional[str] = None
    url: Optional[str] = None
    detail: str = ""
    done: bool = False
    kind: str = "action"      # action|secret|repair

    def to_json(self) -> dict:
        return {"id": self.id, "verb": self.verb, "title": self.title,
                "command": self.command, "url": self.url, "detail": self.detail,
                "done": self.done, "kind": self.kind}


def secrets_cards(checklist_items: List[dict]) -> List[Card]:
    cards: List[Card] = []
    seen = set()
    for item in checklist_items:
        name = item.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        if item.get("file", "").endswith(".env") and not is_secret_env_name(name) \
                and not item.get("secret"):
            continue
        profile = item.get("profile") or ""
        where = item.get("file", ".env") + (f" (profile {profile})" if profile else "")
        cards.append(Card(
            id=f"secret-{name.lower()}", verb="Paste", kind="secret",
            title=name,
            url=PROVIDER_URLS.get(name),
            detail=f"used by {where}; get it from the old machine's {item.get('file', '.env')} "
                   "or the provider dashboard"))
    return cards


def post_restore_cards(manifest: dict, outcome_json: dict,
                       target_os: str = "linux") -> List[Card]:
    """Action cards keyed to real findings — exact commands, one verb each."""
    cards: List[Card] = []
    source = manifest.get("source") or {}

    cards.append(Card("gateway-install", "Register",
                      "Register the gateway with this machine",
                      command="hermes gateway install",
                      detail="services/units are never copied — they bake old-machine "
                             "paths; this regenerates them here"))

    skipped = {s.get("path", ""): s.get("reason", "")
               for s in outcome_json.get("skipped", [])}
    if any("device-linked" in reason for reason in skipped.values()):
        cards.append(Card("whatsapp-pair", "Re-pair", "Re-pair WhatsApp on this machine",
                          command="hermes whatsapp",
                          detail="WhatsApp sessions are device-linked; copying them "
                                 "fights for the account's device slot — re-pairing "
                                 "takes about a minute", kind="repair"))

    refs = manifest.get("checklist", {}).get("items", [])
    mcp_oauth = [i for i in refs if str(i.get("name", "")).startswith("mcp-tokens")]
    art_kinds = {a.get("kind") for a in manifest.get("artifacts", [])
                 if a.get("files")}
    if "mcp-tokens" in art_kinds or mcp_oauth:
        cards.append(Card("mcp-reauth", "Reauthorize", "Refresh MCP server logins",
                          command="hermes mcp reauth --all",
                          detail="OAuth tokens can be machine- or session-bound; a "
                                 "refresh guarantees they work here"))

    if source.get("lazy_features"):
        feats = ", ".join(source["lazy_features"])
        cards.append(Card("lazy-features", "Reinstall",
                          "Re-enable optional Hermes features",
                          command="hermes setup --repair",
                          detail=f"the old machine had extras enabled ({feats}); "
                                 "nothing records them in state, so re-ensure them"))

    if any("whatsapp-bridge" in path for path in skipped):
        cards.append(Card("bridge-npm", "Install", "Rebuild the WhatsApp bridge",
                          command="npm install",
                          detail="run inside scripts/whatsapp-bridge/ — node_modules "
                                 "never travels"))

    if manifest.get("capture_mode") == "live":
        cards.append(Card("live-capture", "Check", "Review live-capture caveat",
                          detail="the bundle was packed while Hermes ran on the old "
                                 "machine; if anything looks stale, re-pack quiesced",
                          kind="repair"))

    checkout = source.get("git_dirty")
    if checkout:
        cards.append(Card("checkout-patch", "Review",
                          "Re-apply your Hermes code tweaks",
                          command="talaria inspect <bundle> --cat meta/checkout.patch",
                          detail="the old checkout had local modifications; the patch "
                                 "traveled in the bundle — apply it with git if wanted"))

    cards.append(Card("doctor", "Run", "Let Hermes check itself",
                      command="hermes doctor",
                      detail="upstream's own diagnostics, after everything above"))
    return cards


def save_state(path: Path, cards: List[Card]) -> None:
    """Persist check-state only (never values) — R-SEC-03/06."""
    state = {c.id: c.done for c in cards}
    path.parent.mkdir(parents=True, exist_ok=True)
    import os as _os

    fd = _os.open(path, _os.O_CREAT | _os.O_WRONLY | _os.O_TRUNC, 0o600)
    with _os.fdopen(fd, "w") as fh:
        json.dump({"version": 1, "done": state}, fh, indent=1)


def load_state(path: Path, cards: List[Card]) -> None:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        done = data.get("done", {})
        for card in cards:
            if done.get(card.id):
                card.done = True
    except (OSError, ValueError):
        pass
