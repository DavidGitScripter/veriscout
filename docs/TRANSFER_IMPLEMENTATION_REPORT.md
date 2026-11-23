# Umsetzung und technische Prüfung der Wiederverwendbarkeit

Stand 25.09.2026. Vorbereitung der Evaluation mit Marc, noch kein Ergebnis dieser Evaluation.

## Ergebnis in Kürze

Der Prototyp besitzt einen neuen Arbeitsbereich für öffentlich formulierte Suchaufträge und eine getrennte, kostenlose Transferprüfung. Eigene Organisationskontexte lassen sich ohne Codeänderung konfigurieren und als geprüfte Projektdateien übertragen. Die Transferprüfung hält Aufgaben, Hilfen, Beobachtungen und Bearbeitungszeiten fest. Der primäre SAS-MAS-Vergleich wird dadurch nicht verändert.

Die lokale Testsuite umfasst 146 bestandene Prüfungen. Die Tests enthalten auch simulierte Modellantworten und synthetische Daten. Sie sind technische Nachweise für die geprüften Verträge, keine Stichprobe realer Startup-Suchen. Es wurden bei dieser Überarbeitung keine kostenpflichtigen Modellaufrufe und keine CRM- oder Outlook-Aktionen ausgeführt.

## Was konkret neu ist

1. **Getrennter Transfermodus.** Ein eigener Start auf Port 8001 deaktiviert Modellzugänge, Live-Läufe, CRM und die alten Aktionsschnittstellen. Laufzeitdateien werden getrennt vom bisherigen Betrieb abgelegt. Der ursprüngliche Live-Start bleibt erhalten.
2. **Organisationsneutrale Projektdatei.** Exportiert werden nur Bezeichnung, Organisationsname, Suchprompt und Zeitpunkt samt Versionsfingerabdrücken. Geheimnisse, Einwilligung zum Live-Lauf, Ergebnisse und Feedback gehören nicht hinein. Feste Entscheidungsregeln lassen sich über einen Import nicht verändern.
3. **Geprüfte Wiederherstellung.** Importierte Dateien werden vor einer Änderung des Formulars validiert. Ungültige, übergroße oder manipulierte Projekte werden abgewiesen. Ein Wechsel entfernt alte Ergebnisansichten, frühere Freigaben und den zuvor eingetragenen Bedienerschlüssel aus der Ansicht. Unterschiedliche Zeitzonenschreibweisen desselben Zeitpunkts werden vereinheitlicht.
4. **Sechs beobachtbare Aufgaben.** Das Frontend unterstützt Aufgabenstart, Urteil, Hilfen und konkrete Notizen. Abgeschlossene Beobachtungen sind in dieser Sitzung nicht überschreibbar. Nicht bearbeitete Aufgaben bleiben im Export offen. Ein Teilprotokoll ist ausdrücklich zulässig.
5. **Modellübertragung statt bloßer Oberflächenbefragung.** Modellkarte und Aufgaben T1/T6 verlangen eine Erklärung der Rollen, Übergaben, Entscheidungsrechte und Informationsgrenzen im zweiten Anwendungskontext. Die Aufgaben T2–T5 prüfen die konkrete Umsetzung.
6. **Neues Erscheinungsbild.** Ruhige helle Flächen, dunkle Typografie, zurückhaltende violette Akzente, klare Navigation und reduzierte Eingaben. Suche, Transferprüfung, Ergebnisansicht und Bewertung sind sichtbar getrennt. Eine zusätzliche Organisationsprofil-Datei ist keine Eingabevoraussetzung.
7. **Verteilbares Quellpaket.** Der Paketbau schließt virtuelle Umgebungen, Laufzeitdaten, lokale Schlüsseldateien und symbolische Links aus. Ein Manifest hält die Dateifingerabdrücke fest. Ein separates Prüfprogramm erkennt nachträglich veränderte Paketdateien. Es ersetzt weder eine digitale Signatur noch eine vollständige Prüfung auf vertrauliche Inhalte.
8. **Langsamen Programmfingerabdruck repariert.** Die bisherige Ermittlung durchlief auch installierte Abhängigkeiten in der virtuellen Umgebung. Das blockierte zunächst zwei Testanläufe. Diese Verzeichnisse werden jetzt ausgelassen, während Änderungen an relevanten Quelldateien weiterhin erkannt werden.

