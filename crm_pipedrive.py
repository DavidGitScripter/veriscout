"""
crm_pipedrive.py — CRM-Ueberfuehrung (Pipedrive), Dry-Run ODER Live-API.

Zwei Modi, identische Methoden-Signaturen:
- Dry-Run (Standard): in-memory, kein Netz, valide Payload-Strukturen. Reproduzierbar
  fuer Evaluation/Demo.
- Live: Pipedrive API v2 fuer Organisationen, Personen, Deals, Felder, Pipelines
  und Phasen. Nur die noch nicht als v2 angebotenen Notizen laufen ueber v1.
  Der API-Token wird ausschliesslich im ``x-api-token``-Header uebertragen und
  steht NIE im Code. Geschrieben wird erst NACH dem Human-in-the-Loop-Gate.

Echtzeit-Bestaetigung: list_organizations() liest die Organisationen live zurueck;
der Server pollt das und pusht es per SSE ans Dashboard (siehe server.py).
"""
from __future__ import annotations

import re
import json
import ssl
import hashlib
import urllib.request
import urllib.parse
from core import Config, Decision, Recommendation, Autonomy

# SSL-Kontext: nutzt certifi-Zertifikate, falls installiert (behebt das macOS-
# Problem CERTIFICATE_VERIFY_FAILED bei Python ohne Systemzertifikate).
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()

PIPELINE_NAME = Config.PIPEDRIVE_PIPELINE
STAGES = ["Vorqualifiziert", "Kontakt vorbereitet", "Kontakt aufgenommen",
          "Termin vereinbart", "Kooperationsprüfung", "Follow-up"]


class CRMAuthError(RuntimeError):
    """Anmeldung am CRM fehlgeschlagen (falscher oder abgelaufener Token).
    Wird gesondert behandelt, damit das Dashboard nicht abstuerzt, sondern in
    den Trockenlauf zurueckfaellt und den Zustand ehrlich anzeigt."""


class CRMRateLimitError(RuntimeError):
    """Pipedrive hat das Kontingent gedrosselt (HTTP 429).

    Pipedrive begrenzt zweifach (Stand der Dokumentation vom November 2025):

    - Stossschutz je Token, gleitendes Zwei-Sekunden-Fenster. Beim Tarif Lite
      sind es 20 Anfragen, bei der Suche 10. Dieser Fall loest sich von selbst.
    - Tagesbudget je Konto, gerechnet in Punkten statt in Anfragen. Die Formel
      lautet 30.000 Grundpunkte mal Tarif-Faktor mal Anzahl der Plaetze. Lite
      hat den Faktor 1. Eine Listenabfrage kostet 20 Punkte, ein einzelner
      Datensatz 2, eine Suche 40. Dieses Budget erneuert sich erst um
      Mitternacht in der Zeitzone des Servers.

    Die Unterscheidung ist wichtig, weil im zweiten Fall jedes Warten innerhalb
    der Sitzung vergeblich ist. Wer trotz 429 weiter anfragt, wird von Pipedrive
    zusaetzlich mit einer 403-Sperre belegt."""

    def __init__(self, nachricht: str, wartezeit: int = 0, tagesbudget: bool = False):
        super().__init__(nachricht)
        self.wartezeit = wartezeit
        self.tagesbudget = tagesbudget


# Richtwerte fuer die optimierten v2-Endpunkte. Einzelne v1-Restendpunkte wie
# Notizen koennen abweichende Kosten haben; verbindlich bleiben die API-Header.
PUNKTE = {"liste": 10, "einzeln": 1, "aendern": 5, "anlegen": 5, "suche": 20}


def _punktkosten(method: str, path: str) -> int:
    p = path.lower()
    # Trifft sowohl '/organizations/search' als auch '/itemSearch'.
    if "search" in p:
        return PUNKTE["suche"]
    if method in ("POST", "PUT", "PATCH"):
        return PUNKTE["anlegen"]
    # Ein Pfad ohne abschliessende ID liefert eine Liste.
    letztes = p.rstrip("/").rsplit("/", 1)[-1]
    return PUNKTE["einzeln"] if letztes.isdigit() else PUNKTE["liste"]


def _kontingent_lesen(headers) -> dict:
    """Liest die Kontingent-Angaben aus den Antwort-Headern von Pipedrive.

    Pipedrive fuehrt zwei Zaehler: 'x-ratelimit-*' fuer den Stossschutz je
    Zeitfenster und 'x-daily-requests-left' fuer das Tagesbudget des Kontos.
    Beides wird mitgefuehrt, damit die Oberflaeche den Verbrauch anzeigen kann,
    statt erst bei der Drosselung zu bemerken, dass nichts mehr geht."""
    def zahl(*namen):
        for n in namen:
            v = headers.get(n)
            if v is not None:
                try:
                    return int(str(v).strip())
                except ValueError:
                    return None
        return None

    return {"fenster_limit": zahl("x-ratelimit-limit"),
            "fenster_rest": zahl("x-ratelimit-remaining"),
            "fenster_reset": zahl("x-ratelimit-reset"),
            "tages_rest": zahl("x-daily-requests-left"),
            "tages_limit": zahl("x-daily-requests-limit"),
            "retry_after": zahl("retry-after", "Retry-After")}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "startup"


def _stable_id(kind: str, *parts: object) -> str:
    """Deterministische, nicht personenbezogene Integrations-ID.

    Die ID dient nur der technischen Idempotenz. Der Hash verhindert, dass lange
    URLs oder Namen als Suchschluessel in das CRM kopiert werden. Unterschiedliche
    Entitaetsarten haben getrennte Namensraeume.
    """
    norm = "\x1f".join(
        re.sub(r"\s+", " ", str(p or "").strip().lower()) for p in parts
    )
    digest = hashlib.sha256(norm.encode("utf-8")).hexdigest()[:24]
    return f"scoutref-{kind}-{digest}"


def one_sentence(text: str) -> str:
    """Kuerzt eine Beschreibung auf einen Satz (fuer das Feld 'Loesung')."""
    t = " ".join((text or "").split())
    if not t:
        return ""
    for sep in (". ", "! ", "? "):
        if sep in t:
            return t.split(sep)[0].strip().rstrip(".!?") + "."
    return t if t[-1] in ".!?" else t + "."


