"""Oberflaeche: nur PUSH, Start per Knopf mit Kostenhinweis, Serverschutz bleibt."""
import pathlib

import server

STATIC = pathlib.Path(__file__).resolve().parents[1] / "static"


def test_ui_offers_only_push_and_no_project_name_field():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'name="searchMode"' not in html and 'id="searchArea"' not in html
    assert 'id="projectName"' not in html
    assert "Auftragsart: PUSH" in html
    assert 'return { search_mode: "push" };' in js
    assert 'name: byId("organizationName").value.trim()' in js


def test_start_click_is_the_confirmation_and_shows_max_cost():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert 'id="confirmLive"' not in html
    assert 'id="costNote"' in html
    start = js[js.index("async function startRun()"):]
    start = start[:start.index("\n}\n")]
    # Bestaetigungsdialog vor dem Lauf, Sperre gegen Doppelklick.
    assert start.index("if (state.running) return;") < start.index("window.confirm(")
    assert start.index("window.confirm(") < start.index("state.running = true;")
    assert "confirm_live: true" in start


def test_server_still_rejects_runs_without_confirm_live():
    source = pathlib.Path(server.__file__).read_text(encoding="utf-8")
    assert "if not req.confirm_live:" in source
