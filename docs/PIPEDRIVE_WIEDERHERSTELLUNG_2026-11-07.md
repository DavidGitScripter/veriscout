# Pipedrive: Wiederherstellung der GT-Hub-Struktur (Bauplan, 07.11.2026)

Stand: nur Plan. Im neuen Konto ist bisher nur der VeriScout-Bauplan angelegt
(`config/pipedrive_field_manifest.json`). Nichts aus diesem Dokument ist ausgeführt.

## 1. Quellen

| Quelle | Datum | Inhalt |
|---|---|---|
| Claude-Chat im Ordner „Masterarbeit/aims“ (Sitzung e729f37e…) | 01.08.2026 | Nachbau der GT-Hub-Struktur in `gthub3.pipedrive.com` per API, mit vollständigem Bauskript (Optionen, Reihenfolge, Farben) |
| `Desktop/Dokumente/GT Hub/Pipedrive_1…12.jpeg` | 01.08.2026 | 11 Fotos der damaligen Pipedrive-Oberfläche (Vorlage des Nachbaus) |
| `Desktop/Dokumente/GT Hub/Pipedrive_Deals_geschwärzt.pdf`, `Startups aus Pipedrive.pdf` | 27.06. / 01.08.2026 | Datenansichten des Arbeitgeber-Kontos (damals 145 Organisationen, 113 Deals) |
| `config/pipedrive_field_manifest.json` | im Repo | VeriScout-Felder und Pipeline „ScoutRef Scouting“ (heute angelegt) |

Im Ordner `prototype_push` gibt es keine Exporte mit echten Pipedrive-Datensätzen. Der Trockenlauf-Speicher
des Prototyps liegt nur im Arbeitsspeicher und ist leer. Der alte Token steht nur noch im genannten
Chatprotokoll vom 01.08. und ist ungültig (401). Ausgegeben wurde er nicht.

## 2. Ist-Zustand des neuen Kontos „GT Hub“ (gthub.pipedrive.com)

- Organisationen 0, Deals 0, Personen 0.
- Pipeline 1 „Pipeline“ (Pipedrive-Standard, 5 leere Standardphasen).
- Pipeline 2 „ScoutRef Scouting“ mit 6 Phasen (heute von VeriScout angelegt).
- Organisationsfelder von VeriScout: ScoutRef Entitäts-ID, Lösung, Lösung Stand, Gründungsjahr (Zahl),
  Entwicklungsphase, Technologie (9 Werte), Evidenzstatus Unternehmen.
- 8 Deal-Felder von VeriScout.
- Feld „Label“ enthält nur die Pipedrive-Demowerte (Kunde, Heißer Lead, Warmer Lead, Kalter Lead).

## 3. Soll: GT-Hub-Struktur wie am 01.08. (nur ergänzen, nichts löschen)

| Feld (Organisation) | Typ | Werte | Aktion |
|---|---|---|---|
| Label | Mehrfachauswahl | STARTUP, MATCHING, ACCELERATOR, HUB-MIETER, COMMUNITY (schwarz); MITGLIED, GESELLSCHAFTER (rot); HOCHSCHULE/UNI, GRÜNDERZENTRUM (gelb); SONSTIGES (blau); CO-WORKING SPACE, DIENSTLEISTER (grün); EVENTS (braun); PREFILLED, INVESTMENT INSTITUT (pink); FAILED (lila) | 16 Werte ergänzen. Die 4 Demowerte lassen sich per API nicht löschen, das geht nur von Hand. |
| Prio | Auswahl | 1, 2, 3 | neu |
| Impact Cluster | Auswahl | Circular Economy, Energy, Mobility, Building & Construction, Smart & Efficient Industry, CO2 Capture & Technology, Food & Agritech, Digital Business Infrastructure | neu |
| Technologie | Mehrfachauswahl | 13 Werte | vorhanden (9), 4 ergänzen: Plattform & Ökosystem, Manufacturing Tech, Leistungselektronik, Simulation & Digital Twin |
| Lösung | Text | – | vorhanden |
| Lösung Stand | Datum | – | vorhanden |
| Gründungsjahr | damals Text, heute Zahl | – | vorhanden lassen (Zahl passt für Jahre, ein Typwechsel ginge nur durch Löschen) |
| Notion Shortlist | Mehrfachauswahl | Alois Müller, Südpack, Reisacher, Kutter, Baugrund Süd, CB Tec, Demmeler, Goldhofer, Knestel, Vensol, AVIA, Dachser, Baufritz, Max Wild, Martin | neu |
| Longlist | Mehrfachauswahl | dieselben 15 | neu |
| Longlist besprochen | Mehrfachauswahl | dieselben 15 | neu |
| Entwicklungsphase | Auswahl | damals: Nicht angefangen, Pre-Seed, Seed, Series A, Series B | vorhanden; „Nicht angefangen“ ergänzen (Unbekannt und Bootstrapped bleiben) |
| Bewertung (Score) | Zahl | – | neu |
| Zuständig | Auswahl | David, Stefan, Corinna, Fabian, Martin | neu, nur nach Freigabe (Vornamen von Kolleginnen und Kollegen) |

