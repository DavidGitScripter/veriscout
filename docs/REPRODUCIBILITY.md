# Reproduzierbarer Studienstand

## Offline-Verträge

```bash
python -m compileall -q .
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --check static/app.js
```

Diese Prüfungen belegen Schnittstellen und Sicherheitsregeln, nicht die
qualitative Überlegenheit einer Architektur.

## Konfirmatorischer Lauf

Vor dem ersten Holdout-Lauf werden unveränderlich festgehalten:

- Quell- und Aufgabenmanifest einschließlich manueller Prüfdokumentation,
- archivierter Inhalts-Hash jeder Ausgangsquelle,
- Code-, Instanz-, Prompt-, Budget- und Memory-Hash,
- angeforderte und gelieferte Modell-ID, Reasoning-Level, API-Vertrag,
  Payload-Schema, Modellparameter und Preisstand samt Hash,
- Hash jedes Systemprompts, des tatsächlich gerenderten Nutzerprompts und der
  gesendeten Request-Payload,
- Websuchkonfiguration, Rubrikversion und Schwelle 61 als notwendige, nicht
  hinreichende Bedingung,
- Python-, Betriebssystem-, Container- und Abhängigkeitsfingerabdruck,
- Idempotenzschlüssel und randomisierte Ausführungsreihenfolge,
- Annotationsrubrik, Primärmetrik, Ausschlüsse und Fehlerregeln.

Das Holdout-Manifest wird beim Laden neu gehasht. Eine selektive Teilmenge der
eingefrorenen Replikationen oder Memory-Zustände ist unzulässig. Execution-IDs
werden vor dem Modellaufruf prozessübergreifend gesperrt und nach jedem Ausgang
-- auch einem technischen Fehler -- mit Ergebnisstatus und Ergebnishash als
verbraucht finalisiert.

Das persistente Studienledger reserviert das maximale Paarbudget vor dem Lauf.
Es prüft Schema, Währung und eingefrorenes Gesamtlimit; abgeschlossene
Reservierungen können nicht erneut verwendet werden. Tatsächliche Mehrkosten
gegenüber der Reservierung werden vollständig verbucht und als Verletzung
ausgewiesen, nicht auf den reservierten Betrag gekappt.

Die API gibt zunächst ausschließlich das Blindpaket aus. Zufällige Arm-Codes
sind nicht aus Lauf-ID oder Architektur ableitbar. Erst wenn die finale
Annotationsdatei durch ihren SHA-256-Wert gebunden wurde, gibt der geschützte
Entblindungsendpunkt Zuordnung und interne Laufdaten frei.

Je Arm werden Roh- und Stufenartefakte vor und nach Self-Review beziehungsweise
Verifikation sowie das finale Policy-Ergebnis getrennt gespeichert und
gehasht. Damit lassen sich Kandidatenrang, Claims, Quellen und die Änderung des
Prüfschritts rekonstruieren.

## Quellpaket

`python scripts/build_source_release.py` erstellt aus einer Positivliste ein
ZIP mit `MANIFEST.SHA256`. Lokale `.env`, Laufzeitdaten, private Altstände und
historische Berichte können dadurch nicht durch bloßes Ziehen des
Arbeitsordners in die Freigabe gelangen.
