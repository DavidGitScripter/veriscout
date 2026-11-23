# Generalprobe 4 (12.11.2026, Prompt v13)

Code: v13 (`public-push-pull-sas2-mas-v13-input-check-2026-11-12`), Budgetprofil `pilot-calibrated-2026-10-19`, Reasoning „low“. Paare einzeln mit Worst-Case-Prüfung (1,50 USD je Paar), Deckel 2,50 USD je Modell. Nichts eingefroren.

## Ergebnis je Arm
| Lauf | Modell | Unternehmen | Arm | Suchen | Kandidat | Entscheidung | Index | offen | abgeleitet | gescheiterte Abrufe | Kosten USD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 960dfb292bbf | claude-sonnet-5-5 | Max Wild | SAS-2 | 7 (0 Fehler) | Optocycle GmbH | Enthaltung | 44 | Zielprozess, Input, Wirkung, Ergebnis, Kette | – | handelsregister.ai (403) | 0,512 |
| 960dfb292bbf | claude-sonnet-5-5 | Max Wild | MAS | 8 (0 Fehler) | Optocycle GmbH | Enthaltung | 78 | Ergebnis, Kette | Wirkung | maxwild.com/…/max-wild-ist-sieger… (404) | 0,534 |
| ee22dd0954b8 | gpt-6.1-sol | Südpack | SAS-2 | 9 | jora.tech FlexCo | Enthaltung | 33 | Zielprozess, Input, Fähigkeit, Wirkung, Ergebnis, Kette | – | keine | 0,305 |
| ee22dd0954b8 | gpt-6.1-sol | Südpack | MAS | 10 | jora.tech FlexCo | Enthaltung | 44 | Zielprozess, Input, Wirkung, Ergebnis, Kette | – | keine | 0,339 |
| 8abd266147be | gpt-6.1-sol | Goldhofer | SAS-2 | 6 | Assemblio GmbH | Enthaltung | 78 | Input, Kette | Wirkung, Ergebnis | crunchbase.com (403) | 0,231 |
| 8abd266147be | gpt-6.1-sol | Goldhofer | MAS | 8 | synthavo GmbH | Enthaltung | 56 | Startup-Status, Input, Wirkung, Kette | Ergebnis | cyber-valley.de (404) | 0,276 |

0 Empfehlungen, 0 technische Fehler. Zusätzliche Gründe:
- Optocycle (Sonnet, beide Arme): „Produktfaehigkeit nicht durch die offizielle Quelle belegt“.
- jora.tech (SAS-2): „Identitaet und Produktfaehigkeit nicht beide auf Aussageebene belegt“.
- synthavo: „Gruendungsjahr nicht belegt“.

## Was die Änderungen bewirkt haben
- **(2) Sonnet-Suchwerkzeug:** wirkt. SAS-2 sucht wieder (7 Suchen, 0 Fehler; vorher dreimal 0 Suchen). Werkzeugversion `web_search_20250305` steht in jedem Aufruf. Nebenwirkung: deutlich mehr Eingabetokens (rund 170.000 je Arm statt 45.000 bis 130.000), Kosten etwa 0,52 USD je Arm (Deckel 0,75 USD je Arm).
- **(3) QG3:** sperrte in Probe 4 keinen Kandidaten. In der Neubewertung aller gespeicherten Läufe macht es jora.tech aus Probe 3 zur Empfehlung.
- **(A) Abrufe:** gescheiterte Abrufe in der Neubewertung 50 → 37, SSL/Timeout 14 → 2. In Probe 4 nur noch 403/404 (Sperren bzw. fehlende Seiten, werden respektiert).
- **(C) Prüffrage Input:** kein messbarer Effekt. Kein Arm lieferte einen gestützten `input_stream_mechanism`-Beleg (Sonnet versuchte es in beiden Armen, aber ohne bestätigten Auszug; Sol gar nicht). Input bleibt die häufigste Lücke.

