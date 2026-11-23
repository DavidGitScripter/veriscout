"""Panelbewertung: Ziehung, Zuteilung (10 Personen, 3 je Fall) und Mehrheitsregel."""
import itertools
import random
from collections import Counter

import pytest
import rating_panel as rp


def _case(cid, task, recommended=False, arch="mas", model="m", state="enthaltung"):
    rep = {"occurrence_id": "O" + cid, "pair_id": "P" + task, "blind_arm_id": "A" + arch + task,
           "architecture": arch, "model": model, "run_id": "r", "candidate_id": "c" + cid,
           "decision_state": "empfehlung" if recommended else state, "recommended": recommended,
           "operating_status": "active", "marked_claim_id": "", "marked_excerpt_verified": True,
           "name": cid, "website": "", "claims": [], "sources": []}
    return {"case_id": cid, "task_id": task, "occurrences": [rep]}


def _pool(n_tasks=15, per_task=4):
    return [_case(f"C{t:02d}{i}", f"T{t:02d}", recommended=(i == 0 and t % 3 == 0),
                  arch="mas" if i % 2 else "sas2", model="sol" if t % 2 else "sonnet")
            for t in range(n_tasks) for i in range(per_task)]


def _assign(seed="x", n_tasks=10, per_task=4):
    # 10 Unternehmen mit je 4 Faellen: Bloecke gross genug fuer hoechstens 6 Unternehmen je Person.
    rng = random.Random(seed)
    sample, _ = rp.select_cases(_pool(n_tasks, per_task), 40, rng)
    return sample, rp.assign_cases(sample, raters=10, per_rater=12, overlap=3, max_orgs=6, rng=rng)


def test_assignment_meets_protocol():
    sample, assignment = _assign()
    assert len(sample) == 40
    counts = Counter(cid for ids in assignment.values() for cid in ids)
    assert set(counts) == {c["case_id"] for c in sample} and set(counts.values()) == {3}
    task_of = {c["case_id"]: c["task_id"] for c in sample}
    for ids in assignment.values():
        assert len(ids) == 12
        assert len({task_of[c] for c in ids}) <= 6
    for a, b in itertools.combinations(assignment.values(), 2):
        assert set(a) != set(b)
    # Bloecke: alle Faelle eines Unternehmens gehen an dieselben drei Personen.
    holders = {}
    for rater, ids in assignment.items():
        for cid in ids:
            holders.setdefault(task_of[cid], set()).add(rater)
    assert all(len(h) == 3 for h in holders.values())


def test_assignment_is_deterministic_for_seed():
    assert _assign("seed-a")[1] == _assign("seed-a")[1]
    assert _assign("seed-a")[1] != _assign("seed-b")[1]


def test_all_recommended_cases_are_drawn_first():
    rng = random.Random(1)
    pool = _pool()
    sample, weights = rp.select_cases(pool, 40, rng)
    recommended = {c["case_id"] for c in pool if any(o["recommended"] for o in c["occurrences"])}
    assert recommended <= {c["case_id"] for c in sample}
    assert weights["empfohlen"] and all(w["weight"] == 1 for w in weights["empfohlen"])


def test_rater_verdict_and_majority_rule():
    yes = {"f1": "yes", "f2": "yes", "f3": "yes", "f4": "no"}
    assert rp.rater_verdict(yes) == rp.HIT
    assert rp.rater_verdict({**yes, "f2": "no"}) == rp.NO_HIT
    assert rp.rater_verdict({**yes, "f4": "yes"}) == rp.NO_HIT
    assert rp.rater_verdict({**yes, "f1": "na"}) == rp.NOT_ASSESSABLE
    assert rp.rater_verdict({**yes, "f1": "na", "f3": "no"}) == rp.NO_HIT
    H, N, X = rp.HIT, rp.NO_HIT, rp.NOT_ASSESSABLE
    assert rp.combine([H, H, N]) == H
    assert rp.combine([H, N, X]) == rp.DISPUTED
    assert rp.combine([H, X, X]) == X
    assert rp.combine([N, N]) == N  # Ausfall einer Person: zwei Urteile genuegen


def _full_answer(hit=True):
    return {"f1": "yes", "f2": "yes" if hit else "no", "f3": "yes", "f4": "no", "f5": "no",
            "reasons": {"f2": "Auszug fehlt.", "f3": "Kette passt."}}


