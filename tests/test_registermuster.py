"""Registerangaben im Impressum (12.11.2026): englische Gerichtsbezeichnungen,
Nummer immer Pflicht."""
import pytest

from evidence_resolver import parse_impressum


@pytest.mark.parametrize("text,country,needle", [
    ("SURAP GmbH Register entry: Register court: Bochum Local Court Register number: HRB 19154", "DE", "HRB 19154"),
    ("A GmbH Commercial Register: HRB 34542 Registration Court: Local Court of Stendal", "DE", "HRB 34542"),
    ("A GmbH District Court Munich HRB 230246", "DE", "HRB 230246"),
    ("A GmbH, Registergericht: Amtsgericht Stuttgart, HRB 783981", "DE", "HRB 783981"),
    ("A eG Genossenschaftsregister GnR 123 Amtsgericht Kempten", "DE", "GnR 123"),
    ("A FlexCo, Kapfenberg, Firmenbuchnummer: FN 663933y, Landesgericht Leoben", "AT", "FN 663933y"),
    ("A AG, 8000 Zürich, UID CHE-123.456.789", "CH", "CHE-123.456.789"),
])
def test_register_with_number_is_recognised(text, country, needle):
    name = text.split(",")[0].split(" Register")[0].split(" Commercial")[0].split(" District")[0].split(" Genossenschaft")[0]
    parsed = parse_impressum(text, name)
    assert needle in parsed["register"] and parsed["country"] == country


@pytest.mark.parametrize("text", [
    "A GmbH Eingetragen im Firmenbuch des Landesgerichts Leoben",   # Wort ohne Nummer
    "A GmbH Register court: Bochum Local Court",                      # Gericht ohne Nummer
    "A GmbH Our commercial register entry is available on request",   # kein Registermerkmal
])
def test_no_register_without_number(text):
    assert parse_impressum(text, "A GmbH")["register"] == ""
