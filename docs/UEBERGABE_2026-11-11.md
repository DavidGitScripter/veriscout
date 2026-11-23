# Übergabe 11.11.2026 (Stand nach der Korrekturrunde)

Für eine spätere Sitzung, die den Verlauf nicht kennt. Enthält keine Schlüssel und keine Inhalte aus `.env`.

## Arbeitsregeln
- **Prüfen und Beenden nie in einem Schritt.** Vor dem Beenden eines Prozesses zuerst prüfen (z. B. offene Verbindungen mit `lsof -p <PID> -a -i`), das Ergebnis lesen und erst dann in einem eigenen Schritt beenden. Am 11.11. wurde ein laufender Claude-Lauf mitten in Paar 3 beendet, weil Prüfung und `kill` in einem Befehl standen.
- Kein kostenpflichtiger Lauf ohne ausdrückliche Freigabe von David. `.env` nicht anzeigen und nicht ändern.
- Nichts einfrieren, solange David den Laufplan nicht freigegeben hat.

## Python-Umgebung (wichtig)
`Dokumente` liegt in iCloud. Die alte `.venv` im Projekt ist teilweise ausgelagert („dataless“), deshalb dauern Starts dort sehr lange. Seit 11.11. gilt:
- Umgebung: `~/.veriscout_venv` (außerhalb von iCloud). Die Paketversionen stimmen exakt mit der alten `.venv` überein, auch die indirekten. `pip freeze` liegt in `runtime/umgebung_veriscout_venv_2026-11-11.txt`.
- Für HTTPS-Aufrufe aus Python immer `SSL_CERT_FILE=/etc/ssl/cert.pem` setzen. Die Python-Installation von python.org findet sonst keine Zertifikate.
- Tests: `~/.veriscout_venv/bin/python -m pytest -q -p no:cacheprovider` (Stand 323 bestanden, 12.11.).
- Oberfläche (nur lokal, Pipedrive live, Studienläufe schreiben nie ins CRM):
  `SSL_CERT_FILE=/etc/ssl/cert.pem nohup ~/.veriscout_venv/bin/python scripts/start_live_review.py --pipedrive-live > /tmp/veriscout_ui.log 2>&1 &`
  Die alte `.venv` liegt noch im Projekt und wurde nicht gelöscht.

## Codestand
- **K1** (`entity_verifier.py`): Produktfähigkeit gilt als durch die offizielle Quelle belegt, wenn irgendeine abgerufene Seite derselben offiziellen Website mit gefundenem Auszug „product“ stützt, nicht nur die Identitätsseite.
- **K2** (`agents.py`, `baselines.py`): Fließtext vor einem leeren JSON-Array zählt als gültiges Leerergebnis. Gespeichert werden der Vortext (`empty_array_preamble`) und die Protokollabweichung `empty_array_with_preamble`. Ein nicht leeres Array mit Vortext bleibt ein Vertragsfehler.
- **K3** (`agents.py`, `ScoutingAgent.SYSTEM`, gilt für SAS-2 und MAS): „Nach der Recherche zur Zielorganisation suchst du mit mindestens drei unterschiedlichen Websuchen gezielt nach Startups. Erst danach ist ein leeres Array zulaessig …“. Die Promptfassung `core.py` ist `public-push-pull-sas2-mas-v11-startup-search-2026-11-11`. Budgetprofil und Reasoning-Stufe („low“) sind unverändert.
- **Suchprotokoll**: Jeder Modellaufruf speichert `search_log` (zusätzliches Feld, ändert weder Anfrage noch Auswertung). Anthropic: `input.query` je Suche, Treffer mit Titel und URL. OpenAI: `action.query` bzw. `action.queries`, Aktionstypen `search`, `open_page`, `find_in_page`, Treffer aus `action.sources`.
- **Feste Studienvorlage** (`scripts/run_study.py`, `PUSH_TEMPLATE`): „Suche ein reales, aktives B2B-Startup … Ob ein passendes Startup-Unternehmen existiert, ist offen; ein leeres Ergebnis ist zulaessig.“ Die Generalprobe (`scripts/run_api_probe.py`) nutzt denselben Wortlaut.
- **Bewertungsbogen für 10 Personen** (`rating_panel.py`, `rating_panel_template.py`, Oberfläche Reiter 3):
  - Je Fall 3 Personen, 12 Fälle je Person, Mehrheitsregel ohne Einigung.
  - F1–F4 mit ja / nein / nicht beurteilbar, F5 nur ja / nein.
  - Begründung bei F3 immer, sonst bei jeder Antwort gegen das Startup und bei „nicht beurteilbar“.
  - Der Schulungsbogen liegt in `artifacts/vorschau_bewertungsbogen/`.
