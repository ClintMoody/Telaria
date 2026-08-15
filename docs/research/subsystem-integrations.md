# Subsystem Report: External Integration Surface (Gateway, MCP, Providers, Dashboard, Browser)

All paths repo-relative to hermes-agent @ 0.20.1. Classification legend used throughout:
**(a)** safe to copy verbatim · **(b)** copy but rewrite paths/hosts · **(c)** machine-bound —
re-create on target · **(d)** secret material (encrypt in transit, 0600 on restore).

## 0. Foundation

- HERMES_HOME per-OS (hermes_constants.py:53-59); dual-layout resolver `get_hermes_dir(new, old)`
  (:259+) — older installs use flat names (`whatsapp/session`, `pairing`, `image_cache`), newer
  use `platforms/…`, `cache/…`. **Handle both layouts.**
- Profiles are separate integration universes (own .env, auth.json, mcp-tokens/, whatsapp session,
  pairing store) (:179-209).
- Canonical config surfaces: config.yaml (`mcp_servers:`, `platforms:`, `gateway:`, `dashboard:`,
  `hooks.outbound:`, `monitoring:`, `model:`, `providers:`), `.env`, `auth.json`; legacy
  `gateway.json` still read as base layer (gateway/config.py:1316-1334).
- **Canonical credential classifier lists**: `gateway/platforms/base.py:1381-1413`
  (`_ROOT_CREDENTIAL_FILES`/`_DIRS`), `hermes_cli/web_server.py:1798-1826` (+ `.git-credentials`).
- Prior art: `hermes_cli/backup.py` exclusion/import-skip/secret sets + `_external/` prefix;
  `hermes_cli/profiles.py:207` `_DEFAULT_EXPORT_EXCLUDE_ROOT`; `hermes_cli/profile_distribution.py`
  user-owned vs distribution-owned split (:49-59).

## 1. Gateway & platforms

### 1.1 Platform inventory

Built-in enum (gateway/config.py:317-347): local, telegram, discord, whatsapp, whatsapp_cloud,
slack, signal, mattermost, matrix, homeassistant, email, sms, dingtalk, api_server, webhook,
msgraph_webhook, feishu, wecom, wecom_callback, weixin, bluebubbles, qqbot, yuanbao, relay.
Plugin platforms (auto-discovered from `plugins/platforms/*/plugin.yaml`, :392-411): a2a, buzz,
dingtalk, discord, email, feishu, google_chat, homeassistant, irc, line, matrix, mattermost, ntfy,
photon, raft, simplex, slack, sms, teams, telegram, wecom, whatsapp.
Each plugin declares `requires_env` / `optional_env` in plugin.yaml — **the machine-readable
credential manifest to enumerate.** Settings merged from config.yaml + env
(gateway/config.py:1503-1560, 1892-1918).

### 1.2 Per-platform classification (highlights)

