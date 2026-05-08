import json
from collections.abc import Callable
from time import perf_counter
from typing import Any, Protocol
from urllib import request as url_request

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.agent import AgentState, LlmProvider
from app.contracts.research_task import ResearchTaskType


class LlmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    provider: LlmProvider
    model: str | None = None
    task_type: ResearchTaskType
    system_prompt: str = Field(min_length=1)
    user_prompt: str = Field(min_length=1)
    state: AgentState
    timeout_seconds: int = Field(default=30, gt=0, le=180)


class LlmResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: LlmProvider
    model: str | None = None
    content: dict[str, Any]
    raw_text: str | None = None
    latency_ms: int = Field(default=0, ge=0)
    usage: dict[str, Any] = Field(default_factory=dict)


class LlmClient(Protocol):
    provider: LlmProvider

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        raise NotImplementedError


class StaticJsonLlmClient:
    def __init__(self, content: dict[str, Any], provider: LlmProvider = LlmProvider.OPENAI) -> None:
        self.provider = provider
        self._content = content

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        started_at = perf_counter()
        return LlmResponse(
            provider=request.provider,
            model=request.model,
            content=self._content,
            latency_ms=int((perf_counter() - started_at) * 1000),
        )


LlmTransport = Callable[[str, dict[str, object], dict[str, str], int], dict[str, object]]


class OpenAiCompatibleLlmClient:
    def __init__(
        self,
        provider: LlmProvider,
        api_key: str,
        *,
        base_url: str,
        transport: LlmTransport | None = None,
    ) -> None:
        self.provider = provider
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport or _urllib_transport

    def __repr__(self) -> str:
        return f"OpenAiCompatibleLlmClient(provider={self.provider.value})"

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        started_at = perf_counter()
        payload: dict[str, object] = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            "max_tokens": 512,
        }
        raw = self._transport(
            f"{self._base_url}/chat/completions",
            payload,
            {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            request.timeout_seconds,
        )
        text = _extract_chat_content(raw)
        return LlmResponse(
            provider=request.provider,
            model=request.model,
            content=_parse_json_text(text),
            raw_text=text,
            latency_ms=int((perf_counter() - started_at) * 1000),
            usage=_dict_value(raw.get("usage")),
        )


def default_model_for_provider(provider: LlmProvider) -> str:
    defaults = {
        LlmProvider.SILICONFLOW: "Pro/moonshotai/Kimi-K2.6",
        LlmProvider.OPENAI: "gpt-5.2",
        LlmProvider.GEMINI: "gemini-2.5-pro",
    }
    return defaults[provider]


def create_llm_client(provider: LlmProvider, *, api_key: str) -> LlmClient:
    base_urls = {
        LlmProvider.SILICONFLOW: "https://api.siliconflow.cn/v1",
        LlmProvider.OPENAI: "https://api.openai.com/v1",
        LlmProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta/openai",
    }
    return OpenAiCompatibleLlmClient(provider, api_key, base_url=base_urls[provider])


def _urllib_transport(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = url_request.Request(url, data=body, headers=headers, method="POST")
    with url_request.urlopen(request, timeout=timeout_seconds) as response:
        raw_body = response.read().decode("utf-8")
    parsed = json.loads(raw_body)
    if not isinstance(parsed, dict):
        raise ValueError("LLM provider response must be a JSON object")
    return parsed


def _extract_chat_content(raw: dict[str, object]) -> str:
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM provider response did not include choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("LLM provider choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("LLM provider choice did not include message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM provider message content was empty")
    return content


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON content must be an object")
    return parsed


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
