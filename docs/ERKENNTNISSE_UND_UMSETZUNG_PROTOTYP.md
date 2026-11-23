# Erkenntnisse und ihre Umsetzung im Prototyp VeriScout

Chronologische Übersicht vom 5. September bis 18. Oktober 2026. Jede Zeile nennt zuerst die Erkenntnis und ihre Herkunft (Kapitel der Masterarbeit, Literatur oder Probelauf), dann die konkrete Umsetzung im Code und den Test, der sie absichert. Alle genannten Dateien liegen im Ordner `prototype_push`. Stand: 174 von 174 Tests bestanden (18.10.2026).

## 1. Ausgangslage: Entwicklungsläufe vom 5. September 2026

| Nr. | Erkenntnis (Herkunft) | Umsetzung im Prototyp | Nachweis |
|---|---|---|---|
| 1 | Ein einzelner Modellaufruf mit Websuche braucht 27.736 bis 32.776 Eingabe- und bis 6.000 Ausgabetokens. Die damaligen Grenzen (20.000 / 4.000) konnten keinen Lauf tragen (Kap. 7.2.2, Pilotdaten). | Budget je Arm neu kalibriert, zunächst 120.000 Eingabe-, 16.000 Ausgabe-, 8.000 Reasoning-Tokens, 8 Websuchen, 12 Quellenabrufe, 3 Kandidaten, 0,60 USD (`core.py`, Profil `BUDGET_PROFILE_VERSION`). | `test_default_budget_covers_observed_pilot_consumption` |
| 2 | Überzieht der Anbieter in Stufe 1 das Websuchlimit (4 statt 3), wurde die Verifikation komplett blockiert. Gemessen hätte der Versuch dann Anbieterverhalten statt Architektur (Kap. 6.6). | Jede der beiden Modellstufen bekommt eine fest reservierte Hälfte des Ausgabe- und Websuchbudgets, für SAS-2 und MAS identisch (`resource_budget.py`, `reserve_stages`). Überzug wird als Protokollabweichung je Stufe gespeichert; Schalter `SCOUTREF_EVAL_WEB_OVERRUN_POLICY=fail` für die strenge Sensitivitätsanalyse. | `test_stage_one_tool_overrun_does_not_block_reserved_second_stage`, `test_strict_overrun_policy_restores_fail_closed_behaviour` |
| 3 | Der Self-Review wurde bei 6.000 Tokens abgeschnitten, weil er das ganze Kandidatenschema neu schreiben musste (Kap. 7.2.2). | Gemeinsamer kompakter Prüfvertrag für Self-Review und Verifier: Urteil je Kandidat und je Aussage, mit Quelle und wörtlichem Auszug (`review_contract.py`). | `test_both_review_stages_share_rules_and_output_contract` |

## 2. Analyse vom 13. Oktober 2026 (Abgleich Arbeit ↔ Code)

