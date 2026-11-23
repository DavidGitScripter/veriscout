"""
store.py — dauerhafte Ablage der vorqualifizierten Startups.

Die Schicht bedient zwei Datenbanken hinter derselben Schnittstelle. Lokal
laeuft sie auf SQLite aus der Standardbibliothek, in Azure auf PostgreSQL.
Welche der beiden verwendet wird, entscheidet die Umgebungsvariable DATABASE_URL.
Ist sie nicht gesetzt oder verweist sie auf eine Datei, gilt SQLite.

    lokal      (nichts gesetzt)              -> runtime/vorqualifiziert.db
    Azure      DATABASE_URL=postgresql://... -> PostgreSQL

Der Aufrufer merkt davon nichts, server.py bleibt unveraendert. Die
Unterschiede zwischen den beiden Dialekten sind an einer Stelle gebuendelt,
naemlich in _dialekt, _ph und _einfuegen_mit_id. Das ist bewusst so, denn ein
Wechsel der Datenbank soll das Referenzmodell nicht beruehren.

Gespeichert werden ausschliesslich Angaben aus oeffentlichen Quellen sowie die
Bewertung des Systems und die menschliche Freigabe (Datenrestriktion RB1).
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone

# --------------------------------------------------------------------------
# Verbindung und Dialekt
# --------------------------------------------------------------------------
BASE = os.path.dirname(os.path.abspath(__file__))
RUNTIME_ROOT = os.environ.get(
    "SCOUTREF_RUNTIME_ROOT", os.path.join(BASE, "runtime"))
os.makedirs(RUNTIME_ROOT, mode=0o700, exist_ok=True)
try:
    os.chmod(RUNTIME_ROOT, 0o700)
except OSError:
    pass
DB_PATH = os.environ.get(
    "SCOUTREF_SQLITE_PATH", os.path.join(RUNTIME_ROOT, "vorqualifiziert.db"))
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()


def _dialekt() -> str:
    """postgres oder sqlite. Wird bei jedem Aufruf neu bestimmt, damit Tests
    die Umgebung zur Laufzeit umstellen koennen."""
    url = os.environ.get("DATABASE_URL", DATABASE_URL).strip()
    return "postgres" if url.startswith(("postgres://", "postgresql://")) else "sqlite"


def _ph(sql: str) -> str:
    """Fragezeichen-Platzhalter in das Format der jeweiligen Datenbank bringen.
    SQLite erwartet ?, PostgreSQL erwartet %s."""
    return sql.replace("?", "%s") if _dialekt() == "postgres" else sql


def _like() -> str:
    """PostgreSQL vergleicht mit LIKE gross- und kleinschreibungsempfindlich,
    SQLite nicht. ILIKE stellt das Verhalten gleich."""
    return "ILIKE" if _dialekt() == "postgres" else "LIKE"


def _conn():
    if _dialekt() == "postgres":
        import psycopg
        from psycopg.rows import dict_row
        url = os.environ.get("DATABASE_URL", DATABASE_URL).strip()
        return psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
    c = sqlite3.connect(DB_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    return c


# --------------------------------------------------------------------------
# Schema. Die beiden Fassungen unterscheiden sich nur in der Schluesselspalte
# und im Zeitstempeltyp, inhaltlich sind sie identisch.
# --------------------------------------------------------------------------
def _schema() -> list:
    pk = ("INTEGER PRIMARY KEY AUTOINCREMENT" if _dialekt() == "sqlite"
          else "BIGSERIAL PRIMARY KEY")
    return [
        f"""CREATE TABLE IF NOT EXISTS vorqualifiziert (
            id              {pk},
            name            TEXT NOT NULL,
            akteur_id       TEXT,
            akteur          TEXT,
            score           INTEGER,
            fit             TEXT,
            beschreibung    TEXT,
            sektor          TEXT,
            phase           TEXT,
            region          TEXT,
            gruendungsjahr  INTEGER,
            begruendung     TEXT,
            skepsis         TEXT,
            quellen         TEXT,
            status          TEXT DEFAULT 'vorqualifiziert',
            crm_status      TEXT,
            crm_org_id      TEXT,
            outreach_status TEXT DEFAULT 'offen',
            kontakt_email   TEXT,
            notiz           TEXT,
            freigegeben_am  TEXT,
            freigegeben_von TEXT,
            UNIQUE(name, akteur_id))""",
        "CREATE INDEX IF NOT EXISTS idx_vq_status ON vorqualifiziert(status)",
        "CREATE INDEX IF NOT EXISTS idx_vq_akteur ON vorqualifiziert(akteur_id)",
        f"""CREATE TABLE IF NOT EXISTS lauf (
            id            {pk},
            lauf_uid      TEXT UNIQUE,
            zeitpunkt     TEXT,
            suchauftrag   TEXT,
            akteur        TEXT,
            suchfeld      TEXT,
            wellen        INTEGER,
            guardrail     INTEGER,
            gefunden      INTEGER,
            empfohlen     INTEGER,
            verworfen     INTEGER,
            kosten_usd    DOUBLE PRECISION,
            modus         TEXT)""" if _dialekt() == "postgres" else
        f"""CREATE TABLE IF NOT EXISTS lauf (
            id            {pk},
            lauf_uid TEXT UNIQUE, zeitpunkt TEXT, suchauftrag TEXT, akteur TEXT, suchfeld TEXT,
            wellen INTEGER, guardrail INTEGER, gefunden INTEGER,
            empfohlen INTEGER, verworfen INTEGER, kosten_usd REAL, modus TEXT)""",
        "CREATE INDEX IF NOT EXISTS idx_lauf_zeit ON lauf(zeitpunkt)",
        f"""CREATE TABLE IF NOT EXISTS verworfen (
            id            {pk},
            lauf_id       BIGINT,
            zeitpunkt     TEXT,
            name          TEXT NOT NULL,
            akteur        TEXT,
            score         INTEGER,
            schwelle      INTEGER,
            grund         TEXT,
            skepsis       TEXT,
            beschreibung  TEXT,
            UNIQUE(name, akteur))""" if _dialekt() == "postgres" else
        f"""CREATE TABLE IF NOT EXISTS verworfen (
            id            {pk},
            lauf_id INTEGER, zeitpunkt TEXT, name TEXT NOT NULL, akteur TEXT,
            score INTEGER, schwelle INTEGER, grund TEXT, skepsis TEXT,
            beschreibung TEXT, UNIQUE(name, akteur))""",
        "CREATE INDEX IF NOT EXISTS idx_vw_name ON verworfen(name)",
    ]


STATUS = ["vorqualifiziert", "kontaktiert", "im Gespräch", "übergeben", "verworfen"]

_bereit = {"dialekt": None, "ziel": None}


def init(erzwingen: bool = False) -> None:
    """Legt die Tabellen an. Laeuft je Prozess und Ziel nur einmal, damit
    nicht jede Abfrage eine zusaetzliche Netzrunde kostet."""
    ziel = os.environ.get("DATABASE_URL", DATABASE_URL) or DB_PATH
    if not erzwingen and _bereit["ziel"] == ziel and _bereit["dialekt"] == _dialekt():
        return
    with _conn() as c:
        cur = c.cursor()
        for anweisung in _schema():
            cur.execute(anweisung)
        # Migration fuer bereits vorhandene Arbeitsdatenbanken. Die externe
        # Lauf-ID bleibt ueber UI, Auditlog und Pipedrive hinweg identisch;
        # die lokale numerische ID dient weiterhin nur als Fremdschluessel.
        if _dialekt() == "postgres":
            cur.execute("ALTER TABLE lauf ADD COLUMN IF NOT EXISTS lauf_uid TEXT")
        else:
            cur.execute("PRAGMA table_info(lauf)")
            spalten = {dict(row).get("name") for row in cur.fetchall()}
            if "lauf_uid" not in spalten:
                cur.execute("ALTER TABLE lauf ADD COLUMN lauf_uid TEXT")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_lauf_uid ON lauf(lauf_uid)")
        if _dialekt() == "sqlite":
            c.commit()
    _bereit["ziel"] = ziel
    _bereit["dialekt"] = _dialekt()


def _jetzt() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _als_dict(row) -> dict:
    """Zeilen beider Treiber in ein gewoehnliches Woerterbuch bringen."""
    if row is None:
        return {}
    d = dict(row)
    if d.get("quellen"):
        try:
            d["quellen"] = json.loads(d["quellen"])
        except Exception:
            d["quellen"] = []
    else:
        d["quellen"] = []
    return d


def _einfuegen_mit_id(cur, sql: str, werte: list) -> int:
    """Zeile einfuegen und den erzeugten Schluessel zurueckgeben. SQLite
    liefert ihn als lastrowid, PostgreSQL nur ueber RETURNING."""
    if _dialekt() == "postgres":
        cur.execute(_ph(sql + " RETURNING id"), werte)
        zeile = cur.fetchone()
        return zeile["id"] if zeile else 0
    cur.execute(sql, werte)
    return cur.lastrowid


# --------------------------------------------------------------------------
# Vorqualifizierte Startups
# --------------------------------------------------------------------------
FELDER_VQ = ("name", "akteur_id", "akteur", "score", "fit", "beschreibung",
             "sektor", "phase", "region", "gruendungsjahr", "begruendung",
             "skepsis", "quellen", "status", "crm_status", "crm_org_id",
             "outreach_status", "kontakt_email", "notiz", "freigegeben_am",
             "freigegeben_von")


def speichern(eintrag: dict) -> dict:
    """Legt einen vorqualifizierten Treffer an oder aktualisiert ihn. Die
    Kombination aus Startup und Akteur ist eindeutig, damit derselbe Kandidat
    nicht doppelt in der Liste erscheint."""
    init()
    d = {k: eintrag.get(k) for k in FELDER_VQ}
    if isinstance(d.get("quellen"), (list, dict)):
        d["quellen"] = json.dumps(d["quellen"], ensure_ascii=False)
    d["freigegeben_am"] = d["freigegeben_am"] or _jetzt()
    d["status"] = d["status"] or "vorqualifiziert"
    d["outreach_status"] = d["outreach_status"] or "offen"
    spalten = ", ".join(FELDER_VQ)
    platz = ", ".join("?" for _ in FELDER_VQ)
    update = ", ".join(f"{k}=excluded.{k}" for k in FELDER_VQ
                       if k not in ("name", "akteur_id"))
    with _conn() as c:
        cur = c.cursor()
        cur.execute(_ph(
            f"INSERT INTO vorqualifiziert ({spalten}) VALUES ({platz}) "
            f"ON CONFLICT(name, akteur_id) DO UPDATE SET {update}"),
            [d[k] for k in FELDER_VQ])
        cur.execute(_ph("SELECT * FROM vorqualifiziert WHERE name=? AND "
                        "COALESCE(akteur_id,'')=COALESCE(?,'')"),
                    (d["name"], d["akteur_id"]))
        row = cur.fetchone()
        if _dialekt() == "sqlite":
            c.commit()
    return _als_dict(row) if row else d


def liste(status: str = "", akteur_id: str = "", suche: str = "") -> list:
    init()
    sql = "SELECT * FROM vorqualifiziert WHERE 1=1"
    args = []
    if status:
        sql += " AND status = ?"; args.append(status)
    if akteur_id:
        sql += " AND akteur_id = ?"; args.append(akteur_id)
    if suche:
        L = _like()
        sql += f" AND (name {L} ? OR beschreibung {L} ? OR akteur {L} ?)"
        args += [f"%{suche}%"] * 3
    sql += " ORDER BY freigegeben_am DESC, id DESC"
    with _conn() as c:
        cur = c.cursor()
        cur.execute(_ph(sql), args)
        return [_als_dict(r) for r in cur.fetchall()]


def aktualisieren(eintrag_id: int, felder: dict) -> dict:
    """Aendert einzelne Felder, etwa den Bearbeitungsstand oder eine Notiz."""
    init()
    erlaubt = {"status", "notiz", "outreach_status", "kontakt_email",
               "crm_status", "crm_org_id"}
    setz = {k: v for k, v in felder.items() if k in erlaubt}
    if not setz:
        raise ValueError("Keine aenderbaren Felder uebergeben.")
    if "status" in setz and setz["status"] not in STATUS:
        raise ValueError(f"Unbekannter Status: {setz['status']}")
    zuw = ", ".join(f"{k}=?" for k in setz)
    with _conn() as c:
        cur = c.cursor()
        cur.execute(_ph(f"UPDATE vorqualifiziert SET {zuw} WHERE id=?"),
                    list(setz.values()) + [eintrag_id])
        cur.execute(_ph("SELECT * FROM vorqualifiziert WHERE id=?"), (eintrag_id,))
        row = cur.fetchone()
        if _dialekt() == "sqlite":
            c.commit()
    if not row:
        raise KeyError(f"Eintrag {eintrag_id} nicht gefunden.")
    return _als_dict(row)


def loeschen(eintrag_id: int) -> None:
    init()
    with _conn() as c:
        cur = c.cursor()
        cur.execute(_ph("DELETE FROM vorqualifiziert WHERE id=?"), (eintrag_id,))
        if _dialekt() == "sqlite":
            c.commit()


def _wert(zeile, spalte: str = None):
    """Erste Spalte einer Aggregatzeile holen, unabhaengig vom Treiber."""
    if zeile is None:
        return None
    if isinstance(zeile, dict):
        return zeile.get(spalte) if spalte else list(zeile.values())[0]
    return zeile[0]


def kennzahlen() -> dict:
    """Verdichtete Zahlen fuer die Kopfzeile der Ansicht."""
    init()
    with _conn() as c:
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM vorqualifiziert")
        gesamt = _wert(cur.fetchone(), "n") or 0
        cur.execute("SELECT status, COUNT(*) AS n FROM vorqualifiziert "
                    "GROUP BY status")
        je_status = {r["status"]: r["n"] for r in
                     (dict(x) for x in cur.fetchall())}
        cur.execute("SELECT COUNT(DISTINCT akteur_id) AS n FROM vorqualifiziert")
        akteure = _wert(cur.fetchone(), "n") or 0
        cur.execute("SELECT AVG(score) AS a FROM vorqualifiziert "
                    "WHERE score IS NOT NULL")
        schnitt = _wert(cur.fetchone(), "a")
    return {"gesamt": gesamt, "je_status": je_status, "akteure": akteure,
            "score_schnitt": round(float(schnitt), 1) if schnitt else None,
            "status_liste": STATUS}


# --------------------------------------------------------------------------
# Protokoll: Laeufe und verworfene Kandidaten
# --------------------------------------------------------------------------
FELDER_LAUF = ("lauf_uid", "zeitpunkt", "suchauftrag", "akteur", "suchfeld", "wellen",
               "guardrail", "gefunden", "empfohlen", "verworfen", "kosten_usd",
               "modus")
FELDER_VW = ("lauf_id", "zeitpunkt", "name", "akteur", "score", "schwelle",
             "grund", "skepsis", "beschreibung")


def lauf_speichern(daten: dict) -> int:
    """Haelt einen Scouting-Lauf mit Auftrag, Konfiguration und Ergebnis fest."""
    init()
    d = {k: daten.get(k) for k in FELDER_LAUF}
    d["zeitpunkt"] = d["zeitpunkt"] or _jetzt()
    sql = (f"INSERT INTO lauf ({', '.join(FELDER_LAUF)}) "
           f"VALUES ({', '.join('?' for _ in FELDER_LAUF)})")
    with _conn() as c:
        cur = c.cursor()
        neu = _einfuegen_mit_id(cur, _ph(sql) if _dialekt() == "sqlite" else sql,
                                [d[k] for k in FELDER_LAUF])
        if _dialekt() == "sqlite":
            c.commit()
        return neu


def verworfen_speichern(eintrag: dict) -> None:
    """Legt einen abgelehnten Kandidaten samt Begruendung ab."""
    init()
    d = {k: eintrag.get(k) for k in FELDER_VW}
    d["zeitpunkt"] = d["zeitpunkt"] or _jetzt()
    update = ", ".join(f"{k}=excluded.{k}" for k in FELDER_VW
                       if k not in ("name", "akteur"))
    with _conn() as c:
        cur = c.cursor()
        cur.execute(_ph(
            f"INSERT INTO verworfen ({', '.join(FELDER_VW)}) "
            f"VALUES ({', '.join('?' for _ in FELDER_VW)}) "
            f"ON CONFLICT(name, akteur) DO UPDATE SET {update}"),
            [d[k] for k in FELDER_VW])
        if _dialekt() == "sqlite":
            c.commit()


def laeufe(limit: int = 50) -> list:
    init()
    with _conn() as c:
        cur = c.cursor()
        cur.execute(_ph("SELECT * FROM lauf ORDER BY id DESC LIMIT ?"), (limit,))
        return [dict(r) for r in cur.fetchall()]


def verworfene(suche: str = "", limit: int = 200) -> list:
    init()
    sql = "SELECT * FROM verworfen WHERE 1=1"
    args = []
    if suche:
        L = _like()
        sql += f" AND (name {L} ? OR akteur {L} ? OR grund {L} ?)"
        args += [f"%{suche}%"] * 3
    sql += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    with _conn() as c:
        cur = c.cursor()
        cur.execute(_ph(sql), args)
        return [dict(r) for r in cur.fetchall()]


def protokoll_kennzahlen() -> dict:
    init()
    with _conn() as c:
        cur = c.cursor()
        cur.execute("SELECT COUNT(*) AS n FROM lauf")
        anz_l = _wert(cur.fetchone(), "n") or 0
        cur.execute("SELECT COUNT(*) AS n FROM verworfen")
        anz_v = _wert(cur.fetchone(), "n") or 0
        cur.execute("SELECT SUM(kosten_usd) AS s, SUM(gefunden) AS g, "
                    "SUM(empfohlen) AS e FROM lauf")
        z = dict(cur.fetchone() or {})
    kosten = float(z.get("s") or 0.0)
    gefunden = int(z.get("g") or 0)
    empfohlen = int(z.get("e") or 0)
    quote = round(100 * empfohlen / gefunden, 1) if gefunden else None
    return {"laeufe": anz_l, "verworfen": anz_v,
            "kosten_gesamt": round(kosten, 2),
            "gefunden": gefunden, "empfohlen": empfohlen,
            "empfehlungsquote": quote}


def zustand() -> dict:
    """Kurze Selbstauskunft fuer die Startdiagnose und den Health-Endpunkt."""
    return {"dialekt": _dialekt(),
            "ziel": ("PostgreSQL" if _dialekt() == "postgres"
                     else os.path.basename(DB_PATH))}
