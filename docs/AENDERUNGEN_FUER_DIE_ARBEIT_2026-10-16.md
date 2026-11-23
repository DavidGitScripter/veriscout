# Stellen in der Masterarbeit, die wegen des Prototypstands vom 16.10.2026 anzupassen sind

Bezug: `masterarbeit/final/main.tex` (Stand 15.10.2026, 106 Seiten). Diese Liste ändert die Arbeit nicht selbst. Sie beschreibt, was der Thesis-Thread übernehmen sollte. Alle Angaben sind am Code geprüft (Ordner `prototype_push`, Testlauf 16.10.2026).

## 1. Neuer Name des Prototyps

- **VentureScout heißt jetzt EvidenzScout.** Der Name betont die belegte Empfehlung statt eines „Venture“-Bezugs. Er ist im Code an einer Stelle hinterlegt (`Config.PRODUCT_NAME`) und erscheint in Oberfläche, Fußzeile und Konfigurationsschnittstelle.
- Betroffen sind 9 Stellen in `main.tex`: Z. 130 (`\prototypeVersion`), 2203, 2373, 3571, 4154, 4277, 4292, 4321, 4504.
- Vorschlag für `\prototypeVersion`: `EvidenzScout, Stand 2026-10-16 (v18)`.
- Interne Dateiformate behalten aus Kompatibilitätsgründen ihre alten Kennungen (z. B. `venturescout.workspace.v1`). Das muss in der Arbeit nicht erwähnt werden.

## 2. Kapitel 6.4 „Entscheidungslogik“: vier Zielzustände sind jetzt einheitlich umgesetzt

Z. 4116–4123 sagt noch, eine durchgängig einheitliche Abbildung der vier Zielzustände in API, Oberfläche und Speicherung sei „noch nicht erreicht“. Das ist überholt.

Neuer Stand: Jede Entscheidung trägt das Feld `decision_state` mit genau einem der Werte *Empfehlung*, *Ablehnung*, *Enthaltung* oder *technischer Fehler* sowie eine Begründung. Die Zuordnung folgt der Reihenfolge aus Abb. „Entscheidungswege“: zuerst technische Gültigkeit (inklusive erschöpftem Prüfbudget), dann belegter Ausschluss (ausgeschlossener Unternehmenstyp) oder Gegenbeleg (widerlegte Pflichtdimension), dann Evidenzlücke (Enthaltung), zuletzt Empfehlung. Oberfläche, Laufdatei und Zuordnungsdatei verwenden diese vier Zustände. Die alten Bezeichnungen *Pilot*, *beobachten* und *abgelehnt* bleiben nur intern für die Qualitätsbarrieren erhalten und werden nicht mehr angezeigt. Erfüllt damit FA6 auf Code-Ebene (Tests: `test_contradiction_yields_rejection_state`, `test_unsupported_review_yields_abstention_state`).

## 3. Kapitel 6.2 „Begründung der Einzelagenten-Vergleichsbedingung“: Sensitivitätsanalyse ist implementiert

Z. 3858–3863 sagt, die MAS-Variante mit Quellen der Scoutingrolle sei „vorgesehen, aber noch nicht implementiert“. Sie ist jetzt implementiert.

Formulierungsvorschlag: Für jeden MAS-Lauf wird nach dem Primärergebnis eine zweite, kostenfreie Auswertung derselben Modellantworten berechnet. Darin zählt eine Aussage der Scoutingrolle mit ihrer Quelle, wenn die Verifikation sie nicht gestützt, aber auch nicht widerlegt hat. Ein Widerspruch der Verifikation bleibt immer bestehen. Fehlende Dokumente werden mit einem eigenen, gleich großen Abrufkontingent geholt. Modellaufrufe entstehen dabei nicht. Das Primärergebnis bleibt unverändert.

## 4. Kapitel 6.6 „Technische Instanziierung“: drei Ergänzungen

1. **Prüfliste aus atomaren Aussagen.** Die Prüfliste der zweiten Stufe enthält nur die atomaren Aussagen der ersten Stufe. Pauschale Quellen-Kennzeichnungen erzeugen keine zusätzlichen, doppelten Prüfpunkte mehr.
2. **Nicht tragende Quelle.** Ein vollständig belegter positiver Fall bleibt abgeschlossen, auch wenn eine zusätzliche, für die Entscheidung nicht benötigte Quelle technisch nicht abrufbar war (z. B. HTTP 403). Vorher wurde ein solcher Fall als technischer Fehler gezählt.
3. **Gespeicherte Läufe.** Jeder Lauf wird lokal als Laufdatei gespeichert (`artifacts/runs/`). Sie enthält die Prüferansicht, das Blindpaket und die Zuordnungsdatei und lässt sich in der Oberfläche ohne erneute API-Kosten öffnen. Das unterstützt QA3 (Laufdokumentation) und die Vorführung.

