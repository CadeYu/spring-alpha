from typing import Any, cast

from app.agents.coverage import check_coverage
from app.agents.llm_gateway import LlmClient
from app.agents.planner import PlannerDecisionType, plan_next_step
from app.agents.tool_registry import (
    ToolRegistry,
    default_tool_registry,
)
from app.contracts.agent import (
    AgentEvent,
    AgentPhase,
    AgentRequest,
    AgentRunStatus,
    AgentState,
    BoundedAgentResult,
    PlannerContext,
    ToolCall,
    ToolStatus,
    default_task_policy,
)
from app.contracts.report import (
    CitationStatus,
    EvidenceAwareReport,
    EvidenceBoundClaim,
    SourceRef,
    TaskSpecificSections,
)
from app.contracts.research_task import ResearchTaskType


class DeterministicAgentWorkflow:
    def __init__(
        self,
        registry: ToolRegistry | None = None,
        llm_client: LlmClient | None = None,
    ) -> None:
        self._registry = registry or default_tool_registry()
        self._llm_client = llm_client

    def run(self, request: AgentRequest) -> BoundedAgentResult:
        state = AgentState(
            run_id=request.run_id,
            ticker=request.ticker,
            task_type=request.task_type,
            language=request.language,
            provider=self._llm_client.provider if self._llm_client else None,
            model=request.llm_model if self._llm_client else None,
            task_policy=default_task_policy(request.task_type),
        )
        state = _run_dynamic_deterministic_loop(
            state,
            _planned_tool_calls(request),
            self._registry,
            self._llm_client,
        )
        final_report = _build_final_report(request, state)
        status = (
            AgentRunStatus.DEGRADED
            if state.degraded_reasons or state.status == AgentRunStatus.DEGRADED
            else AgentRunStatus.OK
        )
        return BoundedAgentResult(
            run_id=request.run_id,
            task_type=request.task_type,
            status=status,
            events=state.tool_events,
            degraded_reasons=state.degraded_reasons,
            final_report=final_report.model_dump(mode="json"),
        )


def _run_dynamic_deterministic_loop(
    state: AgentState,
    calls: list[ToolCall],
    registry: ToolRegistry,
    llm_client: LlmClient | None = None,
) -> AgentState:
    if llm_client is not None:
        return _run_live_planner_loop(state, calls, registry, llm_client)

    current = state
    planned_calls = list(calls)

    while planned_calls and current.step_index < current.task_policy.max_steps:
        call = planned_calls.pop(0)

        current = _execute_planned_call(current, call, registry)
        if current.status == AgentRunStatus.DEGRADED:
            break

    return current


def _run_live_planner_loop(
    state: AgentState,
    calls: list[ToolCall],
    registry: ToolRegistry,
    llm_client: LlmClient,
) -> AgentState:
    current = state
    fallback_calls = list(calls)

    while current.step_index < current.task_policy.max_steps:
        coverage_result = check_coverage(current)
        current = current.model_copy(update={"coverage": coverage_result.coverage})
        if coverage_result.should_finalize:
            return _append_loop_event(
                current,
                AgentPhase.FINALIZE_REPORT,
                ToolStatus.OK,
                (
                    "Coverage is sufficient; finalizing bounded live planner loop. "
                    f"{_planner_context_suffix(current)}"
                ),
                planner_context=_planner_context(current),
            )

        if current.tool_call_count >= current.task_policy.max_tool_calls:
            return _append_degraded_event(
                current,
                "Tool budget exhausted before planner could finalize.",
            )

        decision = plan_next_step(current, llm_client)
        if decision.decision == PlannerDecisionType.FINALIZE:
            return _append_loop_event(
                current,
                AgentPhase.FINALIZE_REPORT,
                ToolStatus.OK,
                f"Planner finalized: {decision.summary} {_planner_context_suffix(current)}",
                planner_context=_planner_context(current),
            )

        call = decision.tool_call
        if decision.decision != PlannerDecisionType.CALL_TOOL or call is None:
            reason = decision.degraded_reason or decision.summary
            current = _append_degraded_event(
                current,
                (
                    "Planner decision was invalid; used deterministic fallback. "
                    f"{reason} {_planner_context_suffix(current)}"
                ),
                degraded_reason=reason,
                planner_context=_planner_context(current),
            )
            call = _fallback_tool_call(current, fallback_calls)
        elif call.tool_name not in current.task_policy.allowed_tools:
            reason = f"Planner tool {call.tool_name} is not allowed for {current.task_type.value}."
            current = _append_degraded_event(
                current,
                (
                    "Planner decision was invalid; used deterministic fallback. "
                    f"{reason} {_planner_context_suffix(current)}"
                ),
                degraded_reason=reason,
                planner_context=_planner_context(current),
            )
            call = _fallback_tool_call(current, fallback_calls)

        previous_degraded_count = len(current.degraded_reasons)
        current = _execute_planned_call(current, call, registry)
        if _tool_execution_failed(current, previous_degraded_count):
            break

    if current.step_index >= current.task_policy.max_steps:
        coverage_result = check_coverage(current)
        current = current.model_copy(update={"coverage": coverage_result.coverage})
        if coverage_result.should_finalize:
            return _append_loop_event(
                current,
                AgentPhase.FINALIZE_REPORT,
                ToolStatus.OK,
                (
                    "Coverage is sufficient; finalizing bounded live planner loop. "
                    f"{_planner_context_suffix(current)}"
                ),
                planner_context=_planner_context(current),
            )
        return _append_degraded_event(
            current,
            f"Planner step budget exhausted after {current.task_policy.max_steps} steps.",
        )
    return current