def test_evaluate_panel_end_to_end():
    sample, assignment = _assign()
    key = {"schema_version": rp.PANEL_KEY_SCHEMA, "panel_id": "panel-test", "seed": "x",
           "parameters": {}, "assignment": assignment,
           "cases": [{"case_id": c["case_id"], "task_id": c["task_id"],
                      "recommended": any(o["recommended"] for o in c["occurrences"]),
                      "representation": c["occurrences"][0],
                      "occurrences": c["occurrences"]} for c in sample],
           "arms": sorted({(o["pair_id"], o["blind_arm_id"], o["architecture"], o["model"])
                           for c in sample for o in c["occurrences"]}),
           "unsampled_recommended_cases": []}
    ratings = [{"schema_version": rp.PANEL_RATINGS_SCHEMA, "panel_id": "panel-test", "rater_id": r,
                "answers": {cid: _full_answer(hit=(cid.endswith("0"))) for cid in ids}}
               for r, ids in assignment.items()]
    result = rp.evaluate_panel(key, ratings, bootstrap_draws=50)
    assert all(v["answered"] == 12 and not v["problems"] for v in result["completeness"].values())
    assert result["unanimous_share"] == 1
    recommended_arms = [a for a in result["arms"] if a["recommended_cases"]]
    assert recommended_arms and all(a["hit_primary"] == 1 for a in recommended_arms)
    assert all(a["hit_primary"] == 0 for a in result["arms"] if not a["recommended_cases"])
    assert result["questions"]["f1"]["not_assessable_share"] == 0


def test_rating_validation_requires_reasons_and_link():
    key = {"panel_id": "p", "assignment": {"P01": ["C1"]}}
    bad = {"schema_version": rp.PANEL_RATINGS_SCHEMA, "panel_id": "p", "rater_id": "P01",
           "answers": {"C1": {"f1": "no", "f2": "yes", "f3": "no", "f4": "no", "f5": "no", "reasons": {}}}}
    _, _, problems = rp.validate_rating(key, bad)
    assert rp.needs_reason("f4", "no") is False and rp.needs_reason("f4", "yes") is True
    assert problems and "Begründung F1" in problems[0] and "gescheitertes Glied F3" in problems[0]
    with pytest.raises(ValueError):
        rp.validate_rating(key, {**bad, "panel_id": "anderer"})


def test_fewer_cases_still_three_ratings_and_balanced_load():
    rng = random.Random("wenig")
    sample, _ = rp.select_cases(_pool(n_tasks=7, per_task=3), 40, rng)
    assert len(sample) == 21
    assignment, load, _ = rp.assign_balanced(sample, raters=10, per_rater=7, overlap=3, max_orgs=6, rng=rng)
    assert load >= 7
    counts = Counter(cid for ids in assignment.values() for cid in ids)
    assert set(counts.values()) == {3}
    loads = [len(ids) for ids in assignment.values()]
    assert max(loads) - min(loads) <= 3  # hoechstens eine Blockgroesse Unterschied


def test_sheet_data_is_blinded(tmp_path):
    import json
    import pathlib
    runs = sorted((pathlib.Path(__file__).resolve().parents[1] / "artifacts" / "runs").glob("run-*.json"))
    records = [json.loads(p.read_text(encoding="utf-8")) for p in runs]
    records = [r for r in records if (r.get("run_set") or (r.get("operator_view") or {}).get("run_set")) != "studie"]
    if not records:
        pytest.skip("keine gespeicherten Probeläufe")
    key, sheet = rp.build_panel(records, seed="blind", purpose="schulung", raters=3,
                               cases_per_rater=12, ratings_per_case=3)
    text = json.dumps(sheet, ensure_ascii=False).lower()
    for word in ("sas2", "sas-2", '"mas"', "gpt-", "claude-", "decision_state", "blind_arm",
                 "pair-", "run-", "architecture", "operating_status", "recommended", "search_log"):
        assert word not in text, word
    # Freitexte des Systems mit Urteilswoertern werden im Schluessel gemeldet, nicht verschwiegen.
    flagged = set(key["verdict_words_in_text"])
    for cid, case in sheet["cases"].items():
        import re
        has = bool(re.search(r"\b(empfehlung|empfohlen|ablehnung|abgelehnt|enthaltung)\b",
                             " ".join(cl["claim_text"] or "" for cl in case["claims"]).lower()))
        assert has == (cid in flagged)
    assert key["marked_claim_rule"]
    assert all(c["representation"]["architecture"] for c in key["cases"])