| Nr. | Erkenntnis (Herkunft) | Umsetzung im Prototyp | Nachweis |
|---|---|---|---|
| 4 | Kein Test zeigte, dass ein echter Treffer die ganze Kette durchlaufen *kann*; TP = 0 im Zehn-Fall-Test war konstruktionsbedingt (Kap. 7.2.3). | End-to-End-Test mit simuliertem Modell und gespeicherten Webseiten: Ein vollständig belegter Kandidat erreicht in beiden Armen die Empfehlung, ohne Belege keiner. | `test_fully_supported_candidate_reaches_positive_decision_in_both_arms`, `test_unsupported_review_blocks_positive_decision` |
| 5 | Die Arbeit verlangt, dass gescheiterte Läufe in der Primäranalyse als 0 zählen; der Auswerter ließ sie weg (Kap. 7.3.2, OFFEN in 7.2.1). | Primärgröße „intention to treat“: alle zugewiesenen Läufe, Fehler und Enthaltungen = 0; dazu $\overline{Q}_a$ und $Q^{alle}_{a,r}$ (`evaluation_analysis.py`). Bedingte Analyse bleibt Sekundärgröße. | `test_itt_counts_technical_failures_as_zero_and_keeps_pair`, `test_all_replicates_success_differs_from_mean_success` |
| 6 | Wortgleicher Abgleich ließ echte Belege an Satzzeichen und Zeilenumbrüchen scheitern; PDFs wurden still nicht geprüft (Kap. 6.6). | Unscharfer Auszugsabgleich (≥ 90 % der Wörter in gleicher Reihenfolge, ≥ 6 Wörter), Protokoll je Quelle `exact`/`fuzzy`, PDF-Status `pdf_not_parsed` (`evidence_resolver.py`). Schalter `SCOUTREF_EXCERPT_MATCH_MODE=exact` für die Sensitivitätsanalyse. | `test_fuzzy_excerpt_accepts_formatting_drift_but_not_shuffled_keywords`, `test_exact_mode_keeps_previous_strict_behaviour` |
| 7 | Fairness: SAS-2 darf Quellen beider Aufrufe nutzen, der MAS-Verifier nur eigene. Das muss offengelegt und abgesichert werden (Kap. 6.2). | Quellen-Kennzeichnungen entstehen in beiden Armen nur aus den in Stufe 2 gestützten Aussagen; die Asymmetrie bleibt als Teil der Behandlung bestehen und wird protokolliert. | `test_compact_review_never_inherits_unsupported_stage_one_fields` |
| 8 | Selbstkorrektur ohne externe Information bewirkt wenig, getrennt beantwortete Prüffragen helfen (Huang et al. 2024; Dhuliawala et al. 2024; Kap. 7.3.2, H3). | Der Verifier bekommt nur die Prüfliste ohne Begründung und Quellen des Scouts (Informationsisolation); beide Arme bekommen dieselbe Prüfliste mit Aussagekennungen. | `test_verifier_handoff_uses_candidate_id_claims_and_no_scout_rationale` |

## 3. Abgleich mit der überarbeiteten Arbeit, 16. Oktober 2026

