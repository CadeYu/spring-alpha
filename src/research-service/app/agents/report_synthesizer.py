from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.llm_gateway import LlmClient, LlmRequest
from app.contracts.agent import AgentRequest, AgentState
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


class ReportSynthesisError(RuntimeError):
    pass


class _SynthesizedPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    citation_status: CitationStatus = CitationStatus.UNVERIFIED


class _SynthesizedMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    value: str = Field(min_length=1)
    period: str | None = None
    interpretation: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    citation_status: CitationStatus = CitationStatus.UNVERIFIED

    @field_validator("value", mode="before")
    @classmethod
    def normalize_value(cls, value: object) -> str:
        return str(value)


class _SynthesizedDashboard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[_SynthesizedMetric] = Field(default_factory=list)
    chart_focus: list[str] = Field(default_factory=list)


class _SynthesizedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    citation_status: CitationStatus = CitationStatus.UNVERIFIED


class _LatestEarningsSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topline_verdict: ToplineVerdict
    key_takeaways: list[_SynthesizedPoint] = Field(default_factory=list)
    financial_dashboard: _SynthesizedDashboard
    driver_snapshot: list[_SynthesizedPoint] = Field(default_factory=list)
    risk_snapshot: list[_SynthesizedPoint] = Field(default_factory=list)
    claims: list[_SynthesizedClaim] = Field(default_factory=list)


class _SynthesizedDriverMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: list[_SynthesizedPoint] = Field(default_factory=list)
    segment: list[_SynthesizedPoint] = Field(default_factory=list)
    geography: list[_SynthesizedPoint] = Field(default_factory=list)
    demand: list[_SynthesizedPoint] = Field(default_factory=list)
    pricing: list[_SynthesizedPoint] = Field(default_factory=list)
    customer: list[_SynthesizedPoint] = Field(default_factory=list)
    strategy: list[_SynthesizedPoint] = Field(default_factory=list)


class _BusinessDriverSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver_thesis: DriverThesis
    driver_map: _SynthesizedDriverMap
    positive_signals: list[_SynthesizedPoint] = Field(default_factory=list)
    negative_signals: list[_SynthesizedPoint] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)
    claims: list[_SynthesizedClaim] = Field(default_factory=list)


class _SynthesizedCapitalAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capex: list[_SynthesizedPoint] = Field(default_factory=list)
    buybacks: list[_SynthesizedPoint] = Field(default_factory=list)
    dividends: list[_SynthesizedPoint] = Field(default_factory=list)
    debt: list[_SynthesizedPoint] = Field(default_factory=list)
    liquidity: list[_SynthesizedPoint] = Field(default_factory=list)


class _CashFlowSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cash_quality_verdict: CashQualityVerdict
    cash_metrics: list[_SynthesizedMetric] = Field(default_factory=list)
    capital_allocation: _SynthesizedCapitalAllocation
    allocation_discipline: list[_SynthesizedPoint] = Field(default_factory=list)
    red_flags: list[_SynthesizedPoint] = Field(default_factory=list)
    claims: list[_SynthesizedClaim] = Field(default_factory=list)