Unverändert gültig sind Tabelle `tab:rm-ressourcen`, die Stufenreservierung, der Prüfvertrag und der unscharfe Auszugsabgleich.

## 5. Kapitel 6.4 „Prüfoberfläche“ (QA5) und Kapitel 7.3.3: neue Oberfläche

Die Oberfläche wurde neu aufgebaut und auf vier Bereiche reduziert:

1. **Suchauftrag:** mittelständisches Unternehmen, Suchauftrag, kanonischer Auftrag mit Hash, Versuchsbedingungen, Budget je Arm und je Stufe, Freigabe des Laufs.
2. **Ergebnis:** SAS-2 und MAS nebeneinander, je Arm Ergebnisstatus, Ressourcen, Kennzahlen der zweiten Stufe und Sensitivitätsanalysen. Je Kandidat folgen Zielzustand mit Begründung, die neun Dimensionen der Evidenzmatrix, Aussagen mit wörtlichem Auszug und Quelle sowie offene Fragen. Bei einer Empfehlung ist die menschliche Freigabe für CRM Pipedrive und den E-Mail-Entwurf sichtbar, im Vergleichslauf aber gesperrt (RB4).
3. **Bewertung:** Blindpaket, Bewertungsvorlage für zwei Bewertende, Zuordnungsdatei, Auswertung.
4. **Transferprüfung:** unverändert in Ablauf und Exportformat.

Entfernt wurden Elemente, die die Arbeit nicht braucht (Werbetexte, Themenkatalog, alte Navigation). Die OFFEN-Stellen für Screenshots in 7.3.3 (Z. 5415–5420) können mit der neuen Oberfläche gefüllt werden. Ein Screenshot sollte einen echten Lauf zeigen, keinen Testfall.

## 6. Kapitel 7.3.2: Auswertung, Bayes-Intervall, Grenzen und H3

1. **Bayesianisches Intervall implementiert (Z. 5160–5170).** Verfahren: Bayesianisches Bootstrap über Aufgaben (Dirichlet-Gewichte, Rubin 1981) kombiniert mit einer Beta-Posterior je Aufgabe und Architektur bei Gleichverteilungs-Prior. Wiederholungen einer Aufgabe gehen nur über ihre Erfolgszahl ein und zählen nicht als unabhängige Fälle. Berichtet werden Mittelwert und 95-%-Intervall der Differenz MAS minus SAS-2, P(Δ > 0) und P(Δ > Mindestverbesserung). Das Bootstrap-Intervall bleibt ergänzend. **Neue Quelle nötig:** Rubin, D. B. (1981). The Bayesian Bootstrap. *The Annals of Statistics*, 9(1), 130–134.
   Hinweis: Bowyer et al. stellen eine eigene Python-Bibliothek bereit. Der Prototyp nutzt sie nicht, sondern ein dokumentiertes, gleichwertig bayesianisches Verfahren ohne zusätzliche Abhängigkeit. In der Arbeit sollte nicht stehen, dass deren Bibliothek verwendet wurde.
