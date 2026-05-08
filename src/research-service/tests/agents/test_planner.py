from typing import Any

from app.agents.llm_gateway import LlmRequest, LlmResponse, StaticJsonLlmClient
from app.agents.planner import PlannerDecisionType, plan_next_step
from app.contracts.agent import AgentState, CoverageState, LlmProvider, default_task_policy
from app.contracts.research_task import ResearchTaskType


class RecordingJsonLlmClient:
    provider = LlmProvider.OPENAI

    def __init__(self, content: dict[str, Any]) -> None:
        self.content = content
        self.requests: list[LlmRequest] = []

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        self.requests.append(request)
        return LlmResponse(
            provider=request.provider,
            model=request.model,
            content=self.content,
        )


def test_planner_converts_llm_tool_json_to_tool_call() -> None:
    state = AgentState(
        run_id="run_planner_001",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        provider=LlmProvider.OPENAI,
        model="test-model",
        task_policy=default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE),
    )
    client = StaticJsonLlmClient(
        {
            "decision": "call_tool",
            "summary": "Need MD&A driver evidence.",
            "tool_name": "search_filing_sections",
            "tool_input": {
                "sections": ["MD&A"],
                "query": "services demand pricing",
            },
        }
    )

    decision = plan_next_step(state, client)

    assert decision.decision == PlannerDecisionType.CALL_TOOL
    assert decision.tool_call is not None
    assert decision.tool_call.tool_name == "search_filing_sections"
    assert decision.tool_call.step_index == state.step_index
    assert decision.tool_call.tool_input["query"] == "services demand pricing"
    assert decision.summary == "Need MD&A driver evidence."


def test_planner_fills_default_input_for_incomplete_tool_json() -> None:
    state = AgentState(
        run_id="run_planner_defaults",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        provider=LlmProvider.OPENAI,
        model="test-model",
        task_policy=default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE),
    )
    client = StaticJsonLlmClient(
        {
            "decision": "call_tool",
            "summary": "Search filing sections.",
            "tool_name": "search_filing_sections",
            "tool_input": {},
        }
    )

    decision = plan_next_step(state, client)

    assert decision.decision == PlannerDecisionType.CALL_TOOL
    assert decision.tool_call is not None
    assert decision.tool_call.tool_input == {
        "sections": ["MD&A"],
        "query": "business driver deep dive evidence",
    }


def test_planner_converts_llm_finalize_json_to_finalize_decision() -> None:
    state = AgentState(
        run_id="run_planner_002",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        provider=LlmProvider.OPENAI,
        model="test-model",
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )
    client = StaticJsonLlmClient({"decision": "finalize", "summary": "Coverage is enough."})

    decision = plan_next_step(state, client)

    assert decision.decision == PlannerDecisionType.FINALIZE
    assert decision.tool_call is None
    assert decision.summary == "Coverage is enough."


def test_planner_returns_degraded_decision_for_invalid_llm_json() -> None:
    state = AgentState(
        run_id="run_planner_003",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        provider=LlmProvider.OPENAI,
        model="test-model",
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )
    client = StaticJsonLlmClient({"decision": "call_tool", "summary": "Missing tool."})

    decision = plan_next_step(state, client)

    assert decision.decision == PlannerDecisionType.DEGRADED
    assert decision.tool_call is None
    assert "Planner JSON was invalid" in decision.summary


def test_planner_prompt_includes_budget_and_coverage_context() -> None:
    state = AgentState(
        run_id="run_planner_prompt_context",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        provider=LlmProvider.OPENAI,
        model="test-model",
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
        step_index=2,
        tool_call_count=3,
        coverage=CoverageState(
            status="partial",
            missing_outputs=["riskSnapshot"],
            evidence_count=4,
            citation_coverage="missing",
        ),
    )
    client = RecordingJsonLlmClient({"decision": "finalize", "summary": "Ready."})

    plan_next_step(state, client)

    prompt = client.requests[0].user_prompt
    assert "Allowed tools: get_company_facts, search_filing_sections" in prompt
    assert "Coverage status: partial" in prompt
    assert "Missing outputs: riskSnapshot" in prompt
    assert "Citation coverage: missing" in prompt
    assert "Remaining steps: 3" in prompt
    assert "Remaining tool calls: 2" in prompt