def _fallback_tool_call(state: AgentState, calls: list[ToolCall]) -> ToolCall:
    fallback_index = min(state.tool_call_count, len(calls) - 1)
    fallback = calls[fallback_index]
    return fallback.model_copy(
        update={
            "step_index": state.step_index,
            "summary": f"Deterministic fallback: {fallback.summary}",
        }
    )


def _tool_execution_failed(state: AgentState, previous_degraded_count: int) -> bool:
    if len(state.degraded_reasons) <= previous_degraded_count:
        return False
    latest_event = state.tool_events[-1] if state.tool_events else None
    return latest_event is not None and latest_event.status in {
        ToolStatus.ERROR,
        ToolStatus.DEGRADED,
    }


def _execute_planned_call(
    state: AgentState,
    call: ToolCall,
    registry: ToolRegistry,
) -> AgentState:
    current = _append_loop_event(
        state,
        AgentPhase.BUILD_EVIDENCE_PLAN,
        ToolStatus.OK,
        f"Plan next step: {call.summary} {_planner_context_suffix(state)}",
        tool_name=call.tool_name,
        planner_context=_planner_context(state),
    )
    current = registry.execute(current, call)
    coverage_result = check_coverage(current)
    current = current.model_copy(update={"coverage": coverage_result.coverage})
    return _append_loop_event(
        current,
        AgentPhase.VALIDATE_CLAIMS,
        ToolStatus.OK if coverage_result.coverage.evidence_count else ToolStatus.DEGRADED,
        (
            "Coverage is sufficient to finalize."
            if coverage_result.should_finalize
            else "Coverage gaps remain; continue bounded loop if budget allows."
        ),
    )


def _planner_context_suffix(state: AgentState) -> str:
    context = _planner_context(state)
    return (
        "[planner_context "
        f"remaining_steps={context.remaining_steps} "
        f"remaining_tool_calls={context.remaining_tool_calls} "
        f"coverage={context.coverage_status} "
        f"evidence={context.evidence_count} "
        f"citation_coverage={context.citation_coverage}]"
    )


def _planner_context(state: AgentState) -> PlannerContext:
    return PlannerContext(
        remaining_steps=max(state.task_policy.max_steps - state.step_index, 0),
        remaining_tool_calls=max(state.task_policy.max_tool_calls - state.tool_call_count, 0),
        coverage_status=state.coverage.status,
        evidence_count=state.coverage.evidence_count,
        citation_coverage=state.coverage.citation_coverage,
    )


def _append_degraded_event(
    state: AgentState,
    summary: str,
    *,
    degraded_reason: str | None = None,
    planner_context: PlannerContext | None = None,
) -> AgentState:
    reason = degraded_reason or summary
    event = AgentEvent(
        run_id=state.run_id,
        task_type=state.task_type,
        phase=AgentPhase.DEGRADED,
        status=ToolStatus.DEGRADED,
        summary=summary,
        degraded_reason=reason,
        planner_context=planner_context,
    )
    return state.model_copy(
        update={
            "status": AgentRunStatus.DEGRADED,
            "degraded_reasons": [*state.degraded_reasons, reason],
            "tool_events": [*state.tool_events, event],
        }
    )


