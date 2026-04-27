import json
from typing import Any, Literal

import httpx

from company_mcp.config import settings


class OpenRouterUnavailable(Exception):
    pass


ModelTask = Literal[
    "company_profile_extract",
    "linkedin_lookup",
    "news_summary",
    "final_brief",
    "quality_synthesis",
]


def model_for_task(task: ModelTask) -> str:
    if task in {"final_brief", "quality_synthesis"}:
        return settings.openrouter_quality_model
    return settings.openrouter_extraction_model


class OpenRouterClient:
    def __init__(self, api_key: str | None = None) -> None:
        self.api_key = api_key if api_key is not None else settings.openrouter_api_key

    async def chat(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        task: ModelTask,
        model: str | None = None,
        response_format: dict[str, str] | None = None,
        temperature: float = 0,
    ) -> str:
        if not self.api_key:
            raise OpenRouterUnavailable("OPENROUTER_API_KEY is not configured.")

        payload = {
            "model": model or model_for_task(task),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if response_format:
            payload["response_format"] = response_format

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
            return json.dumps(content)
        return content

    async def extract_json(
        self,
        prompt: str,
        *,
        task: ModelTask = "company_profile_extract",
        model: str | None = None,
    ) -> dict[str, Any]:
        content = await self.chat(
            system_prompt="Extract company research facts. Return only strict JSON, no Markdown.",
            user_prompt=prompt,
            task=task,
            model=model,
            response_format={"type": "json_object"},
        )
        if isinstance(content, dict):
            return content
        return json.loads(content)

    async def summarize_text(self, prompt: str, *, model: str | None = None) -> str:
        return await self.chat(
            system_prompt=(
                "Summarize company news for interview preparation. "
                "Be factual, concise, and do not add claims absent from the source text."
            ),
            user_prompt=prompt,
            task="news_summary",
            model=model,
        )

    async def synthesize_json(self, prompt: str, *, model: str | None = None) -> dict[str, Any]:
        content = await self.chat(
            system_prompt=(
                "Synthesize a final company research brief. "
                "Prioritize precision, source-grounded claims, and explicit uncertainty. "
                "Return only strict JSON, no Markdown."
            ),
            user_prompt=prompt,
            task="final_brief",
            model=model,
            response_format={"type": "json_object"},
        )
        return json.loads(content)
