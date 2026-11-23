# VeriScout (früher VentureScout) – kontrollierter SAS–MAS-Scoutingvergleich

Forschungsprototyp für öffentlich belegtes PUSH-Scouting. Das System vergleicht
einen starken Single Agent mit Self-Review (`SAS-2`) und ein kleines
Multi-Agentensystem aus Recherche und getrennter Verifikation (`MAS`). CRM und
Outreach bleiben nachgelagerte Demonstrationsfunktionen und sind nicht Teil des
primären Qualitätsvergleichs.

## Transferprüfung mit Marc

Der neue Arbeitsbereich unterstützt eigene Organisationskontexte, geprüften
Projektimport/-export und ein Aufgabenprotokoll. Start ohne API-Zugangsdaten:

```bash
.venv/bin/python scripts/start_transfer_review.py
```

Danach `http://127.0.0.1:8001` öffnen. Dieser getrennte Startmodus deaktiviert
Live-Recherche, CRM und Outlook. Der vorhandene Live-Start bleibt erhalten.
Projektdateien enthalten Organisation, Suchprompt, Zeitpunkt und Bezeichnung.
Sie ersetzen weder die Serverkonfiguration noch ein Studien- oder Run Bundle.
Ein Transfer erfolgt im Pilotmodus ohne Memory mit einer Wiederholung.

- [Schritt-für-Schritt-Anleitung](docs/MARC_TRANSFERTEST.md)
- [Modellkarte und Übertragungsblatt](docs/REFERENCE_MODEL_CARD.md)
- [Ergebnisvorlage für den 08.10.](docs/TRANSFER_RESULT_TEMPLATE.md)
- [Änderungen, Prüfnachweise und Grenzen](docs/TRANSFER_IMPLEMENTATION_REPORT.md)

### Quellpaket auf einem weiteren Rechner vorbereiten

Das ZIP enthält keine virtuelle Umgebung und keine persönlichen API-Zugänge.
Nach dem Entpacken im Ordner `venturescout` zunächst mit Python 3.13 prüfen:

```bash
python3 scripts/verify_release.py
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/start_transfer_review.py
```

Unter Windows lauten die letzten beiden Programmaufrufe
`.venv\Scripts\python.exe -m pip install -r requirements.txt` und
`.venv\Scripts\python.exe scripts/start_transfer_review.py`.
Die Installation benötigt Internetzugang zum Paketregister. Der anschließende
Transfermodus benötigt weder API-Schlüssel noch Modellaufrufe. Der Manifestcheck
erkennt veränderte Paketdateien, authentifiziert aber keinen Absender. Getestet
wurde macOS mit vorhandenen Abhängigkeiten. Eine Neuinstallation auf einem
fremden Rechner oder Windows wurde bislang nicht ausgeführt.

Die Oberfläche hält Beobachtungen nur im aktuellen Tab, bis sie exportiert
werden. Export vor dem Schließen ist erforderlich. Ein erfolgreiches
Bedienexperiment ist weder ein fachlicher Treffernachweis noch ein Nachweis
allgemeiner MAS-Überlegenheit.

## Stand vom 16. Oktober 2026 (v18)

Neue Oberfläche „VeriScout“ mit vier Bereichen, vier einheitliche
Zielzustände, kostenfreie Sensitivitätsanalysen, bayesianisches Intervall im
Auswerter, Laufdateien in `artifacts/runs/`, zweite Modellfamilie (Claude über
`anthropic`), robusterer Quellenabruf und Neubewertung gespeicherter Läufe.
Vorführung und Selbsttest: [docs/VORFUEHRUNG.md](docs/VORFUEHRUNG.md).
Stand: 170 von 170 Tests bestanden.

## Änderungen vom 13. Oktober 2026 (P0)

- Standardbudget aus den Pilotläufen vom 5. September kalibriert
  (120.000 Input-, 16.000 Ausgabe- und 8.000 Reasoning-Tokens, acht
  Websuchen, zwölf Quellenabrufe, drei Kandidaten, 0,60 USD je Arm).
- Beide Modellstufen erhalten eine harte Reservierung je Arm. Überzieht der
  Anbieter das Websuchlimit, wird das als Protokollabweichung je Stufe
  berichtet (`SCOUTREF_EVAL_WEB_OVERRUN_POLICY=fail` stellt das alte
  Verhalten her).
- SAS-2-Self-Review und MAS-Verifier verwenden denselben kompakten
  Prüfvertrag (`review_contract.py`). Unterschiedlich sind nur Rolle,
  Kontext und Quellenbasis.
