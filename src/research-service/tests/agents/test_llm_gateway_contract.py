from typing import cast

import pytest

from app.agents.llm_gateway import (
    LlmRequest,
    OpenAiCompatibleLlmClient,
    StaticJsonLlmClient,
    create_llm_client,
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
    assert payload["max_tokens"] == 512
    assert captured["timeout_seconds"] == 5
    assert captured["authorization"] == "Bearer secret"
    assert "secret" not in response.model_dump_json()