- Noch nicht eingebaut: die zwei Ergänzungssätze zur Anleitung und Übungsfälle mit Musterlösung.

## Sicherungen
- `_sicherung_2026-11-07` bis `_sicherung_2026-11-07g`: Oberfläche und Bewertungsbogen, 07.11.
- `_sicherung_2026-11-11`: `rating_panel*.py` vor der Überarbeitung, `core.py` und `llm_anthropic.py` vor dem Suchprotokoll.
- `_sicherung_2026-11-11b/vor_K1`, `vor_K2`, `vor_K3`: Stand vor der jeweiligen Korrektur (Rücknahme einzeln möglich).

## Läufe vom 11.11. (alle Probeläufe, Kosten laut Kostenbuch in USD)
| Lauf | Modell | Prompt | Unternehmen | Kosten | Ergebnis |
|---|---|---|---|---|---|
| run-probe-44eaa71a0a21 | Sonnet | v10 | Max Wild | 0,750 | 2 Kandidaten, Enthaltung |
| run-probe-c151d1840978 | Sonnet | v10 | Baufritz | 0,158 | 1 Suche je Arm, leer |
| (kein Lauf gespeichert) | Sonnet | v10 | Goldhofer | unbekannt, höchstens 1,50 | durch Beenden abgebrochen |
| run-probe-6d1af3f19a7d | Sonnet | v10 | Baufritz | 0,158 | Wiederholung, wieder leer |
| run-probe-e15a5145b717 | Sonnet | v10 | Goldhofer | 0,285 | leer; MAS technischer Fehler (Vortext) |
| run-probe-b61a2f87f9b4 | Sol | v10 | Max Wild | 0,476 | Optocycle 2×, Enthaltung |
| run-probe-6dc708027ffc | Sol | v10 | Baufritz | 0,487 | CAALA (9/9 belegt), ecoplanet, Enthaltung |
| run-probe-c8a8069537a3 | Sol | v10 | Goldhofer | 0,539 | Sonibel, ArcNC, Enthaltung |
| run-probe-100f93575d55 | Sonnet | v11 | Max Wild | 1,086 | Optocycle 2×, Enthaltung |
| run-probe-b478e41fc8e7 | Sonnet | v11 | Baufritz | 0,345 | Startup-Suchen, aber leer |
| run-probe-ed445bc5ad41 | Sonnet | v11 | Goldhofer | 0,397 | Startup-Suchen, aber leer |
| run-probe-26ae2494415b | Sol | v11 | Max Wild | 0,484 | Optocycle, Neustark, Enthaltung |
| run-probe-64acba6783eb | Sol | v11 | Baufritz | 0,463 | ecoplanet 2×, Enthaltung |
| run-probe-ff81069408af | Sol | v11 | Goldhofer | 0,622 | Verbotics (Index 78), WeldNova, Enthaltung |

Summen laut Kostenbuch: OpenAI 3,071 USD, Anthropic 3,179 USD plus das abgebrochene Paar (höchstens 1,50 USD). Den Abgleich mit den Konsolen macht David.
Eingangsprüfung v11: beide Modelle `passed = true`. 0 Empfehlungen.

## Offene Punkte
1. Davids Entscheidung: Hauptlauf vorbereiten, eine weitere Verbesserungsrunde oder erst Prof. Ertl fragen.
2. Laufplan (empfohlen C: 15 Aufgaben × 2 Modelle × 2 Wiederholungen), Aufgabenliste `studie/aufgaben.csv`, Fallblätter `studie/fallblaetter.json` und Bewertungsprotokoll `studie/BEWERTUNGSPROTOKOLL.md` kommen aus der Cloud. Die maßgebliche Fassung des Protokolls ist die aus der Cloud, nicht `docs/BEWERTUNGSPROTOKOLL_ENTWURF.md`.
3. Bodeneffekt: bisher keine Empfehlung. Sonnet findet bei 2 von 3 Unternehmen nichts, auch mit v11.
4. Ergänzungen im Bewertungsbogen (zwei Sätze, Übungsfälle) und Abschnitt 6 von `docs/HAUPTSTUDIE_ABLAUF.md` (beschreibt noch das alte Verfahren mit 2 Personen).

