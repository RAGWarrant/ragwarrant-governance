from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

from ragwarrant.generators.base import GenerationResult, GeneratorUnavailable
from ragwarrant.generators.util import estimate_tokens, hash_text, write_local_answer


class OllamaGenerator:
    provider = "ollama"

    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def available_models(self, timeout_s: float = 2.0) -> list[str]:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=timeout_s) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GeneratorUnavailable(str(exc)) from exc
        return [model.get("name", "") for model in payload.get("models", []) if model.get("name")]

    def thinking_enabled(self, model: str) -> bool | None:
        configured = os.environ.get("RAGWARRANT_OLLAMA_THINK")
        if configured is not None:
            return configured.strip().lower() in {"1", "true", "yes", "on"}
        if model.lower().startswith(("qwen3", "gpt-oss")):
            return False
        return None

    def use_chat_endpoint(self, model: str) -> bool:
        configured = os.environ.get("RAGWARRANT_OLLAMA_ENDPOINT")
        if configured is not None:
            return configured.strip().lower() == "chat"
        return model.lower().startswith("gpt-oss")

    def generate(
        self,
        prompt: str,
        *,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_s: float,
    ) -> GenerationResult:
        if model not in self.available_models(timeout_s=timeout_s):
            raise GeneratorUnavailable(f"ollama model not available: {model}")
        use_chat = self.use_chat_endpoint(model)
        payload = (
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }
            if use_chat
            else {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }
        )
        think = self.thinking_enabled(model)
        if think is not None:
            payload["think"] = think
        request = urllib.request.Request(
            f"{self.base_url}/api/{'chat' if use_chat else 'generate'}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        start = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise GeneratorUnavailable(str(exc)) from exc
        latency_ms = (time.perf_counter() - start) * 1000.0
        answer = body.get("message", {}).get("content", "") if use_chat else body.get("response", "")
        local_path = write_local_answer(self.provider, model, answer)
        input_tokens = estimate_tokens(prompt)
        output_tokens = estimate_tokens(answer)
        return GenerationResult(
            provider=self.provider,
            model=model,
            model_version_or_digest=body.get("model", model),
            prompt_hash=hash_text(prompt),
            answer_hash=hash_text(answer),
            answer_char_count=len(answer),
            answer_token_estimate=output_tokens,
            latency_ms=latency_ms,
            input_token_estimate=input_tokens,
            output_token_estimate=output_tokens,
            cost_units=2.0 + 0.1 * input_tokens / 1000.0 + 0.2 * output_tokens / 1000.0,
            finish_reason="stop" if body.get("done") else "unknown",
            error_type="",
            raw_answer_local_path=local_path,
        )
