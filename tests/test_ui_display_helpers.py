"""Anzeigehilfen der Oberflaeche (static/ui_helpers.js) und lesende Fundstellen-Anreicherung."""
import json
import pathlib
import shutil
import subprocess

import pytest
import server

ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPERS = ROOT / "static" / "ui_helpers.js"
NODE = shutil.which("node")


def _js(expression: str):
    script = f"const h = require({json.dumps(str(HELPERS))}); console.log(JSON.stringify({expression}));"
    out = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


needs_node = pytest.mark.skipif(NODE is None, reason="Node.js nicht installiert")


@needs_node
def test_fragment_url_short_excerpt_is_encoded():
    url = _js('h.fragmentUrl("https://example.com/a", "Wir verwerten Schleifschlamm, sauber-getrennt.")')
    assert url == ("https://example.com/a#:~:text="
                   "Wir%20verwerten%20Schleifschlamm%2C%20sauber%2Dgetrennt.")


@needs_node
def test_fragment_url_long_excerpt_uses_start_and_end_and_first_part_only():
    excerpt = ("eins zwei drei vier fuenf sechs sieben acht neun zehn elf zwoelf"
               " ... ganz anderer Teil der Seite")
    url = _js(f'h.fragmentUrl("https://example.com/p#abschnitt", {json.dumps(excerpt)})')
    assert url == ("https://example.com/p#abschnitt:~:text="
                   "eins%20zwei%20drei%20vier%20fuenf,acht%20neun%20zehn%20elf%20zwoelf")


@needs_node
def test_fragment_url_rejects_unsafe_schemes_and_tiny_excerpts():
    assert _js('h.fragmentUrl("javascript:alert(1)", "irgendein langer Auszug")') == ""
    assert _js('h.fragmentUrl("https://example.com/", "kurz")') == "https://example.com/"


@needs_node
def test_shared_candidates_match_by_name_or_domain():
    arms = [
        {"candidates": [{"candidate_id": "a1", "name": "WeSort.AI GmbH", "website": "https://wesort.ai"},
                        {"candidate_id": "a2", "name": "Allein AG", "website": ""}]},
        {"candidates": [{"candidate_id": "b1", "name": "WeSort AI", "website": "https://www.wesort.ai/de"},
                        {"candidate_id": "b2", "name": "Andere", "website": "https://andere.de"}]},
    ]
    shared = _js(f"[...h.sharedCandidateIds({json.dumps(arms)})].sort()")
    assert shared == ["a1", "b1"]


@needs_node
def test_why_sentence_only_summarises_stored_fields():
    candidate = {"decision_state": "enthaltung", "matrix": [
        {"dimension": "identity", "status": "supported"},
        {"dimension": "startup_status", "status": "partial"},
        {"dimension": "input_stream", "status": "missing"},
        {"dimension": "transformation", "status": "contradicted"},
        {"dimension": "x", "status": "not_applicable"}]}
    text = _js(f'h.whyNoRecommendation({json.dumps(candidate)}, {{startup_status: "Unternehmenstyp"}}, '
               f'{{partial: "teilweise", missing: "fehlt", contradicted: "Widerspruch"}})')
    assert text == ("3 von 4 Dimensionen nicht vollständig belegt: Unternehmenstyp (teilweise), "
                    "input_stream (fehlt), transformation (Widerspruch). Davon 1 durch eine Quelle widerlegt.")
    assert _js('h.whyNoRecommendation({decision_state: "empfehlung"})') == ""


@needs_node
def test_arm_sentence_and_supported_share():
    arm = {"decision_states": [], "candidates": [], "resources": {"failure_reasons": ["timeout"]}}
    assert _js(f"h.whyArmWithoutRecommendation({json.dumps(arm)})") == "Kein Startup vorgeschlagen. Grund: timeout."
    assert _js('h.supportedShare({claims_stage_1: 0})') is None
    assert _js('h.supportedShare({claims_stage_1: 8, claims_supported_stage_2: 6})') == 0.75
    assert _js('h.firstStartBlocker([{label: "A", ok: true}, {label: "B", ok: false, help: "x"}])') == "B: x"


def test_run_record_gets_source_locations_without_touching_the_file():
    runs = sorted((ROOT / "artifacts" / "runs").glob("run-probe-*-neubewertet.json"))
    if not runs:
        pytest.skip("kein gespeicherter Lauf vorhanden")
    path = runs[0]
    before = path.read_bytes()
    record = json.loads(before)
    server._attach_source_locations(record)
    assert path.read_bytes() == before
    sources = [s for p in record["operator_view"]["pairs"] for a in p["arms"]
               for c in a["candidates"] for s in c["sources"]]
    assert sources and all("resolved_url" in s and "matched_context" in s for s in sources)


def test_index_loads_helpers_before_app():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert html.index("/static/ui_helpers.js") < html.index("/static/app.js")
