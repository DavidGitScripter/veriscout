#!/usr/bin/env python3
"""
pipedrive_check.py — Live-Preflight fuer Pipedrive (lokal auf deinem Rechner).

Liest den Token aus der .env (automatisch) und prueft schrittweise:
  1. Token geladen?
  2. Auth ok? (GET /users/me) -> zeigt Account + Company-Domain
  3. Pipeline "ScoutRef Scouting" + Phase "Vorqualifiziert" vorhanden?
  4. optional (--write): legt EINEN echten Testeintrag an und liest ihn zurueck.

Der Token wird nie ausgegeben (nur maskiert) und nirgends gespeichert.

Aufruf (aus dem prototype-Ordner):
    python3 pipedrive_check.py            # nur Lese-/Auth-Test
    python3 pipedrive_check.py --write    # zusaetzlich ein Testeintrag (loeschbar)
"""
import sys
from core import Config
from crm_pipedrive import PipedriveAdapter, PIPELINE_NAME


def mask(t: str) -> str:
    if not t:
        return "(leer)"
    return f"{t[:4]}…{t[-4:]}" if len(t) > 8 else "…"


def main():
    print("== Pipedrive-Preflight ==")
    print("Token geladen:", "ja" if Config.PIPEDRIVE_API_TOKEN else "NEIN",
          "|", mask(Config.PIPEDRIVE_API_TOKEN))
    print("API-Base:", Config.PIPEDRIVE_API_BASE)
    if not Config.PIPEDRIVE_API_TOKEN:
        print("\nKein Token gefunden. So setzen:")
        print("  cp .env.example .env")
        print("  # in .env eintragen: PIPEDRIVE_API_TOKEN=... und PIPEDRIVE_LIVE=1")
        sys.exit(1)

    ad = PipedriveAdapter(dry_run=False)

    # 1) Auth
    print("\n[1/3] Auth-Test (GET /users/me) ...")
    try:
        me = ad._api("GET", "/users/me")
        print("  OK — eingeloggt als:", me.get("name"),
              "| Firma:", me.get("company_name"),
              "| Domain:", me.get("company_domain"))
    except Exception as e:
        print("  FEHLGESCHLAGEN:", e)
        print("  Haeufige Ursachen:")
        print("   - Token falsch/abgelaufen -> in Pipedrive neu generieren")
        print("   - Company-Domain noetig -> in .env setzen:")
        print("       PIPEDRIVE_API_BASE=https://DEINE-DOMAIN.pipedrive.com/api/v1")
        sys.exit(1)

    # 2) Pipeline / Phase
    print(f"\n[2/3] Pipeline '{PIPELINE_NAME}' + Phase '{Config.PIPEDRIVE_STAGE}' ...")
    st = ad._resolve_stage()
    print("  Pipeline gefunden:", "ja" if st.get("pipeline_id") else "NEIN")
    if st.get("stage_id"):
        print("  Phase gefunden:   ja")
    else:
        print("  Phase gefunden:   NEIN — Deal landet in der Default-Pipeline; "
              "die Organisation wird trotzdem korrekt angelegt.")
        print("  (Optional in Pipedrive anlegen: Pipeline 'ScoutRef Scouting' mit "
              "Phase 'Vorqualifiziert'.)")

    # 3) Optionaler Schreibtest
    if "--write" in sys.argv:
        print("\n[3/3] Schreibtest: lege Testorganisation an ...")
        org = ad.create_organization(
            "ScoutRef Testeintrag (loeschbar)", bcc_dropbox="")
        print("  angelegt: id", org["id"], "— erscheint jetzt unter 'Organisationen'")
        back = ad.list_organizations(limit=5)
        print("  zurueckgelesen (juengste):", [o["name"] for o in back])
        print("  Bitte diesen Testeintrag in Pipedrive wieder loeschen.")
    else:
        print("\n[3/3] uebersprungen. Fuer einen echten Schreibtest:")
        print("  python3 pipedrive_check.py --write")

    print("\nFertig.")


if __name__ == "__main__":
    main()