| Platform | Creds | Extra state | Class |
|---|---|---|---|
| Telegram | TELEGRAM_BOT_TOKEN | — | (a); polling conflicts if both machines run (409); webhook URL (b) |
| Discord | DISCORD_BOT_TOKEN | slash-command sync cache under gateway/ | (a); cache droppable |
| Slack | SLACK_BOT_TOKEN + SLACK_APP_TOKEN (Socket Mode) | slack_tokens.json per-team map | (a)+(d); fully portable (no public URL) |
| WhatsApp (Baileys) | allowlists | **platforms/whatsapp/session/** creds.json + Signal-protocol keys | **(c/d) device-linked**: full-account credential; concurrent run gets device unlinked; long inactivity unlinks → `hermes whatsapp` QR re-pair. Default: flag re-pair; opt-in copy with loud warning |
| WhatsApp bridge runtime | — | scripts/whatsapp-bridge/node_modules (mirrored to $HH/scripts/whatsapp-bridge when install tree read-only, whatsapp_common.py:506-549) | (c) `npm install` on target; doctor checks it (doctor.py:2225-2242) |
| WhatsApp Cloud | Meta tokens | platforms/whatsapp_cloud/media cache | (a) tokens; (b) Meta webhook URL |
| Signal | SIGNAL_HTTP_URL (default 127.0.0.1:8080) | **~/.local/share/signal-cli/ — OUTSIDE HERMES_HOME** | (c) linked secondary device + Java 17 + signal-cli; re-link QR or copy store separately (single-device only) |
| Matrix | MATRIX_HOMESERVER/ACCESS_TOKEN/DEVICE_ID | **platforms/matrix/store/ + crypto.db (Olm E2EE device keys)** | (c/d): copy whole store + keep DEVICE_ID works if source stops; concurrent run corrupts Olm. Needs mautrix[encryption]+python-olm on target |
| Teams | TEAMS_CLIENT_ID/SECRET/TENANT_ID | — | (a); (b) Azure Bot Framework endpoint re-point |
| Email/SMS/LINE | creds + host/port/public URL | — | (a)/(d); external webhook URLs (b) |
| DingTalk/Feishu/WeCom | app id+secret (Stream/WS) | — | (a) |
| Weixin | — | weixin/accounts/<id>{.json,.context-tokens.json,.sync.json} — QR-login artifacts (weixin.py:254-332,1018-1033) | (c) re-scan |
| Google Chat | SA JSON (path OR inline), events URL, Pub/Sub | per-user OAuth via /setup-files | (b) if path; (d) inline; URL (b) |
| Home Assistant | HASS_TOKEN, HASS_URL (LAN) | — | (a) token; (b) LAN URL |
| BlueBubbles | server URL+password | — | (c) requires macOS BlueBubbles server reachable |
| Photon | PHOTON_PROJECT_ID/SECRET (.env) + device token (auth.json) | runtime/photon-sidecar.json; sidecar node_modules at $HH/photon/sidecar | creds (a)/(d); runtime record + node_modules (c) |
| A2A | A2A_BEARER_TOKEN/PEER_TOKENS, host/port | agent-card at /.well-known | (d) tokens; (b) URL + hostname-derived agent name; peers re-point |
| api_server | API_SERVER_KEY, port 8642 | — | (d); (b) clients re-point |
| Inbound webhook | per-route HMAC | **webhook_subscriptions.json** | (d) copy; (b) every producer re-points |
| msgraph_webhook | Graph subscription | bound to notificationUrl, expires | (c) re-create |
| Relay | GATEWAY_RELAY_ID/SECRET/DELIVERY_KEY (.env) | — | **(c) machine-bound enrollment** — gatewayId defaults gw-<hostname>; re-run `hermes gateway enroll` |

### 1.3 Cross-platform gateway state

(a): `platforms/pairing/` (+legacy `pairing/`; {platform}-pending/approved.json, _rate_limits;
0600; authoritative grant record; dual-dir merge gateway/pairing.py:340-376),
channel_directory.json, channel_aliases.json, sticker_cache.json, feishu_*.json,
<platform>_threads.json.
(c) drop: gateway/dead_targets.json, gateway/restart_loop.json, gateway-starts.log,
gateway_state.json, pids, locks, processes.json.

### 1.4 OS-registered gateway artifacts — ALL (c), regenerate via `hermes gateway install`

- Linux systemd: `~/.config/systemd/user/<name>.service` / `/etc/systemd/system/`; name derived
  from HERMES_HOME (hermes-gateway[-profile] or short hash, gateway.py:1781-1868); unit bakes
  ExecStart python path, WorkingDirectory, PATH, VIRTUAL_ENV, HERMES_HOME (:3011-3075).
- macOS launchd: `~/Library/LaunchAgents/ai.hermes.gateway[-profile].plist` (:2622-2630, :4212+).
- Windows: schtasks `Hermes_Gateway[_suffix]` ONLOGON + Startup-folder .vbs + .cmd launcher
  (gateway_windows.py:1-21,58,290-352,518-590).
- Container/s6: /run/service scandir (service_manager.py:331-338). Linux .desktop entry with
  absolute Exec/Icon (linux_desktop_entry.py:1-50).
- Hermes refuses to bake a temp HERMES_HOME into a service (gateway.py:3169-3221) — mirror this.

## 2. MCP servers

### 2.1 Config

**Single canonical store: config.yaml `mcp_servers:`** (no ~/.hermes/mcp.json at top level).
Loader `tools/mcp_tool.py:5095-5147` (loads .env, interpolates ${VAR}, filters suspicious,
merges plugin portable servers). Writers `hermes_cli/mcp_config.py:88-104,120-150`.
Schema: stdio {command,args,env,cwd,idle_timeout_seconds,max_lifetime_seconds}; HTTP/SSE
{url,headers,transport,ssl_verify,client_cert,client_key,skip_preflight,identity_header};
common {enabled,timeout,connect_timeout,keepalive_interval,tools.{include,exclude,prompts,
resources},auth:oauth,oauth.*,trust,sampling,elicitation,supports_parallel_tool_calls}
(website/docs/reference/mcp-config-reference.md:17-76).
**Interpolation = migration-friendly**: `${VAR}`/`${env:VAR}`, `${userHome}`,
`${workspaceFolder}`, `${pathSeparator}` (:78-110). Literal absolute paths = (b).
Agent Plugins carry their own `mcp.json` ($schema agent-plugins.org 1.0.0) expanded against
`${PLUGIN_ROOT}`/`${PLUGIN_DATA}` — auto-rewrites on target = (a) (agent_plugins.py:22,436-500;
plugins.py:4726,4753-4763).

### 2.2 OAuth state

`$HH/mcp-tokens/`: `<server>.json` (tokens), `<server>.client.json` (dynamic client reg —
**embeds loopback redirect port**; reused so client_id keeps matching, mcp_oauth.py:245-277,
1052-1099), `<server>.meta.json`. 0600 atomic (:400-420). (d); recovery cheap: `hermes mcp login/
reauth --all` (mcp_config.py:787-959). **Always emit "reauth if 401s" in the checklist.**
API-key style: config gets `Bearer ${MCP_<NAME>_API_KEY}`, raw token in .env (:153-196).

### 2.3 optional-mcps catalog

Root = optional-mcps/ ("presence = approval", mcp_catalog.py:4-11,137-141); manifest.yaml v1
{name,description,source,transport,install,auth,tools.default_enabled,post_install}; install flow
:722-808 (clone→bootstrap→creds→write config→probe→tool checklist); ${INSTALL_DIR} =
$HH/mcp-installs/<name> (:384-389,473-480).
comfy-cloud/figma/linear: remote HTTP + OAuth → (a)/(d). Note figma forces client_name
"Claude Code" (Figma allowlists exact names). n8n: stdio git-install with baked venv path →
**(c) reinstall on target** (`hermes mcp install official/n8n`); N8N_BASE_URL localhost (b).
unreal-engine: 127.0.0.1:8000 editor-embedded → (c) by definition. Figma desktop variant
127.0.0.1:3845 → (c).

### 2.4 Enumeration recipe (deterministic)

1. config.yaml mcp_servers per profile. 2. url→HTTP (portable) vs command→stdio (executable dep).
3. stdio runtime: npx/node→Node (managed $HH/node — never copy, re-provision); uvx/python→uv/Py;
docker→daemon; path under mcp-installs→reinstall; path under plugin root→migrates with plugin.
4. Scan all strings for ${VAR} → cross-check .env → report missing. 5. Flag literal abs paths /
localhost/127.0.0.1/LAN in command,args,cwd,url,env,ssl_verify,client_cert,client_key.
6. auth:oauth → check mcp-tokens presence → mark reauth-maybe. 7. **Re-validate on restore with
hermes_cli/mcp_security.validate_mcp_server_entry** — unvalidated writes get silently dropped at
spawn (mcp_tool.py:5068). 8. Include plugin-provided servers via
PluginManager.get_portable_mcp_servers() (plugins.py:5350-5359).

## 3. Model providers

- Abstraction providers/ + 34 bundled plugins/model-providers/ + `hermes_cli/auth.py
  PROVIDER_REGISTRY` (auth_type, api_key_env_vars, base_url_env_var);
  `hermes_cli/provider_catalog.py:22-23` — lmstudio, openai-api, tencent-tokenhub, xai-oauth have
  no plugin profile.
- Env-key inventory: ~35 providers each with 1-3 env var names (see .env.example; e.g.
  ANTHROPIC_API_KEY/ANTHROPIC_TOKEN/CLAUDE_CODE_OAUTH_TOKEN for anthropic; GOOGLE_API_KEY/
  GEMINI_API_KEY; COPILOT_GITHUB_TOKEN/GH_TOKEN/GITHUB_TOKEN; GLM_API_KEY/ZAI_API_KEY/Z_AI_API_KEY).
- **Machine-bound hazards:** LM Studio 127.0.0.1:1234 (auth.py:285-290) — (c) service; ollama/
  vllm/llamacpp alias to provider "custom" with user base_url (custom/__init__.py:84-96) — (b)/(c);
  named providers with private endpoints + extra_headers (Cloudflare Access tokens — (d),
  cli-config.yaml.example:118-134); bedrock→~/.aws + AWS_PROFILE (auth_type aws_sdk, auth.py:521,
  7122) — (c); vertex→GCP ADC — (c); azure-foundry entra_id → az login — (c); copilot-acp spawns
  external `copilot` binary — (c).
- Caches to drop: cache/local_endpoint_probes.json, cache/model_catalog.json,
  cache/openrouter_model_metadata.json, provider_models_cache.json, models_dev_cache.etag,
  context_length_cache.yaml.
- **External secret sources = best secrets migration story**: bitwarden (bws CLI auto-installed to
  ~/.hermes/bin; BWS_ACCESS_TOKEN bootstrap; caches drop), onepassword (op CLI;
  OP_SERVICE_ACCOUNT_TOKEN), command. Config (a), bootstrap token (d), CLI binary (c), caches (c).

## 4. Web dashboard

- Config only: dashboard.oauth.client_id/portal_url; **dashboard.public_url (b) — OAuth callback
  base**; oauth.self_hosted.{issuer,client_id,scopes,client_secret (d)}; basic_auth.{username,
  password|password_hash,secret} — **basic_auth.secret (d): copying preserves live sessions,
  rotating logs everyone out (often safer)**; HERMES_DASHBOARD_DRAIN_SECRET (d, fails closed
  <256 bits entropy).
- **Sessions are cookies only — nothing on disk**; users re-login. (dashboard_auth/cookies.py:
  access + 30-day refresh + routing hint; __Host-/__Secure- prefixes.)
- Port not persisted (CLI flag; relaunch re-derives, dashboard_procs.py:167).
- `hermes dashboard register` writes OAuth client id into .env from Nous token; tied to old
  deployment identity — **offer re-run on target** (dashboard_register.py:1-23,230-352).
- Drop: logs/dashboard-auth.log, dashboard-restart.log, web-ui-build-stamp.json,
  desktop-build-stamp.json (forces rebuild against target Node).

## 5. Browser plugin

- plugins/browser/ = cloud backends only (browser_use, browserbase, firecrawl) — API keys,
  fully portable (a)/(d).
- **chrome-debug/ = real Chromium profile** (browser_connect.py:132-142, --user-data-dir):
  cookies/logins encrypted with OS keyring (Keychain/DPAPI/gnome-keyring) — **do not decrypt
  cross-machine**. Default exclude; flag "re-login in browser"; opt-in copy for same-OS moves only.
- **Camoufox identity trap** (tools/browser_camofox_state.py:18-46): stable user_id =
  uuid5(NAMESPACE_URL, "camofox-user:" + str(state_dir abs path)) — **derived from absolute
  HERMES_HOME path**. Cross-machine move silently changes user_id → server hands back a fresh
  empty profile → **all browser logins vanish, no error**. Mitigation: capture source user_id,
  pin on target via `browser.camofox.user_id` / CAMOFOX_USER_ID (documented escape hatch,
  browser.md:294-296). CAMOFOX_URL localhost default (b)/(c).
- agent-browser engine: npm -g agent-browser + Chromium download — (c) reinstall; screenshots at
  cache/screenshots droppable.
- browser.cdp_url / BROWSER_CDP_URL — (b); **treat as (d) when it carries ?token=** (redact_cdp_url
  exists for this; browser_supervisor.py:42-55).

## 6. Outbound webhooks & observability

- hooks.outbound: [{url, events, secret_env|secret, matcher, timeout, name}]
  (agent/outbound_webhooks.py:32-44); HMAC-SHA256 X-Hermes-Signature-256; no runtime state.
  Config (a); secret_env must resolve in target .env (d); url (b) if host-local.
- monitoring.export.otlp: endpoint (b if localhost); headers_env maps header→ENV VAR NAME (values
  never stored — migration-friendly); needs [otlp] lazy extra (c).
- **monitoring.install_id** (agent/monitoring/policy.py:18-51): minted once into config.yaml;
  signals carry one-way hash. **Surface keep-vs-rotate decision; default keep** (machine is being
  replaced).
- Observability plugins langfuse/nemo_relay: env keys (a)/(d). telemetry/shared_metrics — (c) drop.

## 7. Consolidated classification (summary)

**(a)**: config.yaml (minus (b) keys), ${VAR}-style mcp entries, pairing stores, channel
directory/aliases, thread maps, hooks.outbound, monitoring (minus endpoint), plugin mcp.json,
memories/, skills/, cron/jobs.json, SOUL.md.
**(b)**: every absolute path across a home change (esp. POSIX↔Windows); mcp command/args/cwd/
ssl_verify/client_cert/client_key; mcp-tokens client.json loopback port; dashboard.public_url;
OIDC issuer; otlp endpoint; model.base_url local servers; HASS_URL, SIMPLEX_WS_URL,
SIGNAL_HTTP_URL, CAMOFOX_URL, N8N_BASE_URL, BROWSER_CDP_URL, A2A host/port; external webhook/
callback URLs (Telegram webhook, Twilio, LINE, Teams, WhatsApp Cloud, Google Chat, msgraph,
inbound producers); **camofox user_id pin**; Google Chat SA JSON path.
**(c)**: service units/plists/tasks/.vbs/.desktop (hermes gateway install); runtime pids/locks/
state; managed node/venvs/bins/native libs; mcp-installs (reinstall); signal-cli store; WhatsApp
session (default); Weixin sessions; Matrix crypto.db (unless wholesale+stop); relay enrollment;
dashboard OAuth client; dashboard cookie sessions; chrome-debug profile; local services (LM
Studio, ollama, n8n, Unreal, Figma desktop, Camoufox server, BlueBubbles mac server, simplex
daemon); CLIs (bws, op, copilot, buzz, agent-browser); cloud auth (~/.aws, GCP ADC, Entra);
all caches/logs/stamps.
**(d)**: .env, auth.json(+lock), .anthropic_oauth.json, credentials, mcp-tokens/**, pairing/**,
slack_tokens.json, google_* tokens, webhook_subscriptions.json, bws caches, .git-credentials,
whatsapp session/**, matrix crypto.db, weixin accounts, chrome-debug, state.db/memory_store.db/
projects.db (conversation content), config.yaml inline api_key/client_secret/extra_headers.
**Restore must chmod 0600** (zipfile drops mode bits — backup.py:132 precedent).

## 8. Recommended tool behaviours

1. Enumerate per profile. 2. Handle both dir layouts (get_hermes_dir semantics; merge split
pairing dirs). 3. Reuse backup.py exclusion sets. 4. sqlite3.backup() snapshots; skip sidecars.
5. Re-validate MCP entries on restore (else silently dropped at spawn). 6. Never bake temp/foreign
HERMES_HOME into anything (gateway.py:3169-3221 precedent). 7. **Emit a post-restore checklist**
keyed off findings: hermes mcp reauth --all, hermes gateway install, hermes gateway enroll,
hermes dashboard register, hermes whatsapp, signal-cli link, npm install (whatsapp bridge),
hermes mcp install official/n8n, hermes doctor. 8. **Warn loudly about concurrent-run hazards**
(WhatsApp/Signal/Matrix/Telegram polling/relay id): failure mode is account unlinking and split
messages, not startup errors.