## Zusammenhang mit dem wissenschaftlichen Vorgehen

| Ausgangspunkt | Umsetzung | Was damit nicht belegt ist |
|---|---|---|
| Allgemeines Lösungskonzept und konkrete Anwendung sind zu unterscheiden (Iivari, 2015, S. 107). | Modellkarte sowie eigene Aufgaben zur Erklärung und Übertragung der Rollen. | Ein verständliches Formular allein beweist keine Wiederverwendbarkeit des gesamten Referenzmodells. |
| Referenzmodelle werden durch Instanziierung auf einen Kontext bezogen (vom Brocke, 2007, S. 52, 58). | Zwei selbst formulierte Organisationskontexte mit unverändertem Regelkern und dokumentierten Variationen. | Zwei Fälle decken weder alle Branchen noch alle möglichen Varianten ab. |
| Evaluationsziele, Gegenstand und Eigenschaften sind aufeinander abzustimmen (Baskerville et al., 2026, S. 833–834). | Vier getrennte Eigenschaften mit Aufgaben und Nachweisen. Kein nachträglich optimierter Gesamtscore. | Der Versuch misst weder fachliche Trefferqualität noch eine kausale MAS-Überlegenheit. |
| Aufgabenbezogene Evaluation soll tatsächlich beobachtbare Fehler und geeignete menschliche Urteile einbeziehen. | Technische Regressionstests und Marcs Beobachtungen bleiben getrennte Nachweise. Keine automatisch erfundenen Nutzerurteile. | Technische Tests ersetzen keine Domänenexpertise. |

Die konkreten Aufgaben, Zeitvorgaben und Bewertungskriterien sind eigene Operationalisierungen. Sie werden nicht als fertige Instrumente dieser Publikationen ausgegeben. Vollständige Quellen und die Begründung der Seitenbezüge stehen in `MARC_TRANSFERTEST.md`. Die zuletzt genannte allgemeine Evaluationspraxis wird auch in der offiziellen OpenAI-Dokumentation beschrieben, sie ist jedoch keine wissenschaftliche Quelle für eine Überlegenheit der verwendeten Architektur: https://developers.openai.com/api/docs/guides/evaluation-best-practices

## Bereits vorhandene Qualitätskontrollen, die erhalten blieben

Die bestehenden Tests prüfen unter anderem identische Auftrags- und Promptkennungen im SAS-MAS-Paar, gemeinsame Ressourcenobergrenzen, getrennte Verifikation, relationale Evidenz, den Umgang mit Widersprüchen, die zeitliche Trennung von Memory und Bewertungsfall sowie die Freigabe vor bezahlten Aktionen. Diese Mechanismen wurden nicht als neue Verbesserungen dieser Sitzung gezählt.

Der Schwellenwert bleibt 61. Er ist eine vorab festgelegte Entwicklungsregel und keine kalibrierte Erfolgswahrscheinlichkeit. Der Memory-Vergleich bleibt eine gesonderte Ablation. Im Transfermodus ist Memory ausgeschaltet, damit die Bedien- und Übertragungsprüfung keine unkontrollierten Vorinformationen erhält. Für den fachlichen Vergleich kann weiterhin der gemeinsame eingefrorene Snapshot untersucht werden.

Es wurde kein trainierter Spezialverifikator hinzugefügt. Dafür fehlen hier eine dokumentierte Trainingsstichprobe, ein davon getrenntes Prüfset und belastbare Vergleichsergebnisse. Mehr Modellaufrufe oder zusätzliche Agenten ohne kontrollierte Prüfung würden den behaupteten Erkenntnisgewinn nicht absichern. Ebenso wurde nicht behauptet, sämtliche Erkenntnisse aller zitierten Publikationen vollständig implementiert zu haben.

