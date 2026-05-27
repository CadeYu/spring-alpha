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
    SourceRef,
    TaskSectionCoverage,
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
            final_report = _fallback_report_from_state(request, exc.state, reason=str(exc))
            if final_report is not None and _is_final_synthesis_failure(str(exc)):
                state = exc.state
            else:
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


def _is_final_synthesis_failure(reason: str) -> bool:
    normalized = reason.lower()
    return "final synthesis failed" in normalized or "final json was invalid" in normalized


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
    report_source_refs = (
        _business_driver_report_source_refs(source_refs)
        if request.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE
        else source_refs
    )
    summary = _fallback_summary(request, reason, metrics, report_source_refs)
    present_metrics = _present_metrics(metrics)
    coverage = TaskSectionCoverage(
        status="partial",
        missing_sections=["llm_final_synthesis"],
        evidence_count=len(source_refs),
    )
    claims = _fallback_claims(request, summary, report_source_refs)
    if request.task_type == ResearchTaskType.LATEST_EARNINGS_READOUT:
        fallback_report = build_latest_earnings_report_from_payload(
            request,
            state,
            _latest_earnings_fallback_payload(
                summary=summary,
                metrics=present_metrics[:3],
                source_refs=source_refs,
            ),
        )
        return fallback_report.model_copy(
            update={
                "task_sections": fallback_report.task_sections.model_copy(
                    update={"coverage": coverage}
                ),
                "sections": {
                    "summary": summary,
                    "synthesis": "deterministic_fallback",
                },
                "claims": claims,
            }
        )
    elif request.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        task_sections = _business_driver_fallback_sections(
            request=request,
            state=state,
            summary=summary,
            metrics=present_metrics,
            source_refs=source_refs,
            coverage=coverage,
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


def _latest_earnings_fallback_payload(
    *,
    summary: str,
    metrics: list[EvidenceBoundMetric],
    source_refs: list[SourceRef],
) -> dict[str, Any]:
    fallback_source_ids = [source_ref.source_id for source_ref in source_refs[:3]]
    primary_source_ids = fallback_source_ids[:1]
    primary_metric = _primary_fallback_metric(metrics)
    risk_source = _risk_source_ref(source_refs, primary_source_ids)
    return {
        "company_profile": None,
        "topline_verdict": {
            "headline": "Evidence-backed fallback earnings view",
            "summary": summary,
            "verdict": "mixed",
            "confidence": "low",
        },
        "key_takeaways": [
            _fallback_payload_point(
                title="Evidence-backed fallback",
                summary=summary,
                source_ids=primary_source_ids,
                citation_status=_fallback_citation_status(source_refs),
            )
        ],
        "financial_dashboard": {
            "metrics": [
                _fallback_payload_metric(metric)
                for metric in metrics
                if not _is_missing_metric(metric)
            ],
            "chart_focus": [metric.name for metric in metrics if not _is_missing_metric(metric)],
        },
        "driver_snapshot": [
            _fallback_payload_point(
                title=_driver_fallback_title(primary_metric),
                summary=_driver_fallback_summary(primary_metric, summary),
                source_ids=_metric_source_ids(primary_metric) or primary_source_ids,
                citation_status=_fallback_citation_status(source_refs),
            )
        ],
        "risk_snapshot": [
            _fallback_payload_point(
                title=_risk_fallback_title(risk_source),
                summary=_risk_fallback_summary(risk_source),
                source_ids=(
                    [risk_source.source_id]
                    if risk_source is not None
                    else primary_source_ids
                ),
                citation_status=(
                    risk_source.citation_status
                    if risk_source is not None
                    else _fallback_citation_status(source_refs)
                ),
            )
        ],
        "claims": [
            {
                "text": summary,
                "source_ids": primary_source_ids,
                "citation_status": _fallback_citation_status(source_refs).value,
            }
        ],
    }


def _primary_fallback_metric(
    metrics: list[EvidenceBoundMetric],
) -> EvidenceBoundMetric | None:
    present_metrics = [metric for metric in metrics if not _is_missing_metric(metric)]
    if not present_metrics:
        return None
    priority_terms = ("revenue", "sales", "operating income", "margin", "cash flow")
    for term in priority_terms:
        for metric in present_metrics:
            if term in metric.name.strip().lower():
                return metric
    return present_metrics[0]


def _driver_fallback_title(metric: EvidenceBoundMetric | None) -> str:
    if metric is None:
        return "Evidence anchor"
    return f"{_title_case_metric(metric.name)} evidence anchor"


def _driver_fallback_summary(metric: EvidenceBoundMetric | None, summary: str) -> str:
    if metric is None:
        return summary
    return (
        f"{metric.name} of {metric.value} is the clearest available earnings driver "
        f"before final synthesis completed. {metric.interpretation}"
    )


def _business_driver_fallback_point(
    summary: str,
    metrics: list[EvidenceBoundMetric],
    source_refs: list[SourceRef],
) -> EvidenceBoundPoint:
    metric = _primary_fallback_metric(metrics)
    if metric is None:
        return _fallback_point(summary, source_refs, title="Evidence-backed demand signal")
    fallback_refs = [_evidence_ref(source_refs[0])] if source_refs else []
    return EvidenceBoundPoint(
        title=f"{_title_case_metric(metric.name)} demand signal",
        summary=(
            f"{metric.name} of {metric.value} is the clearest available demand or "
            f"scale signal in the collected evidence. {metric.interpretation}"
        ),
        evidence_refs=metric.evidence_refs or fallback_refs,
        citation_status=metric.citation_status,
    )


def _business_driver_context_point(
    source_refs: list[SourceRef],
    *,
    title: str,
    summary: str,
) -> EvidenceBoundPoint:
    return EvidenceBoundPoint(
        title=title,
        summary=summary,
        evidence_refs=[_evidence_ref(source_refs[0])] if source_refs else [],
        citation_status=(
            source_refs[0].citation_status
            if source_refs
            else CitationStatus.UNVERIFIED
        ),
    )


def _business_driver_fallback_sections(
    *,
    request: AgentRequest,
    state: AgentState,
    summary: str,
    metrics: list[EvidenceBoundMetric],
    source_refs: list[SourceRef],
    coverage: TaskSectionCoverage,
) -> BusinessDriverSections:
    revenue_metric = _metric_by_terms(metrics, ("revenue", "sales", "net sales"))
    margin_metric = _metric_by_terms(
        metrics,
        ("margin", "gross profit", "operating income", "operating profit"),
    )
    revenue_point = _business_driver_fallback_lens_point(
        request=request,
        state=state,
        title_zh="收入桥接证据",
        title_en="Revenue bridge evidence",
        lens="revenue_bridge",
        metric=revenue_metric,
        source_refs=source_refs,
    )
    segment_point = _business_driver_fallback_lens_point(
        request=request,
        state=state,
        title_zh="分部动能证据",
        title_en="Segment momentum evidence",
        lens="segment_momentum",
        metric=_metric_by_terms(metrics, ("segment", "product", "service")),
        source_refs=source_refs,
    )
    margin_point = _business_driver_fallback_lens_point(
        request=request,
        state=state,
        title_zh="利润率与组合证据",
        title_en="Margin and mix evidence",
        lens="margin_and_mix",
        metric=margin_metric,
        source_refs=source_refs,
    )
    demand_point = _business_driver_fallback_lens_point(
        request=request,
        state=state,
        title_zh="需求信号证据",
        title_en="Demand signal evidence",
        lens="demand_signals",
        metric=revenue_metric,
        source_refs=source_refs,
    )
    thesis_summary = _business_driver_fallback_thesis_summary(
        request=request,
        summary=summary,
        points=[revenue_point, segment_point, margin_point, demand_point],
    )
    thesis_title = (
        "业务驱动证据优先结论"
        if _is_zh_locale(request.language)
        else "Evidence-backed business driver thesis"
    )
    return BusinessDriverSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        coverage=coverage,
        driver_thesis=DriverThesis(
            headline=thesis_title,
            durability="mixed" if source_refs else "unclear",
            summary=thesis_summary,
        ),
        driver_map=DriverMap(
            revenue_bridge=revenue_point,
            segment_momentum=segment_point,
            margin_and_mix=margin_point,
            demand_signals=demand_point,
        ),
    )


