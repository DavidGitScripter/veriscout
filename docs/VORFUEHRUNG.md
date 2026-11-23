# VeriScout vorführen und selbst testen

Diese Anleitung ist für die Verteidigung geschrieben. Alle Schritte bis auf Schritt 6 kosten nichts und brauchen kein Internet außer für die Quellenabrufe.

## 0. Was der Prototyp zeigt (in einem Satz)

Zwei Architekturen bekommen denselben Suchauftrag, dasselbe Modell und dasselbe Budget: **SAS-2** (ein Agent recherchiert und prüft sich danach selbst) und **MAS** (eine Scoutingrolle recherchiert, eine getrennte Verifikationsrolle prüft ohne deren Begründung und Quellen). Danach entscheidet derselbe feste Regelkern, ob ein Startup-Unternehmen empfohlen wird.

## 1. Tests laufen lassen (1 Minute)

```bash
cd "$HOME/Documents/New project/prototype_push"
.venv/bin/python -m pytest -q
```

Erwartung: alle Tests bestanden. Zum Zeigen eignet sich besonders:

```bash
.venv/bin/python -m pytest -v tests/test_p0_end_to_end_comparison.py
```

Was du dazu sagst: „Der wichtigste Test spielt einen vollständig belegten Fall durch beide Architekturen. Beide kommen zur Empfehlung. Wenn die Prüfstufe die Aussagen nicht belegt, kommt keine Architektur zur Empfehlung, und bei einem Widerspruch wird abgelehnt.“

## 2. Prototyp ohne Kosten starten

```bash
env OPENAI_API_KEY="" ANTHROPIC_API_KEY="" SCOUTREF_EVAL_LIVE_ENABLED=0 .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
```

Dann im Browser `http://127.0.0.1:8000` öffnen. Oben rechts steht „Ohne Live-Läufe“. Damit ist ausgeschlossen, dass versehentlich Kosten entstehen.

## 3. Bereich 1 · Suchauftrag

1. Mittelständisches Unternehmen eintragen, z. B. „Max Wild GmbH“.
2. Suchauftrag eintragen, z. B. „Suche ein reales B2B-Startup, dessen Produkt die Aufbereitung mineralischer Baustoffe von Max Wild effizienter machen könnte.“
3. Rechts erscheint der **Auftrag an beide Architekturen** mit Auftrags-Hash. Erklärung: „Das ist exakt der Text, den beide Architekturen bekommen. Der Hash beweist, dass er identisch ist.“
4. „Fallblatt für die Bewertung“ aufklappen. Erklärung: „Hier stehen öffentliche Angaben zum Unternehmen für die Bewertenden. Das Fallblatt geht nie an SAS-2 oder MAS. Es wird mit Fingerabdruck in der Laufdatei gespeichert, und ein Test prüft, dass es in keinem Prompt landet.“
5. „Versuchsbedingungen“ aufklappen: Budget je Architektur und die Aufteilung auf Recherche und Prüfung zeigen. Erklärung: „Jede Stufe hat ihre fest reservierte Hälfte. Die erste Stufe kann der zweiten nichts wegnehmen.“
6. Unter „Lauf starten“ zeigt die Checkliste, warum gerade kein bezahlter Lauf möglich ist. Das ist gewollt (RB4).

## 4. Bereich 2 · Ergebnis eines gespeicherten Laufs

1. Oben „Lauf“ einen gespeicherten echten Lauf auswählen. Öffnen kostet nichts.
2. Links SAS-2, rechts MAS. Je Arm zeigen:
   - **Ergebnisstatus** des Arms und die Zielzustände der Kandidaten (Empfehlung, Ablehnung, Enthaltung, technischer Fehler).
   - **Ressourcen:** Tokens, Websuchen, Quellenabrufe, Kosten, Dauer.
   - **Zweite Stufe:** wie viele Aussagen gestützt, widerlegt oder unbestätigt blieben. Das ist die Messgröße für H3.
   - **Sensitivitätsanalysen:** was passiert wäre mit wortgleichem Abgleich bzw. wenn der Verifier die Quellen des Scouts nutzen dürfte.
3. Einen Kandidaten öffnen: die neun Dimensionen der Evidenzmatrix, darunter „Aussagen und Belege“ mit wörtlichem Auszug und Link zur Quelle. Erklärung: „Jede Aussage ist an eine abrufbare Quelle gebunden. Der Auszug wurde vom System im abgerufenen Dokument wiedergefunden.“
4. Bei einer Empfehlung: der Kasten „Menschliche Freigabe“. Erklärung: „CRM Pipedrive und E-Mail-Entwurf sind sichtbar, aber im Vergleichslauf gesperrt. Eine Empfehlung löst nie automatisch etwas aus.“

## 5. Bereich 3 · Bewertung und Auswertung

Zum Vorführen „Probeläufe (Schulungsbogen)“ wählen; das kostet nichts und berührt keine Studiendaten.

1. **Bewertungsbogen erstellen.** Es entstehen drei Dateien:
   - der **Bewertungsbogen** (HTML) für die Bewertenden: läuft offline im Browser, zeigt je Startup das Fallblatt, die Aussagen und die Belege. Kein Systemurteil, kein Hinweis auf SAS-2 oder MAS, nur Quellen, auf die sich eine Aussage stützt. Dasselbe Startup zur selben Aufgabe erscheint einmal, auch wenn es in mehreren Läufen vorkommt;
   - der **Bewertungsschlüssel** (bleibt bei der Versuchsleitung, ordnet die Einheiten den Läufen zu, ohne Architektur);
   - die **Zuordnungsdatei** (getrennt aufbewahren, erst verwenden, wenn alle Urteile eingelesen sind).
