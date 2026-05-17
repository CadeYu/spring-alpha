from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Any, Protocol
from urllib import request as url_request

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
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
            "max_tokens": 2048,
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

    def as_chat_model(
        self,
        *,
        model: str | None = None,
        timeout_seconds: int = 30,
        max_tokens: int = 4096,
        response_format: dict[str, Any] | None = None,
    ) -> BaseChatModel:
        return OpenAiCompatibleChatModel(
            provider=self.provider,
            model=model,
            base_url=self._base_url,
            api_key=self._api_key,
            transport=self._transport,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            response_format=response_format,
            compact_synthesis=_should_use_compact_synthesis(self.provider, model),
        )


class OpenAiCompatibleChatModel(BaseChatModel):
    provider: LlmProvider
    model: str | None = None
    base_url: str
    api_key: str
    transport: LlmTransport
    timeout_seconds: int = 30
    max_tokens: int = 4096
    response_format: dict[str, Any] | None = None
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_choice: str | dict[str, Any] | None = None
    compact_synthesis: bool = False

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable[..., Any] | BaseTool],
        *,
        tool_choice: str | dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        converted_tools = [convert_to_openai_tool(tool) for tool in tools]
        return self.model_copy(update={"tools": converted_tools, "tool_choice": tool_choice})

    @property
    def _llm_type(self) -> str:
        return f"openai-compatible-{self.provider.value}"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        started_at = perf_counter()
        payload: dict[str, object] = {
            "model": self.model,
            "messages": [_message_payload(message) for message in messages],
            "temperature": 0,
            "max_tokens": self.max_tokens,
        }
        if self.response_format is not None:
            payload["response_format"] = self.response_format
        if _should_disable_kimi_thinking(self.provider, self.model):
            payload["thinking"] = {"type": "disabled"}
        if self.tools:
            payload["tools"] = self.tools
            payload["tool_choice"] = self.tool_choice or "auto"
        raw = self.transport(
            f"{self.base_url}/chat/completions",
            payload,
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            self.timeout_seconds,
        )
        message = _extract_chat_message(raw)
        generation = ChatGeneration(
            message=_ai_message_from_openai_message(
                message,
                latency_ms=int((perf_counter() - started_at) * 1000),
                usage=_dict_value(raw.get("usage")),
            )
        )
        return ChatResult(generations=[generation])


def default_model_for_provider(provider: LlmProvider) -> str:
    defaults = {
        LlmProvider.SILICONFLOW: os.getenv("SILICONFLOW_MODEL", "Pro/moonshotai/Kimi-K2.6"),
        LlmProvider.OPENAI: os.getenv("OPENAI_MODEL", "gpt-5.2"),
        LlmProvider.GEMINI: os.getenv("GEMINI_MODEL", "gemini-2.5-pro"),
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
    message = _extract_chat_message(raw)
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("LLM provider message content was empty")
    return content


def _extract_chat_message(raw: dict[str, object]) -> dict[str, object]:
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("LLM provider response did not include choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("LLM provider choice must be an object")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("LLM provider choice did not include message")
    return message


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    parsed = json.loads(cleaned, strict=False)
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON content must be an object")
    return parsed


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _message_payload(message: BaseMessage) -> dict[str, object]:
    if message.type == "system":
        return {"role": "system", "content": _message_content(message.content)}
    if message.type == "human":
        return {"role": "user", "content": _message_content(message.content)}
    if message.type == "tool":
        return {
            "role": "tool",
            "content": _message_content(message.content),
            "tool_call_id": str(getattr(message, "tool_call_id", "")),
        }
    if message.type == "ai":
        payload: dict[str, object] = {
            "role": "assistant",
            "content": _message_content(message.content),
        }
        tool_calls = getattr(message, "tool_calls", None)
        if isinstance(tool_calls, list) and tool_calls:
            payload["tool_calls"] = [
                {
                    "id": str(tool_call.get("id") or ""),
                    "type": "function",
                    "function": {
                        "name": str(tool_call.get("name") or ""),
                        "arguments": json.dumps(tool_call.get("args") or {}),
                    },
                }
                for tool_call in tool_calls
                if isinstance(tool_call, dict)
            ]
        return payload
    return {"role": "user", "content": _message_content(message.content)}


def _message_content(content: object) -> str:
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=True)


def _ai_message_from_openai_message(
    message: dict[str, object],
    *,
    latency_ms: int,
    usage: dict[str, Any],
) -> AIMessage:
    content = message.get("content")
    tool_calls = _tool_calls_from_message(message)
    return AIMessage(
        content=content if isinstance(content, str) else "",
        tool_calls=tool_calls,
        response_metadata={"latency_ms": latency_ms, "usage": usage},
    )


def _tool_calls_from_message(message: dict[str, object]) -> list[dict[str, Any]]:
    raw_tool_calls = message.get("tool_calls")
    if not isinstance(raw_tool_calls, list):
        return []
    tool_calls: list[dict[str, Any]] = []
    for index, raw_tool_call in enumerate(raw_tool_calls, start=1):
        if not isinstance(raw_tool_call, dict):
            continue
        function = raw_tool_call.get("function")
        if not isinstance(function, dict):
            continue
        name = function.get("name")
        if not isinstance(name, str) or not name:
            continue
        tool_calls.append(
            {
                "name": name,
                "args": _parse_tool_arguments(function.get("arguments")),
                "id": str(raw_tool_call.get("id") or f"call_{index}"),
            }
        )
    return tool_calls


def _parse_tool_arguments(arguments: object) -> dict[str, Any]:
    if isinstance(arguments, dict):
        return arguments
    if not isinstance(arguments, str) or not arguments.strip():
        return {}
    parsed = json.loads(arguments)
    return parsed if isinstance(parsed, dict) else {}


def _should_disable_kimi_thinking(provider: LlmProvider, model: str | None) -> bool:
    if provider != LlmProvider.SILICONFLOW or model is None:
        return False
    normalized = model.lower()
    return "moonshotai/kimi-k2.6" in normalized


def _should_use_compact_synthesis(provider: LlmProvider, model: str | None) -> bool:
    if provider != LlmProvider.SILICONFLOW or model is None:
        return False
    normalized = model.lower()
    return "deepseek-v4-flash" in normalized or "moonshotai/kimi-k2.6" in normalized