def synthesize_latest_earnings_report(
    request: AgentRequest,
    state: AgentState,
    client: LlmClient,
) -> EvidenceAwareReport:
    if request.task_type != ResearchTaskType.LATEST_EARNINGS_READOUT:
        raise ReportSynthesisError(f"Unsupported synthesis task: {request.task_type.value}")

    source_refs = _source_refs_from_state(state)
    source_refs_by_id = _alias_source_refs_by_id(source_refs)
    response = _complete_synthesis_json(
        client,
        LlmRequest(
            run_id=request.run_id,
            provider=client.provider,
            model=request.llm_model,
            task_type=request.task_type,
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(request, state, source_refs),
            state=state,
            timeout_seconds=120,
        ),
    )
    payload = _LatestEarningsSynthesis.model_validate(response.content)
    _validate_source_ids(payload, source_refs_by_id)
    coverage = _coverage(payload, source_refs)
    task_sections = LatestEarningsSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        coverage=coverage,
        topline_verdict=payload.topline_verdict,
        key_takeaways=[
            _point_from_payload(point, source_refs_by_id) for point in payload.key_takeaways
        ],
        financial_dashboard=LatestFinancialDashboard(
            metrics=[
                _metric_from_payload(metric, source_refs_by_id)
                for metric in payload.financial_dashboard.metrics
            ],
            chart_focus=payload.financial_dashboard.chart_focus,
        ),
        driver_snapshot=[
            _point_from_payload(point, source_refs_by_id) for point in payload.driver_snapshot
        ],
        risk_snapshot=[
            _point_from_payload(point, source_refs_by_id) for point in payload.risk_snapshot
        ],
    )
    claims = [
        EvidenceBoundClaim(
            claim_id=f"{request.run_id}:synthesized_claim:{index + 1}",
            text=claim.text,
            citation_status=claim.citation_status,
            source_refs=[source_refs_by_id[source_id] for source_id in claim.source_ids],
        )
        for index, claim in enumerate(payload.claims)
    ]
    if not claims and source_refs:
        claims = [
            EvidenceBoundClaim(
                claim_id=f"{request.run_id}:synthesized_claim:1",
                text=payload.topline_verdict.summary,
                citation_status=source_refs[0].citation_status,
                source_refs=source_refs[:1],
            )
        ]
    return EvidenceAwareReport(
        run_id=request.run_id,
        ticker=state.ticker,
        task_type=request.task_type,
        task_sections=task_sections,
        sections={"summary": payload.topline_verdict.summary, "synthesis": "llm"},
        claims=claims,
        retrieval_records=state.retrieval_records,
    )


def synthesize_business_driver_report(
    request: AgentRequest,
    state: AgentState,
    client: LlmClient,
) -> EvidenceAwareReport:
    if request.task_type != ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        raise ReportSynthesisError(f"Unsupported synthesis task: {request.task_type.value}")

    source_refs = _source_refs_from_state(state)
    source_refs_by_id = _alias_source_refs_by_id(source_refs)
    response = _complete_synthesis_json(
        client,
        LlmRequest(
            run_id=request.run_id,
            provider=client.provider,
            model=request.llm_model,
            task_type=request.task_type,
            system_prompt=_system_prompt(),
            user_prompt=_business_driver_prompt(request, state, source_refs),
            state=state,
            timeout_seconds=120,
        ),
    )
    payload = _BusinessDriverSynthesis.model_validate(response.content)
    _validate_business_driver_source_ids(payload, source_refs_by_id)
    task_sections = BusinessDriverSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        coverage=_business_driver_coverage(payload, source_refs),
        driver_thesis=payload.driver_thesis,
        driver_map=DriverMap(
            product=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.driver_map.product
            ],
            segment=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.driver_map.segment
            ],
            geography=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.driver_map.geography
            ],
            demand=[
                _point_from_payload(point, source_refs_by_id) for point in payload.driver_map.demand
            ],
            pricing=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.driver_map.pricing
            ],
            customer=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.driver_map.customer
            ],
            strategy=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.driver_map.strategy
            ],
        ),
        positive_signals=[
            _point_from_payload(point, source_refs_by_id) for point in payload.positive_signals
        ],
        negative_signals=[
            _point_from_payload(point, source_refs_by_id) for point in payload.negative_signals
        ],
        watchlist=payload.watchlist,
    )
    return EvidenceAwareReport(
        run_id=request.run_id,
        ticker=state.ticker,
        task_type=request.task_type,
        task_sections=task_sections,
        sections={"summary": payload.driver_thesis.summary, "synthesis": "llm"},
        claims=_claims_from_payload(request, payload.claims, source_refs, source_refs_by_id),
        retrieval_records=state.retrieval_records,
    )


