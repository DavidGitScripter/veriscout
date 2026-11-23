# Bewertungsprotokoll (Entwurf, noch nicht eingefroren)

> **Überholt.** Diese Fassung gilt nicht mehr. Maßgeblich wird `studie/BEWERTUNGSPROTOKOLL.md`; sie kommt beim Einfrieren aus der Cloud.

Quelle: Thread zur Labeling-Kritik, übermittelt am 07.11.2026. Noch nicht im Code umgesetzt.

1. **Gegenstand:** je Aufgabe (Unternehmen, Suchauftrag, Stichtag) und Startup ein Fall. Mehrfach gefundene Startups derselben Aufgabe zählen einmal. F5 bezieht sich auf die empfohlene Darstellung, sonst auf die zuerst gezogene. Verblindet: kein Hinweis auf SAS-2/MAS, Modell oder Systemurteil.
2. **Fragen** (F1–F4 ja / nein / nicht beurteilbar, F5 nur ja / nein; Begründungssatz Pflicht bei F1, F2 und F3 = nein, bei F4 und F5 = ja, bei jedem „nicht beurteilbar“ und bei F3 immer; kein Gesamturteil):
   - F1 Existenz und Fortbestand: existiert unter Name und Website, eigenes Angebot, nicht übernommen, insolvent oder eingestellt.
   - F2 Beleg: Der markierte Auszug steht auf der verlinkten Seite, und „Laut dieser Quelle gilt: [Aussage]“ trifft zu.
   - F3 Kette: Belegter Prozess, Input, Fähigkeit und nutzbares Ergebnis sind schlüssig. Bei Nein das gescheiterte Glied wählen (Prozess, Input, Fähigkeit, Ergebnis). Begründungssatz immer.
   - F4: Ein Ausschlusskriterium aus dem Fallblatt greift.
   - F5 Schönfärberei: Die Darstellung behauptet mehr, als die Belege hergeben (nur ja/nein).
3. **Treffer je Person:** F1 ja und F2 ja und F3 ja und F4 nein. Sonst kein Treffer. Gibt es in F1 bis F4 ein „nicht beurteilbar“, aber kein Nein und kein F4 = ja, dann ist das Urteil „nicht beurteilbar“. Qualified-Hit eines Arms = 1, wenn mindestens ein empfohlenes Startup ein Treffer ist. Enthaltung, leeres Ergebnis und technischer Fehler zählen 0.
4. **Zusammenführung:** Jeder Fall wird von 3 Personen unabhängig bewertet, ohne Einigung. Es entscheidet die Mehrheit der festen Urteile (Treffer oder kein Treffer); „nicht beurteilbar“ zählt nicht mit.
   - 1:1 gilt als strittig: primär kein Treffer, in der Sensitivitätsanalyse je einmal als Treffer und als kein Treffer.
   - 0 oder 1 feste Urteile gelten als nicht beurteilbar: primär kein Treffer, Sensitivität wie bei strittig.
   - Der Anteil einstimmiger Fälle wird berichtet.
5. **Stichprobe und Zuteilung:** 10 Bewertende mit je 12 Fällen, jeder Fall 3-fach bewertet, also 40 Fälle.
   - Stufe 1: alle empfohlenen Startups. Sind es mehr als 40, wird geschichtet nach Arm und Modell gezogen, mit Gewichten.
   - Stufe 2: der Rest, geschichtet aus den nicht empfohlenen Startups (Arm, Modell, Endzustand).
   - Die Fälle eines Unternehmens bilden einen Block, jeder Block geht an 3 Personen.
   - Die Last wird ausgeglichen: 12 Fälle und höchstens 6 Unternehmen je Person. Kein Personenpaar teilt alle Fälle.
   - Die Reihenfolge der Unternehmen und Fälle ist je Person zufällig, mit festem Startwert. Ziehung und Zuteilung werden mit Fingerabdruck gespeichert.
   - Fällt eine Person aus, behalten ihre Fälle 2 Urteile, die Regel bleibt unverändert.
6. **Kennzahlen:**
   - Krippendorffs Alpha (nominal) je Frage über alle 10 Personen. „Nicht beurteilbar“ zählt als fehlend, das Design ist unvollständig.
   - Paarweise Übereinstimmung.
   - Beides jeweils mit Bootstrap über die Fälle.
   - Gültigkeit von F2 gegen `excerpt_verified` und von F1 gegen `operating_status`, mit Wilson-Intervall (aktiv = ja; übernommen, insolvent, eingestellt = nein; ungeklärt wird nicht verglichen).
   - Anteil „nicht beurteilbar“ je Frage.
   - Verteilung der gescheiterten Glieder in F3.

## Umsetzung (offen)
- Ein Bewertungsbogen je Person (oder ein Bogen, der nach Kürzel nur die zugeteilten Fälle zeigt), mit Karten je Unternehmen und Kurzprofil aus dem Fallblatt. Export als JSON je Person.
- In der Oberfläche ersetzt „Bewertungen einlesen“ (bis zu 10 Dateien, Vollständigkeit je Person) den bisherigen Schritt 2 „Abgleich und Einigung“. Schritt 3 wertet nach der Regel oben aus.
- Die alte R1/R2-Einigung wird aus der Oberfläche entfernt. Die alten Auswertungsfunktionen bleiben für die Tests erhalten.
- Tests für die Zuteilung (jeder Fall 3-mal, höchstens 6 Unternehmen und 12 Fälle je Person, deterministisch mit Startwert) und für die Zusammenführung.
- Hinweis aus der Datensichtung: Die Blindpakete enthalten je Kandidat `claims_for_annotation` und `sources`. Arm und Architektur stehen nur in `assignment_manifests`. Endzustand und `operating_status` stehen in `operator_view`.