2. Den Bogen öffnen und zeigen: Kürzel wählen, je Fall die Fragen F1 bis F5. F1 bis F4 mit ja, nein oder nicht beurteilbar, F5 nur mit ja oder nein, jeweils mit Entscheidungshilfe aus dem Kodierleitfaden.
3. **Bewertungen einlesen:** Schlüssel und die exportierten Bewertungen aller Bewertenden laden. Jeder Fall hat drei unabhängige Urteile, es gibt keine Einigung. Es entscheidet die Mehrheit der festen Urteile (Treffer oder kein Treffer), „nicht beurteilbar“ zählt nicht mit, 1:1 gilt als strittig. Angezeigt werden Krippendorffs Alpha je Frage und die paarweise Übereinstimmung.
4. **Auswertung:** Erfolgsrate je Architektur, Precision, das bayesianische Intervall der Differenz MAS minus SAS-2, H1 bis H3, die Sensitivitätsanalysen (auch „strittige Fälle als Treffer“), die Ergebnisse je Modell und je Unternehmensgruppe, die Stabilität über Wiederholungen und die Übereinstimmung der Bewertenden.

## 6. Einen echten Lauf starten (kostet Geld)

1. Einen eventuell noch laufenden alten Server beenden (im jeweiligen Terminal `Ctrl+C`).
2. Live-Server starten, mit GPT oder Claude:

```bash
.venv/bin/python scripts/start_live_review.py
```

```bash
.venv/bin/python scripts/start_live_review.py --model claude-sonnet-5-5
```

3. Das Terminal zeigt die Adresse (`http://127.0.0.1:8000`) und den **Bedienerschlüssel**. Oben rechts in der Oberfläche steht jetzt „Live-Läufe freigegeben“.
4. In Bereich 1 Unternehmen, Auftragsart und Suchauftrag eintragen, den Bedienerschlüssel einfügen, „Kostenpflichtigen Lauf freigeben“ anhaken, „Vergleich starten“.
5. Ein Paar (SAS-2 und MAS) dauert etwa 2 bis 4 Minuten und kostet mit gpt-6.1-sol im Mittel etwa 0,50 USD, höchstens 1,50 USD. Danach öffnet sich Bereich 2 automatisch.

Die lokale Kostengrenze der Sitzung liegt bei 10 USD (`--budget-usd 5` setzt sie niedriger). Sie ist eine Schätzung, kein Abrechnungslimit beim Anbieter.

Für mehrere Probeläufe ohne Oberfläche:

```bash
.venv/bin/python scripts/run_api_probe.py --pairs 5
.venv/bin/python scripts/run_api_probe.py --pairs 5 --confirm-paid
```

Der erste Befehl zeigt nur den Plan und die Höchstkosten, der zweite führt aus.

**Anderes Modell (Replikation mit Claude):** Für SAS-2, Scouting und Verifikation gilt immer dieselbe Modellkennung. Mit Claude Sonnet 5.5:

```bash
.venv/bin/python scripts/run_api_probe.py --model claude-sonnet-5-5 --pairs 2 --confirm-paid
```

In der Oberfläche: den Server mit `SCOUTREF_OPENAI_MODEL=claude-sonnet-5-5` starten. Der Schlüssel steht als `ANTHROPIC_API_KEY` in `.env`.

**Gespeicherte Läufe neu bewerten (ohne API-Kosten):** Ändert sich der Regelkern, lassen sich dieselben Modellantworten erneut prüfen. Das Original bleibt erhalten, die Neubewertung wird als eigener Lauf mit dem Zusatz „-neubewertet“ gespeichert:

```bash
.venv/bin/python scripts/reevaluate_run.py artifacts/runs/run-probe-XXXX.json
```

## 7. Bereich 4 · Transferprüfung

Teilnehmercode eintragen, „Prüfung beginnen“, Aufgaben nacheinander starten und beobachten. Die Zeit je Aufgabe wird mitgeschrieben. Danach füllt die teilnehmende Person den Fragebogen aus (System Usability Scale und Fragen zum Referenzmodell), am Ende „Protokoll exportieren“. Es entstehen keine API-Kosten. Wer auch bewertet, macht die Transferprüfung erst nach der Bewertung.

## 7a. Hauptstudie

Ablauf, Kosten und Befehle stehen in `docs/HAUPTSTUDIE_ABLAUF.md`.

## 8. Typische Fragen in der Verteidigung

- **Ist der Vergleich fair?** Gleicher Auftrag (Hash), gleiches Modell (vom Runner erzwungen), zwei Aufrufe je Arm, gleiches Budget mit gleicher Stufenaufteilung, gleicher Prüfvertrag, gleicher Regelkern, wechselnde Reihenfolge AB/BA. Bewusster Unterschied: SAS-2 darf eigene Quellen weiterverwenden, MAS muss neu belegen. Die Sensitivitätsanalyse zeigt, wie viel dieser Unterschied ausmacht.
- **Warum zählt eine Enthaltung als 0?** Gemessen wird der gelieferte Suchnutzen. Eine berechtigte Enthaltung ist kein Fehler, liefert aber keinen Treffer.
- **Warum bayesianisch?** Bei wenigen Aufgaben unterschätzen übliche Intervalle die Unsicherheit. Das Verfahren behandelt Wiederholungen einer Aufgabe als zusammengehörig.
- **Was beweisen die Tests?** Dass die Regeln wie beschrieben greifen. Über die Trefferqualität sagen sie nichts; dafür gibt es die verblindete Bewertung.
