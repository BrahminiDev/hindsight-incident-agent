const $ = (id) => document.getElementById(id);

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

// Minimal markdown for the reflect output: headings, bullets, bold, inline code, INC ids.
function md(text) {
  const inline = (s) =>
    esc(s)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\b(INC-\d{4})\b/g, '<span class="inc mono">$1</span>');
  let html = "", inList = false;
  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const bullet = line.match(/^\s*[-*]\s+(.*)/);
    if (bullet) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(bullet[1])}</li>`;
      continue;
    }
    if (inList) { html += "</ul>"; inList = false; }
    const h = line.match(/^(#{1,4})\s+(.*)/);
    if (h) html += `<h3>${inline(h[2])}</h3>`;
    else if (line.trim()) html += `<p>${inline(line)}</p>`;
  }
  return html + (inList ? "</ul>" : "");
}

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ? JSON.stringify(body.detail) : res.statusText);
  return body;
}

function toast(msg) {
  const t = $("toast");
  t.textContent = msg;
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), 3500);
}

// ---- tabs -------------------------------------------------------------------
document.querySelectorAll(".tab").forEach((btn) =>
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
    document.querySelectorAll(".tab-panel").forEach((p) => (p.hidden = p.id !== `tab-${btn.dataset.tab}`));
  })
);

// ---- health + demo alerts ---------------------------------------------------
api("/api/health").then((h) => {
  $("health").innerHTML = h.ok
    ? `<span class="ok">● connected</span><br>bank <code>${esc(h.bank_id)}</code> · ${esc(h.model)}`
    : `<span class="bad">● not configured</span><br>missing ${esc(h.missing.join(", "))}`;
}).catch(() => ($("health").innerHTML = '<span class="bad">● backend unreachable</span>'));

api("/api/demo-alerts").then((alerts) => {
  for (const a of alerts) {
    const chip = document.createElement("button");
    chip.className = "chip";
    chip.textContent = a.label;
    chip.onclick = () => { $("alert").value = a.alert; $("service").value = a.service; };
    $("demo-alerts").appendChild(chip);
  }
});

// ---- triage -----------------------------------------------------------------
let lastTriage = null;

function renderCard(result, withMemory) {
  const t = result.triage;
  const list = (items, cls = "") =>
    items.length ? `<ol class="${cls}">${items.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>` : '<p class="muted">—</p>';

  const sims = t.similar_incidents.length
    ? `<div class="section-label">Similar past incidents</div>` +
      t.similar_incidents.map((s) => `<div class="sim-row"><span class="inc mono sim">${esc(s.id)}</span>
        <span class="why">${esc(s.when)}${s.when && s.why_similar ? " · " : ""}${esc(s.why_similar)}</span></div>`).join("")
    : "";

  const avoid = t.avoid.length
    ? `<div class="section-label">Do not repeat</div><ul class="avoid">${t.avoid.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
    : "";

  const recalled = withMemory
    ? `<details class="recalled"><summary>What Hindsight recalled — ${result.memories.length} memories in ${result.recall_ms} ms</summary>
        ${result.memories.map((m) => `<div class="mem"><span class="meta">${esc(m.type || "")} · ${esc((m.when || "").slice(0, 10))} · ${esc(m.document_id || "")}</span>${esc(m.text)}</div>`).join("") || '<p class="muted">Nothing relevant in memory.</p>'}
      </details>`
    : `<p class="nomem-note">No memory: the model only sees the alert text.</p>`;

  return `<div class="card ${withMemory ? "with-memory" : ""}">
    <div class="card-head">
      <span class="card-title">${withMemory ? "With Hindsight memory" : "Without memory"}</span>
      <span class="timing">llm ${result.llm_ms} ms</span>
    </div>
    <div class="badges">
      <span class="badge ${esc(t.severity)}">${esc(t.severity)}</span>
      <span class="badge conf-${esc(t.confidence)}">confidence: ${esc(t.confidence)}</span>
      ${t.estimated_time_to_mitigate ? `<span class="badge">ETA ${esc(t.estimated_time_to_mitigate)}</span>` : ""}
    </div>
    <div class="summary">${esc(t.summary)}</div>
    <div class="section-label">Likely root cause</div>
    <div>${esc(t.likely_root_cause)}</div>
    ${sims}
    <div class="section-label">Next steps</div>
    ${list(t.next_steps)}
    ${avoid}
    ${recalled}
  </div>`;
}

async function runTriage(mode) {
  const alert = $("alert").value.trim();
  const service = $("service").value.trim() || null;
  if (alert.length < 5) return toast("Paste an alert first");

  const buttons = document.querySelectorAll(".alert-panel button");
  buttons.forEach((b) => (b.disabled = true));
  const out = $("results");
  out.className = "results" + (mode === "compare" ? " compare" : "");
  out.innerHTML = `<div class="spinner">${mode === "no_memory" ? "Thinking…" : "Recalling past incidents from Hindsight…"}</div>`;

  try {
    const res = await api("/api/triage", { method: "POST", body: JSON.stringify({ alert, service, mode }) });
    out.innerHTML =
      (res.without_memory ? renderCard(res.without_memory, false) : "") +
      (res.with_memory ? renderCard(res.with_memory, true) : "");
    lastTriage = { alert, service, result: res.with_memory || res.without_memory };
    prefillResolve();
  } catch (e) {
    out.innerHTML = `<div class="panel error">Triage failed: ${esc(e.message)}</div>`;
  } finally {
    buttons.forEach((b) => (b.disabled = false));
  }
}

$("btn-compare").onclick = () => runTriage("compare");
$("btn-memory").onclick = () => runTriage("memory");
$("btn-nomemory").onclick = () => runTriage("no_memory");

// ---- resolve (the learning loop) ----------------------------------------------
function prefillResolve() {
  $("resolve").hidden = false;
  $("r-id").value = `INC-${2400 + Math.floor(Math.random() * 500)}`;
  $("r-cause").value = lastTriage.result.triage.likely_root_cause;
  $("r-fix").value = lastTriage.result.triage.next_steps[0] || "";
  $("r-notes").value = "";
  $("r-ttm").value = "";
}

$("btn-resolve").onclick = async () => {
  if (!lastTriage) return;
  const btn = $("btn-resolve");
  btn.disabled = true;
  try {
    await api("/api/resolve", {
      method: "POST",
      body: JSON.stringify({
        incident_id: $("r-id").value.trim(),
        service: lastTriage.service || "unknown",
        alert: lastTriage.alert,
        root_cause: $("r-cause").value.trim(),
        fix: $("r-fix").value.trim(),
        suggestion_verdict: document.querySelector('input[name="verdict"]:checked').value,
        time_to_mitigate_min: $("r-ttm").value ? Number($("r-ttm").value) : null,
        notes: $("r-notes").value.trim() || null,
      }),
    });
    toast(`${$("r-id").value} retained. The agent will remember this next time.`);
    $("resolve").hidden = true;
  } catch (e) {
    toast(`Retain failed: ${e.message}`);
  } finally {
    btn.disabled = false;
  }
};

// ---- playbook (reflect) --------------------------------------------------------
$("btn-playbook").onclick = async () => {
  const btn = $("btn-playbook");
  btn.disabled = true;
  $("playbook").innerHTML = '<div class="spinner">Hindsight is reflecting over every incident…</div>';
  try {
    const { markdown } = await api("/api/playbook");
    $("playbook").innerHTML = md(markdown);
  } catch (e) {
    $("playbook").innerHTML = `<p class="error">${esc(e.message)}</p>`;
  } finally {
    btn.disabled = false;
  }
};

// ---- explorer (raw recall) -----------------------------------------------------
async function search() {
  const q = $("q").value.trim();
  if (!q) return;
  $("explore-results").innerHTML = '<div class="spinner">Recalling…</div>';
  try {
    const { memories } = await api(`/api/memories?q=${encodeURIComponent(q)}`);
    $("explore-results").innerHTML =
      memories.map((m) => `<div class="mem"><span class="meta">${esc(m.type || "")} · ${esc((m.when || "").slice(0, 10))} · ${esc(m.document_id || "")}</span>${esc(m.text)}</div>`).join("") ||
      '<p class="muted">No memories matched.</p>';
  } catch (e) {
    $("explore-results").innerHTML = `<p class="error">${esc(e.message)}</p>`;
  }
}
$("btn-search").onclick = search;
$("q").addEventListener("keydown", (e) => e.key === "Enter" && search());
