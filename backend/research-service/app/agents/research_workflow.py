import logging
from time import perf_counter
from typing import Any

from app.agents.business_driver_agent import BusinessDriverAgentError, run_business_driver_agent
from app.agents.cash_flow_agent import CashFlowAgentError, run_cash_flow_agent
from app.agents.domain_tools import ResearchToolService
from app.agents.earnings_agent import EarningsAgentError, run_latest_earnings_agent
from app.agents.llm_gateway import LlmClient, OpenAiCompatibleLlmClient
from app.agents.report_synthesizer import (
    build_business_driver_report_from_payload,
    build_cash_flow_report_from_payload,
    build_latest_earnings_report_from_payload,
)
from app.contracts.agent import (
    AgentEvent,
    AgentPhase,
    AgentRequest,
    AgentRunStatus,
    AgentState,
    BoundedAgentResult,
    EvidenceMemory,
    ToolStatus,
    default_task_policy,
)
from app.contracts.report import (
    BusinessDriverSections,
    CapitalAllocation,
    CashFlowCapitalAllocationSections,
    CashQualityVerdict,
    CitationStatus,
    DriverMap,
    DriverThesis,
    EvidenceAwareReport,
    EvidenceBoundClaim,
    EvidenceBoundMetric,
    EvidenceBoundPoint,
    EvidenceRef,
    LatestEarningsSections,
    LatestFinancialDashboard,
    SourceRef,
    TaskSectionCoverage,
    ToplineVerdict,
)
from app.contracts.research_task import ResearchTaskType

logger = logging.getLogger("uvicorn.error")


class ResearchAgentWorkflow:
    def __init__(
        self,
        *,
        tool_service: ResearchToolService | None = None,
        llm_client: LlmClient | None = None,
        rag_pipeline: Any | None = None,
    ) -> None:
        self._tool_service = tool_service or ResearchToolService()
        self._llm_client = llm_client
        self._rag_pipeline = rag_pipeline

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
        if request.facts:
            state = state.model_copy(
                update={
                    "evidence_memory": state.evidence_memory.model_copy(
                        update={"facts": dict(request.facts)}
                    )
                }
            )

        if not isinstance(self._llm_client, OpenAiCompatibleLlmClient):
            state = _append_degraded_event(
                state,
                "OpenAI-compatible LLM client is required for tool-calling research agents.",
            )
            return _result(request, state, final_report=None)

        started_at = perf_counter()
        try:
            final_report, state = self._run_task_agent(request, state, self._llm_client)
        except EarningsAgentError as exc:
            state = _append_degraded_event(
                exc.state,
                f"Earnings research agent failed. {exc}",
                degraded_reason=f"Earnings research agent failed: {exc}",
            )
            final_report = _fallback_report_from_state(request, state, reason=str(exc))
        except BusinessDriverAgentError as exc:
            state = _append_degraded_event(
                exc.state,
                f"Business driver research agent failed. {exc}",
                degraded_reason=f"Business driver research agent failed: {exc}",
            )
            final_report = _fallback_report_from_state(request, state, reason=str(exc))
        except CashFlowAgentError as exc:
            state = _append_degraded_event(
                exc.state,
                f"Cash flow research agent failed. {exc}",
                degraded_reason=f"Cash flow research agent failed: {exc}",
            )
            final_report = _fallback_report_from_state(request, state, reason=str(exc))
        except Exception as exc:
            state = _append_degraded_event(
                state,
                f"Tool-calling research agent failed. {exc}",
                degraded_reason=f"Tool-calling research agent failed: {exc}",
            )
            final_report = None
        stage_summary = _stage_latency_summary(state.tool_events)
        logger.info(
            (
                "research_agent_stage_summary run_id=%s task_type=%s agent=%s "
                "planning_ms=%s tool_ms=%s synthesis_ms=%s total_ms=%s "
                "tool_events=%s reasoning_events=%s"
            ),
            request.run_id,
            request.task_type.value,
            stage_summary["agent_name"],
            stage_summary["planning_ms"],
            stage_summary["tool_ms"],
            stage_summary["synthesis_ms"],
            int((perf_counter() - started_at) * 1000),
            stage_summary["tool_event_count"],
            stage_summary["reasoning_event_count"],
        )
        logger.info(
            "research_agent_complete run_id=%s task_type=%s latency_ms=%s events=%s",
            request.run_id,
            request.task_type.value,
            int((perf_counter() - started_at) * 1000),
            len(state.tool_events),
        )
        return _result(request, state, final_report=final_report)

    def _run_task_agent(
        self,
        request: AgentRequest,
        state: AgentState,
        llm_client: OpenAiCompatibleLlmClient,
    ) -> tuple[EvidenceAwareReport, AgentState]:
        chat_model = llm_client.as_chat_model(model=request.llm_model, timeout_seconds=20)
        if request.task_type == ResearchTaskType.LATEST_EARNINGS_READOUT:
            payload, agent_state = run_latest_earnings_agent(
                request=request,
                state=state,
                llm=chat_model,
                tool_service=self._tool_service,
                rag_pipeline=self._rag_pipeline,
            )
            try:
                return (
                    build_latest_earnings_report_from_payload(request, agent_state, payload),
                    agent_state,
                )
            except Exception as exc:
                raise EarningsAgentError(str(exc), state=agent_state) from exc
        if request.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
            payload, agent_state = run_business_driver_agent(
                request=request,
                state=state,
                llm=chat_model,
                tool_service=self._tool_service,
                rag_pipeline=self._rag_pipeline,
            )
            try:
                return (
                    build_business_driver_report_from_payload(request, agent_state, payload),
                    agent_state,
                )
            except Exception as exc:
                raise BusinessDriverAgentError(str(exc), state=agent_state) from exc
        if request.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
            payload, agent_state = run_cash_flow_agent(
                request=request,
                state=state,
                llm=chat_model,
                tool_service=self._tool_service,
                rag_pipeline=self._rag_pipeline,
            )
            try:
                return (
                    build_cash_flow_report_from_payload(request, agent_state, payload),
                    agent_state,
                )
            except Exception as exc:
                raise CashFlowAgentError(str(exc), state=agent_state) from exc
        raise ValueError(f"Unsupported research task: {request.task_type.value}")


