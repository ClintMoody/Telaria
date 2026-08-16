/* Talaria wizard front-end. Vanilla JS, zero dependencies, token-authed API. */
"use strict";

const $ = (sel) => document.querySelector(sel);
const screen = $("#screen");
let TOKEN = null;
let lastSeq = 0;
let pollTimer = null;
let currentJob = null;
let state = {};

/* ---------------------------------------------------------------- utilities */
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v; /* only with escaped/static input */
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child == null) continue;
    node.append(child.nodeType ? child : document.createTextNode(child));
  }
  return node;
}
const esc = (s) => String(s ?? "");
const mib = (b) => {
  if (b >= 1073741824) return (b / 1073741824).toFixed(2) + " GiB";
  if (b >= 1048576) return (b / 1048576).toFixed(1) + " MiB";
  if (b >= 1024) return (b / 1024).toFixed(0) + " KiB";
  return b + " B";
};

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json" };
  if (TOKEN) headers["X-Talaria-Token"] = TOKEN;
  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).error || detail; } catch (e) { /* noop */ }
    throw new Error(detail);
  }
  return res.json();
}

function setPromise(text) { $("#promise-strip").textContent = text; }

function showError(err) {
  const banner = el("div", { class: "error-banner" },
    el("b", {}, "Something needs attention: "), esc(err.message || err));
  screen.prepend(banner);
}

/* ---------------------------------------------------------------- event poll */
function startPolling() {
  if (pollTimer) return;
  pollTimer = setInterval(async () => {
    try {
      const data = await api(`/api/events?after=${lastSeq}`);
      for (const ev of data.events) {
        lastSeq = ev.seq;
        renderEvent(ev);
      }
      if (!data.busy && currentJob) {
        const finished = currentJob;
        currentJob = null;
        await refreshState();
        finished.onDone && finished.onDone();
      }
    } catch (e) { /* transient poll errors are fine */ }
  }, 350);
}

function renderEvent(ev) {
  const strip = $("#log-strip");
  strip.hidden = false;
  const line = $("#log-line");
  const bar = $("#log-progress");
  if (ev.kind === "progress" && ev.bytes_total) {
    bar.hidden = false;
    bar.value = Math.round((ev.bytes_done / ev.bytes_total) * 100);
    line.textContent = `${ev.phase}: ${ev.detail} — ${mib(ev.bytes_done)} of ${mib(ev.bytes_total)}`;
  } else if (ev.kind === "phase") {
    bar.hidden = true;
    line.textContent = `▸ ${ev.detail || ev.phase}`;
  } else if (ev.kind === "warn") {
    line.textContent = `! ${ev.detail}`;
  } else if (ev.kind === "error") {
    bar.hidden = true;
    line.textContent = `✗ ${ev.detail}`;
    showError({ message: ev.detail });
  } else if (ev.kind === "item") {
    line.textContent = `  ${ev.detail}`;
  } else if (ev.kind === "done") {
    line.textContent = `✓ ${ev.detail || ev.phase}`;
  }
}

async function runJob(kind, args, onDone) {
  const res = await api("/api/jobs", { method: "POST",
    body: JSON.stringify({ kind, args: args || {} }) });
  currentJob = { id: res.job_id, kind, onDone };
}

async function refreshState() { state = await api("/api/state"); return state; }

/* ---------------------------------------------------------------- screens */
function render(node) { screen.replaceChildren(node); }

function screenDetect() {
  setPromise("Nothing on this computer is changed or deleted.");
  const s = state;
  if (s.hermes_here && !(s.bundles_found || []).length) return screenPackS0();
  if (!s.hermes_here && (s.bundles_found || []).length) return screenApplyT1();
  if (s.hermes_here && (s.bundles_found || []).length) {
    render(el("div", { class: "card" },
      el("div", { class: "step-label" }, "Choose a direction"),
      el("h1", {}, "This computer has both"),
      el("p", { class: "muted" },
        `A Hermes install (${esc(s.home)}) and a bundle (${esc(s.bundles_found[0])}).`),
      el("div", { class: "btn-row" },
        el("button", { class: "btn primary big", onclick: screenPackS0 },
          "Pack up this Hermes"),
        el("button", { class: "btn big", onclick: screenApplyT1 },
          "Move the bundle in"))));
    return;
  }
  render(el("div", { class: "card center" },
    el("h1", {}, "Nothing to do here yet"),
    el("p", { class: "muted" },
      "No Hermes install and no .hermespack bundle were found."),
    el("p", { class: "small muted" },
      "To pack: run talaria on the machine where Hermes lives. To apply: put the ",
      el("code", {}, ".hermespack"), " file in your home folder and reopen.")));
}

