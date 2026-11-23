# Prüfung des Prototyps vor dem bezahlten Hauptlauf (06.11.2026)

Geprüfter Stand: Ordner `prototype_push` auf Davids Mac, letzte Änderung 21.10.2026, 194 Tests grün. Es wurde kein kostenpflichtiger Lauf gestartet. Alle Tests liefen offline in einer Cloud-Kopie.

## Wie oft wirklich geprüft wurde

Sechs Prüfdurchgänge, nicht fünfzig. Ab dem fünften Durchgang kamen keine neuen Befunde mehr, nur noch Kleinigkeiten an meinen eigenen Änderungen. Weitere Durchgänge ohne neue Daten hätten nichts geändert. Was sich ohne bezahlten Lauf nicht prüfen lässt, steht unten unter „Offen“.

1. Laufskript `scripts/run_study.py`: Plan, Fingerabdruck, Kostenstopp, Wiederaufnahme, Kostenbuch.
2. Fairness SAS-2 gegen MAS: gleicher Erstauftrag, gleiche Budgetaufteilung, gleiche Quellenprüfung, Anbieteradapter OpenAI und Anthropic.
3. Auswertung und Bewertungsmaterial: Statusregeln, ITT-Auswertung, Bewertungsbogen, Abgleich mit Kapitel 7.
4. Transfermodus auf einem frischen Verzeichnis ohne API-Schlüssel; Laufplan C als Trockenplan (15 × 2 × 2).
5. Gegenlesen aller eigenen Änderungen, neue Tests.
6. Abschlussdurchgang über Restrisiken (Sperrdatei, doppelte Laufdateien, Verblindung, Zeitabstand der Modellphasen).

## Behoben (mit Tests, jetzt 204 von 204 grün)