def _append_degraded_event(
    state: AgentState,
    summary: str,
    *,
    degraded_reason: str | None = None,
) -> AgentState:
    reason = degraded_reason or summary
    event = AgentEvent(
        run_id=state.run_id,
        task_type=state.task_type,
        phase=AgentPhase.DEGRADED,
        status=ToolStatus.DEGRADED,
        summary=summary,
        degraded_reason=reason,
    )
    return state.model_copy(
        update={
            "status": AgentRunStatus.DEGRADED,
            "degraded_reasons": [*state.degraded_reasons, reason],
            "tool_events": [*state.tool_events, event],
        }
    )


def _result(
    request: AgentRequest,
    state: AgentState,
    *,
    final_report: EvidenceAwareReport | None,
) -> BoundedAgentResult:
    status = AgentRunStatus.DEGRADED if final_report is None else AgentRunStatus.OK
    return BoundedAgentResult(
        run_id=request.run_id,
        task_type=request.task_type,
        status=status,
        events=state.tool_events,
        degraded_reasons=state.degraded_reasons,
        retrieval_records=state.retrieval_records,
        retryable=final_report is None,
        final_report=final_report.model_dump(mode="json") if final_report is not None else None,
    )


def _fallback_report_from_state(
    request: AgentRequest,
    state: AgentState,
    *,
    reason: str,
) -> EvidenceAwareReport | None:
    source_refs = _source_refs_from_memory(state.evidence_memory)
    metrics = _fallback_metrics(state.evidence_memory, source_refs)
    if not source_refs and not metrics:
        return None
    summary = _fallback_summary(request, reason, metrics, source_refs)
    present_metrics = _present_metrics(metrics)
    coverage = TaskSectionCoverage(
        status="partial",
        missing_sections=["llm_final_synthesis"],
        evidence_count=len(source_refs),
    )
    claims = _fallback_claims(request, summary, source_refs)
    if request.task_type == ResearchTaskType.LATEST_EARNINGS_READOUT:
        task_sections = LatestEarningsSections(
            schema_version="task_sections.v1",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            coverage=coverage,
            company_profile=None,
            topline_verdict=ToplineVerdict(
                headline="Evidence-backed fallback earnings view",
                summary=summary,
                verdict="mixed",
            ),
            key_takeaways=[_fallback_point(summary, source_refs)],
            financial_dashboard=LatestFinancialDashboard(
                metrics=present_metrics[:3],
                chart_focus=[metric.name for metric in present_metrics[:3]],
            ),
            driver_snapshot=[],
            risk_snapshot=[
                _fallback_point(
                    "The final LLM synthesis did not complete, so this section keeps "
                    "the evidence-backed figures and should be treated as partial.",
                    source_refs,
                    title="Synthesis risk",
                )
            ],
        )
    elif request.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        point = _fallback_point(summary, source_refs, title="Evidence-backed driver signal")
        task_sections = BusinessDriverSections(
            schema_version="task_sections.v1",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            coverage=coverage,
            driver_thesis=DriverThesis(
                headline="Evidence-backed fallback driver view",
                durability="unclear",
                summary=summary,
            ),
            driver_map=DriverMap(demand=[point]),
            positive_signals=[point],
            negative_signals=[],
            watchlist=["Review the final LLM synthesis once provider latency recovers."],
        )
    elif request.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        point = _fallback_point(summary, source_refs, title="Cash flow evidence anchor")
        task_sections = CashFlowCapitalAllocationSections(
            schema_version="task_sections.v1",
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            coverage=coverage,
            cash_quality_verdict=CashQualityVerdict(
                headline="Evidence-backed fallback cash view",
                earnings_backed_by_cash="unclear",
                summary=summary,
            ),
            cash_metrics=present_metrics[:3],
            capital_allocation=CapitalAllocation(liquidity=[point]),
            allocation_discipline=[point],
            red_flags=[
                _fallback_point(
                    "The final LLM synthesis did not complete, so allocation discipline "
                    "is partial and should be rechecked when synthesis recovers.",
                    source_refs,
                    title="Partial synthesis",
                )
            ],
        )
    else:
        return None
    return EvidenceAwareReport(
        run_id=request.run_id,
        ticker=state.ticker,
        task_type=request.task_type,
        task_sections=task_sections,
        sections={"summary": summary, "synthesis": "deterministic_fallback"},
        claims=claims,
        retrieval_records=state.retrieval_records,
    )