def synthesize_cash_flow_report(
    request: AgentRequest,
    state: AgentState,
    client: LlmClient,
) -> EvidenceAwareReport:
    if request.task_type != ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        raise ReportSynthesisError(f"Unsupported synthesis task: {request.task_type.value}")

    source_refs = _source_refs_from_state(state)
    source_refs_by_id = _alias_source_refs_by_id(source_refs)
    response = _complete_synthesis_json(
        client,
        LlmRequest(
            run_id=request.run_id,
            provider=client.provider,
            model=request.llm_model,
            task_type=request.task_type,
            system_prompt=_system_prompt(),
            user_prompt=_cash_flow_prompt(request, state, source_refs),
            state=state,
            timeout_seconds=120,
        ),
    )
    payload = _CashFlowSynthesis.model_validate(response.content)
    _validate_cash_flow_source_ids(payload, source_refs_by_id)
    task_sections = CashFlowCapitalAllocationSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        coverage=_cash_flow_coverage(payload, source_refs),
        cash_quality_verdict=payload.cash_quality_verdict,
        cash_metrics=[
            _metric_from_payload(metric, source_refs_by_id) for metric in payload.cash_metrics
        ],
        capital_allocation=CapitalAllocation(
            capex=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.capital_allocation.capex
            ],
            buybacks=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.capital_allocation.buybacks
            ],
            dividends=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.capital_allocation.dividends
            ],
            debt=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.capital_allocation.debt
            ],
            liquidity=[
                _point_from_payload(point, source_refs_by_id)
                for point in payload.capital_allocation.liquidity
            ],
        ),
        allocation_discipline=[
            _point_from_payload(point, source_refs_by_id) for point in payload.allocation_discipline
        ],
        red_flags=[_point_from_payload(point, source_refs_by_id) for point in payload.red_flags],
    )
    return EvidenceAwareReport(
        run_id=request.run_id,
        ticker=state.ticker,
        task_type=request.task_type,
        task_sections=task_sections,
        sections={"summary": payload.cash_quality_verdict.summary, "synthesis": "llm"},
        claims=_claims_from_payload(request, payload.claims, source_refs, source_refs_by_id),
        retrieval_records=state.retrieval_records,
    )


def _system_prompt() -> str:
    return (
        "You are a financial research report synthesizer. Return one JSON object only. "
        "Use only the provided evidence. Do not include chain-of-thought. "
        "Every field must match the requested JSON schema exactly."
    )


def _complete_synthesis_json(client: LlmClient, request: LlmRequest):
    last_error: Exception | None = None
    for _ in range(2):
        try:
            return client.complete_json(request)
        except Exception as exc:
            last_error = exc
    raise ReportSynthesisError(f"LLM synthesis JSON failed after retry: {last_error}")


def _business_driver_prompt(
    request: AgentRequest,
    state: AgentState,
    source_refs: list[SourceRef],
) -> str:
    evidence_refs = _aliased_source_refs(source_refs)
    evidence_lines = _evidence_lines(evidence_refs, source_refs)
    allowed_source_ids = [source_ref.source_id for source_ref in evidence_refs]
    return (
        "Generate typed business driver deep dive task sections.\n"
        "Return JSON only. Do not use strings where objects or arrays are required.\n"
        f"Allowed source_ids: {_json_safe(allowed_source_ids)}.\n"
        "Never invent source_ids. Do not cite facts, concepts, or node ids not listed above.\n"
        "Use exactly this shape:\n"
        "{\n"
        '  "driver_thesis": {"headline": "...", "durability": '
        '"durable|mixed|temporary|unclear", "summary": "..."},\n'
        '  "driver_map": {"product": [], "segment": [], "geography": [], '
        '"demand": [], "pricing": [], "customer": [], "strategy": []},\n'
        '  "positive_signals": [{"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}],\n'
        '  "negative_signals": [{"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}],\n'
        '  "watchlist": ["..."],\n'
        '  "claims": [{"text": "...", "source_ids": ["..."], '
        '"citation_status": "supported|partial|missing|unverified"}]\n'
        "}\n"
        "Each driver_map category value must be an array of points with title, summary, "
        "source_ids, and citation_status.\n"
        "Every source_ids value must come from provided evidence only.\n"
        "If evidence is thin, still return the same object/array shape with cautious text.\n"
        f"Ticker: {state.ticker}\n"
        f"Task: {request.task_type.value}\n"
        f"Business signals: {_json_safe(state.evidence_memory.business_signals)}\n"
        f"Coverage: status={state.coverage.status}; "
        f"evidence_count={state.coverage.evidence_count}; "
        f"citation_coverage={state.coverage.citation_coverage}\n"
        "Evidence:\n" + "\n".join(evidence_lines)
    )


