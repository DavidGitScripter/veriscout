# Memory-Ablation

## Ehrliche Ausgangsthese

Memory kann wiederkehrendes Scouting verbessern, etwa durch Dublettenhinweise,
frühere menschliche Ablehnungsgründe oder bewährte Suchstrategien. Es ist jedoch
weder grundsätzlich ein MAS-Merkmal noch automatisch qualitätssteigernd. Der
vorhandene Memory-Service verändert keine Scores oder Schwellen und darf nicht
als eigener Sachbeleg verwendet werden.

## Kausales Design

```text
                    Memory aus     Frozen Memory
starker SAS-2           A               B
MAS                     C               D
```

Berichtet werden:

- Architektureffekt ohne Memory: `C − A`
- Memory-Effekt im SAS: `B − A`
- Memory-Effekt im MAS: `D − C`
- MAS-spezifische Interaktion: `(D − C) − (B − A)`

Nur eine praktisch relevante positive Interaktion stützt die Aussage, dass
Memory gerade der Rollenaufteilung des MAS zusätzlichen Nutzen bringt.

## Fairnessregeln

- ein eingefrorener Snapshot ausschließlich aus Entwicklungsfällen,
- kein Schreiben während eines Evaluationslaufs,
- identischer deterministischer Abruf für SAS und MAS,
- identisches Top-k- und Memory-Tokenlimit,
- Ausschluss derselben Task-, Relations- und Kandidaten-ID,
- Ausschluss späterer Ereignisse und sämtlicher Holdout-Urteile,
- tatsächliche Memory-, Input- und Gesamttokens berichten,
- gleiche Backbones, Werkzeuge und Gesamtobergrenzen.

## Diagnostische Kontrollen

Neben sinnvollem Memory werden auf Entwicklungsdaten kleine Placebo-Tests
durchgeführt:

- irrelevante Einträge,
- veraltete Einträge,
- widersprüchliche Einträge.

Verbessert Memory nur bei passendem, aktuellem Inhalt und bleibt das System bei
Widersprüchen vorsichtig, ist die Erklärung belastbarer als ein bloßer
Leistungsanstieg mit zusätzlichem Kontext.

## Aussagegrenze

Bei einer einmaligen Suche kann Memory ohne Nutzen bleiben. Das ist kein
Fehlschlag des Experiments, sondern eine mögliche Erkenntnis. Ein allgemeiner
Memory-Vorteil, der SAS und MAS gleichermaßen hilft, begründet keine
Multi-Agentenarchitektur.
