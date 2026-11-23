"use strict";

/* VeriScout – Oberfläche des Forschungsprototyps.
 * Zeigt nur, was für Suchauftrag, Vergleich SAS-2/MAS, verblindete Bewertung
 * und Transferprüfung gebraucht wird. Alle Entscheidungen fallen serverseitig.
 */

const byId = (id) => document.getElementById(id);
const state = {
  config: null,
  preview: null,
  running: false,
  current: null,          // {operator_view, blind_pairs, assignment_manifests}
  runs: [],
  pairIndex: 0,
  transfer: { protocol: null, session: null, active: null, starts: new Map(), outcomes: new Map(), exported: false },
};

const STATE_LABEL = {
  empfehlung: "Empfehlung", ablehnung: "Ablehnung",
  enthaltung: "Enthaltung", technischer_fehler: "Technischer Fehler",
};
const RUN_STATUS_LABEL = {
  completed: "abgeschlossen, mit Empfehlung", abstention: "gültig, ohne Empfehlung",
  not_checked_budget: "Prüfbudget erschöpft", technical_error: "technischer Fehler",
};
const DIMENSION_LABEL = {
  identity: "Identität des Startup-Unternehmens",
  startup_status: "Unternehmenstyp und Gründung",
  target_identity: "Identität des mittelständischen Unternehmens",
  target_process: "Zielprozess",
  input_stream: "Input- oder Ressourcenstrom",
  startup_capability: "Fähigkeit des Startup-Unternehmens",
  transformation: "Wirkmechanismus",
  output_application: "Nutzbares Ergebnis",
  relational_chain: "Zusammenhang der Kette",
  input_stream_mechanism: "Fachbeleg zum abgeleiteten Reststrom",
};
const DIM_STATUS_LABEL = {
  supported: "belegt", partial: "teilweise", contradicted: "Widerspruch",
  missing: "fehlt", not_applicable: "n. a.",
};
const STANCE_LABEL = { support: "gestützt", contradict: "widerlegt", unknown: "unbestätigt" };

