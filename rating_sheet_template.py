"""HTML-Vorlage des Offline-Bewertungsbogens (eine Datei, ohne Netzaufrufe)."""

TEMPLATE = r'''<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:">
<title>VeriScout Bewertungsbogen</title>
<style>
:root{--bg:#f5f6f8;--surface:#fff;--surface-2:#f9fafb;--text:#111827;--muted:#5b6472;--border:#e3e6eb;--primary:#1f3a5f;--accent:#2563eb;--focus:#93b4f5;--ok:#15803d;--ok-bg:#e7f6ec;--warn:#a15c07;--warn-bg:#fdf3e1;--bad:#b42318;--bad-bg:#fdecea;--radius:10px;font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;font-size:15px;line-height:1.5;color:var(--text);background:var(--bg)}
@media (prefers-color-scheme:dark){:root{--bg:#0f141b;--surface:#161d27;--surface-2:#1b2430;--text:#e7ebf1;--muted:#a3adbb;--border:#2a3442;--primary:#9cc0ff;--accent:#8db4ff;--ok-bg:#12301e;--ok:#6fd39a;--warn-bg:#352611;--warn:#f0b866;--bad-bg:#3a1714;--bad:#ff9b8f}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text)}
header{background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:5}
.bar{max-width:1180px;margin:0 auto;padding:10px 16px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.bar strong{font-size:16px}.bar .grow{flex:1}
.progress{height:6px;background:var(--border);border-radius:99px;overflow:hidden;min-width:140px;flex:1;max-width:320px}
.progress i{display:block;height:100%;background:var(--ok);width:0}
main{max-width:1180px;margin:0 auto;padding:16px}
.layout{display:grid;grid-template-columns:260px 1fr;gap:16px}
@media (max-width:860px){.layout{grid-template-columns:1fr}nav.steps{max-height:180px}}
nav.steps{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:8px;max-height:calc(100vh - 110px);overflow:auto;position:sticky;top:70px}
nav.steps button{display:flex;gap:8px;width:100%;text-align:left;border:0;background:none;padding:6px 8px;border-radius:8px;cursor:pointer;color:var(--text);font:inherit;font-size:13.5px}
nav.steps button:hover{background:var(--surface-2)}nav.steps button[aria-current=true]{background:var(--surface-2);font-weight:600}
nav.steps .tick{width:18px;flex:none;color:var(--muted)}nav.steps .done .tick{color:var(--ok)}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:16px;margin-bottom:14px}
h1{font-size:22px;margin:0 0 6px}h2{font-size:17px;margin:0 0 10px}h3{font-size:15px;margin:0 0 8px}
p{margin:0 0 8px}.muted{color:var(--muted)}.small{font-size:13px}
.banner{padding:10px 12px;border-radius:8px;background:var(--warn-bg);color:var(--warn);margin-bottom:12px}
.case dl{display:grid;grid-template-columns:150px 1fr;gap:4px 12px;margin:8px 0}.case dt{color:var(--muted)}.case dd{margin:0}
@media (max-width:600px){.case dl{grid-template-columns:1fr}}
details{margin:6px 0}summary{cursor:pointer;color:var(--accent)}
.occ{border-left:4px solid var(--primary)}.entity{border-left:4px solid var(--ok)}
.claim{border-top:1px solid var(--border);padding:8px 0}.claim:first-child{border-top:0}
.claim .f{font-size:12.5px;color:var(--muted);text-transform:none}
q{display:block;margin:4px 0;padding:6px 10px;background:var(--surface-2);border-radius:6px;font-style:italic}
q::before,q::after{content:""}
.q{margin:12px 0;padding-top:10px;border-top:1px dashed var(--border)}
.q legend{font-weight:600;padding:0}.q fieldset{border:0;padding:0;margin:0}
.opts{display:flex;gap:8px;flex-wrap:wrap;margin:6px 0}
.opts label{display:flex;align-items:center;gap:6px;border:1px solid var(--border);border-radius:8px;padding:6px 10px;cursor:pointer;background:var(--surface-2)}
.opts input{margin:0}.opts label:has(input:checked){border-color:var(--primary);outline:2px solid var(--focus)}
textarea,input[type=text]{width:100%;font:inherit;color:inherit;background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:8px}
button.btn{font:inherit;border:1px solid var(--border);background:var(--surface);color:var(--text);border-radius:8px;padding:8px 14px;cursor:pointer}
button.primary{background:var(--primary);border-color:var(--primary);color:var(--surface)}
button.btn:disabled{opacity:.5;cursor:not-allowed}
:focus-visible{outline:3px solid var(--focus);outline-offset:2px}
.warn{padding:8px 10px;border-radius:8px;background:var(--warn-bg);color:var(--warn);margin-top:8px}
.nav{display:flex;gap:8px;justify-content:space-between;flex-wrap:wrap}
.status{font-size:13px;color:var(--muted)}
a{color:var(--accent);word-break:break-word}
ul.rules{padding-left:20px;margin:6px 0}
</style>
</head>
<body>
<script id="sheet-data" type="application/json">__SHEET_DATA__</script>
<header><div class="bar">
  <strong>VeriScout · Bewertungsbogen</strong>
  <span class="status" id="who"></span>
  <span class="grow"></span>
  <div class="progress" aria-hidden="true"><i id="bar"></i></div>
  <span class="status" id="count" aria-live="polite"></span>
  <button class="btn" id="importBtn" type="button">Zwischenstand laden</button>
  <button class="btn primary" id="exportBtn" type="button" disabled>Bewertung exportieren</button>
  <input type="file" id="importFile" accept=".json,application/json" hidden>
</div></header>
<main id="main"></main>
<script>
"use strict";
const S = JSON.parse(document.getElementById("sheet-data").textContent);
const FIELD = {identity:"Identität des Startups",startup_status:"Unternehmenstyp und Gründung",target_identity:"Mittelständisches Unternehmen",target_process:"Zielprozess",input_stream:"Input- oder Ressourcenstrom",startup_capability:"Fähigkeit des Startups",transformation:"Wirkmechanismus",output_application:"Nutzbares Ergebnis",relational_chain:"Zusammenhang der Kette",input_stream_mechanism:"Fachbeleg zum abgeleiteten Reststrom"};
const TASKS = Object.fromEntries(S.tasks.map((t) => [t.task_ref, t]));
let rater = "", order = [], idx = 0, shownAt = 0;
let store = { entity_ratings: {}, occurrence_ratings: {}, seconds: {} };

function esc(v){return String(v ?? "").replace(/[&<>"']/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function url(v){try{const u=new URL(String(v||""));return ["http:","https:"].includes(u.protocol)?u.href:"";}catch{return "";}}
function link(href, text){const u=url(href);return u?`<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(text||u)}</a>`:esc(text||"");}
function hash(s){let h=2166136261>>>0;for(const ch of s){h^=ch.codePointAt(0);h=Math.imul(h,16777619)>>>0;}return h;}
function rng(seed){return function(){seed|=0;seed=(seed+0x6D2B79F5)|0;let t=Math.imul(seed^(seed>>>15),1|seed);t=(t+Math.imul(t^(t>>>7),61|t))^t;return((t^(t>>>14))>>>0)/4294967296;};}
function shuffle(a,r){a=a.slice();for(let i=a.length-1;i>0;i--){const j=Math.floor(r()*(i+1));[a[i],a[j]]=[a[j],a[i]];}return a;}
function storageKey(){return `veriscout-${S.sheet_id}-${rater}`;}
function save(){try{localStorage.setItem(storageKey(),JSON.stringify(store));}catch{/* Speicher nicht verfügbar: Export nutzen */}}
function load(){try{const raw=localStorage.getItem(storageKey());if(raw){const v=JSON.parse(raw);if(v&&v.entity_ratings)store=v;}}catch{/* ohne Zwischenspeicher */}}

function buildOrder(){
  // Eigene, reproduzierbare Reihenfolge je bewertender Person.
  const r=rng(hash(S.sheet_id+"|"+rater)); const byTask={};
  S.entities.forEach((e)=>{(byTask[e.task_ref]=byTask[e.task_ref]||[]).push(e);});
  const out=[];
  for(const ref of shuffle(Object.keys(byTask).sort(),r))
    for(const e of shuffle(byTask[ref],r)) out.push({...e,occurrences:shuffle(e.occurrences,r)});
  return out;
}
function entityDone(e){
  const er=store.entity_ratings[e.unit_id]||{};
  return S.entity_metrics.every((m)=>er[m]) && e.occurrences.every((o)=>{const r=store.occurrence_ratings[o.unit_id]||{};return S.occurrence_metrics.every((m)=>r[m]);});
}
function updateProgress(){
  const done=order.filter(entityDone).length;
  document.getElementById("count").textContent=`${done} von ${order.length} Startups vollständig`;
  document.getElementById("bar").style.width=(order.length?100*done/order.length:0)+"%";
  document.getElementById("exportBtn").disabled=!rater;
  document.querySelectorAll("nav.steps button").forEach((b)=>{const e=order[Number(b.dataset.i)];b.classList.toggle("done",entityDone(e));b.querySelector(".tick").textContent=entityDone(e)?"✓":"○";});
}
function question(unit, metric, value){
  const c=S.codebook[metric]; const name=`${unit}|${metric}`;
  const opt=(v,l)=>`<label><input type="radio" name="${esc(name)}" value="${v}" ${value===v?"checked":""}> ${l}</label>`;
  return `<div class="q"><fieldset><legend>${esc(c.label)}</legend><p class="small">${esc(c.question)}</p>
    <div class="opts">${opt("yes","Ja")}${opt("no","Nein")}${opt("na","Nicht beurteilbar")}</div></fieldset>
    <details><summary>Wie entscheide ich?</summary><p class="small">${esc(c.help)}</p></details></div>`;
}
function caseBlock(t){
  const cs=t.case_sheet; const mode=t.search_mode==="pull"?"PULL (Unternehmen hat ein Suchfeld benannt)":"PUSH (ohne benannten Bedarf)";
  let sheet="<p class='muted small'>Für diesen Fall liegt kein Fallblatt vor. Nutze die Website des Unternehmens.</p>";
  if(cs){
    const procs=(cs.processes||[]).map((p)=>`<li>${esc(p.text)}${p.source_url?` · ${link(p.source_url,"Quelle")}`:""}</li>`).join("");
    const list=(a)=>(a||[]).length?`<ul>${a.map((x)=>`<li>${esc(x)}</li>`).join("")}</ul>`:"–";
    sheet=`<dl>
      ${cs.industry?`<dt>Branche</dt><dd>${esc(cs.industry)}</dd>`:""}
      ${cs.profile?`<dt>Kurzprofil</dt><dd>${esc(cs.profile)}</dd>`:""}
      <dt>Belegte Prozesse</dt><dd>${procs?`<ul>${procs}</ul>`:"–"}</dd>
      ${cs.need?`<dt>Bedarf oder Inputstrom</dt><dd>${esc(cs.need)}</dd>`:""}
      ${cs.search_area?`<dt>Suchfeld</dt><dd>${esc(cs.search_area)}</dd>`:""}
      <dt>Ausschlusskriterien</dt><dd>${list(cs.exclusion_criteria)}</dd>
      <dt>Unsicherheiten</dt><dd>${list(cs.uncertainties)}</dd></dl>`;
  }
  return `<section class="card case"><h2>Fall: ${esc(t.organization_name)}</h2>
    <dl><dt>Website</dt><dd>${t.website?link(/^https?:/.test(t.website)?t.website:"https://"+t.website,t.website):"–"}</dd>
    <dt>Auftragsart</dt><dd>${esc(mode)}${t.search_area?` · ${esc(t.search_area)}`:""}</dd>
    <dt>Suchauftrag</dt><dd>${esc(t.search_prompt)}</dd></dl>
    <details open><summary>Fallblatt (öffentliche Informationen zum Unternehmen)</summary>${sheet}</details></section>`;
}
const ORDER = ["identity","startup_status","startup_capability","target_identity","target_process","input_stream","input_stream_mechanism","transformation","output_application","relational_chain"];
function occurrenceBlock(o, i, n){
  const c=o.candidate||{}; const r=store.occurrence_ratings[o.unit_id]||{};
  const sources=new Map((c.sources||[]).map((s)=>[String(s.source_id),s]));
  const rank=(f)=>{const k=ORDER.indexOf(f);return k<0?99:k;};
  const list=(c.claims_for_annotation||[]).slice().sort((a,b)=>rank(a.field)-rank(b.field));
  const claims=list.map((cl)=>{const s=sources.get(String(cl.source_id))||{};
    return `<div class="claim"><div class="f">${esc(FIELD[cl.field]||cl.field||"Aussage")}</div>${esc(cl.claim_text)}
      ${cl.excerpt?`<q>${esc(cl.excerpt)}</q>`:""}<div class="small muted">${s.url?link(s.url,s.title||s.url):"keine Quelle angegeben"}</div></div>`;}).join("");
  return `<section class="card occ"><h3>Darstellung ${i+1} von ${n}</h3>
    <p class="small muted">Aussagen in der Reihenfolge der Kette: Startup, Unternehmen und Prozess, Input, Wirkung, Ergebnis.</p>
    ${claims||"<p class='muted'>Diese Darstellung enthält keine Aussagen.</p>"}
    ${S.occurrence_metrics.map((m)=>question(o.unit_id,m,r[m])).join("")}
    <label class="small" for="c-${esc(o.unit_id)}">Kurze Begründung (Pflicht bei „Nicht beurteilbar“)</label>
    <textarea id="c-${esc(o.unit_id)}" data-comment="${esc(o.unit_id)}" data-level="occurrence" rows="2" maxlength="2000">${esc(r.comment||"")}</textarea></section>`;
}
function warnings(e){
  const er=store.entity_ratings[e.unit_id]||{}; const out=[];
  if(er.qualified==="yes"&&er.valid_entity&&er.valid_entity!=="yes") out.push("„Prüfwürdig“ setzt ein gültiges, aktives Startup voraus. Bitte prüfen.");
  if(er.qualified==="yes"&&e.occurrences.every((o)=>(store.occurrence_ratings[o.unit_id]||{}).claim_support_complete==="no")) out.push("Keine Darstellung belegt die Kernaussagen. Ist „prüfwürdig“ trotzdem begründet?");
  const needs=[...S.entity_metrics.map((m)=>[er[m],er.comment])].some(([v,c])=>v==="na"&&!String(c||"").trim());
  if(needs) out.push("Bitte „Nicht beurteilbar“ kurz begründen.");
  return out.map((w)=>`<div class="warn">${esc(w)}</div>`).join("");
}
function render(){
  const main=document.getElementById("main");
  if(!rater){ renderStart(main); return; }
  if(idx>=order.length){ renderEnd(main); return; }
  const e=order[idx]; const t=TASKS[e.task_ref]||{}; const er=store.entity_ratings[e.unit_id]||{};
  shownAt=performance.now();
  main.innerHTML=`<div class="layout"><nav class="steps" aria-label="Startups">${order.map((x,i)=>`<button type="button" data-i="${i}" aria-current="${i===idx}"><span class="tick">○</span><span>${i+1}. ${esc(x.name)}<br><span class="muted small">${esc((TASKS[x.task_ref]||{}).organization_name)}</span></span></button>`).join("")}</nav>
    <div>${S.purpose==="schulung"?`<div class="banner">Schulung: Diese Bewertungen zählen nicht für die Studie.</div>`:""}
    ${caseBlock(t)}
    <section class="card"><h2>Startup ${idx+1} von ${order.length}: ${esc(e.name)}</h2><p class="small muted">${e.website?link(e.website,e.website):""} · ${e.occurrences.length} ${e.occurrences.length===1?"Darstellung":"Darstellungen"}. Lies zuerst alle Darstellungen, bewerte jede für sich und danach das Startup insgesamt.</p></section>
    ${e.occurrences.map((o,i)=>occurrenceBlock(o,i,e.occurrences.length)).join("")}
    <section class="card entity"><h3>Zum Startup insgesamt</h3>
      ${S.entity_metrics.map((m)=>question(e.unit_id,m,er[m])).join("")}
      <label class="small" for="ce">Kurze Begründung, z. B. greifendes Ausschlusskriterium</label>
      <textarea id="ce" data-comment="${esc(e.unit_id)}" data-level="entity" rows="2" maxlength="2000">${esc(er.comment||"")}</textarea>
      <div id="warns">${warnings(e)}</div></section>
    <div class="nav"><button class="btn" type="button" id="prev" ${idx===0?"disabled":""}>Zurück</button><button class="btn primary" type="button" id="next">${idx===order.length-1?"Abschließen":"Weiter"}</button></div></div></div>`;
  updateProgress(); window.scrollTo(0,0);
}
function leaveStep(){ if(rater&&idx<order.length){const e=order[idx];store.seconds[e.unit_id]=Math.round((store.seconds[e.unit_id]||0)+(performance.now()-shownAt)/1000);save();} }
function renderStart(main){
  const occ=S.entities.reduce((n,e)=>n+e.occurrences.length,0);
  main.innerHTML=`<section class="card"><h1>Bewertungsbogen</h1>
    ${S.purpose==="schulung"?`<div class="banner">Schulung: Diese Bewertungen zählen nicht für die Studie.</div>`:""}
    <p>${S.entities.length} Startups mit ${occ} Darstellungen aus ${S.tasks.length} Fällen. Rechne mit 5 bis 8 Minuten je Startup. Der Zwischenstand bleibt in diesem Browser erhalten, solange du die Datei nicht in einem privaten Fenster öffnest. Exportiere trotzdem nach jeder Sitzung.</p>
    <h2>Regeln</h2><ul class="rules">${S.rules.map((r)=>`<li>${esc(r)}</li>`).join("")}</ul>
    <h2>Kriterien</h2><ul class="rules">${Object.values(S.codebook).map((c)=>`<li><strong>${esc(c.label)}:</strong> ${esc(c.question)}</li>`).join("")}</ul>
    <label for="rater"><strong>Dein Kürzel</strong> (von der Versuchsleitung, z. B. R1)</label>
    <input type="text" id="rater" maxlength="20" autocomplete="off" style="max-width:200px;display:block;margin:6px 0 10px">
    <button class="btn primary" type="button" id="start">Bewertung beginnen</button>
    <p class="small muted" style="margin-top:10px">Bogen ${esc(S.sheet_id)}</p></section>`;
}
function renderEnd(main){
  const done=order.filter(entityDone).length;
  main.innerHTML=`<section class="card"><h1>${done===order.length?"Alle Startups bewertet":"Noch nicht vollständig"}</h1>
    <p>${done} von ${order.length} Startups sind vollständig bewertet.</p>
    <p>Exportiere jetzt die Bewertung und gib die Datei an die Versuchsleitung. Sprich bis zum Einigungsgespräch nicht über deine Urteile.</p>
    <div class="nav"><button class="btn" type="button" id="back">Zurück zur Liste</button><button class="btn primary" type="button" id="exportEnd">Bewertung exportieren</button></div></section>`;
  updateProgress();
}
function exportRatings(){
  leaveStep();
  const clean=(obj,metrics)=>Object.fromEntries(Object.entries(obj).map(([k,v])=>[k,{...Object.fromEntries(metrics.map((m)=>[m,v[m]||null])),comment:v.comment||""}]));
  const out={schema_version:"veriscout-ratings-v1",sheet_id:S.sheet_id,purpose:S.purpose,rater_id:rater,exported_at:new Date().toISOString(),
    complete:order.every(entityDone),entity_ratings:clean(store.entity_ratings,S.entity_metrics),
    occurrence_ratings:clean(store.occurrence_ratings,S.occurrence_metrics),seconds_per_startup:store.seconds};
  const blob=new Blob([JSON.stringify(out,null,1)],{type:"application/json"});
  const a=document.createElement("a"); a.href=URL.createObjectURL(blob);
  a.download=`bewertung-${rater}-${S.sheet_id.slice(6,16)}.json`; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(()=>URL.revokeObjectURL(a.href),1000);
  shownAt=performance.now();
}
document.addEventListener("change",(ev)=>{
  const el=ev.target;
  if(el.type==="radio"){const [unit,metric]=el.name.split("|");const level=S.entity_metrics.includes(metric)?"entity_ratings":"occurrence_ratings";
    (store[level][unit]=store[level][unit]||{})[metric]=el.value; save(); updateProgress();
    const w=document.getElementById("warns"); if(w&&order[idx]) w.innerHTML=warnings(order[idx]);}
  if(el.id==="importFile"&&el.files[0]){el.files[0].text().then((txt)=>{const v=JSON.parse(txt);
    if(v.sheet_id!==S.sheet_id) throw new Error("Die Datei gehört zu einem anderen Bewertungsbogen.");
    if(rater&&v.rater_id!==rater) throw new Error("Die Datei trägt ein anderes Kürzel.");
    rater=v.rater_id; order=buildOrder(); idx=0;
    store={entity_ratings:v.entity_ratings||{},occurrence_ratings:v.occurrence_ratings||{},seconds:v.seconds_per_startup||{}};
    for(const k of ["entity_ratings","occurrence_ratings"]) for(const r of Object.values(store[k])) for(const m of Object.keys(r)) if(r[m]===null) delete r[m];
    save(); document.getElementById("who").textContent=`Kürzel ${rater}`; render();}).catch((e)=>alert(e.message)).finally(()=>{el.value="";});}
});
document.addEventListener("input",(ev)=>{const el=ev.target; if(el.dataset&&el.dataset.comment){const level=el.dataset.level==="entity"?"entity_ratings":"occurrence_ratings";
  (store[level][el.dataset.comment]=store[level][el.dataset.comment]||{}).comment=el.value; save();
  const w=document.getElementById("warns"); if(w&&order[idx]) w.innerHTML=warnings(order[idx]);}});
document.addEventListener("click",(ev)=>{
  const b=ev.target.closest("button"); if(!b) return;
  if(b.id==="start"){const v=document.getElementById("rater").value.trim(); if(!/^[A-Za-z0-9_-]{1,20}$/.test(v)){alert("Bitte ein Kürzel mit Buchstaben oder Ziffern eingeben, z. B. R1.");return;}
    rater=v; load(); order=buildOrder(); idx=0; document.getElementById("who").textContent=`Kürzel ${rater}`; render();}
  else if(b.id==="next"){leaveStep(); idx+=1; render();}
  else if(b.id==="prev"){leaveStep(); idx=Math.max(0,idx-1); render();}
  else if(b.id==="back"){idx=0; render();}
  else if(b.dataset&&b.dataset.i!==undefined){leaveStep(); idx=Number(b.dataset.i); render();}
  else if(b.id==="exportBtn"||b.id==="exportEnd"){exportRatings();}
  else if(b.id==="importBtn"){document.getElementById("importFile").click();}
});
window.addEventListener("beforeunload",()=>{leaveStep();});
render();
</script>
</body>
</html>
'''