def _source_refs_from_memory(memory: EvidenceMemory) -> list[SourceRef]:
    refs: list[SourceRef] = []
    for ref in memory.source_refs:
        try:
            refs.append(
                SourceRef(
                    source_id=str(ref.get("source_id", "fallback_source")),
                    section=str(ref.get("section", "Evidence")),
                    snippet=str(ref.get("snippet", "")),
                    citation_status=_citation_status_from_value(ref.get("citation_status")),
                    filing_type=_optional_str(ref.get("filing_type")),
                    filing_date=_optional_str(ref.get("filing_date")),
                    accession_number=_optional_str(ref.get("accession_number")),
                )
            )
        except ValueError:
            continue
    return refs


def _fallback_metrics(
    memory: EvidenceMemory,
    source_refs: list[SourceRef],
) -> list[EvidenceBoundMetric]:
    refs_by_id = {source_ref.source_id: source_ref for source_ref in source_refs}
    metrics: list[EvidenceBoundMetric] = []
    for record in memory.metric_evidence:
        name = str(record.get("metric") or record.get("normalized_metric") or "").strip()
        if not name:
            continue
        source_ref = refs_by_id.get(str(record.get("source_id") or ""))
        metric_refs = [_evidence_ref(source_ref)] if source_ref is not None else []
        metrics.append(
            EvidenceBoundMetric(
                name=name,
                value=_metric_value(record.get("value"), record.get("unit")),
                period=_optional_str(record.get("fact_period") or record.get("period")),
                interpretation=_metric_interpretation(record, source_ref),
                evidence_refs=metric_refs,
                citation_status=source_ref.citation_status
                if source_ref is not None
                else CitationStatus.UNVERIFIED,
            )
        )
    return metrics[:3]


def _fallback_summary(
    request: AgentRequest,
    reason: str,
    metrics: list[EvidenceBoundMetric],
    source_refs: list[SourceRef],
) -> str:
    metric_text = ", ".join(_display_metric(metric) for metric in _present_metrics(metrics)[:3])
    missing_metrics = _missing_metric_names(metrics)
    missing_text = _missing_metric_boundary_text(
        missing_metrics,
        zh=_is_zh_locale(request.language),
    )
    evidence_text = _clip(source_refs[0].snippet, 180) if source_refs else "evidence was collected"
    base = metric_text or evidence_text
    if _is_zh_locale(request.language):
        boundary = f"；{missing_text}" if missing_text else ""
        return (
            f"{request.ticker} 的证据收集已完成，"
            "当前报告先以已验证的 SEC 指标和 filing 片段形成保守结论："
            f"{base}{boundary}。这份结论应视为证据优先版本，后续需要继续观察同一指标在下一季度是否延续。"
        )
    boundary = f"; {missing_text}" if missing_text else ""
    return (
        f"{request.ticker} evidence collection completed, and this conservative report "
        f"uses verified SEC metrics and filing snippets first: {base}{boundary}. Treat it as an "
        "evidence-first view until the next quarter confirms whether the same signals persist."
    )


def _fallback_claims(
    request: AgentRequest,
    summary: str,
    source_refs: list[SourceRef],
) -> list[EvidenceBoundClaim]:
    if not source_refs:
        return []
    claims = [
        EvidenceBoundClaim(
            claim_id=f"{request.run_id}:fallback_claim:1",
            text=summary,
            citation_status=source_refs[0].citation_status,
            source_refs=source_refs[:3],
        )
    ]
    for index, source_ref in enumerate(source_refs[1:3], start=2):
        claims.append(
            EvidenceBoundClaim(
                claim_id=f"{request.run_id}:fallback_claim:{index}",
                text=_clip(source_ref.snippet, 220),
                citation_status=source_ref.citation_status,
                source_refs=[source_ref],
            )
        )
    return claims


