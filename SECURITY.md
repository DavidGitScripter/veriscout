# Sicherheitsrahmen

VentureScout ist ein Forschungsprototyp, kein produktionsreifes autonomes
Entscheidungssystem. Der veröffentlichbare Standardbetrieb ist read-only und
verursacht keine Modellkosten.

## Schutzgrenzen

- Geheimnisse werden ausschließlich über Umgebungsvariablen eingelesen.
- Bezahlte Vergleichsläufe erfordern zugleich einen API-Schlüssel,
  `SCOUTREF_EVAL_LIVE_ENABLED=1`, ein `SCOUTREF_OPERATOR_TOKEN` und die
  ausdrückliche Bestätigung in der Oberfläche.
- Legacy-, CRM- und Outreach-Endpunkte sind standardmäßig deaktiviert.
- Vergleichsläufe schreiben weder in ein CRM noch in ein E-Mail-System.
- Der Operator-Token wird nur als HTTP-Header übertragen und nicht in lokalen
  Browser-Speichern gesichert.
- Fehlerdetails und interne Pfade bleiben im Serverprotokoll.

## Datenregel

Konfirmatorische Aufgaben dürfen nur öffentlich zugängliche Quellen enthalten.
Personenbezogene CRM-Daten, interne Prozessbelege und vertrauliche
Organisationslisten gehören weder in Aufgabenpakete noch in Laufartefakte oder
Memory-Snapshots.

## Meldung eines Problems

Eine öffentliche Sicherheitslücke sollte nicht zusammen mit Schlüsseln,
personenbezogenen Daten oder produktiven Endpunkten veröffentlicht werden.
Bis ein eigener Meldekanal festgelegt ist, wird der Prototyp ausschließlich
lokal beziehungsweise in einer zugriffsbeschränkten Forschungsumgebung
betrieben.
