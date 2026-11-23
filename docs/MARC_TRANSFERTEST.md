# Marc testet die Wiederverwendbarkeit

Protokollfassung vom 24.09.2026 · Vorbereitung für den Termin am 08.10.2026

## Was dieser Test beantworten soll

Kann eine nicht an der Implementierung beteiligte Person das Referenzmodell verstehen und den Prototypen ohne Änderung des Programmcodes auf zwei neue Organisationskontexte übertragen? Geprüft werden vier Eigenschaften. Das sind Instanziierbarkeit, Portabilität, Verständlichkeit des Kontrollkerns und verständliche Fehlerbehandlung.

Marc bewertet mit seiner UI/UX-Erfahrung die Handhabung und die Nachvollziehbarkeit. Er muss dafür keine Materialtechnologie, Bauprozesse oder Leistungswerte eines Startups beurteilen. Ein Urteil über die technische Eignung einer Kooperation bleibt einer entsprechend fachkundigen Person vorbehalten. Die Ergebnisse dieses Tests sind kein SAS-MAS-Leistungsnachweis.

Der Prototyp ist eine konkrete Umsetzung. Das Referenzmodell beschreibt allgemeiner Aufgaben, Rollen, Übergaben, Evidenzanforderungen und menschliche Entscheidungen. Daher gehören neben der Bedienung zwei Modellaufgaben zum Test. Ein reiner Import-/Export-Test würde die Wiederverwendbarkeit des Referenzmodells zu eng prüfen.

## Vorbereitung durch David, spätestens vor der Sitzung

1. Plane 75–90 Minuten ein. Die sechs Aufgaben haben zusammen 55 Minuten Orientierungszeit. Die restliche Zeit dient Einweisung und Nachbesprechung. Das sind eigene Planungswerte, keine wissenschaftlich validierten Zeitgrenzen.
2. Nutze einen frischen Browser-Tab und den kostenfreien Transfermodus auf `http://127.0.0.1:8001`. Der Server muss auf dem gleichen Rechner laufen. Ein Link mit `127.0.0.1` öffnet sich auf Marcs Rechner nicht automatisch auf Davids Rechner.
3. Start auf dem vorbereiteten Rechner im Projektordner mit `.venv/bin/python scripts/start_transfer_review.py`. Alternativ auf einem zweiten Rechner das geprüfte Quellpaket entpacken, Python 3.13 und die festgeschriebenen Abhängigkeiten installieren und `python scripts/start_transfer_review.py` ausführen. Dazu werden keine API-Zugangsdaten benötigt. Eine durch David vorbereitete Installation ist ausdrücklich als solche zu dokumentieren. Sie ist kein Nachweis einer selbstständigen Installation durch Marc.
4. Lege einen Ablageordner für Exporte an. Er muss nicht mit einem Cloud-Dienst synchronisiert werden. Lade keine API-Schlüssel, CRM-Daten oder internen Organisationsunterlagen in diesen Ordner.
5. Friere diese Anleitung und den Programmstand vor Beginn ein. Das System nimmt einen Fingerabdruck von Programm, Oberfläche, Modellkarte und Regeln in das Sitzungsprotokoll auf. Während der Sitzung nichts reparieren. Probleme protokollieren und erst anschließend beheben. Ein Nachtest erhält eine neue Sitzung und wird getrennt berichtet.
6. Halte Marcs Rolle, Erfahrung, frühere Beteiligung am Projekt und Verhältnis zum Verfasser fest. Bezeichne ihn nur dann als unabhängig von der Entwicklung, wenn er daran tatsächlich nicht beteiligt war.
7. Erläutere Zweck, Freiwilligkeit und Umgang mit den Protokollen. Eine Bildschirm- oder Tonaufzeichnung erfolgt nur nach ausdrücklicher Einwilligung. Speicherung, Zugriff und Löschzeitpunkt sind vorab nach den Hochschulvorgaben festzulegen. Ohne Aufzeichnung reichen strukturierte Beobachtungsnotizen.
8. Vereinbare vorab mit Marc zwei öffentlich dokumentierte Organisationen aus unterschiedlichen Branchen. Keine Mitgliedslisten oder internen Prozessbelege verwenden. Marc formuliert die Suchaufträge selbst. Für T3 soll der konkrete Suchauftrag nicht vorgeübt sein. Halte fest, ob er eine Organisation bereits kannte. Ein dritter Kontext wäre eine zusätzliche Replikation, kein Ersatz für einen gescheiterten Fall.

