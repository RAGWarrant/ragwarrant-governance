# Copyright 2026 RAGWarrant contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import os
import urllib.error
import urllib.request
from dataclasses import dataclass

from ragwarrant.generators.azure_openai import AzureOpenAIGenerator
from ragwarrant.generators.base import Generator, GeneratorUnavailable
from ragwarrant.generators.hosted_openai import HostedOpenAIGenerator
from ragwarrant.generators.local_openai_compatible import LocalOpenAICompatibleGenerator
from ragwarrant.generators.ollama import OllamaGenerator


@dataclass(frozen=True)
class GeneratorDiscovery:
    provider: str
    model: str
    available: bool
    local_or_hosted: str
    status: str
    instructions: str
    generator: Generator | None = None


def discover_generator(*, dry_run: bool = False) -> GeneratorDiscovery:
    provider = os.environ.get("RAGWARRANT_GENERATOR_PROVIDER", "none").strip() or "none"
    model = os.environ.get("RAGWARRANT_GENERATOR_MODEL", "").strip()
    if provider == "none":
        return GeneratorDiscovery(
            provider="none",
            model="",
            available=False,
            local_or_hosted="none",
            status="GEN_LLM_VALIDATION_BLOCKED_NO_GENERATOR",
            instructions="Set RAGWARRANT_GENERATOR_PROVIDER to ollama, local_openai_compatible, openai, or azure_openai.",
        )
    if not model and provider not in {"azure_openai"}:
        return GeneratorDiscovery(
            provider=provider,
            model="",
            available=False,
            local_or_hosted="local" if provider in {"ollama", "local_openai_compatible"} else "hosted",
            status="GEN_LLM_VALIDATION_BLOCKED_NO_MODEL_CREDENTIALS",
            instructions="Set RAGWARRANT_GENERATOR_MODEL to a pinned model name.",
        )
    try:
        if provider == "ollama":
            base_url = os.environ.get("RAGWARRANT_OLLAMA_BASE_URL", "http://localhost:11434")
            generator = OllamaGenerator(base_url=base_url)
            if not dry_run:
                models = generator.available_models(timeout_s=2.0)
                if model not in models:
                    raise GeneratorUnavailable(f"configured Ollama model is not available: {model}")
            return GeneratorDiscovery(provider=provider, model=model, available=not dry_run, local_or_hosted="local", status="available" if not dry_run else "dry_run_not_called", instructions="", generator=generator)
        if provider == "local_openai_compatible":
            base_url = os.environ.get("RAGWARRANT_LOCAL_OPENAI_BASE_URL", "http://localhost:11434/v1")
            if not dry_run:
                urllib.request.urlopen(f"{base_url.rstrip('/')}/models", timeout=2.0).close()
            generator = LocalOpenAICompatibleGenerator(
                base_url=base_url,
                api_key=os.environ.get("RAGWARRANT_LOCAL_OPENAI_API_KEY", "local-not-secret"),
            )
            return GeneratorDiscovery(provider=provider, model=model, available=not dry_run, local_or_hosted="local", status="available" if not dry_run else "dry_run_not_called", instructions="", generator=generator)
        if provider == "openai":
            if not os.environ.get("OPENAI_API_KEY"):
                raise GeneratorUnavailable("OPENAI_API_KEY is not configured")
            return GeneratorDiscovery(provider=provider, model=model, available=not dry_run, local_or_hosted="hosted", status="available" if not dry_run else "dry_run_not_called", instructions="", generator=None if dry_run else HostedOpenAIGenerator())
        if provider == "azure_openai":
            deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT", "")
            if not (os.environ.get("AZURE_OPENAI_ENDPOINT") and os.environ.get("AZURE_OPENAI_API_KEY") and deployment):
                raise GeneratorUnavailable("Azure OpenAI endpoint, key, and deployment are required")
            return GeneratorDiscovery(provider=provider, model=model or deployment, available=not dry_run, local_or_hosted="hosted", status="available" if not dry_run else "dry_run_not_called", instructions="", generator=None if dry_run else AzureOpenAIGenerator())
    except (GeneratorUnavailable, urllib.error.URLError, TimeoutError) as exc:
        return GeneratorDiscovery(
            provider=provider,
            model=model,
            available=False,
            local_or_hosted="local" if provider in {"ollama", "local_openai_compatible"} else "hosted",
            status="GEN_LLM_VALIDATION_BLOCKED_NO_GENERATOR" if provider in {"ollama", "local_openai_compatible"} else "GEN_LLM_VALIDATION_BLOCKED_NO_MODEL_CREDENTIALS",
            instructions=str(exc),
        )
    return GeneratorDiscovery(
        provider=provider,
        model=model,
        available=False,
        local_or_hosted="unknown",
        status="GEN_LLM_VALIDATION_BLOCKED_NO_GENERATOR",
        instructions=f"Unsupported provider: {provider}",
    )
