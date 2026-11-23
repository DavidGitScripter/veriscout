# Ursachen der Beleglücken (12.11.2026, kostenlos)

Grundlage: alle gespeicherten Läufe der Entwicklungsunternehmen (Max Wild, Baufritz, Goldhofer, Südpack), neu bewertet mit Regelkern v13 (Quellen neu abgerufen, keine Modellaufrufe). 39 Kandidaten mit mindestens einer offenen oder teilweisen Dimension, 138 offene Dimensionen. Je Dimension genau eine Ursache (die erste zutreffende in der Reihenfolge Abruf/Auszug vor Regel). Der Kettenschluss (9) folgt aus den übrigen und ist nicht mitgezählt.

## 1. Ursache je Dimension

| Dimension | (a) keine Aussage | (b) ohne Auszug/Quelle | (c) Auszug nicht gefunden | (d) Abruf gescheitert | (e) Regel/Gate trotz Beleg | Summe |
|---|---|---|---|---|---|---|
| Identität (1) | 4 | 1 | 0 | 0 | 1 | 6 |
| Startup-Status/Gründung (2) | 10 | 1 | 0 | 3 | 6 | 20 |
| Zielprozess (4) | 0 | 5 | 2 | 7 | 2 | 16 |
| Input (5) | 3 | 11 | 2 | 9 | 5 | 30 |
| Fähigkeit (6) | 0 | 3 | 3 | 3 | 2 | 11 |
| Wirkung (7) | 3 | 11 | 2 | 1 | 8 | 25 |
| Ergebnis (8) | 3 | 11 | 2 | 3 | 11 | 30 |
| **Summe** | **23** | **43** | **11** | **26** | **35** | **138** |

**(c) Auszug nicht gefunden, vermutete Ursache:** Paraphrase (Wörter großteils vorhanden) 6; Leerzeichen/Silbentrennung/Zeichen 2; nicht auf der Seite (Paraphrase/erfunden) 2; zusammengesetzte Teile/Tabellenzellen 1

**(d) Abruf gescheitert:** HTTP 404 20; Bezahl-/Sperrdatenbank (403/Login) 2; Verbindung 2; HTTP 401 2

**(e) Regel oder Tor trotz bestätigtem Auszug, aufgeschlüsselt:**
- Wirkung (7) und Ergebnis (8) belegt, aber Zielprozess (4) offen, daher nach R4 nur „teilweise“: 11.
- Prüfstufe setzt die Aussage auf „unknown“, obwohl der wörtliche Auszug bestätigt ist (Bindung korrekt): 12.
- Aussage an falsches oder fehlendes Subjekt gebunden (Startup statt Zielorganisation o. ä.): 5.
- Startup-Status: Gründung belegt, aber Fortbestand nicht als „aktiv“ beurteilt (operating_status unknown/leer): 5; ein Gegenbeleg: 1.
- Input mit bestätigtem Auszug, aber nicht gewertet (Freitextfeld input_stream leer oder Zielprozess offen): 1.

## 2. Bezahl- und Sperrdatenbanken
- Arme insgesamt: 60 (mit und ohne Kandidat). Websuchen: 231; keine Suchanfrage nannte eine Datenbank im Suchtext.
- Suchtreffer: 2476, davon 115 auf Datenbankseiten (4.6 %). Diese kommen von der Websuche selbst, nicht aus unserer Abfrage.
- Als Quelle zitiert und dann abgerufen: 15 Datenbankseiten in 13 Armen (companyhouse 3, fusionbase 2, linkedin 2, crunchbase 2, dealroom 2, handelsregister.ai 1, cbinsights 1, f6s.com 1, registercheck 1).
- Kosten: Der Abruf durch den Resolver ist ein kostenloser HTTP-Abruf. Geld kosten diese Seiten nur indirekt, weil das Modell ihre Suchtreffer liest (Eingabetokens). Nutzen: keiner, die Seiten liefern 403 oder nur einen Anriss hinter Login.

## 3. Beinahe-Treffer (Index ≥ 56, höchstens drei offene Dimensionen, ohne Kettenschluss)