2. **Grenzen (Z. 5133–5135, OFFEN).** Im Code als Parameter hinterlegt: Nichtunterlegenheitsgrenze für die Precision **−0,10**, Mindestverbesserung der Erfolgsrate **0,10**. Die −0,10 ist der Vorschlag vom 13.10. Die 0,10 für die Mindestverbesserung ist ein Vorschlag dieses Stands und muss von David bestätigt werden, bevor das Protokoll eingefroren wird. Begründungsvorschlag: Eine Verbesserung um 10 Prozentpunkte entspricht einem zusätzlichen qualifizierten Treffer je zehn Aufgaben.
3. **Entscheidungsregeln im Auswerter.** H1 gilt als gestützt, wenn die untere 95-%-Grenze der Differenz über 0 liegt und der Mittelwert mindestens die Mindestverbesserung erreicht. H2 (Nichtunterlegenheit) gilt, wenn die untere 95-%-Grenze der Precision-Differenz über −0,10 liegt.
4. **Was als Erfolg zählt (präzisieren).** q = 1 nur, wenn ein vom System *empfohlener* Kandidat von den Bewertenden als qualifiziert beurteilt wird. Enthaltungen zählen 0, auch wenn ein ausgegebener, aber nicht empfohlener Kandidat qualifiziert wäre. Das entspricht dem Satz „Ein technisch gültiges Leer- oder Enthaltungsergebnis erhält ebenfalls den Erfolgswert null“, macht ihn aber operational eindeutig. Die Bewertenden beurteilen trotzdem alle ausgegebenen Kandidaten, damit die Sensitivitätsanalysen möglich bleiben.
5. **H3 ist messbar.** Je Arm werden erfasst: Kandidaten aus Stufe 1, in Stufe 2 verworfene Kandidaten, Aussagen aus Stufe 1 und deren Urteil in Stufe 2 (gestützt, widerlegt, unbestätigt). Der Auswerter berichtet Verwerfungs-, Widerlegungs- und Nichtbestätigungsquote je Arm.
6. **Sensitivitätsanalysen.** Der Auswerter berechnet alle drei aus Kap. 6/7 automatisch: strikte Websuchregel, wortgleicher Auszugsabgleich, MAS mit Scout-Quellen.
7. **Verblindung.** Im Blindpaket wird die Reihenfolge der beiden Arme jetzt zufällig gemischt, damit die Laufreihenfolge (AB/BA) nicht aus der Position ablesbar ist.

## 7. Kapitel 7.2.1 und Anhang A: Testanzahl und Stand

- `\offlineTestCount` von 160 auf **172**, `\offlineTestDate` auf **16.~Oktober 2026** (Stand nach allen Änderungen dieses Tages, Python 3.13.9).
- Neue Prüfungen: einheitliche Zielzustände inklusive Ablehnung bei Widerspruch und Enthaltung ohne Belege, Sensitivitätsanalyse mit Scout-Quellen, Erfolg nur bei empfohlenem Kandidaten, bayesianisches Intervall bei wenigen und vielen Aufgaben, strikte Websuchregel als Sensitivität, gemischte Armreihenfolge im Blindpaket.
- Anhang A (Artefaktstände): neuer Stand **v18, 16.10.2026**: Name EvidenzScout, neue Oberfläche, vier Zielzustände, Sensitivitätsanalysen, bayesianischer Auswerter, Laufdateien.

## 8. Kapitel 6.6: weitere Änderungen nach den Probeläufen

Die Probeläufe haben vier Schwächen des Quellenabrufs offengelegt. Sie sind behoben und gelten für beide Arme gleich:

1. **Weiterleitungen.** Bisher wurde jede Weiterleitung blockiert (z. B. `/de/start/` → `/de/start`). Jetzt folgt der Resolver höchstens fünf Weiterleitungen, aber nur zu öffentlichen HTTP(S)-Zielen; jedes Ziel wird erneut geprüft, die Endadresse protokolliert.
2. **Einzelne nicht erreichbare Quellen.** Bisher machte eine einzige Quelle mit 403, 404 oder Zeitüberschreitung den ganzen Arm zum technischen Fehler. Jetzt wird sie gezählt und wirkt nur beim betroffenen Kandidaten: Fehlt dadurch ein Pflichtbeleg, folgt eine Enthaltung. Ein Kandidat gilt nur dann als technisch nicht prüfbar, wenn keine einzige seiner Quellen abrufbar war. HTTP-Status und Fehlerart werden je Quelle gespeichert.
3. **Subjektbindung.** Die Modelle erfinden eigene Kennungen für das Startup (z. B. „wesort-ai-gmbh“). Stimmt der angegebene Name mit dem Kandidaten bzw. der Zielorganisation überein, wird deterministisch die interne Kennung gesetzt. Abweichende Namen bleiben ungültig gebunden.
4. **Auszüge mit Auslassungszeichen.** Ein Auszug der Form „A … B“ gilt nur, wenn jedes Teilstück (mindestens drei, zusammen mindestens sechs Wörter) im Dokument gefunden wird; protokolliert als Abgleichsart „segments“. Der Prüfvertrag verlangt zusätzlich zusammenhängende Auszüge ohne Auslassungszeichen.

Außerdem:

