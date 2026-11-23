# Generalprobe 6 (12.11.2026, Prompt v15)

Code v15 (`public-push-pull-sas2-mas-v15-quellenabgleich-2026-11-12`): zusätzlich zu v14 N1 Quellenabgleich, N2 Wortlaut-Hilfe, N3 Auslöser der Nachrecherche Index ≥ 44 und höchstens 4 offene Dimensionen. Deckel: Sol 2,00 USD, Sonnet 4,00 USD, zusammen 6,00 USD. Paare einzeln mit Worst-Case-Prüfung (2,00 USD je Paar). Nichts eingefroren.

## Ergebnis je Arm
| Lauf | Modell | Unternehmen | Arm | Suchen | Kandidat | Entscheidung | Index | offen | Nachrecherche | Kosten USD |
|---|---|---|---|---|---|---|---|---|---|---|
| b010fc1ca416 | gpt-6.1-sol | Südpack | SAS-2 | 9 | ENLYZE GmbH | Enthaltung | 33 | Zielprozess, Input, Fähigkeit, Wirkung, Ergebnis | nein (Index < 44) | 0,332 |
| b010fc1ca416 | gpt-6.1-sol | Südpack | MAS | 14 | jora.tech FlexCo | Enthaltung | 56 | Zielprozess, Wirkung, Ergebnis | ja: 44 → 56, 5 Aussagen bestätigt | 0,442 |
| 7e9f16d97da2 | claude-sonnet-5-5 | Baufritz | SAS-2 | 9 | Emidat GmbH | Enthaltung | 78 | Wirkung | ja: 44 → 78, 6 von 7 Aussagen bestätigt | 0,624 |
| 7e9f16d97da2 | claude-sonnet-5-5 | Baufritz | MAS | 4 | – (leeres Ergebnis nach 3 Startup-Suchen) | Enthaltung | – | – | – | 0,186 |
| c446dd8f93b2 | claude-sonnet-5-5 | Goldhofer | SAS-2 | 7 | IUNA AI Systems GmbH | Enthaltung | 33 | Zielprozess, Input, Fähigkeit, Wirkung, Ergebnis | nein (Index < 44) | 0,478 |
| c446dd8f93b2 | claude-sonnet-5-5 | Goldhofer | MAS | 4 | – (leeres Ergebnis nach 3 Startup-Suchen) | Enthaltung | – | – | – | 0,181 |

0 Empfehlungen, 0 technische Fehler, 0 Suchfehler. Sonnet: beide Paare ohne technischen Fehler; mit Probe 4 und 5 jetzt 4 fehlerfreie Paare mit `web_search_20250305` (Eingangsprüfung erfüllt).

Gescheiterte Abrufe: nur IUNA (Sonnet SAS-2): baslerweb.com 406 (2×), buildingnet.de 403 (2×), indeed.com 403.

## Wirkung von N1, N2, N3
- **N1 Quellenabgleich:** 0 Umbindungen in Probe 6. Kostenlose Gegenprüfung über alle gespeicherten Läufe: Von 332 Quellen mit Suchnachweis sind 86 unbestätigt; nur ein einziger dieser Auszüge steht wortgleich auf einer anderen geladenen Seite, und der stammt von LinkedIn (Sperrdatenbank, regelgerecht nicht übernommen). Die übrigen sind Umschreibungen des Modells.
- **N2 Wortlaut-Hilfe:** einmal eingesetzt (Emidat, 4 Hinweise). Die Nachrecherche lieferte dort 7 Aussagen, 6 wortgleich bestätigt; Index 44 → 78.
- **N3 Auslöser:** Beide Nachrecherchen dieser Probe (Emidat, jora.tech MAS, je Index 44) wären mit dem alten Auslöser (≥ 56) nicht gelaufen.

## Neuer Befund (nicht geändert, Entscheidung nötig)
jora.tech (Sol, MAS): Die Nachrecherche lieferte für den Zielprozess einen wortgleich bestätigten Auszug von suedpack.com. Die Zelle bleibt trotzdem „teilweise“, weil der Zielprozess zusätzlich das Freitextfeld `process_stage` verlangt, das hier leer ist. Wegen R4 bleiben dadurch auch Wirkung und Ergebnis „teilweise“. Das ist dieselbe Hürde, die für den Input am 12.11. bereits gestrichen wurde.
Kostenlose Simulation über alle 49 gespeicherten Arme: Ohne diese Zusatzbedingung beim Zielprozess wird genau ein Kandidat zusätzlich empfohlen, jora.tech aus dieser Probe (MAS, Index 100, „Empfehlung; Wirkung und Ergebnis abgeleitet, im Erstgespraech zu klaeren; uebrige Pflichtdimensionen belegt“); sonst ändert sich nichts. Dann 4 Empfehlungen in 49 Armen (heute 3).

## Vergleich mit Probe 3 bis 5 (dieselben Unternehmen)
| | Probe 3 | Probe 4 | Probe 5 | Probe 6 |
|---|---|---|---|---|
| Sol Südpack SAS-2 | jora.tech 89 (neu bewertet Empfehlung) | jora.tech 33 | – | ENLYZE 33 |
| Sol Südpack MAS | jora.tech 67 | jora.tech 44 | – | jora.tech 56 (mit Feldregel: Empfehlung) |
| Sonnet Baufritz | – | – | – | SAS-2 Emidat 78, MAS leer |
| Sonnet Goldhofer | – | – | – | SAS-2 IUNA 33, MAS leer |

## Kosten
| | Anthropic | OpenAI |
|---|---|---|
| Probe 6 | 0,810 + 0,659 = 1,469 USD | 0,774 USD |
| 12.11. gesamt (Proben 4–6) | 3,617 USD | 2,625 USD |
| 11.11. | 4,140 USD (+ ca. 0,35 Diagnose) | 5,322 USD |

## Hauptlauf
- Erwartet je Paar (v15): Sol etwa 0,70 USD, Sonnet etwa 0,90 USD (Probe 4–6: 1,05; 1,10; 0,81; 0,66). Plan C (60 Paare): etwa 21 + 27 = 48 USD; Worst Case 120 USD, harter Stopp 90 USD.
- Auffällig: Sonnet-MAS lieferte in beiden Paaren nach drei Startup-Suchen ein leeres Ergebnis. Das ist regelgerecht (leeres Ergebnis zulässig), senkt aber die Trefferchance des MAS-Arms bei Sonnet.
- Empfehlungsrate über alle Proben bleibt niedrig: 3 von 49 Armen (mit Feldregel 4).
