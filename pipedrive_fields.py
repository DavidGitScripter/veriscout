#!/usr/bin/env python3
"""
pipedrive_fields.py — liest die Pipedrive-Struktur aus (lokal).

Zeigt:
  - alle Organisations-Felder: Anzeigename, Key, Typ und (bei Dropdowns) die Optionen
  - alle Deal-Pipelines mit ihren Phasen (Name + ID)

So koennen wir Felder/Phase exakt ansteuern, ohne zu raten. In der Ausgabe stehen
nur Feld-Metadaten — keine Geheimnisse. Aufruf (mit gesetztem Token, aus prototype):
    python3 pipedrive_fields.py
"""
import sys
from core import Config
from crm_pipedrive import PipedriveAdapter


def main():
    if not Config.PIPEDRIVE_API_TOKEN:
        print("Kein Token gefunden. Erst per export/.env setzen.")
        sys.exit(1)
    ad = PipedriveAdapter(dry_run=False)

    print("== Organisations-Felder ==")
    try:
        fields = ad._api("GET", "/organizationFields") or []
    except Exception as e:
        print("Fehler:", e)
        sys.exit(1)
    for f in fields:
        name = f.get("name", "")
        key = f.get("key", "")
        ftype = f.get("field_type", "")
        line = f"  - {name!r:26} typ={ftype:10} key={key}"
        opts = f.get("options")
        if opts:
            line += " | Optionen: " + ", ".join(
                f'{o.get("label")}={o.get("id")}' for o in opts)
        print(line)

    print("\n== Deal-Pipelines & Phasen ==")
    try:
        pls = ad._api("GET", "/pipelines") or []
        for p in pls:
            print(f"  Pipeline {p.get('name')!r} (id {p.get('id')})")
            st = ad._api("GET", "/stages", params={"pipeline_id": p.get("id")}) or []
            for s in st:
                print(f"     - Phase {s.get('name')!r} (id {s.get('id')})")
    except Exception as e:
        print("Fehler:", e)


if __name__ == "__main__":
    main()