## Kurze Einweisung zum Vorlesen

> Du prüfst heute nicht, ob du die richtigen Startups erkennst. Du prüfst, ob du den beschriebenen Ablauf auf eigene Suchaufgaben übertragen kannst. Bitte arbeite so selbstständig wie möglich. Du darfst die Modellkarte und die Hinweise in der Oberfläche verwenden. Sage laut, was du gerade erwartest und was unklar ist. Wenn du Hilfe brauchst, halten wir das fest. Schwierigkeiten sind ein Ergebnis des Tests und kein Fehler von dir. Heute entstehen keine API-Kosten und es wird nichts an ein CRM oder E-Mail-System übertragen.

Lautes Denken bedeutet, dass Marc während der Bearbeitung seine Überlegungen ausspricht. Dadurch werden Verständnisprobleme sichtbar. Die gemessenen Zeiten sind deshalb keine unverzerrten Arbeitszeitmessungen gegenüber einer manuellen Suche.

## Schritt für Schritt für Marc und die beobachtende Person

1. **Prüfung beginnen.** Öffne den Bereich „Transferprüfung“. Verwende einen Code wie `P01`, keinen Klarnamen. Klicke auf „Prüfung beginnen“. Halte den angezeigten Versionsfingerabdruck fest. Die beobachtende Person trägt Urteile ein. Wenn Marc selbst protokolliert, muss dies als Selbstbericht ausgewiesen werden.
2. **T1 – Modell verstehen.** Klicke „Aufgabe starten“. Lies die Modellkarte. Erkläre, welche Aufgaben Suche, Verifikation, Regelprüfung und menschliche Entscheidung haben. Benenne mindestens zwei veränderbare Angaben und drei unveränderte Kontrollregeln. Die beobachtende Person hält die tatsächliche Antwort fest. Die Modellkarte ist ein erlaubtes Arbeitsmittel. Eine zusätzliche Erklärung von David zählt als Hilfe.
3. **T2 – Ersten Fall einrichten.** Starte T2. Trage den öffentlichen Organisationsnamen und einen eigenen Suchprompt ein. Die Projektbezeichnung entsteht automatisch aus dem Organisationsnamen. Ein zusätzlicher Profil-Link oder Belegauszug wird nicht verlangt. Beschreibe das Suchziel und erkennbare Randbedingungen, ohne eine gewünschte Startup-Antwort vorzugeben. Prüfe den erzeugten kanonischen Auftrag. Exportiere das Projekt. Bewahre die Datei als `Fall-A` auf und notiere den angezeigten Projektfingerabdruck. Er wird nicht mit dem Prompt-Fingerabdruck verwechselt.
4. **T3 – Zweiten Kontext übertragen.** Starte T3. Wähle „Neues Projekt“, nachdem Fall A exportiert wurde. Richte Organisation B aus einer anderen Branche ein. Prüfe, ob Organisation, Prompt und Ergebnisansicht des ersten Falls zurückgesetzt wurden. Vergleiche die festen Regeln mit Fall A. Exportiere Fall B. Eine Änderung des Codes oder versteckter Stammdaten ist nicht zulässig. Falls sie nötig wäre, ist dies ein negativer Transferbefund.
5. **T4 – Ersten Fall wiederherstellen.** Starte T4 im ursprünglichen Tab. Öffne einen zweiten Tab mit derselben lokalen Adresse. Importiere dort Fall A. Vergleiche Organisation, Prompt, Zeitpunkt und Projektfingerabdruck. Exportiere erneut und vergleiche die beiden Projektdateien. Die Fingerabdrücke für Projekt, Regeln und Programmstand müssen unverändert sein. Notiere das Ergebnis wieder im ursprünglichen Tab. Ereignisse des zweiten Tabs werden nicht automatisch in die erste Sitzung übernommen, daher gehören beide Dateien zum Nachweis.
6. **T5 – Fehlerfall erkennen.** Starte T5. Verwende „Ungültige Testdatei laden“ und versuche diese Datei zu importieren. Die Oberfläche muss den Import ablehnen und den vorhandenen Auftrag erhalten. Dokumentiere die Meldung. Die absichtlich ungültige Datei ist ein technischer Testfall und kein empirisches Suchergebnis.
7. **T6 – Modell übertragen und Grenzen erklären.** Starte T6. Beschreibe schriftlich für Fall B, wer einen Suchauftrag stellt, wer Belege beurteilt, wer einen Discovery-Call führt und wer über eine Zusammenarbeit entscheidet. Benenne die erforderlichen Übergaben und zwei Fragen, die öffentliche Quellen voraussichtlich nicht klären. Erkläre den Unterschied zwischen fehlender Evidenz, einem Widerspruch und einem technischen Fehler. Bewerte nicht die tatsächliche industrielle Realisierbarkeit ohne ausreichende Fachkenntnis.
8. **Jede Aufgabe protokollieren.** Wähle „ohne Hilfe“, „mit Hilfe“ oder „nicht abgeschlossen“, trage die Anzahl der Hilfen und eine konkrete Beobachtung ein. Verweise auf eine Nachweisdatei oder eine wörtlich notierte Aussage. Klicke „Beobachtung speichern“. Ein leerer Befund genügt nicht. Eine abgeschlossene Aufgabe wird nicht nachträglich überschrieben.
9. **Sitzung sichern.** Wähle „Prüfprotokoll exportieren“. Sichere die JSON-Datei zusammen mit Fall A, Fall B, dem Reimport und der ausgefüllten Modellübertragung. Erst danach den Tab schließen. Ohne Export gehen die nur im Tab gehaltenen Beobachtungen verloren. Auch ein abgebrochener Versuch wird als Teilprotokoll exportiert.
10. **Nachbesprechung.** Frage offen, welche Anweisung unklar war, wo eine unnötige Eingabe verlangt wurde und welcher Teil des Modells für den zweiten Kontext geändert werden müsste. Trenne ein konkretes Problem von einem bloßen Gestaltungswunsch. Protokolliere jeweils Beobachtung, vermutete Ursache und mögliche Änderung.

