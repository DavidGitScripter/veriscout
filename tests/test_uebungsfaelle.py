"""Uebungsfaelle im Bewertungsbogen: zaehlen nicht, Musterloesung erst nach Antwort,
Bogen funktioniert ohne Uebungsdatei."""
import json
import pathlib
import re

import pytest

import rating_panel as rp

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _practice_file(tmp_path, answer="yes"):
    data = {"schema_version": rp.PRACTICE_SCHEMA, "status": "entwurf", "cases": [{
        "task": {"organization_name": "Beispiel Bau GmbH", "website": "https://beispiel-bau.example",
                 "search_prompt": "Suche ein Startup.", "case_sheet": None},
        "case": {"name": "Uebung Startup GmbH", "website": "https://uebung.example",
                 "claims": [{"claim_id": "c1", "claim_text": "Sortiert Bauschutt.", "field": "startup_capability",
                             "source_id": "s1", "excerpt": "Wir sortieren Bauschutt mit Kameras."}],
                 "sources": [{"source_id": "s1", "url": "https://uebung.example/produkt", "title": "Produkt"}],
                 "marked_claim_id": "c1", "chain_basis": {"process": "belegt"}},
        "solution": {"f1": {"answer": answer, "reason": "Impressum mit HRB."},
                     "f2": {"answer": "yes", "reason": "Auszug steht dort."},
                     "f3": {"answer": "no", "reason": "Input nicht belegt."},
                     "f4": {"answer": "no", "reason": ""}, "f5": {"answer": "no", "reason": ""},
                     "f3_link": "input"}}]}
    path = tmp_path / "uebungsfaelle.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _records():
    runs = sorted((ROOT / "artifacts" / "runs").glob("run-*.json"))
    records = [json.loads(p.read_text(encoding="utf-8")) for p in runs]
    records = [r for r in records if (r.get("run_set") or (r.get("operator_view") or {}).get("run_set")) != "studie"]
    if not records:
        pytest.skip("keine gespeicherten Probeläufe")
    return records


def test_missing_practice_file_means_no_practice(tmp_path):
    assert rp.load_practice(tmp_path / "fehlt.json") == []
    key, sheet = rp.build_panel(_records(), seed="u", purpose="schulung", raters=3,
                               cases_per_rater=12, ratings_per_case=3,
                               practice_path=tmp_path / "fehlt.json")
    assert sheet["practice"] == [] and key["practice"]["case_ids"] == []
    html = rp.render_panel_html(sheet)
    assert "__PANEL_DATA__" not in html and '"practice": []' in html


def test_practice_is_not_counted(tmp_path):
    key, sheet = rp.build_panel(_records(), seed="u", purpose="schulung", raters=3,
                               cases_per_rater=12, ratings_per_case=3,
                               practice_path=_practice_file(tmp_path))
    ids = [p["practice_id"] for p in sheet["practice"]]
    assert ids == ["U1"] and key["practice"]["counted"] is False
    assigned = {cid for cases in key["assignment"].values() for cid in cases}
    assert not set(ids) & assigned and not set(ids) & set(sheet["cases"])
    assert not set(ids) & {c["case_id"] for c in key["cases"]}
    # Auch wenn eine Datei Uebungsantworten enthielte: Einlesen uebernimmt nur zugeteilte Faelle.
    rater = sorted(key["assignment"])[0]
    full = {"f1": "yes", "f2": "yes", "f3": "yes", "f4": "no", "f5": "no", "reasons": {"f3": "passt"}}
    answers = {cid: dict(full) for cid in key["assignment"][rater]}
    answers["U1"] = dict(full)
    _, clean, problems = rp.validate_rating(key, {"schema_version": rp.PANEL_RATINGS_SCHEMA,
                                                  "panel_id": key["panel_id"], "rater_id": rater,
                                                  "answers": answers})
    assert "U1" not in clean and not problems


def test_invalid_model_answer_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="ungültige Musterantwort"):
        rp.load_practice(_practice_file(tmp_path, answer="vielleicht"))


def test_template_shows_solution_only_after_complete_answer():
    from rating_panel_template import TEMPLATE
    # Musterloesung nur im Uebungsmodus und nur, wenn der Fall als beantwortet markiert ist.
    body = TEMPLATE.split("function solutionHtml(cid) {", 1)[1].split("\n}\n", 1)[0]
    assert 'if (!isPractice()) return "";' in body
    assert 'if (!a._revealed) return "";' in body
    # _revealed wird nur im Weiter-Knopf gesetzt, und zwar erst nach der Vollstaendigkeitspruefung.
    assert len(re.findall(r"_revealed = true", TEMPLATE)) == 1
    handler = TEMPLATE.split('$("nextBtn").addEventListener("click", () => {', 1)[1]
    assert handler.index("if (miss.length)") < handler.index("a._revealed = true")


def test_template_exports_only_rating_cases():
    from rating_panel_template import TEMPLATE
    export = TEMPLATE.split('$("exportBtn").addEventListener("click", () => {', 1)[1].split("});", 1)[0]
    assert "const ids = ratingCases();" in export and "state.practice" not in export
    # Uebungsantworten liegen in einem eigenen Speicher.
    assert 'storeKey() + "-uebung"' in TEMPLATE


