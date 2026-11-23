# Vorläufiges Evaluationsprotokoll

Dieses Dokument wird vor dem ersten konfirmatorischen API-Lauf finalisiert und
anschließend eingefroren. Nachträgliche Abweichungen werden versioniert und
begründet; ungünstige Resultate werden nicht entfernt.

## Primäre Forschungsbehandlung

- **Kontrolle:** starker Single Agent mit Recherche und Self-Review.
- **Behandlung:** ScoutingAgent plus informationsgetrennter
  VerificationAgent; beide verwenden dasselbe Grundmodell.
- **Konstant:** Modell, Reasoning-Level, kanonischer Suchauftrag,
  Recherchestichtag, Kandidatenlimit, Gesamtressourcen und gemeinsame
  deterministische Prüfungen. Keine Quelle wird einem Arm vorgegeben.
- **Primärer Endpunkt:** Aufgabe enthält unter den ersten fünf mindestens einen
  blind als qualifiziert bewerteten Kandidaten (`Qualified-Hit@5`).

Eine Empfehlung gilt nur dann als qualifiziert, wenn Bewertungswert
`>= 61`, vollständige relationale Evidenz, Widerspruchsfreiheit, negative
Ausschlussprüfung und sämtliche Quality Gates gemeinsam vorliegen. Die
Schwelle wurde in formativen Entwicklungsdurchläufen bestimmt und wird vor dem
Holdout eingefroren; sie wird nicht am konfirmatorischen Ergebnis nachjustiert.

## Primärer Umfang

Ein möglicher Planungsfall sind 15 voneinander verschiedene, öffentliche
Organisations--Suchfeld-Aufträge mit fünf Wiederholungen je Architektur. Das
ergäbe 150 Systemläufe beziehungsweise 75 Paare, aber weiterhin nur 15
unabhängige Aufgabencluster. Diese Zahl ist keine bereits begründete
Mindeststichprobe. Aufgaben- und Wiederholungszahl werden erst nach getrenntem
Kosten-/Varianzpilot und einer simulationsgestützten Power- beziehungsweise
Präzisionsanalyse eingefroren. Wiederholungen messen Modell- und Suchvarianz;
sie erzeugen keine zusätzlichen unabhängigen Anwendungskontexte.

## Memory

Memory ist eine getrennte 2×2-Frage:

```text
{SAS, MAS} × {Memory aus, identischer eingefrorener Memory-Snapshot}
```

Der Snapshot enthält ausschließlich Entwicklungsfälle vor dem Freeze-Zeitpunkt.
Aktuelle Task-, Relations- und Kandidaten-IDs sowie spätere Ereignisse werden
ausgeschlossen. Ein Memory-Haupteffekt allein begründet keinen MAS-Vorteil;
dafür ist eine praktisch relevante Architektur×Memory-Interaktion erforderlich.

## Ressourcen

Je Arm werden global begrenzt und berichtet:

- Eingabe-, Cache-, Ausgabe- und Reasoning-Tokens,
- Modell- und native Webaufrufe,
- direkte Dokumentabrufe,
- Kosten und Laufzeit,
- technische oder vertragliche Fehler,
- tatsächlich zurückgelieferte Modell-ID.

Gleiche Obergrenzen bedeuten nicht gleichen Verbrauch. Zusätzlich zur Qualität
werden deshalb Kosten und Laufzeit je qualifiziertem Kandidaten ausgewiesen.
Die ausgelieferten konservativen Werte sind Pilotgrenzen, keine bereits
festgelegten Hauptstudienparameter. Vor dem Holdout werden sie anhand weniger
getrennter Entwicklungsaufgaben auf technische Fehlerrate, Quellenabdeckung,
Varianz und realen Verbrauch geprüft und anschließend unverändert eingefroren.

Direkte Dokumentabrufe werden in beiden Armen durch denselben deterministischen
Round-Robin-Resolver auf Kandidatenrang und Quellenposition verteilt. Ein
gleiches Gesamtcap darf nicht durch unterschiedliche Allokationsalgorithmen zu
unterschiedlichen Prüfchancen führen.

## Gültigkeit eines Versuchspaars

- `completed` und `abstention` sind primär auswertbar. Ein valides leeres
  Ergebnis besitzt keine Kandidatenzeile und zählt bei `Qualified-Hit@5` als
  null.
- `not_checked_budget` bezeichnet eine unvollständige Prüfung wegen des
  eingefrorenen Resolvercaps. Dieser Zustand ist kein fachliches Urteil.
- `technical_error` umfasst Provider-, Schema-, Modellidentitäts- und sonstige
  Vertragsfehler sowie Ressourcenüberschreitungen.
- Ist ein Arm `not_checked_budget` oder `technical_error`, wird das gesamte
  gepaarte Ergebnis aus der Primäranalyse ausgeschlossen. Zahl, Arm, Ursache
  und Ressourcenverbrauch werden vollständig berichtet; es wird kein günstiger
  Ersatzlauf ausgewählt.
- Die Entblindungsdatei bindet vor der Annotation die exakte Kandidatenmenge je
  Arm. Eine fehlende Annotation darf dadurch nicht als valides Leerresultat
  erscheinen.

## Annotation

Der Kandidatenpool wird erst nach allen Läufen aus beiden Armen und einer
unabhängigen manuellen Recherche gebildet. Bewertende sehen weder Architektur,
Systemscore, Empfehlung, Systemstatus noch interne Begründungsfelder.

Zwei Fachpersonen annotieren atomare Claims und die Gesamtentscheidung
unabhängig; Konflikte werden geklärt. Berichtet werden Interrater-Reliabilität,
Entscheidungsregeln und Änderungen am Codebuch.

## Metriken

Primär:

- Qualified-Hit@5 je Aufgabe,
- qualifizierte Precision@5,
- False-Positive- beziehungsweise Over-Match-Rate.

Sekundär:

- Rate unbelegter oder widersprochener Claims,
- Vollständigkeit der relationalen Kette,
- falsche oder nicht existente Entitäten,
- Net Error Reduction des Verifiers,
- richtige und falsche Enthaltungen,
- einzigartige qualifizierte Kandidaten,
- Ressourcen je qualifiziertem Kandidaten.

Für Net Error Reduction werden unveränderliche Stufenartefakte vor und nach
Self-Review beziehungsweise Verifikation archiviert. Ohne diese
Vorher-/Nachher-Bindung wird die Kennzahl nicht berichtet.

## Aussagegrenze

Das MAS wird nur als überlegen bezeichnet, wenn der primäre Endpunkt praktisch
relevant besser ist, die Sicherheitsmetriken mindestens nicht schlechter sind,
keine Ressourcenobergrenze verletzt wurde und der Effekt nicht ausschließlich
aus zusätzlichem Verbrauch stammt. Andernfalls wird präzise zwischen
„sicherer“, „prozessual effizienter“, „gleichwertig“ und „unterlegen“
unterschieden.
