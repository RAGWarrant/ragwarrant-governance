from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from ragwarrant.generators.base import GenerationResult, GeneratorUnavailable
from ragwarrant.generators.util import estimate_tokens, hash_text, write_local_answer


class LocalOpenAICompatibleGenerator:
    provider = "local_openai_compatible"

    def __init__(self, *, base_url: str, api_key: str = "local-not-secret") -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_s: float,
    ) -> GenerationResult:
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GeneratorUnavailable(str(exc)) from exc
        latency_ms = (time.perf_counter() - start) * 1000.0
        answer = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        finish_reason = body.get("choices", [{}])[0].get("finish_reason") or "unknown"
        local_path = write_local_answer(self.provider, model, answer)
        input_tokens = estimate_tokens(prompt)
        output_tokens = estimate_tokens(answer)
        return GenerationResult(
            provider=self.provider,
            model=model,
            model_version_or_digest=model,
            prompt_hash=hash_text(prompt),
            answer_hash=hash_text(answer),
            answer_char_count=len(answer),
            answer_token_estimate=output_tokens,
            latency_ms=latency_ms,
            input_token_estimate=input_tokens,
            output_token_estimate=output_tokens,
            cost_units=2.0 + 0.1 * input_tokens / 1000.0 + 0.2 * output_tokens / 1000.0,
            finish_reason=finish_reason,
            error_type="",
            raw_answer_local_path=local_path,
        )