# Beschreibung -> Optionen des Set-Felds 'Technologie'.
# Kurze, mehrdeutige Begriffe (<=4 Zeichen) matchen nur als ganzes Wort
# (sonst traefe z.B. 'ki' in 'logistik'); lange Begriffe auch als Wortanfang.
TECH_RULES = [
    (("ki", "ai", "predictive", "analytics", "datenanalyse", "machine vision",
      "bildverarbeitung", "bilderkennung"), "KI & Advanced Analytics"),
    (("sensorik", "sensor", "messtechnik", "gasanalytik"), "Sensorik"),
    (("robotik", "roboter", "automatisierung", "agv", "amr", "cobot"),
     "Robotik & Automation"),
    (("embedded", "edge", "iot"), "Embedded Systems"),
    (("leistungselektronik", "frequenzumrichter"), "Leistungselektronik"),
    (("folie", "folien", "compound", "compounds", "chemisch", "keramik",
      "biobasiert", "materialien", "recycling"), "Materials & Chemistry"),
    (("wasserstoff", "speicher", "batterie", "geothermie", "erdwaerme",
      "waermepumpe", "hvo", "kraftstoff", "solar", "wind", "pv",
      "energiemanagement"), "Energiesysteme"),
    (("plattform", "marktplatz"), "Plattform & Ökosystem"),
    (("software", "saas"), "Software"),
    (("fertigung", "vorfertigung", "schweiss"), "Fertigungsverfahren"),
    (("bohr", "tiefbau", "baustellen"), "Bau-/Hardware-Systeme"),
]


def _heute() -> str:
    """Datum im Pipedrive-Format (ISO). Dokumentiert den Stand der Angabe."""
    from datetime import date
    return date.today().isoformat()


def _address(c) -> str:
    """Standort so konkret wie oeffentlich auffindbar. Bevorzugt der von der
    Discovery recherchierte Ort, sonst die grobe Einordnung."""
    ort = (getattr(c, "standort", "") or
           (getattr(c, "steckbrief", {}) or {}).get("standort", "")).strip()
    if ort:
        # Zusaetze in Klammern entfernen, Pipedrive erwartet eine Adresse
        ort = re.sub(r"\s*\(.*?\)", "", ort).strip(" ,;")
    teile = [t for t in (ort, getattr(c, "region", "")) if t and t != "—"]
    if not teile:
        teile = [t for t in (getattr(c, "location_class", ""),) if t and t != "—"]
    return ", ".join(dict.fromkeys(teile))


def _website(c) -> str:
    """Haupt-URL. Zuerst die recherchierte Angabe, sonst die erste Belegstelle,
    die weder LinkedIn noch ein Verzeichnis ist."""
    w = (getattr(c, "website", "") or "").strip()
    if w:
        return w if w.startswith("http") else "https://" + w
    for s in (getattr(c, "sources", None) or []):
        u = (getattr(s, "url", "") or "").strip()
        if u.startswith("http") and not any(x in u.lower() for x in
                ("linkedin.", "crunchbase.", "wikipedia.", "youtube.", "twitter.")):
            return u
    return ""


def _linkedin(c) -> str:
    li = (getattr(c, "linkedin", "") or "").strip()
    if li:
        return li if li.startswith("http") else "https://" + li
    for s in (getattr(c, "sources", None) or []):
        u = (getattr(s, "url", "") or "").strip()
        if "linkedin." in u.lower():
            return u
    return ""


# Sektoren der Akteursprofile und Stichworte -> Optionen des Felds
# 'Impact Cluster'. Die Optionen sind in Pipedrive fest hinterlegt, deshalb
# muss hier exakt einer dieser Werte herauskommen.
IMPACT_CLUSTER = [
    ("Circular Economy", ["circular economy", "kreislauf", "recycling", "rezyklat",
                          "abfall", "waste", "verpackung", "packaging"]),
    ("Energy", ["energy", "energie", "waerme", "wärme", "photovoltaik", "solar",
                "wasserstoff", "hydrogen", "speicher", "netz", "geothermie"]),
    ("Mobility", ["mobility", "mobilitaet", "mobilität", "transport", "logistik",
                  "logistics", "fahrzeug", "flotte", "laden", "charging",
                  "aerospace", "luftfahrt"]),
    ("Building & Construction", ["building", "construction", "bau", "gebaeude",
                                 "gebäude", "immobilien", "tga", "holzbau"]),
    ("Smart & Efficient Industry", ["industry", "manufacturing", "industrie",
                                    "fertigung", "produktion", "maschinen",
                                    "automatisierung", "qualitaetskontrolle",
                                    "qualitätskontrolle", "machine vision",
                                    "predictive", "instandhaltung"]),
    ("CO2 Capture & Technology", ["co2", "carbon", "climate tech", "emission",
                                  "abscheidung", "capture", "klimabilanz"]),
    ("Food & Agritech", ["food", "farming", "agri", "landwirtschaft",
                         "lebensmittel", "wasser", "water"]),
    ("Digital Business Infrastructure", ["software", "plattform", "platform",
                                         "saas", "daten", "data", "cloud",
                                         "schnittstelle", "digital"]),
]


def impact_cluster(c) -> str:
    """Genau eine der acht Optionen bestimmen.

    Bewertet wird, nicht der erste Treffer genommen: der Sektor aus der Discovery
    zaehlt dreifach, Stichworte aus der Beschreibung einfach. Sonst gewaenne bei
    'CO2-Abscheidung an Industrieanlagen' die Industrie ueber das Wort
    'Industrieanlagen', obwohl der Sektor eindeutig auf CO2 zeigt.
    'Digital Business Infrastructure' greift nur, wenn keine der sieben
    fachlichen Klassen passt, weil fast jedes Startup Software einsetzt."""
    from core import normalize
    sektor = " " + " ".join(normalize(x) for x in
                            (list(getattr(c, "sectors", []) or []))) + " "
    text = " " + normalize(getattr(c, "description", "")) + " "
    punkte = {}
    for label, kws in IMPACT_CLUSTER:
        p = sum(3 for k in kws if k in sektor) + sum(1 for k in kws if k in text)
        if p:
            punkte[label] = p
    fach = {k: v for k, v in punkte.items() if k != "Digital Business Infrastructure"}
    quelle = fach or punkte
    if not quelle:
        return ""
    reihenfolge = [l for l, _ in IMPACT_CLUSTER]
    return max(quelle, key=lambda l: (quelle[l], -reihenfolge.index(l)))


# Finanzierungsphase (Discovery) -> Optionslabel des Felds 'Entwicklungsphase'.
# Nicht gefundene Werte werden vom Resolver uebersprungen und protokolliert.
PHASE_LABELS = {
    "pre-seed": "Pre-Seed", "preseed": "Pre-Seed",
    "seed": "Seed",
    "series a": "Series A", "series-a": "Series A",
    "series b": "Series B", "series-b": "Series B",
    "bootstrapped": "Bootstrapped",
    "nicht angefangen": "Unbekannt", "unbekannt": "Unbekannt",
    "none": "Unbekannt", "keine": "Unbekannt",
}


