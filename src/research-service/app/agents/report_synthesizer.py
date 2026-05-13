from os import getenv
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.llm_gateway import LlmClient, LlmRequest, LlmResponse
from app.contracts.agent import AgentRequest, AgentState
from app.contracts.report import (
    BusinessDriverSections,
    CapitalAllocation,
    CashFlowCapitalAllocationSections,
    CashQualityVerdict,
    CitationStatus,
    CompanyProfileSection,
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


DEFAULT_SYNTHESIS_TIMEOUT_SECONDS = 5
DEFAULT_SYNTHESIS_ATTEMPTS = 1


class _SynthesizedPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    citation_status: CitationStatus = CitationStatus.UNVERIFIED

    @field_validator("citation_status", mode="before")
    @classmethod
    def normalize_citation_status(cls, value: object) -> CitationStatus:
        return _citation_status_from_value(value)


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

    @field_validator("citation_status", mode="before")
    @classmethod
    def normalize_citation_status(cls, value: object) -> CitationStatus:
        return _citation_status_from_value(value)


class _SynthesizedDashboard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[_SynthesizedMetric] = Field(default_factory=list)
    chart_focus: list[str] = Field(default_factory=list)


class _SynthesizedClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    citation_status: CitationStatus = CitationStatus.UNVERIFIED

    @field_validator("citation_status", mode="before")
    @classmethod
    def normalize_citation_status(cls, value: object) -> CitationStatus:
        return _citation_status_from_value(value)


class _SynthesizedCompanyProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    citation_status: CitationStatus = CitationStatus.UNVERIFIED

    @field_validator("citation_status", mode="before")
    @classmethod
    def normalize_citation_status(cls, value: object) -> CitationStatus:
        return _citation_status_from_value(value)


class _CompanyProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1)


class _LatestEarningsSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company_profile: _SynthesizedCompanyProfile | None = None
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
            timeout_seconds=_synthesis_timeout_seconds(),
        ),
    )
    payload = _LatestEarningsSynthesis.model_validate(response.content)
    return build_latest_earnings_report_from_payload(
        request, state, payload.model_dump(mode="json")
    )


def build_latest_earnings_report_from_payload(
    request: AgentRequest,
    state: AgentState,
    payload_data: dict[str, Any],
) -> EvidenceAwareReport:
    source_refs = _source_refs_from_state(state)
    source_refs_by_id = _alias_source_refs_by_id(source_refs)
    payload_data = _normalize_latest_earnings_payload(payload_data)
    payload = _LatestEarningsSynthesis.model_validate(payload_data)
    _validate_source_ids(payload, source_refs_by_id)
    coverage = _coverage(payload, source_refs)
    company_profile = _company_profile_from_synthesis(payload, state, source_refs_by_id)
    task_sections = LatestEarningsSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        coverage=coverage,
        company_profile=company_profile,
        topline_verdict=payload.topline_verdict,
        key_takeaways=[
            _point_from_payload(point, source_refs_by_id) for point in payload.key_takeaways
        ],
        financial_dashboard=LatestFinancialDashboard(
            metrics=[
                _metric_with_evidence_guardrail(metric, state, source_refs_by_id)
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


def synthesize_latest_earnings_payload() -> dict[str, Any]:
    return {
        "company_profile": {
            "summary": "Concise investor-facing company profile.",
            "source_ids": [],
            "citation_status": "unverified",
        },
        "topline_verdict": {
            "headline": "Short evidence-bound earnings verdict.",
            "summary": "One to two sentences on the latest earnings readout.",
            "verdict": "mixed",
        },
        "key_takeaways": [
            {
                "title": "Key takeaway",
                "summary": "Evidence-bound takeaway.",
                "source_ids": [],
                "citation_status": "unverified",
            }
        ],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "Revenue",
                    "value": "$0.0B",
                    "period": "latest_quarter",
                    "interpretation": "What the KPI means.",
                    "source_ids": [],
                    "citation_status": "unverified",
                }
            ],
            "chart_focus": ["revenue", "gross_margin", "operating_income"],
        },
        "driver_snapshot": [
            {
                "title": "Driver",
                "summary": "Operating driver backed by evidence.",
                "source_ids": [],
                "citation_status": "unverified",
            }
        ],
        "risk_snapshot": [
            {
                "title": "Risk",
                "summary": "Risk backed by evidence.",
                "source_ids": [],
                "citation_status": "unverified",
            }
        ],
        "claims": [
            {
                "text": "Evidence-bound claim.",
                "source_ids": [],
                "citation_status": "unverified",
            }
        ],
    }