## Vorab festgelegte Auswertung

| Eigenschaft | Aufgabe und Nachweis | Aussage bei positivem Befund |
|---|---|---|
| Instanziierbarkeit | T2 und T3, zwei unterschiedliche exportierte Aufträge, keine Codeänderung | Zwei Kontexte konnten mit derselben Implementierung konfiguriert werden. |
| Portabilität | T4, identischer Projekt-, Regel- und Programmfingerabdruck | Die Konfiguration konnte im geprüften Umfeld ohne inhaltliche Änderung wiederhergestellt werden. |
| Verständlichkeit | T1 und T6, konkrete Aussagen und ausgefüllte Modellübertragung | Marc konnte die zentralen Rollen und Modellgrenzen auf diese Fälle beziehen. |
| Fehlerbehandlung | T5, Ablehnung und unveränderter Auftrag | Der geprüfte ungültige Import wurde nachvollziehbar abgefangen. |

Berichte pro Aufgabe Abschlussstatus, Hilfen, Dauer, Fehler und Beleg. Die Dauer ist beschreibend. Ein Überschreiten der Orientierungszeit ist nicht automatisch ein Scheitern. Ein unbemerkter Kontextwechsel, eine veränderte Schutzregel oder eine erforderliche Codeänderung ist hingegen ein kritischer Befund. Schließe nicht von „sechs Aufgaben abgeschlossen“ auf „100 Prozent wiederverwendbar“. Die sechs Aufgaben sind keine sechs unabhängigen Teilnehmenden.