- Unscharfer Auszugsabgleich im Resolver (`SCOUTREF_EXCERPT_MATCH_MODE=exact`
  für den früheren strengen Modus), PDF-Quellen erhalten einen eigenen Status.
- Primäranalyse zählt alle zugewiesenen Läufe (Fehler = 0), inklusive des
  Anteils in allen Wiederholungen erfolgreicher Aufgaben.
- `tests/test_p0_end_to_end_comparison.py` zeigt den Positivpfad in beiden
  Armen. Stand: 160 von 160 Tests bestanden.

## Sicherheitsstatus

- Ein API-Schlüssel allein startet keinen bezahlten Lauf.
- Live-Vergleiche erfordern zusätzlich `SCOUTREF_EVAL_LIVE_ENABLED=1`, einen
  `SCOUTREF_OPERATOR_TOKEN` und eine
  ausdrückliche Bestätigung in der Oberfläche.
- Vergleichsläufe schreiben weder in Pipedrive noch nach Outlook.
- Kuratierte Kandidaten sind in beiden Versuchsarmen deaktiviert.
- Technische Fehler, Modellabweichungen und Budgetverletzungen werden
  fail-closed protokolliert.

## Schnellstart ohne bezahlte Aufrufe

```bash
python3 scripts/run_contract_tests.py
uvicorn server:app --host 127.0.0.1 --port 8000
```

Danach `http://127.0.0.1:8000` öffnen. Die Vorschau erzeugt den kanonischen
Auftrag, Input- und Prompt-Hash und verursacht keine API-Kosten.

## Geschützter lokaler Entwicklungsstart

```bash
.venv/bin/python scripts/start_live_review.py
```

Einen bereits laufenden lokalen Server vorher beenden. Der Starter bindet nur
an `127.0.0.1:8000`, aktiviert die Live-Freigabe und speichert einen privaten
Bedienerschlüssel in `runtime/local_review_operator_token.txt` (Dateimodus 0600).
Diesen Schlüssel lokal öffnen und in das Feld „Laufberechtigung“ der Oberfläche
einfügen. Nicht den OpenAI-API-Key in dieses Feld eintragen.

Der Start selbst verursacht keine API-Kosten. Nach der Auftragsvorschau muss
ein kostenpflichtiger Lauf ausdrücklich bestätigt werden. Dieses Profil dient
nur der Entwicklung: ein Pilotpaar ohne Memory, maximal ein Kandidat je Arm,
160.000 Inputtokens, 16.000 Outputtokens, acht Webaufrufe, zwei Modellaufrufe
und zwölf direkte Quellenabrufe je Arm. Der lokale Kostenrahmen beträgt 0,60 USD
je Arm beziehungsweise 2 USD für diese Entwicklungsserie. Das ist eine
Schätzung, kein hartes Abrechnungslimit des Anbieters. Frühere oder außerhalb
dieses Starters ausgeführte API-Aufrufe werden in diesem separaten Ledger nicht
erfasst. Ein Überschreiten durch unerwartete Provider-Nutzung bleibt möglich.

Die Einstellung ersetzt nicht das eingefrorene Protokoll einer Hauptstudie.
CRM- und Outlook-Aktionen bleiben gesperrt. Fehlende Freigaben werden in der
Oberfläche einzeln benannt. `--check` prüft das Profil ohne Serverstart,
Schlüsselerzeugung oder API-Aufrufe.

Der fachliche Eingabevertrag ist bewusst knapp. Ein Auftrag enthält nur:

1. den öffentlichen Namen genau einer Zielorganisation und
2. einen ausreichend konkreten Suchprompt, der den öffentlich erkennbaren
   Prozessbezug und die gewünschte Wirkung beschreibt.

Eine Profil-URL, Quellenliste oder ein vorformulierter Belegauszug ist kein
Eingabefeld. Beide Versuchsarme müssen Organisationskontext, Kandidaten und
Belege selbst recherchieren. Der Server erzeugt aus den beiden Eingaben eine
stabile Organisations-, Aufgaben- und Prompt-Kennung und friert den identischen
kanonischen Auftrag für SAS und MAS ein.

## Kontrollierter Datenfluss

```text
Zielorganisation + eingefrorener kanonischer Suchauftrag
                   │
        ┌──────────┴──────────┐
        │                     │
 SAS-2: Recherche       MAS: Recherche
 + eigener Review       → Verifikation
        │                     │
        └──────────┬──────────┘
                   │
 gemeinsame deterministische Quellenauflösung, Entitätsprüfung,
 Claim-Manifest, relationale Evidenzmatrix und Gates
                   │
       verblindeter Export für Fachurteile
```

