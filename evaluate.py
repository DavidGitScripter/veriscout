"""
evaluate.py — formative, kuenstliche Evaluation am synthetischen Korpus.

Misst die Matching-Guete (Precision/Recall/F1), die Over-Match-Rate (faelschlich
als ausreichend gemeldete Kandidaten) und die Label-Genauigkeit. Die Ablation
zeigt den Wertbeitrag des Guardrails (mit vs. ohne).
Vorhersage = 'mindestens ein ausreichender Match' (Empfehlung Pilot).
Referenzurteil = reference_sufficient aus dem synthetischen Korpus.
"""
from __future__ import annotations

import json
from core import Candidate, Config, Recommendation
from pipeline import Pipeline


def load_corpus(path: str = None):
    path = path or Config.SEED_CORPUS
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            reference = {
                "sufficient": d.pop("reference_sufficient", None),
                "organization_id": d.pop(
                    "reference_organization_id", None),
                "reason": d.pop("reference_reason", ""),
            }
            srcs = d.pop("sources", [])
            from core import Source
            c = Candidate(**{k: v for k, v in d.items()
                             if k in Candidate.__dataclass_fields__})
            c.discovery_mode = "synthetic"
            c.verification_status = "synthetic_case"
            c.sources = [Source(**s) for s in srcs]
            items.append((c, reference))
    return items


def run_eval(pipeline: Pipeline, use_guardrail: bool = True) -> dict:
    items = load_corpus()
    tp = fp = fn = tn = 0
    rows = []
    for c, reference in items:
        dec = pipeline.scout(c, use_guardrail=use_guardrail, use_memory=False)
        pred = (dec.recommendation == Recommendation.PILOT)
        truth = bool(reference["sufficient"])
        if pred and truth: tp += 1
        elif pred and not truth: fp += 1
        elif not pred and truth: fn += 1
        else: tn += 1
        rows.append({"name": c.name, "pred_sufficient": pred,
                     "reference": truth,
                     "score": dec.best_score, "rec": dec.recommendation.value,
                     "abstain": dec.abstained})
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    over_match = fp / (fp + tn) if (fp + tn) else 0.0
    acc = (tp + tn) / len(items) if items else 0.0
    return {"n": len(items), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
            "over_match_rate": round(over_match, 3), "accuracy": round(acc, 3),
            "rows": rows}


def run_ablation(pipeline: Pipeline) -> dict:
    return {"mit_guardrail": run_eval(pipeline, use_guardrail=True),
            "ohne_guardrail": run_eval(pipeline, use_guardrail=False)}
