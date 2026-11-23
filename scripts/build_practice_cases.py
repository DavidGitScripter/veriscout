"""Erzeugt studie/uebungsfaelle.json aus gespeicherten Laeufen (Entwurf).

Kostenlos: keine Modellaufrufe. Mit ``--reevaluate`` (Standard) wird der Lauf
vorher mit dem aktuellen Regelkern neu bewertet (scripts/reevaluate_run.py,
nur HTTP-Abrufe der Quellen), damit Kette und Kennzeichen belegt/abgeleitet dem
Stand des Hauptlaufs entsprechen. Vorhandene Musterloesungen werden nie
ueberschrieben; neue Faelle bekommen eine leere Musterloesung.

Beispiel:
    SSL_CERT_FILE=/etc/ssl/cert.pem ~/.veriscout_venv/bin/python scripts/build_practice_cases.py \
        --case 26ae2494415b:sas2:"Optocycle GmbH" --case 26ae2494415b:mas:Neustark \
        --case 6dc708027ffc:sas2:"CAALA GmbH"
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import rating_panel  # noqa: E402

PRACTICE_EXCLUSIONS = [
    "reines Endkundenprodukt",
    "Startup nicht mehr aktiv (übernommen, insolvent, eingestellt)",
    "Forschungsprojekt ohne marktfähiges Angebot",
    "kein Bezug zu einem belegten Prozess des Unternehmens",
    "Sitz nicht in Deutschland, Österreich oder der Schweiz",
    "gegründet vor 2016 (älter als zehn Jahre)",
]


def practice_profile(case, *more_cases) -> dict:
    """Uebungsprofil, gekuerzt, je Unternehmen: Prozesszeilen, die in einem Uebungsfall
    dieses Unternehmens schon mit Quelle stehen."""
    processes, seen = [], set()
    for one in (case, *more_cases):
        processes.extend(_cited_processes(one, seen))
    return {"profile": "Übungsprofil, gekürzt. Es enthält nur Prozesse, die in den Übungsfällen zu diesem Unternehmen bereits mit Quelle stehen.",
            "processes": processes, "exclusion_criteria": list(PRACTICE_EXCLUSIONS),
            "practice_profile": True}


def _cited_processes(case: dict, seen: set) -> list[dict]:
    sources = {s.get("source_id"): s for s in case.get("sources") or []}
    processes = []
    for claim in case.get("claims") or []:
        source = sources.get(claim.get("source_id")) or {}
        if claim.get("field") != "target_process" or not source.get("url"):
            continue
        key = (claim.get("claim_text"), source.get("url"))
        if key in seen:
            continue
        seen.add(key)
        processes.append({"text": claim.get("claim_text"), "source_url": source.get("url")})
    return processes


DEFAULT_CASES = ["26ae2494415b:sas2:Optocycle GmbH", "26ae2494415b:mas:Neustark",
                 "6dc708027ffc:sas2:CAALA GmbH"]


def _record(run_id: str, reevaluate: bool) -> dict:
    source = ROOT / "artifacts" / "runs" / f"run-probe-{run_id}.json"
    if not source.is_file():
        source = ROOT / "artifacts" / "runs" / f"{run_id}.json"
    record = json.loads(source.read_text(encoding="utf-8"))
    if "internal_pair" not in record and record.get("internal_pairs"):
        record["internal_pair"] = record["internal_pairs"][0]
    if not reevaluate:
        return record
    from compare_architectures import annotation_package, assignment_manifest, operator_view
    from reevaluate_run import reevaluate as run_reevaluation
    pair = run_reevaluation(record)
    created = datetime.datetime.now(datetime.timezone.utc).isoformat()
    view = operator_view([pair], run_id=source.stem + "-uebung", created_at=created)
    view["run_set"] = "probe"
    return {"run_set": "probe", "operator_view": view,
            "blind_pairs": [{"blind_annotation": annotation_package(pair)}],
            "assignment_manifests": [assignment_manifest(pair)], "internal_pair": pair}


def apply_company_profiles(cases: list[dict]) -> None:
    """Ein Uebungsprofil je Unternehmen, fuer alle Faelle dieses Unternehmens gleich."""
    by_org: dict[str, list[dict]] = {}
    for item in cases:
        by_org.setdefault(item["task"]["organization_name"], []).append(item)
    for items in by_org.values():
        profile = practice_profile(*[i["case"] for i in items])
        for item in items:
            sheet = item["task"].get("case_sheet")
            if not sheet or sheet.get("practice_profile"):
                item["task"]["case_sheet"] = profile


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", default=[],
                        help="run_id:architektur:Startupname (mehrfach)")
    parser.add_argument("--out", default=str(rating_panel.DEFAULT_PRACTICE_PATH))
    parser.add_argument("--no-reevaluate", action="store_true")
    args = parser.parse_args()
    out = Path(args.out)
    existing = {}
    if out.is_file():
        for item in json.loads(out.read_text(encoding="utf-8")).get("cases") or []:
            origin = item.get("origin") or {}
            existing[(origin.get("run_id_source"), origin.get("architecture"),
                      str((item.get("case") or {}).get("name", "")).lower())] = item
    cases, records = [], {}
    for spec in args.case or DEFAULT_CASES:
        run_id, architecture, name = spec.split(":", 2)
        if run_id not in records:
            records[run_id] = _record(run_id, not args.no_reevaluate)
        built = rating_panel.practice_case_from_record(
            records[run_id], architecture=architecture, candidate_name=name)
        built["origin"]["run_id_source"] = run_id
        built["origin"]["reevaluated"] = not args.no_reevaluate
        old = existing.get((run_id, architecture, built["case"]["name"].lower()))
        built["solution"] = (old or {}).get("solution") or {
            q: {"answer": None, "reason": ""} for q in rating_panel.QUESTIONS}
        built["solution"].setdefault("f3_link", "")
        old_sheet = ((old or {}).get("task") or {}).get("case_sheet")
        # Von Hand gepflegte Profile bleiben; automatische werden je Unternehmen neu gebildet.
        built["task"]["case_sheet"] = old_sheet if old_sheet and not old_sheet.get("practice_profile") else None
        cases.append(built)
    apply_company_profiles(cases)
    document = {"schema_version": rating_panel.PRACTICE_SCHEMA, "status": "entwurf",
                "note": ("Uebungsfaelle fuer den Bewertungsbogen. Zaehlen nicht. Musterloesungen "
                         "gibt David frei; erst dann status auf 'freigegeben' setzen."),
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "cases": cases}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")
    for item in cases:
        print(json.dumps({"name": item["case"]["name"], "origin": item["origin"],
                          "chain_basis": item["case"]["chain_basis"],
                          "marked_claim_id": item["case"]["marked_claim_id"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