/* ------------------------------------------------ pack flow S0..S4 */
function screenPackS0() {
  const s = state;
  render(el("div", {},
    el("div", { class: "card" },
      el("div", { class: "step-label" }, "Step 1 of 5 · Found it"),
      el("h1", {}, "Pack up this Hermes"),
      el("p", {}, `Your agent lives at `, el("code", {}, esc(s.home)), "."),
      el("p", { class: "muted" },
        "I'll read everything, show you what travels, and pack it into one file. ",
        el("b", {}, "Nothing on this computer is changed or deleted.")),
      el("div", { class: "btn-row" },
        el("button", { class: "btn primary big",
          onclick: () => { screenScanning(); runJob("scan", {}, screenPackS2); } },
          "Start — read what's here")))));
}

function screenScanning() {
  render(el("div", { class: "card center" },
    el("div", { class: "step-label" }, "Step 2 of 5 · Reading"),
    el("h1", {}, "Reading your Hermes…"),
    el("p", { class: "muted" }, "Memories, skills, scheduled tasks, conversations, connections — metadata only, read-only.")));
}

const FAMILY_LABELS = {
  "identity-memory": ["Personality & memories", false],
  "skills": ["Skills", false],
  "plugins": ["Plugins", false],
  "automations": ["Scheduled tasks", false],
  "conversations-history": ["Conversations & history", true],
  "platforms-messaging": ["Connections & pairings", true],
  "configuration": ["Settings & hooks", false],
  "boards-projects": ["Projects & boards", false],
  "external-state": ["Memory-provider data", true],
  "unrecognized": ["Other files (safety-scanned)", false],
};

function screenPackS2() {
  const scan = state.scan || {};
  const fams = scan.families || {};
  const rows = [];
  for (const [key, [label, priv]] of Object.entries(FAMILY_LABELS)) {
    const f = fams[key];
    if (!f || !f.travel) continue;
    rows.push(el("div", { class: "cat-row" },
      el("input", { type: "checkbox", checked: "", disabled: "" }),
      el("span", { class: "name" }, label,
        priv ? el("span", { class: "badge private" }, "private content") : null),
      el("span", { class: "meta" }, `${f.travel} · ${mib(f.bytes)}`)));
  }
  const excluded = Object.values(scan.excluded || {}).reduce((a, b) => a + b, 0);
  const ident = (scan.identity || {});
  render(el("div", {},
    el("div", { class: "card" },
      el("div", { class: "step-label" }, "Step 3 of 5 · What travels"),
      el("h1", {}, "Everything portable, pre-selected"),
      el("div", { class: "tiles" },
        el("div", { class: "tile" }, el("b", {}, esc(ident.hermes_version || "?")),
          el("span", {}, "Hermes version")),
        el("div", { class: "tile" }, el("b", {}, (scan.files || 0).toLocaleString()),
          el("span", {}, "files read")),
        el("div", { class: "tile" }, el("b", {}, mib(scan.bytes || 0)),
          el("span", {}, "total size"))),
      ...rows,
      el("div", { class: "dismiss-card" }, "ℹ️",
        el("span", {},
          `Won't travel: ${excluded} machine-specific file(s) — running services, `,
          "device pairings, caches. The finish checklist covers re-creating each one. ",
          "Nothing silently vanishes.")),
      (scan.warnings || []).length
        ? el("div", { class: "dismiss-card" }, "⚠️",
            el("span", {}, esc(scan.warnings[0])))
        : null,
      el("div", { class: "dismiss-card" }, "🧭",
        el("span", {}, "Optional: your agent can help find things it touches outside ",
          "Hermes. ", el("button", { class: "linkish", onclick: deepscanCard },
            "Generate the Deep-Scan skill"), " — advisory only, skippable."),
      ),
      el("div", { class: "btn-row" },
        el("button", { class: "btn primary big", onclick: screenPackS3 },
          "Looks right — continue"),
        el("span", { class: "muted small" },
          "fine-grained choices: talaria pack --include/--exclude")))));
}

function deepscanCard() {
  runJob("deepscan-generate", {}, async () => {
    alert("Observation skill written to ~/talaria-deepscan/. Copy it to the OLD " +
      "machine's skills folder, ask your Hermes to run it, then ingest the JSON " +
      "with: talaria deepscan ingest <file>. Its findings are suggestions you " +
      "approve — never automatic.");
  });
}

