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


def max_tokens_for_task(task: ModelTask) -> int:
    if task == "news_summary":
        return 350
    if task == "linkedin_lookup":
        return 900
    if task == "company_profile_extract":
        return 1200
    if task in {"final_brief", "quality_synthesis"}:
        return 2000
    return 1000


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
        max_tokens: int | None = None,
    ) -> str:
        if not self.api_key:
            raise OpenRouterUnavailable("OPENROUTER_API_KEY is not configured.")

        selected_model = model or model_for_task(task)
        payload = {
            "model": selected_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens or max_tokens_for_task(task),
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
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = exc.response.text.strip().replace("\n", " ")
                if len(detail) > 240:
                    detail = f"{detail[:240]}..."
                raise OpenRouterUnavailable(
                    f"OpenRouter rejected model '{selected_model}' for task '{task}' "
                    f"with HTTP {exc.response.status_code}: {detail or 'No response body'}"
                ) from exc
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
            max_tokens=max_tokens_for_task(task),
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
            max_tokens=max_tokens_for_task("news_summary"),
        )

    async def synthesize_json(self, prompt: str, *, model: str | None = None) -> dict[str, Any]:
        content = await self.chat(
            system_prompt=(
                "Synthesize a final company research brief. "
                "Prioritize precision, source-grounded claims, and explicit uncertainty. "
                "Keep the output concise: summary under 120 words, list items under 25 words. "
                "Return only strict JSON, no Markdown."
            ),
            user_prompt=prompt,
            task="final_brief",
            model=model,
            response_format={"type": "json_object"},
            max_tokens=max_tokens_for_task("final_brief"),
        )
        return json.loads(content)
