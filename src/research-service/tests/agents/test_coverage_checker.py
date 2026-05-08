from app.agents.coverage import check_coverage
from app.contracts.agent import AgentState, default_task_policy
from app.contracts.research_task import ResearchTaskType


def test_coverage_checker_marks_complete_when_evidence_and_citations_exist() -> None:
    state = AgentState(
        run_id="run_coverage_001",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        task_policy=default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE),
    )
    state.evidence_memory.source_refs.append({"source_id": "src_1"})
    state.evidence_memory.citation_results.append({"status": "unverified"})

    result = check_coverage(state)

    assert result.coverage.status == "complete"
    assert result.coverage.evidence_count == 1
    assert result.coverage.citation_coverage == "partial"
    assert result.should_finalize
    assert result.degraded_reasons == []


def test_coverage_checker_marks_degraded_when_evidence_is_missing() -> None:
    state = AgentState(
        run_id="run_coverage_002",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
    )

    result = check_coverage(state)

    assert result.coverage.status == "degraded"
    assert result.coverage.evidence_count == 0
    assert result.coverage.missing_outputs == state.task_policy.required_outputs
    assert result.coverage.citation_coverage == "missing"
    assert not result.should_finalize
    assert result.degraded_reasons == ["No evidence source refs were collected."]