def _cash_flow_prompt(
    request: AgentRequest,
    state: AgentState,
    source_refs: list[SourceRef],
) -> str:
    evidence_refs = _aliased_source_refs(source_refs)
    evidence_lines = _evidence_lines(evidence_refs, source_refs)
    allowed_source_ids = [source_ref.source_id for source_ref in evidence_refs]
    return (
        "Generate typed cash flow and capital allocation task sections.\n"
        "Return JSON only. Do not use strings where objects or arrays are required.\n"
        f"Allowed source_ids: {_json_safe(allowed_source_ids)}.\n"
        "Never invent source_ids. Do not cite facts, concepts, or node ids not listed above.\n"
        "Use exactly this shape:\n"
        "{\n"
        '  "cash_quality_verdict": {"headline": "...", '
        '"earnings_backed_by_cash": "yes|mixed|no|unclear", "summary": "..."},\n'
        '  "cash_metrics": [{"name": "...", "value": "...", '
        '"period": "latest_quarter", "interpretation": "...", "source_ids": ["..."], '
        '"citation_status": "supported|partial|missing|unverified"}],\n'
        '  "capital_allocation": {"capex": [], "buybacks": [], "dividends": [], '
        '"debt": [], "liquidity": []},\n'
        '  "allocation_discipline": [{"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}],\n'
        '  "red_flags": [{"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}],\n'
        '  "claims": [{"text": "...", "source_ids": ["..."], '
        '"citation_status": "supported|partial|missing|unverified"}]\n'
        "}\n"
        "Each capital_allocation category value must be an array of points with title, "
        "summary, source_ids, and citation_status.\n"
        "Every source_ids value must come from provided evidence only.\n"
        "If evidence is thin, still return the same object/array shape with cautious text.\n"
        f"Ticker: {state.ticker}\n"
        f"Task: {request.task_type.value}\n"
        f"Facts: {_json_safe(state.evidence_memory.facts)}\n"
        f"Metric evidence: {_json_safe(state.evidence_memory.metric_evidence)}\n"
        f"Coverage: status={state.coverage.status}; "
        f"evidence_count={state.coverage.evidence_count}; "
        f"citation_coverage={state.coverage.citation_coverage}\n"
        "Evidence:\n" + "\n".join(evidence_lines)
    )


def _user_prompt(
    request: AgentRequest,
    state: AgentState,
    source_refs: list[SourceRef],
) -> str:
    evidence_refs = _aliased_source_refs(source_refs)
    evidence_lines = _evidence_lines(evidence_refs, source_refs)
    allowed_source_ids = [source_ref.source_id for source_ref in evidence_refs]
    facts = state.evidence_memory.facts
    return (
        "Generate typed latest earnings task sections.\n"
        "Return JSON only. Do not use strings where objects or arrays are required.\n"
        f"Allowed source_ids: {_json_safe(allowed_source_ids)}.\n"
        "Never invent source_ids. Do not cite facts, concepts, or node ids not listed above.\n"
        "Use exactly this shape:\n"
        "{\n"
        '  "topline_verdict": {"headline": "...", "summary": "...", '
        '"verdict": "positive|mixed|negative"},\n'
        '  "key_takeaways": [{"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}],\n'
        '  "financial_dashboard": {"metrics": [{"name": "...", "value": "...", '
        '"period": "latest_quarter", "interpretation": "...", "source_ids": ["..."], '
        '"citation_status": "supported|partial|missing|unverified"}], '
        '"chart_focus": ["revenue"]},\n'
        '  "driver_snapshot": [{"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}],\n'
        '  "risk_snapshot": [{"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}],\n'
        '  "claims": [{"text": "...", "source_ids": ["..."], '
        '"citation_status": "supported|partial|missing|unverified"}]\n'
        "}\n"
        "Each point, metric, and claim must use source_ids from the provided evidence only.\n"
        "If evidence is thin, still return the same object/array shape with cautious text.\n"
        "Use cautious language when evidence is thin.\n"
        f"Ticker: {state.ticker}\n"
        f"Task: {request.task_type.value}\n"
        f"Facts: {_json_safe(facts)}\n"
        f"Coverage: status={state.coverage.status}; "
        f"evidence_count={state.coverage.evidence_count}; "
        f"citation_coverage={state.coverage.citation_coverage}\n"
        "Evidence:\n" + "\n".join(evidence_lines)
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
                    filing_type=_optional_str(ref.get("filing_type")),
                    filing_date=_optional_str(ref.get("filing_date")),
                    accession_number=_optional_str(ref.get("accession_number")),
                )
            )
        except ValueError:
            continue
    return refs