Die Versuchsarme erhalten denselben fachlichen Auftrag, dieselbe Modell-ID,
dasselbe Reasoning-Level und identische globale Obergrenzen für Kandidaten,
Tokens, Modell- und Webaufrufe, direkte Quellenabrufe sowie Kosten. Der reale
Verbrauch wird je Arm separat berichtet.

## Projektstruktur

```text
prototype_push/
├── config/                 versionierte, nicht geheime Konfiguration
├── data/
│   ├── public/             leere Vorlagen und synthetische Demoentitaeten
│   └── development/        synthetische/kuratierte Entwicklungsdaten
├── docs/                   Architektur, Datenregel und Evaluationsprotokoll
├── artifacts/              Laufartefakte; standardmäßig nicht versioniert
├── scripts/                lokale Prüfwerkzeuge
├── static/                 aufgabenorientierte Vergleichsoberfläche
├── templates/              Outreach-Vorlagen
├── tests/                  Offline- und Vertragstests
├── experiment_protocol.py  unveränderlicher public-only Auftrag
├── compare_architectures.py gepaarter Versuchsrunner und Blindexport
├── resource_budget.py      globaler Ressourcenbroker je Arm
├── agents.py               Recherche- und Verifikationsrolle
├── baselines.py            starke SAS-2-Kontrolle
├── evidence_*.py           Quellen- und relationale Evidenzprüfung
├── pipeline.py             Orchestrierung
└── server.py               lokale API und Oberfläche
```

Die Python-Einstiegsmodule bleiben bewusst im Projektstamm. Diese kompatible
Schicht vermeidet kurz vor der Evaluation unnötige Import- und Deploymentbrüche;
Daten, Konfiguration, Berichte und Artefakte sind bereits fachlich getrennt.

## Dokumentation

- [Architektur](docs/ARCHITECTURE.md)
- [Evaluationsprotokoll](docs/EVALUATION_PROTOCOL.md)
- [Daten- und Vertraulichkeitsregel](docs/DATA_POLICY.md)
- [Memory-Ablation](docs/MEMORY_ABLATION.md)
- [Expertenleitfaden](docs/EXPERT_INTERVIEW_GUIDE.md)
- [Publikationscheckliste](docs/PUBLICATION_CHECKLIST.md)
- [Reproduzierbarkeit und Entblindung](docs/REPRODUCIBILITY.md)

## Live-Konfiguration

`.env.example` dokumentiert alle Schalter und Budgets. Geheimnisse gehören nur
in die lokale `.env`, die nicht versioniert wird. Vor dem ersten bezahlten
Versuch werden Aufgabenmanifest, Holdout, Budget, Wiederholungszahl,
Fehlerregeln und Annotationsrubrik eingefroren.

## Offline-Prüfung

```bash
python3 -m pip install -r requirements-dev.txt
python3 scripts/run_contract_tests.py
python3 -m compileall -q .
node --check static/app.js
```

Der Runner und CI verwenden dieselbe pytest-Sammlung; ein separater
Direktaufruf einzelner Testfunktionen ist bewusst entfernt, damit Fixtures und
Negativtests nicht unbemerkt ausgelassen werden. Am 31. August 2026 bestanden
87 von 87 Offline- und Vertragstests. Diese Zahl belegt ausschließlich den
geprüften Softwarestand.

Eine positive Empfehlung erfordert zugleich einen Bewertungswert von mindestens
61, eine vollständige relationale Evidenzmatrix, Widerspruchsfreiheit, negative
Ausschlussprüfung und sämtliche Quality Gates. Valide Enthaltungen bleiben in
der Primäranalyse; technisch fehlerhafte oder wegen Resolverbudget nicht
vollständig prüfbare Paare werden gesondert ausgewiesen und nicht als
Qualitätsnull umgedeutet.

## Aussagegrenze

Offline-Tests belegen Funktionsverträge, nicht die qualitative Überlegenheit
einer Architektur. Ein MAS-Vorteil wird erst dann behauptet, wenn verblindete
Fachurteile eine praktisch relevante Verbesserung bei gleicher Aufgabe und
gleichen Obergrenzen zeigen und dieser Befund nicht allein durch Mehrverbrauch
entsteht. Memory wird separat in einem 2×2-Design für beide Architekturen
untersucht; ein allgemeiner Memory-Effekt begründet für sich genommen kein MAS.
