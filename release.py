"""Menschliche Freigabe einer Empfehlung: CRM-Uebernahme und E-Mail-Entwurf.

Grundsaetze (RB4):
- Nur eine Empfehlung (decision_state == "empfehlung") kann freigegeben werden.
- Die Freigabe ist an eine unveraenderliche Entscheidungsversion gebunden: Die
  Oberflaeche zeigt den SHA-256-Fingerabdruck der Entscheidung, die Freigabe
  traegt ihn mit, und der Server berechnet ihn aus der gespeicherten Laufdatei
  neu. Weicht er ab, wird nichts geschrieben.
- Studienlaeufe bleiben unveraendert und sind fuer Freigaben gesperrt.
- Das System versendet keine E-Mail. Es bereitet einen Entwurf vor, den die
  freigebende Person in ihrem Mailprogramm prueft und selbst absendet.
- Die Empfaengeradresse stammt nur von der Website des Startups (bevorzugt
  Impressum oder Kontakt) und wird mit Fundstelle angezeigt. Ohne Fund bleibt
  das Feld leer; eine Adresse wird nie aus dem Namen geraten.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import urllib.parse

RELEASE_ACTIONS = {"crm", "email_draft", "outlook_draft"}
CONTACT_HINTS = ("impressum", "imprint", "kontakt", "contact", "legal", "about", "ueber-uns", "uber-uns")
FALLBACK_PATHS = ("/impressum", "/kontakt", "/contact", "/imprint")
PREFERRED_LOCAL = ("info", "kontakt", "contact", "hello", "hallo", "office", "mail", "team", "sales", "vertrieb")
AVOID_LOCAL = ("noreply", "no-reply", "datenschutz", "privacy", "dsb", "jobs", "karriere", "bewerbung", "abuse", "webmaster")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_OBFUSCATED = re.compile(
    r"([A-Za-z0-9._%+-]+)\s*(?:\[at\]|\(at\)|\{at\}| at |\[ät\]|\(ät\))\s*"
    r"([A-Za-z0-9-]+(?:\s*(?:\.|\[dot\]|\(dot\)|\[punkt\]|\(punkt\))\s*[A-Za-z0-9-]+)+)",
    re.IGNORECASE)


def _canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def find_decision(record: dict, pair_index: int, architecture: str,
                  candidate_id: str) -> tuple[dict, dict, dict]:
    """(Paar, Arm, Entscheidung) aus den internen Daten der Laufdatei."""
    pairs = record.get("internal_pairs") or (
        [record["internal_pair"]] if record.get("internal_pair") else [])
    if not 0 <= int(pair_index) < len(pairs):
        raise ValueError("Paar nicht gefunden.")
    pair = pairs[int(pair_index)]
    for arm in pair.get("arms") or []:
        if arm.get("architecture_internal") != architecture:
            continue
        for decision in arm.get("decisions") or []:
            if str((decision.get("candidate") or {}).get("candidate_id") or "") == candidate_id:
                return pair, arm, decision
    raise ValueError("Kandidat nicht gefunden.")


def decision_fingerprint(run_id: str, pair: dict, architecture: str, decision: dict) -> str:
    raw = _canonical({"run_id": run_id, "pair_id": pair.get("pair_id"),
                      "architecture": architecture, "decision": decision})
    return "decision-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _host(url: str) -> str:
    if url and "://" not in url:
        url = "https://" + url
    host = (urllib.parse.urlsplit(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def _site_domain(host: str) -> str:
    parts = host.split(".")
    if len(parts) >= 3 and parts[-2] in {"co", "com", "org", "ac"} and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def extract_emails(text: str, site_domain: str) -> list[str]:
    """E-Mail-Adressen der Website-Domain aus Seitentext (auch "name [at] domain")."""
    found = [m.group(0) for m in _EMAIL.finditer(text or "")]
    for match in _OBFUSCATED.finditer(text or ""):
        domain = re.sub(r"\s*(?:\[dot\]|\(dot\)|\[punkt\]|\(punkt\)|\.)\s*", ".",
                        match.group(2), flags=re.IGNORECASE)
        found.append(f"{match.group(1)}@{domain}")
    result = []
    for email in found:
        email = email.strip(".,;:()<>[]").lower()
        domain = email.rsplit("@", 1)[-1]
        if domain == site_domain or domain.endswith("." + site_domain):
            if email not in result:
                result.append(email)
    return result


def _rank(email: str) -> tuple:
    local = email.split("@", 1)[0]
    return (any(local.startswith(item) for item in AVOID_LOCAL),
            not any(local == item or local.startswith(item) for item in PREFERRED_LOCAL),
            len(email))


def find_contact_email(website: str, fetch, max_fetches: int = 6) -> dict:
    """Sucht eine belegte Kontaktadresse auf der Website des Startups.

    ``fetch(url)`` liefert das Ergebnis von ``EvidenceResolver._fetch``
    (oeffentliche Ziele, sichere Weiterleitungen). Rueckgabe mit Fundstelle;
    ohne Fund ist ``email`` leer.
    """
    host = _host(website)
    if not host:
        return {"email": "", "status": "keine_website", "checked": [], "alternatives": []}
    domain = _site_domain(host)
    base = f"https://{host}"
    queue, checked, hits = [base + "/"], [], []
    seen = set()
    while queue and len(checked) < max_fetches:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        result = fetch(url)
        checked.append({"url": url, "status": result.get("status")})
        if result.get("status") != "resolved":
            continue
        for email in extract_emails(result.get("text") or "", domain):
            hits.append({"email": email, "source_url": result.get("resolved_url") or url,
                         "contact_page": any(h in url.lower() for h in CONTACT_HINTS)})
        if len(checked) == 1:
            links = [link for link in result.get("links") or []
                     if any(h in link.lower() for h in CONTACT_HINTS)]
            queue.extend(links[:4] + [base + path for path in FALLBACK_PATHS])
    if not hits:
        return {"email": "", "status": "nicht_gefunden", "checked": checked, "alternatives": []}
    hits.sort(key=lambda item: (not item["contact_page"],) + _rank(item["email"]))
    best = hits[0]
    alternatives = sorted({item["email"] for item in hits} - {best["email"]})
    return {"email": best["email"], "source_url": best["source_url"], "status": "gefunden",
            "checked": checked, "alternatives": alternatives}


def _claims(decision: dict, fields: tuple) -> list[str]:
    matrix = (decision.get("candidate") or {}).get("evidence_matrix") or {}
    return [item.get("claim_text") for item in matrix.get("claim_manifest") or []
            if item.get("field") in fields and item.get("stance", "support") == "support"
            and item.get("claim_text")]


def email_draft(decision: dict, organization: str, sender: str = "",
                sender_org: str = "") -> dict:
    candidate = decision.get("candidate") or {}
    name = candidate.get("name") or "Ihr Unternehmen"
    process = (_claims(decision, ("target_process",)) or [""])[0]
    capability = (_claims(decision, ("startup_capability",)) or [""])[0]
    lines = [
        "Guten Tag,",
        "",
        f"bei einer Recherche nach Lösungen für {organization} sind wir auf {name} gestoßen.",
    ]
    if process:
        lines.append(f"Anknüpfungspunkt bei {organization}: {process}")
    if capability:
        lines.append(f"Ihr Angebot, wie wir es öffentlich gefunden haben: {capability}")
    lines += [
        "",
        "Ob daraus eine Zusammenarbeit entstehen kann, hängt von Mengen, Kosten und "
        "technischen Voraussetzungen ab, die wir gern in einem kurzen Gespräch klären würden.",
        "Hätten Sie in den nächsten Wochen Zeit für einen Termin von etwa 30 Minuten?",
        "",
        "Freundliche Grüße",
        sender or "[Name]",
    ]
    if sender_org:
        lines.append(sender_org)
    return {"subject": f"Anfrage: mögliche Zusammenarbeit von {name} mit {organization}",
            "body": "\n".join(lines)}


def mailto_link(to: str, subject: str, body: str) -> str:
    query = urllib.parse.urlencode({"subject": subject, "body": body},
                                   quote_via=urllib.parse.quote)
    return f"mailto:{urllib.parse.quote(to, safe='@.+-_')}?{query}"


def crm_transfer(adapter, decision: dict, organization: str, fingerprint: str,
                 run_id: str) -> dict:
    """Legt das Startup als Organisation mit Notiz an; Deal, wenn moeglich."""
    from crm_pipedrive import _stable_id, one_sentence
    candidate = decision.get("candidate") or {}
    name = candidate.get("name") or ""
    website = candidate.get("official_url") or candidate.get("website") or ""
    entity_id = _stable_id("org", _host(website) or name.lower())
    capability = (_claims(decision, ("startup_capability",)) or [""])[0]
    org = adapter.create_organization(
        name, bcc_dropbox="", external_id=entity_id,
        custom_fields={"Zielorganisation": organization, "Datenstand":
                       "dry-run" if adapter.dry_run else "live"},
        field_map={"Website": website, "Lösung": one_sentence(capability or name)})
    note = (f"VeriScout-Empfehlung für {organization}. Entscheidung {fingerprint}, "
            f"Lauf {run_id}. Belege: " + " | ".join(
                _claims(decision, ("target_process", "input_stream",
                                   "startup_capability", "output_application"))[:4]))
    result = {"modus": "dry-run" if adapter.dry_run else "live",
              "org_id": org.get("id"), "operation": org.get("operation"),
              "deal": None, "note": "angelegt"}
    try:
        adapter.add_note(note, org_id=org["id"])
    except Exception as error:  # Notiz ist nachrangig
        result["note"] = f"fehlgeschlagen: {type(error).__name__}"
    try:
        member = adapter.resolve_member_organization(organization)
        deal = adapter.create_deal(
            title=f"{name} → {organization}", org_id=org["id"],
            custom_fields={"ScoutRef Relation-ID": _stable_id("rel", entity_id, organization)},
            relation_id=_stable_id("rel", entity_id, organization),
            member_org_id=member["id"])
        result["deal"] = {"id": deal.get("id"), "operation": deal.get("operation")}
    except Exception as error:
        result["deal"] = {"skipped": str(error)[:200]}
    return result


def audit(path: str, entry: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    entry = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(), **entry}
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
