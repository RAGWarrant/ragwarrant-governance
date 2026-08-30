from __future__ import annotations

import re
from collections import Counter


def normalize_answer(answer: str) -> str:
    text = answer.lower()
    text = re.sub(r"\b(a|an|the)\b", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return " ".join(text.split())


def exact_match(prediction: str, reference: str) -> float:
    return 1.0 if normalize_answer(prediction) == normalize_answer(reference) else 0.0


def token_f1(prediction: str, reference: str) -> float:
    pred_tokens = normalize_answer(prediction).split()
    ref_tokens = normalize_answer(reference).split()
    if not pred_tokens and not ref_tokens:
        return 1.0
    if not pred_tokens or not ref_tokens:
        return 0.0
    common = Counter(pred_tokens) & Counter(ref_tokens)
    overlap = sum(common.values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred_tokens)
    recall = overlap / len(ref_tokens)
    return 2 * precision * recall / (precision + recall)


def containment(prediction: str, reference: str) -> float:
    pred = normalize_answer(prediction)
    ref = normalize_answer(reference)
    if not pred or not ref:
        return 0.0
    return 1.0 if ref in pred or pred in ref else 0.0


def final_hotpotqa_quality(
    *,
    answer_f1: float,
    exact_match_score: float,
    supporting_fact_title_recall: float,
    supporting_fact_sentence_recall: float,
    evidence_efficiency: float,
    abstention_correctness: float,
) -> float:
    return (
        0.45 * answer_f1
        + 0.15 * exact_match_score
        + 0.20 * supporting_fact_title_recall
        + 0.10 * supporting_fact_sentence_recall
        + 0.05 * evidence_efficiency
        + 0.05 * abstention_correctness
    )