5. **Prompt-Fassung v5.** Der Rechercheauftrag verlangt jetzt ausdrücklich, zuerst mit der Websuche zu recherchieren; ein leeres Ergebnis ist nur nach durchgeführter Recherche zulässig. Anlass: Claude antwortete in vier Läufen ohne jede Suche mit „[]“. Die Zeile gilt für beide Modelle und beide Arme. Kennung `public-push-sas2-mas-v5-search-first-2026-10-16`.
6. **Zweite Modellfamilie.** Der Prototyp spricht neben der OpenAI Responses API jetzt auch die Anthropic Messages API an (Claude Sonnet 5.5, `claude-sonnet-5-5`, offizielles Python-Paket `anthropic` 1.15.0). Der Anbieter folgt aus der Modellkennung; SAS-2, Scouting und Verifikation verwenden weiterhin zwingend dieselbe Kennung. Festlegungen: nur das Websuchwerkzeug, keine automatischen Fallbacks auf andere Modelle, eine Ablehnung des Modells gilt als unvollständige Antwort, nur der Text nach dem letzten Werkzeugschritt zählt als Antwort. Reasoning-Tokens weist Anthropic nicht getrennt aus; sie stecken in den Ausgabetokens. Preisstand: 2 USD bzw. 10 USD je 1 Mio. Ein- bzw. Ausgabetokens, Websuche 10 USD je 1.000.
7. **Neubewertung ohne Modellaufrufe.** `scripts/reevaluate_run.py` bewertet gespeicherte Modellantworten mit dem aktuellen Regelkern neu. Das Original bleibt unverändert, die Neubewertung wird als eigener Lauf gekennzeichnet. Für die Arbeit: Neubewertete Läufe sind Entwicklungsbefunde, keine Ergebnisse des Architekturvergleichs.

## 9. Entscheidung vor dem Hauptlauf: Eingabebudget

Beide Claude-Arme für Max Wild überschritten die Eingabegrenze von 120.000 Tokens (124.407 bzw. 130.109) und endeten deshalb nach Protokoll als technischer Fehler. GPT lag in allen sechs Armen bei höchstens 82.089. Empfehlung: Eingabegrenze vor dem Einfrieren für **beide** Modelle auf **160.000** anheben. Der Kostenrahmen von 0,60 USD je Arm bleibt rechnerisch eingehalten (GPT höchstens etwa 0,59 USD, Claude etwa 0,56 USD). Ohne diese Änderung würde ein Teil der Claude-Läufe am Budget statt an der Architektur scheitern. **Von David am 16.10.2026 freigegeben und im Code umgesetzt** (Budgetprofil `pilot-calibrated-2026-10-16`). In Tabelle `tab:rm-ressourcen` und im Text von 6.6 „120.000“ durch „160.000“ ersetzen, mit dem Satz, dass die Grenze nach den Probeläufen für beide Modelle gleich angehoben wurde. Die Mindestverbesserung von 0,10 hat David ebenfalls bestätigt.

## 10. Ergebnisse der API-Probeläufe (Kap. 7.2.2, Entwicklungsdaten)

Am 16.10.2026 liefen gepaarte Probeläufe auf öffentlichen Entwicklungsaufgaben (mittelständische Unternehmen aus dem Allgäu). Sie sind Fehlerdiagnose, kein Architekturvergleich, kein Holdout und ohne fachliche Bewertung. Alle Läufe liegen als Laufdateien in `artifacts/runs/` und lassen sich in der Oberfläche ohne Kosten öffnen. Kosten der Probeläufe: **3,03 USD** (lokale Schätzung). Dazu kamen etwa 0,67 USD für sechs einzelne Diagnoseaufrufe an Claude ohne Laufdatei, zusammen also rund **3,70 USD**.

| Modell | Aufgabe | Arm | Eingabe | Ausgabe | Websuchen | Kosten | Ergebnis im Lauf | nach Neubewertung |
|---|---|---|---:|---:|---:|---:|---|---|
| gpt-5.6-terra | Max Wild | SAS-2 | 74.897 | 9.036 | 7 | 0,328 | techn. Fehler (Resolver) | Enthaltung |
| gpt-5.6-terra | Max Wild | MAS | 52.991 | 10.629 | 5 | 0,284 | techn. Fehler (Resolver) | 2 × Enthaltung |
| gpt-5.6-terra | Baufritz | SAS-2 | 80.637 | 7.791 | 10 | 0,355 | techn. Fehler (Resolver) | Ablehnung (Gegenbeleg Startup-Status) |
| gpt-5.6-terra | Baufritz | MAS | 62.090 | 8.626 | 6 | 0,288 | techn. Fehler (Resolver) | Enthaltung |
| gpt-5.6-terra | Goldhofer | SAS-2 | 82.089 | 5.852 | 9 | 0,324 | techn. Fehler (Resolver) | Enthaltung |
| gpt-5.6-terra | Goldhofer | MAS | 62.761 | 6.463 | 6 | 0,263 | techn. Fehler (Resolver) | Enthaltung |
| claude-sonnet-5-5 (v4) | Max Wild / Baufritz | beide | je ca. 9.800 | 4 | 0 | 0,079 gesamt | 4 × leer ohne Suche | – (Anlass für Prompt v5) |
| claude-sonnet-5-5 (v5) | Max Wild | SAS-2 | 124.407 | 4.665 | 7 | 0,365 | techn. Fehler (Eingabebudget) | – |
| claude-sonnet-5-5 (v5) | Max Wild | MAS | 130.109 | 5.277 | 8 | 0,393 | techn. Fehler (Eingabebudget) | – |
| claude-sonnet-5-5 (v5) | Baufritz | SAS-2 | 72.797 | 876 | 4 | 0,194 | gültig leer nach Suche | – |
| claude-sonnet-5-5 (v5) | Baufritz | MAS | 55.611 | 658 | 4 | 0,158 | gültig leer nach Suche | – |

