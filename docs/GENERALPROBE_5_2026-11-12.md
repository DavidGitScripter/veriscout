# Generalprobe 5 (12.11.2026, Prompt v14)

Code v14 (`public-push-pull-sas2-mas-v14-nachrecherche-2026-11-12`): Quellenregel gegen Bezahl-Datenbanken (M1), gezielte Nachrecherche (M2), Schreibvarianten in der Auszugsprüfung (M3), Fortbestandsregel (M5), Input ohne Freitextfeld. Je Modell ein Paar (Deckel 2,50 USD je Modell, Worst Case je Paar jetzt 2,00 USD). Nichts eingefroren.

## Ergebnis je Arm
| Lauf | Modell | Unternehmen | Arm | Suchen | Kandidat | Entscheidung | Index | offen | abgeleitet | gescheiterte Abrufe | Kosten USD |
|---|---|---|---|---|---|---|---|---|---|---|---|
| dffcc26d9f75 | gpt-6.1-sol | Goldhofer | SAS-2 | 12 (6+3+3) | **byte robotics GmbH** | **Empfehlung** | 100 | – | Input, Wirkung, Ergebnis | keine | 0,405 |
| dffcc26d9f75 | gpt-6.1-sol | Goldhofer | MAS | 8 (4+3+1) | Assemblio GmbH | Enthaltung | 78 | Ergebnis | Wirkung | keine | 0,295 |
| 87dfef1f5ae2 | claude-sonnet-5-5 | Max Wild | SAS-2 | 9 (5+2+2) | Optocycle GmbH | Enthaltung | 56 | Zielprozess, Wirkung, Ergebnis | Input | bw-i.de (403), buildingnet.de (403) | 0,609 |
| 87dfef1f5ae2 | claude-sonnet-5-5 | Max Wild | MAS | 7 (5+2) | Optocycle GmbH | Enthaltung | 33 | Startup-Status, Zielprozess, Fähigkeit, Wirkung, Ergebnis | Input | keine | 0,493 |

0 technische Fehler, keine Sonnet-Suchfehler (`web_search_20250305`).

### Empfehlung im Wortlaut
- **byte robotics GmbH**, Website https://byte-robotics.com/ (Impressum: HRB 34542, Amtsgericht Stendal; gegründet 13.06.2024 in Magdeburg, Ausgründung).
- Begründung: „Empfehlung; Input, Wirkung und Ergebnis abgeleitet, im Erstgespraech zu klaeren; uebrige Pflichtdimensionen belegt“.
- Kette: Zielprozess belegt durch Goldhofer („Für den Rahmen eines fünfachsigen THP-Modulsystems werden sogar 83 Stunden benötigt.“); Fähigkeit belegt („byte robotics erzeugt und optimiert Roboterbewegungen auf Basis einer digital beschriebenen Aufgabe.“); Input abgeleitet über den Beleg der Nachrecherche von byte-robotics.com/en („Planning uses the robot cell, relevant geometry, process positions and constraints.“, wortgleich bestätigt); Wirkung und Ergebnis abgeleitet (Startup-Belege, Übertragung auf Goldhofer im Erstgespräch zu prüfen).

## Nachrecherche (M2)
| Arm | ausgelöst | Kandidat | vorher | nachher | angeboten / übernommen | Kosten (geschätzt) |
|---|---|---|---|---|---|---|
| Sol SAS-2 | ja | byte robotics | Index 78, offen: Input | Index 100, **Empfehlung** | 1 Aussage, 1 Quelle / 1 übernommen und bestätigt | 3 Suchen, 22.745 Ein-, 428 Ausgabetokens ≈ 0,08 USD |
| Sol MAS | ja | Assemblio | Index 67, offen: Fähigkeit, Ergebnis | Index 78, offen: Ergebnis | 2 Aussagen, 2 Quellen / 1 Quelle von der Suche gedeckt | 1 Suche, 14.569 / 510 ≈ 0,04 USD |
| Sonnet SAS-2 | ja | Optocycle | Index 56, offen: Zielprozess, Wirkung, Ergebnis | unverändert | 5 Aussagen, 5 Quellen / 5 gedeckt, davon 2 Auszüge bestätigt | 2 Suchen, 32.056 / 1.995 ≈ 0,10 USD |
| Sonnet MAS | nein | Optocycle | Index 33 (unter 56) | – | – | 0 |