/* ---------- Hilfen ---------- */
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function safeUrl(value) {
  try { const url = new URL(String(value || "")); return ["http:", "https:"].includes(url.protocol) ? url.href : ""; }
  catch { return ""; }
}
function fmt(n, digits = 0) {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "–";
  return Number(n).toLocaleString("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}
function usd(n) { return n === null || n === undefined ? "–" : `${fmt(n, 3)} USD`; }
function pct(n) { return n === null || n === undefined ? "–" : `${fmt(n * 100, 1)} %`; }
function toast(text, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  byId("toasts").appendChild(el);
  setTimeout(() => el.remove(), kind === "error" ? 9000 : 5000);
}
async function requestJson(url, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  const response = await fetch(url, { ...options, headers });
  let data = {};
  try { data = await response.json(); } catch { data = {}; }
  if (!response.ok) throw new Error(data.error || `Anfrage fehlgeschlagen (${response.status}).`);
  return { data, response };
}
function download(content, name, type = "application/json") {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url; link.download = name;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const downloadJson = (value, name) => download(JSON.stringify(value, null, 2), name);
function localDateTimeToIso(value) {
  const date = value ? new Date(value) : new Date();
  return Number.isNaN(date.getTime()) ? new Date().toISOString() : date.toISOString();
}
function isoToLocalInput(iso) {
  const date = new Date(iso);
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
}

/* ---------- Bereiche ---------- */
function showTab(name) {
  document.querySelectorAll(".stepper [data-tab]").forEach((tab) => {
    const active = tab.dataset.tab === name;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll(".panel").forEach((panel) => { panel.hidden = panel.id !== `tab-${name}`; });
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
}

/* ---------- Konfiguration und Status ---------- */
async function loadConfig() {
  try {
    state.config = (await requestJson("/api/comparison/config")).data;
  } catch (error) {
    byId("systemText").textContent = "Getrennt";
    toast(error.message, "error");
    return;
  }
  const cfg = state.config;
  const pill = byId("systemPill");
  pill.classList.toggle("is-live", cfg.live_enabled);
  pill.classList.toggle("is-offline", !cfg.live_enabled);
  byId("systemText").textContent = cfg.live_enabled ? "Live" : "Offline";
  if (cfg.live_enabled && cfg.run_profile === "local_development" && !byId("operatorToken").value) {
    // Lokaler Einzelplatzbetrieb: Schlüssel automatisch eintragen.
    try {
      byId("operatorToken").value = (await requestJson("/api/comparison/local-operator")).data.operator_token || "";
    } catch { /* bleibt leer, manuelles Einfügen möglich */ }
  }
  renderBudget();
  renderPreflight();
}

function renderBudget() {
  const b = (state.config || {}).default_budget || {};
  const half = (n) => Math.floor(Number(n || 0) / 2);
  const rows = [
    ["Modell", b.model, "", ""],
    ["Modellaufrufe", b.max_model_calls, "1", "1"],
    ["Eingabetokens", fmt(b.max_input_tokens), "gemeinsam", "gemeinsam"],
    ["Ausgabetokens", fmt(b.max_output_tokens), fmt(half(b.max_output_tokens)), fmt(b.max_output_tokens - half(b.max_output_tokens))],
    ["Reasoning-Tokens", fmt(b.max_reasoning_tokens), "gemeinsam", "gemeinsam"],
    ["Websuchen", b.max_tool_calls, half(b.max_tool_calls), b.max_tool_calls - half(b.max_tool_calls)],
    ["Quellenabrufe (Resolver)", b.max_resolver_fetches, "–", "–"],
    ["Kandidaten", b.max_candidates, "", ""],
    ["Kostenrahmen", usd(b.max_cost_usd), "", ""],
  ];
  byId("budgetBody").innerHTML = rows.map((row) =>
    `<tr><td>${escapeHtml(row[0])}</td><td>${escapeHtml(row[1] ?? "–")}</td><td>${escapeHtml(row[2])}</td><td>${escapeHtml(row[3])}</td></tr>`).join("");
  const a = (state.config || {}).analysis_parameters || {};
  byId("analysisParams").textContent =
    `Budgetprofil ${a.budget_profile || "–"} · Nichtunterlegenheitsgrenze Precision ${fmt(a.ni_margin_precision, 2)} · `
    + `Mindestverbesserung ${fmt(a.min_improvement, 2)} · Auszugsabgleich ${a.excerpt_match_mode || "–"} · `
    + `Websuch-Überschreitung: ${a.web_overrun_policy === "fail" ? "technischer Fehler" : "Protokollabweichung"}`;
}

function maxCost() {
  const b = (state.config || {}).default_budget || {};
  const reps = Math.max(1, Number(byId("repetitions").value || 1));
  const memoryFactor = byId("memoryMode").value === "both" ? 2 : 1;
  return Number(b.max_cost_usd || 0) * 2 * reps * memoryFactor;
}

function renderPreflight() {
  const cfg = state.config || {};
  const blockers = new Set((cfg.live_blockers || []).map((b) => b.code));
  const org = byId("organizationName").value.trim();
  const prompt = byId("searchPrompt").value.trim();
  const ready = state.preview && state.preview.status === "ready";
  const checks = [
    ["Mittelständisches Unternehmen", !!org, "Name eintragen"],
    ["Suchauftrag (mind. 30 Zeichen)", prompt.length >= 30, prompt.length ? `${prompt.length} von 30` : ""],
    ["Kanonischer Auftrag bereit", !!ready, ready ? "" : "Vorschau prüfen"],
    ...(caseSheetPayload() ? [["Fallblatt: nur öffentliche Quellen bestätigt", byId("csPublic").checked, "Häkchen im Fallblatt setzen"]] : []),
    ["Serverfreigabe für Live-Läufe", !blockers.has("server_disabled"), "Start mit scripts/start_live_review.py"],
    ["API-Schlüssel vorhanden", !blockers.has("api_key_missing"), ".env"],
    ["Bedienerschlüssel eingerichtet", !blockers.has("operator_missing"), ""],
  ];
  byId("preflight").innerHTML = checks.map(([label, ok, help]) =>
    `<li class="${ok ? "ok" : "bad"}">${escapeHtml(label)}${!ok && help ? ` <small>${escapeHtml(help)}</small>` : ""}</li>`).join("");
  const liveOk = !!cfg.live_enabled;
  byId("liveInputs").hidden = !liveOk;
  byId("costNote").textContent = liveOk ? `kostet höchstens ${fmt(maxCost(), 2)} USD` : "";
  const caseOk = !caseSheetPayload() || byId("csPublic").checked;
  const canStart = liveOk && caseOk && org && prompt.length >= 30 && ready
    && byId("operatorToken").value.trim() && !state.running;
  byId("startRunBtn").disabled = !canStart;
  const passed = checks.filter(([, ok]) => ok).length;
  byId("preflightSummary").textContent = `Prüfliste · ${passed} von ${checks.length} erfüllt`;
  const box = byId("preflightBox");
  if (passed < checks.length && !box.dataset.userToggled) box.open = true;
  if (passed === checks.length && !box.dataset.userToggled) box.open = false;
  const blocker = firstStartBlocker([
    { ok: !!org, label: "Name des Unternehmens fehlt" },
    { ok: prompt.length >= 30, label: prompt.length ? `Suchauftrag zu kurz (${prompt.length} von 30 Zeichen)` : "Suchauftrag fehlt" },
    { ok: !!ready, label: "Auftragsvorschau noch nicht bereit" },
    { ok: caseOk, label: "Im Fallblatt fehlt das Häkchen „nur öffentliche Quellen“" },
    { ok: liveOk, label: "Live-Läufe sind am Server nicht aktiv" },
    { ok: !!byId("operatorToken").value.trim(), label: "Bedienerschlüssel fehlt" },
  ]);
  byId("startHint").textContent = state.running || canStart || !blocker ? "" : `Noch nicht startbereit: ${blocker}`;
}

/* ---------- Auftragsart ---------- */
// Nur PUSH: Die Unternehmen nennen ihre Suchfelder nicht öffentlich. Das
// Backend kennt PULL weiterhin, die Oberfläche bietet es nicht mehr an.
function searchMode() { return "push"; }
function modePayload() {
  const hint = byId("domainHint").value.trim();
  return { ...modeOnly(), ...(hint ? { organization_domain_hint: hint } : {}) };
}
function modeOnly() {
  return { search_mode: "push" };
}

/* ---------- Vorschau ---------- */
let previewTimer = null;
function schedulePreview() {
  byId("promptCounter").textContent = `${fmt(byId("searchPrompt").value.length)} / 2.000`;
  state.preview = null;
  renderPreflight();
  clearTimeout(previewTimer);
  previewTimer = setTimeout(runPreview, 450);
}
async function runPreview() {
  const org = byId("organizationName").value.trim();
  const prompt = byId("searchPrompt").value.trim();
  if (!org || prompt.length < 30) {
    byId("taskPreview").textContent = "";
    byId("previewMeta").hidden = true;
    return;
  }
  try {
    const { data } = await requestJson("/api/comparison/preview", {
      method: "POST",
      body: JSON.stringify({ organization_name: org, search_prompt: prompt, ...modePayload(),
        dataset_split: byId("datasetSplit").value, event_time: localDateTimeToIso(byId("eventTime").value) }),
    });
    state.preview = data;
    byId("taskPreview").textContent = (data.task || {}).shared_prompt || "";
    byId("taskHash").textContent = data.task_input_hash || "–";
    byId("promptHash").textContent = data.prompt_hash || "–";
    const issues = ((data.readiness || {}).issues || []).join(" ");
    byId("readiness").textContent = data.status === "ready" ? "bereit" : `nicht bereit ${issues}`;
    byId("previewMeta").hidden = false;
  } catch (error) {
    state.preview = null;
    byId("taskPreview").textContent = error.message;
    byId("previewMeta").hidden = true;
  }
  renderPreflight();
}

/* ---------- Lauf ---------- */
let timerHandle = null;
async function startRun() {
  if (state.running) return;
  if (!window.confirm(`Der Vergleich ruft die KI-Schnittstelle auf und kostet höchstens ${fmt(maxCost(), 2)} USD (lokale Schätzung). Jetzt starten?`)) return;
  state.running = true;
  renderPreflight();
  const started = Date.now();
  byId("runProgress").hidden = false;
  byId("runProgressText").textContent = "SAS-2 und MAS recherchieren und prüfen";
  timerHandle = setInterval(() => {
    const s = Math.floor((Date.now() - started) / 1000);
    byId("elapsed").textContent = `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
  }, 1000);
  try {
    const key = `run-${crypto.randomUUID()}`;
    const { data } = await requestJson("/api/comparison/run", {
      method: "POST",
      headers: { "X-VeriScout-Token": byId("operatorToken").value.trim() },
      body: JSON.stringify({
        organization_name: byId("organizationName").value.trim(),
        search_prompt: byId("searchPrompt").value.trim(),
        ...modePayload(),
        dataset_split: byId("datasetSplit").value,
        repetitions: Number(byId("repetitions").value || 1),
        memory_mode: byId("memoryMode").value,
        event_time: localDateTimeToIso(byId("eventTime").value),
        baseline: "sas2", confirm_live: true, idempotency_key: key,
        study_run: byId("studyRun").checked,
        ...(caseSheetPayload() ? { case_sheet: caseSheetPayload() } : {}),
      }),
    });
    await loadRuns();
    await openRun(data.run_id);
    toast(`Lauf abgeschlossen. Kosten: ${usd(((data.study || {}).actual_cost_usd))}.`);
    showTab("ergebnis");
  } catch (error) {
    toast(error.message, "error");
  } finally {
    clearInterval(timerHandle);
    state.running = false;
    byId("runProgress").hidden = true;
    renderPreflight();
  }
}

/* ---------- Gespeicherte Läufe ---------- */
async function loadRuns() {
  try {
    state.runs = (await requestJson("/api/comparison/runs")).data.runs || [];
  } catch { state.runs = []; }
  const select = byId("runSelect");
  const selected = select.value;
  const option = (run) => {
    const date = run.created_at ? new Date(run.created_at).toLocaleString("de-DE") : "";
    const label = [run.organization_name, run.model, date, usd(run.cost_usd)].filter(Boolean).join(" · ");
    return `<option value="${escapeHtml(run.run_id)}">${escapeHtml(label)}${run.reevaluated ? " · neu bewertet" : ""}</option>`;
  };
  const study = state.runs.filter((run) => run.run_set === "studie");
  const probe = state.runs.filter((run) => run.run_set !== "studie");
  select.innerHTML = state.runs.length
    ? `<option value="">Lauf auswählen …</option>`
      + `<optgroup label="Studienläufe (Masterarbeit)">${study.map(option).join("") || "<option disabled value=\"\">noch keine</option>"}</optgroup>`
      + `<optgroup label="Probe- und Entwicklungsläufe">${probe.map(option).join("")}</optgroup>`
    : `<option value="">Keine gespeicherten Läufe</option>`;
  if (selected) select.value = selected;
  renderRecentRuns();
  updateReviewButtons();
}
function renderRecentRuns() {
  const recent = [...state.runs].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || ""))).slice(0, 6);
  const label = (s) => ({ completed: "Empfehlung", abstention: "ohne Empfehlung", technical_error: "techn. Fehler", not_checked_budget: "Budget erschöpft" }[s] || s || "–");
  byId("recentRuns").innerHTML = recent.length ? `<h3>Zuletzt gespeichert</h3><div class="run-cards">${recent.map((run) => `
    <button type="button" class="run-card-btn" data-run-id="${escapeHtml(run.run_id)}">
      <span class="run-card-top"><strong>${escapeHtml(run.organization_name || "–")}</strong><span class="tag">${run.run_set === "studie" ? "Studienlauf" : "Probelauf"}</span></span>
      <span class="run-card-meta">${escapeHtml(run.created_at ? new Date(run.created_at).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" }) : "")} · ${escapeHtml(usd(run.cost_usd))}${run.reevaluated ? " · neu bewertet" : ""}</span>
      <span class="run-card-meta">SAS-2: ${escapeHtml(label((run.states || {}).sas2))} · MAS: ${escapeHtml(label((run.states || {}).mas))}</span>
    </button>`).join("")}</div>` : "";
}

async function openRun(runId) {
  if (!runId) { state.current = null; renderResult(); updateReviewButtons(); return; }
  try {
    state.current = (await requestJson(`/api/comparison/runs/${encodeURIComponent(runId)}`)).data;
    state.pairIndex = 0;
    byId("runSelect").value = runId;
  } catch (error) { toast(error.message, "error"); state.current = null; }
  renderResult();
  updateReviewButtons();
}

/* ---------- Ergebnisdarstellung ---------- */
function renderResult() {
  const view = state.current && state.current.operator_view;
  byId("resultEmpty").hidden = !!view;
  byId("resultView").hidden = !view;
  byId("printBtn").hidden = !view;
  if (!view) return;
  const pairs = view.pairs || [];
  const wrap = byId("pairSelectWrap");
  wrap.hidden = pairs.length < 2;
  byId("pairSelect").innerHTML = pairs.map((p, i) =>
    `<option value="${i}">Paar ${i + 1}${p.replicate_index ? ` · Wiederholung ${p.replicate_index}` : ""}</option>`).join("");
  byId("pairSelect").value = String(state.pairIndex);
  const pair = pairs[state.pairIndex] || pairs[0] || { arms: [] };
  const task = view.task || {};
  byId("runMeta").innerHTML = `
    <div><span class="label">Mittelständisches Unternehmen und Suchauftrag</span><span class="value"><strong>${escapeHtml(task.organization_name)}</strong> · ${escapeHtml((task.search_mode || "push").toUpperCase())}${task.search_area ? ` · Suchfeld „${escapeHtml(task.search_area)}“` : ""} – ${escapeHtml(task.search_prompt)}</span></div>
    <div><span class="label">Modell (SAS-2 und MAS)</span><span class="value">${escapeHtml(view.model)}</span></div>
    <div><span class="label">Art des Laufs</span><span class="value">${view.run_set === "studie" ? "Studienlauf (Masterarbeit)" : "Probelauf"}</span></div>
    <div><span class="label">Reihenfolge</span><span class="value">${escapeHtml((pair.order || []).map((a) => a === "sas2" ? "SAS-2" : "MAS").join(" → "))}</span></div>
    <div><span class="label">Lauf</span><span class="value"><code>${escapeHtml(view.run_id)}</code><br>${escapeHtml(view.created_at ? new Date(view.created_at).toLocaleString("de-DE") : "")}${view.reevaluated_from ? `<br>Neu bewertet aus ${escapeHtml(view.reevaluated_from)} (ohne neue Modellaufrufe)` : ""}</span></div>`;
  const order = { sas2: 0, mas: 1 };
  const arms = [...(pair.arms || [])].sort((a, b) => order[a.architecture] - order[b.architecture]);
  state.shared = sharedCandidateIds(arms);
  byId("compareView").innerHTML = renderCompare(arms);
  byId("arms").innerHTML = arms.map(renderArm).join("");
}

function renderCompare(arms) {
  const cols = arms.map((arm) => {
    const counts = {};
    (arm.candidates || []).forEach((c) => { counts[c.decision_state] = (counts[c.decision_state] || 0) + 1; });
    const r = arm.resources || {};
    const share = supportedShare(arm.review_mechanics);
    const shared = (arm.candidates || []).filter((c) => state.shared.has(c.candidate_id)).length;
    return { code: arm.architecture === "mas" ? "MAS" : "SAS-2", arm, counts, r, share, shared };
  });
  const row = (label, fn, cls = "") => `<tr><th scope="row">${label}</th>${cols.map((c) => `<td class="${cls}">${fn(c)}</td>`).join("")}</tr>`;
  const sharedNames = arms.length ? (arms[0].candidates || []).filter((c) => state.shared.has(c.candidate_id)).map((c) => c.name) : [];
  return `<h2>Vergleich auf einen Blick</h2>
    <div class="table-wrap"><table class="table compare-table">
      <thead><tr><th scope="col"><span class="visually-hidden">Kennzahl</span></th>${cols.map((c) => `<th scope="col">${c.code}</th>`).join("")}</tr></thead>
      <tbody>
        ${row("Ergebnis", (c) => `<span class="state status-${escapeHtml(c.arm.result_status)}">${escapeHtml(RUN_STATUS_LABEL[c.arm.result_status] || c.arm.result_status)}</span>`)}
        ${row("Empfehlungen", (c) => fmt(c.counts.empfehlung || 0), "num")}
        ${row("Ablehnungen", (c) => fmt(c.counts.ablehnung || 0), "num")}
        ${row("Enthaltungen", (c) => fmt(c.counts.enthaltung || 0), "num")}
        ${row("Technische Fehler", (c) => fmt(c.counts.technischer_fehler || 0), "num")}
        ${row("Gestützte Aussagen (Stufe 2)", (c) => c.share === null ? "–" : `${pct(c.share)} <span class="hint">(${fmt(c.arm.review_mechanics.claims_supported_stage_2)} von ${fmt(c.arm.review_mechanics.claims_stage_1)})</span>`, "num")}
        ${row("Kosten", (c) => usd(c.r.cost_usd), "num")}
        ${row("Dauer", (c) => `${fmt((c.r.wall_latency_ms || 0) / 1000, 0)} s`, "num")}
      </tbody></table></div>
    <p class="hint">${sharedNames.length ? `In beiden Architekturen gefunden: <strong>${sharedNames.map(escapeHtml).join(", ")}</strong> (gleicher Name oder gleiche Website).` : "Keine Überschneidung: Die Architekturen haben unterschiedliche Startups vorgeschlagen."}</p>`;
}

function renderArm(arm) {
  const r = arm.resources || {};
  const m = arm.review_mechanics || {};
  const sens = arm.sensitivity || {};
  const code = arm.architecture === "mas" ? "MAS" : "SAS-2";
  const sub = arm.architecture === "mas" ? "Scouting- und getrennte Verifikationsrolle" : "Ein Agent mit Selbstprüfung";
  const counts = {};
  (arm.decision_states || []).forEach((s) => { counts[s] = (counts[s] || 0) + 1; });
  const stateSummary = Object.keys(counts).length
    ? Object.entries(counts).map(([s, n]) => `<span class="state state-${escapeHtml(s)}">${n} × ${escapeHtml(STATE_LABEL[s] || s)}</span>`).join(" ")
    : `<span class="hint">keine Kandidaten</span>`;
  const sensRows = Object.entries(sens).filter(([k]) => k !== "error").map(([name, value]) => {
    const label = name === "exact_excerpt" ? "Wortgleicher Auszugsabgleich" : "MAS mit Quellen der Scoutingrolle";
    return `<li>${escapeHtml(label)}: ${escapeHtml(RUN_STATUS_LABEL[value.result_status] || value.result_status)} (${(value.positive_candidate_ids || []).length} Empfehlung/en)</li>`;
  }).join("");
  // Satz nur, wenn es keinen Kandidaten oder einen Fehlergrund gibt; sonst begruenden die Kandidaten selbst.
  const whyArm = (arm.candidates || []).length && !(r.failure_reasons || []).length && !arm.primary_exclusion_reason
    ? "" : whyArmWithoutRecommendation(arm, STATE_LABEL);
  const failure = (r.failure_reasons || []).length ? `<p class="hint">Fehlergrund: ${escapeHtml(r.failure_reasons.join(", "))}</p>` : "";
  return `<article class="arm">
    <header class="arm-head">
      <div><span class="code">${code}</span><small>${escapeHtml(sub)}</small></div>
      <span class="state status-${escapeHtml(arm.result_status)}">${escapeHtml(RUN_STATUS_LABEL[arm.result_status] || arm.result_status)}</span>
    </header>
    <div class="arm-body">
      <div class="arm-section"><h3>Ergebniszustände</h3>${stateSummary}${failure}${whyArm ? `<p class="why">${escapeHtml(whyArm)}</p>` : ""}</div>
      <details class="arm-section arm-more"><summary><h3>Ressourcen</h3></summary><div class="metrics">
        <div class="metric"><span>Eingabetokens</span><strong>${fmt(r.input_tokens)}</strong></div>
        <div class="metric"><span>Ausgabetokens</span><strong>${fmt(r.output_tokens)}</strong></div>
        <div class="metric"><span>Websuchen</span><strong>${fmt(r.web_calls)}</strong></div>
        <div class="metric"><span>Quellenabrufe</span><strong>${fmt(r.resolver_fetches)}</strong></div>
        <div class="metric"><span>Kosten</span><strong>${usd(r.cost_usd)}</strong></div>
        <div class="metric"><span>Dauer</span><strong>${fmt((r.wall_latency_ms || 0) / 1000, 0)} s</strong></div>
      </div></details>
      <details class="arm-section arm-more"><summary><h3>Zweite Stufe (Prüfung)</h3></summary>
        <ul class="small-list">
          <li>Kandidaten aus Stufe 1: ${fmt(m.candidates_stage_1)}, verworfen: ${fmt(m.candidates_dropped_stage_2)}</li>
          <li>Aussagen: ${fmt(m.claims_stage_1)} · gestützt ${fmt(m.claims_supported_stage_2)} · widerlegt ${fmt(m.claims_contradicted_stage_2)} · unbestätigt ${fmt(m.claims_unconfirmed_stage_2)}</li>
          ${(arm.protocol_deviations || []).length ? `<li>Protokollabweichung: ${escapeHtml(arm.protocol_deviations.join(", "))}</li>` : ""}
        </ul></details>
      ${sensRows ? `<details class="arm-section arm-more"><summary><h3>Sensitivitätsanalysen (ohne Mehrkosten)</h3></summary><ul class="small-list">${sensRows}</ul></details>` : ""}
      <div class="arm-section"><h3>Kandidaten</h3>${(arm.candidates || []).map((c) => renderCandidate(c, { architecture: arm.architecture, study: (state.current.operator_view || {}).run_set === "studie" })).join("") || `<p class="hint">Kein Startup-Unternehmen vorgeschlagen. Das ist ein gültiges Ergebnis, aber kein Treffer.</p>`}</div>
    </div>
  </article>`;
}

function renderCandidate(c, ctx = {}) {
  const website = safeUrl(c.website);
  const sources = new Map((c.sources || []).map((s) => [String(s.source_id || s.url), s]));
  const SYMBOL = { supported: "✓", partial: "◐", missing: "○", contradicted: "✕", not_applicable: "–" };
  const matrix = (c.matrix || []).map((cell) => {
    const derived = cell.status === "supported" && cell.basis === "derived";
    const statusText = `${DIM_STATUS_LABEL[cell.status] || cell.status}${cell.basis === "derived" ? " (abgeleitet)" : ""}`;
    return `<li class="tile dim-${escapeHtml(derived ? "derived" : cell.status)}" title="${escapeHtml(cell.claim || "")}">
      <b aria-hidden="true">${SYMBOL[cell.status] || "?"}</b><span class="tile-label">${escapeHtml(DIMENSION_LABEL[cell.dimension] || cell.dimension)}</span>
      <span class="visually-hidden">: ${escapeHtml(statusText)}</span><small aria-hidden="true">${escapeHtml(statusText)}</small></li>`;
  }).join("");
  const why = whyNoRecommendation(c, DIMENSION_LABEL, DIM_STATUS_LABEL);
  const claims = (c.claims || []).map((claim) => {
    const src = sources.get(String(claim.source_id)) || {};
    const url = safeUrl(src.url);
    const jump = fragmentUrl(src.resolved_url || src.url, claim.excerpt);
    const context = src.matched_context && claim.excerpt ? highlightContext(src.matched_context, claim.excerpt) : "";
    return `<div class="claim"><strong>${escapeHtml(DIMENSION_LABEL[claim.field] || claim.field)}</strong> · ${escapeHtml(STANCE_LABEL[claim.stance] || claim.stance)}<br>${escapeHtml(claim.claim_text)}
      ${claim.excerpt ? `<q>${escapeHtml(claim.excerpt)}</q>` : ""}
      <span class="src">${url ? `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(src.title || url)}</a>` : escapeHtml(claim.source_id || "keine Quelle")}${src.resolved_status ? ` · Abruf: ${escapeHtml(src.resolved_status)}` : ""}${src.excerpt_match_mode ? ` · Auszug ${src.excerpt_match_mode === "exact" ? "wortgleich" : "unscharf"} gefunden` : ""}${jump && claim.excerpt ? ` · <a class="jump" href="${escapeHtml(jump)}" target="_blank" rel="noopener noreferrer">An der Fundstelle öffnen</a>` : ""}</span>
      ${context ? `<details class="context"><summary>Kontext auf der Quelle</summary><p>${context}</p></details>` : ""}</div>`;
  }).join("");
  const open = [...new Set([...(c.unresolved_requirements || []), ...(c.verification_reasons || [])])];
  const isRecommendation = c.decision_state === "empfehlung";
  return `<div class="candidate">
    <div class="candidate-head"><div><h3>${escapeHtml(c.name)}${state.shared && state.shared.has(c.candidate_id) ? ` <span class="tag tag-shared">in beiden Architekturen</span>` : ""}</h3>${website ? `<a href="${escapeHtml(website)}" target="_blank" rel="noopener noreferrer">${escapeHtml(website)}</a>` : ""}</div>
    <span class="state state-${escapeHtml(c.decision_state)}">${escapeHtml(STATE_LABEL[c.decision_state] || c.decision_state)}</span></div>
    <p class="reason">${escapeHtml([why ? "" : c.decision_state_reason, c.operating_status ? `Fortbestand: ${{active: "aktiv", acquired: "übernommen", insolvent: "insolvent", ceased: "eingestellt", unknown: "ungeklärt"}[c.operating_status] || c.operating_status}` : ""].filter(Boolean).join(" · "))}</p>
    ${why ? `<p class="why"><strong>Warum keine Empfehlung?</strong> ${escapeHtml(why)}</p>` : ""}
    <ul class="matrix-grid" aria-label="Relationale Evidenzmatrix">${matrix}</ul>
    <details class="evidence"><summary>Aussagen und Belege (${(c.claims || []).length})</summary>${claims || "<p class='hint'>Keine Aussagen.</p>"}</details>
    ${open.length ? `<details class="evidence"><summary>Offene Fragen (${open.length})</summary><ul class="small-list">${open.map((q) => `<li>${escapeHtml(q)}</li>`).join("")}</ul></details>` : ""}
    ${isRecommendation ? (ctx.study ? `<div class="release"><strong>Menschliche Freigabe</strong>
      <p>In Studienläufen gesperrt: Die Laufdateien der Masterarbeit bleiben unverändert. CRM-Übernahme und E-Mail-Entwurf sind in Probe- und Demoläufen möglich.</p></div>`
      : `<div class="release" data-release-box="${escapeHtml(c.candidate_id)}"><strong>Menschliche Freigabe</strong>
      <p>Erst prüfen, dann freigeben. Das System versendet nichts selbst: Die E-Mail öffnet sich als Entwurf in deinem Mailprogramm, du sendest sie.</p>
      <div class="btn-row" style="margin-top:6px"><button class="btn" type="button" data-release-prepare="${escapeHtml(c.candidate_id)}" data-arch="${escapeHtml(ctx.architecture)}">Freigabe vorbereiten (CRM und E-Mail)</button></div>
      <div class="release-panel" hidden></div></div>`) : ""}
  </div>`;
}

function highlightContext(context, excerpt) {
  const first = String(excerpt).split(/\s*(?:\.\.\.|…)\s*/)[0].trim();
  const text = String(context);
  const at = first ? text.toLowerCase().indexOf(first.toLowerCase()) : -1;
  if (at < 0) return escapeHtml(text);
  return `${escapeHtml(text.slice(0, at))}<mark>${escapeHtml(text.slice(at, at + first.length))}</mark>${escapeHtml(text.slice(at + first.length))}`;
}

/* ---------- Freigabe: CRM und E-Mail ---------- */
function operatorHeaders() { return { "X-VeriScout-Token": byId("operatorToken").value.trim() }; }
function releaseBase(candidateId, architecture) {
  return { run_id: state.current.operator_view.run_id, pair_index: state.pairIndex, architecture, candidate_id: candidateId };
}
async function prepareRelease(button) {
  const box = button.closest("[data-release-box]");
  const panel = box.querySelector(".release-panel");
  const base = releaseBase(button.dataset.releasePrepare, button.dataset.arch);
  panel.hidden = false; panel.innerHTML = `<p class="hint">Suche Kontaktadresse auf der Website des Startups …</p>`;
  try {
    const { data } = await requestJson("/api/comparison/release/preview", { method: "POST", headers: operatorHeaders(), body: JSON.stringify(base) });
    const c = data.contact || {};
    const src = safeUrl(c.source_url);
    panel.dataset.base = JSON.stringify({ ...base, decision_sha256: data.decision_sha256 });
    panel.innerHTML = `
      <p class="hint">Entscheidungsversion <code>${escapeHtml(data.decision_sha256.slice(0, 24))}…</code> · CRM-Modus: ${data.crm_mode === "live" ? "live (Pipedrive)" : "Trockenlauf, schreibt nicht nach Pipedrive"}</p>
      <label class="field"><span>An <em>${c.email ? `belegt auf ${src ? `<a href="${escapeHtml(src)}" target="_blank" rel="noopener noreferrer">${escapeHtml(src)}</a>` : "der Website"}` : "keine Adresse auf der Website gefunden, bitte selbst eintragen"}</em></span>
        <input data-rel="to" value="${escapeHtml(c.email || "")}" maxlength="200" autocomplete="off"></label>
      ${(c.alternatives || []).length ? `<p class="hint">Weitere Adressen der Website: ${c.alternatives.map(escapeHtml).join(", ")}</p>` : ""}
      <label class="field"><span>Betreff</span><input data-rel="subject" value="${escapeHtml(data.draft.subject)}" maxlength="300"></label>
      <label class="field"><span>Text</span><textarea data-rel="body" rows="9" maxlength="5000">${escapeHtml(data.draft.body)}</textarea></label>
      <label class="check"><input type="checkbox" data-rel="confirm"> Ich habe Startup, Aussagen und Belege geprüft und gebe diese Empfehlung frei.</label>
      <div class="btn-row">
        <button class="btn" type="button" data-release-action="crm">In CRM übernehmen</button>
        <button class="btn btn-primary" type="button" data-release-action="email_draft">E-Mail im Mailprogramm öffnen</button>
        ${data.outlook_available ? `<button class="btn" type="button" data-release-action="outlook_draft">Als Outlook-Entwurf anlegen</button>` : ""}
      </div><p class="hint" data-rel="result"></p>`;
  } catch (error) { panel.innerHTML = `<p class="hint">${escapeHtml(error.message)}</p>`; }
}
async function executeRelease(button) {
  const panel = button.closest(".release-panel");
  const field = (name) => panel.querySelector(`[data-rel="${name}"]`);
  if (!field("confirm").checked) { toast("Bitte die Freigabe bestätigen.", "error"); return; }
  const action = button.dataset.releaseAction;
  if (action !== "crm" && !field("to").value.trim()) { toast("Bitte eine Empfängeradresse eintragen.", "error"); return; }
  try {
    const { data } = await requestJson("/api/comparison/release", { method: "POST", headers: operatorHeaders(), body: JSON.stringify({
      ...JSON.parse(panel.dataset.base), action, confirm: true,
      email_to: field("to").value.trim(), subject: field("subject").value, body: field("body").value }) });
    const r = data.result || {};
    if (action === "email_draft" && r.mailto) { window.location.href = r.mailto; field("result").textContent = "Entwurf im Mailprogramm geöffnet. Versand erfolgt erst durch dich."; }
    else if (action === "crm") { field("result").textContent = r.status === "fehler" ? `CRM: ${r.grund}` : `CRM (${r.modus}): Organisation ${r.operation === "created" ? "angelegt" : "aktualisiert"}${r.deal && r.deal.id ? ", Deal angelegt" : ""}.`; loadCrm(); }
    else field("result").textContent = r.status === "entwurf_in_outlook" ? "Entwurf in Outlook angelegt, nicht gesendet." : `Outlook: ${r.grund || r.status}`;
  } catch (error) { toast(error.message, "error"); }
}

/* ---------- Druckansicht ---------- */
function printResult() {
  const closed = [...byId("resultView").querySelectorAll("details:not([open])")];
  closed.forEach((d) => { d.open = true; });
  const restore = () => { closed.forEach((d) => { d.open = false; }); window.removeEventListener("afterprint", restore); };
  window.addEventListener("afterprint", restore);
  window.print();
}

/* ---------- Darstellung hell/dunkel ---------- */
function applyTheme(choice) {
  if (choice === "light" || choice === "dark") document.documentElement.dataset.theme = choice;
  else delete document.documentElement.dataset.theme;
  document.querySelectorAll("[data-theme-choice]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.themeChoice === (choice || "system"))));
}
function initThemeSwitch() {
  let saved = "system";
  try { saved = localStorage.getItem("veriscout-theme") || "system"; } catch { /* privates Fenster */ }
  applyTheme(saved);
  document.querySelectorAll("[data-theme-choice]").forEach((b) => b.addEventListener("click", () => {
    const choice = b.dataset.themeChoice;
    try { if (choice === "system") localStorage.removeItem("veriscout-theme"); else localStorage.setItem("veriscout-theme", choice); } catch { /* ohne Speicher */ }
    applyTheme(choice);
  }));
}

/* ---------- Dateiauswahl (Ablageflächen) ---------- */
function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1).replace(".", ",")} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1).replace(".", ",")} MB`;
}
function renderDropzone(zone) {
  const input = zone.querySelector(".dz-input");
  const name = zone.querySelector(".dz-name");
  const meta = zone.querySelector(".dz-meta");
  const clear = zone.querySelector(".dz-clear");
  const files = [...input.files];
  const file = files[0];
  const valid = files.every((f) => /\.json$/i.test(f.name) || f.type === "application/json");
  zone.classList.toggle("is-filled", Boolean(file) && valid);
  zone.classList.toggle("is-invalid", Boolean(file) && !valid);
  clear.hidden = !file;
  meta.hidden = !file;
  if (!file) { name.textContent = input.multiple ? "Dateien auswählen" : "Datei auswählen"; name.removeAttribute("title"); meta.textContent = ""; return; }
  name.textContent = files.length > 1 ? `${files.length} Dateien` : file.name;
  name.title = files.map((f) => f.name).join(", ");
  meta.textContent = !valid ? "Keine JSON-Datei" : files.length > 1 ? files.map((f) => f.name).join(", ") : formatBytes(file.size);
}
function initDropzones() {
  document.querySelectorAll("[data-dropzone]").forEach((zone) => {
    const input = zone.querySelector(".dz-input");
    input.addEventListener("change", () => renderDropzone(zone));
    zone.querySelector(".dz-clear").addEventListener("click", () => {
      input.value = ""; renderDropzone(zone); input.focus();
    });
    ["dragenter", "dragover"].forEach((type) => zone.addEventListener(type, (e) => {
      e.preventDefault(); zone.classList.add("is-dragover");
    }));
    ["dragleave", "dragend"].forEach((type) => zone.addEventListener(type, () => zone.classList.remove("is-dragover")));
    zone.addEventListener("drop", (e) => {
      e.preventDefault(); zone.classList.remove("is-dragover");
      const files = e.dataTransfer && e.dataTransfer.files;
      if (!files || !files.length) return;
      const transfer = new DataTransfer();
      (input.multiple ? [...files] : [files[0]]).forEach((f) => transfer.items.add(f));
      input.files = transfer.files;
      renderDropzone(zone);
    });
    renderDropzone(zone);
  });
}

/* ---------- Pipedrive (nur lesend) ---------- */
async function loadCrm() {
  const mode = byId("crmMode");
  const hint = byId("crmHint");
  try {
    const { data } = await requestJson("/api/comparison/crm", { headers: operatorHeaders() });
    const live = data.mode === "live";
    mode.hidden = false;
    mode.textContent = data.auth_error ? "Fehler" : live ? "Live" : "Trockenlauf";
    mode.classList.toggle("is-live", live && !data.auth_error);
    mode.classList.toggle("is-error", Boolean(data.auth_error));
    hint.hidden = !data.auth_error;
    hint.classList.add("is-error");
    hint.textContent = data.auth_error || "";
    const orgs = data.organizations || [];
    byId("crmOrgs").innerHTML = orgs.length
      ? `<table class="table compact"><thead><tr><th>Organisation</th><th>Angelegt</th></tr></thead><tbody>${
        orgs.map((o) => `<tr><td>${escapeHtml(o.name)}</td><td>${escapeHtml((o.add_time || "").slice(0, 16) || "–")}</td></tr>`).join("")}</tbody></table>`
      : `<p class="hint">Keine Einträge.</p>`;
  } catch (error) {
    mode.hidden = false; mode.textContent = "Nicht erreichbar"; mode.classList.add("is-error");
    hint.hidden = false; hint.classList.add("is-error"); hint.textContent = error.message;
  }
}

/* ---------- Bewertung ---------- */
const METRIC_LABEL = {
  qualified: "Prüfwürdige Kooperationsidee", valid_entity: "Startup gültig und aktiv",
  relation_correct: "Zusammenhang stimmig", claim_support_complete: "Belege tragen die Aussagen",
  over_match: "Schönfärberei",
};
const VALUE_LABEL = { true: "Ja", false: "Nein", not_assessable: "nicht beurteilbar", disputed: "strittig" };
const valueLabel = (v) => VALUE_LABEL[String(v)] || String(v);
function updateReviewButtons() {
  const has = !!state.sheet;
  byId("sheetDownloads").hidden = !has;
  updateSteps();
}
function updateSteps() {
  const done = { stepSheet: !!state.sheet, stepMerge: !!(state.panelRatings && state.panelRatings.ready), stepAnalyze: !!state.analysisDone };
  Object.entries(done).forEach(([id, ok]) => {
    const card = byId(id);
    card.classList.toggle("is-done", ok);
    const badge = card.querySelector(".step-no");
    badge.textContent = ok ? "✓" : badge.dataset.stepNo;
    badge.setAttribute("aria-label", ok ? `Schritt ${badge.dataset.stepNo} erledigt` : `Schritt ${badge.dataset.stepNo}`);
  });
  byId("mergeBtn").disabled = !byId("ratingFiles").files.length || (!byId("keyFile").files.length && !state.sheet);
}
async function buildSheet() {
  const scope = byId("sheetScope").value;
  if (scope === "run" && !state.current) { toast("Bitte zuerst in Bereich 2 einen Lauf öffnen.", "error"); return; }
  const seed = byId("panelSeed").value.trim();
  if (!seed) { toast("Bitte einen Startwert eintragen und notieren.", "error"); byId("panelSeed").focus(); return; }
  try {
    const { data } = await requestJson("/api/comparison/panel", { method: "POST", body: JSON.stringify({
      scope, run_id: scope === "run" ? state.current.operator_view.run_id : "",
      purpose: scope === "probe" ? "schulung" : "studie", seed,
      raters: Number(byId("panelRaters").value), cases_per_rater: Number(byId("panelPerRater").value),
      ratings_per_case: Number(byId("panelOverlap").value) }) });
    state.sheet = data;
    const c = data.counts;
    byId("sheetInfo").textContent = `${c.cases} Fälle für ${c.raters} Personen (aus ${c.population.cases} Fällen, davon ${c.population.recommended_cases} empfohlen; ${data.runs} Laufdateien). Bogen ${data.panel_id}.`
      + (c.unsampled_recommended ? ` Achtung: ${c.unsampled_recommended} empfohlene Fälle nicht gezogen (Gewichte im Schlüssel).` : "")
      + (c.cases_per_rater_max > Number(byId("panelPerRater").value) ? ` Höchstens ${c.cases_per_rater_max} Fälle je Person nötig.` : "")
      + (c.orgs_per_rater_max > 6 ? ` Grenze von 6 Unternehmen je Person auf ${c.orgs_per_rater_max} erhöht (im Schlüssel vermerkt).` : "")
      + (c.verdict_words ? ` Hinweis: In ${c.verdict_words} Fällen enthält der Text des Systems Urteilswörter (z. B. „Empfehlung“); Liste im Schlüssel.` : "")
      + (scope === "probe" ? " Schulungsbogen: zählt nicht für die Studie." : "");
  } catch (error) { state.sheet = null; byId("sheetInfo").textContent = error.message; toast(error.message, "error"); }
  updateReviewButtons();
}
function downloadSheet() {
  if (!state.sheet) return;
  download(state.sheet.html, `bewertungsbogen-${state.sheet.panel_id.slice(6, 14)}.html`, "text/html");
}
function downloadKey() { if (state.sheet) downloadJson(state.sheet.key, `bewertungsschluessel-${state.sheet.panel_id.slice(6, 14)}.json`); }
function downloadEvidenceList() {
  const rows = state.runs.filter((run) => run.run_set === "studie").map((run) => ({
    run_id: run.run_id, created_at: run.created_at, organization: run.organization_name,
    model: run.model, pairs: run.pairs, cost_usd: run.cost_usd, states: run.states,
    file: `artifacts/runs/${run.run_id}.json`, sha256: run.file_sha256 }));
  if (!rows.length) { toast("Noch keine Studienläufe gespeichert.", "error"); return; }
  downloadJson({ created_at: new Date().toISOString(), count: rows.length, runs: rows }, "nachweisliste-studienlaeufe.json");
}
async function panelKey() {
  const file = byId("keyFile").files[0];
  if (file) return JSON.parse(await file.text());
  if (state.sheet) return state.sheet.key;
  throw new Error("Bitte den Bewertungsschlüssel auswählen oder in Schritt 1 den Bogen erstellen.");
}
async function mergeRatings() {
  try {
    const key = await panelKey();
    const ratings = await Promise.all([...byId("ratingFiles").files].map(async (f) => JSON.parse(await f.text())));
    const { data } = await requestJson("/api/comparison/panel/evaluate", { method: "POST", body: JSON.stringify({ key, ratings }) });
    const rows = Object.keys(key.assignment).sort().map((rater) => {
      const c = data.completeness[rater];
      if (!c) return `<tr><td>${escapeHtml(rater)}</td><td colspan="2" class="hint">noch keine Datei</td></tr>`;
      const ok = c.answered === c.assigned && !c.problems.length;
      return `<tr><td>${escapeHtml(rater)}</td><td class="num">${c.answered} / ${c.assigned}</td><td>${ok ? "vollständig" : `<details><summary>${c.problems.length} offen</summary><ul class="small-list">${c.problems.map((p) => `<li>${escapeHtml(p)}</li>`).join("")}</ul></details>`}</td></tr>`;
    }).join("");
    const complete = Object.keys(key.assignment).filter((r) => data.completeness[r] && data.completeness[r].answered === data.completeness[r].assigned && !data.completeness[r].problems.length).length;
    state.panelRatings = { key, ratings, data, ready: ratings.length > 0 };
    const view = byId("mergeView"); view.hidden = false;
    view.innerHTML = `<p class="hint">${complete} von ${Object.keys(key.assignment).length} Personen vollständig.</p>
      <table class="table compact"><thead><tr><th>Person</th><th>Fälle</th><th>Stand</th></tr></thead><tbody>${rows}</tbody></table>`;
  } catch (error) { state.panelRatings = null; toast(error.message, "error"); }
  updateSteps();
}
async function analyze() {
  try {
    if (!state.panelRatings) await mergeRatings();
    if (!state.panelRatings) throw new Error("Bitte zuerst die Bewertungen einlesen.");
    renderPanelAnalysis(state.panelRatings.data);
    state.analysisDone = true;
    updateSteps();
  } catch (error) { toast(error.message, "error"); }
}
const RESULT_LABEL = { hit: "Treffer", no_hit: "kein Treffer", disputed: "strittig", not_assessable: "nicht beurteilbar" };
const ci = (v) => v ? `[${fmt(v[0], 3)}; ${fmt(v[1], 3)}]` : "–";
function renderPanelAnalysis(data) {
  const view = byId("analysisView"); view.hidden = false;
  const qRows = Object.entries(data.questions).map(([q, v]) => `<tr><td>${q.toUpperCase()}</td><td class="num">${v.alpha === null ? "–" : fmt(v.alpha, 3)}</td><td>${ci(v.alpha_ci95)}</td><td class="num">${v.pairwise_agreement === null ? "–" : pct(v.pairwise_agreement)}</td><td>${ci(v.pairwise_ci95)}</td><td class="num">${v.not_assessable_share === null ? "–" : pct(v.not_assessable_share)}</td></tr>`).join("");
  const hitRows = Object.keys(data.qualified_hit_rate.primary).map((k) => { const [arch, model] = k.split("|");
    return `<tr><td>${arch === "mas" ? "MAS" : "SAS-2"}</td><td>${escapeHtml(model)}</td><td class="num">${pct(data.qualified_hit_rate.primary[k])}</td><td class="num">${pct(data.qualified_hit_rate.lenient[k])}</td><td class="num">${data.arms.filter((a) => `${a.architecture}|${a.model}` === k).length}</td></tr>`; }).join("");
  const val = (v) => `${v.agreement === null ? "–" : pct(v.agreement)} ${ci(v.ci95_wilson)} (n = ${v.n})`;
  view.innerHTML = `<h2>Auswertung</h2>
    <h3>Qualified-Hit je Arm</h3>
    <table class="table compact"><thead><tr><th>Architektur</th><th>Modell</th><th>primär</th><th>Sensitivität (strittig/n. b. = Treffer)</th><th>Arme</th></tr></thead><tbody>${hitRows}</tbody></table>
    <h3>Fälle</h3><p>${Object.entries(data.result_counts).map(([k, v]) => `${escapeHtml(RESULT_LABEL[k] || k)}: ${v}`).join(" · ")} · einstimmig: ${data.unanimous_share === null ? "–" : pct(data.unanimous_share)}</p>
    ${data.unsampled_recommended_cases.length ? `<p class="hint">${data.unsampled_recommended_cases.length} empfohlene Fälle nicht gezogen; Schichtgewichte stehen im Schlüssel.</p>` : ""}
    <h3>Übereinstimmung je Frage</h3>
    <table class="table compact"><thead><tr><th>Frage</th><th>Alpha</th><th>95 %-KI</th><th>Paarweise</th><th>95 %-KI</th><th>nicht beurteilbar</th></tr></thead><tbody>${qRows}</tbody></table>
    <h3>Gültigkeit</h3><ul class="small-list"><li>F2 gegen technischen Auszugsabgleich: ${val(data.validity.f2_vs_excerpt_verified)}</li><li>F1 gegen Betriebsstatus: ${val(data.validity.f1_vs_operating_status)}</li></ul>
    <h3>Gescheiterte Glieder (F3 = nein)</h3><p>${Object.entries(data.f3_failed_links).map(([k, v]) => `${escapeHtml(k)}: ${v}`).join(" · ") || "keine"}</p>
    <div class="btn-row"><button class="btn" type="button" id="downloadPanelResultBtn">Ergebnis als JSON sichern</button></div>`;
  byId("downloadPanelResultBtn").addEventListener("click", () => downloadJson(data, `auswertung-${data.panel_id.slice(6, 14)}.json`));
}
function caseSheetPayload() {
  const fields = ["csIndustry", "csProfile", "csProcesses", "csNeed", "csExclusions", "csUncertainties", "csAuthor"];
  if (fields.every((id) => !byId(id).value.trim())) return null;
  let website = byId("domainHint").value.trim();
  if (website && !/^https?:\/\//i.test(website)) website = `https://${website}`;
  return { organization_name: byId("organizationName").value.trim(), website,
    industry: byId("csIndustry").value.trim(), profile: byId("csProfile").value.trim(),
    processes: byId("csProcesses").value, need: byId("csNeed").value.trim(),
    search_area: "",
    exclusion_criteria: byId("csExclusions").value, uncertainties: byId("csUncertainties").value,
    author: byId("csAuthor").value.trim(), created_at: new Date().toISOString(),
    public_sources_only: byId("csPublic").checked };
}

/* ---------- Fragebogen der Transferprüfung ---------- */
const SUS_ITEMS = [
  "Ich kann mir vorstellen, dieses System regelmäßig zu nutzen.",
  "Ich empfand das System als unnötig komplex.",
  "Ich empfand das System als einfach zu nutzen.",
  "Ich glaube, ich würde die Hilfe einer technisch versierten Person benötigen, um das System nutzen zu können.",
  "Ich fand, die verschiedenen Funktionen des Systems waren gut integriert.",
  "Ich fand, es gab im System zu viele Inkonsistenzen.",
  "Ich kann mir vorstellen, dass die meisten Menschen den Umgang mit dem System sehr schnell lernen.",
  "Ich empfand die Bedienung als sehr umständlich.",
  "Ich fühlte mich bei der Nutzung des Systems sehr sicher.",
  "Ich musste eine Menge lernen, bevor ich anfangen konnte, das System zu nutzen.",
];
const MEM_ITEMS = [
  ["peou_1", "Das Referenzmodell ist leicht zu verstehen."],
  ["peou_2", "Es wäre leicht, das Modell auf ein weiteres Unternehmen zu übertragen."],
  ["pu_1", "Das Modell würde die Vorauswahl von Startups für ein Unternehmen verbessern."],
  ["pu_2", "Die Belegpflicht und die Prüfung machen die Ergebnisse vertrauenswürdiger."],
  ["itu_1", "Ich würde das Modell in einem passenden Projekt einsetzen."],
  ["itu_2", "Ich würde das Modell einer Kollegin oder einem Kollegen empfehlen."],
];
function renderQuestionnaire() {
  const scale = (name) => `<span class="likert">${[1, 2, 3, 4, 5].map((v) => `<label><input type="radio" name="${name}" value="${v}"> ${v}</label>`).join("")}</span>`;
  byId("questionItems").innerHTML = `<h3>System Usability Scale</h3>`
    + SUS_ITEMS.map((text, i) => `<div class="q-item"><span>${i + 1}. ${escapeHtml(text)}</span>${scale(`sus_${i + 1}`)}</div>`).join("")
    + `<h3 style="margin-top:10px">Referenzmodell</h3>`
    + MEM_ITEMS.map(([id, text]) => `<div class="q-item"><span>${escapeHtml(text)}</span>${scale(id)}</div>`).join("");
}
function questionnaireValues() {
  const value = (name) => { const el = document.querySelector(`input[name="${name}"]:checked`); return el ? Number(el.value) : null; };
  const sus = SUS_ITEMS.map((_, i) => value(`sus_${i + 1}`));
  // SUS nach Brooke (1996): ungerade Aussagen (Wert − 1), gerade (5 − Wert), Summe × 2,5.
  const susScore = sus.every((v) => v !== null)
    ? sus.reduce((sum, v, i) => sum + (i % 2 === 0 ? v - 1 : 5 - v), 0) * 2.5 : null;
  const mem = Object.fromEntries(MEM_ITEMS.map(([id]) => [id, value(id)]));
  return { sus_items: sus, sus_score: susScore, mem_items: mem,
    open_reuse: byId("openReuse").value.trim(), open_advise_against: byId("openAdvise").value.trim(),
    instrument_note: "SUS: Brooke (1996), deutsche Arbeitsübersetzung; MEM-Fragen angelehnt an Moody (2003)." };
}
function updateSusScore() {
  const q = questionnaireValues();
  byId("susScore").textContent = q.sus_score === null ? "SUS-Wert: noch nicht vollständig." : `SUS-Wert: ${fmt(q.sus_score, 1)} von 100.`;
}

/* ---------- Projekt-Import/Export und Transferprüfung ---------- */
function projectMessage(text, error = false) {
  const el = byId("projectMessage");
  el.hidden = false; el.textContent = text; el.classList.toggle("is-error", error);
}
function recordTransfer(type, detail = {}) {
  const t = state.transfer;
  if (t.session) { t.session.events.push({ at: new Date().toISOString(), type, ...detail }); t.exported = false; }
}
async function validateWorkspace(value) {
  const { data } = await requestJson("/api/comparison/workspace/validate", { method: "POST", body: JSON.stringify(value) });
  if (data.status !== "valid") throw new Error("Projekt konnte nicht geprüft werden.");
  return data;
}
function currentWorkspace() {
  return { schema_version: "venturescout.workspace.v1", name: byId("organizationName").value.trim(),
    organization_name: byId("organizationName").value.trim(), search_prompt: byId("searchPrompt").value.trim(),
    event_time: localDateTimeToIso(byId("eventTime").value) };
}
function applyWorkspace(ws) {
  byId("operatorToken").value = "";
  byId("datasetSplit").value = "pilot"; byId("memoryMode").value = "off"; byId("repetitions").value = "1";
  byId("organizationName").value = ws.organization_name;
  byId("searchPrompt").value = ws.search_prompt; byId("eventTime").value = isoToLocalInput(ws.event_time);
  schedulePreview();
}
async function exportProject() {
  try {
    if (byId("datasetSplit").value !== "pilot" || byId("memoryMode").value !== "off" || Number(byId("repetitions").value) !== 1)
      throw new Error("Projekttransfer verwendet Pilot, Memory aus und eine Wiederholung.");
    const result = await validateWorkspace(currentWorkspace());
    downloadJson(result.receipt, `veriscout-projekt-${result.receipt.workspace_sha256.slice(0, 12)}.json`);
    recordTransfer("project_export", { workspace_sha256: result.receipt.workspace_sha256, task_input_hash: result.task_input_hash });
    projectMessage(`Projekt exportiert (${result.receipt.workspace_sha256.slice(0, 16)}). Ohne Zugangsdaten und Ergebnisse.`);
  } catch (error) { projectMessage(error.message, true); recordTransfer("project_export_rejected"); }
}
async function importProject(file) {
  if (!file) return;
  try {
    if (file.size > 16384) throw new Error("Projektdateien dürfen höchstens 16 KB groß sein.");
    const result = await validateWorkspace(JSON.parse(await file.text()));
    applyWorkspace(result.receipt.workspace);
    recordTransfer("project_import", { workspace_sha256: result.receipt.workspace_sha256, warnings: result.warnings });
    projectMessage(`Projekt importiert und geprüft. ${result.warnings.join(" ")}`);
  } catch (error) { projectMessage(`Import abgewiesen. ${error.message}`, true); recordTransfer("project_import_rejected"); }
  finally { byId("workspaceFile").value = ""; }
}
function renderTransferTasks() {
  const p = state.transfer.protocol;
  byId("transferTasks").innerHTML = p.tasks.map((task) => `
    <article class="task" id="task-${task.id}">
      <div class="task-head"><span class="no">${escapeHtml(task.id)}</span><h3>${escapeHtml(task.title)}</h3><span class="hint">ca. ${escapeHtml(task.minutes)} Min. · <span id="time-${task.id}">nicht begonnen</span></span></div>
      <p>${escapeHtml(task.instruction)}</p>
      <details class="evidence"><summary>Beobachtungskriterium</summary><p class="hint">${escapeHtml(task.criterion)}</p></details>
      <div class="grid-2">
        <label class="field" for="outcome-${task.id}"><span>Urteil der beobachtenden Person</span><select id="outcome-${task.id}">
          <option value="not_observed">Noch nicht beurteilt</option><option value="independent">Ohne Hilfe abgeschlossen</option>
          <option value="assisted">Mit Hilfe abgeschlossen</option><option value="blocked">Nicht abgeschlossen</option></select></label>
        <label class="field" for="hints-${task.id}"><span>Anzahl Hilfen</span><input id="hints-${task.id}" type="number" min="0" max="99" value="0"></label>
      </div>
      <label class="field" for="notes-${task.id}"><span>Beobachtung</span><textarea id="notes-${task.id}" rows="3" maxlength="2000" placeholder="Was war erkennbar, was blieb unklar? Keine vertraulichen Informationen."></textarea></label>
      <div class="btn-row"><button class="btn" type="button" data-task-start="${task.id}" disabled>Aufgabe starten</button>
        <button class="btn" type="button" data-task-finish="${task.id}" disabled>Beobachtung speichern</button><span class="hint" id="recorded-${task.id}"></span></div>
    </article>`).join("");
}
async function beginTransfer() {
  const t = state.transfer;
  const code = byId("participantCode").value.trim();
  if (!/^[A-Za-z0-9_-]{2,30}$/.test(code)) { toast("Bitte einen Teilnehmercode mit 2–30 Zeichen angeben.", "error"); return; }
  try {
    t.protocol = (await requestJson("/api/comparison/reuse/protocol")).data;
    renderTransferTasks();
    t.session = { schema_version: "venturescout.observation.v1", session_id: crypto.randomUUID(), participant_code: code,
      started_at: new Date().toISOString(), protocol_version: t.protocol.version, release_sha256: t.protocol.release_sha256,
      policy_sha256: t.protocol.policy_sha256, protocol_tasks: t.protocol.tasks, events: [], limitations: t.protocol.limitations,
      measurement_note: "Urteile sind manuell erfasste Beobachtungen, keine automatisch geprüften Erfolgsnachweise. Browserereignisse sind nicht signiert." };
    byId("beginTransferBtn").disabled = true; byId("participantCode").disabled = true; byId("exportTransferBtn").disabled = false;
    document.querySelectorAll("[data-task-start]").forEach((el) => { el.disabled = false; });
    byId("transferStatus").textContent = `Sitzung läuft · Version ${t.protocol.release_sha256.slice(0, 12)}. Keine API-Kosten.`;
    recordTransfer("session_started");
  } catch (error) { toast(error.message, "error"); }
}
function startTask(id) {
  const t = state.transfer;
  if (!t.session || t.active) { toast("Bitte zuerst die laufende Aufgabe abschließen."); return; }
  t.active = id; t.starts.set(id, { at: new Date().toISOString(), clock: performance.now() });
  document.querySelectorAll("[data-task-start]").forEach((el) => { el.disabled = true; });
  document.querySelector(`[data-task-finish="${id}"]`).disabled = false;
  byId(`time-${id}`).textContent = "läuft";
  recordTransfer("task_started", { task_id: id });
}
function finishTask(id) {
  const t = state.transfer;
  if (t.active !== id) return;
  const outcome = byId(`outcome-${id}`).value;
  const hints = Number(byId(`hints-${id}`).value);
  const notes = byId(`notes-${id}`).value.trim();
  if (outcome === "not_observed" || !notes || !Number.isInteger(hints) || hints < 0 || hints > 99
      || (outcome === "independent" && hints > 0) || (outcome === "assisted" && hints === 0)) {
    toast("Bitte Urteil, Beobachtung und eine passende Anzahl Hilfen eintragen.", "error"); return;
  }
  const start = t.starts.get(id);
  const row = { task_id: id, started_at: start.at, finished_at: new Date().toISOString(),
    elapsed_seconds: Math.round((performance.now() - start.clock) / 1000), outcome, hints, notes };
  t.outcomes.set(id, row); recordTransfer("observer_judgment", row);
  byId(`recorded-${id}`).textContent = "Protokolliert"; byId(`time-${id}`).textContent = `${row.elapsed_seconds} s`;
  ["outcome", "hints", "notes"].forEach((k) => { byId(`${k}-${id}`).disabled = true; });
  document.querySelector(`[data-task-finish="${id}"]`).disabled = true;
  t.active = null;
  document.querySelectorAll("[data-task-start]").forEach((el) => { el.disabled = t.outcomes.has(el.dataset.taskStart); });
}
function exportTransfer() {
  const t = state.transfer;
  if (!t.session) return;
  const observations = t.protocol.tasks.map((task) => t.outcomes.get(task.id) || { task_id: task.id, outcome: "not_observed" });
  const complete = observations.every((r) => r.outcome !== "not_observed");
  downloadJson({ ...t.session, exported_at: new Date().toISOString(), status: complete ? "observations_complete" : "partial", observations,
    questionnaire: questionnaireValues(),
    counts: { observed: t.outcomes.size, independent: observations.filter((x) => x.outcome === "independent").length,
      assisted: observations.filter((x) => x.outcome === "assisted").length, blocked: observations.filter((x) => x.outcome === "blocked").length } },
  `veriscout-transfer-${t.session.participant_code}-${t.session.session_id.slice(0, 8)}.json`);
  t.exported = true;
  byId("transferStatus").textContent = complete ? "Beobachtungen exportiert." : "Zwischenstand exportiert. Offene Aufgaben bleiben offen.";
}

/* ---------- Start ---------- */
document.addEventListener("DOMContentLoaded", async () => {
  const tabButtons = [...document.querySelectorAll(".stepper [data-tab]")];
  tabButtons.forEach((tab, index) => {
    tab.addEventListener("click", () => showTab(tab.dataset.tab));
    tab.addEventListener("keydown", (e) => {
      const keys = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabButtons.length - 1 };
      if (!(e.key in keys)) return;
      e.preventDefault();
      const next = tabButtons[(keys[e.key] + tabButtons.length) % tabButtons.length];
      showTab(next.dataset.tab); next.focus();
    });
  });
  const initial = (location.hash || "#auftrag").slice(1);
  showTab(["auftrag", "ergebnis", "bewertung", "transfer"].includes(initial) ? initial : "auftrag");
  window.addEventListener("hashchange", () => {
    const name = location.hash.slice(1);
    if (["auftrag", "ergebnis", "bewertung", "transfer"].includes(name)) showTab(name);
  });
  byId("eventTime").value = isoToLocalInput(new Date().toISOString());
  ["organizationName", "domainHint", "searchPrompt"].forEach((id) => byId(id).addEventListener("input", schedulePreview));
  ["datasetSplit", "eventTime"].forEach((id) => byId(id).addEventListener("change", schedulePreview));
  ["repetitions", "memoryMode", "operatorToken"].forEach((id) => byId(id).addEventListener("input", renderPreflight));
  byId("memoryMode").addEventListener("change", renderPreflight);
  byId("startRunBtn").addEventListener("click", startRun);
  byId("runSelect").addEventListener("change", (e) => openRun(e.target.value));
  byId("pairSelect").addEventListener("change", (e) => { state.pairIndex = Number(e.target.value); renderResult(); });
  byId("arms").addEventListener("click", (e) => {
    const prepare = e.target.closest("[data-release-prepare]");
    const action = e.target.closest("[data-release-action]");
    if (prepare) prepareRelease(prepare);
    if (action) executeRelease(action);
  });
  byId("buildSheetBtn").addEventListener("click", buildSheet);
  byId("sheetScope").addEventListener("change", () => {
    state.sheet = null; byId("sheetInfo").textContent = "";
    if (byId("sheetScope").value === "probe") { byId("panelRaters").value = 3; byId("panelPerRater").value = 12; byId("panelOverlap").value = 3; }
    else { byId("panelRaters").value = 10; byId("panelPerRater").value = 12; byId("panelOverlap").value = 3; }
    updateReviewButtons();
  });
  byId("downloadSheetBtn").addEventListener("click", downloadSheet);
  byId("downloadKeyBtn").addEventListener("click", downloadKey);
  byId("mergeBtn").addEventListener("click", mergeRatings);
  initDropzones();
  document.querySelectorAll("[data-dropzone] .dz-input").forEach((input) => input.addEventListener("change", updateSteps));
  document.querySelectorAll("[data-dz-clear]").forEach((b) => b.addEventListener("click", updateSteps));
  byId("recentRuns").addEventListener("click", (e) => {
    const card = e.target.closest("[data-run-id]");
    if (card) openRun(card.dataset.runId);
  });
  byId("preflightBox").querySelector("summary").addEventListener("click", () => { byId("preflightBox").dataset.userToggled = "1"; });
  byId("printBtn").addEventListener("click", printResult);
  initThemeSwitch();
  byId("crmRefreshBtn").addEventListener("click", loadCrm);
  ["csIndustry", "csProfile", "csProcesses", "csNeed", "csExclusions", "csUncertainties", "csAuthor", "csPublic"].forEach((id) => byId(id).addEventListener("input", renderPreflight));
  renderQuestionnaire();
  byId("questionnaire").addEventListener("change", updateSusScore);
  byId("analyzeBtn").addEventListener("click", analyze);
  byId("downloadEvidenceListBtn").addEventListener("click", downloadEvidenceList);
  byId("exportProjectBtn").addEventListener("click", exportProject);
  byId("importProjectBtn").addEventListener("click", () => byId("workspaceFile").click());
  byId("workspaceFile").addEventListener("change", (e) => importProject(e.target.files[0]));
  byId("newProjectBtn").addEventListener("click", () => {
    applyWorkspace({ name: "Rechercheprojekt", organization_name: "", search_prompt: "", event_time: new Date().toISOString() });
    projectMessage("Neues Projekt angelegt."); recordTransfer("new_project");
  });
  byId("beginTransferBtn").addEventListener("click", beginTransfer);
  byId("exportTransferBtn").addEventListener("click", exportTransfer);
  byId("invalidWorkspaceBtn").addEventListener("click", () => {
    downloadJson({ schema_version: "unsupported-test-only", threshold: 1 }, "absichtlich-ungueltiges-projekt.json");
    recordTransfer("invalid_fixture_download");
  });
  byId("transferTasks").addEventListener("click", (e) => {
    const start = e.target.closest("[data-task-start]");
    const finish = e.target.closest("[data-task-finish]");
    if (start) startTask(start.dataset.taskStart);
    if (finish) finishTask(finish.dataset.taskFinish);
  });
  window.addEventListener("beforeunload", (e) => {
    if (state.running || (state.transfer.session && !state.transfer.exported)) { e.preventDefault(); e.returnValue = ""; }
  });
  await loadConfig();
  await loadRuns();
  loadCrm();
  try {
    state.transfer.protocol = (await requestJson("/api/comparison/reuse/protocol")).data;
    renderTransferTasks();
  } catch {
    byId("transferTasks").textContent = "Transferdienst nicht erreichbar.";
    byId("beginTransferBtn").disabled = true;
  }
});
