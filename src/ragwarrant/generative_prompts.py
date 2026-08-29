from __future__ import annotations

from ragwarrant.generators.util import hash_text


def build_rag_prompt(*, question_text: str, evidence_items: list[dict[str, str]]) -> tuple[str, str]:
    evidence_lines = []
    for item in evidence_items:
        evidence_id = item.get("evidence_id", "evidence")
        text = item.get("text", "")
        evidence_lines.append(f"[{evidence_id}] {text}")
    prompt = (
        "You are answering a retrieval-augmented question.\n\n"
        "Use only the provided evidence. Do not include hidden reasoning, analysis, or scratch work. "
        "Return a final answer even when uncertain. If the evidence is insufficient, answer exactly: "
        "INSUFFICIENT_EVIDENCE. Never return a blank response.\n\n"
        f"Question:\n{question_text}\n\n"
        "Evidence:\n"
        + "\n".join(evidence_lines)
        + "\n\nReturn exactly two lines:\nANSWER: <concise answer or INSUFFICIENT_EVIDENCE>\nCITATIONS: <evidence ids or none>"
    )
    return prompt, hash_text(prompt)


def build_answer_emission_repair_prompt(*, question_text: str, evidence_items: list[dict[str, str]]) -> tuple[str, str]:
    evidence_lines = []
    for item in evidence_items:
        evidence_id = item.get("evidence_id", "evidence")
        text = item.get("text", "")
        evidence_lines.append(f"[{evidence_id}] {text}")
    prompt = (
        "The previous model response was blank or unparsable. Produce only the final answer now.\n\n"
        "Rules:\n"
        "- Use only the provided evidence.\n"
        "- Do not include reasoning, analysis, markdown, or explanations.\n"
        "- If evidence is insufficient, output exactly: INSUFFICIENT_EVIDENCE.\n"
        "- Do not leave the answer blank.\n\n"
        f"Question:\n{question_text}\n\n"
        "Evidence:\n"
        + "\n".join(evidence_lines)
        + "\n\nFinal answer:"
    )
    return prompt, hash_text(prompt)


def sanitized_prompt_record(*, prompt_hash: str, evidence_count: int, question_hash: str) -> dict[str, object]:
    return {
        "prompt_hash": prompt_hash,
        "question_hash": question_hash,
        "evidence_count": evidence_count,
        "prompt_text_exported": False,
        "raw_question_exported": False,
        "raw_evidence_exported": False,
    }