Warum es bei Sonnet SAS-2 nicht reichte: Der Prozessauszug von maxwild.com war eine Umschreibung des Modells („Unsere Maschinen verwerten Bauabfall wie Beton, Bauschutt oder Asphalt und sind zudem mobil einsetzbar.“); auf der Seite steht der Satz anders, er wurde zu Recht nicht bestätigt. Die zweite Prozessquelle (buildingnet.de) lieferte 403. Die neu bestätigte Wirkung bleibt nach R4 „teilweise“, solange der Zielprozess offen ist.

Kosten der Nachrecherche in Probe 5 zusammen etwa 0,23 USD (3 Aufrufe).

## Vergleich mit Probe 3 und 4 (dieselben Unternehmen)
| | Probe 3 (v12) | Probe 4 (v13) | Probe 5 (v14) |
|---|---|---|---|
| Sol Goldhofer SAS-2 | Assemblio 67 | Assemblio 78 | **byte robotics 100, Empfehlung** |
| Sol Goldhofer MAS | IUNA 78 | synthavo 56 | Assemblio 78 |
| Sonnet Max Wild SAS-2 | 0 Suchen (Werkzeugfehler) | Optocycle 44 | Optocycle 56 |
| Sonnet Max Wild MAS | neustark / OPTOCYCLE (Ablehnung) | Optocycle 78 | Optocycle 33 |

Kostenlose Neubewertung aller übrigen gespeicherten Arme mit M1, M3, M5 und Input-Feld (ohne Nachrecherche, die Modellaufrufe braucht): Empfehlungen unverändert 2 (CAALA, jora.tech); offene Startup-Status-Zellen 19 → 15; 17 Enthaltungen würden die Nachrecherche auslösen. Über alle gespeicherten Arme einschließlich Probe 5: 3 Empfehlungen in 45 Armen.

## Kosten
| Tag | Anthropic | OpenAI |
|---|---|---|
| 11.11. | 4,140 USD (+ etwa 0,35 USD Diagnose) | 5,322 USD |
| 12.11. (Probe 4 und 5) | 1,046 + 1,102 = 2,148 USD | 1,151 + 0,700 = 1,851 USD |

## Hauptlauf mit v14: erwartete Kosten
- Erwartet je Paar: Sol etwa 0,65 USD (Probe 4: 0,51–0,64 ohne Nachrecherche, Probe 5: 0,70 mit zwei Nachrecherchen), Sonnet etwa 1,10 USD (Probe 4: 1,05, Probe 5: 1,10).
- Plan C (15 Aufgaben × 2 Modelle × 2 Wiederholungen = 60 Paare, ohne Stabilitätspaare): Sol 30 × 0,65 ≈ 19,5 USD, Sonnet 30 × 1,10 ≈ 33 USD, zusammen etwa 53 USD (mit 10 % Reserve etwa 58 USD).
- Worst Case: 60 × 2,00 = 120 USD. Der harte Stopp von 90 USD prüft vor jedem Paar, ob „bisher verbraucht + 2,00 USD“ ≤ 90 USD ist; er greift also erst, wenn die tatsächlichen Kosten etwa 88 USD erreichen. Bei den gemessenen Kosten wird er nicht erreicht. Soll der Lauf auch im theoretischen Worst Case vollständig sein, müsste der Stopp auf 120 USD.

## Spricht etwas gegen den Start des Hauptlaufs?
1. Die Verbesserung wirkt, aber auf schmaler Basis: In Probe 5 entstand 1 Empfehlung in 4 Armen (vorher 0 in 6), und zwar genau über die Nachrecherche. Ein Paar je Modell erlaubt keine belastbare Aussage über die künftige Trefferquote.
2. Sonnet: zweites fehlerfreies Paar mit dem neuen Werkzeug (Probe 4 und 5), aber noch keine Empfehlung und starke Streuung (MAS 78 → 33). Die feste Eingangsprüfung verlangt 3 Paare; 1 Paar fehlt.
3. Anthropic-Guthaben für etwa 33 USD Sonnet-Anteil prüfen.
4. Unverändert offen: Aufgabenliste, Fallblätter und Bewertungsprotokoll aus der Cloud; Freigabe der Musterlösungen; Methodenteil der Arbeit auf v12–v14.