def _append_loop_event(
    state: AgentState,
    phase: AgentPhase,
    status: ToolStatus,
    summary: str,
    *,
    tool_name: str | None = None,
    planner_context: PlannerContext | None = None,
) -> AgentState:
    event = AgentEvent(
        run_id=state.run_id,
        task_type=state.task_type,
        phase=phase,
        status=status,
        summary=summary,
        tool_name=tool_name,
        planner_context=planner_context,
    )
    return state.model_copy(update={"tool_events": [*state.tool_events, event]})


def _planned_tool_calls(request: AgentRequest) -> list[ToolCall]:
    if request.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        specs: list[tuple[str, dict[str, Any], str]] = [
            (
                "search_filing_sections",
                {
                    "sections": ["MD&A", "Business"],
                    "query": "product segment demand pricing customers strategy",
                },
                "Search filing sections for business driver evidence.",
            ),
            (
                "search_metric_evidence",
                {
                    "metrics": ["revenue", "segment revenue"],
                    "period": "latest_quarter",
                    "query": "segment revenue growth and demand",
                },
                "Search metric evidence for business driver claims.",
            ),
            (
                "get_business_signals",
                {"signal_types": ["product", "segment", "demand", "pricing", "strategy"]},
                "Collect business signals for the selected task.",
            ),
            (
                "verify_citations",
                {"claims": [], "source_refs": []},
                "Verify citation coverage before finalization.",
            ),
            (
                "finalize_report",
                {"coverage": {}, "draft_sections": {}},
                "Finalize typed business driver report.",
            ),
        ]
    elif request.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        specs = [
            (
                "get_company_facts",
                {"period": "latest_quarter", "metrics": ["operating cash flow", "capex"]},
                "Collect cash flow company facts.",
            ),
            (
                "search_filing_sections",
                {
                    "sections": ["Cash Flows", "MD&A"],
                    "query": "operating cash flow free cash flow capex buybacks debt liquidity",
                },
                "Search filing sections for cash flow and capital allocation evidence.",
            ),
            (
                "search_metric_evidence",
                {
                    "metrics": ["operating cash flow", "capital expenditures"],
                    "period": "latest_quarter",
                    "query": "cash flow capex buybacks debt liquidity",
                },
                "Search metric evidence for cash quality claims.",
            ),
            (
                "verify_citations",
                {"claims": [], "source_refs": []},
                "Verify citation coverage before finalization.",
            ),
            (
                "finalize_report",
                {"coverage": {}, "draft_sections": {}},
                "Finalize typed cash flow report.",
            ),
        ]
    else:
        specs = [
            (
                "get_company_facts",
                {"period": "latest_quarter", "metrics": ["revenue", "gross margin"]},
                "Collect latest earnings company facts.",
            ),
            (
                "search_filing_sections",
                {
                    "sections": ["MD&A", "Risk Factors"],
                    "query": "latest earnings revenue margin drivers risks",
                },
                "Search filing sections for latest earnings evidence.",
            ),
            (
                "search_metric_evidence",
                {
                    "metrics": ["revenue", "gross margin", "operating income"],
                    "period": "latest_quarter",
                    "query": "earnings dashboard metrics",
                },
                "Search metric evidence for the earnings dashboard.",
            ),
            (
                "verify_citations",
                {"claims": [], "source_refs": []},
                "Verify citation coverage before finalization.",
            ),
            (
                "finalize_report",
                {"coverage": {}, "draft_sections": {}},
                "Finalize typed latest earnings report.",
            ),
        ]

    return [
        ToolCall(
            run_id=request.run_id,
            task_type=request.task_type,
            step_index=index,
            tool_name=tool_name,
            tool_input=tool_input,
            summary=summary,
        )
        for index, (tool_name, tool_input, summary) in enumerate(specs)
    ]


def _build_final_report(request: AgentRequest, state: AgentState) -> EvidenceAwareReport:
    source_refs = _source_refs_from_state(state)
    citation_status = _citation_status_from_state(state, source_refs)
    source_refs = [
        source_ref.model_copy(update={"citation_status": citation_status})
        for source_ref in source_refs
    ]
    summary = _summary_for_task(request.task_type)
    claims = [
        EvidenceBoundClaim(
            claim_id=f"{request.run_id}:claim:1",
            text=summary,
            citation_status=citation_status,
            source_refs=source_refs,
        )
    ]
    return EvidenceAwareReport(
        run_id=request.run_id,
        ticker=state.ticker,
        task_type=request.task_type,
        task_sections=cast(
            TaskSpecificSections,
            _task_sections_from_request(request, summary, source_refs, citation_status),
        ),
        sections={"summary": summary},
        claims=claims,
        retrieval_records=state.retrieval_records,
    )