function screenPackS3() {
  let mode = "checklist";
  const pass1 = el("input", { type: "password", placeholder: "vault passphrase" });
  const pass2 = el("input", { type: "password", placeholder: "once more" });
  const vaultBody = el("div", { class: "paste", style: "display:none" }, pass1, pass2);
  const choices = el("div", {},
    el("label", { class: "choice selected", onclick: (e) => pick("checklist", e) },
      el("input", { type: "radio", name: "keys", checked: "" }),
      el("div", { class: "body" },
        el("b", {}, "Checklist (recommended)"),
        el("span", { class: "muted" },
          "Keys stay OUT of the bundle. You paste them on the new machine from a ",
          "generated checklist — like carrying your keys in your pocket."))),
    el("label", { class: "choice", onclick: (e) => pick("vault", e) },
      el("input", { type: "radio", name: "keys" }),
      el("div", { class: "body" },
        el("b", {}, "Locked vault"),
        el("span", { class: "muted" },
          "Keys travel inside the bundle, encrypted (scrypt + AES-256-GCM) under a ",
          "passphrase you choose. Anyone with the file still can't read them."),
        vaultBody)));
  function pick(m, e) {
    mode = m;
    for (const c of choices.querySelectorAll(".choice")) c.classList.remove("selected");
    e.currentTarget.classList.add("selected");
    e.currentTarget.querySelector("input").checked = true;
    vaultBody.style.display = m === "vault" ? "flex" : "none";
  }
  render(el("div", { class: "card" },
    el("div", { class: "step-label" }, "Step 4 of 5 · Keys & passwords — your one decision"),
    el("h1", {}, "How should your keys move?"),
    el("p", { class: "muted" },
      "Your conversations and memories are private content and travel in the bundle ",
      "either way — treat the file like a private notebook."),
    choices,
    el("div", { class: "btn-row" },
      el("button", { class: "btn primary big", onclick: async () => {
        try {
          if (mode === "vault") {
            if (!pass1.value) throw new Error("choose a passphrase (empty is refused)");
            if (pass1.value !== pass2.value) throw new Error("passphrases don't match");
            await api("/api/vault-passphrase", { method: "POST",
              body: JSON.stringify({ passphrase: pass1.value }) });
          } else {
            await api("/api/vault-passphrase", { method: "POST",
              body: JSON.stringify({ passphrase: null }) });
          }
          screenPacking();
          runJob("pack", {}, screenPackS4);
        } catch (e) { showError(e); }
      } }, "Pack it up"))));
}

function screenPacking() {
  setPromise("Reading only — the original is never modified.");
  render(el("div", { class: "card center" },
    el("div", { class: "step-label" }, "Step 5 of 5 · Packing"),
    el("h1", {}, "Packing your Hermes into one file…"),
    el("p", { class: "muted" }, "Databases get safe snapshots; every file is checksummed; the bundle is verified before it's finished.")));
}

function screenPackS4() {
  const pack = state.pack;
  if (!pack) { showError({ message: "packing did not finish — see the log line" }); return screenPackS2(); }
  const checklistName = pack.bundle + ".checklist.html";
  render(el("div", {},
    el("div", { class: "boarding" },
      el("h1", {}, "🎫 Boarding pass"),
      el("div", { class: "row" }, el("span", {}, "bundle"),
        el("code", {}, esc(pack.bundle))),
      el("div", { class: "row" }, el("span", {}, "size"),
        el("span", {}, mib(pack.bytes))),
      el("div", { class: "row" }, el("span", {}, "keys checklist"),
        el("code", {}, esc(checklistName)))),
    el("div", { class: "card" },
      el("h2", {}, "Next steps"),
      el("ul", { class: "plain" },
        el("li", {}, "1. Copy BOTH files to the new computer (USB, scp, cloud drive)."),
        el("li", {}, "2. Install talaria there: ", el("code", {}, "pipx install talaria-migration")),
        el("li", {}, "3. Run: ", el("code", {}, "talaria"), " — it finds the bundle and walks you in.")),
      el("h2", {}, "Retiring this machine?"),
      el("p", { class: "muted small" },
        "Keep this Hermes OFF once the new one starts — they share the same accounts ",
        "and pairings. Your files here are untouched either way."))));
}