_BUSINESS_DRIVER_LENS_TERMS: dict[str, tuple[str, ...]] = {
    "revenue_bridge": (
        "revenue",
        "sales",
        "net sales",
        "growth",
        "increased",
        "declined",
    ),
    "segment_momentum": (
        "segment",
        "services",
        "service",
        "product",
        "data center",
        "client",
        "gaming",
        "embedded",
        "geography",
        "region",
    ),
    "margin_and_mix": (
        "margin",
        "gross margin",
        "gross profit",
        "mix",
        "pricing",
        "price",
        "cost",
        "operating income",
    ),
    "demand_signals": (
        "demand",
        "customer",
        "installed base",
        "engagement",
        "orders",
        "backlog",
        "unit",
        "shipment",
        "accelerator",
        "growth",
    ),
}

_BUSINESS_DRIVER_LENS_SIGNAL_TYPES: dict[str, tuple[str, ...]] = {
    "revenue_bridge": ("demand", "product"),
    "segment_momentum": ("segment", "product"),
    "margin_and_mix": ("pricing", "product"),
    "demand_signals": ("demand", "product"),
}


_NOISY_BUSINESS_DRIVER_SNIPPET_PHRASES = (
    "business metrics utilized by investors",
    "comparable sales percentage changes by revenue category",
    "disaggregate the company's net revenue",
    "disaggregate net revenue",
    "foreign currency risk",
    "following table",
    "following tables",
    "government securities",
    "market risk",
    "net revenue by revenue category",
    "other revenue primarily includes",
    "principal transactions revenue",
    "revenue is generally recognized",
    "revenue sharing",
    "table of contents",
)


