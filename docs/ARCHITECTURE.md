# Systemarchitektur

## Zweck

Der Prototyp untersucht, ob eine getrennte Recherche- und Verifikationslogik
bei einer offenen, ausschließlich öffentlich belegten PUSH-Suche bessere
Ergebnisse liefert als ein starker Single-Agent-Kontrollarm. CRM und Outreach
sind nachgelagerte Demonstrationsfunktionen und nicht Bestandteil des
primären Qualitätsvergleichs.

## Kontrollierter Datenfluss

```text
PublicSearchTaskInput
  ├─ öffentlicher Name genau einer Zielorganisation
  ├─ genau ein frei formulierter Suchprompt
  ├─ serverseitig erzeugte Aufgaben- und Organisations-ID
  └─ kanonischer Auftrag + Prompt- und Task-Hash
              │
              ├──────── SAS-2 ────────┐
              │  Recherche + Self-Review
              │                       │
              └──────── MAS ──────────┤
                 Scouting → unabhängige Verifikation
                                      │
                         gemeinsame Deterministik
                         Round-Robin-Quellenauflösung
                         Claim-Manifest
                         relationale Evidenzmatrix
                         Policy- und Quality-Gates
                                      │
                         verblindeter Ergebnisexport
```

Beide Versuchsarme erhalten denselben kanonischen fachlichen Auftrag, denselben
Recherchestichtag und dieselben Ressourcenobergrenzen. Sie erhalten weder eine
vorgegebene Startquelle noch einen Kandidaten. Die architekturspezifischen
Rollenprompts dürfen sich nur dort unterscheiden, wo sie die jeweils
untersuchte Arbeitsaufteilung umsetzen. Gefundene Quellen und Auszüge sind
protokollierte Systemausgaben, keine Nutzereingaben.

## Agenten und Services

- **ScoutingAgent:** autonome öffentliche Recherche und Kandidatenbildung.
- **VerificationAgent:** informationsseitig getrennte Prüfung atomarer
  Behauptungen; erhält keine Scout-Bewertung als Wahrheit. Da beide Rollen
  dasselbe Grundmodell nutzen, ist dies keine epistemische Unabhängigkeit.
- **SingleAgent-Baseline:** Recherche und Gegenprüfung in einer logischen Rolle.
- **FeedbackMemory:** versionierter, schreibgeschützter Retrieval-Service; kein
  Sachbeleg und ohne separate Kalibration keine Scoreänderung.
- **EvidenceResolver, Evidenzmatrix, Policy Gate und Quality Gates:**
  deterministische gemeinsame Services, keine Agenten.
- **OutreachAgent:** erst nach menschlicher Freigabe; außerhalb des Experiments.

## Entscheidungs- und Statusvertrag

Eine positive Empfehlung ist nur zulässig, wenn der Bewertungswert mindestens
61 beträgt, die relationale Evidenzmatrix `fully_supported` ist, kein
Widerspruch oder Ausschluss vorliegt und sämtliche Quality Gates bestehen. Die
61er-Schwelle ist damit notwendig, aber niemals hinreichend. Der Wert stammt
aus formativen Entwicklungsdurchläufen und wird im Holdout nicht nachträglich
optimiert.

Die Versuchsarme verwenden vier getrennte Ergebniszustände:

- `completed`: technisch gültiger Arm mit mindestens einem vollständig
  geprüften Kandidaten;
- `abstention`: technisch gültiges Leer- oder Enthaltungsergebnis; es zählt
  bei `Qualified-Hit@5` als null;
- `not_checked_budget`: der eingefrorene Resolverrahmen reichte nicht für eine
  vollständige Prüfung; das gesamte Paar wird aus der Primäranalyse
  ausgeschlossen und separat berichtet;
- `technical_error`: Provider-, Schema-, Modellidentitäts- oder
  Budgetverletzung; auch hier wird das gesamte Paar ausgeschlossen.

Der gemeinsame Resolver verteilt direkte Dokumentabrufe deterministisch nach
Kandidatenrang und Quellenposition im Round-Robin-Verfahren. Nicht mehr
erreichbare Quellen erhalten `not_checked_budget`; das Erreichen des Caps ist
für sich genommen kein Providerfehler.

## Sicherheitsgrenzen

- Ein vorhandener API-Schlüssel aktiviert keine bezahlten Vergleichsläufe.
- Live-Evaluation erfordert zusätzlich `SCOUTREF_EVAL_LIVE_ENABLED=1`, einen
  Operator-Token, einen Idempotenzschlüssel und eine explizite Bestätigung.
- Kuratierte Kandidaten, CRM-Schreiben und Outreach sind im Vergleich aus.
- Unterschiedliche URLs zählen nur dann als getrennte Evidenz, wenn Domain,
  Quellenfamilie und Inhaltsfingerabdruck keine Spiegelung oder Syndizierung
  erkennen lassen.
- Budgeterschöpfung, Modellabweichung oder technische Fehler führen zu einem
  dokumentierten, nicht positiv verwertbaren Lauf.
- Roh- und Zwischenartefakte werden als `scout_raw`, `scout_normalized`,
  `verifier_raw`, `verifier_merged` und `final_policy_output` beziehungsweise
  als entsprechende SAS-Stufen mit stabilen Hashes archiviert. So bleibt die
  Änderung vor und nach der Prüfung rekonstruierbar.
- Nicht ableitbare Zufallscodes verblinden die Arme. Die Zuordnung bleibt
  serverseitig gesperrt, bis finale Annotationen durch ihren SHA-256-Wert
  unveränderlich gebunden wurden.

## Modulgrenzen

| Bereich | Verantwortliche Module |
|---|---|
| Aufgabenvertrag | `experiment_protocol.py` |
| Ressourcen | `resource_budget.py`, `core.py` |
| Modellrollen | `agents.py`, `baselines.py` |
| Orchestrierung | `pipeline.py`, `compare_architectures.py` |
| Evidenz | `evidence_resolver.py`, `evidence_matrix.py`, `entity_verifier.py` |
| Experiment-API | `server.py` |
| Benutzeroberfläche | `static/` |
| Integrationen | `crm_pipedrive.py`, `outreach.py`, `outlook_mac.py` |
| Offlineprüfungen | `tests/`, `scripts/run_contract_tests.py` |