Alle Felder werden im Formular „Organisation hinzufügen“ sichtbar geschaltet, Reihenfolge wie damals:
Prio, Impact Cluster, Technologie, Lösung, Lösung Stand, Gründungsjahr, Notion Shortlist, Longlist,
Longlist besprochen, Entwicklungsphase, Bewertung (Score), Zuständig.

**Pipeline „Startup Vorqualifizierung“:** Die Standard-Pipeline 1 wird umbenannt. Ihre 5 leeren
Standardphasen werden umbenannt statt gelöscht, in: Backlog Vorqualifizierung → Kontaktaufnahme →
Terminfindung → Entscheidungsfindung → Follow-up (optional).

**Filter „Startups_All“:** Organisationen mit Label STARTUP.

## 4. Was VeriScout bei „In CRM übernehmen“ füllt und was von Hand gepflegt wird

| Feld | Quelle | Wer |
|---|---|---|
| Name, Website | Kandidat | VeriScout (heute schon) |
| Lösung | belegte Fähigkeit des Startups, ein Satz | VeriScout (heute schon) |
| ScoutRef Entitäts-ID, Notiz mit Entscheidungs-Fingerabdruck und Belegen | Lauf | VeriScout (heute schon) |
| Deal „Startup → Mittelständler“ mit ScoutRef Relation-ID | Lauf | VeriScout, nur wenn die Zielorganisation in Pipedrive existiert |
| Label = STARTUP | fest | VeriScout könnte das setzen (kleine Codeänderung) |
| Gründungsjahr | nur wenn in der Evidenzmatrix belegt | VeriScout könnte das setzen (kleine Codeänderung) |
| Notion Shortlist | Zielorganisation, falls einer der 15 Akteure | nicht automatisch: Die Shortlist ist eine menschliche Auswahl |
| Prio, Impact Cluster, Technologie, Entwicklungsphase, Bewertung (Score), Zuständig, Longlist | – | von Hand, weil VeriScout dafür keine geprüften Daten hat |

## 5. Welche Pipeline nutzt VeriScout?

- **Option A (empfohlen bis nach der Studie):** weiter „ScoutRef Scouting“ / „Vorqualifiziert“. Am Code
  ändert sich nichts. „Startup Vorqualifizierung“ dient für die eigene Arbeit von Hand.
- **Option B:** VeriScout schreibt in „Startup Vorqualifizierung“ / „Backlog Vorqualifizierung“. Pipeline
  und Phase liest der Adapter aus `PIPEDRIVE_PIPELINE` und `PIPEDRIVE_STAGE`. Nötig wären diese beiden
  Werte im Startskript, ein angepasster Pipeline-Abschnitt in `config/pipedrive_field_manifest.json`
  (sonst meldet die Selbstprüfung eine Abweichung), die Liste `STAGES` in `crm_pipedrive.py` (nur für die
  Trockenlauf-Ansicht) und die Tests. „ScoutRef Scouting“ würde dann überflüssig, bliebe aber stehen.

## 6. Daten (Kontakte, Organisationen, Deals)

Die damaligen 145 Organisationen und 113 Deals stammen aus dem Konto des Arbeitgebers. Am 01.08. hast du
ausdrücklich „Nur Struktur“ gewählt. Die Daten liegen nur als Fotos und PDFs vor. Ohne deine
ausdrückliche Bestätigung werden keine Datensätze und keine personenbezogenen Daten übernommen.
Sinnvoll und unkritisch wäre, die Mittelständler, für die du Läufe machst, als Organisationen anzulegen,
damit VeriScout Deals verknüpfen kann.
