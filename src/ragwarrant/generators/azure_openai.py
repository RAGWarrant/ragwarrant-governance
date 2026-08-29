from __future__ import annotations

import os

from ragwarrant.generators.base import GeneratorUnavailable
from ragwarrant.generators.local_openai_compatible import LocalOpenAICompatibleGenerator


class AzureOpenAIGenerator(LocalOpenAICompatibleGenerator):
    provider = "azure_openai"

    def __init__(self) -> None:
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        deployment = os.environ.get("AZURE_OPENAI_DEPLOYMENT")
        version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-10-21")
        if not endpoint or not api_key or not deployment:
            raise GeneratorUnavailable("Azure OpenAI endpoint, key, and deployment are required")
        base_url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}"
        self.api_version = version
        super().__init__(base_url=base_url, api_key=api_key)
