from __future__ import annotations

import re
from dataclasses import dataclass


GENERATED_QUALITY_CLASSES = {
    "GENERATED_QUALITY_CRAG_LOCAL_EVALUATOR",
    "GENERATED_QUALITY_CRAG_PROXY_PLUS_EVIDENCE",
    "GENERATED_QUALITY_HOTPOTQA_ANSWER_LABELS_PLUS_SUPPORTING_FACTS",
    "GENERATED_QUALITY_BLOCKED_NO_SIGNAL",
}


def normalize_answer(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def token_f1(prediction: str, reference: str) -> float:
    pred = normalize_answer(prediction).split()
    ref = normalize_answer(reference).split()
    if not pred and not ref:
        return 1.0
    if not pred or not ref:
        return 0.0
    common = sum(min(pred.count(token), ref.count(token)) for token in set(pred))
    if common == 0:
        return 0.0
    precision = common / len(pred)
    recall = common / len(ref)
    return 2 * precision * recall / (precision + recall)


def exact_match(prediction: str, reference: str) -> float:
    return 1.0 if normalize_answer(prediction) == normalize_answer(reference) else 0.0


def containment(prediction: str, reference: str) -> float:
    pred = normalize_answer(prediction)
    ref = normalize_answer(reference)
    if not pred or not ref:
        return 0.0
    return 1.0 if ref in pred or pred in ref else 0.0


def generated_quality_score(
    *,
    answer_correctness_f1: float,
    answer_exact_match: float,
    answer_containment: float,
    evidence_support_score: float,
    citation_support_score: float,
    abstention_correctness: float,
) -> float:
    return (
        0.35 * answer_correctness_f1
        + 0.15 * answer_exact_match
        + 0.10 * answer_containment
        + 0.20 * evidence_support_score
        + 0.10 * citation_support_score
        + 0.10 * abstention_correctness
    )


@dataclass(frozen=True)
class QualitySignal:
    quality_class: str
    usable: bool
    reason: str


def assess_quality_signal(values: list[float]) -> QualitySignal:
    if not values:
        return QualitySignal("GENERATED_QUALITY_BLOCKED_NO_SIGNAL", False, "no generated quality values")
    if all(value == 0.0 for value in values):
        return QualitySignal("GENERATED_QUALITY_BLOCKED_NO_SIGNAL", False, "all generated quality values are zero")
    if len({round(value, 12) for value in values}) <= 1:
        return QualitySignal("GENERATED_QUALITY_BLOCKED_NO_SIGNAL", False, "generated quality values are constant")
    return QualitySignal("GENERATED_QUALITY_HOTPOTQA_ANSWER_LABELS_PLUS_SUPPORTING_FACTS", True, "usable generated quality variation present")