| Nr. | Befund | Folge ohne Korrektur | Korrektur |
|---|---|---|---|
| 1 | Der Code-Fingerabdruck im Plan erfasste 12 von 22 geladenen Modulen. Es fehlten unter anderem `quality_gates.py` (Freigaberegeln), `entity_verifier.py` (Betriebsstatus) und `evidence_subjects.py`. | Eine Änderung an den Entscheidungsregeln nach dem Einfrieren wäre nicht bemerkt worden; der Plan-Fingerabdruck in der Arbeit hätte weniger belegt als behauptet. | Alle geladenen Module plus Daten- und Konfigurationsdateien. Ein Test startet einen frischen Prozess und schlägt fehl, wenn künftig ein Modul fehlt. |
| 2 | Der Plan prüfte nur Bezeichner („Budgetprofil“), nicht die wirksamen Werte. Budget, Auszugsabgleich, Reasoning-Stufe und Schwelle lassen sich über `.env` ändern. | Ein alter `.env`-Eintrag (etwa 160.000 Eingabetokens vom 16.10.) hätte den Lauf still mit anderen Werten als in der Arbeit beschrieben ausgeführt. | Der Plan friert alle wirksamen Werte ein; `run` bricht bei Abweichung ab und nennt den Wert. `plan` verweigert ein Budget, das vom Profil der Arbeit abweicht. |
| 3 | Ein Abbruch mitten im Paar (Netz, Ruhezustand, Strg+C) ließ das Paar dauerhaft „begonnen“ stehen; es wurde nie nachgeholt. | Fehlende Paare, also genau die „still verworfenen Läufe“, die die Arbeit ausschließen will. Bei 4 bis 5 Stunden Laufzeit auf einem Laptop wahrscheinlich. | Ein ergebnisloses Paar wird einmal vollständig neu gestartet; der Abbruch bleibt mit 1,50 USD verbucht und im Kostenbuch protokolliert. Technische Fehler in abgeschlossenen Paaren werden weiterhin nie wiederholt (Erfolgswert 0). Das Ergebnis wird auch dann gespeichert, wenn die Aufbereitung der Laufdatei scheitert. |
| 4 | Ein Arm mit einer vollständig geprüften Empfehlung galt als „nicht vollständig geprüft“, sobald Quellen eines anderen Kandidaten wegen des Abrufbudgets ungeprüft blieben. Seit dem Unterseitenabruf (bis zu 3 Unterseiten je Quelle) wird das 24er-Budget schneller verbraucht. | Ein echter Treffer hätte für H1 als 0 gezählt. Kapitel 7 sagt dagegen: Erfolg ist ein geliefertes, vollständig geprüftes, qualifiziertes Ergebnis. Code und Arbeit widersprachen sich. | Eine Empfehlung bleibt gültig; der Arm erhält die Protokollabweichung `resolver_budget_partial`. Die alte, strengere Lesart rechnet der Auswerter als neue Sensitivitätsanalyse `strict_budget` mit. **Bitte bestätigen (siehe unten).** |
| 5 | Der OpenAI-Pfad wiederholte bei Überlastung (HTTP 429/5xx) nie, der Anthropic-Pfad zweimal (Voreinstellung des SDK). | Kurzzeitige Überlastungen hätten bei Sol mehr technische Fehler (Erfolgswert 0) erzeugt als bei Sonnet. | Beide Anbieter höchstens zwei Wiederholungen bei 429/5xx und Verbindungsabbruch; keine Wiederholung bei Zeitüberschreitung, weil die Anfrage dann schon berechnet sein kann. Zahl der Wiederholungen wird je Aufruf protokolliert. |
| 6 | Für jede gefundene Quelle speicherte der Prototyp nur Prüfsummen, nicht die Fundstelle. | Ändert sich eine Seite zwischen Lauf und Bewertung, lässt sich nicht mehr zeigen, was der Quellenabgleich gesehen hat; menschliches Urteil und technische Prüfung wären nicht sauber vergleichbar. | Je bestätigtem Auszug ein Ausschnitt von höchstens 600 Zeichen der Fundstelle (`matched_context`). |
| 7 | Bei zwei Läufen je Aufgabe und Modell (Laufplan C) war die Reihenfolge SAS-2/MAS nur über alle Aufgaben ausgeglichen; bei 18 von 30 Aufgaben liefen beide Wiederholungen in derselben Reihenfolge. | Ein Reihenfolgeeffekt hätte sich nicht je Aufgabe aufgehoben. | Bei mehreren Läufen je Aufgabe abwechselnd AB/BA mit zufälligem Start. |
| 8 | Wunsch aus dem Thread zur Labeling-Kritik: Das Bewertungsprotokoll muss vor dem Lauf feststehen. | Ohne Fingerabdruck wäre nicht belegbar, dass Fragen und Trefferregel vor den Ergebnissen festgelegt wurden. | `plan --protocol-file <Datei>` nimmt den SHA-256 des Protokolls in den Plan auf. |
| 9 | Kleinigkeiten: Platzhalter „noch keine“ in der Laufliste erzeugte Fehlanfragen (im Serverprotokoll sichtbar); Quellpaket hieß noch `venturescout`; `run` verlangte einen API-Schlüssel, auch wenn nichts mehr offen war; `AUSWAHLREGEL.md` sprach noch von PUSH/PULL je zur Hälfte. | Kosmetisch, bzw. Widerspruch zur Festlegung „nur PUSH“. | Behoben. |

Bereits in Ordnung (geprüft, nichts geändert): gleicher Erstauftrag für SAS-2 und MAS (bytegleich), gleiche Budgetaufteilung je Stufe, gleiche gemeinsame Quellenprüfung, kein zweiter Aufruf bei leerem Erstergebnis in beiden Armen, technische Fehler zählen als 0 und werden nicht verworfen, harter Stopp bei 90 USD (bei Plan C liegen die Höchstkosten von 60 × 1,50 USD genau auf der Grenze, alle Paare können laufen), Modell innerhalb eines Paars fest, Fallblatt erreicht die Systeme nie, `.env` überschreibt keine ausdrücklich gesetzte Modellwahl. Betriebsstatus je Kandidat und Abgleichergebnis je Quelle und Aussage (gefunden ja/nein, wortgleich/unscharf/Unterseite) werden bereits gespeichert.

## Transfermodus auf fremdem Rechner

