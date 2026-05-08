import json

import pytest
from pydantic import ValidationError

from app.contracts.agent import (
    AgentEvent,
    AgentPhase,
    AgentRequest,
    AgentState,
    CoverageState,
    EvidenceMemory,
    LlmProvider,
    TaskPolicy,
    ToolStatus,
    default_task_policy,
)
from app.contracts.report import CitationStatus
from app.contracts.research_task import ResearchTaskType


def test_agent_state_is_json_serializable_and_replayable() -> None:
    state = AgentState(
        run_id="run_state_001",
        ticker="aapl",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="en",
        provider=LlmProvider.SILICONFLOW,
        model="Pro/moonshotai/Kimi-K2.6",
        task_policy=default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE),
        step_index=1,
        tool_call_count=1,
        evidence_memory=EvidenceMemory(
            facts={"revenue": {"value": "$100B", "period": "FY2026 Q2"}},
            source_refs=[
                {
                    "source_id": "src_001",
                    "section": "MD&A",
                    "snippet": "Services revenue increased.",
                    "citation_status": CitationStatus.UNVERIFIED,
                }
            ],
        ),
        retrieval_records=[
            {
                "tool_name": "search_filing_sections",
                "status": ToolStatus.OK,
                "source_ref_count": 1,
            }
        ],
        tool_events=[
            AgentEvent(
                run_id="run_state_001",
                task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
                phase=AgentPhase.RETRIEVE_EVIDENCE,
                status=ToolStatus.OK,
                summary="Searched MD&A for business driver evidence.",
                tool_name="search_filing_sections",
                latency_ms=25,
            )
        ],
        coverage=CoverageState(status="partial", missing_outputs=["driverMap"]),
        degraded_reasons=[],
    )

    payload = state.model_dump(mode="json")
    serialized = json.dumps(payload)
    restored = AgentState.model_validate_json(serialized)

    assert restored.ticker == "AAPL"
    assert restored.task_policy.allowed_tools == [
        "search_filing_sections",
        "search_metric_evidence",
        "get_business_signals",
        "verify_citations",
        "finalize_report",
    ]
    assert restored.evidence_memory.source_refs[0]["source_id"] == "src_001"
    assert "chain_of_thought" not in serialized
    assert "scratchpad" not in serialized
    assert "api_key" not in serialized


def test_agent_request_accepts_planner_provider_without_persisting_api_key() -> None:
    request = AgentRequest(
        run_id="run_provider_001",
        ticker="aapl",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model="Pro/moonshotai/Kimi-K2.6",
        llm_api_key="secret",
    )

    serialized = request.model_dump(mode="json")

    assert serialized["llm_provider"] == LlmProvider.SILICONFLOW
    assert serialized["llm_model"] == "Pro/moonshotai/Kimi-K2.6"
    assert "llm_api_key" not in serialized
    assert "secret" not in request.model_dump_json()


@pytest.mark.parametrize(
    ("task_type", "required_outputs"),
    [
        (
            ResearchTaskType.LATEST_EARNINGS_READOUT,
            [
                "toplineVerdict",
                "keyTakeaways",
                "financialDashboard",
                "driverSnapshot",
                "riskSnapshot",
            ],
        ),
        (
            ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            [
                "driverThesis",
                "driverMap",
                "positiveSignals",
                "negativeSignals",
                "watchlist",
            ],
        ),
        (
            ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            [
                "cashQualityVerdict",
                "cashMetrics",
                "capitalAllocation",
                "allocationDiscipline",
                "redFlags",
            ],
        ),
    ],
)
def test_default_task_policies_encode_required_outputs(
    task_type: ResearchTaskType,
    required_outputs: list[str],
) -> None:
    policy = default_task_policy(task_type)

    assert policy.task_type == task_type
    assert policy.required_outputs == required_outputs
    assert policy.max_steps == 5
    assert policy.max_repair_loops == 2
    assert "finalize_report" in policy.allowed_tools


def test_task_policy_rejects_unknown_tools() -> None:
    with pytest.raises(ValidationError):
        TaskPolicy(
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            allowed_tools=["finalize_report", "unknown_tool"],
            required_outputs=["toplineVerdict"],
            max_steps=5,
            max_tool_calls=4,
            max_repair_loops=2,
            degraded_policy="finalize_degraded",
        )
