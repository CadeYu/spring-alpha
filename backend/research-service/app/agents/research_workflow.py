import logging
import re
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
from app.agents.structured_facts import normalize_metric_name
from app.agents.zh_text_helpers import (
    localize_market_classification,
    localize_market_classifications_in_text,
    summarize_english_business_snippet_for_zh,
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
    BullBearNarrative,
    BusinessDriverSections,
    CapitalAllocation,
    CashFlowCapitalAllocationSections,
    CashQualityVerdict,
    CitationStatus,
    EvidenceAwareReport,
    EvidenceBoundClaim,
    EvidenceBoundMetric,
    EvidenceBoundPoint,
    EvidenceRef,
    SentimentHeader,
    SourceDivergence,
    SourceRef,
    TaskSectionCoverage,
)
from app.contracts.research_task import ResearchTaskType

logger = logging.getLogger("uvicorn.error")

_ZH_METRIC_LABELS = {
    "revenue": "收入",
    "sales": "收入",
    "net sales": "收入",
    "gross margin": "毛利率",
    "operating margin": "经营利润率",
    "gross profit": "毛利润",
    "operating income": "经营利润",
    "net income": "净利润",
    "operating cash flow": "经营现金流",
    "free cash flow": "自由现金流",
    "capital expenditures": "资本开支",
    "current ratio": "流动比率",
    "total debt": "总债务",
    "cash and short term investments": "现金及短期投资",
}

_ZH_FALLBACK_TEXT_REPLACEMENTS = (
    (
        r"\bData Center segment revenue increased as EPYC demand improved\b",
        "数据中心分部收入增长，EPYC 需求改善提供支撑",
    ),
    (
        r"\bCustomer demand for AI accelerators remained strong\b",
        "AI 加速器客户需求保持强劲",
    ),
    (
        r"\bGross margin expanded because product mix improved\b",
        "产品组合改善推动毛利率扩张",
    ),
    (
        r"\bCustomer concentration and supply constraints remain key risks\b",
        "客户集中度和供应约束仍是主要风险",
    ),
    (
        (
            r"\bWireless service revenue increased as fixed wireless access and "
            r"fiber broadband demand supported customer additions\b"
        ),
        "无线服务收入增长，固定无线接入和光纤宽带需求支撑客户新增",
    ),
    (
        r"\bRevenue was (?P<value>\$?-?\d+(?:\.\d+)?[BMK]?) in the quarter\b",
        r"本季度收入为 \g<value>",
    ),
    (
        r"\bNet income was (?P<value>\$?-?\d+(?:\.\d+)?[BMK]?)\b",
        r"净利润为 \g<value>",
    ),
    (
        r"\bOperating cash flow was (?P<value>-?\$?-?\d+(?:\.\d+)?[BMK]?)\b",
        r"经营现金流为 \g<value>",
    ),
    (
        r"\bFree cash flow was (?P<value>-?\$?-?\d+(?:\.\d+)?[BMK]?)\b",
        r"自由现金流为 \g<value>",
    ),
    (
        r"\bCash and short-term investments were (?P<value>\$?-?\d+(?:\.\d+)?[BMK]?)\b",
        r"现金及短期投资为 \g<value>",
    ),
    (
        r"\bSEC companyfacts concept\s+[A-Za-z0-9]+\.?",
        "SEC 公司事实指标提供了对应指标来源。",
    ),
    (
        r"\bPaymentsToAcquirePropertyPlantAndEquipment\b",
        "购置固定资产相关资本开支",
    ),
    (r"\brevenue bridge\b", "收入桥接"),
    (r"\bsegment momentum\b", "分部动能"),
    (r"\bmargin and mix\b", "利润率与组合"),
    (r"\bdemand signals\b", "需求信号"),
    (r"\bsource_ids\b", "证据来源"),
    (r"\bfiling\b", "披露文件"),
    (r"\bpartial\b", "阶段性"),
    (r"\bprice\b", "价格"),
    (r"\bcost\b", "成本"),
    (r"\bmix\b", "组合"),
    (r"\boperating cash flow\b", "经营现金流"),
    (r"\bfree cash flow\b", "自由现金流"),
    (r"\bcapital expenditures\b", "资本开支"),
    (r"\bcurrent ratio\b", "流动比率"),
    (r"\bcash and short-term investments\b", "现金及短期投资"),
    (r"\bcash and short term investments\b", "现金及短期投资"),
)


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
            final_report = _fallback_report_from_state(request, exc.state, reason=str(exc))
            if final_report is not None and _is_final_synthesis_failure(str(exc)):
                state = exc.state
            else:
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
    retrieval_records = _report_retrieval_records(request, state)
    return BoundedAgentResult(
        run_id=request.run_id,
        task_type=request.task_type,
        status=status,
        events=state.tool_events,
        degraded_reasons=state.degraded_reasons,
        retrieval_records=retrieval_records,
        retryable=final_report is None,
        final_report=_report_payload(final_report, retrieval_records)
        if final_report is not None
        else None,
    )


