"""Offline-Bewertungsbogen fuer das Panel (eine HTML-Datei, keine Netzaufrufe)."""

TEMPLATE = r'''<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>VeriScout Bewertungsbogen</title>
<style>
:root { --bg:#f5f6f8; --surface:#fff; --surface-2:#f6f7f9; --text:#111827; --muted:#4b5563; --faint:#636b79;
  --border:#e3e6eb; --border-strong:#cfd4dc; --primary:#1f3a5f; --primary-text:#1f3a5f; --on-primary:#fff;
  --accent:#1d4ed8; --ok:#146c36; --ok-bg:#e7f6ec; --bad:#b42318; --bad-bg:#fdecea; --warn:#8a4f06; --warn-bg:#fdf3e1;
  --mark:#fde68a; --field:#fff; }
@media (prefers-color-scheme: dark) { :root { --bg:#0e1116; --surface:#161a21; --surface-2:#1c212a; --text:#e7eaf0;
  --muted:#a7b0bd; --faint:#8e99a9; --border:#2a303a; --border-strong:#3b4350; --primary:#3d6bd1; --primary-text:#9dbcff;
  --accent:#7aa7ff; --ok:#5fd08a; --ok-bg:#12291c; --bad:#ff8a80; --bad-bg:#321719; --warn:#f2b54a; --warn-bg:#2f2410;
  --mark:#5c4a12; --field:#0f1318; } }
* { box-sizing: border-box; }
body { margin:0; font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif; background:var(--bg); color:var(--text); }
header { position:sticky; top:0; z-index:5; background:var(--surface); border-bottom:1px solid var(--border);
  display:flex; gap:12px; align-items:center; flex-wrap:wrap; padding:10px 20px; }
header strong { font-size:16px; } header .grow { flex:1; }
.progress { min-width:160px; font-size:13px; color:var(--muted); }
.bar { height:6px; background:var(--border); border-radius:99px; overflow:hidden; margin-top:3px; }
.bar i { display:block; height:100%; background:var(--ok); width:0; }
button, select, textarea, input { font:inherit; color:inherit; }
.btn { border:1px solid var(--border-strong); background:var(--surface); border-radius:8px; padding:7px 13px; cursor:pointer; }
.btn-primary { background:var(--primary); border-color:var(--primary); color:var(--on-primary); }
.btn:disabled { opacity:.5; cursor:not-allowed; }
main { max-width:1180px; margin:0 auto; padding:20px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:10px; padding:16px 18px; margin-bottom:14px; }
.notice { background:var(--warn-bg); color:var(--warn); border-radius:8px; padding:8px 12px; }
.hint { color:var(--muted); font-size:13px; }
.layout { display:grid; grid-template-columns:270px 1fr; gap:16px; align-items:start; }
nav.list { position:sticky; top:70px; max-height:calc(100vh - 90px); overflow:auto; }
nav.list h3 { font-size:12px; text-transform:uppercase; letter-spacing:.04em; color:var(--faint); margin:12px 0 4px; }
nav.list button { display:flex; gap:8px; width:100%; text-align:left; border:0; background:none; padding:6px 8px; border-radius:6px; cursor:pointer; color:var(--text); }
nav.list button[aria-current="true"] { background:var(--surface-2); font-weight:600; }
nav.list .dot { width:10px; height:10px; border-radius:50%; border:1.5px solid var(--border-strong); margin-top:6px; flex:none; }
nav.list .done .dot { background:var(--ok); border-color:var(--ok); }
dl.kv { display:grid; grid-template-columns:160px 1fr; gap:4px 12px; margin:0; }
dl.kv dt { color:var(--faint); font-size:13px; } dl.kv dd { margin:0; overflow-wrap:anywhere; }
.claim { border-top:1px solid var(--border); padding:8px 0; font-size:14px; }
.claim q { display:block; color:var(--muted); font-style:italic; margin:3px 0; }
.claim.marked { background:var(--surface-2); border-left:4px solid var(--accent); padding-left:10px; border-radius:0 6px 6px 0; }
.link-head { font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--faint); margin:14px 0 2px; }
details.more { margin-top:12px; } details.more summary { cursor:pointer; color:var(--accent); font-size:14px; }
.crit { background:var(--surface-2); border-radius:8px; padding:6px 10px; margin:6px 0; font-size:14px; } .crit ul { margin:4px 0 0; padding-left:18px; }
.link-row { border-left:3px solid var(--border-strong); padding-left:10px; margin:8px 0; }
.basis { text-transform:none; letter-spacing:0; font-size:12px; font-weight:600; border-radius:99px; padding:1px 8px; margin-left:6px; }
.basis-ok { background:var(--ok-bg); color:var(--ok); } .basis-der { background:var(--warn-bg); color:var(--warn); } .basis-none { background:var(--surface-2); color:var(--muted); }
.claim .tag { font-size:12px; font-weight:600; color:var(--accent); }
.claim a { color:var(--accent); font-size:13px; overflow-wrap:anywhere; }
fieldset { border:1px solid var(--border); border-radius:8px; padding:10px 12px; margin:0 0 10px; }
legend { font-weight:600; padding:0 4px; }
.opts { display:flex; gap:14px; flex-wrap:wrap; margin:6px 0; }
.opts label { display:inline-flex; gap:6px; align-items:center; cursor:pointer; }
textarea { width:100%; min-height:54px; border:1px solid var(--border-strong); border-radius:8px; padding:6px 8px; background:var(--field); }
select { border:1px solid var(--border-strong); border-radius:8px; padding:6px 8px; background:var(--field); }
.missing { border-color:var(--bad) !important; }
.nav-row { display:flex; justify-content:space-between; gap:8px; }
mark { background:var(--mark); color:inherit; }
@media (max-width:820px) { .layout { grid-template-columns:1fr; } nav.list { position:static; max-height:none; } dl.kv { grid-template-columns:1fr; } }
</style>
</head>
<body>
<header>
  <strong>VeriScout · Bewertungsbogen</strong><span id="who" class="hint"></span>
  <span class="grow"></span>
  <div class="progress"><span id="progressText"></span><div class="bar"><i id="progressBar"></i></div></div>
  <label class="btn" for="loadFile">Zwischenstand laden<input id="loadFile" type="file" accept=".json,application/json" hidden></label>
  <button class="btn btn-primary" id="exportBtn" type="button" disabled>Bewertung exportieren</button>
</header>
<main id="main"></main>
<script id="panel-data" type="application/json">__PANEL_DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("panel-data").textContent);
const SCHEMA = "veriscout-panel-ratings-v1";
const Q = ["f1", "f2", "f3", "f4", "f5"];
const state = { rater: "", index: 0, answers: {}, mode: "rating", practice: {}, practiceDone: false };
// Uebung: eigene Antworten, eigener Speicher; wird nie exportiert oder ausgewertet.
const PRACTICE = Array.isArray(DATA.practice) ? DATA.practice : [];
const PRACTICE_BY_ID = Object.fromEntries(PRACTICE.map((p) => [p.practice_id, p]));
const isPractice = (m = state.mode) => m === "practice";
const caseOf = (cid, m = state.mode) => isPractice(m) ? PRACTICE_BY_ID[cid].case : DATA.cases[cid];
const taskOf = (cid, m = state.mode) => isPractice(m) ? PRACTICE_BY_ID[cid].task : DATA.tasks[DATA.cases[cid].task_id];
const storeOf = (m = state.mode) => isPractice(m) ? state.practice : state.answers;
const $ = (id) => document.getElementById(id);
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (u) => { try { const p = new URL(String(u || "")); return (p.protocol === "https:" || p.protocol === "http:") ? p.href : ""; } catch { return ""; } };
const storeKey = () => `veriscout-panel-${DATA.panel_id}-${state.rater}`;
function save() {
  try {
    localStorage.setItem(storeKey(), JSON.stringify(state.answers));
    localStorage.setItem(storeKey() + "-uebung", JSON.stringify({ answers: state.practice, done: state.practiceDone }));
  } catch { /* ohne Speicher */ }
}
function restore() {
  try { const raw = localStorage.getItem(storeKey()); if (raw) state.answers = JSON.parse(raw) || {}; } catch { state.answers = {}; }
  try { const p = JSON.parse(localStorage.getItem(storeKey() + "-uebung") || "{}"); state.practice = p.answers || {}; state.practiceDone = !!p.done; } catch { state.practice = {}; }
}
const ratingCases = () => DATA.raters[state.rater] || [];
const myCases = (m = state.mode) => isPractice(m) ? PRACTICE.map((p) => p.practice_id) : ratingCases();
// Begruendung bei Antworten gegen das Startup, bei nicht beurteilbar und bei F3 immer.
function needsReason(q, v) {
  if (!v) return false;
  if (q === "f3") return true;
  if (q === "f4" || q === "f5") return v === "yes" || v === "na";
  return v === "no" || v === "na";
}
const exclusions = (cid, m = state.mode) => ((taskOf(cid, m).case_sheet || {}).exclusion_criteria || []).map((x) => typeof x === "string" ? x : x.text);
const MISSING_LABEL = { f1: "F1", f2: "F2", f3: "F3", f4: "F4", f5: "F5", f3_link: "gescheitertes Glied bei F3", f4_criterion: "Kriterium bei F4" };
function missingFor(cid, m = state.mode) {
  const a = storeOf(m)[cid] || {}; const r = a.reasons || {}; const miss = [];
  Q.forEach((q) => { if (!a[q]) miss.push(q); });
  Q.forEach((q) => { if (needsReason(q, a[q]) && !String(r[q] || "").trim()) miss.push("r_" + q); });
  if (a.f3 === "no" && !a.f3_link) miss.push("f3_link");
  if (a.f4 === "yes" && exclusions(cid, m).length && !a.f4_criterion) miss.push("f4_criterion");
  return miss;
}
const missingText = (m) => m.map((x) => x.startsWith("r_") ? `Begründung ${x.slice(2).toUpperCase()}` : (MISSING_LABEL[x] || x)).join(", ");

// Zeit je Fall: Sekunden, solange der Fall offen ist.
let openedAt = 0, openedCase = "";
function stopClock() {
  if (openedCase && openedAt) { const a = (state.answers[openedCase] = state.answers[openedCase] || { reasons: {} }); a.seconds = (a.seconds || 0) + Math.round((Date.now() - openedAt) / 1000); save(); }
  openedAt = 0; openedCase = "";
}
function startClock(cid) { stopClock(); if (isPractice()) return; openedCase = cid; openedAt = Date.now(); }
window.addEventListener("beforeunload", stopClock);
document.addEventListener("visibilitychange", () => { if (document.hidden) stopClock(); else if (state.rater) startClock(myCases()[state.index]); });

function progress() {
  const ids = myCases(); const done = ids.filter((c) => !missingFor(c).length).length;
  $("progressText").textContent = isPractice() ? `Übung ${state.index + 1} von ${ids.length}` : `${done} von ${ids.length} Fällen vollständig`;
  $("progressBar").style.width = ids.length ? `${100 * done / ids.length}%` : "0";
  $("exportBtn").disabled = !state.rater;
  document.querySelectorAll("nav.list [data-i]").forEach((b) => b.classList.toggle("done", !missingFor(ids[+b.dataset.i]).length));
}

function start() {
  const raters = Object.keys(DATA.raters).sort();
  const n = raters.length ? Math.max(...raters.map((r) => DATA.raters[r].length)) : 0;
  $("main").innerHTML = `<section class="card intro">
    <h1>Bewertungsbogen</h1>
    ${DATA.purpose === "schulung" ? `<p class="notice">Schulung: Diese Bewertungen zählen nicht für die Studie.</p>` : ""}
    <h2>Deine Rolle</h2>
    <p>Ein KI-System hat für mittelständische Unternehmen Startups gesucht, die einen öffentlich belegten Prozess nachhaltiger oder effizienter machen könnten. Du prüfst als unabhängige Person, ob ein vorgeschlagenes Startup mit seinen Belegen trägt. Ein Fall ist ein Startup zu einem Unternehmen. Du bekommst ${n} Fälle; rechne mit etwa 3 bis 5 Minuten je Fall.</p>
    <h2>Regeln</h2><ul>${DATA.rules.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>
    <h2>Die fünf Fragen</h2><ol>${Q.map((q) => `<li><strong>${esc(DATA.codebook[q].label)}:</strong> ${esc(DATA.codebook[q].question)}</li>`).join("")}</ol>
    <h2>Ablauf</h2><ol>
      <li>Kürzel wählen (steht in deiner Einladung).</li>
      ${PRACTICE.length ? `<li>Zuerst ${PRACTICE.length} Übungsfälle: Du beantwortest sie wie echte Fälle und siehst danach die Musterlösung mit Begründung. Die Übung zählt nicht und wird nicht mitgeschickt.</li>` : ""}
      <li>Je Unternehmen zuerst das Unternehmensprofil lesen, dann die Fälle dazu.</li>
      <li>Je Fall die Aussagen und Belege ansehen, Links bei Bedarf öffnen, die fünf Fragen beantworten.</li>
      <li>Dein Stand bleibt in diesem Browser gespeichert. Am Ende „Bewertung exportieren“ und die Datei an die Versuchsleitung schicken.</li>
    </ol>
    <label>Dein Kürzel <select id="raterSel"><option value="">wählen …</option>${raters.map((r) => `<option>${esc(r)}</option>`).join("")}</select></label>
    <button class="btn btn-primary" id="beginBtn" type="button">Bewertung beginnen</button>
    <p class="hint">Bogen ${esc(DATA.panel_id)}</p></section>`;
  $("beginBtn").addEventListener("click", () => {
    const r = $("raterSel").value; if (!r) { $("raterSel").classList.add("missing"); return; }
    if (!confirm(`Du bewertest als ${r}. Stimmt das Kürzel aus deiner Einladung?`)) return;
    state.rater = r; restore(); $("who").textContent = `Kürzel ${r}`; state.index = 0;
    state.mode = PRACTICE.length && !state.practiceDone ? "practice" : "rating"; render();
  });
}

// Textfragment, damit der Browser an der zitierten Stelle oeffnet.
function fragmentUrl(url, excerpt) {
  const base = safeUrl(url); if (!base) return "";
  const first = String(excerpt || "").split(/\s*(?:\.\.\.|…)\s*/).map((p) => p.replace(/\s+/g, " ").trim()).filter(Boolean)[0] || "";
  if (first.length < 8) return base;
  const enc = (t) => encodeURIComponent(t).replace(/-/g, "%2D").replace(/,/g, "%2C").replace(/&/g, "%26");
  const w = first.split(" ");
  const dir = w.length > 10 ? `${enc(w.slice(0, 5).join(" "))},${enc(w.slice(-5).join(" "))}` : enc(first);
  return `${base.replace(/:~:.*$/, "")}${base.includes("#") ? "" : "#"}:~:text=${dir}`;
}
const CHAIN = [
  ["Prozess des Unternehmens", ["target_process"], "process"],
  ["Input oder Ressource", ["input_stream", "input_stream_mechanism"], "input"],
  ["Fähigkeit des Startups", ["startup_capability", "transformation"], "capability"],
  ["Nutzbares Ergebnis", ["output_application", "relational_chain"], "result"],
];
function claimHtml(cl, c, sources) {
  const s = sources[cl.source_id] || {}; const url = safeUrl(s.url); const marked = cl.claim_id === c.marked_claim_id;
  const jump = cl.excerpt ? fragmentUrl(s.url, cl.excerpt) : url;
  return `<div class="claim ${marked ? "marked" : ""}">${marked ? `<div class="tag">Markierte Aussage für Frage 2</div>` : ""}
    ${marked ? `Laut dieser Quelle gilt: <strong>${esc(cl.claim_text)}</strong>` : esc(cl.claim_text)}
    ${cl.excerpt ? `<q>${marked ? `<mark>${esc(cl.excerpt)}</mark>` : esc(cl.excerpt)}</q>` : ""}
    ${url ? `<a href="${esc(jump)}" target="_blank" rel="noopener noreferrer">Beleg öffnen: ${esc(s.title || url)}</a>` : `<span class="hint">kein Beleg</span>`}
    ${safeUrl(s.verified_url) ? `<div class="hint">Der Satz steht nicht auf der genannten Seite, sondern hier: <a href="${esc(fragmentUrl(s.verified_url, cl.excerpt))}" target="_blank" rel="noopener noreferrer">${esc(s.verified_url)}</a></div>` : ""}</div>`;
}
// Gemischte Zeilen ("Fähigkeit belegt · Wirkung abgeleitet"): Farbe nach dem schwaechsten Teil.
const basisClass = (b) => b === "belegt" ? "ok" : String(b).includes("ohne Beleg") ? "none" : "der";
function claimsHtml(c) {
  const sources = Object.fromEntries((c.sources || []).map((s) => [s.source_id, s]));
  const seen = new Set(); const claims = (c.claims || []).filter((cl) => {
    const k = `${cl.field}|${cl.claim_text}|${cl.excerpt}`; if (seen.has(k)) return false; seen.add(k); return true; });
  const used = new Set();
  const marked = claims.find((cl) => cl.claim_id === c.marked_claim_id);
  if (marked) used.add(marked);
  const rows = CHAIN.map(([label, fields, row]) => {
    const items = claims.filter((cl) => fields.includes(cl.field) && !used.has(cl));
    items.forEach((cl) => used.add(cl));
    const basis = (c.chain_basis || {})[row] || "";
    return `<div class="link-row"><h3 class="link-head">${esc(label)}${basis ? ` <span class="basis basis-${basisClass(basis)}">${esc(basis)}</span>` : ""}</h3>${items.map((cl) => claimHtml(cl, c, sources)).join("") || `<p class="hint">Keine Aussage dazu.</p>`}</div>`;
  }).join("");
  const rest = claims.filter((cl) => !used.has(cl));
  return `${marked ? claimHtml(marked, c, sources) : ""}
    <h3>Die Kette (für Frage 3)</h3>${rows}
    ${rest.length ? `<details class="more"><summary>Weitere Angaben zu Identität und Gründung (${rest.length})</summary>${rest.map((cl) => claimHtml(cl, c, sources)).join("")}</details>` : ""}`;
}
function profileHtml(sheet, website) {
  const link = (u, t) => safeUrl(u) ? `<a href="${esc(safeUrl(u))}" target="_blank" rel="noopener noreferrer">${esc(t || u)}</a>` : esc(t || u || "–");
  if (!sheet) return `<dl class="kv"><dt>Website</dt><dd>${link(website)}</dd></dl><p class="hint">Für dieses Unternehmen liegt kein Profil vor. Nutze die Website.</p>`;
  const list = (xs) => (xs || []).map((x) => `<li>${esc(typeof x === "string" ? x : x.text)}${x && x.source_url ? ` · ${link(x.source_url, "Quelle")}` : ""}</li>`).join("");
  return `<dl class="kv"><dt>Website</dt><dd>${link(website)}</dd>
    ${sheet.profile ? `<dt>Kurzprofil</dt><dd>${esc(sheet.profile)}</dd>` : ""}
    ${(sheet.processes || []).length ? `<dt>Belegte Prozesse</dt><dd><ul>${list(sheet.processes)}</ul></dd>` : ""}
    ${sheet.need ? `<dt>Bedarf</dt><dd>${esc(sheet.need)}</dd>` : ""}
    ${(sheet.uncertainties || []).length ? `<dt>Unsicherheiten</dt><dd><ul>${list(sheet.uncertainties)}</ul></dd>` : ""}</dl>`;
}
const LABELS = {
  f1: { yes: "Ja", no: "Nein", na: "Nicht beurteilbar" },
  f2: { yes: "Ja", no: "Nein", na: "Nicht beurteilbar" },
  f3: { yes: "Ja, schlüssig", no: "Nein", na: "Nicht beurteilbar" },
  f4: { yes: "Ja, ein Kriterium greift", no: "Nein, keines greift", na: "Nicht beurteilbar" },
  f5: { yes: "Ja, übertrieben", no: "Nein, angemessen" },
};
function question(cid, q, c) {
  const a = storeOf()[cid] || {}; const cb = DATA.codebook[q];
  const locked = isPractice() && a._revealed ? "disabled" : "";
  const miss = missingFor(cid);
  const crit = exclusions(cid);
  // Impressum: zuerst das vom System abgerufene (R2), sonst eine Quelle mit Impressum-Adresse.
  const impressum = (c.impressum && safeUrl(c.impressum.url)) ? c.impressum
    : (c.sources || []).find((s) => /impressum|imprint|legal/i.test(`${s.url} ${s.title}`));
  return `<fieldset class="${miss.includes(q) && a._touched ? "missing" : ""}"><legend>Frage ${q.slice(1)}: ${esc(cb.label)}</legend>
    <div>${esc(cb.question)}</div><div class="hint">${esc(cb.help)}</div>
    ${q === "f1" ? `<div class="hint">${safeUrl(c.website) ? `<a href="${esc(safeUrl(c.website))}" target="_blank" rel="noopener noreferrer">Website des Startups</a>` : "keine Website angegeben"}${impressum && safeUrl(impressum.url) ? ` · <a href="${esc(safeUrl(impressum.url))}" target="_blank" rel="noopener noreferrer">Impressum</a>` : ""}</div>` : ""}
    ${q === "f4" ? (crit.length ? `<div class="crit"><strong>Ausschlusskriterien:</strong><ul>${crit.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>` : `<div class="hint">Kein Unternehmensprofil mit Ausschlusskriterien vorhanden.</div>`) : ""}
    <div class="opts">${Object.entries(LABELS[q]).map(([o, t]) => `<label><input type="radio" name="${q}" value="${o}" ${a[q] === o ? "checked" : ""} ${locked}> ${esc(t)}</label>`).join("")}</div>
    ${q === "f3" && a.f3 === "no" ? `<label>Gescheitertes Glied <select data-link><option value="">wählen …</option>${Object.entries(DATA.chain_labels).map(([k, v]) => `<option value="${k}" ${a.f3_link === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>` : ""}
    ${q === "f4" && a.f4 === "yes" && crit.length ? `<label>Welches Kriterium? <select data-crit><option value="">wählen …</option>${crit.map((x) => `<option ${a.f4_criterion === x ? "selected" : ""}>${esc(x)}</option>`).join("")}</select></label>` : ""}
    ${needsReason(q, a[q]) ? `<textarea data-reason="${q}" maxlength="1000" placeholder="Begründung in einem Satz" ${locked}>${esc((a.reasons || {})[q] || "")}</textarea>` : ""}
  </fieldset>`;
}
// Musterloesung: nur im Uebungsmodus und erst, nachdem der Fall vollstaendig beantwortet ist.
function solutionHtml(cid) {
  if (!isPractice()) return "";
  const a = state.practice[cid] || {}; if (!a._revealed) return "";
  const sol = PRACTICE_BY_ID[cid].solution || {};
  const rows = Q.map((q) => {
    const s = sol[q] || {}; const own = a[q]; const model = s.answer;
    const same = model ? (own === model ? `<span class="basis basis-ok">wie Musterlösung</span>` : `<span class="basis basis-none">abweichend</span>`) : "";
    return `<li><strong>Frage ${q.slice(1)}:</strong> Musterlösung ${model ? esc(LABELS[q][model]) : "<em>noch nicht hinterlegt</em>"}${q === "f3" && sol.f3_link ? ` (Glied: ${esc(DATA.chain_labels[sol.f3_link])})` : ""} · deine Antwort ${esc(LABELS[q][own] || "–")} ${same}${s.reason ? `<div class="hint">${esc(s.reason)}</div>` : ""}</li>`;
  }).join("");
  return `<section class="card"><h2>Musterlösung</h2>${PRACTICE_BY_ID[cid].status !== "freigegeben" ? `<p class="notice">Entwurf: Diese Musterlösung ist noch nicht freigegeben.</p>` : ""}<ol>${rows}</ol></section>`;
}

function render() {
  const P = isPractice();
  const ids = myCases(); const cid = ids[state.index]; const c = caseOf(cid); const task = taskOf(cid);
  const groupKey = (id) => P ? id : DATA.cases[id].task_id;
  const groupName = (g) => P ? `Übung: ${taskOf(g.t).organization_name}` : DATA.tasks[g.t].organization_name;
  const groups = []; ids.forEach((id, i) => { const t = groupKey(id); const g = groups.find((x) => x.t === t); g ? g.items.push(i) : groups.push({ t, items: [i] }); });
  const firstOfBlock = P || state.index === 0 || DATA.cases[ids[state.index - 1]].task_id !== c.task_id;
  const pa = P ? (state.practice[cid] || {}) : {};
  const nextLabel = P ? (pa._revealed ? (state.index === ids.length - 1 ? "Übung beenden, zu deinen Fällen" : "Nächster Übungsfall") : "Antwort abgeben, Musterlösung zeigen")
    : (state.index === ids.length - 1 ? "Fertig" : "Weiter");
  $("main").innerHTML = `<div class="layout">
    <nav class="list card" aria-label="Fälle">${groups.map((g) => `<h3>${esc(groupName(g))}</h3>${g.items.map((i) => `<button type="button" data-i="${i}" aria-current="${i === state.index}"><span class="dot"></span><span>${P ? "Übung " : ""}${i + 1}. ${esc(caseOf(ids[i]).name)}</span></button>`).join("")}`).join("")}</nav>
    <div>
      ${DATA.purpose === "schulung" ? `<p class="notice">Schulung: Diese Bewertungen zählen nicht für die Studie.</p>` : ""}
      ${P ? `<p class="notice"><strong>Übung.</strong> Dieser Fall zählt nicht und wird nicht mitgeschickt. Beantworte ihn wie einen echten Fall; danach siehst du die Musterlösung.</p>` : ""}
      <section class="card"><h2>Unternehmen: ${esc(task.organization_name)}</h2>
        <dl class="kv"><dt>Suchauftrag</dt><dd>${esc(task.search_prompt)}</dd></dl>
        <details ${firstOfBlock ? "open" : ""}><summary>Unternehmensprofil</summary>${profileHtml(task.case_sheet, task.website)}</details></section>
      <section class="card"><h2>${P ? "Übungsfall" : "Fall"} ${state.index + 1} von ${ids.length}: ${esc(c.name)}</h2>
        ${safeUrl(c.website) ? `<a href="${esc(safeUrl(c.website))}" target="_blank" rel="noopener noreferrer">${esc(c.website)}</a>` : ""}
        <p class="hint">Aussagen und Belege, wie das System sie geliefert hat.</p>
        ${claimsHtml(c)}
      </section>
      <section class="card" id="qs">${Q.map((q) => question(cid, q, c)).join("")}
        <div class="nav-row"><button class="btn" id="prevBtn" type="button" ${state.index === 0 ? "disabled" : ""}>Zurück</button>
        <span class="hint">${P ? "Übungsfall" : "Fall"} ${state.index + 1} von ${ids.length}</span>
        <button class="btn btn-primary" id="nextBtn" type="button">${esc(nextLabel)}</button></div></section>
      ${solutionHtml(cid)}
    </div></div>`;
  startClock(cid);
  document.querySelectorAll("nav.list [data-i]").forEach((b) => b.addEventListener("click", () => { state.index = +b.dataset.i; render(); window.scrollTo(0, 0); }));
  const store = storeOf(); const a = (store[cid] = store[cid] || { reasons: {} });
  $("qs").addEventListener("change", (e) => {
    if (e.target.name && Q.includes(e.target.name)) {
      a[e.target.name] = e.target.value;
      if (e.target.name === "f3" && e.target.value !== "no") delete a.f3_link;
      if (e.target.name === "f4" && e.target.value !== "yes") delete a.f4_criterion;
      save(); const y = window.scrollY; render(); window.scrollTo(0, y);
    }
    if (e.target.matches("[data-link]")) { a.f3_link = e.target.value; save(); progress(); }
    if (e.target.matches("[data-crit]")) { a.f4_criterion = e.target.value; save(); progress(); }
  });
  $("qs").addEventListener("input", (e) => { if (e.target.dataset.reason) { a.reasons = a.reasons || {}; a.reasons[e.target.dataset.reason] = e.target.value; save(); progress(); } });
  $("prevBtn").addEventListener("click", () => { state.index -= 1; render(); window.scrollTo(0, 0); });
  $("nextBtn").addEventListener("click", () => {
    const miss = missingFor(cid);
    if (miss.length) { a._touched = true; const y = window.scrollY; render(); window.scrollTo(0, y); alert(`Noch offen: ${missingText(miss)}.`); return; }
    if (P) {
      if (!a._revealed) { a._revealed = true; save(); render(); const box = document.querySelector("#main section.card:last-of-type"); if (box) box.scrollIntoView(); return; }
      if (state.index < ids.length - 1) { state.index += 1; render(); window.scrollTo(0, 0); return; }
      state.practiceDone = true; state.mode = "rating"; state.index = 0; save(); render(); window.scrollTo(0, 0); return;
    }
    if (state.index < ids.length - 1) { state.index += 1; render(); window.scrollTo(0, 0); } else { progress(); alert("Alle Fälle vollständig. Bitte jetzt „Bewertung exportieren“ und die Datei an die Versuchsleitung schicken."); }
  });
  progress();
}

$("exportBtn").addEventListener("click", () => {
  stopClock(); if (state.rater) startClock(myCases()[state.index]);
  const ids = ratingCases(); const open = ids.map((c, i) => [i + 1, missingFor(c, "rating")]).filter(([, m]) => m.length);
  if (open.length && !confirm(`Noch unvollständig:\n${open.map(([n, m]) => `Fall ${n}: ${missingText(m)}`).join("\n")}\n\nTrotzdem als Zwischenstand exportieren?`)) return;
  const answers = {}; ids.forEach((c) => { if (state.answers[c]) { const { _touched, ...rest } = state.answers[c]; answers[c] = rest; } });
  const out = { schema_version: SCHEMA, panel_id: DATA.panel_id, rater_id: state.rater, exported_at: new Date().toISOString(), complete: !open.length, answers };
  const blob = new Blob([JSON.stringify(out, null, 2)], { type: "application/json" });
  const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
  link.download = `bewertung-${state.rater}-${DATA.panel_id.slice(6, 14)}${open.length ? "-zwischenstand" : ""}.json`;
  document.body.appendChild(link); link.click(); link.remove();
});
$("loadFile").addEventListener("change", async (e) => {
  const file = e.target.files[0]; if (!file) return;
  try {
    const data = JSON.parse(await file.text());
    if (data.schema_version !== SCHEMA || data.panel_id !== DATA.panel_id || !DATA.raters[data.rater_id]) throw new Error("Diese Datei gehört nicht zu diesem Bogen.");
    state.rater = data.rater_id; restore(); state.answers = data.answers || {}; state.index = 0;
    state.mode = "rating"; state.practiceDone = true; save();
    $("who").textContent = `Kürzel ${state.rater}`; render();
  } catch (err) { alert(err.message); } finally { e.target.value = ""; }
});
start();
</script>
</body>
</html>'''