def _business_driver_fallback_lens_point(
    *,
    request: AgentRequest,
    state: AgentState,
    title_zh: str,
    title_en: str,
    lens: str,
    metric: EvidenceBoundMetric | None,
    source_refs: list[SourceRef],
) -> EvidenceBoundPoint:
    terms = _BUSINESS_DRIVER_LENS_TERMS[lens]
    signal_types = _BUSINESS_DRIVER_LENS_SIGNAL_TYPES[lens]
    signal_records = _business_signal_records(state.evidence_memory, signal_types, terms)
    lens_refs = _business_driver_lens_refs(
        lens=lens,
        metric=metric,
        signal_records=signal_records,
        source_refs=source_refs,
        terms=terms,
    )
    summary = _business_driver_fallback_lens_summary(
        request=request,
        lens=lens,
        metric=metric,
        source_refs=lens_refs,
        signal_records=signal_records,
    )
    citation_status = _business_driver_citation_status(metric, lens_refs)
    return EvidenceBoundPoint(
        title=title_zh if _is_zh_locale(request.language) else title_en,
        summary=summary,
        evidence_refs=_business_driver_evidence_refs(metric, lens_refs),
        citation_status=citation_status,
    )


def _business_driver_fallback_lens_summary(
    *,
    request: AgentRequest,
    lens: str,
    metric: EvidenceBoundMetric | None,
    source_refs: list[SourceRef],
    signal_records: list[dict[str, Any]],
) -> str:
    zh = _is_zh_locale(request.language)
    metric_text = _display_metric(metric) if metric is not None else ""
    source_text = _business_driver_source_text(source_refs)
    signal_text = _business_driver_signal_text(signal_records)
    if lens in {"revenue_bridge", "margin_and_mix"}:
        evidence_text = source_text or signal_text or metric_text
    else:
        evidence_text = signal_text or source_text or metric_text
    evidence_text = evidence_text or ("已收集证据" if zh else "collected evidence")
    if zh:
        if lens == "revenue_bridge":
            anchor = (
                f"以 {metric_text} 作为量化锚点"
                if metric_text
                else "主要依赖已检索的 filing 证据"
            )
            return (
                f"{request.ticker} 的 revenue bridge {anchor}；对应证据显示：{evidence_text}。"
                "这说明收入侧仍是判断业务动能的第一层证据，投资上需要继续和分部表现、利润率转化一起验证。"
                "当前结论只限定在已检索证据内，不外推未被 source_ids 支持的需求叙事。"
            )
        if lens == "segment_momentum":
            return (
                f"{request.ticker} 的 segment momentum 主要来自这条证据：{evidence_text}。"
                "如果分部或产品线层面的动能能和总收入同向，它会提高收入质量；如果只靠单一业务拉动，则后续季度需要验证可持续性。"
                "这段判断优先使用 segment、product 或 geography 相关 filing 片段，"
                "因此比通用宏观叙事更可追溯。"
            )
        if lens == "margin_and_mix":
            anchor = f"量化锚点是 {metric_text}；" if metric_text else ""
            return (
                f"{request.ticker} 的 margin and mix 线索中，{anchor}关键证据是：{evidence_text}。"
                "这说明投资者不能只看收入方向，还要看产品组合、定价和成本是否把收入转成利润。"
                "如果证据没有明确拆出 price、cost 和 mix，这里应保持 partial 结论。"
            )
        return (
            f"{request.ticker} 的 demand signals 来自：{evidence_text}。"
            "这类信号能帮助判断收入是由真实客户需求、装机基础或订单动能驱动，还是仅由短期价格和渠道变化支撑。"
            "在当前证据范围内，需求结论应和 revenue bridge 交叉验证，避免把单个片段解读成完整趋势。"
        )
    if lens == "revenue_bridge":
        anchor = (
            f"uses {metric_text} as the quantitative anchor"
            if metric_text
            else "rests on the retrieved filing evidence"
        )
        return (
            f"{request.ticker}'s revenue bridge {anchor}. Evidence: {evidence_text}. "
            "This keeps revenue as the first operating signal, while still requiring "
            "confirmation from segment momentum and margin conversion."
        )
    if lens == "segment_momentum":
        return (
            f"{request.ticker}'s segment momentum is anchored by this evidence: {evidence_text}. "
            "A segment-level signal matters because it shows whether revenue strength is broad "
            "or concentrated in one business line."
        )
    if lens == "margin_and_mix":
        anchor = f"The metric anchor is {metric_text}. " if metric_text else ""
        return (
            f"{anchor}{request.ticker}'s margin and mix read comes from: {evidence_text}. "
            "This keeps the investment read tied to whether revenue converts into better "
            "profitability through product mix, pricing, or cost control."
        )
    return (
        f"{request.ticker}'s demand signals come from: {evidence_text}. "
        "The signal is useful only when it cross-checks against revenue and segment evidence, "
        "so the conclusion remains bounded to the retrieved sources."
    )