/* ------------------------------------------------ apply flow T1..T4 */
function screenApplyT1() {
  const bundle = (state.bundles_found || [])[0];
  setPromise("Anything we change on this computer can be undone.");
  render(el("div", { class: "card" },
    el("div", { class: "step-label" }, "Step 1 of 4 · Bundle found"),
    el("h1", {}, "Move this Hermes in"),
    el("p", {}, el("code", {}, esc(bundle))),
    state.hermes_here ? null : el("p", { class: "muted" },
      "Hermes isn't installed here yet. Install it first (official command, copy it — ",
      "I never run installers): ",
      el("code", {}, "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"),
      " — then stop it: ", el("code", {}, "hermes gateway stop")),
    el("div", { class: "btn-row" },
      el("button", { class: "btn primary big", onclick: () => {
        render(el("div", { class: "card center" }, el("h1", {}, "Checking this machine…")));
        runJob("preflight", { bundle }, screenApplyT2);
      } }, "Check this machine"))));
}

const WHO_ACTS = {
  ok: "Ready to move in", warn: "Worth knowing",
  consent: "Needs your OK", refuse: "Blocks the move",
};

function screenApplyT2() {
  const pf = state.preflight;
  if (!pf) { showError({ message: "preflight did not finish" }); return screenApplyT1(); }
  const groups = { refuse: [], consent: [], warn: [], ok: [] };
  for (const g of pf.gates) (groups[g.status] || groups.warn).push(g);
  const sections = [];
  for (const status of ["refuse", "consent", "warn", "ok"]) {
    if (!groups[status].length) continue;
    sections.push(el("h2", {}, WHO_ACTS[status]));
    for (const g of groups[status]) {
      sections.push(el("div", { class: `gate ${status}` },
        el("span", { class: "mark" },
          { ok: "✓", warn: "!", consent: "?", refuse: "✗" }[status]),
        el("span", {}, el("b", {}, esc(g.title)),
          g.detail ? ` — ${esc(g.detail)}` : "",
          g.fix && status !== "ok" ? el("span", { class: "fix" }, `fix: ${esc(g.fix)}`) : null)));
    }
  }
  const blocked = groups.refuse.length > 0;
  const hasUnrecognized = pf.gates.some((g) => g.id === "PF-17");
  const vaultPass = el("input", { type: "password",
    placeholder: "vault passphrase (leave blank to keep keys on the checklist)" });
  const vaultRow = state.vault_present
    ? el("div", { class: "card" },
        el("h2", {}, "This bundle has a locked vault"),
        el("p", { class: "muted small" },
          "Enter the passphrase to restore the encrypted keys, or leave it blank and ",
          "paste keys from the checklist instead."),
        el("div", { class: "paste" }, vaultPass))
    : null;
  render(el("div", {},
    el("div", { class: "card" },
      el("div", { class: "step-label" }, "Step 2 of 4 · Preflight"),
      el("h1", {}, blocked ? "Not yet — fix the blockers first" : "This machine is ready"),
      ...sections),
    vaultRow,
    el("div", { class: "card" },
      el("h2", {}, "Ready when you are"),
      el("p", { class: "muted small" },
        "Applying a bundle installs things this machine will run (skills, scripts, ",
        "plugins, MCP commands) and covers the disclosed lists above. A full safety ",
        "copy is made first; one click undoes everything."),
      el("div", { class: "btn-row" },
        el("button", { class: "btn primary big", disabled: blocked ? "" : null,
          onclick: async () => {
            if (state.vault_present && vaultPass.value) {
              await api("/api/vault-passphrase", { method: "POST",
                body: JSON.stringify({ passphrase: vaultPass.value }) });
            }
            setPromise("A safety copy is made before anything changes — undo any time.");
            render(el("div", { class: "card center" },
              el("h1", {}, "Moving your Hermes in…"),
              el("p", { class: "muted" },
                "ready → safety copy → moving in → making it at home → double-checking")));
            runJob("apply", { consent: true, include_unrecognized: hasUnrecognized },
                   screenApplyT4);
          } }, "Move everything in"),
        blocked ? el("span", { class: "muted small" }, "resolve the ✗ items, then re-run") : null))));
}