def _alias_source_refs_by_id(source_refs: list[SourceRef]) -> dict[str, SourceRef]:
    refs_by_id: dict[str, SourceRef] = {}
    for index, source_ref in enumerate(source_refs, start=1):
        refs_by_id[f"src_{index}"] = source_ref
        refs_by_id[source_ref.source_id] = source_ref
    return refs_by_id


def _aliased_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    return [
        source_ref.model_copy(update={"source_id": f"src_{index}"})
        for index, source_ref in enumerate(source_refs, start=1)
    ]


def _validate_source_ids(
    payload: _LatestEarningsSynthesis,
    source_refs_by_id: dict[str, SourceRef],
) -> None:
    source_id_groups: list[list[str]] = [
        *[point.source_ids for point in payload.key_takeaways],
        *[point.source_ids for point in payload.driver_snapshot],
        *[point.source_ids for point in payload.risk_snapshot],
        *[metric.source_ids for metric in payload.financial_dashboard.metrics],
        *[claim.source_ids for claim in payload.claims],
    ]
    for source_ids in source_id_groups:
        for source_id in source_ids:
            if source_id not in source_refs_by_id:
                raise ReportSynthesisError(f"Unknown source_id in synthesized report: {source_id}")


def _validate_business_driver_source_ids(
    payload: _BusinessDriverSynthesis,
    source_refs_by_id: dict[str, SourceRef],
) -> None:
    source_id_groups: list[list[str]] = [
        *[point.source_ids for point in _driver_map_points(payload.driver_map)],
        *[point.source_ids for point in payload.positive_signals],
        *[point.source_ids for point in payload.negative_signals],
        *[claim.source_ids for claim in payload.claims],
    ]
    for source_ids in source_id_groups:
        for source_id in source_ids:
            if source_id not in source_refs_by_id:
                raise ReportSynthesisError(f"Unknown source_id in synthesized report: {source_id}")


def _validate_cash_flow_source_ids(
    payload: _CashFlowSynthesis,
    source_refs_by_id: dict[str, SourceRef],
) -> None:
    source_id_groups: list[list[str]] = [
        *[metric.source_ids for metric in payload.cash_metrics],
        *[point.source_ids for point in _capital_allocation_points(payload.capital_allocation)],
        *[point.source_ids for point in payload.allocation_discipline],
        *[point.source_ids for point in payload.red_flags],
        *[claim.source_ids for claim in payload.claims],
    ]
    for source_ids in source_id_groups:
        for source_id in source_ids:
            if source_id not in source_refs_by_id:
                raise ReportSynthesisError(f"Unknown source_id in synthesized report: {source_id}")


def _coverage(
    payload: _LatestEarningsSynthesis,
    source_refs: list[SourceRef],
) -> TaskSectionCoverage:
    missing_sections = []
    if not payload.key_takeaways:
        missing_sections.append("key_takeaways")
    if not payload.financial_dashboard.metrics:
        missing_sections.append("financial_dashboard.metrics")
    if not payload.driver_snapshot:
        missing_sections.append("driver_snapshot")
    if not payload.risk_snapshot:
        missing_sections.append("risk_snapshot")
    if not source_refs:
        missing_sections.append("evidence_refs")
    return TaskSectionCoverage(
        status="complete" if not missing_sections else "partial",
        missing_sections=missing_sections,
        evidence_count=len(source_refs),
    )


def _business_driver_coverage(
    payload: _BusinessDriverSynthesis,
    source_refs: list[SourceRef],
) -> TaskSectionCoverage:
    missing_sections = []
    if not any(_driver_map_points(payload.driver_map)):
        missing_sections.append("driver_map")
    if not payload.positive_signals and not payload.negative_signals:
        missing_sections.append("signals")
    if not payload.watchlist:
        missing_sections.append("watchlist")
    if not source_refs:
        missing_sections.append("evidence_refs")
    return TaskSectionCoverage(
        status="complete" if not missing_sections else "partial",
        missing_sections=missing_sections,
        evidence_count=len(source_refs),
    )