def _fallback_point(
    summary: str,
    source_refs: list[SourceRef],
    *,
    title: str = "Evidence-backed fallback",
) -> EvidenceBoundPoint:
    return EvidenceBoundPoint(
        title=title,
        summary=summary,
        evidence_refs=[_evidence_ref(source_ref) for source_ref in source_refs[:1]],
        citation_status=(
            source_refs[0].citation_status if source_refs else CitationStatus.UNVERIFIED
        ),
    )


def _evidence_ref(source_ref: SourceRef) -> EvidenceRef:
    return EvidenceRef(
        section=source_ref.section,
        excerpt=source_ref.snippet,
        filing_date=source_ref.filing_date,
        accession_number=source_ref.accession_number,
        source_id=source_ref.source_id,
    )


def _citation_status_from_value(value: Any) -> CitationStatus:
    try:
        return CitationStatus(str(value or CitationStatus.UNVERIFIED.value))
    except ValueError:
        return CitationStatus.UNVERIFIED


def _metric_interpretation(
    record: dict[str, Any],
    source_ref: SourceRef | None,
) -> str:
    concept = str(record.get("concept") or "").strip()
    if concept:
        return f"SEC companyfacts concept {concept}."
    if source_ref is not None:
        return _clip(source_ref.snippet, 220)
    return "Evidence-backed metric collected before final synthesis failed."


def _metric_value(value: object, unit: object) -> str:
    if value is None:
        return "Not extracted"
    formatted = _format_fallback_metric_value(value, unit)
    if str(unit or "").strip() == "USD" and not formatted.startswith("$"):
        return f"${formatted}"
    return formatted


def _display_metric(metric: EvidenceBoundMetric) -> str:
    return f"{metric.name}: {metric.value}"


def _present_metrics(metrics: list[EvidenceBoundMetric]) -> list[EvidenceBoundMetric]:
    return [metric for metric in metrics if not _is_missing_metric(metric)]


def _missing_metric_names(metrics: list[EvidenceBoundMetric]) -> list[str]:
    return [metric.name for metric in metrics if _is_missing_metric(metric)]


def _is_missing_metric(metric: EvidenceBoundMetric) -> bool:
    return metric.value.strip().lower() in {"not extracted", "n/a", "na", "none", ""}


def _missing_metric_boundary_text(metric_names: list[str], *, zh: bool) -> str:
    if not metric_names:
        return ""
    visible_names = ", ".join(metric_names[:3])
    if zh:
        return f"{visible_names} 未在当前证据包中稳定抽取，不能作为强结论"
    return (
        f"{visible_names} were not stably extracted from the current evidence pack "
        "and should not be treated as strong conclusions"
    )


def _compact_number(value: int | float) -> str:
    absolute = abs(float(value))
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value:,.0f}"


def _format_fallback_metric_value(value: object, unit: object) -> str:
    if isinstance(value, int | float):
        numeric_value = float(value)
        unit_text = str(unit or "").strip().lower()
        if unit_text in {"pure", "ratio", "percent", "percentage"} or abs(numeric_value) <= 1:
            return (
                f"{numeric_value * 100:.1f}%"
                if abs(numeric_value) <= 1
                else f"{numeric_value:.1f}%"
            )
        return _compact_number(numeric_value)
    return str(value)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _clip(text: str, limit: int = 700) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}..."


def _is_zh_locale(language: str | None) -> bool:
    return str(language or "").lower().startswith("zh")


def _stage_latency_summary(events: list[AgentEvent]) -> dict[str, int | str]:
    planning_ms = sum(
        event.latency_ms
        for event in events
        if event.event_kind == "reasoning" and event.phase == AgentPhase.BUILD_EVIDENCE_PLAN
    )
    synthesis_ms = sum(
        event.latency_ms
        for event in events
        if event.event_kind == "reasoning" and event.phase == AgentPhase.DRAFT_REPORT_SECTIONS
    )
    tool_ms = sum(event.latency_ms for event in events if event.event_kind == "tool")
    return {
        "agent_name": next(
            (str(event.agent_name) for event in events if event.agent_name),
            "unknown",
        ),
        "planning_ms": planning_ms,
        "tool_ms": tool_ms,
        "synthesis_ms": synthesis_ms,
        "tool_event_count": sum(1 for event in events if event.event_kind == "tool"),
        "reasoning_event_count": sum(1 for event in events if event.event_kind == "reasoning"),
    }