## Befehle für den Hauptlauf (erst nach Freigabe)
Plan einfrieren (Laufplan C; das Kommando legt den Plan an und überschreibt keinen vorhandenen):
```bash
SSL_CERT_FILE=/etc/ssl/cert.pem ~/.veriscout_venv/bin/python scripts/run_study.py plan --tasks studie/aufgaben.csv --case-sheets studie/fallblaetter.json --seed "<frei gewählter Text, notieren>" --models gpt-6.1-sol,claude-sonnet-5-5 --modes push --replicates 2 --stability 0 --max-usd-per-model gpt-6.1-sol=28,claude-sonnet-5-5=26 --protocol-file studie/BEWERTUNGSPROTOKOLL.md --out studie/plan.json
```
Plan ansehen (kostenlos): `~/.veriscout_venv/bin/python scripts/run_study.py run-all --plan studie/plan.json`
Hauptlauf:
```bash
SSL_CERT_FILE=/etc/ssl/cert.pem caffeinate -i ~/.veriscout_venv/bin/python -u scripts/run_study.py run-all --plan studie/plan.json --confirm-paid
```
Stand: `~/.veriscout_venv/bin/python scripts/run_study.py status --plan studie/plan.json`

## Nachtrag abends: Regeln v12 und Generalprobe v12
- Regeln R1–R5 (DACH, Impressum, Gründungsjahr ≤ 10 Jahre, Kette belegt/abgeleitet, Kennzeichnung): siehe `docs/REGELN_V12_2026-11-11.md`; Simulation: `runtime/simulation_regeln_v12_2026-11-11.md` (1 Empfehlung CAALA, 2 Ablehnungen, 22 Enthaltungen).
- Generalprobe v12: Sol 2 Paare (`run-probe-a73de2a4765f`, `run-probe-6abdf11a8c43`, zusammen 1,167 USD, alle Enthaltung). Sonnet angehalten (`run-probe-683e533a070c`, `run-probe-33e51cba27bf`, je 0,187 USD): Websuche scheitert mit `invalid_tool_input`, weil das Modell `{"params": {...}}` sendet; plus Diagnose etwa 0,35 USD.
- Paare einzeln mit `--only <task_id> --max-total-usd 1.5`, weil die Worst-Case-Prüfung (1,50 USD je Paar) sonst den Deckel 2,50 USD je Modell reißt. Nebenwirkung: Reihenfolge immer SAS-2 zuerst.
- Offen: Entscheidung zu Sonnet (später erneut testen oder älteres Suchwerkzeug `web_search_20250305`); optional `truststore` für Seiten mit unvollständiger SSL-Kette (ändert die festgeschriebene Umgebung, nur mit Freigabe).

## Generalprobe 3 (11.11.2026, 18 Uhr, v12, aktueller Code)
- Sonnet, Max Wild (`run-probe-4694ffb167c2`, 0,587 USD): SAS-2 wieder 0 Suchen (`invalid_tool_input`, `{"params": …}`), drittes Mal in Folge; MAS normal (11 Suchen): neustark AG Enthaltung, OPTOCYCLE GmbH Ablehnung (Gegenbeleg Startup-Status). Sonnet angehalten.
- Sol, Goldhofer (`run-probe-deb9f4a19b17`, 0,542 USD): Assemblio (SAS-2, Index 67; Gründungsjahr und Input offen), IUNA AI Systems (MAS, Index 78; nur Input offen). Input hat das Modell selbst als unbekannt markiert.
- Sol, Südpack (`run-probe-e3c0871f73e8`, 0,543 USD): jora.tech FlexCo in beiden Armen. SAS-2 Index 89, nur Startup-Status offen: Firmenbuch-Eintrag 08.10.2025 (evi.gv.at, bestätigt) zählt nicht als Gründungsbeleg, weil R3 nur Gründungswörter erkennt und nur im Verifier wirkt, nicht in der Matrix. Vorschlag an David, nicht umgesetzt.
- 0 Empfehlungen, kein technischer Fehler bei Sol.

