"""Expliziter, nur lokal erreichbarer Entwicklungsstart ohne automatische API-Läufe.

Der Start erzeugt nötigenfalls einen lokalen Bedienerschlüssel. Der API-Key
bleibt in der bestehenden .env. Studien- und CRM-Standardkonfigurationen werden
nicht überschrieben. Die Kostenbestätigung im Browser bleibt erforderlich.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import stat
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def development_environment(root: Path) -> dict[str, str]:
    return {
        "SCOUTREF_EVAL_LIVE_ENABLED": "1",
        "SCOUTREF_LOCAL_REVIEW_MODE": "1",
        "SCOUTREF_ENABLE_LEGACY_API": "0",
        "PIPEDRIVE_LIVE": "0",
        "SCOUTREF_EVAL_MAX_INPUT_TOKENS": "200000",
        "SCOUTREF_EVAL_MAX_OUTPUT_TOKENS": "24000",
        "SCOUTREF_EVAL_MAX_REASONING_TOKENS": "8000",
        "SCOUTREF_EVAL_MAX_TOOL_CALLS": "12",
        "SCOUTREF_EVAL_MAX_MODEL_CALLS": "2",
        "SCOUTREF_EVAL_MAX_RESOLVER_FETCHES": "24",
        "SCOUTREF_EVAL_MAX_CANDIDATES": "3",
        "SCOUTREF_EVAL_MAX_COST_USD": "0.75",
        "SCOUTREF_RUN_MAX_COST_USD": "1.50",
        "SCOUTREF_STUDY_BUDGET_USD": os.environ.get("SCOUTREF_LOCAL_BUDGET_USD", "10.00"),
        "SCOUTREF_STUDY_BUDGET_LEDGER": str(
            root / "runtime" / "local_review_budget.json"),
    }


def pipedrive_live_flag(requested: bool) -> str:
    """Live-CRM nur auf ausdruecklichen Wunsch; der Server verlangt zusaetzlich
    einen Token. Ein PIPEDRIVE_LIVE=1 aus der .env allein schaltet nichts ein."""
    return "1" if requested else "0"


def operator_secret(path: Path) -> str:
    """Bestehenden Schlüssel erhalten, nie ins Protokoll schreiben."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not path.exists() and not path.is_symlink():
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(secrets.token_urlsafe(32) + "\n")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
            raise RuntimeError("Bedienerschlüssel muss eine private Datei (0600) sein.")
        if info.st_uid != os.getuid():
            raise RuntimeError("Bedienerschlüssel gehört nicht dem angemeldeten Benutzer.")
        token = handle.read(256).strip()
    if len(token) < 32 or any(character.isspace() for character in token):
        raise RuntimeError("Ungültiger lokaler Bedienerschlüssel.")
    return token


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="Nur Konfiguration prüfen, keine Dateien oder API-Aufrufe erzeugen.")
    parser.add_argument("--model", default="gpt-6.1-sol",
                        help="gpt-6.1-sol (Standard), gpt-5.6-terra oder claude-sonnet-5-5")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--budget-usd", default="10.00",
                        help="Lokale Kostengrenze fuer alle Laeufe dieser Sitzung (Schaetzung)")
    parser.add_argument("--pipedrive-live", action="store_true",
                        help="Freigaben aus Probe- und Demolaeufen wirklich nach Pipedrive "
                             "schreiben (braucht PIPEDRIVE_API_TOKEN in .env). Studienlaeufe "
                             "bleiben immer gesperrt. Voreinstellung: Trockenlauf.")
    args = parser.parse_args()
    os.environ["SCOUTREF_LOCAL_BUDGET_USD"] = str(args.budget_usd)
    os.environ.update(development_environment(ROOT))
    os.environ["PIPEDRIVE_LIVE"] = pipedrive_live_flag(args.pipedrive_live)
    # Dieselbe Modellkennung fuer SAS-2, Scouting und Verifikation.
    os.environ["SCOUTREF_OPENAI_MODEL"] = args.model
    # Erst nach Setzen der expliziten Entwicklungsgrenzen importieren.
    from core import Config
    key_name = "ANTHROPIC_API_KEY" if args.model.startswith("claude-") else "OPENAI_API_KEY"
    if not os.environ.get(key_name):
        raise SystemExit(f"{key_name} fehlt. Bestehende .env prüfen.")
    from compare_architectures import ExperimentBudget
    ExperimentBudget().validate()
    if args.check:
        print("Entwicklungsprofil gültig. Kein API-Aufruf, kein Schlüssel erzeugt.")
        return
    key_path = ROOT / "runtime" / "local_review_operator_token.txt"
    os.environ["SCOUTREF_OPERATOR_TOKEN"] = operator_secret(key_path)
    token = os.environ["SCOUTREF_OPERATOR_TOKEN"]
    print(f"VeriScout mit Live-Läufen: http://127.0.0.1:{args.port}", flush=True)
    print(f"Modell (beide Arme): {args.model}", flush=True)
    print(f"Bedienerschlüssel (in das Feld 'Bedienerschlüssel' kopieren): {token}", flush=True)
    print(f"Lokale Kostengrenze dieser Sitzung: {args.budget_usd} USD, höchstens 1,50 USD je Paar.", flush=True)
    print("Das ist eine Schätzung, kein Abrechnungslimit beim Anbieter.", flush=True)
    print("Pipedrive: " + ("LIVE angefordert (nur mit Token, nie fuer Studienlaeufe)"
                           if args.pipedrive_live else "Trockenlauf"), flush=True)
    print("Vorschau und Start sind kostenlos. Erst 'Vergleich starten' löst API-Aufrufe aus.", flush=True)
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=args.port, reload=False)


if __name__ == "__main__":
    main()
