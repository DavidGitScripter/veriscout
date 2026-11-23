# Hauptstudie Variante A: Ablauf Schritt für Schritt

> Stand 06.11.2026: Laufskript abgesichert (siehe `docs/PRUEFUNG_VOR_HAUPTLAUF_2026-11-06.md`). Der Laufplan (A′, B oder C aus der Umplanung vom 28.10.) ist noch offen; die Befehle für C stehen in Abschnitt 4. Abschnitt 6 (Bewertung) beschreibt noch das alte Verfahren mit Einigung und wird nach der Entscheidung zur Evaluation ersetzt.

Design: 30 Aufgaben (30 verschiedene mittelständische Unternehmen), jede einmal mit **gpt-6.1-sol** und einmal mit **claude-sonnet-5-5**, dazu 10 zufällig gezogene Aufgaben ein zweites Mal mit gpt-6.1-sol für die Stabilität. Zusammen 70 Paare (140 Architekturläufe). Erwartete Kosten etwa 35 bis 45 USD, harter Stopp bei 90 USD.

Bezahlte Schritte sind mit 💶 markiert. Alle anderen kosten nichts.

## 1. Unternehmen auswählen

- `studie/AUSWAHLREGEL.md` ausfüllen und datieren, **bevor** Unternehmen gezogen werden.
- Gruppe `gt_hub`: alle Partner, die nicht im Entwicklungskorpus sind. Gruppe `extern`: auffüllen bis 30, gleiche Branchen, gezogen nach der Regel.
- Aufgabenliste anlegen: `studie/aufgaben_vorlage.csv` nach `studie/aufgaben.csv` kopieren. Je Unternehmen eine Zeile mit `task_key`, `gruppe`, `unternehmen`, `website`, `branche`, `suchfeld`. Alle Aufgaben laufen als PUSH (Kap. 7.3.2; Budgets sind an PUSH kalibriert). `search_mode` leer lassen.
- Das `suchfeld` wird im PUSH-Hauptlauf nicht an die Systeme gegeben; es dient nur als Angabe im Fallblatt.

## 2. Fallblätter schreiben

- `studie/fallblaetter_vorlage.json` nach `studie/fallblaetter.json` kopieren, je `task_key` ein Eintrag.
- Nur öffentliche Quellen, kein Wissen aus der Scouting-Tätigkeit. `public_sources_only` auf `true` setzen.
- Die Fallblätter gehen nie an SAS-2 oder MAS. Sie werden mit Fingerabdruck in den Plan übernommen und später nur den Bewertenden gezeigt.

## 3. Eingangsprüfung des zweiten Modells 💶 (etwa 2 USD, höchstens 4,50 USD)

Hinweis 06.11.: Mit dem aktuellen Prompt (v10) und dem aktuellen Budget gab es noch keinen einzigen Live-Lauf, weder mit Sol noch mit Sonnet. Die letzten Sol-Läufe stammen vom 19./20.10. (ältere Fassung), die Sonnet-Läufe vom 16.10. (Prompt v4/v5, damals 120.000 Eingabetokens). Die Eingangsprüfung ist deshalb zugleich die erste Generalprobe des eingefrorenen Stands. Empfohlen: dieselbe Prüfung auch mit Sol (`--model gpt-6.1-sol`), zusammen etwa 4 bis 9 USD.

```bash
.venv/bin/python scripts/run_api_probe.py --model claude-sonnet-5-5 --pairs 3 --entry-check --confirm-paid
```

Das Kriterium steht vorab fest und gilt für jedes Modell gleich: kein Arm scheitert technisch, mindestens eine Quelle mit eigener Quellenangabe des Anbieters wird abgerufen und ihr Auszug gefunden, mindestens ein Arm liefert einen Kandidaten. Das Ergebnis (`"passed": true/false`) wird in der Arbeit berichtet. Fällt Sonnet durch, wird das dokumentiert und die Studie mit dem Ersatzplan durchgeführt (siehe Abschnitt 8).

## 4. Plan einfrieren

```bash
.venv/bin/python scripts/run_study.py plan --tasks studie/aufgaben.csv \
    --case-sheets studie/fallblaetter.json --seed "<frei gewählter Text, notieren>" \
    --out studie/plan.json
```

