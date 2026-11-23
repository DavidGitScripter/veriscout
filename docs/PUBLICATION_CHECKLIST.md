# Checkliste für eine publikationsfähige Studie

## Vor dem Holdout

- [ ] primäre Hypothese und `Qualified-Hit@5` vorregistrieren
- [ ] kleinsten praktisch relevanten Effekt festlegen
- [ ] Aufgabenmanifest mit Zielorganisation, Suchprompt, Aufgabenzeitpunkt und
      Prompt-Hash vorab einfrieren; keine Quelle und keinen Kandidaten vorgeben
- [ ] Entwicklungs-, Pilot- und Holdoutfälle strikt trennen
- [ ] Kosten-/Varianzpilot abschließen und Fallzahl danach einfrieren
- [ ] stärkste SAS-2-Kontrolle und Ressourcenobergrenzen fixieren
- [ ] technische Fehler-, Wiederholungs- und Ausschlussregeln fixieren
- [ ] Schwelle 61, Rubrikversion und Sensitivitätsanalyse vorab fixieren;
      Schwelle nur zusammen mit vollständiger Evidenz und Quality Gates nutzen
- [ ] gültiges Leerresultat, `not_checked_budget` und `technical_error`
      disjunkt definieren
- [ ] atomare Annotationsrubrik vor Einsicht in Systemergebnisse einfrieren

## Durchführung

- [ ] randomisierte AB/BA-Reihenfolge erhalten
- [ ] Modell-ID, API-Version, Datum und Parameter je Aufruf archivieren
- [ ] Prompts und Hashes vor dem Lauf sowie alle je Arm gefundenen Quellen,
      Abrufzeiten und Inhaltsfingerabdrücke nach dem Abruf sichern
- [ ] tatsächliche Tokens, Webaufrufe, Dokumentabrufe, Kosten und Laufzeit berichten
- [ ] alle technischen Fehler und Enthaltungen erhalten
- [ ] Paare mit `not_checked_budget` oder `technical_error` vollständig und
      begründet aus der Primäranalyse ausschließen; keine Ersatzläufe auswählen
- [ ] valide Leerresultate als `Qualified-Hit@5 = 0` erhalten
- [ ] Stufenartefakte und Hashes vor/nach Self-Review beziehungsweise Verifikation
      archivieren
- [ ] keine nachträgliche Auswahl günstiger Läufe
- [ ] Kandidatenpool aus beiden Armen plus unabhängiger menschlicher Recherche bilden

## Fachurteile und Statistik

- [ ] zwei blinde Fachpersonen und dokumentierte Konfliktklärung
- [ ] Interrater-Reliabilität berichten
- [ ] Kandidaten nicht als unabhängige Stichproben behandeln
- [ ] Unternehmen als Cluster berücksichtigen
- [ ] gepaarte Effektgrößen und 95-%-Konfidenzintervalle berichten
- [ ] exakten gepaarten Permutationstest oder clusterrobuste Alternative verwenden
- [ ] sekundäre Tests als solche kennzeichnen und Mehrfachtests berücksichtigen

## Reproduzierbarkeit, Ethik und Freigabe

- [ ] Code-Commit, Abhängigkeiten und Container einfrieren
- [ ] Aufgabenmanifest, Blindpakete, Entblindungsdateien und Analysecode archivieren
- [ ] vollständiges Laufmanifest mit Prompt-, Payload-, Preis-, Rubrik-,
      Umgebungs- und Stufenartefakt-Hashes archivieren
- [ ] Datenminimierung, Aufbewahrung und Löschung dokumentieren
- [ ] keine CRM-Kontakte oder vertraulichen Inhalte in Forschungsartefakten
- [ ] veröffentlichbare anonymisierte oder synthetische Replikationsdaten bereitstellen
- [ ] Lizenz, Datenverfügbarkeit und KI-Nutzung transparent erklären

Ein negatives oder gleichwertiges Ergebnis bleibt publikationsfähig, wenn Design,
Auswertung und Aussagegrenzen sauber sind. Publikationsfähigkeit setzt keine
MAS-Überlegenheit voraus.
