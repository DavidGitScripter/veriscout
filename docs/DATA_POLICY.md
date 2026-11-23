# Public-only Daten- und Vertraulichkeitsregel

## Zulässiger Evaluationsinput

Jeder Vergleichsauftrag enthält als fachlichen Input genau:

- den öffentlichen Namen genau einer Zielorganisation und
- einen vorab festgelegten Suchprompt mit öffentlich überprüfbarem Prozessbezug
  und offen formulierter Zielwirkung.

Auftrags-ID, Organisations-ID, Prompt-Hash und Zeitpunkt werden serverseitig
erzeugt. Profil-URL, Quellenliste, Belegauszug, Kandidat oder gewünschtes Ergebnis
werden nicht eingegeben. Der Prompt darf keine internen Prozess-, Mengen-,
Kosten-, Prioritäts- oder Strategiedaten enthalten.

Es existiert kein zentraler Organisations- oder Suchfeldkatalog. Frühere
Matching-Heuristiken, Prioritäten, vorselektierte Kandidaten und CRM-Adressen
sind kein zulässiger Evaluationsinput.

## Modellregel

SAS und MAS erhalten denselben kanonischen Auftrag und müssen die
Zielorganisation selbst anhand öffentlicher Quellen untersuchen. Ein
Prozessdetail darf in der Ausgabe nur dann als Fakt behandelt werden, wenn es
einem auflösbaren Quelldokument und einem konkreten Textauszug zugeordnet ist.
Andernfalls lautet der Status `unknown` oder ausdrücklich `hypothesis`; eine
solche Annahme trägt keine positive Empfehlung.

Nachhaltigkeits-, Effizienz- und Profitabilitätswirkungen sind grundsätzlich
Wirkungshypothesen, solange keine belastbare Messung für den konkreten Fall
vorliegt.

## Nicht zulässig

- vertrauliche Organisationslisten oder interne Use Cases,
- aus Gesprächen erinnerte, aber nicht öffentlich belegte Details,
- personenbezogene CRM- oder Outreach-Daten in Forschungsartefakten,
- Holdout-Ergebnisse im Memory,
- kuratierte Kandidaten nur in einem Architekturarm,
- nachträglich ergänzte Quellen zur Rettung eines einzelnen Ergebnisses,
- eine vorgegebene Startquelle oder ein vorgegebener Kandidat nur für einen Arm.

## Reifezustand eines Auftrags

- `draft_not_ready`: Organisationsname oder ein ausreichend konkreter Suchprompt
  fehlt beziehungsweise verletzt die Public-only-Regel.
- `ready`: Organisation, Suchprompt, Aufgabenzeitpunkt und serverseitige Hashes
  sind vollständig; derselbe kanonische Auftrag kann beiden Armen übergeben
  werden.

Nur `ready` darf technisch einen bezahlten Lauf starten. Nach dem Lauf werden
alle von den Armen gefundenen Quellen mit URL, Abrufzeitpunkt,
Inhaltsfingerabdruck und Claim-Zuordnung archiviert. Ein Lauf gehört erst nach
vollständigem Aufgaben- und Ausgabemanifest zur konfirmatorischen Stichprobe.
