from typing import cast

import pytest

from app.agents.llm_gateway import (
    LlmRequest,
    OpenAiCompatibleLlmClient,
    StaticJsonLlmClient,
    create_llm_client,
    default_model_for_provider,
)
from app.contracts.agent import AgentState, LlmProvider, default_task_policy
from app.contracts.research_task import ResearchTaskType


def test_static_json_llm_client_returns_provider_agnostic_response() -> None:
    state = AgentState(
        run_id="run_llm_001",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )
    client = StaticJsonLlmClient({"decision": "finalize", "summary": "Ready."})

    response = client.complete_json(
        LlmRequest(
            run_id=state.run_id,
            provider=LlmProvider.OPENAI,
            model="test-model",
            task_type=state.task_type,
            system_prompt="Return JSON.",
            user_prompt="Plan next step.",
            state=state,
            timeout_seconds=5,
        )
    )

    assert response.provider == LlmProvider.OPENAI
    assert response.content == {"decision": "finalize", "summary": "Ready."}
    assert response.raw_text is None
    assert response.latency_ms >= 0
    assert "api_key" not in response.model_dump(mode="json")


@pytest.mark.parametrize(
    "provider",
    [LlmProvider.SILICONFLOW, LlmProvider.OPENAI, LlmProvider.GEMINI],
)
def test_llm_gateway_factory_creates_supported_provider_clients(provider: LlmProvider) -> None:
    client = create_llm_client(provider, api_key="secret")

    assert client.provider == provider
    assert "secret" not in repr(client)


def test_default_model_for_provider_honors_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.0-flash")

    assert default_model_for_provider(LlmProvider.SILICONFLOW) == "Qwen/Qwen2.5-7B-Instruct"
    assert default_model_for_provider(LlmProvider.OPENAI) == "gpt-4.1-mini"
    assert default_model_for_provider(LlmProvider.GEMINI) == "gemini-2.0-flash"


def test_openai_compatible_client_parses_json_from_chat_completion() -> None:
    state = AgentState(
        run_id="run_llm_002",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        captured["url"] = url
        captured["payload"] = payload
        captured["authorization"] = headers.get("Authorization")
        captured["timeout_seconds"] = timeout_seconds
        return {
            "choices": [
                {"message": {"content": '```json\n{"decision":"finalize","summary":"Done."}\n```'}}
            ],
            "usage": {"total_tokens": 12},
        }

    client = OpenAiCompatibleLlmClient(
        provider=LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )

    response = client.complete_json(
        LlmRequest(
            run_id=state.run_id,
            provider=LlmProvider.SILICONFLOW,
            model="test-model",
            task_type=state.task_type,
            system_prompt="Return JSON.",
            user_prompt="Plan next step.",
            state=state,
            timeout_seconds=5,
        )
    )

    assert response.provider == LlmProvider.SILICONFLOW
    assert response.content == {"decision": "finalize", "summary": "Done."}
    assert response.usage == {"total_tokens": 12}
    assert captured["url"] == "https://example.test/v1/chat/completions"
    payload = cast(dict[str, object], captured["payload"])
    assert payload["max_tokens"] == 2048
    assert captured["timeout_seconds"] == 5
    assert captured["authorization"] == "Bearer secret"
    assert "secret" not in response.model_dump_json()


def test_openai_compatible_chat_model_parses_tool_calls() -> None:
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        captured["payload"] = payload
        return {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "search_sec_evidence",
                                    "arguments": '{"query":"revenue drivers","top_k":2}',
                                },
                            }
                        ],
                    }
                }
            ]
        }

    client = OpenAiCompatibleLlmClient(
        provider=LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )
    chat_model = client.as_chat_model(model="test-model")

    result = chat_model.bind_tools(
        [
            {
                "type": "function",
                "function": {
                    "name": "search_sec_evidence",
                    "description": "Search evidence.",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ]
    ).invoke("Find evidence")

    assert result.tool_calls == [
        {
            "name": "search_sec_evidence",
            "args": {"query": "revenue drivers", "top_k": 2},
            "id": "call_1",
            "type": "tool_call",
        }
    ]
    payload = cast(dict[str, object], captured["payload"])
    assert "tools" in payload
    assert payload["tool_choice"] == "auto"


def test_openai_compatible_chat_model_can_request_json_response_mode() -> None:
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"headline":"Done"}'}}]}

    client = OpenAiCompatibleLlmClient(
        provider=LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )
    chat_model = client.as_chat_model(
        model="test-model",
        max_tokens=768,
        response_format={"type": "json_object"},
    )

    result = chat_model.invoke("Return JSON")

    assert result.content == '{"headline":"Done"}'
    payload = cast(dict[str, object], captured["payload"])
    assert payload["max_tokens"] == 768
    assert payload["response_format"] == {"type": "json_object"}


def test_openai_compatible_chat_model_disables_kimi_thinking_on_siliconflow() -> None:
    captured: dict[str, object] = {}

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        captured["payload"] = payload
        return {"choices": [{"message": {"content": '{"headline":"Done"}'}}]}

    client = OpenAiCompatibleLlmClient(
        provider=LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )

    client.as_chat_model(model="Pro/moonshotai/Kimi-K2.6").invoke("Return JSON")

    payload = cast(dict[str, object], captured["payload"])
    assert payload["thinking"] == {"type": "disabled"}


def test_openai_compatible_chat_model_marks_deepseek_flash_for_compact_synthesis() -> None:
    client = OpenAiCompatibleLlmClient(
        provider=LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=lambda url, payload, headers, timeout_seconds: {
            "choices": [{"message": {"content": '{"headline":"Done"}'}}]
        },
    )

    chat_model = client.as_chat_model(model="deepseek-ai/DeepSeek-V4-Flash")

    assert getattr(chat_model, "compact_synthesis", False) is True