Es gibt keinen nachträglich angepassten Gesamtscore. Formuliere stattdessen, welche der vier Eigenschaften unter welchen Bedingungen gestützt wird und welche nicht. „Mit Hilfe abgeschlossen“ ist kein unabhängiger Transfer. Fehlt ein Nachweis, bleibt die entsprechende Aussage offen.

## Was bis zum 08.10. als neues Ergebnis vorliegen kann

- Ein nachvollziehbar versioniertes Modell und ein praktisch getesteter Instanziierungspfad.
- Zwei reale Organisationskontexte mit selbst formulierten Suchaufgaben, ohne vertrauliche Unterlagen.
- Sechs dokumentierte Beobachtungen mit Zeit, Hilfen, Fehlern und Artefakten.
- Eine ausgefüllte Modellübertragung und eine begründete Liste von Verbesserungen.
- Eine präzise Grenze der Aussage. Kein Nachweis besserer Startup-Treffer, kein allgemeiner Branchenvergleich und kein Test produktiver Mehrbenutzerfähigkeit.

Falls zusätzlich reale Ergebnisdossiers auf Verständlichkeit geprüft werden sollen, erfolgt dies als eigene Episode mit dokumentiertem API-Budget. Die fachliche Bewertung braucht geeignete Referenzurteile. Für SAS-MAS-Überlegenheit bleibt das getrennte, verblindete Vergleichsexperiment erforderlich.

## Methodische Begründung

Iivari unterscheidet ein allgemeines Lösungskonzept von seiner konkreten Anwendung. Deshalb beziehen sich T1 und T6 auf das Modell und T2 bis T5 auf dessen Umsetzung (Iivari, 2015, S. 107). Die Übertragung generischer Modellbestandteile auf einen Anwendungskontext orientiert sich an vom Brockes Beschreibung der Instanziierung. Hier wird nur ein begrenzter Ausschnitt dieser Wiederverwendung praktisch untersucht (vom Brocke, 2007, S. 52, 58).

MEDS verlangt, zunächst den Evaluationsgegenstand und die Ziele zu bestimmen und darauf die untersuchten Eigenschaften auszurichten. Daher konzentriert sich diese Episode auf vier Eigenschaften und trennt sie von Trefferqualität. Sie ist eine formative, angeleitete Nutzungssituation und keine vollständige Feldstudie (Baskerville et al., 2026, S. 833–834). Die konkrete Aufgabenfolge, Zeitplanung und Bewertungsrubrik sind eigene Operationalisierungen, keine Vorgaben aus diesen Publikationen.

Quellen der Paraphrasen sind die bereits geprüften Originalfassungen im Quellenbestand der Masterarbeit. Es werden die gedruckten Seiten verwendet.

- Iivari, J. (2015). Distinguishing and contrasting two strategies for design science research. European Journal of Information Systems, 24, 107–115. https://doi.org/10.1057/ejis.2013.35
- vom Brocke, J. (2007). Design Principles for Reference Modeling: Reusing Information Models by Means of Aggregation, Specialisation, Instantiation, and Analogy. In Reference Modeling for Business Systems Analysis. https://doi.org/10.4018/978-1-59904-054-7.ch003
- Baskerville, R., Pries-Heje, J., & Venable, J. R. (2026). MEDS: Methodology for Evaluation in Design Science. European Journal of Information Systems. https://doi.org/10.1080/0960085X.2026.2627280
