/* VeriScout · reine Anzeigehilfen ohne DOM-Zugriff (auch in Tests mit Node nutzbar). */
"use strict";

const LEGAL_FORMS = /\b(gmbh|mbh|ag|se|kg|ug|ohg|gbr|e\.?\s?v|s\.?r\.?o|ltd|limited|inc|llc|bv|b\.v|sa|sas|oy|ab|aps|co)\b/g;

function normalizeCompanyName(name) {
  return String(name || "").toLowerCase()
    .replace(/&/g, " ").replace(LEGAL_FORMS, " ")
    .replace(/[^a-z0-9äöüß]+/g, " ").replace(/\s+/g, " ").trim();
}

function normalizeDomain(url) {
  try {
    const host = new URL(String(url || "")).hostname.toLowerCase();
    return host.replace(/^www\./, "");
  } catch { return ""; }
}

/** Schluessel, unter denen ein Kandidat in beiden Armen als derselbe gilt. */
function candidateKeys(candidate) {
  const keys = [];
  const name = normalizeCompanyName(candidate && candidate.name);
  const domain = normalizeDomain(candidate && candidate.website);
  if (name) keys.push(`n:${name}`);
  if (domain) keys.push(`d:${domain}`);
  return keys;
}

/** Kandidaten-IDs, die in beiden Architekturen vorkommen (Name oder Domain gleich). */
function sharedCandidateIds(arms) {
  if (!Array.isArray(arms) || arms.length < 2) return new Set();
  const keySets = arms.map((arm) => new Set((arm.candidates || []).flatMap(candidateKeys)));
  const shared = new Set();
  arms.forEach((arm, index) => {
    const others = keySets.filter((_, i) => i !== index);
    (arm.candidates || []).forEach((c) => {
      if (candidateKeys(c).some((k) => others.every((set) => set.has(k)))) shared.add(c.candidate_id);
    });
  });
  return shared;
}

function encodeFragmentPart(text) {
  return encodeURIComponent(text).replace(/-/g, "%2D").replace(/,/g, "%2C").replace(/&/g, "%26");
}

/**
 * Link mit Text-Fragment (#:~:text=...), damit der Browser an der zitierten Stelle
 * oeffnet und sie markiert. Mit "..." gekuerzte Auszuege bestehen aus nicht
 * zusammenhaengenden Teilen; verwendet wird nur der erste Teil. Lange Teile werden
 * als textStart,textEnd aus den ersten und letzten fuenf Woertern angegeben.
 * Unbekannte Fundstellen ignoriert der Browser und oeffnet einfach die Seite.
 */
function fragmentUrl(url, excerpt) {
  let base;
  try {
    const parsed = new URL(String(url || ""));
    if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return "";
    base = parsed.href;
  } catch { return ""; }
  const first = String(excerpt || "").split(/\s*(?:\.\.\.|…)\s*/)
    .map((part) => part.replace(/\s+/g, " ").trim()).filter(Boolean)[0] || "";
  const clean = first.replace(/^["„“'»«]+|["„“'»«]+$/g, "").trim();
  if (clean.length < 8) return base;
  const words = clean.split(" ");
  const directive = words.length > 10
    ? `${encodeFragmentPart(words.slice(0, 5).join(" "))},${encodeFragmentPart(words.slice(-5).join(" "))}`
    : encodeFragmentPart(clean);
  const withoutDirective = base.replace(/:~:.*$/, "");
  return `${withoutDirective}${withoutDirective.includes("#") ? "" : "#"}:~:text=${directive}`;
}

/** Anteil gestuetzter Aussagen in Stufe 2; null, wenn es keine Aussagen gab. */
function supportedShare(mechanics) {
  const total = Number((mechanics || {}).claims_stage_1 || 0);
  if (!(total > 0)) return null;
  return Number((mechanics || {}).claims_supported_stage_2 || 0) / total;
}

const OPEN_STATUS = new Set(["missing", "partial", "contradicted"]);

/**
 * Begruendung "Warum keine Empfehlung?" nur aus gespeicherten Feldern:
 * Matrixstatus je Dimension, technische Fehlergruende. Nichts wird hinzuerfunden.
 */
function whyNoRecommendation(candidate, labels = {}, statusLabels = {}) {
  if (!candidate || candidate.decision_state === "empfehlung") return "";
  if (candidate.decision_state === "technischer_fehler") {
    return candidate.decision_state_reason
      ? `Technischer Fehler: ${candidate.decision_state_reason}` : "Technischer Fehler bei der Prüfung.";
  }
  const cells = (candidate.matrix || []).filter((cell) => cell.status !== "not_applicable");
  const open = cells.filter((cell) => OPEN_STATUS.has(cell.status));
  if (!open.length) return candidate.decision_state_reason || "";
  const parts = open.map((cell) =>
    `${labels[cell.dimension] || cell.dimension} (${statusLabels[cell.status] || cell.status})`);
  const contradicted = open.filter((cell) => cell.status === "contradicted").length;
  return `${open.length} von ${cells.length} Dimensionen nicht vollständig belegt: ${parts.join(", ")}.`
    + (contradicted ? ` Davon ${contradicted} durch eine Quelle widerlegt.` : "");
}

/** Satz fuer einen Arm ohne Empfehlung. */
function whyArmWithoutRecommendation(arm, stateLabels = {}) {
  if (!arm || (arm.decision_states || []).includes("empfehlung")) return "";
  const reasons = [...((arm.resources || {}).failure_reasons || [])];
  if (arm.primary_exclusion_reason) reasons.push(arm.primary_exclusion_reason);
  const candidates = arm.candidates || [];
  if (!candidates.length) {
    return reasons.length ? `Kein Startup vorgeschlagen. Grund: ${reasons.join(", ")}.`
      : "Kein Startup vorgeschlagen. Ein leeres Ergebnis ist zulässig.";
  }
  const counts = {};
  candidates.forEach((c) => { counts[c.decision_state] = (counts[c.decision_state] || 0) + 1; });
  const summary = Object.entries(counts)
    .map(([s, n]) => `${n} × ${stateLabels[s] || s}`).join(", ");
  return `Keine Empfehlung: ${candidates.length} Kandidat${candidates.length === 1 ? "" : "en"} geprüft (${summary}).`
    + (reasons.length ? ` Grund: ${reasons.join(", ")}.` : "");
}

/** Erster unerfuellter Punkt der Startpruefung als kurzer Hinweis. */
function firstStartBlocker(checks) {
  const failed = (checks || []).find((check) => !check.ok);
  if (!failed) return "";
  return failed.help ? `${failed.label}: ${failed.help}` : failed.label;
}

if (typeof module !== "undefined") {
  module.exports = { normalizeCompanyName, normalizeDomain, sharedCandidateIds, fragmentUrl,
    supportedShare, whyNoRecommendation, whyArmWithoutRecommendation, firstStartBlocker };
}
