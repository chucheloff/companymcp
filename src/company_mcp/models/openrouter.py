import json
from typing import Any

import httpx

from company_mcp.config import settings


class OpenRouterUnavailable(Exception):
    pass


class OpenRouterClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key

    async def extract_json(self, prompt: str, *, model: str | None = None) -> dict[str, Any]:
        if not self.api_key:
            raise OpenRouterUnavailable("OPENROUTER_API_KEY is not configured.")

        payload = {
            "model": model or settings.openrouter_extraction_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract company research facts. Return only strict JSON, no Markdown."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            data = response.json()

        content = data["choices"][0]["message"]["content"]
        if isinstance(content, dict):
            return content
        return json.loads(content)