def _normalize_latest_earnings_payload(payload_data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload_data)
    company_profile = normalized.get("company_profile")
    if isinstance(company_profile, str):
        normalized["company_profile"] = {
            "summary": company_profile,
            "source_ids": [],
            "citation_status": "unverified",
        }
    elif isinstance(company_profile, dict) and "summary" not in company_profile:
        summary = (
            company_profile.get("business_summary")
            or company_profile.get("businessSummary")
            or company_profile.get("description")
        )
        normalized["company_profile"] = {
            "summary": str(
                summary or company_profile.get("name") or "Company profile unavailable."
            ),
            "source_ids": _list_of_strings(company_profile.get("source_ids")),
            "citation_status": str(company_profile.get("citation_status") or "unverified"),
        }
    topline_verdict = normalized.get("topline_verdict")
    if isinstance(topline_verdict, str):
        normalized["topline_verdict"] = {
            "headline": topline_verdict[:120],
            "summary": topline_verdict,
            "verdict": "mixed",
        }
    normalized["key_takeaways"] = _normalize_synthesized_points(
        normalized.get("key_takeaways", [])
    )
    normalized["driver_snapshot"] = _normalize_synthesized_points(
        normalized.get("driver_snapshot", [])
    )
    normalized["risk_snapshot"] = _normalize_synthesized_points(
        normalized.get("risk_snapshot", [])
    )
    normalized["claims"] = _normalize_synthesized_claims(normalized.get("claims", []))
    dashboard = normalized.get("financial_dashboard")
    if isinstance(dashboard, dict):
        normalized["financial_dashboard"] = {
            "metrics": _normalize_synthesized_metrics(dashboard.get("metrics", [])),
            "chart_focus": _list_of_strings(dashboard.get("chart_focus")),
        }
    return normalized


def synthesize_business_driver_report(
    request: AgentRequest,
    state: AgentState,
    client: LlmClient,
) -> EvidenceAwareReport:
    if request.task_type != ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        raise ReportSynthesisError(f"Unsupported synthesis task: {request.task_type.value}")

    source_refs = _source_refs_from_state(state)
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
            timeout_seconds=_synthesis_timeout_seconds(),
        ),
    )
    payload = _BusinessDriverSynthesis.model_validate(response.content)
    return build_business_driver_report_from_payload(
        request,
        state,
        payload.model_dump(mode="json"),
    )


def build_business_driver_report_from_payload(
    request: AgentRequest,
    state: AgentState,
    payload_data: dict[str, Any],
) -> EvidenceAwareReport:
    source_refs = _source_refs_from_state(state)
    source_refs_by_id = _alias_source_refs_by_id(source_refs)
    payload_data = _normalize_business_driver_payload(payload_data)
    payload = _BusinessDriverSynthesis.model_validate(payload_data)
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


def _normalize_business_driver_payload(payload_data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload_data)
    driver_thesis = normalized.get("driver_thesis")
    if isinstance(driver_thesis, str):
        normalized["driver_thesis"] = {
            "headline": driver_thesis[:120],
            "durability": "unclear",
            "summary": driver_thesis,
        }
    driver_map = payload_data.get("driver_map")
    if not isinstance(driver_map, dict):
        normalized["driver_map"] = {
            "product": [],
            "segment": [],
            "geography": [],
            "demand": [],
            "pricing": [],
            "customer": [],
            "strategy": [],
        }
    else:
        normalized["driver_map"] = {
            key: _normalize_synthesized_points(value)
            for key, value in driver_map.items()
        }
    normalized["positive_signals"] = _normalize_synthesized_points(
        normalized.get("positive_signals", [])
    )
    normalized["negative_signals"] = _normalize_synthesized_points(
        normalized.get("negative_signals", [])
    )
    normalized["claims"] = _normalize_synthesized_claims(normalized.get("claims", []))
    return normalized


def _normalize_synthesized_points(value: object) -> object:
    if isinstance(value, str):
        return [
            {
                "title": "Evidence point",
                "summary": value,
                "source_ids": [],
                "citation_status": "unverified",
            }
        ]
    if not isinstance(value, list):
        return value
    return [_normalize_synthesized_point(point) for point in value]


def _normalize_synthesized_metrics(value: object) -> object:
    if isinstance(value, dict):
        return [
            _normalize_synthesized_metric({"name": key, "value": metric_value})
            for key, metric_value in value.items()
        ]
    if not isinstance(value, list):
        return value
    return [_normalize_synthesized_metric(metric) for metric in value]