def _business_driver_fallback_thesis_summary(
    *,
    request: AgentRequest,
    summary: str,
    points: list[EvidenceBoundPoint],
) -> str:
    snippets = [
        _clip(point.summary, 140)
        for point in points
        if point.summary.strip()
    ]
    if _is_zh_locale(request.language):
        return (
            f"{request.ticker} 的业务驱动结论应以已检索证据为边界："
            f"{summary} 四个核心观察分别是：{' '.join(snippets[:4])}"
        )
    return (
        f"{request.ticker}'s business driver thesis is bounded by the retrieved evidence: "
        f"{summary} The four operating observations are: {' '.join(snippets[:4])}"
    )


def _metric_by_terms(
    metrics: list[EvidenceBoundMetric],
    terms: tuple[str, ...],
) -> EvidenceBoundMetric | None:
    for metric in metrics:
        metric_name = metric.name.strip().lower()
        if any(term in metric_name for term in terms):
            return metric
    return None


def _source_refs_from_metric(
    metric: EvidenceBoundMetric | None,
    source_refs: list[SourceRef],
) -> list[SourceRef]:
    if metric is None:
        return []
    source_ids = {
        evidence_ref.source_id
        for evidence_ref in metric.evidence_refs
        if evidence_ref.source_id
    }
    return [source_ref for source_ref in source_refs if source_ref.source_id in source_ids]


