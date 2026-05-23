from __future__ import annotations

import logging

from app.agents.llm_gateway import OpenAiCompatibleLlmClient
from app.agents.research_workflow import ResearchAgentWorkflow
from app.contracts.agent import (
    AgentEvent,
    AgentPhase,
    AgentRequest,
    AgentRunStatus,
    AgentState,
    LlmProvider,
    TaskPolicy,
    ToolStatus,
)
from app.contracts.research_task import ResearchTaskType


class _FakeReport:
    def model_dump(self, mode: str = "json") -> dict[str, str]:
        return {"summary": "ok"}


def _fake_transport(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": "{}",
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def _make_client() -> OpenAiCompatibleLlmClient:
    return OpenAiCompatibleLlmClient(
        LlmProvider.SILICONFLOW,
        "sk-test",
        base_url="https://example.com/v1",
        transport=_fake_transport,
    )


def _make_state() -> AgentState:
    return AgentState(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="en",
        provider=LlmProvider.SILICONFLOW,
        model="Pro/moonshotai/Kimi-K2.6",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["toplineVerdict"],
        ),
        tool_events=[
            AgentEvent(
                run_id="run_1",
                task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
                phase=AgentPhase.BUILD_EVIDENCE_PLAN,
                status=ToolStatus.OK,
                summary="Planned evidence collection.",
                event_kind="reasoning",
                agent_name="Earnings agent",
                model_name="Pro/moonshotai/Kimi-K2.6",
                latency_ms=41,
            ),
            AgentEvent(
                run_id="run_1",
                task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
                phase=AgentPhase.COLLECT_FINANCIAL_FACTS,
                status=ToolStatus.OK,
                summary="Collected company facts.",
                event_kind="tool",
                agent_name="Earnings agent",
                model_name="Pro/moonshotai/Kimi-K2.6",
                tool_name="get_company_facts",
                latency_ms=118,
            ),
            AgentEvent(
                run_id="run_1",
                task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
                phase=AgentPhase.DRAFT_REPORT_SECTIONS,
                status=ToolStatus.OK,
                summary="Synthesized final report sections.",
                event_kind="reasoning",
                agent_name="Earnings agent",
                model_name="Pro/moonshotai/Kimi-K2.6",
                latency_ms=612,
                usage={"prompt_tokens": 10, "completion_tokens": 22},
            ),
        ],
    )


def test_research_workflow_logs_stage_summary(caplog, monkeypatch) -> None:
    workflow = ResearchAgentWorkflow(llm_client=_make_client())
    request = AgentRequest(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="en",
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model="Pro/moonshotai/Kimi-K2.6",
        llm_api_key="sk-test",
    )
    state = _make_state()

    def fake_run_task_agent(request_arg, state_arg, llm_client_arg):
        return _FakeReport(), state

    monkeypatch.setattr(workflow, "_run_task_agent", fake_run_task_agent)
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    result = workflow.run(request)

    assert result.status == AgentRunStatus.OK
    assert any(
        "research_agent_stage_summary" in record.message
        and "planning_ms=41" in record.message
        and "tool_ms=118" in record.message
        and "synthesis_ms=612" in record.message
        for record in caplog.records
    )