| Lauf | Modell | Unternehmen | Arm | Startup | Index | Ergebnis | offen | weitere Gründe |
|---|---|---|---|---|---|---|---|---|
| c8a8069537a3 | gpt-6.1-sol | Goldhofer AG | mas | ArcNC | 89 | ablehnung | Startup-Status/Gründung (2) | kein unabhaengiger Existenz- oder Gruendungsbeleg; Gruendungsjahr nicht belegt; Ausschluss: Sitz nicht in Deutschland, Oesterreich oder der Schweiz |
| 6abdf11a8c43 | gpt-6.1-sol | Baufritz GmbH & Co | sas2 | SURAP GmbH | 78 | enthaltung | Wirkung (7) | Sitz in Deutschland, Oesterreich oder der Schweiz nicht belegt |
| 6dc708027ffc | gpt-6.1-sol | Baufritz GmbH & Co | mas | ecoplanet | 78 | enthaltung | Input (5) | – |
| 8abd266147be | gpt-6.1-sol | Goldhofer AG | sas2 | Assemblio GmbH | 78 | enthaltung | Input (5) | – |
| 960dfb292bbf | claude-sonnet-5-5 | Max Wild GmbH | mas | Optocycle GmbH | 78 | enthaltung | Ergebnis (8) | Produktfaehigkeit nicht durch die offizielle Quelle belegt |
| deb9f4a19b17 | gpt-6.1-sol | Goldhofer AG | sas2 | Assemblio GmbH | 78 | enthaltung | Input (5) | – |
| deb9f4a19b17 | gpt-6.1-sol | Goldhofer AG | mas | IUNA AI Systems GmbH | 78 | enthaltung | Input (5) | – |
| ff81069408af | gpt-6.1-sol | Goldhofer AG | sas2 | Verbotics | 78 | enthaltung | Ergebnis (8) | kein unabhaengiger Existenz- oder Gruendungsbeleg; Sitz in Deutschland, Oesterreich oder der Schweiz nicht belegt |
| 4694ffb167c2 | claude-sonnet-5-5 | Max Wild GmbH | mas | OPTOCYCLE GmbH | 67 | ablehnung | Startup-Status/Gründung (2), Ergebnis (8) | Produktfaehigkeit nicht durch die offizielle Quelle belegt |
| dfcaa34bd138 | gpt-5.6-terra | Max Wild GmbH | sas2 | WeSort.AI GmbH | 67 | enthaltung | Startup-Status/Gründung (2), Input (5) | Gruendungsjahr nicht belegt |
| e3c0871f73e8 | gpt-6.1-sol | Südpack Verpackung | mas | jora.tech FlexCo | 67 | enthaltung | Startup-Status/Gründung (2), Input (5) | Gruendungsjahr keiner Quelle auf Aussageebene zugeordnet |
| 100f93575d55 | claude-sonnet-5-5 | Max Wild GmbH | mas | Optocycle | 56 | enthaltung | Startup-Status/Gründung (2), Input (5), Ergebnis (8) | Produktfaehigkeit nicht durch die offizielle Quelle belegt |
| 61b758941236 | gpt-5.6-terra | Baufritz GmbH & Co | sas2 | Carbo Culture | 56 | ablehnung | Identität (1), Startup-Status/Gründung (2), Ergebnis (8) | Ausschluss: Scale-up, kein Startup; keine identitaetsgleiche offizielle Quelle; kein unabhaengiger Existenz- oder Gruendungsbeleg; Gruendungsjahr nicht belegt; Ausschluss: Sitz nicht in Deutschland, Oesterreich oder der Schweiz; Identitaet und Produktfaehigkeit nicht beide auf Aussageebene belegt |
| 64acba6783eb | gpt-6.1-sol | Baufritz GmbH & Co | mas | ecoplanet | 56 | enthaltung | Input (5), Fähigkeit (6), Ergebnis (8) | Identitaet und Produktfaehigkeit nicht beide auf Aussageebene belegt; Produktfaehigkeit nicht durch die offizielle Quelle belegt |
| 64acba6783eb | gpt-6.1-sol | Baufritz GmbH & Co | sas2 | ecoplanet | 56 | enthaltung | Fähigkeit (6), Wirkung (7), Ergebnis (8) | Identitaet und Produktfaehigkeit nicht beide auf Aussageebene belegt; Produktfaehigkeit nicht durch die offizielle Quelle belegt |
| 8abd266147be | gpt-6.1-sol | Goldhofer AG | mas | synthavo GmbH | 56 | enthaltung | Startup-Status/Gründung (2), Input (5), Wirkung (7) | Gruendungsjahr nicht belegt |
| c8a8069537a3 | gpt-6.1-sol | Goldhofer AG | sas2 | Sonibel Instruments | 56 | enthaltung | Input (5), Wirkung (7), Ergebnis (8) | kein unabhaengiger Existenz- oder Gruendungsbeleg; Sitz in Deutschland, Oesterreich oder der Schweiz nicht belegt |
| ff81069408af | gpt-6.1-sol | Goldhofer AG | mas | WeldNova GmbH | 56 | enthaltung | Startup-Status/Gründung (2), Input (5), Ergebnis (8) | Gruendungsjahr nicht belegt |

Nur eine Dimension offen (ohne Ablehnungen): Input (5) 4, Ergebnis (8) 2, Wirkung (7) 1.

## 4. Folgerungen (Vorschlag, nichts umgesetzt)
1. Fast die Hälfte der Lücken (a+b) entsteht, weil das Modell zu einer Dimension gar keinen oder keinen zitierbaren Beleg liefert. Größter Hebel: gezielte Nachrecherche nur für die offenen Dimensionen (M2).
2. Bei 12 Aussagen liegt ein bestätigter wörtlicher Auszug vor, die Prüfstufe setzt sie aber auf „unknown“. Hier entscheidet das Modell gegen einen technisch bestätigten Beleg. Ob ein solcher Auszug die Aussage trägt, beurteilen ohnehin die Bewertenden in F2.
3. 11 Lücken bei Wirkung und Ergebnis sind Folgefehler eines offenen Zielprozesses; der Zielprozess ist der eigentliche Engpass dieser Fälle.
4. Gescheiterte Abrufe sind überwiegend 404 (vom Modell zitierte Unterseiten, die nicht existieren); Bezahl- und Sperrdatenbanken sind selten Ursache (2), kosten aber Suchtreffer. Quellenregel M1 ist sinnvoll, bringt aber für sich wenig.
5. Toleranz bei der Auszugsprüfung (M3) beträfe höchstens 3 Fälle (Leerzeichen/Zeichen 2, Tabellenzellen 1); 8 der 11 nicht gefundenen Auszüge sind Paraphrasen und dürfen nicht toleriert werden.
6. Der Input (5) ist die häufigste alleinige Lücke bei Beinahe-Treffern.