def _report_payload(
    final_report: EvidenceAwareReport,
    retrieval_records: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = final_report.model_dump(mode="json")
    payload["retrieval_records"] = retrieval_records
    return payload


def _report_retrieval_records(
    request: AgentRequest,
    state: AgentState,
) -> list[dict[str, Any]]:
    return state.retrieval_records


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
        _market_sentiment_source_refs(source_refs)
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
                ticker=request.ticker,
                summary=summary,
                metrics=present_metrics[:3],
                source_refs=source_refs,
                language=request.language,
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
        task_sections = _market_sentiment_fallback_sections(
            request=request,
            summary=summary,
            source_refs=source_refs,
            coverage=coverage,
        )
    elif request.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        task_sections = _cash_flow_fallback_sections(
            request=request,
            summary=summary,
            metrics=present_metrics,
            source_refs=source_refs,
            coverage=coverage,
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
    ticker: str,
    summary: str,
    metrics: list[EvidenceBoundMetric],
    source_refs: list[SourceRef],
    language: str | None = None,
) -> dict[str, Any]:
    is_zh = _is_zh_locale(language)
    fallback_source_ids = [source_ref.source_id for source_ref in source_refs[:3]]
    primary_source_ids = fallback_source_ids[:1]
    primary_metric = _primary_fallback_metric(metrics)
    risk_source = _risk_source_ref(source_refs, primary_source_ids)
    fallback_view = _latest_earnings_structured_fallback_view(
        metrics=metrics,
        source_refs=source_refs,
        summary=summary,
        ticker=ticker,
        is_zh=is_zh,
    )
    return {
        "company_profile": None,
        "topline_verdict": {
            "headline": fallback_view["headline"],
            "summary": fallback_view["summary"],
            "verdict": "mixed",
            "confidence": "low",
        },
        "key_takeaways": [
            _fallback_payload_point(
                title=fallback_view["takeaway_title"],
                summary=fallback_view["takeaway_summary"],
                source_ids=fallback_view["takeaway_source_ids"] or primary_source_ids,
                citation_status=_fallback_citation_status(source_refs),
            ),
            *(
                [
                    _fallback_payload_point(
                        title=fallback_view["profit_title"],
                        summary=fallback_view["profit_summary"],
                        source_ids=fallback_view["profit_source_ids"] or primary_source_ids,
                        citation_status=_fallback_citation_status(source_refs),
                    )
                ]
                if fallback_view["profit_summary"]
                else []
            ),
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
                title=_driver_fallback_title(primary_metric, is_zh),
                summary=_driver_fallback_summary(
                    primary_metric,
                    fallback_view["summary"],
                    is_zh,
                ),
                source_ids=_metric_source_ids(primary_metric) or primary_source_ids,
                citation_status=_fallback_citation_status(source_refs),
            )
        ],
        "risk_snapshot": [
            _fallback_payload_point(
                title=_risk_fallback_title(risk_source, is_zh),
                summary=_risk_fallback_summary(
                    risk_source,
                    is_zh,
                    context=fallback_view["summary"],
                ),
                source_ids=(
                    [risk_source.source_id] if risk_source is not None else primary_source_ids
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


def _latest_earnings_structured_fallback_view(
    *,
    ticker: str,
    metrics: list[EvidenceBoundMetric],
    source_refs: list[SourceRef],
    summary: str,
    is_zh: bool,
) -> dict[str, object]:
    metric_map = {
        _normalize_metric_lookup_key(metric.name): metric
        for metric in metrics
        if not _is_missing_metric(metric)
    }
    revenue = _first_metric(
        metric_map,
        ("revenue", "sales", "net sales"),
    )
    profit = _first_metric(
        metric_map,
        ("operating income", "operating profit", "gross margin", "gross profit", "net income"),
    )
    cash = _first_metric(
        metric_map,
        ("operating cash flow", "free cash flow"),
    )
    risk_source = _risk_source_ref(source_refs, _metric_source_ids(revenue))
    risk_text = _visible_source_snippet(risk_source, is_zh=is_zh)
    revenue_text = _visible_metric_sentence(revenue, is_zh=is_zh)
    profit_text = _visible_metric_sentence(profit, is_zh=is_zh)
    cash_text = _visible_metric_sentence(cash, is_zh=is_zh)
    metric_clauses = [text for text in (revenue_text, profit_text, cash_text) if text]
    fallback_summary = _zh_fallback_text(summary) if is_zh else summary

    if is_zh:
        headline_subject = ticker or "本季度"
        headline_metric = revenue_text or profit_text or cash_text or "已收集的关键指标"
        headline = f"{headline_subject} 收入、利润率与现金流需要同步验证"
        summary_parts = [
            f"{ticker or '该公司'} 本季分析以已验证指标为基础，{headline_metric}",
        ]
        if profit_text:
            summary_parts.append(f"{profit_text}，用于判断收入是否转化为利润质量")
        if cash_text:
            summary_parts.append(f"{cash_text}，用于交叉验证会计利润的现金支撑")
        if risk_text:
            summary_parts.append(f"主要风险观察来自披露片段：{risk_text}")
        summary_parts.append("因此这是一份保守但可执行的财报读数，下一季应继续验证收入、利润率和现金流是否同向改善。")
        report_summary = "；".join(summary_parts)
        takeaway_summary = (
            f"增长质量的核心锚点是{revenue_text or headline_metric}。"
            "如果后续季度收入继续扩张，同时利润率没有明显回落，当前财报判断会更有支撑；"
            "反之，收入增速放缓会削弱这份读数的安全边际。"
        )
        cash_quality_note = (
            f"同时，{cash_text}，这能帮助判断利润是否有现金流支撑。"
            if cash_text
            else "在缺少现金流锚点时，这一判断仍需保守处理。"
        )
        profit_summary = f"利润质量需要重点看{profit_text or headline_metric}。{cash_quality_note}"
        return {
            "headline": headline,
            "summary": report_summary,
            "takeaway_title": "增长质量",
            "takeaway_summary": takeaway_summary,
            "takeaway_source_ids": _metric_source_ids(revenue),
            "profit_title": "利润与现金转化",
            "profit_summary": profit_summary,
            "profit_source_ids": _metric_source_ids(profit) or _metric_source_ids(cash),
        }

    headline_subject = ticker or "The quarter"
    headline_metric = revenue_text or profit_text or cash_text or "the collected metrics"
    report_summary = (
        f"{headline_subject} should be read from verified financial anchors: "
        f"{', '.join(metric_clauses) if metric_clauses else fallback_summary}. "
        "The conservative conclusion is to judge growth, margin conversion, "
        "and cash support together "
        "rather than treating one metric as a standalone signal."
    )
    if risk_text:
        report_summary += f" The main risk context is: {risk_text}"
    takeaway_summary = (
        f"Growth quality is anchored by {revenue_text or headline_metric}. "
        "If revenue continues to expand without margin deterioration, "
        "the earnings read gains support; "
        "if growth slows, the view should stay cautious."
    )
    cash_quality_note = (
        f"Cash support is visible through {cash_text}."
        if cash_text
        else "Without a cash-flow anchor, this remains a partial view."
    )
    profit_summary = (
        f"Profit quality should be checked against {profit_text or headline_metric}. "
        f"{cash_quality_note}"
    )
    return {
        "headline": f"{headline_subject} needs revenue, profit, and cash-flow confirmation",
        "summary": report_summary,
        "takeaway_title": "Growth quality",
        "takeaway_summary": takeaway_summary,
        "takeaway_source_ids": _metric_source_ids(revenue),
        "profit_title": "Profit and cash conversion",
        "profit_summary": profit_summary,
        "profit_source_ids": _metric_source_ids(profit) or _metric_source_ids(cash),
    }


def _first_metric(
    metric_map: dict[str, EvidenceBoundMetric],
    names: tuple[str, ...],
) -> EvidenceBoundMetric | None:
    for name in names:
        metric = metric_map.get(_normalize_metric_lookup_key(name))
        if metric is not None:
            return metric
    return None


def _visible_metric_sentence(
    metric: EvidenceBoundMetric | None,
    *,
    is_zh: bool,
) -> str:
    if metric is None:
        return ""
    if is_zh:
        return f"{_zh_metric_name(metric.name)}为 {metric.value}"
    return f"{metric.name} was {metric.value}"


def _visible_source_snippet(
    source_ref: SourceRef | None,
    *,
    is_zh: bool,
) -> str:
    if source_ref is None:
        return ""
    text = _zh_fallback_text(source_ref.snippet) if is_zh else source_ref.snippet
    return _clip(text, 180)


def _driver_fallback_title(metric: EvidenceBoundMetric | None, is_zh: bool = False) -> str:
    if metric is None:
        return "财报驱动观察" if is_zh else "Earnings driver watch"
    if is_zh:
        return f"{_zh_metric_name(metric.name)}驱动观察"
    return f"{_title_case_metric(metric.name)} evidence anchor"


def _driver_fallback_summary(
    metric: EvidenceBoundMetric | None,
    summary: str,
    is_zh: bool = False,
) -> str:
    if metric is None:
        return summary
    if is_zh:
        return (
            f"{_zh_metric_name(metric.name)}为 {metric.value}，是本季财报最清晰的量化驱动之一。"
            f"{_zh_fallback_text(metric.interpretation)}"
        )
    return (
        f"{metric.name} of {metric.value} is one of the clearest available earnings "
        f"drivers in the collected evidence. {metric.interpretation}"
    )


def _market_sentiment_fallback_sections(
    *,
    request: AgentRequest,
    summary: str,
    source_refs: list[SourceRef],
    coverage: TaskSectionCoverage,
) -> BusinessDriverSections:
    is_zh = _is_zh_locale(request.language)
    sentiment_refs = _market_sentiment_source_refs(source_refs)
    source_summary = _market_sentiment_source_summary(sentiment_refs, is_zh=is_zh)
    narrative_summary = _market_sentiment_fallback_summary(
        request=request,
        summary=summary,
        source_summary=source_summary,
    )
    coverage = coverage.model_copy(
        update={
            "missing_sections": [
                *coverage.missing_sections,
                "llm_sentiment_synthesis",
            ],
            "evidence_count": len(sentiment_refs),
        }
    )
    return BusinessDriverSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        coverage=coverage,
        sentiment_header=SentimentHeader(
            overall_band="Mixed",
            overall_score=5.0,
            confidence="low",
            summary=narrative_summary,
        ),
        narrative_snapshot=EvidenceBoundPoint(
            title="市场叙事样本" if is_zh else "Market narrative sample",
            summary=narrative_summary,
            evidence_refs=[_evidence_ref(source_ref) for source_ref in sentiment_refs[:3]],
            citation_status=_fallback_citation_status(sentiment_refs),
        ),
        bull_bear_narrative=BullBearNarrative(
            bull_case=(
                "多头叙事需要等待情绪源和 LLM 合成恢复后再细分。"
                if is_zh
                else (
                    "The bullish narrative needs sentiment sources and LLM "
                    "synthesis to recover before it can be split out."
                )
            ),
            bear_case=(
                "空头叙事同样只能先按样本限制处理，不能编造社媒或新闻观点。"
                if is_zh
                else (
                    "The bearish narrative is constrained by the available sample; "
                    "the fallback must not invent social or news views."
                )
            ),
            balanced_read=(
                "本次只给出低置信度读数：来源样本已记录，但最终情绪合成失败。"
                if is_zh
                else (
                    "This is a low-confidence read: source collection is recorded, "
                    "but the final sentiment synthesis failed."
                )
            ),
        ),
        source_divergence=SourceDivergence(
            summary=source_summary,
            news_direction=_source_direction(sentiment_refs, "yahoo_news"),
            stocktwits_direction=_source_direction(sentiment_refs, "stocktwits"),
            reddit_direction=_source_direction(sentiment_refs, "reddit"),
        ),
        noise_warnings=[
            (
                "最终情绪合成失败；当前展示的是保守 fallback，不代表完整社媒结论。"
                if is_zh
                else (
                    "Final sentiment synthesis failed; this conservative fallback "
                    "is not a complete social sentiment read."
                )
            )
        ],
        driver_thesis=None,
        driver_map=None,
    )


def _market_sentiment_fallback_summary(
    *,
    request: AgentRequest,
    summary: str,
    source_summary: str,
) -> str:
    if _is_zh_locale(request.language):
        return (
            f"{request.ticker} 的市场叙事与情绪分析未完成最终 LLM 合成；"
            f"已收集来源状态：{source_summary}。"
            f"错误上下文：{_zh_fallback_text(summary)}"
        )
    return (
        f"{request.ticker} market narrative and sentiment did not complete final "
        f"LLM synthesis. Collected source status: {source_summary}. Context: {summary}"
    )


def _market_sentiment_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    return [
        source_ref
        for source_ref in source_refs
        if source_ref.source_id.lower().startswith("sentiment:")
        or source_ref.section.lower()
        in {
            "yahoo_news",
            "stocktwits",
            "reddit",
        }
    ]


def _market_sentiment_source_summary(
    source_refs: list[SourceRef],
    *,
    is_zh: bool,
) -> str:
    statuses = {
        "Yahoo Finance": _source_direction(source_refs, "yahoo_news"),
        "StockTwits": _source_direction(source_refs, "stocktwits"),
        "Reddit": _source_direction(source_refs, "reddit"),
    }
    separator = "；" if is_zh else "; "
    return separator.join(f"{source}={status}" for source, status in statuses.items())


def _source_direction(source_refs: list[SourceRef], source_name: str) -> str:
    matching_refs = [
        source_ref
        for source_ref in source_refs
        if source_name in source_ref.source_id.lower()
        or source_name in source_ref.section.lower()
    ]
    if not matching_refs:
        return "unavailable"
    if any(source_ref.citation_status == CitationStatus.SUPPORTED for source_ref in matching_refs):
        return "mixed"
    return "thin"



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


def _risk_fallback_title(source_ref: SourceRef | None, is_zh: bool = False) -> str:
    if source_ref is None:
        return "证据风险观察" if is_zh else "Evidence risk watch"
    if is_zh:
        return f"{_clip_title(source_ref.section)} 风险观察"
    return f"{_clip_title(source_ref.section)} risk watch"


def _risk_fallback_summary(
    source_ref: SourceRef | None,
    is_zh: bool = False,
    *,
    context: object = "",
) -> str:
    if source_ref is None:
        if is_zh:
            context_text = str(context or "").strip()
            fallback = "风险判断仍应保持保守，下一季需要继续验证收入、利润率和现金流是否同向改善。"
            return (
                f"{context_text} {fallback}"
                if context_text
                else fallback
            )
        return (
            "Risk framing should stay conservative until revenue, margin, and cash-flow "
            "signals confirm the same direction next quarter."
        )
    if is_zh:
        snippet = _visible_source_snippet(source_ref, is_zh=True)
        return (
            f"{snippet} 这条风险证据说明当前财报读数不能只看单一增长指标，"
            "还要继续验证需求、利润率和现金流是否同时改善。"
        )
    return (
        f"{_clip(source_ref.snippet, 180)} This keeps the earnings read balanced "
        "because investors still need confirmation across demand, margins, and cash flow."
    )


def _metric_source_ids(metric: EvidenceBoundMetric | None) -> list[str]:
    if metric is None:
        return []
    return [
        evidence_ref.source_id for evidence_ref in metric.evidence_refs if evidence_ref.source_id
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
    return metrics


def _cash_flow_fallback_sections(
    *,
    request: AgentRequest,
    summary: str,
    metrics: list[EvidenceBoundMetric],
    source_refs: list[SourceRef],
    coverage: TaskSectionCoverage,
) -> CashFlowCapitalAllocationSections:
    is_zh = _is_zh_locale(request.language)
    metric_map = {
        _normalize_metric_lookup_key(metric.name): metric
        for metric in metrics
        if not _is_missing_metric(metric)
    }
    cash_metrics = [
        metric
        for metric in [
            _lookup_metric(metric_map, "net income"),
            _lookup_metric(metric_map, "operating cash flow"),
            _lookup_metric(metric_map, "capital expenditures"),
            _lookup_metric(metric_map, "free cash flow"),
            _lookup_metric(metric_map, "current ratio"),
            _lookup_metric(metric_map, "total debt"),
            _lookup_metric(metric_map, "cash and short term investments"),
        ]
        if metric is not None
    ]
    visible_cash_metrics = (
        [_zh_metric_for_visible_report(metric) for metric in cash_metrics]
        if is_zh
        else cash_metrics
    )
    cash_quality = _cash_quality_verdict(request, metric_map, summary)
    capex_point = _cash_flow_metric_point(
        metric_map,
        "capital expenditures",
        title="资本开支与再投资" if is_zh else "Capex and reinvestment",
        fallback_summary=(
            "资本开支数据是主要再投资信号。"
            if is_zh
            else "Capital expenditure data was collected as the main reinvestment signal."
        ),
        zh=is_zh,
    )
    debt_point = _cash_flow_metric_point(
        metric_map,
        "total debt",
        title="债务负担" if is_zh else "Debt load",
        fallback_summary=(
            "债务数据是主要资产负债表风险信号。"
            if is_zh
            else "Debt data was collected as the main balance sheet risk signal."
        ),
        zh=is_zh,
    )
    liquidity_point = _cash_flow_liquidity_point(metric_map, source_refs, is_zh)
    red_flags = _cash_flow_red_flags(metric_map, source_refs, is_zh)
    outlook = _fallback_point(
        _cash_flow_outlook_summary(request, metric_map, summary),
        source_refs,
        title="最终现金流观察" if is_zh else "Final analyst outlook",
        zh=is_zh,
    )
    return CashFlowCapitalAllocationSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        coverage=coverage,
        cash_quality_verdict=cash_quality,
        cash_metrics=visible_cash_metrics[:7],
        capital_allocation=CapitalAllocation(
            capex=[capex_point] if capex_point is not None else [],
            buybacks=[],
            dividends=[],
            debt=[debt_point] if debt_point is not None else [],
            liquidity=[liquidity_point] if liquidity_point is not None else [],
        ),
        allocation_discipline=[outlook],
        red_flags=red_flags,
    )


def _normalize_metric_lookup_key(value: str) -> str:
    normalized = value.strip().lower().replace("_", " ")
    aliases = {
        "capex": "capital expenditures",
        "capital expenditure": "capital expenditures",
        "cash and equivalents": "cash and short term investments",
        "cash and cash equivalents": "cash and short term investments",
    }
    return aliases.get(normalized, normalized)


def _lookup_metric(
    metric_map: dict[str, EvidenceBoundMetric],
    name: str,
) -> EvidenceBoundMetric | None:
    return metric_map.get(_normalize_metric_lookup_key(name))


def _cash_quality_verdict(
    request: AgentRequest,
    metric_map: dict[str, EvidenceBoundMetric],
    fallback_summary: str,
) -> CashQualityVerdict:
    is_zh = _is_zh_locale(request.language)
    net_income = _metric_float(_lookup_metric(metric_map, "net income"))
    ocf = _metric_float(_lookup_metric(metric_map, "operating cash flow"))
    fcf = _metric_float(_lookup_metric(metric_map, "free cash flow"))
    capex = _metric_float(_lookup_metric(metric_map, "capital expenditures"))
    if ocf is not None and capex is not None and fcf is not None and fcf < 0 < ocf:
        return CashQualityVerdict(
            headline=(
                "现金质量受到资本开支压力。"
                if is_zh
                else "Cash quality is pressured by capex."
            ),
            earnings_backed_by_cash="mixed",
            summary=(
                (
                    f"{request.ticker} 经营现金流为正，"
                    "但资本开支吸收了这部分现金并导致自由现金流为负。"
                    "因此现金质量取决于再投资能否转化为可持续的经营现金流修复。"
                )
                if is_zh
                else (
                    f"{request.ticker} generated positive operating cash flow, but capex "
                    "absorbed that cash and left free cash flow negative. The cash story "
                    "therefore depends on whether reinvestment starts converting into durable "
                    "operating cash recovery."
                )
            ),
        )
    if ocf is not None and net_income is not None and ocf > 0 and net_income <= 0:
        return CashQualityVerdict(
            headline=(
                "现金流强于报告利润。"
                if is_zh
                else "Cash flow is stronger than reported earnings."
            ),
            earnings_backed_by_cash="mixed",
            summary=(
                (
                    f"{request.ticker} 报告利润偏弱，但经营现金流仍为正。"
                    "这支撑了流动性，不过自由现金流和资本开支仍决定现金画像是否真正改善。"
                )
                if is_zh
                else (
                    f"{request.ticker} reported weak earnings, but operating cash flow stayed "
                    "positive. That supports liquidity, while free cash flow and capex still "
                    "decide whether the cash profile is improving."
                )
            ),
        )
    if ocf is not None and fcf is not None and ocf > 0 and fcf > 0:
        if is_zh:
            capex_clause = (
                f"同时资本开支为 {_format_metric_value(capex)}，"
                if capex is not None
                else "同时仍要核对资本开支节奏，"
            )
            return CashQualityVerdict(
                headline="现金流验证盈利，但再投资后弹性仍是关键。",
                earnings_backed_by_cash="yes",
                summary=(
                    f"{request.ticker} 经营现金流为 {_format_metric_value(ocf)}，"
                    f"自由现金流为 {_format_metric_value(fcf)}，说明本期利润至少有现金生成支撑。"
                    f"{capex_clause}投资判断不能只看现金流为正，还要看经营现金流能否持续覆盖再投资，"
                    "并在下一季继续转化为稳定的自由现金流。"
                ),
            )
        return CashQualityVerdict(
            headline="Earnings are supported by cash generation.",
            earnings_backed_by_cash="yes",
            summary=(
                f"{request.ticker} produced positive operating cash flow and free cash "
                "flow, giving management real capital allocation capacity."
            ),
        )
    return CashQualityVerdict(
        headline="现金质量仍需要更多证据。" if is_zh else "Cash quality needs more evidence.",
        earnings_backed_by_cash="unclear",
        summary=fallback_summary,
    )


def _cash_flow_metric_point(
    metric_map: dict[str, EvidenceBoundMetric],
    metric_name: str,
    *,
    title: str,
    fallback_summary: str,
    zh: bool = False,
) -> EvidenceBoundPoint | None:
    metric = _lookup_metric(metric_map, metric_name)
    if metric is None:
        return None
    return EvidenceBoundPoint(
        title=title,
        summary=(
            f"{_zh_metric_name(metric.name)}为 {metric.value}。"
            f"{_zh_fallback_text(metric.interpretation or fallback_summary)}"
            if zh
            else f"{metric.name} was {metric.value}. {metric.interpretation or fallback_summary}"
        ),
        evidence_refs=(
            [_zh_evidence_ref(evidence_ref) for evidence_ref in metric.evidence_refs]
            if zh
            else metric.evidence_refs
        ),
        citation_status=metric.citation_status,
    )


def _cash_flow_liquidity_point(
    metric_map: dict[str, EvidenceBoundMetric],
    source_refs: list[SourceRef],
    zh: bool = False,
) -> EvidenceBoundPoint | None:
    current_ratio = _lookup_metric(metric_map, "current ratio")
    cash = _lookup_metric(metric_map, "cash and short term investments")
    liquidity_refs = _cash_flow_source_refs_matching_terms(
        source_refs,
        ("liquidity", "cash", "working capital", "current ratio"),
    )
    if current_ratio is None and cash is None and not liquidity_refs:
        return None
    parts = []
    evidence_refs: list[EvidenceRef] = []
    citation_status = CitationStatus.UNVERIFIED
    if current_ratio is not None:
        parts.append(
            f"流动比率为 {current_ratio.value}"
            if zh
            else f"current ratio was {current_ratio.value}"
        )
        evidence_refs.extend(
            [_zh_evidence_ref(evidence_ref) for evidence_ref in current_ratio.evidence_refs]
            if zh
            else current_ratio.evidence_refs
        )
        citation_status = current_ratio.citation_status
    if cash is not None:
        parts.append(
            f"现金及短期投资为 {cash.value}"
            if zh
            else f"cash and short-term investments were {cash.value}"
        )
        evidence_refs.extend(
            [_zh_evidence_ref(evidence_ref) for evidence_ref in cash.evidence_refs]
            if zh
            else cash.evidence_refs
        )
        citation_status = cash.citation_status
    if not parts and liquidity_refs:
        snippet = (
            _zh_fallback_text(liquidity_refs[0].snippet)
            if zh
            else liquidity_refs[0].snippet
        )
        parts.append(_clip(snippet, 160))
        citation_status = liquidity_refs[0].citation_status
    return EvidenceBoundPoint(
        title="资产负债表韧性" if zh else "Balance sheet resilience",
        summary=(
            (
                "流动性背景："
                + "和".join(parts)
                + "。这决定管理层有多少时间把投资转化为现金回报。"
            )
            if zh
            else (
                "Liquidity context: "
                + " and ".join(parts)
                + ". This determines how much time management has to convert "
                "investment into cash returns."
            )
        ),
        evidence_refs=evidence_refs
        or [
            _zh_evidence_ref(_evidence_ref(source_ref)) if zh else _evidence_ref(source_ref)
            for source_ref in liquidity_refs[:2]
        ],
        citation_status=citation_status,
    )


def _cash_flow_source_refs_matching_terms(
    source_refs: list[SourceRef],
    terms: tuple[str, ...],
) -> list[SourceRef]:
    matches: list[SourceRef] = []
    for source_ref in source_refs:
        searchable = f"{source_ref.section} {source_ref.snippet}".lower()
        if any(term in searchable for term in terms):
            matches.append(source_ref)
    return matches


def _cash_flow_red_flags(
    metric_map: dict[str, EvidenceBoundMetric],
    source_refs: list[SourceRef],
    zh: bool = False,
) -> list[EvidenceBoundPoint]:
    flags: list[EvidenceBoundPoint] = []
    ocf = _metric_float(_lookup_metric(metric_map, "operating cash flow"))
    fcf = _metric_float(_lookup_metric(metric_map, "free cash flow"))
    capex = _metric_float(_lookup_metric(metric_map, "capital expenditures"))
    if fcf is not None and fcf < 0:
        flags.append(
            _fallback_point(
                (
                    "自由现金流为负，下一季需要观察经营现金流能否提升到资本开支之上。"
                    if zh
                    else (
                        "Free cash flow is negative, so the next quarter should show whether "
                        "operating cash flow can rise above capex."
                    )
                ),
                source_refs,
                title="自由现金流为负" if zh else "Negative free cash flow",
                zh=zh,
            )
        )
    if ocf is not None and capex is not None and capex > ocf > 0:
        flags.append(
            _fallback_point(
                (
                    "资本开支高于经营现金流，使再投资短期内难以转化为自由现金流。"
                    if zh
                    else (
                        "Capex is larger than operating cash flow, which keeps reinvestment "
                        "from translating into near-term free cash flow."
                    )
                ),
                source_refs,
                title="资本开支高于经营现金流" if zh else "Capex exceeds operating cash flow",
                zh=zh,
            )
        )
    return flags or [
        _fallback_point(
            (
                "观察下一季经营现金流、资本开支和流动性是否朝同一方向变化。"
                if zh
                else (
                    "Watch whether operating cash flow, capex, and liquidity move in the same "
                    "direction next quarter."
                )
            ),
            source_refs,
            title="观察下一季" if zh else "Watch next",
            zh=zh,
        )
    ]


def _cash_flow_outlook_summary(
    request: AgentRequest,
    metric_map: dict[str, EvidenceBoundMetric],
    fallback_summary: str,
) -> str:
    ocf = _lookup_metric(metric_map, "operating cash flow")
    fcf = _lookup_metric(metric_map, "free cash flow")
    capex = _lookup_metric(metric_map, "capital expenditures")
    if ocf is None and fcf is None and capex is None:
        return (
            _zh_fallback_text(fallback_summary)
            if _is_zh_locale(request.language)
            else fallback_summary
        )
    if _is_zh_locale(request.language):
        pieces = [
            f"{_zh_metric_name(metric.name)}为 {metric.value}"
            for metric in [ocf, capex, fcf]
            if metric is not None
        ]
        return (
            f"{request.ticker} 的现金质量应围绕"
            + "、".join(pieces)
            + "判断。投资判断只有在经营现金流能够覆盖再投资、并维持自由现金流改善时才更可信。"
        )
    pieces = [
        f"{metric.name} at {metric.value}" for metric in [ocf, capex, fcf] if metric is not None
    ]
    return (
        f"{request.ticker} should be read as a cash conversion story: "
        + ", ".join(pieces)
        + ". The investment case improves only if operating cash flow can cover reinvestment "
        "and sustain positive free cash flow."
    )


def _metric_float(metric: EvidenceBoundMetric | None) -> float | None:
    if metric is None:
        return None
    raw = metric.value.strip().replace("$", "").replace(",", "")
    multiplier = 1.0
    if raw.endswith("B"):
        multiplier = 1_000_000_000.0
        raw = raw[:-1]
    elif raw.endswith("M"):
        multiplier = 1_000_000.0
        raw = raw[:-1]
    elif raw.endswith("%") or raw.endswith("x"):
        raw = raw[:-1]
    try:
        return float(raw) * multiplier
    except ValueError:
        return None


def _format_metric_value(value: float) -> str:
    abs_value = abs(value)
    if abs_value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if abs_value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value:g}"


def _fallback_summary(
    request: AgentRequest,
    reason: str,
    metrics: list[EvidenceBoundMetric],
    source_refs: list[SourceRef],
) -> str:
    is_zh = _is_zh_locale(request.language)
    metric_text = ", ".join(
        (_zh_display_metric(metric) if is_zh else _display_metric(metric))
        for metric in _present_metrics(metrics)[:3]
    )
    missing_metrics = _missing_metric_names(metrics)
    missing_text = _missing_metric_boundary_text(
        missing_metrics,
        zh=is_zh,
    )
    evidence_text = (
        _clip(_zh_fallback_text(source_refs[0].snippet), 180)
        if is_zh and source_refs
        else _clip(source_refs[0].snippet, 180)
        if source_refs
        else "evidence was collected"
    )
    base = metric_text or evidence_text
    if is_zh:
        boundary = f"；{missing_text}" if missing_text else ""
        return (
            f"{request.ticker} 的证据收集已完成，"
            "当前报告先以已验证的 SEC 指标和披露片段形成保守结论："
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
    zh = _is_zh_locale(request.language)
    visible_source_refs = (
        [_zh_source_ref(source_ref) for source_ref in source_refs]
        if zh
        else source_refs
    )
    claims = [
        EvidenceBoundClaim(
            claim_id=f"{request.run_id}:fallback_claim:1",
            text=summary,
            citation_status=visible_source_refs[0].citation_status,
            source_refs=visible_source_refs[:3],
        )
    ]
    for index, source_ref in enumerate(visible_source_refs[1:3], start=2):
        claims.append(
            EvidenceBoundClaim(
                claim_id=f"{request.run_id}:fallback_claim:{index}",
                text=_clip(
                    _zh_fallback_text(source_ref.snippet) if zh else source_ref.snippet,
                    220,
                ),
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
    zh: bool = False,
) -> EvidenceBoundPoint:
    return EvidenceBoundPoint(
        title=title,
        summary=summary,
        evidence_refs=[
            _zh_evidence_ref(_evidence_ref(source_ref)) if zh else _evidence_ref(source_ref)
            for source_ref in source_refs[:1]
        ],
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


def _zh_source_ref(source_ref: SourceRef) -> SourceRef:
    return source_ref.model_copy(
        update={
            "snippet": _zh_fallback_text(source_ref.snippet),
        }
    )


def _zh_evidence_ref(evidence_ref: EvidenceRef) -> EvidenceRef:
    return evidence_ref.model_copy(
        update={
            "excerpt": _zh_fallback_text(evidence_ref.excerpt),
        }
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
    return "Metric was collected from available structured financial evidence."


def _metric_value(value: object, unit: object) -> str:
    if value is None:
        return "Not extracted"
    formatted = _format_fallback_metric_value(value, unit)
    if str(unit or "").strip() == "USD" and not formatted.startswith("$"):
        return f"${formatted}"
    return formatted


def _display_metric(metric: EvidenceBoundMetric) -> str:
    return f"{metric.name}: {metric.value}"


def _zh_display_metric(metric: EvidenceBoundMetric) -> str:
    return f"{_zh_metric_name(metric.name)}：{metric.value}"


def _zh_metric_name(metric_name: str) -> str:
    normalized = normalize_metric_name(metric_name)
    return _ZH_METRIC_LABELS.get(normalized, metric_name)


def _zh_metric_for_visible_report(metric: EvidenceBoundMetric) -> EvidenceBoundMetric:
    return metric.model_copy(
        update={
            "name": _zh_metric_name(metric.name),
            "interpretation": _zh_fallback_text(metric.interpretation),
            "evidence_refs": [_zh_evidence_ref(ref) for ref in metric.evidence_refs],
        }
    )


def _zh_fallback_text(value: str) -> str:
    text = " ".join(str(value or "").split()).strip()
    if not text:
        return text
    text = summarize_english_business_snippet_for_zh(text)
    text = _rewrite_profile_snippet_for_zh(text)
    text = _rewrite_structured_metric_snippet_for_zh(text)
    text = localize_market_classifications_in_text(text)
    for pattern, replacement in _ZH_FALLBACK_TEXT_REPLACEMENTS:
        text = re.sub(pattern, replacement, text, flags=re.I)
    text = re.sub(r"\bnet income\b", "净利润", text, flags=re.I)
    text = re.sub(r"\bgross margin\b", "毛利率", text, flags=re.I)
    text = re.sub(r"\brevenue\b", "收入", text, flags=re.I)
    text = re.sub(r"\bfiling\b", "披露文件", text, flags=re.I)
    text = re.sub(r"\blatest quarter\b", "最近季度", text, flags=re.I)
    text = re.sub(r"\bwas\b", "为", text, flags=re.I)
    text = re.sub(r"\bwere\b", "为", text, flags=re.I)
    text = re.sub(r"\s+([，。；：,.!?;:])", r"\1", text)
    return text.strip()


def _rewrite_profile_snippet_for_zh(text: str) -> str:
    if "business_summary=" not in text and "company_name=" not in text:
        return text
    company = _profile_field(text, "company_name") or "公司"
    sector = _profile_field(text, "sector")
    industry = _profile_field(text, "industry")
    parts = [f"{company} 的业务画像已收集"]
    if sector or industry:
        parts.append(
            "行业暴露集中在"
            + localize_market_classification(sector, industry)
        )
    return "，".join(parts) + "。"


def _profile_field(text: str, field: str) -> str:
    match = re.search(
        rf"{re.escape(field)}=([^,。;；]+)",
        text,
        flags=re.I,
    )
    return match.group(1).strip() if match else ""


def _rewrite_structured_metric_snippet_for_zh(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        metric = _zh_metric_name(match.group("metric"))
        value = _format_fallback_metric_value(float(match.group("value")), match.group("unit"))
        if match.group("unit").upper() == "USD" and not value.startswith("$"):
            value = f"${value}"
        period = match.group("period").replace("_", " ").strip()
        return f"{period} {metric}为 {value}。"

    return re.sub(
        r"Structured\s+yfinance\s+facts\s+reports\s+"
        r"(?P<metric>[A-Za-z ]+?)\s+of\s+"
        r"(?P<value>-?\d+(?:\.\d+)?)\s+(?P<unit>USD|pure|percent|percentage|x|ratio)"
        r"\s+for\s+(?P<period>[^.。]+?)(?:\s+filed\s+[^.。]+)?(?:\.|。|$)",
        replace,
        text,
        flags=re.I,
    )


def _present_metrics(metrics: list[EvidenceBoundMetric]) -> list[EvidenceBoundMetric]:
    return [metric for metric in metrics if not _is_missing_metric(metric)]


def _missing_metric_names(metrics: list[EvidenceBoundMetric]) -> list[str]:
    return [metric.name for metric in metrics if _is_missing_metric(metric)]


def _is_missing_metric(metric: EvidenceBoundMetric) -> bool:
    return metric.value.strip().lower() in {"not extracted", "n/a", "na", "none", ""}


def _missing_metric_boundary_text(metric_names: list[str], *, zh: bool) -> str:
    if not metric_names:
        return ""
    visible_names = ", ".join(
        _zh_metric_name(metric_name) if zh else metric_name
        for metric_name in metric_names[:3]
    )
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
