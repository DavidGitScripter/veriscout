# Evidenz- und Vergleichsaudit

Aktuelles Projekt: `prototype_push`. Neuer Softwarestand: v15, Promptvertrag v3-compact. Die Masterarbeit verwendet neun Pflichtdimensionen und trennt Belegvollständigkeit von fachlicher Eignung. Schwelle 61 bleibt gesetzt; bei vollständig gestützter Matrix ist der Index ohnehin 100.

## Verträge

- SAS-2 und MAS verwenden denselben Erstprompt einschließlich identischer Systemanweisung und gleicher Ressourcenobergrenzen.
- SAS-2 behält native Quellen beider eigener Aufrufe. MAS startet den Verifikationskontext mit Claim-IDs und Subjektbindung, ohne Scout-Score oder Quellenliste.
- URL-Queryparameter bleiben dokumentbestimmend. Atomare Claim-Auszüge werden einzeln geprüft; lokal berechnete Auszugshashes dürfen nicht aus Modell-JSON übernommen werden.
- Wiederholte Claim-/Quellenzeilen derselben URL teilen den Resolver-Cache. Das Abruflimit zählt neue URLs.
- Verifikation verwirft ungeprüfte Beschreibung und Steckbrief. Ein technischer Ressourcenfehler sperrt weitere Modellaufrufe.
- Auswertung berichtet neben bedingten Qualitätsmetriken die Statusverteilung aller zugewiesenen Läufe.
- Zusatzfelder für Kontakte, Finanzierung und Marketing gehören nicht in den kompakten Recherchevertrag. CRM-Felder und Adapter bleiben bestehen, unbekannte Werte werden nicht erfunden.

## Nachweise und Grenzen

95 Offline-Tests bestehen. Zusätzlich wurden zwei Entwicklungspaare mit dem vorherigen Promptvertrag v2 ausgeführt; alle vier Arme waren technisch unvollständig. Keine dieser Ausgaben ist ein Qualitäts- oder MAS-Erfolgsnachweis. Die letzte Vertragsverkürzung v3 ist noch nicht live geprüft. Keine große bezahlte Serie starten, bevor vollständige End-to-End-Piloten und ein eingefrorener Versuchsplan vorliegen.

Der Resolver prüft Textvorkommen, nicht semantische Folgerichtigkeit. Er blockiert Weiterleitungen und extrahiert keine PDFs. Der Cache ist nicht dauerhaft. Ein vollständiges Matrixobjekt beweist keine reale technische oder wirtschaftliche Kompatibilität. Die feste Teilbudgetaufteilung kann nach höherem Webtoolverbrauch den zweiten Pass blockieren; eine andere Allokationsregel muss vor dem Hauptversuch symmetrisch festgelegt und geprüft werden.

Literaturbezogene Mechanismen: Lazy Grounding (arXiv:2608.30303) motiviert genaue Aufgabenbindung; HALT (2608.02009) motiviert evidenzgerichtete Suchpriorisierung, dessen trainierter Verifier ist nicht implementiert; Tan et al. (2608.27924) motiviert die getrennte Messung richtiger Enthaltung und unnötiger Verweigerung. Memory-Effekte sind ohne menschlich bewertete Trainingsereignisse nicht nachgewiesen.

Die Entwicklungsdaten werden außerhalb des freigabefähigen Quellpakets unter `review_2026_09_05` aufbewahrt. Sie enthalten keine API-Schlüssel. Das Quellpaket wird über das vorhandene Release-Skript mit Dateimanifest erstellt.
