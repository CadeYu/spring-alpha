import json
from typing import Any

from app.agents.bounded_workflow import BoundedAgentWorkflow, DefaultAgentToolset
from app.contracts.agent import AgentPhase, AgentRequest, AgentRunStatus, RepairAction, ToolResult
from app.contracts.report import CitationStatus
from app.contracts.research_task import ResearchTaskType


def test_workflow_emits_structured_events_without_chain_of_thought() -> None:
    workflow = BoundedAgentWorkflow()

    result = workflow.run(
        AgentRequest(
            run_id="run_001",
            ticker="TSLA",
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        )
    )

    assert result.status == AgentRunStatus.OK
    assert result.final_report is not None
    assert result.final_report["task_type"] == "cash_flow_capital_allocation"
    assert [event.phase for event in result.events] == [
        AgentPhase.RESOLVE_TASK,
        AgentPhase.COLLECT_FINANCIAL_FACTS,
        AgentPhase.COLLECT_FILING_METADATA,
        AgentPhase.BUILD_EVIDENCE_PLAN,
        AgentPhase.RETRIEVE_EVIDENCE,
        AgentPhase.EXTRACT_SIGNALS,
        AgentPhase.DRAFT_REPORT_SECTIONS,
        AgentPhase.VALIDATE_CLAIMS,
        AgentPhase.FINALIZE_REPORT,
    ]
    assert all(event.summary for event in result.events)

    serialized_result = json.dumps(result.model_dump(mode="json"))
    assert "chain_of_thought" not in serialized_result
    assert "scratchpad" not in serialized_result
    assert "hidden_reasoning" not in serialized_result


def test_final_report_binds_claims_to_evidence_metadata() -> None:
    workflow = BoundedAgentWorkflow()

    result = workflow.run(
        AgentRequest(
            run_id="run_005",
            ticker="TSLA",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        )
    )

    assert result.final_report is not None
    claim = result.final_report["claims"][0]
    assert claim["text"]
    assert claim["citation_status"] == CitationStatus.UNVERIFIED.value
    assert claim["source_refs"]

    source_ref = claim["source_refs"][0]
    assert source_ref["source_id"] == "run_005:node:1"
    assert source_ref["filing_type"] == "10-Q"
    assert source_ref["section"] == "Business Drivers"
    assert source_ref["snippet"]
    assert source_ref["citation_status"] == CitationStatus.UNVERIFIED.value


def test_unknown_citation_status_defaults_to_unverified() -> None:
    workflow = BoundedAgentWorkflow(toolset=UnknownCitationStatusToolset())

    result = workflow.run(
        AgentRequest(
            run_id="run_006",
            ticker="TSLA",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        )
    )

    assert result.final_report is not None
    claim = result.final_report["claims"][0]
    assert claim["citation_status"] == CitationStatus.UNVERIFIED.value
    assert claim["source_refs"][0]["citation_status"] == CitationStatus.UNVERIFIED.value


def test_final_report_marks_claim_missing_when_no_source_refs_exist() -> None:
    workflow = BoundedAgentWorkflow(toolset=NoSourceRefsToolset())

    result = workflow.run(
        AgentRequest(
            run_id="run_007",
            ticker="TSLA",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        )
    )

    assert result.final_report is not None
    claim = result.final_report["claims"][0]
    assert claim["citation_status"] == CitationStatus.MISSING.value
    assert claim["source_refs"] == []


def test_workflow_bounds_evidence_repair_and_marks_degraded() -> None:
    toolset = EmptyEvidenceToolset()
    workflow = BoundedAgentWorkflow(toolset=toolset)

    result = workflow.run(
        AgentRequest(
            run_id="run_002",
            ticker="TSLA",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            max_evidence_repair_loops=2,
        )
    )

    assert result.status == AgentRunStatus.DEGRADED
    assert toolset.retrieve_calls == 3
    assert any(event.phase == AgentPhase.DEGRADED for event in result.events)
    assert any(
        "Evidence coverage remained incomplete" in reason for reason in result.degraded_reasons
    )


def test_tool_errors_become_degraded_events() -> None:
    workflow = BoundedAgentWorkflow(toolset=FailingFactsToolset())

    result = workflow.run(
        AgentRequest(
            run_id="run_003",
            ticker="TSLA",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        )
    )

    assert result.status == AgentRunStatus.DEGRADED
    assert any(event.phase == AgentPhase.DEGRADED for event in result.events)
    assert any("collect_financial_facts" in reason for reason in result.degraded_reasons)


def test_direct_validation_fallback_keeps_degraded_status() -> None:
    workflow = BoundedAgentWorkflow(toolset=FallbackValidationToolset())

    result = workflow.run(
        AgentRequest(
            run_id="run_004",
            ticker="TSLA",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        )
    )

    assert result.status == AgentRunStatus.DEGRADED
    assert any(event.phase == AgentPhase.DEGRADED for event in result.events)
    assert any("raw filing fallback" in reason for reason in result.degraded_reasons)


class EmptyEvidenceToolset(DefaultAgentToolset):
    def __init__(self) -> None:
        self.retrieve_calls = 0

    def retrieve_evidence(
        self,
        request: AgentRequest,
        data: dict[str, Any],
        repair_count: int,
    ) -> ToolResult:
        self.retrieve_calls += 1
        return ToolResult.empty(
            data={
                "query": "missing evidence",
                "repair_count": repair_count,
            },
            degraded_reason="No evidence nodes returned.",
        )


class UnknownCitationStatusToolset(DefaultAgentToolset):
    def retrieve_evidence(
        self,
        request: AgentRequest,
        data: dict[str, Any],
        repair_count: int,
    ) -> ToolResult:
        return ToolResult.ok(
            {
                "query": "unknown status",
                "repair_count": repair_count,
                "retrieved_nodes": [
                    {
                        "node_id": f"{request.run_id}:node:unknown-status",
                        "section": "MD&A",
                        "snippet": "Evidence with an unexpected citation status.",
                        "filing_type": "10-Q",
                        "citation_status": "maybe_supported",
                    }
                ],
            }
        )


class NoSourceRefsToolset(DefaultAgentToolset):
    def retrieve_evidence(
        self,
        request: AgentRequest,
        data: dict[str, Any],
        repair_count: int,
    ) -> ToolResult:
        return ToolResult.ok(
            {
                "query": "empty evidence",
                "repair_count": repair_count,
                "retrieved_nodes": [],
            }
        )


class FailingFactsToolset(DefaultAgentToolset):
    def collect_financial_facts(self, request: AgentRequest) -> ToolResult:
        raise RuntimeError("facts provider unavailable")


class FallbackValidationToolset(DefaultAgentToolset):
    def validate_claims(self, request: AgentRequest, data: dict[str, Any]) -> ToolResult:
        return ToolResult.partial(
            data={
                "repair_action": RepairAction.FALLBACK_TO_RAW_FILING.value,
                "reason": "raw_filing_fallback",
            },
            degraded_reason="Using raw filing fallback for unsupported evidence gap.",
        )