def _source_refs_from_signals(
    signal_records: list[dict[str, Any]],
    source_refs: list[SourceRef],
) -> list[SourceRef]:
    refs_by_id = {source_ref.source_id: source_ref for source_ref in source_refs}
    refs: list[SourceRef] = []
    for record in signal_records:
        source_id = str(record.get("source_id") or "").strip()
        if source_id in refs_by_id:
            refs.append(refs_by_id[source_id])
        elif source_id:
            refs.append(
                SourceRef(
                    source_id=source_id,
                    section=str(record.get("section") or "Business signal"),
                    snippet=str(record.get("snippet") or record.get("summary") or ""),
                    citation_status=_citation_status_from_value(record.get("citation_status")),
                )
            )
    return refs


def _source_refs_matching_terms(
    source_refs: list[SourceRef],
    terms: tuple[str, ...],
) -> list[SourceRef]:
    matches: list[SourceRef] = []
    for source_ref in source_refs:
        if not _is_clean_business_driver_source_ref(source_ref):
            continue
        searchable = f"{source_ref.section} {source_ref.snippet}".lower()
        if any(term in searchable for term in terms):
            matches.append(source_ref)
    return matches


def _business_driver_lens_refs(
    *,
    lens: str,
    metric: EvidenceBoundMetric | None,
    signal_records: list[dict[str, Any]],
    source_refs: list[SourceRef],
    terms: tuple[str, ...],
) -> list[SourceRef]:
    metric_refs = _clean_business_driver_source_refs(
        _source_refs_from_metric(metric, source_refs)
    )
    signal_refs = _clean_business_driver_source_refs(
        _source_refs_from_signals(signal_records, source_refs)
    )
    term_refs = _source_refs_matching_terms(source_refs, terms)
    broad_fallback_refs = (
        _clean_business_driver_source_refs(source_refs[:1])
        if lens == "revenue_bridge"
        else []
    )
    if lens in {"revenue_bridge", "margin_and_mix"}:
        ordered_refs = [*metric_refs, *signal_refs, *term_refs, *broad_fallback_refs]
    else:
        ordered_refs = [*signal_refs, *term_refs, *metric_refs, *broad_fallback_refs]
    return _dedupe_business_driver_refs(ordered_refs)


def _business_signal_records(
    memory: EvidenceMemory,
    signal_types: tuple[str, ...],
    terms: tuple[str, ...],
) -> list[dict[str, Any]]:
    exact_matches: list[dict[str, Any]] = []
    keyword_matches: list[dict[str, Any]] = []
    for record in memory.business_signals:
        signal_type = str(record.get("signal_type") or "").strip().lower()
        searchable_text = " ".join(
            str(record.get(key) or "")
            for key in ("signal", "summary", "section", "snippet")
        )
        if _is_noisy_business_driver_snippet(searchable_text):
            continue
        searchable = searchable_text.lower()
        if signal_type in signal_types:
            exact_matches.append(record)
        elif any(term in searchable for term in terms):
            keyword_matches.append(record)
    return [*exact_matches, *keyword_matches]


def _dedupe_business_driver_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    seen: set[str] = set()
    deduped: list[SourceRef] = []
    for source_ref in source_refs:
        if not _is_clean_business_driver_source_ref(source_ref):
            continue
        key = source_ref.source_id or source_ref.snippet
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(source_ref)
    return deduped[:3]


def _business_driver_source_text(source_refs: list[SourceRef]) -> str:
    for source_ref in source_refs:
        if _is_clean_business_driver_source_ref(source_ref):
            return _clip(source_ref.snippet, 220)
    return ""


def _business_driver_signal_text(signal_records: list[dict[str, Any]]) -> str:
    for record in signal_records:
        text = str(record.get("summary") or record.get("snippet") or "").strip()
        if text and not _is_noisy_business_driver_snippet(text):
            return _clip(text, 220)
    return ""


def _business_driver_citation_status(
    metric: EvidenceBoundMetric | None,
    source_refs: list[SourceRef],
) -> CitationStatus:
    if source_refs:
        return source_refs[0].citation_status
    if metric is not None:
        return metric.citation_status
    return CitationStatus.UNVERIFIED