def _source_refs_from_state(state: AgentState) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for ref in state.evidence_memory.source_refs:
        try:
            refs.append(
                SourceRef(
                    source_id=str(ref.get("source_id", "unknown")),
                    section=str(ref.get("section", "unknown")),
                    snippet=str(ref.get("snippet", "")),
                    citation_status=_citation_status_from_value(ref.get("citation_status")),
                )
            )
        except ValueError:
            continue
    return refs


def _citation_status_from_value(value: Any) -> CitationStatus:
    try:
        return CitationStatus(value)
    except (TypeError, ValueError):
        return CitationStatus.UNVERIFIED


def _citation_status_from_state(
    state: AgentState,
    source_refs: list[SourceRef],
) -> CitationStatus:
    for record in state.evidence_memory.citation_results:
        status = _citation_status_from_value(record.get("status"))
        if status in {CitationStatus.SUPPORTED, CitationStatus.PARTIAL}:
            return status
    return source_refs[0].citation_status if source_refs else CitationStatus.MISSING


def _summary_for_task(task_type: ResearchTaskType) -> str:
    summaries = {
        ResearchTaskType.LATEST_EARNINGS_READOUT: (
            "Deterministic latest earnings readout generated from bounded tool evidence."
        ),
        ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE: (
            "Deterministic business driver deep dive generated from bounded tool evidence."
        ),
        ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION: (
            "Deterministic cash flow and capital allocation review generated from "
            "bounded tool evidence."
        ),
    }
    return summaries[task_type]


def _task_sections_from_request(
    request: AgentRequest,
    summary: str,
    source_refs: list[SourceRef],
    citation_status: CitationStatus,
) -> dict[str, Any]:
    evidence_refs = [
        {
            "section": source_ref.section,
            "excerpt": source_ref.snippet,
            "filing_date": source_ref.filing_date,
            "accession_number": source_ref.accession_number,
            "source_id": source_ref.source_id,
        }
        for source_ref in source_refs
    ]
    point = {
        "title": "Deterministic evidence point",
        "summary": summary,
        "evidence_refs": evidence_refs,
        "citation_status": citation_status.value,
    }
    coverage = {
        "status": "complete" if evidence_refs else "degraded",
        "missing_sections": [] if evidence_refs else ["evidence_refs"],
        "evidence_count": len(evidence_refs),
    }
    base = {
        "schema_version": "task_sections.v1",
        "task_type": request.task_type.value,
        "coverage": coverage,
    }

    if request.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        return {
            **base,
            "driver_thesis": {
                "headline": "Business drivers are ready for evidence review",
                "durability": "unclear",
                "summary": summary,
            },
            "driver_map": {
                "product": [point],
                "segment": [point],
                "geography": [],
                "demand": [point],
                "pricing": [],
                "customer": [],
                "strategy": [point],
            },
            "positive_signals": [point],
            "negative_signals": [],
            "watchlist": ["Review live RAG evidence after tool handlers are connected."],
        }

    if request.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        metric = {
            "name": "Cash quality",
            "value": "See evidence",
            "interpretation": summary,
            "evidence_refs": evidence_refs,
            "citation_status": citation_status.value,
        }
        return {
            **base,
            "cash_quality_verdict": {
                "headline": "Cash quality is ready for evidence review",
                "earnings_backed_by_cash": "unclear",
                "summary": summary,
            },
            "cash_metrics": [metric],
            "capital_allocation": {
                "capex": [point],
                "buybacks": [],
                "dividends": [],
                "debt": [],
                "liquidity": [point],
            },
            "allocation_discipline": [point],
            "red_flags": [],
        }

    metric = {
        "name": "Latest earnings context",
        "value": "See evidence",
        "interpretation": summary,
        "evidence_refs": evidence_refs,
        "citation_status": citation_status.value,
    }
    return {
        **base,
        "topline_verdict": {
            "headline": "Latest earnings are ready for evidence review",
            "summary": summary,
            "verdict": "mixed",
        },
        "key_takeaways": [point],
        "financial_dashboard": {
            "metrics": [metric],
            "chart_focus": ["revenue", "margin", "cash flow"],
        },
        "driver_snapshot": [point],
        "risk_snapshot": [point],
    }