Der Plan enthält Aufgaben, Suchaufträge, Fallblätter, die zufällige Zuteilung (PUSH/PULL, Reihenfolge SAS-2/MAS, Stabilitätsaufgaben), Promptfassung, Budgetprofil und einen Fingerabdruck des Programmcodes. Er lässt sich nicht überschreiben. Wird danach Code, Prompt oder Budget geändert, verweigert das Skript den Lauf; dann braucht es einen neuen Plan.

`plan_sha256` aus der Ausgabe in die Arbeit übernehmen.

Zusätzlich seit 06.11.:
- `--protocol-file <Bewertungsprotokoll.md>` nimmt den SHA-256 des Bewertungsprotokolls (Fragen, Trefferregel, Strittig-Regel, Ziehung) in den Plan auf. Das Protokoll muss vor dem Einfrieren feststehen.
- Der Plan friert alle wirksamen Laufzeitwerte ein (Budget, Auszugsabgleich, Reasoning-Stufe, Schwelle, Preise, Zeitgrenzen). Ändert danach ein Eintrag in `.env` einen davon, verweigert `run` den Start und nennt den Wert.
- Weicht das Budget vom Profil der Arbeit ab (200.000 Eingabe, 16.000 Ausgabe, 12 Websuchen, 24 Abrufe, 0,75 USD je Arm, 3 Kandidaten, Reasoning „low“), legt `plan` keinen Plan an.
- Laufplan (Stand 12.11.2026): 15 Unternehmen × 2 Modelle × 2 Läufe = 60 Paare, `--replicates 2 --stability 0`. Die beiden Läufe einer Aufgabe mit demselben Modell bekommen entgegengesetzte Reihenfolgen (einmal SAS-2 zuerst, einmal MAS zuerst).
- Obergrenzen je Anbieter (Pflicht, werden mit eingefroren): `--max-usd-per-model gpt-6.1-sol=28,claude-sonnet-5-5=26`; Gesamtwert 54 USD. Höchstkosten je Paar 2,00 USD (inkl. Nachrecherche).
- Einfrieren:
  ```bash
  SSL_CERT_FILE=/etc/ssl/cert.pem ~/.veriscout_venv/bin/python scripts/run_study.py plan --tasks studie/aufgaben.csv --case-sheets studie/fallblaetter.json --seed "<frei gewählter Text, notieren>" --models gpt-6.1-sol,claude-sonnet-5-5 --modes push --replicates 2 --stability 0 --max-usd-per-model gpt-6.1-sol=28,claude-sonnet-5-5=26 --protocol-file studie/BEWERTUNGSPROTOKOLL.md --out studie/plan.json
  ```

## 5. Hauptlauf 💶 (erwartet etwa 48 USD; Obergrenzen Sol 28 USD, Sonnet 26 USD)

Erst den Plan ansehen (kostenlos):

```bash
.venv/bin/python scripts/run_study.py run-all --plan studie/plan.json
```

Dann ausführen:

```bash
.venv/bin/python scripts/run_study.py run-all --plan studie/plan.json --confirm-paid
```

- Reihenfolge: erst alle 30 Paare des ersten Laufs, dann alle 30 des zweiten; innerhalb eines Laufs wechseln die Modelle Paar für Paar (Firmenreihenfolge und Startmodell nach Seed). Ohne `--confirm-paid` zeigt `run-all` nur diese Reihenfolge.
- Vor jedem Paar prüft das Skript je Modell: bisherige Kosten dieses Modells + 2,00 USD Höchstkosten + 0,50 USD Sicherheitsaufschlag dürfen die Obergrenze des Modells nicht übersteigen (ebenso für die Gesamtsumme). Ist ein Modell erschöpft, entfallen nur dessen restliche Paare (Status `budget_stop` mit Liste), das andere läuft weiter. Ein abgebrochenes Paar wird mit 2,00 USD verbucht.
- Den Mac wach halten: den Befehl mit `caffeinate -i` beginnen, Netzteil anschließen, Deckel offen lassen. Bei etwa 3 bis 4 Minuten je Paar dauern 60 bis 70 Paare grob 4 bis 5 Stunden (Schätzung aus den Probeläufen).
  ```bash
  caffeinate -i .venv/bin/python scripts/run_study.py run-all --plan studie/plan.json --confirm-paid
  ```
