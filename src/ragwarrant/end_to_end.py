from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RAGPolicy:
    chunk_size: int = 80
    chunk_overlap: int = 0
    retriever_type: str = "sparse"
    top_k: int = 3
    reranker_enabled: bool = False
    reranker_depth: int = 5
    context_compression: bool = False
    citation_required: bool = True
    abstention_threshold: float = 0.5
    generator_model: str = "deterministic_fake"
    answer_length_policy: str = "short"


class Generator(Protocol):
    def generate(self, query: str, contexts: list[str], policy: RAGPolicy) -> str: ...


def mini_corpus() -> dict[str, str]:
    return {
        "doc-a": "RAGWarrant evaluates retrieval policies with cost and latency constraints.",
        "doc-b": "No-fork search is the default candidate because it avoids expensive branching.",
        "doc-c": "Protected examples prevent regressions on known important behaviors.",
        "doc-d": "Adaptive compute remains research-only unless hard subsets justify escalation.",
    }


def chunk_documents(corpus: dict[str, str], policy: RAGPolicy) -> list[dict[str, str]]:
    chunks = []
    for doc_id, text in sorted(corpus.items()):
        step = max(1, policy.chunk_size - policy.chunk_overlap)
        for start in range(0, len(text), step):
            chunk = text[start : start + policy.chunk_size]
            if chunk:
                chunks.append({"chunk_id": f"{doc_id}:{start}", "doc_id": doc_id, "text": chunk})
    return chunks


def sparse_retrieve(query: str, chunks: list[dict[str, str]], policy: RAGPolicy) -> list[dict[str, str]]:
    terms = set(query.lower().split())
    scored = []
    for chunk in chunks:
        text_terms = set(chunk["text"].lower().replace(".", "").split())
        score = len(terms & text_terms)
        scored.append({**chunk, "score": score})
    return sorted(scored, key=lambda row: (-row["score"], row["chunk_id"]))[: policy.top_k]


class DeterministicGenerator:
    def generate(self, query: str, contexts: list[str], policy: RAGPolicy) -> str:
        if not contexts or max(len(set(query.lower().split()) & set(ctx.lower().split())) for ctx in contexts) == 0:
            return "I do not have enough evidence to answer." if policy.abstention_threshold >= 0.5 else "Insufficient evidence."
        citation = " [citation]" if policy.citation_required else ""
        return f"{contexts[0].split('.')[0]}{citation}"


def evaluate_answer(answer: str, contexts: list[str], policy: RAGPolicy) -> dict[str, float]:
    joined = " ".join(contexts).lower()
    answer_terms = set(answer.lower().replace("[citation]", "").replace(".", "").split())
    evidence_terms = set(joined.replace(".", "").split())
    overlap = len(answer_terms & evidence_terms) / max(1, len(answer_terms))
    citation = 1.0 if ("[citation]" in answer) == policy.citation_required else 0.5
    abstention = 1.0 if "not have enough evidence" in answer else 0.0
    return {
        "faithfulness_proxy": overlap,
        "citation_support_proxy": citation,
        "abstention_accuracy_proxy": abstention,
        "raw_quality": 0.65 * overlap + 0.25 * citation + 0.10 * (1.0 - abstention),
    }


def run_pipeline(policy: RAGPolicy, queries: list[str] | None = None) -> dict[str, float]:
    queries = queries or [
        "What does RAGWarrant optimize?",
        "Why use no fork?",
        "How are protected examples used?",
    ]
    chunks = chunk_documents(mini_corpus(), policy)
    generator = DeterministicGenerator()
    metrics = []
    latencies = []
    for query in queries:
        start = time.perf_counter()
        retrieved = sparse_retrieve(query, chunks, policy)
        if policy.reranker_enabled:
            retrieved = sorted(retrieved, key=lambda row: (-row["score"], row["chunk_id"]))[
                : policy.reranker_depth
            ][: policy.top_k]
        contexts = [row["text"] for row in retrieved]
        answer = generator.generate(query, contexts, policy)
        latencies.append(time.perf_counter() - start + 0.001 * policy.top_k)
        metrics.append(evaluate_answer(answer, contexts, policy))
    avg = {key: sum(row[key] for row in metrics) / len(metrics) for key in metrics[0]}
    avg["queries_evaluated"] = float(len(queries))
    avg["cost"] = 0.02 + 0.01 * policy.top_k + (0.03 if policy.reranker_enabled else 0.0)
    avg["latency_p50"] = sorted(latencies)[len(latencies) // 2]
    avg["latency_p95"] = max(latencies)
    avg["latency_p99"] = max(latencies) * 1.05
    avg["protected_subset_score"] = avg["raw_quality"]
    avg["overall_utility"] = avg["raw_quality"] - 0.25 * avg["cost"] - 0.10 * avg["latency_p95"]
    avg["cost_adjusted_utility"] = avg["overall_utility"]
    return avg

