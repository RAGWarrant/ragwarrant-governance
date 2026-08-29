from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Protocol


class GeneratorUnavailable(RuntimeError):
    """Raised when a configured generator cannot be used."""


@dataclass(frozen=True)
class GenerationResult:
    provider: str
    model: str
    model_version_or_digest: str
    prompt_hash: str
    answer_hash: str
    answer_char_count: int
    answer_token_estimate: int
    latency_ms: float
    input_token_estimate: int
    output_token_estimate: int
    cost_units: float
    finish_reason: str
    error_type: str
    raw_answer_local_path: str

    def sanitized_dict(self) -> dict[str, object]:
        payload = asdict(self)
        if self.raw_answer_local_path:
            payload["raw_answer_local_path"] = "<gitignored-local-answer-path>"
        return payload


class Generator(Protocol):
    provider: str

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_s: float,
    ) -> GenerationResult:
        ...