- Bricht der Lauf ab (Netz, Ruhezustand, Strg+C), denselben Befehl erneut starten. Ein Paar, das ohne Ergebnis abgebrochen ist, wird einmal vollständig neu gestartet (beide Arme). Der Abbruch bleibt mit 2,00 USD im Kostenbuch und wird als Protokollabweichung berichtet. Ein zweiter Abbruch desselben Paars wird nicht mehr wiederholt. Technische Fehler innerhalb eines abgeschlossenen Paars werden nie wiederholt; sie zählen als Erfolgswert 0.
- Meldet das Skript „Es laeuft bereits ein Studienlauf“, obwohl keiner läuft (etwa nach einem Absturz), die Datei `studie/.lauf-<study_id>.lock` löschen und neu starten.
- Kurze Überlastungen des Anbieters (HTTP 429/5xx, Verbindungsabbruch vor einer Antwort) wiederholt das Programm bei beiden Anbietern höchstens zweimal. Zeitüberschreitungen werden nicht wiederholt.
- Die Kosten im Kostenbuch sind eine Schätzung aus Tokens und Preistabelle. Nach der Eingangsprüfung die Abrechnung in den Konsolen von OpenAI und Anthropic mit dem Kostenbuch vergleichen.
- Stand jederzeit: `.venv/bin/python scripts/run_study.py status --plan studie/plan.json`
- Jedes Paar wird als Studienlauf in `artifacts/runs/` gespeichert und erscheint in der Oberfläche unter „Studienläufe“.

## 6. Bewertung

1. Einarbeitung ohne Treffen: Jede Person arbeitet allein. Sie liest die Kurzanleitung (`docs/KODIERLEITFADEN.md`) und bearbeitet zwei Übungsfälle mit Musterlösung allein. Erst danach bewertet sie ihre 12 Fälle. Die Übungsurteile zählen nicht.
2. In Bereich 3 „Alle Studienläufe“ wählen, „Bewertungsbogen erstellen“. Die Zuteilung ist fest: 10 Bewertende mit je 12 Fällen, jeder Fall geht an drei Personen. Jede Person erhält den **Bewertungsbogen** mit ihrem Kürzel; nach Wahl des Kürzels zeigt er nur die ihr zugeteilten Fälle. **Bewertungsschlüssel** und **Zuordnungsdatei** behältst du; die Zuordnungsdatei erst öffnen, wenn alle Urteile eingelesen sind.
3. Alle bewerten unabhängig, ohne Absprache und ohne KI-Chatbots, und schicken ihre exportierte Datei zurück. Es gibt keine Einigung.
4. „Bewertungen einlesen“: Schlüssel und die Dateien aller Bewertenden laden. Jeder Fall hat drei unabhängige Urteile; es gibt keine Einigung. Es entscheidet die Mehrheit der festen Urteile (Treffer oder kein Treffer), „nicht beurteilbar“ zählt nicht mit; 1:1 gilt als strittig. Krippendorffs Alpha und die paarweise Übereinstimmung werden mitberechnet.
5. „Auswertung“: eingelesene Urteile und Zuordnungsdatei. Alle Zahlen und die Nachweisliste der Studienläufe in den Anhang.

## 7. Transferprüfung

Nach der Bewertung, mit allen 10 Bewertenden (Kürzel wie im Bewertungsbogen), im kostenlosen Modus (Bereich 4). Jede Person füllt den Transferfragebogen (SUS) aus. Protokoll und Fragebögen exportieren.

## 8. Wenn etwas schiefgeht

- **Sonnet besteht die Eingangsprüfung nicht:** Plan mit `--models gpt-6.1-sol --replicates 2 --stability 0` anlegen (30 Aufgaben × 2 Läufe mit Sol, Variante B). Das wird in der Arbeit als vorab festgelegter Ersatzplan berichtet.
- **Kosten laufen höher als erwartet:** Der Stopp bei 90 USD greift zuerst bei den Stabilitätswiederholungen. Der Kernvergleich ist dann vollständig.
- **Ein Unternehmen erweist sich nach dem Einfrieren als ungeeignet:** Es bleibt im Plan und wird ausgewertet. Ausschlüsse nach dem Einfrieren wären eine nachträgliche Auswahl.