def test_reading_reports_wrong_sheet_and_duplicates():
    sample, assignment = _assign()
    key = {"schema_version": rp.PANEL_KEY_SCHEMA, "panel_id": "panel-a", "seed": "x", "parameters": {},
           "assignment": assignment, "cases": [], "arms": [], "unsampled_recommended_cases": []}
    rating = {"schema_version": rp.PANEL_RATINGS_SCHEMA, "panel_id": "panel-a", "rater_id": "P01", "answers": {}}
    with pytest.raises(ValueError, match="doppelt"):
        rp.evaluate_panel(key, [rating, rating], bootstrap_draws=5)
    with pytest.raises(ValueError, match="anderen Bogen"):
        rp.evaluate_panel(key, [{**rating, "panel_id": "panel-b"}], bootstrap_draws=5)
    result = rp.evaluate_panel(key, [rating], bootstrap_draws=5)
    assert result["completeness"]["P01"]["answered"] == 0


def test_reason_rule_matches_protocol():
    """Satz bei F3 immer; sonst bei Antworten gegen das Startup und bei nicht beurteilbar."""
    assert all(rp.needs_reason("f3", v) for v in ("yes", "no", "na"))
    for q in ("f1", "f2"):
        assert rp.needs_reason(q, "no") and rp.needs_reason(q, "na") and not rp.needs_reason(q, "yes")
    assert rp.needs_reason("f4", "yes") and rp.needs_reason("f4", "na") and not rp.needs_reason("f4", "no")
    # F5 nur ja/nein: Satz bei „Ja, übertrieben“, keiner bei „Nein, angemessen“.
    assert rp.needs_reason("f5", "yes") and not rp.needs_reason("f5", "no")
    key = {"panel_id": "p", "assignment": {"P01": ["C1"]}}
    answer = {"f1": "yes", "f2": "yes", "f3": "yes", "f4": "no", "f5": "na", "reasons": {"f3": "ok", "f5": "x"}}
    _, _, problems = rp.validate_rating(key, {"schema_version": rp.PANEL_RATINGS_SCHEMA, "panel_id": "p",
                                              "rater_id": "P01", "answers": {"C1": answer}})
    assert problems and "f5" in problems[0]


def test_openai_search_log_keeps_action_and_results():
    from core import LLMClient
    response = {"output": [{"type": "web_search_call", "id": "ws_1", "status": "completed",
                            "action": {"type": "search", "query": "Holzrest Startup",
                                       "sources": [{"type": "url", "url": "https://x.example", "title": "X"}]}},
                           {"type": "message", "content": []}]}
    log = LLMClient._extract_search_log(response)
    assert log == [{"id": "ws_1", "status": "completed", "action": {"type": "search", "query": "Holzrest Startup"},
                    "results": [{"title": "X", "url": "https://x.example"}]}]
    # Die bestehende Zitatauswertung bleibt unveraendert.
    text, citations, calls = LLMClient._extract_text_and_citations(response)
    assert calls == 1 and citations[0]["url"] == "https://x.example"


def test_f3_reason_required_even_when_f3_is_yes():
    """F3: Begründungssatz immer Pflicht, auch bei „Ja, schlüssig“ (Protokoll, Abschnitt 2)."""
    key = {"panel_id": "p", "assignment": {"P01": ["C1"]}}

    def check(reasons):
        answer = {"f1": "yes", "f2": "yes", "f3": "yes", "f4": "no", "f5": "no", "reasons": reasons}
        return rp.validate_rating(key, {"schema_version": rp.PANEL_RATINGS_SCHEMA, "panel_id": "p",
                                        "rater_id": "P01", "answers": {"C1": answer}})[2]

    problems = check({})
    assert problems == ["C1: Begründung F3"]
    assert check({"f3": "   "}) == ["C1: Begründung F3"]
    assert check({"f3": "Prozess, Input und Ergebnis greifen ineinander."}) == []
    # Der Bogen im Browser verlangt den Satz ebenfalls immer.
    import rating_panel_template
    source = open(rating_panel_template.__file__, encoding="utf-8").read()
    assert 'if (q === "f3") return true;' in source