def _normalize_synthesized_metric(metric: object) -> object:
    if not isinstance(metric, dict):
        return {
            "name": "Metric",
            "value": str(metric),
            "period": None,
            "interpretation": "Reported metric.",
            "source_ids": [],
            "citation_status": "unverified",
        }
    return {
        "name": str(metric.get("name") or metric.get("metric") or metric.get("label") or "Metric"),
        "value": str(metric.get("value") or "Not extracted"),
        "period": metric.get("period"),
        "interpretation": str(
            metric.get("interpretation") or metric.get("summary") or "Reported metric."
        ),
        "source_ids": _source_ids_from_value(metric),
        "citation_status": str(metric.get("citation_status") or "supported"),
    }


def _normalize_synthesized_claims(value: object) -> object:
    if not isinstance(value, list):
        return value
    normalized_claims: list[object] = []
    for claim in value:
        if isinstance(claim, str):
            normalized_claims.append(
                {
                    "text": claim,
                    "source_ids": [],
                    "citation_status": "unverified",
                }
            )
            continue
        if not isinstance(claim, dict):
            normalized_claims.append(claim)
            continue
        normalized_claims.append(
            {
                "text": str(
                    claim.get("text")
                    or claim.get("claim")
                    or claim.get("statement")
                    or claim.get("summary")
                    or ""
                ),
                "source_ids": _source_ids_from_value(claim),
                "citation_status": str(claim.get("citation_status") or "supported"),
            }
        )
    return normalized_claims


def _list_of_strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item)]


def _source_ids_from_value(value: dict[str, object]) -> list[str]:
    source_ids = _list_of_strings(value.get("source_ids"))
    source_id = value.get("source_id") or value.get("node_id")
    if source_id:
        source_ids.append(str(source_id))
    return source_ids


def _normalize_synthesized_point(point: object) -> object:
    if not isinstance(point, dict):
        return {
            "title": "Evidence point",
            "summary": str(point),
            "source_ids": [],
            "citation_status": "unverified",
        }
    if "title" in point and "summary" in point:
        return {
            **point,
            "source_ids": _source_ids_from_value(point),
            "citation_status": str(point.get("citation_status") or "supported"),
        }
    if "signal" in point:
        signal = str(point.get("signal") or "")
        return {
            "title": signal or "Evidence signal",
            "summary": signal or "Evidence signal.",
            "source_ids": _source_ids_from_value(point),
            "citation_status": str(point.get("citation_status") or "unverified"),
        }
    text = point.get("summary") or point.get("text") or point.get("snippet")
    title = point.get("title") or point.get("driver") or point.get("label")
    if not text and "value" in point:
        value = point.get("value")
        period = point.get("period")
        text = f"Value was {value}" + (f" for {period}." if period else ".")
    if not text:
        return point
    return {
        "title": str(
            title or ("Capital allocation item" if "value" in point else "Evidence node")
        ),
        "summary": str(text),
        "source_ids": _source_ids_from_value(point),
        "citation_status": str(point.get("citation_status") or "supported"),
    }


def synthesize_cash_flow_report(
    request: AgentRequest,
    state: AgentState,
    client: LlmClient,
) -> EvidenceAwareReport:
    if request.task_type != ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        raise ReportSynthesisError(f"Unsupported synthesis task: {request.task_type.value}")

    source_refs = _source_refs_from_state(state)
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
            timeout_seconds=_synthesis_timeout_seconds(),
        ),
    )
    payload = _CashFlowSynthesis.model_validate(response.content)
    return build_cash_flow_report_from_payload(request, state, payload.model_dump(mode="json"))