Getestet in einer frischen Linux-Umgebung mit Python 3.13: Quellpaket entpacken, zwei Pakete installieren, starten. Dauer etwa 12 bis 30 Sekunden bei schnellem Netz, Startseite und Bereich „Transferprüfung“ laden ohne Fehler in einem echten Browser. Kein API-Schlüssel nötig. Anleitung für macOS und Windows: `docs/TRANSFER_START_FREMDER_RECHNER.md`. Nicht getestet: macOS und Windows selbst. Der unsicherste Schritt ist, ob Python auf dem Rechner der Person schon installiert ist; bei einer Doktorandin bzw. einem Doktoranden in Computer Vision und einer Person im KI-Engineering ist das wahrscheinlich, aber nicht geprüft.

## Offen und ohne bezahlten Lauf nicht prüfbar

1. **Es gab noch keinen einzigen Live-Lauf mit dem aktuellen Stand.** Sol lief zuletzt am 19./20.10. mit einer älteren Promptfassung (3 Paare, alle Enthaltung), Sonnet am 16.10. mit Prompt v4/v5 und damals 120.000 Eingabetokens (beide Arme überschritten das Limit). Mit Prompt v10 und dem Budget vom 19.10. ist keines der beiden Modelle gelaufen. Ob der Anthropic-Pfad mit dem Werkzeug `web_search_20260209` und dem Parameter `effort` beim aktuellen Modell fehlerfrei läuft, kann ich ohne Aufruf nicht bestätigen.
2. **Bodeneffekt.** In allen bisherigen Live-Läufen gab es null Empfehlungen. Bleibt das so, enden H1 und H2 bei beiden Armen nahe null. Das ist ein auswertbares Ergebnis, aber kein Wirksamkeitsnachweis.
3. **Kosten.** Das Kostenbuch schätzt aus Tokens und der Preistabelle (Sol und Sonnet je 2/10 USD pro Mio. Tokens, Websuche 10 USD je 1.000; Preisstand 16.10.). Die tatsächliche Abrechnung kann abweichen. Bisher im Prototyp verbucht: ungefähr 5 bis 6 USD. Ob 90 USD unter 100 EUR bleiben, hängt vom Wechselkurs ab, den ich nicht geprüft habe.
4. **Erwartungsrahmung im Auftrag (Hinweis Liu 2026).** Die PUSH-Vorlage lautet „Suche ein reales B2B-Startup, dessen Produkt … machen könnte“. Sie enthält keine Vorab-Behauptung wie im Versuch von Liu („Prior research indicates …“), setzt aber implizit voraus, dass es ein solches Startup gibt. Die Systemrolle erlaubt ausdrücklich ein leeres Ergebnis („Fülle NIEMALS auf … liefere ein leeres Array“), und die Empfehlung trifft eine feste Regel außerhalb des Modells. Ich habe die Vorlage nicht geändert, weil die Wirkung für beide Arme gleich ist und jede Promptänderung eine neue Generalprobe braucht. Optional wäre der Zusatz „Ob ein solches Startup existiert, ist offen; ein leeres Ergebnis ist zulässig.“
5. **Bewertungsmaterial.** Bewertungsbogen und Auswerter bilden noch das alte Verfahren ab (beide bewerten alles, Einigungsgespräch). Die Umplanung vom 28.10. (Karten je Unternehmen, 6 gemeinsame, keine Einigung) ist nicht umgesetzt. Das wird erst nach dem Lauf gebraucht und hängt an der Entscheidung zur Evaluation (Thread zur Labeling-Kritik).

## Empfohlene Reihenfolge

1. Entscheidungen von David: Laufplan (A′, B oder C) und Punkt 4 der Tabelle.
2. Bewertungsprotokoll fertig (Thread zur Labeling-Kritik), Fallblätter und Aufgabenliste fertig.
3. Generalprobe = Eingangsprüfung mit beiden Modellen (`run_api_probe.py --entry-check`, je 3 Paare auf den Entwicklungsunternehmen, zusammen ungefähr 4 bis 9 USD). Danach Konsolenabrechnung mit dem Kostenbuch vergleichen.
4. Erst wenn beide bestehen: Plan einfrieren mit `--protocol-file`, dann `caffeinate -i … run-all --confirm-paid`.