## Tatsächlich ausgeführte Prüfungen

- Lokale Gesamtsuite mit 146 bestandenen Tests. Davon wurden 43 in dieser Überarbeitung ergänzt. Der vorherige Bestand umfasste 103 Tests.
- Syntaxprüfung beider JavaScript-Dateien `app.js` und `reuse.js` ohne Fehler.
- Browserprüfung der kostenlosen Auftragsvorschau, des Exports und des Reimports. Der Projektfingerabdruck blieb beim Roundtrip erhalten. Änderungen am Programmstand wurden beim Import älterer Dateien kenntlich gemacht.
- Eine absichtlich ungültige Datei wurde zurückgewiesen. Die Eingaben des aktuellen zweiten Kontexts blieben erhalten.
- Eine ausdrücklich als `TECHNICAL_QA` bezeichnete synthetische Beobachtung wurde exportiert. Das Teilprotokoll enthielt eine bearbeitete und fünf nicht beobachtete Aufgaben. Dies ist kein Versuch mit Marc und darf nicht als dessen Ergebnis verwendet werden.
- Prüfung bei 390 × 844 Pixeln und in der Desktopansicht. Kein horizontales Überlaufen in der geprüften Mobilansicht. Die zuvor auf kleinen Bildschirmen ausgeblendete Navigation wurde korrigiert. Dies ist keine vollständige Barrierefreiheitsprüfung.
- Die Schutzgrenze lässt kostenlose Transfer-Endpunkte zu, weist dagegen nicht autorisierte Vergleichs- und Entblindungsaktionen zurück. Alte Aktionsendpunkte bleiben deaktiviert.

Die maschinenlesbaren Testergebnisse liegen im Entwicklungsprojekt unter `artifacts/reuse_2026_09_24/verified-tests.xml`. Diese lokalen Prüfnachweise werden bewusst nicht in das Quellpaket aufgenommen. Die Tests selbst sind enthalten und können erneut ausgeführt werden.

## Grenzen und nächster notwendiger Schritt

Marc hat den neuen Stand noch nicht getestet. Die reale Evaluation soll 75–90 Minuten dauern und ist in `MARC_TRANSFERTEST.md` beschrieben. Zwei Kontexte bei einer Person liefern begrenzte formative Evidenz. Aufgabenreihenfolge, Erfahrung, Hilfen, persönliche Beziehung zum Verfasser und Vorbereitung der Installation müssen mitberichtet werden.

Die Transferprüfung benötigt keine API-Aufrufe und findet keine neuen Startups. Ihre Aussage betrifft den Übertragungsweg, das Modellverständnis und die Handhabung. Reale Suchqualität, Quellenrichtigkeit, wirtschaftliche Eignung und MAS-SAS-Unterschiede bleiben Gegenstände der gesonderten fachlichen Evaluation.

Beobachtungen liegen bis zum Export nur im geöffneten Tab. Ein Browserabsturz kann sie verlieren. Die Exportdatei ist nicht signiert und lässt sich außerhalb des Programms verändern. Sie ist ein Forschungsprotokoll mit menschlicher Verantwortlichkeit, kein manipulationssicherer Auditdienst. Der Modus ist für einen lokalen Test ausgelegt, nicht für produktiven Mehrbenutzerbetrieb.

Eine frische Installation auf Marcs Rechner und Betriebssystem ist zusätzlich zu prüfen, sofern Marc dort arbeiten soll. Ein Test in einem zweiten Ordner auf demselben Rechner ersetzt diese Prüfung nicht. Kein endlicher Testumfang begründet „100 Prozent Sicherheit“ oder allgemein optimale Suchqualität.

An der Masterarbeit wurden noch keine erfundenen Nutzerbefunde ergänzt. Nach Marcs Sitzung lassen sich die tatsächlichen Beobachtungen mit `TRANSFER_RESULT_TEMPLATE.md` auswerten und in Evaluation und Limitationen übernehmen.