Befunde, die in 7.2.2 berichtet werden können:

1. **Beide Modellstufen laufen jetzt in beiden Armen technisch durch.** Kein GPT-Arm überschritt Token- oder Kostengrenzen; das reservierte Budget der zweiten Stufe wurde nie blockiert. In zwei SAS-2-Armen überschritt der Anbieter das Websuchlimit einer Stufe (insgesamt dreimal); das wurde als Protokollabweichung erfasst, ohne den Arm zu beenden.
2. **Die gefundenen Startup-Unternehmen sind real und fachlich plausibel** (z. B. WeSort.AI und Recycleye für Max Wild, Carbo Culture und Carbon Instead für Baufritz, WeldNova und SprayVision für Goldhofer, Optocycle in beiden Claude-Armen für Max Wild). Das ist eine Beobachtung, kein Fachurteil.
3. **Keine Empfehlung.** Nach der Neubewertung fehlten jeweils Pflichtbelege, meist Gründungsjahr, Zielprozess oder Inputstrom, teils weil zitierte Seiten tatsächlich nicht mehr existierten (HTTP 404, mit unabhängigem Abruf bestätigt). Die strenge Evidenzprüfung verhindert unbelegte Empfehlungen, senkt aber die Trefferquote. Für die Hauptstudie ist deshalb mit vielen Enthaltungen zu rechnen.
4. **Selbstauskunft und technische Prüfung weichen ab.** In der zweiten Stufe meldete GPT 50 von 54 Aussagen als gestützt. Die technische Prüfung bestätigte deutlich weniger. Das stützt die Entscheidung, Belege außerhalb des Modells zu prüfen (Kap. 6.1, dritte Entwurfsentscheidung).
5. **Claude braucht mehr Eingabetokens als GPT** (siehe Abschnitt 9).


## 11. PUSH und PULL sind jetzt im Prototyp wählbar (Kap. 5.2, 6.1, 7.3.2)

Bis 16.10. kannte der Prototyp nur PUSH; jeder Auftrag hieß intern „PUSH-Suchauftrag“, eine Auswahl gab es nicht. Jetzt:

- In der Oberfläche wird die **Auftragsart** gewählt. **PUSH:** Das Unternehmen hat keinen Bedarf benannt; die Recherche erschließt Anknüpfungspunkte aus öffentlich erkennbaren Tätigkeiten. **PULL:** Zusätzlich wird das Suchfeld eingetragen, das das Unternehmen selbst öffentlich benennt (z. B. „Recycling mineralischer Baustoffe im Tiefbau“).
- Bei PULL verlangt der Auftrag, zuerst mit einer öffentlichen Quelle des Unternehmens zu belegen, dass es dieses Suchfeld selbst benennt, und nur Startups für dieses Feld zu suchen. Ist das Suchfeld nicht belegbar, wird das als offene Frage ausgewiesen. Die Evidenzmatrix bleibt bei neun Pflichtdimensionen.
- Auftragsart und Suchfeld gehören zum kanonischen Auftrag und zum Auftrags-Hash. Beide Arme erhalten bei PUSH wie bei PULL bytegleich denselben Auftrag. Prompt-Fassung `public-push-pull-sas2-mas-v6-2026-10-16`.
- Einschränkung: Der Projektexport der Transferprüfung unterstützt weiterhin nur PUSH.
- Für 7.3.2: Der Satz „Die Einheit ist ein Tupel aus Zielorganisation, kanonischem PUSH-Suchauftrag und festem Stichtag“ sollte entweder auf PUSH- *oder* PULL-Auftrag erweitert oder bewusst auf PUSH begrenzt werden. Die Probeläufe vom 16.10. waren ausschließlich PUSH.