def _phase_label(stage: str) -> str:
    """Immer eine gueltige Option liefern, ohne Unwissen als Reifegrad zu deuten."""
    s = (stage or "").strip()
    if not s:
        return "Unbekannt"
    return PHASE_LABELS.get(s.lower(), s)


def _evidence_label(candidate, relation: bool = False) -> str:
    status = (getattr(candidate, "verification_status", "") or "").lower()
    if status != "verified_startup":
        if status in {"not_a_startup", "non_existing"}:
            return "Widersprüchlich"
        return "Nicht ausreichend"
    if not relation:
        return "Verifiziert"
    process_supported = any(
        "process" in {str(x).strip().lower() for x in
                      (getattr(source, "supports", None) or [])}
        for source in (getattr(candidate, "sources", None) or []))
    if getattr(candidate, "problem_fit", None) is True and process_supported:
        return "Verifiziert"
    return "Teilweise verifiziert"


def derive_tech_options(description: str) -> list:
    """Leitet aus der Beschreibung die passenden 'Technologie'-Optionen ab."""
    from core import normalize
    norm = " " + " ".join(normalize(description).split()) + " "
    out = []
    for kws, label in TECH_RULES:
        hit = False
        for kw in kws:
            if len(kw) <= 4:
                if f" {kw} " in norm:
                    hit = True
                    break
            else:
                if f" {kw}" in norm:   # Wortanfang genuegt (faengt Komposita)
                    hit = True
                    break
        if hit and label not in out:
            out.append(label)
    return out[:4]