| Nr. | Erkenntnis (Herkunft) | Umsetzung im Prototyp | Nachweis |
|---|---|---|---|
| 9 | Vier fachliche Zielzustände (Empfehlung, Ablehnung, Enthaltung, technischer Fehler) waren in API, Oberfläche und Speicherung nicht einheitlich (Kap. 5, FA6; Kap. 6.4). | Jede Entscheidung trägt `decision_state` mit Begründung, gebildet in der Reihenfolge des Referenzmodells (`pipeline.py`, `_decision_state`). | `test_contradiction_yields_rejection_state`, `test_unsupported_review_yields_abstention_state` |
| 10 | Bei wenigen Aufgaben unterschätzen übliche Intervalle die Unsicherheit; für gepaarte, gruppierte Daten erreichen bayesianische Verfahren die angestrebte Überdeckung (Bowyer et al. 2025; Kap. 4.6, 7.3.2). | Bayesianisches Intervall der Differenz MAS minus SAS-2: bayesianisches Bootstrap über Aufgaben (Rubin 1981) mit Beta-Posterior je Aufgabe und Arm; Wiederholungen bleiben gebündelt (`bayesian_paired_difference`). | `test_bayesian_interval_widens_for_few_tasks_and_detects_clear_effect` |
| 11 | Entscheidungsregel: Eine Konfiguration ist nur überlegen, wenn sie mehr Treffer liefert, ohne dass die Precision über eine Grenze hinaus sinkt (Kap. 5.5, 7.3.2, H1/H2). | Parameter `EVAL_NI_MARGIN_PRECISION = −0,10` und `EVAL_MIN_IMPROVEMENT = 0,10` (von David bestätigt); Auswerter gibt Urteil zu H1 und H2 aus. Ein Treffer zählt nur, wenn ein vom System empfohlener Kandidat qualifiziert ist. | `test_abstention_with_qualified_candidate_scores_zero` |
| 12 | H3 braucht eine Messgröße: Verwirft oder widerlegt die getrennte Prüfung häufiger als die Selbstprüfung? (Kap. 7.3.2) | Je Arm werden verworfene Kandidaten und gestützte, widerlegte, unbestätigte Aussagen gezählt und im Auswerter als Quoten berichtet (`review_mechanics`). | `test_positive_run_reports_unified_state_mechanics_and_sensitivities` |
| 13 | Die Sensitivitätsanalyse „MAS mit Quellen der Scoutingrolle“ war vorgesehen, aber nicht implementiert (Kap. 6.2). | Für jeden MAS-Lauf kostenfrei mitberechnet: Scout-Aussagen zählen, wenn der Verifier sie nicht widerlegt (`merge_scout_evidence`). Dazu Sensitivität „wortgleicher Abgleich“ und „strikte Websuchregel“. | `test_unsupported_review_yields_abstention_state` (Sensitivitätsteil), `test_strict_web_sensitivity_counts_overrun_arm_as_zero` |
| 14 | Verblindung: Die Laufreihenfolge (AB/BA) darf aus dem Blindpaket nicht ablesbar sein (Kap. 7.3.2). | Reihenfolge der Arme im Blindpaket wird zufällig gemischt (`annotation_package`). | `test_blind_package_order_is_shuffled` |
| 15 | Prüfgerechte Darstellung ohne Überflüssiges (QA5); Laufdokumentation muss rekonstruierbar sein (QA3). | Neue Oberfläche mit vier Bereichen (Suchauftrag, Ergebnis, Bewertung, Transferprüfung). Jeder Lauf wird als Laufdatei gespeichert und lässt sich ohne API-Kosten wieder öffnen (`server.py`, `static/`). | im Browser geprüft |
| 16 | Ein Ergebnis nur mit einem Modell kann eine Eigenheit dieses Modells sein (Kap. 7.4; Kim et al. 2026 vergleichen mehrere Modellfamilien). | Zweite Modellfamilie: Anbindung an Claude Sonnet 5.5 (`llm_anthropic.py`); SAS-2, Scouting und Verifikation nutzen weiter zwingend dieselbe Kennung, keine automatischen Ausweichmodelle. | `test_adapter_maps_text_citations_usage_and_resumes_pause_turn`, `test_truncated_or_refused_answer_is_not_completed` |

## 4. Probeläufe vom 16. Oktober 2026 (14 bezahlte Läufe, rund 3,70 USD)

| Nr. | Erkenntnis (Herkunft) | Umsetzung im Prototyp | Nachweis |
|---|---|---|---|
| 17 | Harmlose Weiterleitungen (z. B. `/de/start/` → `/de/start`) wurden blockiert; echte Quellen galten als nicht abrufbar. | Resolver folgt bis zu fünf Weiterleitungen, nur zu öffentlichen Zielen; HTTP-Status je Quelle gespeichert. | Neubewertung der Probeläufe |
| 18 | Eine einzige Quelle mit 403 oder 404 machte den ganzen Arm zum technischen Fehler. | Nicht abrufbare Quellen wirken nur beim betroffenen Kandidaten (Enthaltung); technischer Fehler nur, wenn keine einzige Quelle abrufbar war. | Neubewertung: 6 von 6 GPT-Armen gültig |
| 19 | Modelle erfinden eigene Kennungen für das Startup („wesort-ai-gmbh“); alle Startup-Aussagen galten als falsch zugeordnet. | Stimmt der Name überein, wird deterministisch die interne Kennung gesetzt, für beide Arme gleich (`_rebind_subjects`). | Neubewertung |
| 20 | Modelle kürzen Auszüge mit „…“. | Teilstücke werden einzeln gesucht (je ≥ 3, zusammen ≥ 6 Wörter); der Prüfvertrag verlangt zusätzlich zusammenhängende Auszüge. | Neubewertung |
| 21 | Claude antwortete viermal ohne jede Suche mit einer leeren Liste. | Der Rechercheauftrag verlangt für beide Modelle und Arme, zuerst zu suchen; leer ist nur nach Recherche zulässig. Nur der Text nach dem letzten Suchschritt zählt als Antwort. | `test_only_text_after_last_tool_block_is_the_answer` |
| 22 | Claude brauchte bis 130.109 Eingabetokens je Arm, GPT höchstens 82.089. | Eingabegrenze für beide Modelle auf 160.000 angehoben (von David freigegeben); Kostenrahmen 0,60 USD je Arm bleibt eingehalten. | `test_default_budget_covers_observed_pilot_consumption` |
| 23 | Gespeicherte Modellantworten sollen nach einer Regeländerung ohne neue Kosten erneut geprüft werden können. | `scripts/reevaluate_run.py`: Neubewertung als eigener, gekennzeichneter Lauf; das Original bleibt unverändert. | Neubewertungen in `artifacts/runs/` |
| 24 | Befund: In Stufe 2 meldet GPT 50 von 54 Aussagen als gestützt, die technische Prüfung bestätigt deutlich weniger. | Bestätigt die Entwurfsentscheidung, Belege außerhalb des Modells zu prüfen (Kap. 6.1). Keine Codeänderung nötig. | Laufdateien |