def build_cash_flow_report_from_payload(
    request: AgentRequest,
    state: AgentState,
    payload_data: dict[str, Any],
) -> EvidenceAwareReport:
    source_refs = _source_refs_from_state(state)
    source_refs_by_id = _alias_source_refs_by_id(source_refs)
    payload_data = _normalize_cash_flow_payload(payload_data)
    payload = _CashFlowSynthesis.model_validate(payload_data)
    _validate_cash_flow_source_ids(payload, source_refs_by_id)
    task_sections = CashFlowCapitalAllocationSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        coverage=_cash_flow_coverage(payload, source_refs),
        cash_quality_verdict=payload.cash_quality_verdict,
        cash_metrics=[
            _metric_with_evidence_guardrail(metric, state, source_refs_by_id)
            for metric in payload.cash_metrics
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


def _normalize_cash_flow_payload(payload_data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload_data)
    verdict = normalized.get("cash_quality_verdict")
    if isinstance(verdict, str):
        normalized["cash_quality_verdict"] = {
            "headline": verdict[:120],
            "earnings_backed_by_cash": "unclear",
            "summary": verdict,
        }
    normalized["cash_metrics"] = _normalize_synthesized_metrics(
        normalized.get("cash_metrics", [])
    )
    capital_allocation = payload_data.get("capital_allocation")
    if isinstance(capital_allocation, dict):
        normalized["capital_allocation"] = {
            key: _normalize_synthesized_points(value)
            for key, value in capital_allocation.items()
        }
    normalized["allocation_discipline"] = _normalize_synthesized_points(
        normalized.get("allocation_discipline", [])
    )
    normalized["red_flags"] = _normalize_synthesized_points(normalized.get("red_flags", []))
    normalized["claims"] = _normalize_synthesized_claims(normalized.get("claims", []))
    return normalized


def synthesize_company_profile(
    request: AgentRequest,
    state: AgentState,
    client: LlmClient,
) -> CompanyProfileSection | None:
    business_summary = _company_profile_raw_summary_from_facts(state)
    if not business_summary:
        return None
    response = _complete_company_profile_json(
        client,
        LlmRequest(
            run_id=request.run_id,
            provider=client.provider,
            model=request.llm_model,
            task_type=request.task_type,
            system_prompt=_company_profile_system_prompt(),
            user_prompt=_company_profile_user_prompt(state, business_summary),
            state=state,
            timeout_seconds=2,
        ),
    )
    payload = _CompanyProfileWrite.model_validate(response.content)
    summary = _concise_company_profile(payload.summary)
    if not summary:
        return None
    return CompanyProfileSection(
        summary=summary,
        evidence_refs=[],
        citation_status=CitationStatus.UNVERIFIED,
    )


def _system_prompt() -> str:
    return (
        "You are a financial research report synthesizer. Return one JSON object only. "
        "Use only the provided evidence. Do not include chain-of-thought. "
        "Every field must match the requested JSON schema exactly."
    )


def _complete_synthesis_json(client: LlmClient, request: LlmRequest) -> LlmResponse:
    last_error: Exception | None = None
    for _ in range(_synthesis_attempts()):
        try:
            return client.complete_json(request)
        except Exception as exc:
            last_error = exc
    raise ReportSynthesisError(f"LLM synthesis JSON failed after retry: {last_error}")


def _complete_company_profile_json(client: LlmClient, request: LlmRequest) -> LlmResponse:
    try:
        return client.complete_json(request)
    except Exception as exc:
        raise ReportSynthesisError(f"Company profile synthesis failed: {exc}") from exc


def _company_profile_system_prompt() -> str:
    return (
        "You write concise investor-facing company profiles. Return one JSON object only. "
        "Use only the provided company facts. Do not include chain-of-thought."
    )


def _company_profile_user_prompt(state: AgentState, business_summary: str) -> str:
    facts = {
        key: value
        for key, value in state.evidence_memory.facts.items()
        if key
        in {
            "company_name",
            "companyName",
            "market_sector",
            "marketSector",
            "market_industry",
            "marketIndustry",
            "business_summary",
            "businessSummary",
            "market_business_summary",
            "marketBusinessSummary",
            "description",
        }
    }
    return (
        "Write a concise investor-facing company profile in 1-2 sentences.\n"
        "Use only the provided company facts.\n"
        "Mention business identity, core products, and primary markets when available.\n"
        "Do not include founding history, headquarters, retail channels, or exhaustive "
        "product lists.\n"
        'Return JSON only: {"summary": "..."}.\n'
        f"Ticker: {state.ticker}\n"
        f"Facts: {_json_safe(facts)}\n"
        f"Business summary: {business_summary}"
    )


def _synthesis_timeout_seconds() -> int:
    return _bounded_int_from_env(
        "AGENT_SYNTHESIS_TIMEOUT_SECONDS",
        default=DEFAULT_SYNTHESIS_TIMEOUT_SECONDS,
        minimum=5,
        maximum=75,
    )


def _synthesis_attempts() -> int:
    return _bounded_int_from_env(
        "AGENT_SYNTHESIS_RETRIES",
        default=DEFAULT_SYNTHESIS_ATTEMPTS,
        minimum=1,
        maximum=3,
    )


def _bounded_int_from_env(
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = getenv(name)
    if raw_value is None or not raw_value.strip():
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


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
        "Prioritize operating drivers: products, services, segments, demand, pricing, "
        "customers, channel inventory, mix, and strategy.\n"
        "Regulatory, compliance, legal, or market-risk evidence belongs in risks, "
        "negative_signals, or watchlist and must not be the main driver_thesis "
        "unless no operating-driver evidence is available.\n"
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
        "Prioritize operating cash flow, capital expenditures, share repurchases, "
        "dividends, debt, and liquidity as separate capital_allocation categories when "
        "the evidence contains those terms. Do not collapse all capital return evidence "
        "into liquidity.\n"
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
        '  "company_profile": {"summary": "...", "source_ids": ["..."], '
        '"citation_status": "supported|partial|missing|unverified"},\n'
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
        "Company profile must use Facts.business_summary, businessSummary, "
        "market_business_summary, marketBusinessSummary, or description when available. "
        "If no such profile fact exists, return null for company_profile; do not synthesize "
        "a company profile from filing snippets or risk-factor evidence.\n"
        "Each profile, point, metric, and claim must use source_ids from the provided "
        "evidence only.\n"
        "If evidence is thin, still return the same object/array shape with cautious text.\n"
        "Use cautious language when evidence is thin.\n"
        "Use Metric evidence values for financial_dashboard.metrics when they are available. "
        "Prefer SEC companyfacts metric values over table snippets for KPI values. "
        "Do not say a metric was not extracted when Metric evidence contains value and unit. "
        "For latest earnings, prioritize revenue, gross margin, and operating income.\n"
        "Put operating result evidence in topline_verdict, key_takeaways, "
        "financial_dashboard, and driver_snapshot. Risk disclosure evidence belongs only "
        "in risk_snapshot unless no operating result evidence is available.\n"
        f"Ticker: {state.ticker}\n"
        f"Task: {request.task_type.value}\n"
        f"Facts: {_json_safe(facts)}\n"
        f"Metric evidence: {_json_safe(state.evidence_memory.metric_evidence)}\n"
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
        if source_ref.source_id and ":sec_companyfacts:" in source_ref.source_id:
            refs_by_id.setdefault("sec_companyfacts", source_ref)
        if source_ref.section.strip().lower() == "sec companyfacts":
            refs_by_id.setdefault("sec_companyfacts", source_ref)
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
        payload.company_profile.source_ids if payload.company_profile is not None else [],
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
    if payload.company_profile is None:
        missing_sections.append("company_profile")
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


def _company_profile_from_payload(
    profile: _SynthesizedCompanyProfile,
    source_refs_by_id: dict[str, SourceRef],
) -> CompanyProfileSection:
    return CompanyProfileSection(
        summary=_concise_company_profile(profile.summary),
        evidence_refs=[
            _evidence_ref(source_refs_by_id[source_id]) for source_id in profile.source_ids
        ],
        citation_status=profile.citation_status,
    )


def _company_profile_from_synthesis(
    payload: _LatestEarningsSynthesis,
    state: AgentState,
    source_refs_by_id: dict[str, SourceRef],
) -> CompanyProfileSection | None:
    if payload.company_profile is not None:
        return _company_profile_from_payload(payload.company_profile, source_refs_by_id)
    business_summary = _company_profile_summary_from_facts(state)
    if not business_summary:
        return None
    return CompanyProfileSection(
        summary=business_summary,
        evidence_refs=[],
        citation_status=CitationStatus.UNVERIFIED,
    )


def _company_profile_summary_from_facts(state: AgentState) -> str:
    return _concise_company_profile(_company_profile_raw_summary_from_facts(state))


def _company_profile_raw_summary_from_facts(state: AgentState) -> str:
    return str(
        state.evidence_memory.facts.get("business_summary")
        or state.evidence_memory.facts.get("businessSummary")
        or state.evidence_memory.facts.get("market_business_summary")
        or state.evidence_memory.facts.get("marketBusinessSummary")
        or state.evidence_memory.facts.get("description")
        or ""
    ).strip()


def _concise_company_profile(summary: str, *, max_sentences: int = 2) -> str:
    normalized = " ".join(summary.split()).strip()
    if not normalized:
        return ""
    sentences = _profile_sentences(normalized)
    concise = " ".join(sentences[:max_sentences]).strip()
    return concise or normalized


def _profile_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    for index, char in enumerate(text):
        if char not in ".!?":
            continue
        if _is_abbreviation_period(text, index):
            continue
        sentence = text[start : index + 1].strip()
        if sentence:
            sentences.append(sentence)
        start = index + 1
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences or [text]


def _is_abbreviation_period(text: str, index: int) -> bool:
    token_start = text.rfind(" ", 0, index) + 1
    token = text[token_start : index + 1]
    return token in {"Inc.", "Corp.", "Co.", "Ltd.", "U.S.", "Mr.", "Ms.", "Dr."}


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


def _metric_with_evidence_guardrail(
    metric: _SynthesizedMetric,
    state: AgentState,
    source_refs_by_id: dict[str, SourceRef],
) -> EvidenceBoundMetric:
    metric_record = _metric_evidence_for_name(metric.name, state.evidence_memory.metric_evidence)
    if not metric_record or not _has_fact_value(metric_record):
        return _metric_from_payload(metric, source_refs_by_id)
    if not _metric_value_needs_evidence(metric.value, metric.interpretation):
        return _metric_from_payload(metric, source_refs_by_id)
    source_id = str(metric_record.get("source_id") or "").strip()
    if not source_id or source_id not in source_refs_by_id:
        return _metric_from_payload(metric, source_refs_by_id)
    source_ref = source_refs_by_id[source_id]
    return EvidenceBoundMetric(
        name=metric.name,
        value=_metric_evidence_value(metric_record),
        period=_metric_evidence_period(metric_record) or metric.period,
        interpretation=_metric_evidence_interpretation(metric_record, source_ref),
        evidence_refs=[_evidence_ref(source_ref)],
        citation_status=CitationStatus.SUPPORTED,
    )


def _metric_evidence_for_name(
    metric_name: str,
    metric_evidence: list[dict[str, Any]],
) -> dict[str, Any] | None:
    normalized_name = _normalize_metric_name(metric_name)
    for record in metric_evidence:
        normalized_record = _normalize_metric_name(
            str(record.get("normalized_metric") or record.get("metric") or "")
        )
        if normalized_record == normalized_name:
            return record
    for record in metric_evidence:
        normalized_record = _normalize_metric_name(
            str(record.get("normalized_metric") or record.get("metric") or "")
        )
        if normalized_record and (
            normalized_record in normalized_name or normalized_name in normalized_record
        ):
            return record
    return None


def _has_fact_value(record: dict[str, Any]) -> bool:
    return record.get("value") is not None and str(record.get("source") or "") == "sec_companyfacts"


def _metric_value_needs_evidence(value: str, interpretation: str) -> bool:
    normalized = f"{value} {interpretation}".lower()
    markers = (
        "not discernible",
        "not extracted",
        "not provided",
        "specific financial figures not extracted",
        "see cited evidence",
        "n/a",
        "unknown",
    )
    return any(marker in normalized for marker in markers)


def _metric_evidence_value(record: dict[str, Any]) -> str:
    value = record.get("value")
    unit = str(record.get("unit") or "").strip()
    if isinstance(value, int | float):
        formatted = _compact_number(value)
    else:
        formatted = str(value)
    if unit == "USD" and not formatted.startswith("$"):
        return f"${formatted}"
    return formatted


def _metric_evidence_period(record: dict[str, Any]) -> str | None:
    period = record.get("fact_period") or record.get("period")
    return str(period) if period is not None else None


def _metric_evidence_interpretation(record: dict[str, Any], source_ref: SourceRef) -> str:
    concept = str(record.get("concept") or "").strip()
    if concept:
        clipped_excerpt = _clip(source_ref.snippet, 220)
        return f"SEC companyfacts concept {concept}; evidence excerpt: {clipped_excerpt}"
    return _clip(source_ref.snippet, 220)


def _normalize_metric_name(metric: str) -> str:
    return " ".join(metric.strip().lower().replace("_", " ").split())


def _compact_number(value: int | float) -> str:
    absolute = abs(float(value))
    if absolute >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    return f"{value:,.0f}"


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
    if isinstance(value, str):
        normalized = value.strip().lower()
        aliases = {
            "verified": CitationStatus.SUPPORTED,
            "grounded": CitationStatus.SUPPORTED,
            "cited": CitationStatus.SUPPORTED,
            "unsupported": CitationStatus.MISSING,
            "unknown": CitationStatus.UNVERIFIED,
        }
        if normalized in aliases:
            return aliases[normalized]
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