function screenApplyT4() {
  const outcome = state.apply;
  if (!outcome) { showError({ message: "apply did not report an outcome" }); return; }
  if (outcome.status === "rolled_back") {
    render(el("div", { class: "card" },
      el("h1", {}, "Rolled back — this machine is unchanged"),
      el("p", {}, esc((outcome.failures || [])[0] || "")),
      el("p", { class: "muted small" }, "Fix the cause and try again; the bundle is untouched.")));
    return;
  }
  if (outcome.status === "needs_attention") {
    render(el("div", { class: "card" },
      el("h1", {}, "Needs attention — nothing was deleted"),
      el("p", {}, "Rollback couldn't finish. Your safety copy and journal:"),
      el("p", {}, el("code", {}, esc(outcome.backup_dir))),
      el("p", {}, el("code", {}, esc(outcome.journal)))));
    return;
  }
  render(el("div", {},
    el("div", { class: "card" },
      el("div", { class: "step-label" }, "Step 4 of 4 · Done"),
      el("h1", {}, `✓ Moved in — ${(outcome.placed || []).length} files, all verified`),
      el("p", { class: "muted" },
        "Report saved under migration/talaria/ in your Hermes folder. ",
        el("button", { class: "linkish", onclick: async () => {
          const res = await fetch("/api/report/latest",
            { headers: { "X-Talaria-Token": TOKEN } });
          const html = await res.text();
          const w = window.open("", "_blank");
          w.document.write(html);
        } }, "open it"))),
    el("div", { class: "card" },
      el("h2", {}, "Keys & passwords — paste them in"),
      el("p", { class: "muted small" },
        "Values never traveled in the bundle. Paste each one; it lands in .env with ",
        "tight permissions and is never shown again."),
      secretPasteRows()),
    el("div", { class: "card" },
      el("h2", {}, "Before you start Hermes here"),
      el("ul", { class: "plain" },
        el("li", {}, "[ ] Register the gateway: ", el("code", {}, "hermes gateway install")),
        el("li", {}, "[ ] Re-pair device-linked chats (WhatsApp/Signal): ",
          el("code", {}, "hermes whatsapp")),
        el("li", {}, "[ ] Refresh MCP logins: ", el("code", {}, "hermes mcp reauth --all")),
        el("li", {}, "[ ] Let Hermes check itself: ", el("code", {}, "hermes doctor"))),
      el("p", { class: "muted small" },
        el("b", {}, "Turn the OLD machine's Hermes off before starting it here"),
        " — they share accounts and pairings."),
      el("div", { class: "btn-row" },
        el("button", { class: "btn", onclick: () => runJob("rollback", {}, () => {
          alert("Restored the pre-apply state. The safety copy remains on disk.");
        }) }, "Undo everything")))));
}

function secretPasteRows() {
  const wrap = el("div", {});
  // The bundle's checklist (names only) was captured at preflight time.
  const items = state.checklist || [];
  const rows = items.length ? items
    : [{ name: "OPENROUTER_API_KEY" }, { name: "TELEGRAM_BOT_TOKEN" }];
  for (const item of rows) {
    const isFile = item.name.includes(".") || item.name.includes("/");
    if (isFile) {
      // File-shaped secrets (auth.json, token stores) can't be pasted into .env —
      // they move by hand, and only if wanted.
      wrap.append(el("div", { class: "check-card" },
        el("input", { type: "checkbox" }),
        el("div", { class: "body" },
          el("code", {}, esc(item.name)),
          el("div", { class: "muted small" },
            "a credential file — copy it from the old machine yourself if you ",
            "want it (or just log in again here: usually easier)"))));
      continue;
    }
    const input = el("input", { type: "password", placeholder: "paste value…" });
    const btn = el("button", { class: "btn", onclick: async () => {
      try {
        await api("/api/secrets", { method: "POST",
          body: JSON.stringify({ name: item.name, value: input.value }) });
        input.value = "";
        btn.textContent = "✓ saved";
        btn.disabled = true;
      } catch (e) { showError(e); }
    } }, "Save");
    wrap.append(el("div", { class: "check-card" },
      el("input", { type: "checkbox" }),
      el("div", { class: "body" },
        el("code", {}, esc(item.name)),
        el("div", { class: "paste" }, input, btn))));
  }
  return wrap;
}

/* ---------------------------------------------------------------- boot */
async function boot() {
  const hash = new URLSearchParams(location.hash.slice(1));
  const bootstrap = hash.get("t");
  history.replaceState(null, "", "/");  // drop the token from the URL bar
  try {
    const res = await api("/api/session", { method: "POST",
      body: JSON.stringify({ bootstrap }) });
    TOKEN = res.token;
  } catch (e) {
    render(el("div", { class: "card center" },
      el("h1", {}, "Session unavailable"),
      el("p", { class: "muted" },
        "Reopen the exact link the terminal printed — it carries a one-time key, ",
        "and only one browser session may drive a migration.")));
    return;
  }
  await refreshState();
  $("#foot-version").textContent =
    `talaria ${state.tool_version} · localhost only · token-authed`;
  startPolling();
  screenDetect();
}

$("#btn-quit").addEventListener("click", async () => {
  try { await api("/api/shutdown", { method: "POST", body: "{}" }); } catch (e) {}
  render(el("div", { class: "card center" }, el("h1", {}, "Closed"),
    el("p", { class: "muted" }, "You can close this tab.")));
});

boot();