## Vergleich mit Probe 3 auf denselben Unternehmen
| Unternehmen / Arm | Probe 3 (v12, live) | Probe 3 neu bewertet (Regelkern v13) | Probe 4 (v13, live) |
|---|---|---|---|
| Südpack SAS-2 | jora.tech, Index 89, Enthaltung | jora.tech, Index 100, **Empfehlung** | jora.tech, Index 33, Enthaltung |
| Südpack MAS | jora.tech, Index 67 | Index 67, Enthaltung | jora.tech, Index 44 |
| Goldhofer SAS-2 | Assemblio, Index 67 | Enthaltung | Assemblio, Index 78 (nur Input offen) |
| Goldhofer MAS | IUNA, Index 78 (nur Input offen) | Enthaltung | synthavo, Index 56 |
| Max Wild SAS-2 (Sonnet) | 0 Suchen (Werkzeugfehler) | – | Optocycle, Index 44 |
| Max Wild MAS (Sonnet) | neustark Enthaltung, OPTOCYCLE Ablehnung | gleich | Optocycle, Index 78 |

Auffällig ist die große Streuung zwischen Wiederholungen: jora.tech fiel von Index 100 auf 33, obwohl kein Abruf scheiterte. Diesmal setzte die zweite Stufe Zielprozess und Input auf „unknown“, obwohl die Südpack-Quelle bestätigt war. Außerdem fügte das Modell Tabellenzellen zu einem Auszug zusammen (Impressum, Firmenbuch); solche Auszüge stehen so nicht auf der Seite und werden zu Recht nicht bestätigt. Ob die strengere Haltung an der v13-Prüffrage liegt oder Zufall ist, lässt sich mit einem Paar nicht trennen.

## Gesamtbild über alle gespeicherten Läufe (Regelkern v13, kostenlos neu bewertet)
35 Kandidaten-Arme vor Probe 4: 2 Empfehlungen (CAALA, Baufritz, SAS-2; jora.tech, Südpack, SAS-2), 3 Ablehnungen, 30 Enthaltungen. Mit Probe 4: 2 von 41.

## Kosten
| Tag | Anthropic | OpenAI |
|---|---|---|
| 11.11. (Läufe laut Kostenbuch) | 4,140 USD, dazu etwa 0,35 USD Diagnose außerhalb des Kostenbuchs | 5,322 USD |
| 12.11. (Probe 4) | 1,046 USD | 1,151 USD |

Ein zweites Sonnet-Paar (Baufritz) entfiel: 1,046 + 1,50 Worst Case = 2,55 USD > 2,50 USD Deckel.

## Spricht etwas gegen den Start des Hauptlaufs?
Technisch nein: beide Modelle laufen ohne technische Fehler, das Sonnet-Suchproblem ist behoben, Abrufe sind robuster. Vor dem Einfrieren offen bzw. zu bedenken:
1. **Bodeneffekt:** 2 Empfehlungen in 41 Armen. Im Hauptlauf ist mit sehr wenigen Empfehlungen zu rechnen; der Unterschied SAS-2 gegen MAS bei Qualified-Hit wird dann statistisch kaum nachweisbar. Das ist ein ehrliches Ergebnis strenger Belegregeln und muss in der Arbeit so eingeordnet werden (Enthaltungsquote, offene Dimensionen als sekundäre Ergebnisse).
2. **Sonnet nur ein Paar mit dem neuen Werkzeug:** Die feste Eingangsprüfung verlangt 3 Paare ohne technischen Fehler. Für Sol ist das über die Proben erfüllt, für Sonnet mit `web_search_20250305` noch nicht. Empfehlung: Eingangsprüfung Sonnet mit 3 Paaren (Worst Case 4,50 USD, erwartet etwa 3,20 USD) vor dem Einfrieren, oder bewusst als Abweichung dokumentieren.
3. **Guthaben:** Hauptlauf Plan C (15 Aufgaben × 2 Modelle × 2 Wiederholungen = 60 Paare) bei den gemessenen Kosten: Sonnet etwa 30 × 1,05 ≈ 32 USD, Sol etwa 30 × 0,55 ≈ 17 USD, zusammen etwa 49 USD (Worst Case 90 USD, durch den Plan gedeckelt). Das Anthropic-Guthaben (35 USD geladen, davon schon über 5 USD verbraucht) reicht dafür voraussichtlich nicht; bitte in der Konsole prüfen und gegebenenfalls aufladen.
4. **Noch nicht da:** `studie/aufgaben.csv`, `studie/fallblaetter.json`, `studie/BEWERTUNGSPROTOKOLL.md` aus der Cloud; die neue Fallblattvorlage mit sechs Kriterien; Musterlösungen der Übungsfälle freigeben.
5. **Masterarbeit:** v12- und v13-Änderungen (Regeln, QG3, Suchwerkzeug je Modell, Abrufregeln) im Methodenteil nachziehen, bevor die Ergebnisse geschrieben werden.
