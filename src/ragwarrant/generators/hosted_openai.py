from __future__ import annotations

import os

from ragwarrant.generators.base import GeneratorUnavailable
from ragwarrant.generators.local_openai_compatible import LocalOpenAICompatibleGenerator


class HostedOpenAIGenerator(LocalOpenAICompatibleGenerator):
    provider = "openai"

    def __init__(self) -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise GeneratorUnavailable("OPENAI_API_KEY is not configured")
        super().__init__(base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"), api_key=api_key)