## 5. Rückmeldungen zur Arbeit, 16. bis 18. Oktober 2026

| Nr. | Erkenntnis (Herkunft) | Umsetzung im Prototyp | Nachweis |
|---|---|---|---|
| 25 | PUSH und PULL sind in Kap. 5.2 und 6.1 beschrieben, der Prototyp kannte nur PUSH. | Auswahl der Auftragsart in der Oberfläche; bei PULL zusätzlich das vom Unternehmen öffentlich benannte Suchfeld, das zuerst zu belegen ist. Auftragsart und Suchfeld gehören zum Auftrags-Hash (`experiment_protocol.py`). | `test_push_and_pull_produce_distinct_identical_for_both_arms_prompts`, `test_pull_task_reaches_both_arms_unchanged` |
| 26 | Ein empfohlenes Startup muss noch eigenständig existieren, darf nicht übernommen, insolvent oder eingestellt sein (Rückmeldung David, 18.10.). Bisher nicht abgedeckt. | Die Prüfstufe beider Arme beurteilt den Fortbestand (`operating_status`: aktiv, übernommen, insolvent, eingestellt, ungeklärt). Ein belegter Hinweis auf Übernahme, Insolvenz oder Einstellung ist ein Gegenbeleg zur Dimension „Unternehmenstyp und Gründung“ und führt zur Ablehnung; ohne Urteil „aktiv“ bleibt die Dimension offen (Enthaltung). | `test_acquired_startup_is_rejected_in_both_arms`, `test_unknown_operating_status_blocks_recommendation` |
| 27 | Der Name soll zur Belegprüfung passen (Rückmeldung David). | Umbenennung in **VeriScout** in Oberfläche, Server, Laufprotokoll, Resolver-Kennung und Dokumentation. | `test_scouting_contract_is_public_only_and_configuration_driven` |
| 28 | David will selbst Live-Läufe starten. | Startskript `scripts/start_live_review.py` mit Modellwahl (`--model`), lokaler Kostengrenze (`--budget-usd`, Standard 10 USD) und dem Profil der Hauptstudie (3 Kandidaten, 160.000 Eingabetokens). | `test_development_profile_is_bounded_and_disables_external_writes` |

## 6. Noch nicht umgesetzt

- **Kontaminationskontrolle** (Kleinert und Urbig 2026): ob ein Startup vor dem Wissensstichtag des Modells bekannt war, wird noch nicht erfasst.
- **Abgleich mit ausgelassenen Auftragsbedingungen** (Kap. 6.3, „nächste Entwicklungsstufe“): Bedingungen aus dem Suchauftrag, etwa eine Mindestmenge, werden noch nicht eigens geprüft.
- **PDF-Texte** werden nicht ausgelesen, sondern nur gekennzeichnet.
- **Projektexport der Transferprüfung** unterstützt nur PUSH.
- **Heterogenes MAS** (Scout und Verifier aus verschiedenen Modellfamilien) ist vorbereitet, aber nicht als eigene Bedingung eingebaut.