## R3 Registereintrag (11.11.2026, 19:22, David „1 ja“)
- Bestätigter Register-/Firmenbucheintrag zählt als Gründungsbeleg, auch in der Matrixzelle Startup-Status (`entity_verifier.founding_source`). Sicherung `_sicherung_2026-11-11d/`. 276 Tests.
- Neubewertung aller 35 gespeicherten Kandidaten-Arme: 1 Empfehlung (CAALA), 3 Ablehnungen (Carbo Culture, ArcNC, OPTOCYCLE Sonnet-MAS), 31 Enthaltungen. jora.tech (SAS-2) jetzt Index 100 und volle Matrix, blockiert nur durch QG3 (zitiertes Interview kunststoffe.de, Auszug nicht bestätigt). Entscheidung zu QG3 offen.

## 12.11.2026: v13 und Generalprobe 4
- Änderungen v13 (Sonnet `web_search_20250305`, QG3, ein Wiederholversuch, truststore, Input-Prüffrage): `docs/REGELN_V13_2026-11-12.md`. Sicherung `_sicherung_2026-11-12/vor_v13/`. 287 Tests.
- Generalprobe 4: `docs/GENERALPROBE_4_2026-11-12.md` (Läufe 960dfb292bbf, ee22dd0954b8, 8abd266147be; 0 Empfehlungen; Anthropic 1,046 USD, OpenAI 1,151 USD).
- Offen: Davids Entscheidung zur Sonnet-Eingangsprüfung (3 Paare), Guthaben Anthropic, Cloud-Dateien, Freigabe Musterlösungen.

## 12.11.2026 nachmittags: v14 und Generalprobe 5
- Ursachenanalyse: `docs/URSACHEN_LUECKEN_2026-11-12.md`. Änderungen v14 (M1 Datenbanksperre, M2 Nachrecherche `follow_up.py`, M3, M5, Input-Feld): `docs/REGELN_V14_2026-11-12.md`. Sicherung `_sicherung_2026-11-12/vor_v14/`. 307 Tests.
- Worst Case je Paar jetzt 2,00 USD (Arm 1,00 USD inkl. Nachrecherche-Reserve 0,25 USD).
- Generalprobe 5: `docs/GENERALPROBE_5_2026-11-12.md` (Läufe dffcc26d9f75 Sol Goldhofer, 87dfef1f5ae2 Sonnet Max Wild). 1 Empfehlung: byte robotics GmbH (Sol, SAS-2) über die Nachrecherche.
- Davids Entscheidung: Deckel 2,50 USD je Modell, keine zweiten Paare. Keine weiteren bezahlten Aufrufe ohne Freigabe.

## 12.11.2026 abends: v15 und Generalprobe 6
- Änderungen v15 (N1 Quellenabgleich, N2 Wortlaut-Hilfe, N3 Auslöser 44/4, CODE_FILES ergänzt): `docs/REGELN_V15_2026-11-12.md`. Sicherung `_sicherung_2026-11-12/vor_v15/`. 323 Tests.
- Generalprobe 6: `docs/GENERALPROBE_6_2026-11-12.md` (Läufe b010fc1ca416 Sol Südpack, 7e9f16d97da2 Sonnet Baufritz, c446dd8f93b2 Sonnet Goldhofer). 0 Empfehlungen, 0 technische Fehler; Sonnet-Eingangsprüfung mit 4 fehlerfreien Paaren erfüllt. Kosten 2,243 USD.
- Offen: Entscheidung „Prozessfeld“ (Freitextfeld process_stage beim Zielprozess nicht mehr verlangen; Simulation +1 Empfehlung, jora.tech MAS b010fc1ca416).
- Archive: vollständige Quellpakete nur in `New project/releases/` (bis 18.10.2026); `_sicherung_*` enthalten nur geänderte Dateien.

## 12.11.2026 spät: v16, v17, Hauptlaufplan
- v16 Prozessfeld (`docs/REGELN_V16_2026-11-12.md`), v17 Suchregel, Feldregel 6–8, Registermuster, Fundseite, Reihenfolge und Obergrenzen je Anbieter (`docs/REGELN_V17_2026-11-12.md`). 349 Tests.
- Sonnet-Probepaar v17 Baufritz (`run-probe-cf98adc3d821`, 0,556 USD): beide Arme leer nach 5 bzw. 6 Suchen, kein technischer Fehler.
- Hauptlauf: 60 Paare, Obergrenzen Sol 28 USD, Sonnet 26 USD. Freeze-Befehl oben angepasst; noch nicht eingefroren.
- Kostenbuch (Laufdateien): OpenAI 9,789 USD, Anthropic 9,502 USD (+ ca. 0,35 USD Diagnose außerhalb des Kostenbuchs).