class PipedriveAdapter:
    def __init__(self, dry_run: bool = True):
        self.token = Config.PIPEDRIVE_API_TOKEN
        # Live nur, wenn ausdruecklich gewuenscht UND Token vorhanden:
        self.dry_run = dry_run or not self.token
        # Alte Konfigurationen enthielten oft bereits /api/v1. Intern wird nur
        # die Unternehmens-Domain gespeichert; die Version ist endpunktspezifisch.
        self.base = re.sub(
            r"(?:/api)?/v[12]/?$", "", Config.PIPEDRIVE_API_BASE.rstrip("/")
        )
        # Dry-Run-Speicher
        self.orgs, self.persons, self.deals = {}, {}, {}
        self.member_orgs = {}
        self._seq = {"org": 0, "person": 0, "deal": 0, "member": 100000}
        self._stage_cache = None
        self._field_cache = {}
        # Merkt einen Anmeldefehler, damit das Dashboard den Zustand anzeigen
        # kann, statt bei jedem Aufruf erneut zu scheitern.
        self.auth_error = ""
        # Zuletzt von Pipedrive gemeldeter Kontingentstand.
        self.kontingent = {}
        # Eigene Schaetzung des Tagesverbrauchs in Punkten. Pipedrive meldet den
        # Stand nur unvollstaendig zurueck (x-daily-requests-left gilt allein
        # fuer schreibende Zugriffe), deshalb wird mitgezaehlt.
        self.verbrauch = {"tag": "", "punkte": 0, "anfragen": 0}

    # ------------------------------------------------------------------ #
    # Live-API-Helfer
    # ------------------------------------------------------------------ #
    def _api(self, method: str, path: str, payload: dict = None,
             params: dict = None, _versuch: int = 0, version: str = None):
        """Ruft einen API-Endpunkt auf, ohne den Token in die URL zu schreiben.

        Organisationen, Personen, Deals, Felder, Pipelines und Phasen verwenden
        v2. Fuer die noch nicht als v2 verfuegbaren Notes und ``users/me`` wird
        bewusst v1 gewaehlt. ``version`` ist nur fuer solche Ausnahmen gedacht.
        """
        params = dict(params or {})
        if version is None:
            version = "v1" if path.startswith(
                ("/notes", "/noteFields", "/users", "/activityTypes")
            ) else "v2"
        if version not in ("v1", "v2"):
            raise ValueError(f"Unbekannte Pipedrive-API-Version: {version}")
        query = urllib.parse.urlencode(params, doseq=True)
        url = f"{self.base}/api/{version}{path}" + (f"?{query}" if query else "")
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = urllib.request.Request(
            url, data=data, method=method,
            headers={"Content-Type": "application/json", "x-api-token": self.token})
        self._buchen(method, path)
        try:
            with urllib.request.urlopen(req, timeout=20, context=_SSL_CTX) as r:
                self.kontingent = _kontingent_lesen(r.headers)
                body = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # Aussagekraeftige Meldung statt roher HTTP-Fehler. Der haeufigste
            # Fall ist ein Token, der nicht zur angesprochenen Instanz gehoert.
            if e.code == 401:
                raise CRMAuthError(
                    f"Pipedrive verweigert den Zugriff (401). Der Token passt "
                    f"nicht zu {self.base}. Pruefe, ob Token und Instanz aus "
                    f"demselben Pipedrive-Konto stammen.") from None
            if e.code == 403:
                raise CRMAuthError(
                    "Pipedrive verweigert den Zugriff (403). Der Token ist "
                    "gueltig, hat aber keine Berechtigung fuer diese Aktion.") from None
            if e.code == 429:
                self.kontingent = _kontingent_lesen(e.headers)
                drossel = self._drosselung(_versuch)
                if drossel is None:
                    # Stossschutz, es wurde bereits gewartet. Zweiter Anlauf.
                    return self._api(method, path, payload, params,
                                     _versuch + 1, version=version)
                raise drossel from None
            raise RuntimeError(f"Pipedrive antwortete mit HTTP {e.code}.") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"Pipedrive nicht erreichbar: {e.reason}") from None
        if not body.get("success", True):
            raise RuntimeError(f"Pipedrive API Fehler: {body.get('error', body)}")
        return body.get("data")

    def _buchen(self, method: str, path: str) -> None:
        """Schaetzt die Punktkosten einer Anfrage und schreibt sie dem Tag gut.
        Der Zaehler beginnt bei jedem Datumswechsel von vorn, so wie das Budget
        bei Pipedrive."""
        from datetime import date
        heute = date.today().isoformat()
        if self.verbrauch.get("tag") != heute:
            self.verbrauch = {"tag": heute, "punkte": 0, "anfragen": 0}
        self.verbrauch["punkte"] += _punktkosten(method, path)
        self.verbrauch["anfragen"] += 1

    def _drosselung(self, versuch: int):
        """Wertet eine 429-Antwort aus. Gibt None zurueck, wenn ein zweiter
        Anlauf sinnvoll ist (dann wurde bereits gewartet), sonst den Fehler.
        Beim aufgebrauchten Tagesbudget wird nicht gewartet, weil sich daran
        innerhalb der Sitzung nichts aendert."""
        k = self.kontingent or {}
        wartezeit = k.get("retry_after") or 0
        fenster_rest = k.get("fenster_rest")
        # Woran liegt die Drosselung? Der Stossschutz meldet ein erschoepftes
        # Zwei-Sekunden-Fenster. Ist dort noch Platz, kann es nur das Tagesbudget
        # sein. 'x-daily-requests-left' hilft nur bei schreibenden Zugriffen und
        # fehlt bei Abfragen, deshalb die Herleitung ueber das Fenster.
        tagesbudget = (k.get("tages_rest") == 0
                       or (fenster_rest is not None and fenster_rest > 0)
                       or wartezeit > 120)
        if not tagesbudget and versuch < 2:
            import time
            time.sleep(min(max(wartezeit, 2), 12))
            return None
        rest = k.get("tages_rest")
        if rest is not None:
            zusatz = (f" Pipedrive meldet noch {rest} Schreibzugriffe fuer heute.")
        elif wartezeit:
            zusatz = f" Pipedrive nennt {wartezeit} Sekunden Wartezeit."
        else:
            zusatz = ""
        v = self.verbrauch or {}
        if v.get("punkte"):
            zusatz += (f" Diese Sitzung hat rund {v['punkte']} Punkte in "
                       f"{v['anfragen']} Anfragen verbraucht.")
        return CRMRateLimitError(
            "Pipedrive drosselt die Zugriffe (429)." + zusatz +
            (" Das Tagesbudget des Kontos ist aufgebraucht. Es erneuert sich "
             "erst um Mitternacht in der Zeitzone des Pipedrive-Servers."
             if tagesbudget else
             " Das ist der Stossschutz im Zwei-Sekunden-Fenster. Kurz warten "
             "und erneut versuchen."),
            wartezeit=wartezeit, tagesbudget=tagesbudget)

    def _resolve_stage(self):
        """Loest Pipeline und Zielphase eindeutig per Namen auf.

        Ein fehlendes oder doppelt benanntes Ziel ist ein Konfigurationsfehler.
        Der Live-Pfad faellt dann nicht still auf eine Standard-Pipeline zurueck.
        """
        if self._stage_cache is not None:
            return self._stage_cache
        pipelines = self._api("GET", "/pipelines", params={"limit": 500}) or []
        treffer = [p for p in pipelines if p.get("name") == Config.PIPEDRIVE_PIPELINE]
        if len(treffer) != 1:
            raise RuntimeError(
                f"Pipedrive-Pipeline {Config.PIPEDRIVE_PIPELINE!r} "
                f"muss genau einmal existieren; gefunden: {len(treffer)}."
            )
        pid = treffer[0].get("id")
        stages = self._api("GET", "/stages",
                           params={"pipeline_id": pid, "limit": 500}) or []
        id2name = {s.get("id"): s.get("name") for s in stages}
        ziel = [s for s in stages if s.get("name") == Config.PIPEDRIVE_STAGE]
        if len(ziel) != 1:
            raise RuntimeError(
                f"Pipedrive-Phase {Config.PIPEDRIVE_STAGE!r} in Pipeline "
                f"{Config.PIPEDRIVE_PIPELINE!r} muss genau einmal existieren; "
                f"gefunden: {len(ziel)}."
            )
        sid = ziel[0].get("id")
        self._stage_cache = {"pipeline_id": pid, "stage_id": sid, "id2name": id2name}
        return self._stage_cache

    # ---- Custom Fields ueber Anzeigenamen aufloesen -------------------
    def _fields(self, entity: str):
        """Liefert Feldmetadaten fuer ``organization`` oder ``deal``.

        API v2 bezeichnet Anzeigename und Hash als ``field_name`` und
        ``field_code``. Die Rueckfallnamen halten lokale Test-Doubles und alte
        Metadatenexports lesbar, ohne im Live-Pfad auf v1 zurueckzufallen.
        """
        if entity not in ("organization", "deal"):
            raise ValueError(f"Nicht unterstuetzte Feldentitaet: {entity}")
        if entity in self._field_cache:
            return self._field_cache[entity]
        endpoint = "/organizationFields" if entity == "organization" else "/dealFields"
        m = {}
        for f in (self._api("GET", endpoint, params={"limit": 500}) or []):
            name = (f.get("field_name") or f.get("name") or "").strip()
            if not name:
                continue
            m[name.lower()] = {
                "key": f.get("field_code") or f.get("key"),
                "type": f.get("field_type"),
                "options": f.get("options") or [],
                "custom": f.get("is_custom_field", f.get("edit_flag", True)),
            }
        self._field_cache[entity] = m
        return m

    def _org_fields(self):
        """Kompatibilitaetsmethode fuer den bestehenden Selfcheck."""
        return self._fields("organization")

    def _deal_fields(self):
        return self._fields("deal")

    def _build_field_values(self, field_map: dict, report: dict = None,
                            entity: str = "organization",
                            required: tuple = ()) -> dict:
        """field_map {Anzeigename: Wert} -> {hashkey: API-Wert}.
        - enum: Wert per Options-Label -> Options-ID
        - set:  Wert (Label oder Liste von Labels) -> Liste von Options-IDs
        - Text/Zahl/Datum: Wert direkt
        Nicht auffindbare Felder und nicht passende Optionen werden uebersprungen
        und, falls 'report' uebergeben wird, dort protokolliert. Das ist wichtig
        fuer die Nachvollziehbarkeit: ein stillschweigend ausgelassenes Feld
        waere im Betrieb nicht bemerkbar."""
        fields = self._fields(entity)
        out = {}
        rep = report if report is not None else {}
        rep.setdefault("gesetzt", [])
        rep.setdefault("feld_unbekannt", [])
        rep.setdefault("option_unbekannt", [])
        rep.setdefault("leer", [])
        for name, val in (field_map or {}).items():
            if val in (None, "", []):
                rep["leer"].append(name)
                continue
            f = fields.get(name.strip().lower())
            if not f or not f.get("key") or not f.get("custom", True):
                rep["feld_unbekannt"].append(name)
                continue
            if f["options"]:
                label2id = {str(o.get("label", "")).strip().lower(): o.get("id")
                            for o in f["options"]}
                labels = val if isinstance(val, (list, tuple)) else [val]
                ids = [label2id[str(l).strip().lower()] for l in labels
                       if str(l).strip().lower() in label2id]
                if not ids:
                    rep["option_unbekannt"].append(f"{name}={val}")
                    continue
                fehlend = [str(l) for l in labels
                           if str(l).strip().lower() not in label2id]
                if fehlend:
                    rep["option_unbekannt"].append(f"{name}={', '.join(fehlend)}")
                if f["type"] != "set" and len(ids) > 1:
                    # Einwertiges Feld, mehrwertige Vorgabe: der Rest faellt weg.
                    # Das wird protokolliert, sonst bliebe der Verlust unbemerkt.
                    rep.setdefault("nur_erster_wert", []).append(
                        f"{name}: {labels[0]} gesetzt, verworfen {labels[1:]}")
                out[f["key"]] = ids if f["type"] == "set" else ids[0]
            else:
                out[f["key"]] = val
            rep["gesetzt"].append(name)
        fehlen = [name for name in required if name not in rep["gesetzt"]]
        if fehlen:
            details = []
            for name in fehlen:
                if name in rep["leer"]:
                    details.append(f"{name!r} hat keinen Wert")
                elif name in rep["feld_unbekannt"]:
                    details.append(f"Custom Field {name!r} fehlt")
                else:
                    details.append(f"{name!r} konnte nicht aufgeloest werden")
            raise RuntimeError("Pipedrive-Schema verhindert idempotentes Schreiben: "
                               + "; ".join(details))
        return out

    # ------------------------------------------------------------------ #
    # Schreiboperationen
    # ------------------------------------------------------------------ #
    def _id(self, kind: str) -> int:
        self._seq[kind] += 1
        return self._seq[kind]

    @staticmethod
    def _search_items(data) -> list:
        """Normalisiert die Antwort der v2-Suchendpunkte auf reine Datensaetze."""
        items = (data or {}).get("items", []) if isinstance(data, dict) else []
        return [entry.get("item", entry) for entry in items if isinstance(entry, dict)]

    def _exact_search(self, entity: str, term: str, fields: str,
                      filters: dict = None) -> dict:
        """Fuehrt eine exakte v2-Suche aus und verweigert mehrdeutige Treffer."""
        params = {"term": term, "fields": fields, "exact_match": "true", "limit": 2}
        params.update(filters or {})
        items = self._search_items(
            self._api("GET", f"/{entity}/search", params=params)
        )
        if len(items) > 1:
            raise RuntimeError(
                f"Pipedrive enthaelt mehrere exakte {entity}-Treffer fuer {term!r}; "
                "der Upsert wurde zum Schutz vor einer falschen Zuordnung abgebrochen."
            )
        return items[0] if items else None

    def _require_field_type(self, entity: str, name: str,
                            allowed: tuple) -> None:
        field = self._fields(entity).get(name.lower())
        if not field or not field.get("key") or not field.get("custom", True):
            raise RuntimeError(
                "Pipedrive-Schema verhindert idempotentes Schreiben: "
                f"Custom Field {name!r} fehlt."
            )
        if field.get("type") not in allowed:
            raise RuntimeError(
                f"Pipedrive-Custom-Field {name!r} hat Typ "
                f"{field.get('type')!r}; erwartet wird {', '.join(allowed)}."
            )

    def _find_organization_by_external_id(self, external_id: str):
        return self._exact_search("organizations", external_id, "custom_fields")

    def _find_deal_by_relation_id(self, relation_id: str):
        return self._exact_search("deals", relation_id, "custom_fields")

    def create_organization(self, name: str, bcc_dropbox: str,
                            custom_fields: dict = None,
                            field_map: dict = None,
                            address: str = "", external_id: str = "") -> dict:
        """Legt ein Startup idempotent an oder aktualisiert es."""
        external_id = external_id or _stable_id("org", name)
        fields = dict(field_map or {})
        fields["ScoutRef Entitäts-ID"] = external_id
        website = fields.pop("Website", "")
        linkedin = fields.pop("LinkedIn-Profile", "")
        employees = fields.pop("Anzahl der Mitarbeiter", "")
        if self.dry_run:
            org = next((o for o in self.orgs.values()
                        if o.get("external_id") == external_id), None)
            operation = "updated" if org else "created"
            if org is None:
                org = {"id": self._id("org"), "notes": []}
            org.update({"name": name, "address": address,
                   "external_id": external_id,
                   "website": website, "linkedin": linkedin,
                   "employee_count": employees,
                   "bcc_dropbox": bcc_dropbox or f"{_slug(name)}@scouting.pipedrivemail.com",
                   "custom_fields": custom_fields or {},
                   "felder": {k: v for k, v in fields.items()
                              if v not in (None, "", [])},
                   "datenstand": "synthetisch", "operation": operation})
            self.orgs[org["id"]] = org
            return dict(org)
        self._require_field_type(
            "organization", "ScoutRef Entitäts-ID",
            ("varchar", "varchar_auto", "text")
        )
        report = {}
        fv = self._build_field_values(
            fields, report=report, entity="organization",
            required=("ScoutRef Entitäts-ID",)
        )
        payload = {"name": name}
        if address:
            payload["address"] = {"value": address}
        if website:
            payload["website"] = website
        if linkedin:
            payload["linkedin"] = linkedin
        try:
            employee_count = int(employees)
        except (TypeError, ValueError):
            employee_count = 0
        if employee_count > 0:
            payload["employee_count"] = employee_count
        if fv:
            payload["custom_fields"] = fv
        existing = self._find_organization_by_external_id(external_id)
        if existing:
            data = self._api("PATCH", f"/organizations/{existing['id']}", payload=payload)
            operation = "updated"
        else:
            data = self._api("POST", "/organizations", payload=payload)
            operation = "created"
        return {"id": data["id"], "name": data.get("name", name),
                "add_time": data.get("add_time", ""), "bcc_dropbox": "",
                "address": address, "external_id": external_id,
                "custom_fields": custom_fields or {},
                "felder_gesetzt": report.get("gesetzt", []),
                "felder_uebersprungen": {
                    "unbekanntes_feld": report.get("feld_unbekannt", []),
                    "unbekannte_option": report.get("option_unbekannt", []),
                    "nur_erster_wert": report.get("nur_erster_wert", []),
                    "kein_wert": report.get("leer", [])},
                "datenstand": "live", "operation": operation}

    def resolve_member_organization(self, name: str, member_key: str = "") -> dict:
        """Loest eine bestehende Zielorganisation auf, ohne sie anzulegen."""
        name = (name or "").strip()
        if not name:
            raise RuntimeError("Die Zielorganisation fehlt; kein CRM-Schreiben erfolgt.")
        key = member_key or _stable_id("member", name)
        if self.dry_run:
            found = next((o for o in self.member_orgs.values()
                          if o.get("member_key") == key), None)
            if found:
                return dict(found)
            member = {"id": self._id("member"), "name": name,
                      "member_key": key, "datenstand": "synthetisch"}
            self.member_orgs[member["id"]] = member
            return dict(member)
        found = self.find_organization(name)
        if not found:
            raise RuntimeError(
                f"Zielorganisation {name!r} wurde in Pipedrive nicht exakt "
                "gefunden. Es wird nicht automatisch angelegt."
            )
        found["member_key"] = key
        return found

    def current_user(self) -> dict:
        """Liefert die authentifizierte Freigabeperson fuer das Auditfeld."""
        if self.dry_run:
            return {"id": 1, "name": Config.PIPEDRIVE_OWNER or "Dry-run user"}
        data = self._api("GET", "/users/me", version="v1") or {}
        if not data.get("id"):
            raise RuntimeError("Authentifizierte Pipedrive-Person nicht aufloesbar")
        return {"id": data["id"], "name": data.get("name", "")}

    def create_person(self, org_id: int, name: str, email: str = "",
                      titel: str = ""):
        """Legt nur eine belegte Kontaktperson an; leere Namen bleiben leer."""
        name = (name or "").strip()
        email = (email or "").strip()
        if not name:
            return None
        if self.dry_run:
            person = next((p for p in self.persons.values()
                           if p.get("org_id") == org_id and
                           ((email and p.get("email", "").lower() == email.lower()) or
                            (not email and p.get("name", "").lower() == name.lower()))), None)
            if person:
                person.update({"name": name, "email": email, "titel": titel,
                               "operation": "reused"})
                return dict(person)
            person = {"id": self._id("person"), "org_id": org_id, "name": name,
                      "email": email, "titel": titel, "operation": "created"}
            self.persons[person["id"]] = person
            return dict(person)
        found = self._exact_search(
            "persons", email or name, "email" if email else "name",
            {"organization_id": org_id}
        )
        if found:
            return {"id": found["id"], "org_id": org_id,
                    "name": found.get("name", name), "email": email,
                    "titel": titel, "operation": "reused"}
        payload = {"name": name, "org_id": org_id}
        if email:
            payload["emails"] = [{"value": email, "primary": True, "label": "work"}]
        data = self._api("POST", "/persons", payload=payload)
        return {"id": data["id"], "org_id": org_id, "name": name,
                "email": email, "titel": titel, "operation": "created"}

    def create_deal(self, title: str, org_id: int, person_id: int = None,
                    stage: str = None, value: int = 0,
                    custom_fields: dict = None, relation_id: str = "",
                    member_org_id: int = None) -> dict:
        """Upsert eines Deals ueber die stabile Startup--Zielorganisations-Relation."""
        stage = stage or Config.PIPEDRIVE_STAGE
        relation_id = relation_id or _stable_id("rel", org_id, member_org_id)
        fields = dict(custom_fields or {})
        fields["ScoutRef Relation-ID"] = relation_id
        if member_org_id is not None:
            fields["Zielorganisation"] = member_org_id
        if self.dry_run:
            deal = next((d for d in self.deals.values()
                         if d.get("relation_id") == relation_id), None)
            operation = "updated" if deal else "created"
            if deal is None:
                deal = {"id": self._id("deal"), "notes": []}
            deal.update({"title": title, "org_id": org_id,
                    "person_id": person_id, "member_org_id": member_org_id,
                    "relation_id": relation_id, "pipeline": PIPELINE_NAME,
                    "stage": stage, "value": value,
                    "custom_fields": fields, "operation": operation})
            self.deals[deal["id"]] = deal
            return dict(deal)
        if member_org_id is None:
            raise RuntimeError(
                "Die Zielorganisation fehlt; der Deal wird nicht geschrieben."
            )
        self._require_field_type(
            "deal", "ScoutRef Relation-ID", ("varchar", "varchar_auto", "text")
        )
        self._require_field_type("deal", "Zielorganisation", ("org",))
        report = {}
        fv = self._build_field_values(
            fields, report=report, entity="deal",
            required=("ScoutRef Relation-ID", "Zielorganisation")
        )
        st = self._resolve_stage()
        payload = {"title": title, "org_id": org_id,
                   "pipeline_id": st["pipeline_id"], "stage_id": st["stage_id"],
                   "custom_fields": fv}
        if person_id is not None:
            payload["person_id"] = person_id
        if value:
            payload["value"] = value
        existing = self._find_deal_by_relation_id(relation_id)
        if existing:
            data = self._api("PATCH", f"/deals/{existing['id']}", payload=payload)
            operation = "updated"
        else:
            data = self._api("POST", "/deals", payload=payload)
            operation = "created"
        return {"id": data["id"], "title": title, "org_id": org_id,
                "person_id": person_id, "member_org_id": member_org_id,
                "relation_id": relation_id, "stage": Config.PIPEDRIVE_STAGE,
                "cc_email": data.get("cc_email", data.get("smart_bcc_email", "")),
                "custom_fields": fields,
                "felder_gesetzt": report.get("gesetzt", []),
                "felder_uebersprungen": {
                    "unbekanntes_feld": report.get("feld_unbekannt", []),
                    "unbekannte_option": report.get("option_unbekannt", []),
                    "nur_erster_wert": report.get("nur_erster_wert", []),
                    "kein_wert": report.get("leer", [])},
                "operation": operation}

    def add_note(self, content: str, deal_id: int = None, org_id: int = None) -> None:
        if self.dry_run:
            if deal_id in self.deals:
                self.deals[deal_id]["notes"].append(content)
            return
        payload = {"content": content}
        if deal_id:
            payload["deal_id"] = deal_id
        if org_id:
            payload["org_id"] = org_id
        self._api("POST", "/notes", payload=payload)

    # ------------------------------------------------------------------ #
    # Leseoperationen (Echtzeit-Bestaetigung)
    # ------------------------------------------------------------------ #
    def find_organization(self, name: str):
        """Prueft, ob eine Organisation dieses Namens schon in Pipedrive existiert
        (Dubletten-Check fuer den Steckbrief). Live: /organizations/search."""
        if self.dry_run:
            low = (name or "").strip().lower()
            for o in self.orgs.values():
                if o["name"].strip().lower() == low:
                    return {"id": o["id"], "name": o["name"]}
            return None
        item = self._exact_search("organizations", name, "name")
        return ({"id": item.get("id"), "name": item.get("name", "")}
                if item else None)

    def list_organizations(self, limit: int = 25) -> list:
        """Organisationen live zuruecklesen (juengste zuerst). Dry-Run: aus Speicher."""
        if self.dry_run:
            return [{"id": o["id"], "name": o["name"],
                     "add_time": "", "datenstand": "synthetisch"}
                    for o in sorted(self.orgs.values(),
                                    key=lambda x: x["id"], reverse=True)][:limit]
        data = self._api("GET", "/organizations",
                         params={"limit": limit, "sort_by": "add_time",
                                 "sort_direction": "desc"}) or []
        return [{"id": o["id"], "name": o.get("name", ""),
                 "add_time": o.get("add_time", ""), "datenstand": "live"}
                for o in data]

    def board(self) -> dict:
        """Deal-Board nach Phasen."""
        if self.dry_run:
            b = {s: [] for s in STAGES}
            for d in self.deals.values():
                org = self.orgs.get(d["org_id"], {})
                member = self.member_orgs.get(d.get("member_org_id"), {})
                b.setdefault(d["stage"], []).append({
                    "deal_id": d["id"], "title": d["title"],
                    "org": org.get("name", ""), "bcc": org.get("bcc_dropbox", ""),
                    "sektor": d["custom_fields"].get("ScoutRef-Kategorie", ""),
                    "score": d["custom_fields"].get(
                        "Bewertung (Score)", d["custom_fields"].get("Match-Score", "")
                    ),
                    "akteur": member.get(
                        "name", d["custom_fields"].get("Zielorganisation", "")
                    ),
                })
            return b
        # live: Deals der Pipeline nach Phase gruppieren.
        # Ein Anmeldefehler darf das Dashboard nicht lahmlegen, deshalb wird er
        # abgefangen und als Zustand zurueckgemeldet.
        try:
            return self._board_live()
        except CRMAuthError as e:
            self.auth_error = str(e)
            b = {s: [] for s in STAGES}
            b["_fehler"] = str(e)
            return b
        except Exception as e:
            b = {s: [] for s in STAGES}
            b["_fehler"] = f"CRM nicht abrufbar: {e}"
            return b

    def _board_live(self) -> dict:
        st = self._resolve_stage()
        id2name = st.get("id2name", {})
        b = {name: [] for name in (id2name.values() or STAGES)}
        pid = st.get("pipeline_id")
        deals = self._api(
            "GET", "/deals",
            params={"pipeline_id": pid, "limit": 100,
                    "include_fields": "smart_bcc_email"}
        ) or []
        org_ids = sorted({d.get("org_id") for d in deals
                          if isinstance(d.get("org_id"), int)})
        org_names = {}
        if org_ids:
            org_rows = self._api(
                "GET", "/organizations",
                params={"ids": ",".join(str(x) for x in org_ids),
                        "limit": min(len(org_ids), 100)}
            ) or []
            org_names = {o.get("id"): o.get("name", "") for o in org_rows}
        for d in deals:
            if pid and d.get("pipeline_id") != pid:
                continue
            sname = id2name.get(d.get("stage_id"), "")
            if sname not in b:
                b[sname] = []
            org = d.get("org_id") or {}
            org_name = (org.get("name", "") if isinstance(org, dict)
                        else org_names.get(org, ""))
            b[sname].append({"deal_id": d.get("id"), "title": d.get("title", ""),
                             "org": org_name,
                             "bcc": (d.get("smart_bcc_email", "") or
                                     d.get("cc_email", "")),
                             "score": "", "akteur": ""})
        return b