def _driver_map_points(driver_map: _SynthesizedDriverMap) -> list[_SynthesizedPoint]:
    return [
        *driver_map.product,
        *driver_map.segment,
        *driver_map.geography,
        *driver_map.demand,
        *driver_map.pricing,
        *driver_map.customer,
        *driver_map.strategy,
    ]


def _cash_flow_coverage(
    payload: _CashFlowSynthesis,
    source_refs: list[SourceRef],
) -> TaskSectionCoverage:
    missing_sections = []
    if not payload.cash_metrics:
        missing_sections.append("cash_metrics")
    if not any(_capital_allocation_points(payload.capital_allocation)):
        missing_sections.append("capital_allocation")
    if not payload.allocation_discipline:
        missing_sections.append("allocation_discipline")
    if not source_refs:
        missing_sections.append("evidence_refs")
    return TaskSectionCoverage(
        status="complete" if not missing_sections else "partial",
        missing_sections=missing_sections,
        evidence_count=len(source_refs),
    )


def _capital_allocation_points(
    capital_allocation: _SynthesizedCapitalAllocation,
) -> list[_SynthesizedPoint]:
    return [
        *capital_allocation.capex,
        *capital_allocation.buybacks,
        *capital_allocation.dividends,
        *capital_allocation.debt,
        *capital_allocation.liquidity,
    ]


def _claims_from_payload(
    request: AgentRequest,
    claims: list[_SynthesizedClaim],
    source_refs: list[SourceRef],
    source_refs_by_id: dict[str, SourceRef],
) -> list[EvidenceBoundClaim]:
    synthesized_claims = [
        EvidenceBoundClaim(
            claim_id=f"{request.run_id}:synthesized_claim:{index + 1}",
            text=claim.text,
            citation_status=claim.citation_status,
            source_refs=[source_refs_by_id[source_id] for source_id in claim.source_ids],
        )
        for index, claim in enumerate(claims)
    ]
    if not synthesized_claims and source_refs:
        synthesized_claims = [
            EvidenceBoundClaim(
                claim_id=f"{request.run_id}:synthesized_claim:1",
                text="Evidence-bound synthesis generated without explicit claims.",
                citation_status=source_refs[0].citation_status,
                source_refs=source_refs[:1],
            )
        ]
    return synthesized_claims


def _point_from_payload(
    point: _SynthesizedPoint,
    source_refs_by_id: dict[str, SourceRef],
) -> EvidenceBoundPoint:
    return EvidenceBoundPoint(
        title=point.title,
        summary=point.summary,
        evidence_refs=[
            _evidence_ref(source_refs_by_id[source_id]) for source_id in point.source_ids
        ],
        citation_status=point.citation_status,
    )


def _metric_from_payload(
    metric: _SynthesizedMetric,
    source_refs_by_id: dict[str, SourceRef],
) -> EvidenceBoundMetric:
    return EvidenceBoundMetric(
        name=metric.name,
        value=metric.value,
        period=metric.period,
        interpretation=metric.interpretation,
        evidence_refs=[
            _evidence_ref(source_refs_by_id[source_id]) for source_id in metric.source_ids
        ],
        citation_status=metric.citation_status,
    )


def _evidence_ref(source_ref: SourceRef) -> EvidenceRef:
    return EvidenceRef(
        section=source_ref.section,
        excerpt=source_ref.snippet,
        filing_date=source_ref.filing_date,
        accession_number=source_ref.accession_number,
        source_id=source_ref.source_id,
    )


def _evidence_lines(
    source_refs: list[SourceRef],
    original_source_refs: list[SourceRef] | None = None,
) -> list[str]:
    originals = original_source_refs or source_refs
    return [
        (
            f"- source_id={source_ref.source_id}; section={source_ref.section}; "
            f"original_source_id={original_source_ref.source_id}; "
            f"filing_type={source_ref.filing_type}; filing_date={source_ref.filing_date}; "
            f"snippet={_clip(source_ref.snippet)}"
        )
        for source_ref, original_source_ref in zip(source_refs, originals, strict=False)
    ]


def _citation_status_from_value(value: Any) -> CitationStatus:
    try:
        return CitationStatus(value)
    except (TypeError, ValueError):
        return CitationStatus.UNVERIFIED


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None


def _clip(text: str, limit: int = 700) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}..."


def _json_safe(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=True)
