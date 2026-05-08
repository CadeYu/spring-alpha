from typing import Any

from app.agents.deterministic_workflow import DeterministicAgentWorkflow
from app.agents.llm_gateway import LlmRequest, LlmResponse
from app.contracts.agent import AgentRequest, AgentRunStatus, LlmProvider
from app.contracts.research_task import ResearchTaskType


class SequencePlannerClient:
    provider = LlmProvider.OPENAI

    def __init__(self, decisions: list[dict[str, Any]]) -> None:
        self.decisions = decisions
        self.requests: list[LlmRequest] = []

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.decisions) - 1)
        return LlmResponse(
            provider=request.provider,
            model=request.model,
            content=self.decisions[index],
        )


def test_live_planner_runs_tool_observe_tool_until_finalize() -> None:
    planner = SequencePlannerClient(
        [
            {
                "decision": "call_tool",
                "summary": "Search MD&A evidence first.",
                "tool_name": "search_filing_sections",
                "tool_input": {"sections": ["MD&A"], "query": "services demand"},
            },
            {
                "decision": "call_tool",
                "summary": "Collect business signals after observing filing evidence.",
                "tool_name": "get_business_signals",
                "tool_input": {"signal_types": ["product", "demand"]},
            },
            {
                "decision": "finalize",
                "summary": "Observed evidence and citations are enough.",
            },
        ]
    )
    workflow = DeterministicAgentWorkflow(llm_client=planner)

    result = workflow.run(
        request(
            "run_live_loop",
            ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        )
    )

    tool_names = [event.tool_name for event in result.events if event.tool_name]

    assert result.status == AgentRunStatus.OK
    assert len(planner.requests) == 3
    assert planner.requests[1].state.evidence_memory.source_refs
    assert planner.requests[2].state.evidence_memory.business_signals
    assert tool_names == [
        "search_filing_sections",
        "search_filing_sections",
        "get_business_signals",
        "get_business_signals",
    ]
    assert any(
        event.summary == "Planner finalized: Observed evidence and citations are enough."
        for event in result.events
    )


def test_live_planner_stops_when_coverage_is_sufficient() -> None:
    planner = SequencePlannerClient(
        [
            {
                "decision": "call_tool",
                "summary": "Search filing evidence.",
                "tool_name": "search_filing_sections",
                "tool_input": {"sections": ["MD&A"], "query": "revenue margin"},
            },
            {
                "decision": "call_tool",
                "summary": "Verify citations.",
                "tool_name": "verify_citations",
                "tool_input": {},
            },
            {
                "decision": "call_tool",
                "summary": "This should not run after coverage is enough.",
                "tool_name": "search_metric_evidence",
                "tool_input": {"metrics": ["revenue"]},
            },
        ]
    )
    workflow = DeterministicAgentWorkflow(llm_client=planner)

    result = workflow.run(request("run_live_coverage_stop"))

    tool_names = [event.tool_name for event in result.events if event.tool_name]

    assert result.status == AgentRunStatus.OK
    assert len(planner.requests) == 2
    assert "search_metric_evidence" not in tool_names
    assert any(
        event.summary == "Coverage is sufficient; finalizing bounded live planner loop."
        for event in result.events
    )


def test_live_planner_uses_deterministic_fallback_for_invalid_decision() -> None:
    planner = SequencePlannerClient(
        [
            {
                "decision": "call_tool",
                "summary": "Missing tool name.",
            },
            {
                "decision": "finalize",
                "summary": "Fallback observation is enough.",
            },
        ]
    )
    workflow = DeterministicAgentWorkflow(llm_client=planner)

    result = workflow.run(request("run_live_invalid_fallback"))

    tool_names = [event.tool_name for event in result.events if event.tool_name]

    assert result.status == AgentRunStatus.DEGRADED
    assert len(planner.requests) == 2
    assert tool_names[:2] == ["get_company_facts", "get_company_facts"]
    assert any("Planner JSON was invalid" in reason for reason in result.degraded_reasons)
    assert any(
        event.summary.startswith("Planner decision was invalid; used deterministic fallback")
        for event in result.events
    )


def test_live_planner_finalizes_when_coverage_completes_on_last_budgeted_tool() -> None:
    planner = SequencePlannerClient(
        [
            {
                "decision": "call_tool",
                "summary": "Search filing evidence.",
                "tool_name": "search_filing_sections",
                "tool_input": {"sections": ["MD&A"], "query": "revenue margin"},
            },
            {
                "decision": "call_tool",
                "summary": "Collect facts.",
                "tool_name": "get_company_facts",
                "tool_input": {"period": "latest_quarter", "metrics": ["revenue"]},
            },
            {
                "decision": "call_tool",
                "summary": "Collect metric evidence.",
                "tool_name": "search_metric_evidence",
                "tool_input": {"metrics": ["revenue"]},
            },
            {
                "decision": "call_tool",
                "summary": "Refresh facts.",
                "tool_name": "get_company_facts",
                "tool_input": {"period": "latest_quarter", "metrics": ["gross margin"]},
            },
            {
                "decision": "call_tool",
                "summary": "Verify citations on the final budgeted tool.",
                "tool_name": "verify_citations",
                "tool_input": {},
            },
            {
                "decision": "call_tool",
                "summary": "This should not run after the budget is exactly spent.",
                "tool_name": "search_filing_sections",
                "tool_input": {"sections": ["Risk Factors"], "query": "risk"},
            },
        ]
    )
    workflow = DeterministicAgentWorkflow(llm_client=planner)

    result = workflow.run(request("run_live_budget_edge"))

    assert result.status == AgentRunStatus.OK
    assert len(planner.requests) == 5
    assert not result.degraded_reasons
    assert any(
        event.summary == "Coverage is sufficient; finalizing bounded live planner loop."
        for event in result.events
    )


def test_live_planner_rejects_disallowed_tool_decision_and_uses_fallback() -> None:
    planner = SequencePlannerClient(
        [
            {
                "decision": "call_tool",
                "summary": "Try a tool outside this task policy.",
                "tool_name": "get_business_signals",
                "tool_input": {"signal_types": ["demand"]},
            },
            {
                "decision": "finalize",
                "summary": "Fallback evidence is enough.",
            },
        ]
    )
    workflow = DeterministicAgentWorkflow(llm_client=planner)

    result = workflow.run(request("run_live_disallowed_tool"))

    tool_names = [event.tool_name for event in result.events if event.tool_name]

    assert result.status == AgentRunStatus.DEGRADED
    assert tool_names[:2] == ["get_company_facts", "get_company_facts"]
    assert any(
        "not allowed for latest_earnings_readout" in reason for reason in result.degraded_reasons
    )
    assert not any(
        reason.startswith("Tool get_business_signals is not allowed")
        for reason in result.degraded_reasons
    )


def request(
    run_id: str,
    task_type: ResearchTaskType = ResearchTaskType.LATEST_EARNINGS_READOUT,
) -> AgentRequest:
    return AgentRequest(
        run_id=run_id,
        ticker="AAPL",
        task_type=task_type,
        language="en",
    )