def test_practice_file_is_approved_and_loads():
    path = rp.DEFAULT_PRACTICE_PATH
    if not path.is_file():
        pytest.skip("keine Übungsdatei")
    data = json.loads(path.read_text(encoding="utf-8"))
    # Musterloesungen von DS am 12.11.2026, 19:54 freigegeben.
    assert data["status"] == "freigegeben" and data["approved_by"] == "DS"
    assert data["approved_at"].startswith("2026-11-12T19:54")
    practice = rp.load_practice(path)
    assert len(practice) == 3
    assert all(p["case"]["name"] and p["task"]["organization_name"] for p in practice)
    assert all(p["status"] == "freigegeben" for p in practice)


def test_mixed_chain_row_names_both_links():
    view = {"matrix": [{"dimension": "startup_capability", "status": "supported", "basis": "direct"},
                       {"dimension": "transformation", "status": "supported", "basis": "derived"}]}
    assert rp._chain_basis(view)["capability"] == "Fähigkeit belegt · Wirkung abgeleitet"
    view["matrix"][1] = {"dimension": "transformation", "status": "partial", "basis": "direct"}
    assert rp._chain_basis(view)["capability"] == "Fähigkeit belegt · Wirkung ohne Beleg"
    view["matrix"][1] = {"dimension": "transformation", "status": "supported", "basis": "direct"}
    assert rp._chain_basis(view)["capability"] == "belegt"
    from rating_panel_template import TEMPLATE
    assert 'const basisClass = (b) => b === "belegt" ? "ok" : String(b).includes("ohne Beleg") ? "none" : "der";' in TEMPLATE


def test_imprint_from_resolver_reaches_sheet_and_f1_link():
    # Operator-Sicht traegt das Impressum; der Bogen nimmt es nur mit gefundenem Firmennamen.
    from compare_architectures import operator_view
    assert rp._impressum_link({"impressum": {"url": "https://x.example/impressum", "company_name_found": True,
                                             "register": "HRB 1"}}) == {"url": "https://x.example/impressum",
                                                                        "register": "HRB 1"}
    assert rp._impressum_link({"impressum": {"url": "https://x.example/impressum", "company_name_found": False}}) == {}
    assert rp._impressum_link({"impressum": {"url": "javascript:alert(1)", "company_name_found": True}}) == {}
    pair = {"pair_id": "p", "task": {}, "arms": [{"architecture_internal": "sas2", "decisions": [{
        "candidate": {"name": "A", "impressum": {"url": "https://a.example/impressum", "company_name_found": True,
                                                  "register": "HRB 2", "country": "DE"}}}]}]}
    view = operator_view([pair], run_id="r", created_at="t")
    found = json.dumps(view, ensure_ascii=False)
    assert "https://a.example/impressum" in found and "HRB 2" in found
    from rating_panel_template import TEMPLATE
    assert "const impressum = (c.impressum && safeUrl(c.impressum.url)) ? c.impressum" in TEMPLATE


def test_practice_profile_has_six_exclusions_and_only_cited_processes():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_practice_cases as b
    case = {"claims": [{"claim_id": "1", "field": "target_process", "claim_text": "Prozess A", "source_id": "s1"},
                       {"claim_id": "2", "field": "target_process", "claim_text": "Prozess ohne Quelle", "source_id": "x"},
                       {"claim_id": "3", "field": "startup_capability", "claim_text": "Kann B", "source_id": "s1"}],
            "sources": [{"source_id": "s1", "url": "https://u.example/a"}]}
    profile = b.practice_profile(case)
    assert profile["processes"] == [{"text": "Prozess A", "source_url": "https://u.example/a"}]
    assert len(profile["exclusion_criteria"]) == 6 and profile["profile"].startswith("Übungsprofil, gekürzt")
    assert "Sitz nicht in Deutschland, Österreich oder der Schweiz" in profile["exclusion_criteria"]


def test_practice_profile_is_per_company():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    import build_practice_cases as b
    with_process = {"claims": [{"field": "target_process", "claim_text": "Brechen und Sieben", "source_id": "s"}],
                    "sources": [{"source_id": "s", "url": "https://mw.example/rueckbau"}]}
    without = {"claims": [{"field": "target_process", "claim_text": "ohne Quelle", "source_id": "x"}], "sources": []}
    cases = [{"task": {"organization_name": "Max Wild GmbH", "case_sheet": None}, "case": without},
             {"task": {"organization_name": "Max Wild GmbH", "case_sheet": None}, "case": with_process},
             {"task": {"organization_name": "Andere AG", "case_sheet": {"profile": "von Hand"}}, "case": without}]
    b.apply_company_profiles(cases)
    assert cases[0]["task"]["case_sheet"] == cases[1]["task"]["case_sheet"]
    assert cases[0]["task"]["case_sheet"]["processes"] == [{"text": "Brechen und Sieben",
                                                           "source_url": "https://mw.example/rueckbau"}]
    assert cases[2]["task"]["case_sheet"] == {"profile": "von Hand"}  # Handprofil bleibt