class CRMWriteService:
    """
    Ueberfuehrt einen VORQUALIFIZIERTEN Treffer ins CRM. Wird in der Pipeline erst
    NACH dem Human-in-the-Loop-Gate aufgerufen. REJECT -> kein Eintrag. Bei
    Autonomie 'propose' wird nur geplant (kein Schreibzugriff).
    """
    def __init__(self, adapter: PipedriveAdapter, kb):
        self.adapter = adapter
        self.kb = kb

    def run(self, decision: Decision, autonomy: Autonomy = Autonomy.DRAFT) -> dict:
        if decision.recommendation != Recommendation.PILOT or decision.abstained:
            return {"status": "kein_eintrag",
                    "grund": "Nur ein nicht enthaltener Pilot-Vorschlag darf ins CRM."}

        c = decision.candidate
        if c.discovery_mode == "synthetic" and not self.adapter.dry_run:
            return {"status": "kein_eintrag",
                    "grund": "Synthetische Entwicklungsfaelle duerfen nie live ins CRM."}
        if c.discovery_mode in {"live", "curated"}:
            matrix = c.evidence_matrix or {}
            if (matrix.get("decision_state") != "eligible"
                    or matrix.get("blocking_dimensions")):
                return {"status": "kein_eintrag",
                        "grund": "Relationale Evidenzmatrix nicht vollstaendig."}

        actor_id = (getattr(c, "target_actor_id", "") or
                    decision.best_actor_id or
                    (decision.matches[0].actor_id if decision.matches else ""))
        best = next((m for m in decision.matches if m.actor_id == actor_id), None)
        actor = self.kb.get(actor_id) if actor_id else {}
        if not actor or not actor.get("name"):
            raise RuntimeError(
                "Eine positive CRM-Ueberfuehrung benoetigt ein eindeutiges "
                "Zielorganisation."
            )

        # Die offizielle Domain ist stabiler als der Anzeigename. Protokollpfade
        # oder einzelne Quelldokumente werden bewusst nicht zur CRM-Identitaet.
        identity_url = (getattr(c, "official_url", "") or _website(c) or "").strip()
        parsed = urllib.parse.urlsplit(identity_url)
        identity_basis = (parsed.hostname or identity_url or c.name).lower()
        if identity_basis.startswith("www."):
            identity_basis = identity_basis[4:]
        entity_id = _stable_id("org", identity_basis)
        relation_id = _stable_id("rel", entity_id, actor_id)
        run_id = (getattr(c, "run_id", "") or
                  getattr(c, "opportunity_id", "") or relation_id)

        summary_fields = {
            "ScoutRef-Kategorie": (c.sectors or ["—"])[0],
            "Finanzierungsphase": c.funding_stage or "—",
            "Standort-Klasse": c.location_class or c.region or "—",
            "Match-Score": decision.best_score,
            "Zielorganisation": actor["name"],
            "Datenstand": "live" if not self.adapter.dry_run else "synthetisch",
        }
        if autonomy == Autonomy.PROPOSE:
            return {"status": "geplant", "autonomie": autonomy.value,
                    "plan": {"organisation": c.name,
                             "zielorganisation": actor["name"],
                             "deal_phase": Config.PIPEDRIVE_STAGE,
                             "entity_id": entity_id,
                             "relation_id": relation_id,
                             "lauf_id": run_id}}

        # Die Zielorganisation wird vor dem ersten Schreibzugriff exakt aufgeloest. Im
        # Live-Modus prueft der Preflight zudem Schema, Pipeline und Phase, damit
        # eine Fehlkonfiguration nicht erst nach einer Teilanlage sichtbar wird.
        member = self.adapter.resolve_member_organization(actor["name"], actor_id)
        approving_user = self.adapter.current_user()
        if not self.adapter.dry_run:
            self.adapter._require_field_type(
                "organization", "ScoutRef Entitäts-ID",
                ("varchar", "varchar_auto", "text")
            )
            self.adapter._require_field_type(
                "deal", "ScoutRef Relation-ID", ("varchar", "varchar_auto", "text")
            )
            self.adapter._require_field_type(
                "deal", "Zielorganisation", ("org",)
            )
            self.adapter._resolve_stage()

        note = (f"ScoutRef-Vorqualifizierung | Zielorganisation: {actor['name']} | "
                f"Sektor: {summary_fields['ScoutRef-Kategorie']} | "
                f"Phase: {summary_fields['Finanzierungsphase']} | "
                f"Standort: {summary_fields['Standort-Klasse']} | "
                f"Score: {decision.best_score} | "
                f"Kritische Einordnung: "
                f"{best.critical_assessment if best else '—'}")
        bcc = actor.get("bcc_dropbox", "")

        # Nur Startup-Stammdaten gehoeren an die Organisation. Bewertung und
        # Zielorganisation sind relationsspezifisch und werden erst am Deal gespeichert.
        org_fields = {
            "ScoutRef Entitäts-ID": entity_id,
            "Lösung": one_sentence(c.description),
            "Lösung Stand": _heute(),
            "Gründungsjahr": c.founded or "",
            "Entwicklungsphase": _phase_label(c.funding_stage),
            "Website": _website(c),
            "LinkedIn-Profile": _linkedin(c),
            "Anzahl der Mitarbeiter": c.employees if c.employees else "",
            "Impact Cluster": impact_cluster(c),
            "Technologie": derive_tech_options(c.description),
            "Evidenzstatus Unternehmen": _evidence_label(c),
        }
        org = self.adapter.create_organization(
            c.name, bcc_dropbox=bcc, custom_fields=summary_fields,
            field_map=org_fields, address=_address(c), external_id=entity_id
        )

        # Kein Platzhalter: Eine Person wird nur bei oeffentlich belegtem Namen
        # angelegt. Der Deal selbst ist nicht von einer Person abhaengig.
        ceo = (getattr(c, "ceo", "") or "").strip()
        person = (self.adapter.create_person(
            org["id"], name=ceo, titel="CEO / Geschäftsführung"
        ) if ceo else None)

        deal_fields = {
            "ScoutRef Relation-ID": relation_id,
            "Zielorganisation": member["id"],
            "ScoutRef Lauf-ID": run_id,
            "Bewertung (Score)": decision.best_score,
            "Evidenzstatus Bewertung": _evidence_label(c, relation=True),
            "Kurzbegründung": " | ".join(filter(None, [
                best.rationale if best else "",
                ("Kritische Einordnung: " + best.critical_assessment)
                if best and best.critical_assessment else "",
                ("Offen: " + "; ".join(c.unresolved_requirements[:3]))
                if getattr(c, "unresolved_requirements", None) else "",
            ])),
            "Freigegeben von": approving_user["id"],
            "Freigabedatum": _heute(),
        }
        deal = self.adapter.create_deal(
            title=f"{c.name} → {actor['name']}", org_id=org["id"],
            person_id=person["id"] if person else None,
            stage=Config.PIPEDRIVE_STAGE, custom_fields=deal_fields,
            relation_id=relation_id, member_org_id=member["id"]
        )

        if not self.adapter.dry_run:
            bcc = deal.get("cc_email", "") or bcc
        note_errors = []
        # Notizen werden nur bei der Erstanlage geschrieben. Ein identischer
        # Wiederholungsaufruf erzeugt damit keine Notiz-Dubletten.
        if org.get("operation") == "created":
            try:
                self.adapter.add_note(note, org_id=org["id"])
            except Exception as exc:
                note_errors.append(f"Organisation: {exc}")
        if deal.get("operation") == "created":
            try:
                self.adapter.add_note(
                    f"Vorqualifiziert (Score {decision.best_score}).",
                    deal_id=deal["id"]
                )
            except Exception as exc:
                note_errors.append(f"Deal: {exc}")

        created = (org.get("operation") == "created" or
                   deal.get("operation") == "created")
        return {"status": "angelegt" if created else "aktualisiert",
                "autonomie": autonomy.value,
                "modus": "live" if not self.adapter.dry_run else "dry-run",
                "org_id": org["id"],
                "person_id": person.get("id") if person else None,
                "deal_id": deal.get("id"), "stage": Config.PIPEDRIVE_STAGE,
                "target_organization": member,
                "entity_id": entity_id, "relation_id": relation_id,
                "lauf_id": run_id, "bcc_dropbox": bcc,
                "freigegeben_von": approving_user,
                "custom_fields": summary_fields,
                "org_felder": org_fields, "deal_felder": deal_fields,
                "adresse": org.get("address", ""),
                "kontakt": ({"name": person.get("name", ""),
                             "titel": person.get("titel", "")}
                            if person else None),
                "operationen": {"organisation": org.get("operation"),
                                "person": person.get("operation") if person else "none",
                                "deal": deal.get("operation")},
                "felder_uebersprungen": {
                    "organisation": org.get("felder_uebersprungen", {}),
                    "deal": deal.get("felder_uebersprungen", {})},
                "notizfehler": note_errors}


# Rueckwaertskompatibilitaet fuer bestehende lokale Aufrufer. Die Komponente
# setzt eine bereits menschlich freigegebene Entscheidung deterministisch um
# und ist deshalb wissenschaftlich kein eigener Agent.
CRMAgent = CRMWriteService