def _business_driver_evidence_refs(
    metric: EvidenceBoundMetric | None,
    source_refs: list[SourceRef],
) -> list[EvidenceRef]:
    evidence_refs: list[EvidenceRef] = []
    seen: set[str] = set()
    for evidence_ref in metric.evidence_refs if metric is not None else []:
        if _is_noisy_business_driver_snippet(evidence_ref.excerpt):
            continue
        key = evidence_ref.source_id or evidence_ref.excerpt
        if key and key not in seen:
            seen.add(key)
            evidence_refs.append(evidence_ref)
    for source_ref in source_refs:
        key = source_ref.source_id or source_ref.snippet
        if key and key not in seen:
            seen.add(key)
            evidence_refs.append(_evidence_ref(source_ref))
    return evidence_refs[:3]


def _business_driver_report_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    return _clean_business_driver_source_refs(source_refs)


def _clean_business_driver_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    return [
        source_ref
        for source_ref in source_refs
        if _is_clean_business_driver_source_ref(source_ref)
    ]


def _is_clean_business_driver_source_ref(source_ref: SourceRef) -> bool:
    return not _is_noisy_business_driver_snippet(
        f"{source_ref.section} {source_ref.snippet}"
    )


def _is_noisy_business_driver_snippet(text: str) -> bool:
    normalized = " ".join(str(text or "").split())
    if not normalized:
        return True
    lower_text = normalized.lower()
    if any(phrase in lower_text for phrase in _NOISY_BUSINESS_DRIVER_SNIPPET_PHRASES):
        return True
    pipe_count = normalized.count("|")
    if pipe_count >= 4 or "---|---" in normalized:
        return True
    digits = sum(character.isdigit() for character in normalized)
    separators = sum(1 for character in normalized if character in "|,$%")
    if digits >= 12 and separators >= 5:
        return True
    return False


def _risk_source_ref(
    source_refs: list[SourceRef],
    primary_source_ids: list[str],
) -> SourceRef | None:
    for source_ref in source_refs:
        section = source_ref.section.strip().lower()
        snippet = source_ref.snippet.strip().lower()
        if (
            "risk" in section
            or "risk" in snippet
            or "pressure" in snippet
            or "uncertainty" in snippet
        ):
            return source_ref
    for source_ref in source_refs:
        if source_ref.source_id not in primary_source_ids:
            return source_ref
    return source_refs[0] if source_refs else None


def _risk_fallback_title(source_ref: SourceRef | None) -> str:
    if source_ref is None:
        return "Evidence risk watch"
    return f"{_clip_title(source_ref.section)} risk watch"


def _risk_fallback_summary(source_ref: SourceRef | None) -> str:
    if source_ref is None:
        return (
            "The final LLM synthesis did not complete, so risk framing remains "
            "partial until the next full analysis run."
        )
    return (
        f"{_clip(source_ref.snippet, 180)} This keeps the earnings read balanced "
        "until final synthesis can reconcile the driver and risk evidence."
    )


def _metric_source_ids(metric: EvidenceBoundMetric | None) -> list[str]:
    if metric is None:
        return []
    return [
        evidence_ref.source_id
        for evidence_ref in metric.evidence_refs
        if evidence_ref.source_id
    ]


def _fallback_payload_metric(metric: EvidenceBoundMetric) -> dict[str, Any]:
    return {
        "name": metric.name,
        "value": metric.value,
        "period": metric.period,
        "interpretation": metric.interpretation,
        "source_ids": [
            evidence_ref.source_id
            for evidence_ref in metric.evidence_refs
            if evidence_ref.source_id
        ],
        "citation_status": metric.citation_status.value,
    }


def _fallback_payload_point(
    *,
    title: str,
    summary: str,
    source_ids: list[str],
    citation_status: CitationStatus,
) -> dict[str, Any]:
    return {
        "title": title,
        "summary": summary,
        "source_ids": source_ids,
        "citation_status": citation_status.value,
    }


def _fallback_citation_status(source_refs: list[SourceRef]) -> CitationStatus:
    if not source_refs:
        return CitationStatus.UNVERIFIED
    return source_refs[0].citation_status


def _title_case_metric(value: str) -> str:
    return " ".join(part.capitalize() for part in value.strip().split())


def _clip_title(value: str) -> str:
    title = " ".join(value.strip().split())
    return _clip(title, 64) if title else "Evidence"


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
