import re
from os import getenv
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.llm_gateway import LlmClient, LlmRequest, LlmResponse
from app.agents.structured_facts import (
    cash_flow_metric_records_from_facts,
    normalize_metric_name,
)
from app.contracts.agent import AgentRequest, AgentState
from app.contracts.report import (
    BullBearRead,
    BusinessDriverSections,
    CapitalAllocation,
    CashFlowCapitalAllocationSections,
    CashQualityVerdict,
    CitationStatus,
    CompanyProfileSection,
    DriverMap,
    DriverThesis,
    DriversAndDraggers,
    EvidenceAwareReport,
    EvidenceBoundClaim,
    EvidenceBoundMetric,
    EvidenceBoundPoint,
    EvidenceRef,
    LatestEarningsSections,
    LatestFinancialDashboard,
    QualityOfQuarter,
    SourceRef,
    TaskSectionCoverage,
    ToplineVerdict,
    WatchNextItem,
)
from app.contracts.research_task import ResearchTaskType


class ReportSynthesisError(RuntimeError):
    pass


DEFAULT_SYNTHESIS_TIMEOUT_SECONDS = 5
DEFAULT_SYNTHESIS_ATTEMPTS = 1

_NOISY_BUSINESS_DRIVER_TEXT_PHRASES = (
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
    "revenue and contract costs",
    "revenue is generally recognized",
    "revenue sharing",
    "table of contents",
)

_BUSINESS_DRIVER_PARTIAL_PLACEHOLDER = "Evidence for this business-driver lens remains partial."


def _is_zh_locale(language: str | None) -> bool:
    return str(language or "").lower().startswith("zh")


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
        return _format_metric_display_value(value)

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
    quality_of_quarter: "_SynthesizedQualityOfQuarter | None" = None
    drivers_and_draggers: "_SynthesizedDriversAndDraggers | None" = None
    bull_bear_read: "_SynthesizedBullBearRead | None" = None
    watch_next: list["_SynthesizedWatchNextItem"] = Field(default_factory=list)
    claims: list[_SynthesizedClaim] = Field(default_factory=list)


class _SynthesizedQualityOfQuarter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    growth_quality: _SynthesizedPoint | None = None
    margin_quality: _SynthesizedPoint | None = None
    cash_quality: _SynthesizedPoint | None = None
    one_time_items: _SynthesizedPoint | None = None


class _SynthesizedDriversAndDraggers(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drivers: list[_SynthesizedPoint] = Field(default_factory=list)
    draggers: list[_SynthesizedPoint] = Field(default_factory=list)


class _SynthesizedBullBearRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bull_case: list[_SynthesizedPoint] = Field(default_factory=list)
    bear_case: list[_SynthesizedPoint] = Field(default_factory=list)
    balanced_read: _SynthesizedPoint | None = None


class _SynthesizedWatchNextItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1)
    metric: str | None = None
    why_it_matters: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    citation_status: CitationStatus = CitationStatus.UNVERIFIED

    @field_validator("citation_status", mode="before")
    @classmethod
    def normalize_citation_status(cls, value: object) -> CitationStatus:
        return _citation_status_from_value(value)


class _SynthesizedDriverMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revenue_bridge: _SynthesizedPoint | None = None
    segment_momentum: _SynthesizedPoint | None = None
    margin_and_mix: _SynthesizedPoint | None = None
    demand_signals: _SynthesizedPoint | None = None


class _BusinessDriverSynthesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver_thesis: DriverThesis
    driver_map: _SynthesizedDriverMap
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
            system_prompt=_system_prompt(request.language),
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
    _sanitize_latest_earnings_source_ids(payload, source_refs_by_id)
    dashboard_metrics = _final_dashboard_metrics(
        payload.financial_dashboard.metrics,
        state,
        source_refs_by_id,
    )
    quality_of_quarter = _quality_of_quarter_from_payload(
        payload.quality_of_quarter,
        source_refs_by_id,
    )
    drivers_and_draggers = _drivers_and_draggers_from_payload(
        payload.drivers_and_draggers,
        source_refs_by_id,
    )
    bull_bear_read = _bull_bear_read_from_payload(
        payload.bull_bear_read,
        source_refs_by_id,
    )
    watch_next = [
        _watch_next_item_from_payload(item, source_refs_by_id) for item in payload.watch_next
    ]
    key_takeaways = [
        _point_from_payload(point, source_refs_by_id) for point in payload.key_takeaways
    ]
    driver_snapshot = [
        _point_from_payload(point, source_refs_by_id) for point in payload.driver_snapshot
    ]
    risk_snapshot = [
        _point_from_payload(point, source_refs_by_id) for point in payload.risk_snapshot
    ]
    quality_of_quarter = _latest_quality_with_backfill(
        quality_of_quarter,
        dashboard_metrics,
        key_takeaways,
        source_refs,
    )
    drivers_and_draggers = _latest_drivers_with_backfill(
        drivers_and_draggers,
        driver_snapshot,
        risk_snapshot,
    )
    bull_bear_read = _latest_bull_bear_with_backfill(
        bull_bear_read,
        payload.topline_verdict,
        key_takeaways,
        driver_snapshot,
        risk_snapshot,
        source_refs,
    )
    watch_next = _latest_watch_next_with_backfill(
        watch_next,
        dashboard_metrics,
        risk_snapshot,
        source_refs,
    )
    coverage = _latest_coverage(
        payload,
        source_refs,
        quality_of_quarter,
        drivers_and_draggers,
        bull_bear_read,
        watch_next,
        dashboard_metrics,
    )
    company_profile = _company_profile_from_synthesis(payload, state, source_refs_by_id)
    task_sections = LatestEarningsSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        coverage=coverage,
        company_profile=company_profile,
        topline_verdict=payload.topline_verdict,
        key_takeaways=key_takeaways,
        financial_dashboard=LatestFinancialDashboard(
            metrics=dashboard_metrics,
            chart_focus=payload.financial_dashboard.chart_focus,
        ),
        driver_snapshot=driver_snapshot,
        risk_snapshot=risk_snapshot,
        quality_of_quarter=quality_of_quarter,
        drivers_and_draggers=drivers_and_draggers,
        bull_bear_read=bull_bear_read,
        watch_next=watch_next,
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
    summary = _latest_earnings_report_summary(
        payload.topline_verdict.summary,
        key_takeaways,
        driver_snapshot,
        risk_snapshot,
        dashboard_metrics,
    )
    return EvidenceAwareReport(
        run_id=request.run_id,
        ticker=state.ticker,
        task_type=request.task_type,
        task_sections=task_sections,
        sections={"summary": summary, "synthesis": "llm"},
        claims=claims,
        retrieval_records=state.retrieval_records,
    )


def synthesize_latest_earnings_payload(language: str = "en") -> dict[str, Any]:
    if _is_zh_locale(language):
        return {
            "company_profile": {
                "summary": "简洁的面向投资者的公司画像。",
                "source_ids": [],
                "citation_status": "unverified",
            },
            "topline_verdict": {
                "headline": "有证据支撑的简要财报判断。",
                "summary": "用三到五句话概括最新财报解读。",
                "verdict": "mixed",
                "confidence": "medium",
            },
            "key_takeaways": [
                {
                    "title": "关键要点",
                    "summary": "有证据支撑的要点。",
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
                        "interpretation": "这个 KPI 的含义。",
                        "source_ids": [],
                        "citation_status": "unverified",
                    }
                ],
                "chart_focus": ["revenue", "gross_margin", "operating_income"],
            },
            "driver_snapshot": [
                {
                    "title": "驱动因素",
                    "summary": "有证据支撑的经营驱动。",
                    "source_ids": [],
                    "citation_status": "unverified",
                }
            ],
            "risk_snapshot": [
                {
                    "title": "风险",
                    "summary": "有证据支撑的风险。",
                    "source_ids": [],
                    "citation_status": "unverified",
                }
            ],
            "quality_of_quarter": {
                "growth_quality": None,
                "margin_quality": None,
                "cash_quality": None,
                "one_time_items": None,
            },
            "drivers_and_draggers": {"drivers": [], "draggers": []},
            "bull_bear_read": {
                "bull_case": [],
                "bear_case": [],
                "balanced_read": None,
            },
            "watch_next": [],
            "claims": [
                {
                    "text": "有证据支撑的判断。",
                    "source_ids": [],
                    "citation_status": "unverified",
                }
            ],
        }
    return {
        "company_profile": {
            "summary": "Concise investor-facing company profile.",
            "source_ids": [],
            "citation_status": "unverified",
        },
        "topline_verdict": {
            "headline": "Short evidence-bound earnings verdict.",
            "summary": "Three to five sentences on the latest earnings readout.",
            "verdict": "mixed",
            "confidence": "medium",
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
        "quality_of_quarter": {
            "growth_quality": None,
            "margin_quality": None,
            "cash_quality": None,
            "one_time_items": None,
        },
        "drivers_and_draggers": {"drivers": [], "draggers": []},
        "bull_bear_read": {
            "bull_case": [],
            "bear_case": [],
            "balanced_read": None,
        },
        "watch_next": [],
        "claims": [
            {
                "text": "Evidence-bound claim.",
                "source_ids": [],
                "citation_status": "unverified",
            }
        ],
    }


def _normalize_latest_earnings_payload(payload_data: dict[str, Any]) -> dict[str, Any]:
    normalized = _clean_mapping_keys(payload_data)
    company_profile = normalized.get("company_profile")
    if isinstance(company_profile, str):
        normalized["company_profile"] = {
            "summary": company_profile,
            "source_ids": [],
            "citation_status": "unverified",
        }
    elif isinstance(company_profile, dict):
        clean_profile = _clean_mapping_keys(company_profile)
        summary = clean_profile.get("summary") or (
            clean_profile.get("business_summary")
            or clean_profile.get("businessSummary")
            or clean_profile.get("description")
        )
        if summary:
            normalized["company_profile"] = {
                "summary": str(summary),
                "source_ids": _list_of_strings(clean_profile.get("source_ids")),
                "citation_status": str(clean_profile.get("citation_status") or "unverified"),
            }
        else:
            normalized["company_profile"] = None
    topline_verdict = normalized.get("topline_verdict")
    if isinstance(topline_verdict, str):
        normalized["topline_verdict"] = {
            "headline": topline_verdict[:120],
            "summary": topline_verdict,
            "verdict": "mixed",
        }
    elif isinstance(topline_verdict, dict):
        summary = str(topline_verdict.get("summary") or topline_verdict.get("text") or "")
        if summary and ("headline" not in topline_verdict or "verdict" not in topline_verdict):
            normalized["topline_verdict"] = {
                "headline": str(topline_verdict.get("headline") or summary[:120]),
                "summary": summary,
                "verdict": _earnings_verdict_from_text(
                    str(topline_verdict.get("verdict") or summary)
                ),
                "confidence": str(topline_verdict.get("confidence") or "medium"),
            }
    normalized["key_takeaways"] = _normalize_synthesized_points(normalized.get("key_takeaways", []))
    normalized["driver_snapshot"] = _normalize_synthesized_points(
        normalized.get("driver_snapshot", [])
    )
    normalized["risk_snapshot"] = _normalize_synthesized_points(normalized.get("risk_snapshot", []))
    normalized["claims"] = _normalize_synthesized_claims(normalized.get("claims", []))
    dashboard = normalized.get("financial_dashboard")
    if isinstance(dashboard, dict):
        normalized["financial_dashboard"] = {
            "metrics": _normalize_synthesized_metrics(dashboard.get("metrics", [])),
            "chart_focus": _list_of_strings(dashboard.get("chart_focus")),
        }
    normalized["quality_of_quarter"] = _normalize_quality_of_quarter(
        normalized.get("quality_of_quarter")
    )
    normalized["drivers_and_draggers"] = _normalize_drivers_and_draggers(
        normalized.get("drivers_and_draggers")
    )
    normalized["bull_bear_read"] = _normalize_bull_bear_read(normalized.get("bull_bear_read"))
    normalized["watch_next"] = _normalize_watch_next_items(normalized.get("watch_next", []))
    return _sanitize_payload_user_text(normalized)


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
            system_prompt=_system_prompt(request.language),
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
    backfill_excluded_points = _sanitize_business_driver_source_ids(
        payload,
        source_refs_by_id,
    )
    _backfill_business_driver_point_source_ids(
        payload,
        source_refs,
        backfill_excluded_points,
        request.language,
        source_refs_by_id,
    )
    task_sections = BusinessDriverSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        coverage=_business_driver_coverage(payload, source_refs),
        driver_thesis=payload.driver_thesis,
        driver_map=DriverMap(
            revenue_bridge=_optional_point_from_payload(
                payload.driver_map.revenue_bridge,
                source_refs_by_id,
            ),
            segment_momentum=_optional_point_from_payload(
                payload.driver_map.segment_momentum,
                source_refs_by_id,
            ),
            margin_and_mix=_optional_point_from_payload(
                payload.driver_map.margin_and_mix,
                source_refs_by_id,
            ),
            demand_signals=_optional_point_from_payload(
                payload.driver_map.demand_signals,
                source_refs_by_id,
            ),
        ),
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
    normalized = _clean_mapping_keys(payload_data)
    driver_thesis = normalized.get("driver_thesis")
    if isinstance(driver_thesis, str):
        normalized["driver_thesis"] = {
            "headline": driver_thesis[:120],
            "durability": "unclear",
            "summary": driver_thesis,
        }
    elif isinstance(driver_thesis, dict):
        driver_thesis = _clean_mapping_keys(driver_thesis)
        summary = str(driver_thesis.get("summary") or driver_thesis.get("text") or "")
        if summary and ("headline" not in driver_thesis or "durability" not in driver_thesis):
            normalized["driver_thesis"] = {
                "headline": str(driver_thesis.get("headline") or summary[:120]),
                "durability": _driver_durability_from_text(
                    str(driver_thesis.get("durability") or summary)
                ),
                "summary": summary,
            }
    driver_map = normalized.get("driver_map")
    if not isinstance(driver_map, dict):
        normalized["driver_map"] = _empty_driver_map()
    else:
        normalized["driver_map"] = _normalize_driver_map(driver_map)
    if not _has_complete_driver_thesis(normalized.get("driver_thesis")):
        normalized["driver_thesis"] = _driver_thesis_from_normalized_payload(normalized)
    normalized["claims"] = _normalize_synthesized_claims(normalized.get("claims", []))
    normalized.pop("positive_signals", None)
    normalized.pop("negative_signals", None)
    normalized.pop("watchlist", None)
    return _sanitize_payload_user_text(normalized)


def _empty_driver_map() -> dict[str, object | None]:
    return {
        "revenue_bridge": None,
        "segment_momentum": None,
        "margin_and_mix": None,
        "demand_signals": None,
    }


def _normalize_driver_map(driver_map: dict[str, object]) -> dict[str, object]:
    normalized = _empty_driver_map()
    for key, value in driver_map.items():
        clean_key = _clean_key(key).strip("_")
        if clean_key not in normalized:
            continue
        normalized[clean_key] = _normalize_synthesized_point_or_none(value)
    _fold_legacy_driver_lenses(driver_map, normalized)
    return normalized


def _normalize_synthesized_point_or_none(value: object) -> dict[str, Any] | None:
    if isinstance(value, list):
        points = _normalize_synthesized_points(value)
        return points[0] if points else None
    if value is None:
        return None
    points = _normalize_synthesized_points([value])
    return points[0] if points else None


def _fold_legacy_driver_lenses(
    driver_map: dict[str, object],
    normalized: dict[str, object | None],
) -> None:
    legacy_groups = {
        "revenue_bridge": ("product", "geography"),
        "segment_momentum": ("segment", "strategy"),
        "margin_and_mix": ("pricing",),
        "demand_signals": ("demand", "customer"),
    }
    for target_key, source_keys in legacy_groups.items():
        if normalized.get(target_key):
            continue
        for source_key in source_keys:
            legacy_value = driver_map.get(source_key)
            point = _normalize_synthesized_point_or_none(legacy_value)
            if point:
                normalized[target_key] = point
                break


def _has_complete_driver_thesis(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    return all(str(value.get(key) or "").strip() for key in ("headline", "durability", "summary"))


def _driver_thesis_from_normalized_payload(payload: dict[str, Any]) -> dict[str, str]:
    summary = ""
    headline = ""
    driver_map = payload.get("driver_map")
    if isinstance(driver_map, dict):
        for point in driver_map.values():
            if not isinstance(point, dict):
                continue
            summary = str(point.get("summary") or "").strip()
            headline = str(point.get("title") or "").strip()
            if summary:
                break
    if not summary:
        summary = (
            "Business driver evidence is available, but the model did not provide a "
            "complete driver thesis."
        )
        headline = "Business driver evidence is available"
    return {
        "headline": headline or _title_from_text(summary),
        "durability": _driver_durability_from_text(summary),
        "summary": summary,
    }


def _normalize_synthesized_points(value: object) -> object:
    if isinstance(value, str):
        return [
            {
                "title": _title_from_text(value),
                "summary": value,
                "source_ids": [],
                "citation_status": "unverified",
            }
        ]
    if isinstance(value, dict):
        point = _normalize_synthesized_point(value)
        return [point] if _has_point_summary(point) else []
    if not isinstance(value, list):
        return value
    normalized_points = [_normalize_synthesized_point(point) for point in value]
    return [point for point in normalized_points if _has_point_summary(point)]


def _normalize_synthesized_metrics(value: object) -> object:
    if isinstance(value, dict):
        return [
            _normalize_synthesized_metric({"name": key, "value": metric_value})
            for key, metric_value in value.items()
            if not _is_metric_object_metadata_key(key)
        ]
    if not isinstance(value, list):
        return value
    return [
        normalized_metric
        for metric in value
        for normalized_metric in [_normalize_synthesized_metric(metric)]
        if not _is_unsupported_placeholder_metric(normalized_metric)
    ]


def _normalize_quality_of_quarter(value: object) -> object:
    if not isinstance(value, dict):
        return None
    clean_value = _clean_mapping_keys(value)
    normalized: dict[str, object] = {}
    for key in ("growth_quality", "margin_quality", "cash_quality", "one_time_items"):
        normalized[key] = _normalize_optional_synthesized_point(clean_value.get(key))
    return normalized


def _normalize_drivers_and_draggers(value: object) -> object:
    if not isinstance(value, dict):
        return None
    clean_value = _clean_mapping_keys(value)
    return {
        "drivers": _ensure_point_list(clean_value.get("drivers", [])),
        "draggers": _ensure_point_list(clean_value.get("draggers", [])),
    }


def _normalize_bull_bear_read(value: object) -> object:
    if not isinstance(value, dict):
        return None
    clean_value = _clean_mapping_keys(value)
    return {
        "bull_case": _ensure_point_list(clean_value.get("bull_case", [])),
        "bear_case": _ensure_point_list(clean_value.get("bear_case", [])),
        "balanced_read": _normalize_optional_synthesized_point(clean_value.get("balanced_read")),
    }


def _normalize_watch_next_items(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        value = list(value.values())
    if not isinstance(value, list):
        return []
    normalized_items: list[dict[str, object]] = []
    for item in value:
        if isinstance(item, str):
            item = {"title": _title_from_text(item), "why_it_matters": item}
        if not isinstance(item, dict):
            continue
        clean_item = _clean_mapping_keys(item)
        title = str(clean_item.get("title") or clean_item.get("metric") or "Watch item")
        why_it_matters = str(
            clean_item.get("why_it_matters")
            or clean_item.get("summary")
            or clean_item.get("text")
            or clean_item.get("description")
            or ""
        ).strip()
        if not why_it_matters:
            why_it_matters = title
        normalized_items.append(
            {
                "title": title,
                "metric": _optional_str(clean_item.get("metric")),
                "why_it_matters": why_it_matters,
                "source_ids": _source_ids_from_value(clean_item),
                "citation_status": str(clean_item.get("citation_status") or "unverified"),
            }
        )
    return normalized_items


def _normalize_optional_synthesized_point(value: object) -> object:
    if value is None:
        return None
    normalized = _normalize_synthesized_point(value)
    return normalized if _has_point_summary(normalized) else None


def _ensure_point_list(value: object) -> list[object]:
    normalized = _normalize_synthesized_points(value)
    return normalized if isinstance(normalized, list) else []


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
    name = str(metric.get("name") or metric.get("metric") or metric.get("label") or "Metric")
    raw_value = metric.get("value")
    value = _normalize_metric_value_for_name(name, raw_value)
    period = metric.get("period")
    if not period and isinstance(raw_value, dict):
        period = raw_value.get("period") or raw_value.get("fact_period")
    return {
        "name": name,
        "value": str(value or "Not extracted"),
        "period": period,
        "interpretation": str(
            metric.get("interpretation") or metric.get("summary") or "Reported metric."
        ),
        "source_ids": _source_ids_from_value(metric),
        "citation_status": str(metric.get("citation_status") or "supported"),
    }


def _is_metric_object_metadata_key(key: object) -> bool:
    return _clean_key(key).strip("_") in {
        "source_id",
        "source_ids",
        "citation_status",
        "period",
        "interpretation",
        "summary",
        "evidence_refs",
    }


def _normalize_metric_value_for_name(metric_name: str, value: object) -> object:
    if isinstance(value, dict):
        clean_value = _clean_mapping_keys(value)
        raw_value = next(
            (
                clean_value[key]
                for key in ("value", "amount", "numeric_value")
                if key in clean_value
            ),
            None,
        )
        if raw_value is None:
            return value
        normalized_value = _normalize_metric_value_for_name(metric_name, raw_value)
        unit = str(clean_value.get("unit") or clean_value.get("currency") or "").strip()
        if unit == "%":
            formatted_value = _format_metric_display_value(normalized_value)
            return formatted_value if formatted_value.endswith("%") else f"{formatted_value}%"
        if unit.upper() in {"USD", "EUR", "GBP", "JPY", "CNY"}:
            if isinstance(normalized_value, int | float):
                return f"{_currency_symbol(unit)}{_compact_number(normalized_value)}"
            formatted_value = _format_metric_display_value(f"{normalized_value} {unit}")
            return formatted_value
        return _format_metric_display_value(normalized_value)
    if isinstance(value, int | float) and _metric_name_looks_like_ratio(metric_name):
        numeric_value = float(value)
        if -1 <= numeric_value <= 1:
            return f"{numeric_value * 100:.1f}%"
    return value


def _metric_name_looks_like_ratio(metric_name: str) -> bool:
    normalized = metric_name.strip().lower()
    ratio_markers = ("margin", "rate", "ratio", "yield", "roe", "roa")
    return any(marker in normalized for marker in ratio_markers)


def _normalize_synthesized_claims(value: object) -> object:
    if isinstance(value, dict):
        normalized_claim = _normalize_synthesized_claim(value)
        if normalized_claim:
            return [normalized_claim]
        return [
            normalized_claim
            for claim in value.values()
            if (normalized_claim := _normalize_synthesized_claim(claim))
        ]
    if not isinstance(value, list):
        normalized_claim = _normalize_synthesized_claim(value)
        return [normalized_claim] if normalized_claim else value
    return [
        normalized_claim
        for claim in value
        if (normalized_claim := _normalize_synthesized_claim(claim))
    ]


def _normalize_synthesized_claim(value: object) -> dict[str, object] | None:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        return {
            "text": text,
            "source_ids": [],
            "citation_status": "unverified",
        }
    if not isinstance(value, dict):
        return None
    text = str(
        value.get("text")
        or value.get("claim")
        or value.get("statement")
        or value.get("summary")
        or ""
    ).strip()
    if not text:
        return None
    return {
        "text": text,
        "source_ids": _source_ids_from_value(value),
        "citation_status": str(value.get("citation_status") or "supported"),
    }


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


def _sanitize_payload_user_text(value: object, *, key: str | None = None) -> object:
    if isinstance(value, dict):
        return {
            item_key: _sanitize_payload_user_text(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_sanitize_payload_user_text(item, key=key) for item in value]
    if isinstance(value, str) and key not in {
        "source_id",
        "source_ids",
        "node_id",
        "citation_status",
        "schema_version",
        "task_type",
    }:
        return _sanitize_user_text(value)
    return value


def _strip_noisy_business_driver_fragments(value: str) -> str:
    text = str(value or "")
    text = re.sub(r"\|[^。.!?]*?(?:---\|---|\|[^。.!?]*\|)", "", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()


def _is_noisy_business_driver_source_ref(source_ref: SourceRef) -> bool:
    return _is_noisy_business_driver_text(f"{source_ref.section} {source_ref.snippet}")


def _is_noisy_business_driver_text(value: str) -> bool:
    normalized = " ".join(str(value or "").split())
    if not normalized:
        return False
    lower_text = normalized.lower()
    if any(phrase in lower_text for phrase in _NOISY_BUSINESS_DRIVER_TEXT_PHRASES):
        return True
    pipe_count = normalized.count("|")
    if pipe_count >= 4 or "---|---" in normalized or re.search(r"\|\s*\|\s*\|", normalized):
        return True
    digits = sum(character.isdigit() for character in normalized)
    separators = sum(1 for character in normalized if character in "|,$%")
    return digits >= 12 and separators >= 5


def _sanitize_user_text(value: str) -> str:
    text = re.sub(r"\s*\((?:source[_ ]?id|node[_ ]?id)\s*[:=][^)]+\)", "", value, flags=re.I)
    text = re.sub(
        r"\b(?:source[_ ]?id|node[_ ]?id)\s*[:=]\s*[A-Za-z0-9_.:/-]+,?\s*",
        "",
        text,
        flags=re.I,
    )
    text = _rewrite_placeholder_availability_text(text)
    text = re.sub(r"\s{2,}", " ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip()


def _rewrite_placeholder_availability_text(value: str) -> str:
    text = value
    replacements = (
        (
            re.compile(
                r"\bdata was not available in the retrieved evidence\.?",
                flags=re.I,
            ),
            "coverage remains thin in the retrieved sources.",
        ),
        (
            re.compile(
                r"\b(?:was|were) not available in the retrieved evidence\.?",
                flags=re.I,
            ),
            "coverage remains thin in the retrieved sources.",
        ),
        (
            re.compile(
                r"\bnot available in the retrieved evidence\.?",
                flags=re.I,
            ),
            "coverage remains thin in the retrieved sources.",
        ),
    )
    for pattern, replacement in replacements:
        text = pattern.sub(replacement, text)
    return text


def _normalize_synthesized_point(point: object) -> object:
    if not isinstance(point, dict):
        summary = str(point).strip()
        return {
            "title": _title_from_text(summary),
            "summary": summary,
            "source_ids": [],
            "citation_status": "unverified",
        }
    point = _clean_mapping_keys(point)
    if "signal" in point:
        signal = str(point.get("signal") or "").strip()
        return {
            "title": signal or "Evidence signal",
            "summary": signal or "Evidence signal.",
            "source_ids": _source_ids_from_value(point),
            "citation_status": str(point.get("citation_status") or "unverified"),
        }
    text = (
        point.get("summary")
        or point.get("text")
        or point.get("snippet")
        or point.get("point")
        or point.get("description")
        or point.get("insight")
        or point.get("item")
        or point.get("assessment")
        or point.get("flag")
        or point.get("claim")
    )
    title = (
        point.get("title")
        or point.get("driver")
        or point.get("label")
        or point.get("claim")
        or _title_from_provider_point(point)
    )
    if not text and "value" in point:
        value = point.get("value")
        period = point.get("period")
        text = f"Value was {value}" + (f" for {period}." if period else ".")
    if (
        not text
        and not _has_supplemental_point_text(point)
        and {"strengths", "weaknesses", "investor_implication"}.intersection(point)
    ):
        text = "Capital allocation discipline."
    if not text:
        summary = _summary_from_provider_point(point, "")
        if not summary:
            return point
    else:
        summary = _summary_from_provider_point(point, str(text))
    return {
        "title": str(
            title
            or (
                "Capital allocation item"
                if "value" in point
                else _title_from_text(summary or str(text))
            )
        ),
        "summary": summary,
        "source_ids": _source_ids_from_value(point),
        "citation_status": str(point.get("citation_status") or "supported"),
    }


def _has_point_summary(point: object) -> bool:
    return isinstance(point, dict) and bool(str(point.get("summary") or "").strip())


def _latest_earnings_report_summary(
    summary: str,
    key_takeaways: list[EvidenceBoundPoint],
    driver_snapshot: list[EvidenceBoundPoint],
    risk_snapshot: list[EvidenceBoundPoint],
    dashboard_metrics: list[EvidenceBoundMetric],
) -> str:
    normalized = " ".join(str(summary or "").split())
    if len(normalized) >= 80:
        return normalized

    candidates: list[str] = []
    for point in [*key_takeaways, *driver_snapshot, *risk_snapshot]:
        if point.summary:
            candidates.append(f"{point.title}: {point.summary}")
    for metric in dashboard_metrics:
        if metric.interpretation:
            candidates.append(f"{metric.name}: {metric.interpretation}")

    rich_summary = " ".join(candidates)
    if len(rich_summary) < 80:
        return normalized or rich_summary
    return _trim_sentence(rich_summary, max_chars=520)


def _has_supplemental_point_text(point: dict[str, object]) -> bool:
    return any(
        str(point.get(key) or "").strip()
        for key in (
            "investor_relevance",
            "evidence_limit",
            "strengths",
            "weaknesses",
            "investor_implication",
        )
    )


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
            system_prompt=_system_prompt(request.language),
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
    _sanitize_cash_flow_source_ids(payload, source_refs_by_id)
    cash_metrics = _cash_metrics_with_fact_backfill(payload.cash_metrics, state)
    capital_allocation = _capital_allocation_with_fact_backfill(
        payload.capital_allocation,
        cash_metrics,
    )
    red_flags = _cash_flow_red_flags_with_backfill(payload.red_flags, cash_metrics)
    task_sections = CashFlowCapitalAllocationSections(
        schema_version="task_sections.v1",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        coverage=_cash_flow_coverage(payload, source_refs),
        cash_quality_verdict=payload.cash_quality_verdict,
        cash_metrics=[
            _metric_with_evidence_guardrail(metric, state, source_refs_by_id)
            for metric in cash_metrics
        ],
        capital_allocation=CapitalAllocation(
            capex=[
                _point_from_payload(point, source_refs_by_id) for point in capital_allocation.capex
            ],
            buybacks=[
                _point_from_payload(point, source_refs_by_id)
                for point in capital_allocation.buybacks
            ],
            dividends=[
                _point_from_payload(point, source_refs_by_id)
                for point in capital_allocation.dividends
            ],
            debt=[
                _point_from_payload(point, source_refs_by_id) for point in capital_allocation.debt
            ],
            liquidity=[
                _point_from_payload(point, source_refs_by_id)
                for point in capital_allocation.liquidity
            ],
        ),
        allocation_discipline=[
            _point_from_payload(point, source_refs_by_id) for point in payload.allocation_discipline
        ],
        red_flags=[_point_from_payload(point, source_refs_by_id) for point in red_flags],
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
    normalized = _clean_mapping_keys(payload_data)
    top_level_summary = str(normalized.pop("summary", "") or "").strip()
    verdict = normalized.get("cash_quality_verdict")
    if isinstance(verdict, str):
        normalized["cash_quality_verdict"] = {
            "headline": _complete_sentence_headline(verdict),
            "earnings_backed_by_cash": "unclear",
            "summary": verdict,
        }
    elif isinstance(verdict, dict):
        summary = str(verdict.get("summary") or verdict.get("text") or "")
        if summary and ("headline" not in verdict or "earnings_backed_by_cash" not in verdict):
            headline = str(verdict.get("headline") or summary)
            inferred_rating = _cash_quality_from_text(f"{headline} {summary}")
            normalized["cash_quality_verdict"] = {
                "headline": _complete_sentence_headline(headline),
                "earnings_backed_by_cash": _cash_quality_rating_with_text_guardrail(
                    str(
                        verdict.get("earnings_backed_by_cash") or verdict.get("rating") or "unclear"
                    ),
                    inferred_rating,
                ),
                "summary": summary,
            }
        elif not summary:
            normalized["cash_quality_verdict"] = {
                "headline": "Cash flow evidence is available",
                "earnings_backed_by_cash": "unclear",
                "summary": (
                    "Operating cash flow evidence is available, but the model did not "
                    "provide a complete cash quality verdict."
                ),
            }
        else:
            headline = str(verdict.get("headline") or summary)
            rating = str(verdict.get("earnings_backed_by_cash") or "unclear")
            inferred_rating = _cash_quality_from_text(f"{headline} {summary}")
            normalized["cash_quality_verdict"] = {
                **verdict,
                "headline": _complete_sentence_headline(headline),
                "earnings_backed_by_cash": _cash_quality_rating_with_text_guardrail(
                    rating,
                    inferred_rating,
                ),
                "summary": summary,
            }
    elif top_level_summary:
        normalized["cash_quality_verdict"] = {
            "headline": _complete_sentence_headline(top_level_summary),
            "earnings_backed_by_cash": _cash_quality_from_text(top_level_summary),
            "summary": top_level_summary,
        }
    cash_metrics = normalized.get("cash_metrics", [])
    normalized_cash_metrics = _normalize_synthesized_metrics(
        cash_metrics if isinstance(cash_metrics, list | dict) else []
    )
    if not isinstance(normalized_cash_metrics, list):
        normalized_cash_metrics = []
    cash_metric_points = _qualitative_cash_metric_points(normalized_cash_metrics)
    normalized["cash_metrics"] = [
        metric for metric in normalized_cash_metrics if not _is_qualitative_cash_metric(metric)
    ]
    capital_allocation = normalized.get("capital_allocation")
    if isinstance(capital_allocation, dict):
        normalized["capital_allocation"] = _normalize_capital_allocation(capital_allocation)
    else:
        normalized["capital_allocation"] = {
            "capex": [],
            "buybacks": [],
            "dividends": [],
            "debt": [],
            "liquidity": [],
        }
    discipline_points = _normalize_synthesized_points(normalized.get("allocation_discipline", []))
    if not isinstance(discipline_points, list):
        discipline_points = []
    normalized["allocation_discipline"] = [*cash_metric_points, *discipline_points]
    normalized["red_flags"] = _normalize_synthesized_points(normalized.get("red_flags", []))
    claims = normalized.get("claims", [])
    normalized["claims"] = _normalize_synthesized_claims(claims if isinstance(claims, list) else [])
    normalized = {
        key: normalized[key]
        for key in {
            "cash_quality_verdict",
            "cash_metrics",
            "capital_allocation",
            "allocation_discipline",
            "red_flags",
            "claims",
        }
        if key in normalized
    }
    return _sanitize_payload_user_text(normalized)


def _normalize_capital_allocation(value: dict[str, object]) -> dict[str, object]:
    normalized = {
        "capex": [],
        "buybacks": [],
        "dividends": [],
        "debt": [],
        "liquidity": [],
    }
    for key, item in value.items():
        clean_key = _clean_key(key).strip("_")
        if clean_key not in normalized:
            continue
        normalized[clean_key] = _normalize_synthesized_points(item)
    return normalized


def _qualitative_cash_metric_points(metrics: object) -> list[dict[str, object]]:
    if not isinstance(metrics, list):
        return []
    return [
        {
            "title": str(metric.get("name") or "Cash conversion quality"),
            "summary": str(metric.get("value") or metric.get("interpretation") or ""),
            "source_ids": _source_ids_from_value(metric),
            "citation_status": str(metric.get("citation_status") or "supported"),
        }
        for metric in metrics
        if _is_qualitative_cash_metric(metric)
    ]


def _is_qualitative_cash_metric(metric: object) -> bool:
    if not isinstance(metric, dict):
        return False
    name = _clean_key(metric.get("name") or "").strip("_").lower()
    return name in {"cash_conversion_quality", "cash_quality", "cash_flow_quality"}


def _quality_of_quarter_from_payload(
    value: _SynthesizedQualityOfQuarter | None,
    source_refs_by_id: dict[str, SourceRef],
) -> QualityOfQuarter | None:
    if value is None:
        return None
    return QualityOfQuarter(
        growth_quality=_optional_point_from_payload(
            value.growth_quality,
            source_refs_by_id,
        ),
        margin_quality=_optional_point_from_payload(
            value.margin_quality,
            source_refs_by_id,
        ),
        cash_quality=_optional_point_from_payload(
            value.cash_quality,
            source_refs_by_id,
        ),
        one_time_items=_optional_point_from_payload(
            value.one_time_items,
            source_refs_by_id,
        ),
    )


def _drivers_and_draggers_from_payload(
    value: _SynthesizedDriversAndDraggers | None,
    source_refs_by_id: dict[str, SourceRef],
) -> DriversAndDraggers | None:
    if value is None:
        return None
    return DriversAndDraggers(
        drivers=[_point_from_payload(point, source_refs_by_id) for point in value.drivers],
        draggers=[_point_from_payload(point, source_refs_by_id) for point in value.draggers],
    )


def _bull_bear_read_from_payload(
    value: _SynthesizedBullBearRead | None,
    source_refs_by_id: dict[str, SourceRef],
) -> BullBearRead | None:
    if value is None:
        return None
    return BullBearRead(
        bull_case=[_point_from_payload(point, source_refs_by_id) for point in value.bull_case],
        bear_case=[_point_from_payload(point, source_refs_by_id) for point in value.bear_case],
        balanced_read=_optional_point_from_payload(
            value.balanced_read,
            source_refs_by_id,
        ),
    )


def _watch_next_item_from_payload(
    item: _SynthesizedWatchNextItem,
    source_refs_by_id: dict[str, SourceRef],
) -> WatchNextItem:
    return WatchNextItem(
        title=item.title,
        metric=item.metric,
        why_it_matters=item.why_it_matters,
        evidence_refs=[
            _evidence_ref(source_refs_by_id[source_id]) for source_id in item.source_ids
        ],
        citation_status=item.citation_status,
    )


def _optional_point_from_payload(
    point: _SynthesizedPoint | None,
    source_refs_by_id: dict[str, SourceRef],
) -> EvidenceBoundPoint | None:
    if point is None:
        return None
    return _point_from_payload(point, source_refs_by_id)


def _latest_quality_with_backfill(
    quality: QualityOfQuarter | None,
    metrics: list[EvidenceBoundMetric],
    key_takeaways: list[EvidenceBoundPoint],
    source_refs: list[SourceRef],
) -> QualityOfQuarter | None:
    existing = quality or QualityOfQuarter()
    return QualityOfQuarter(
        growth_quality=existing.growth_quality
        or _quality_point_from_metric(
            "Growth quality",
            "Growth quality is anchored by the reported revenue evidence. Use this lens to judge whether the quarter is expanding from durable top-line demand rather than only narrative momentum.",
            _metric_by_name(metrics, ("revenue", "sales", "net sales")),
            key_takeaways,
            source_refs,
        ),
        margin_quality=existing.margin_quality
        or _quality_point_from_metric(
            "Margin quality",
            "Margin quality is anchored by the available margin or operating income evidence. Use this lens to judge whether revenue is converting into operating leverage.",
            _metric_by_name(metrics, ("margin", "operating income", "gross profit")),
            key_takeaways,
            source_refs,
        ),
        cash_quality=existing.cash_quality
        or _quality_point_from_metric(
            "Cash quality",
            "Cash quality is anchored by operating cash flow or free cash flow evidence. Use this lens to judge whether accounting earnings are supported by cash generation.",
            _metric_by_name(metrics, ("cash flow", "free cash flow", "operating cash")),
            key_takeaways,
            source_refs,
        ),
        one_time_items=existing.one_time_items,
    )


def _latest_drivers_with_backfill(
    drivers_and_draggers: DriversAndDraggers | None,
    driver_snapshot: list[EvidenceBoundPoint],
    risk_snapshot: list[EvidenceBoundPoint],
) -> DriversAndDraggers | None:
    existing = drivers_and_draggers or DriversAndDraggers()
    drivers = existing.drivers or driver_snapshot[:3]
    draggers = existing.draggers or risk_snapshot[:3]
    if not drivers and not draggers:
        return None
    return DriversAndDraggers(drivers=drivers, draggers=draggers)


def _latest_bull_bear_with_backfill(
    bull_bear_read: BullBearRead | None,
    topline: ToplineVerdict,
    key_takeaways: list[EvidenceBoundPoint],
    driver_snapshot: list[EvidenceBoundPoint],
    risk_snapshot: list[EvidenceBoundPoint],
    source_refs: list[SourceRef],
) -> BullBearRead | None:
    existing = bull_bear_read or BullBearRead()
    bull_case = (
        existing.bull_case
        or _scenario_points_or_backfill(
            [*driver_snapshot, *key_takeaways],
            "Bull case",
            "Constructive read",
            (
                "The constructive case is based on the supported revenue and "
                "operating driver evidence. "
                "It remains a scenario, not a price target or trading recommendation."
            ),
            source_refs,
        )[:2]
    )
    bear_case = (
        existing.bear_case
        or _scenario_points_or_backfill(
            risk_snapshot,
            "Bear case",
            "Cautious read",
            (
                "The cautious case is based on the supported risk or pressure evidence. "
                "It keeps the final read balanced until follow-up metrics improve."
            ),
            source_refs,
        )[:2]
    )
    balanced_read = existing.balanced_read or _point_from_source_refs(
        "Balanced read",
        (
            f"The reported quarter screens as {topline.verdict} with "
            f"{topline.confidence} confidence. {topline.summary}"
        ),
        source_refs,
    )
    if not bull_case and not bear_case and balanced_read is None:
        return None
    return BullBearRead(
        bull_case=bull_case,
        bear_case=bear_case,
        balanced_read=balanced_read,
    )


def _scenario_points_or_backfill(
    points: list[EvidenceBoundPoint],
    title_prefix: str,
    summary_prefix: str,
    fallback_summary: str,
    source_refs: list[SourceRef],
) -> list[EvidenceBoundPoint]:
    if not points:
        point = _point_from_source_refs(title_prefix, fallback_summary, source_refs)
        return [point] if point is not None else []
    return [
        EvidenceBoundPoint(
            title=f"{title_prefix}: {point.title}",
            summary=f"{summary_prefix}: {point.summary}",
            evidence_refs=point.evidence_refs,
            citation_status=point.citation_status,
        )
        for point in points
    ]


def _latest_watch_next_with_backfill(
    watch_next: list[WatchNextItem],
    metrics: list[EvidenceBoundMetric],
    risk_snapshot: list[EvidenceBoundPoint],
    source_refs: list[SourceRef],
) -> list[WatchNextItem]:
    if watch_next:
        return watch_next
    metric_items = [
        WatchNextItem(
            title=f"Watch {metric.name}",
            metric=metric.name,
            why_it_matters=(
                f"{metric.name} is already part of the latest-quarter evidence; "
                "the next report should show whether this signal improves, fades, or reverses."
            ),
            evidence_refs=metric.evidence_refs,
            citation_status=metric.citation_status,
        )
        for metric in metrics[:3]
    ]
    if metric_items:
        return metric_items
    return [
        WatchNextItem(
            title=f"Watch {point.title}",
            metric=None,
            why_it_matters=point.summary,
            evidence_refs=point.evidence_refs,
            citation_status=point.citation_status,
        )
        for point in risk_snapshot[:3]
    ] or [
        WatchNextItem(
            title="Watch next filing evidence",
            metric=None,
            why_it_matters=(
                "The next filing should confirm whether the current earnings read is "
                "supported by fresh KPI, driver, and risk evidence."
            ),
            evidence_refs=[_evidence_ref(source_refs[0])] if source_refs else [],
            citation_status=source_refs[0].citation_status
            if source_refs
            else CitationStatus.UNVERIFIED,
        )
    ]


def _quality_point_from_metric(
    title: str,
    fallback_summary: str,
    metric: EvidenceBoundMetric | None,
    key_takeaways: list[EvidenceBoundPoint],
    source_refs: list[SourceRef],
) -> EvidenceBoundPoint | None:
    if metric is not None:
        return EvidenceBoundPoint(
            title=title,
            summary=(
                f"{metric.name} of {metric.value} is the evidence anchor. {metric.interpretation}"
            ),
            evidence_refs=metric.evidence_refs,
            citation_status=metric.citation_status,
        )
    if key_takeaways:
        point = key_takeaways[0]
        return EvidenceBoundPoint(
            title=title,
            summary=f"{fallback_summary} Supporting context: {point.summary}",
            evidence_refs=point.evidence_refs,
            citation_status=point.citation_status,
        )
    return _point_from_source_refs(title, fallback_summary, source_refs)


def _metric_by_name(
    metrics: list[EvidenceBoundMetric],
    needles: tuple[str, ...],
) -> EvidenceBoundMetric | None:
    for metric in metrics:
        normalized = _normalize_metric_name(metric.name)
        if any(needle in normalized for needle in needles):
            return metric
    return metrics[0] if metrics else None


def _points_or_backfill(
    points: list[EvidenceBoundPoint],
    title: str,
    summary: str,
    source_refs: list[SourceRef],
) -> list[EvidenceBoundPoint]:
    return points or (
        [point] if (point := _point_from_source_refs(title, summary, source_refs)) else []
    )


def _point_from_source_refs(
    title: str,
    summary: str,
    source_refs: list[SourceRef],
) -> EvidenceBoundPoint | None:
    if not source_refs:
        return EvidenceBoundPoint(
            title=title,
            summary=summary,
            evidence_refs=[],
            citation_status=CitationStatus.UNVERIFIED,
        )
    return EvidenceBoundPoint(
        title=title,
        summary=summary,
        evidence_refs=[_evidence_ref(source_refs[0])],
        citation_status=source_refs[0].citation_status,
    )


def _normalize_watchlist(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if isinstance(item, dict):
            clean_item = _clean_mapping_keys(item)
            text = clean_item.get("item") or clean_item.get("summary") or clean_item.get("text")
            if text:
                normalized.append(str(text))
            continue
        if str(item):
            normalized.append(str(item))
    return normalized


def _cash_metrics_with_fact_backfill(
    metrics: list[_SynthesizedMetric],
    state: AgentState,
) -> list[_SynthesizedMetric]:
    usable_metrics = [metric for metric in metrics if not _cash_metric_needs_fact_backfill(metric)]
    synthesized_metrics = []
    for record in state.evidence_memory.metric_evidence:
        if not _has_fact_value(record):
            continue
        name = str(record.get("metric") or record.get("normalized_metric") or "").strip()
        if not name:
            continue
        synthesized_metrics.append(
            _SynthesizedMetric(
                name=name.title(),
                value=_metric_evidence_value(record),
                period=_metric_evidence_period(record),
                interpretation=(
                    f"{name.title()} was reported in SEC companyfacts and used as "
                    "the cash-flow KPI anchor."
                ),
                source_ids=_source_ids_from_value(record),
                citation_status=CitationStatus.SUPPORTED,
            )
        )
    source_id = _first_source_id(state)
    for record in _facts_metric_records(state):
        name = str(record.get("name") or "").strip()
        if not name or record.get("value") is None:
            continue
        synthesized_metrics.append(
            _SynthesizedMetric(
                name=name.title(),
                value=_metric_evidence_value(record),
                period=_metric_evidence_period(record),
                interpretation=(
                    f"{name.title()} was reported in structured financial facts and used as "
                    "the cash-flow KPI anchor."
                ),
                source_ids=[source_id] if source_id else [],
                citation_status=CitationStatus.SUPPORTED
                if source_id
                else CitationStatus.UNVERIFIED,
            )
        )
    merged_metrics = [*synthesized_metrics, *usable_metrics]
    return _dedupe_cash_metrics(merged_metrics)[:7]


def _dedupe_cash_metrics(metrics: list[_SynthesizedMetric]) -> list[_SynthesizedMetric]:
    deduped: list[_SynthesizedMetric] = []
    seen: set[str] = set()
    for metric in metrics:
        normalized_name = _normalize_metric_name(metric.name)
        if normalized_name in seen:
            continue
        seen.add(normalized_name)
        deduped.append(metric)
    return deduped


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _cash_metric_needs_fact_backfill(metric: _SynthesizedMetric) -> bool:
    normalized_name = metric.name.strip().lower()
    return normalized_name in {"metric", "cash metric", "kpi"} or _metric_value_needs_evidence(
        metric.value,
        metric.interpretation,
    )


def _capital_allocation_with_fact_backfill(
    capital_allocation: _SynthesizedCapitalAllocation,
    metrics: list[_SynthesizedMetric],
) -> _SynthesizedCapitalAllocation:
    if not metrics:
        return _SynthesizedCapitalAllocation()
    capex_metric = _synthesized_metric_by_name(metrics, ("capital expenditures", "capex"))
    debt_metric = _synthesized_metric_by_name(metrics, ("total debt", "debt"))
    current_ratio_metric = _synthesized_metric_by_name(metrics, ("current ratio",))
    cash_metric = _synthesized_metric_by_name(
        metrics,
        ("cash and short term investments", "cash and equivalents"),
    )
    capex = list(capital_allocation.capex) if capex_metric is not None else []
    debt = list(capital_allocation.debt) if debt_metric is not None else []
    liquidity = (
        list(capital_allocation.liquidity)
        if current_ratio_metric is not None or cash_metric is not None
        else []
    )
    if not capex and capex_metric is not None:
        capex.append(
            _cash_flow_point_from_metric(
                capex_metric,
                title="Capex and reinvestment",
                summary=(
                    f"{capex_metric.name} of {capex_metric.value} is the main "
                    "reinvestment use of cash."
                ),
            )
        )
    if not debt and debt_metric is not None:
        debt.append(
            _cash_flow_point_from_metric(
                debt_metric,
                title="Debt load",
                summary=(
                    f"{debt_metric.name} of {debt_metric.value} frames balance sheet "
                    "risk against cash generation."
                ),
            )
        )
    if not liquidity:
        liquidity_parts = []
        source_ids: list[str] = []
        citation_status = CitationStatus.UNVERIFIED
        if current_ratio_metric is not None:
            liquidity_parts.append(f"current ratio of {current_ratio_metric.value}")
            source_ids.extend(current_ratio_metric.source_ids)
            citation_status = current_ratio_metric.citation_status
        if cash_metric is not None:
            liquidity_parts.append(f"cash and short-term investments of {cash_metric.value}")
            source_ids.extend(cash_metric.source_ids)
            citation_status = cash_metric.citation_status
        if liquidity_parts:
            liquidity.append(
                _SynthesizedPoint(
                    title="Balance sheet resilience",
                    summary=(
                        "Liquidity is anchored by "
                        + " and ".join(liquidity_parts)
                        + ", which determines how much room management has to fund reinvestment."
                    ),
                    source_ids=_dedupe_strings(source_ids),
                    citation_status=citation_status,
                )
            )
    if not any([capex, debt, liquidity, capital_allocation.buybacks, capital_allocation.dividends]):
        metric = metrics[0]
        liquidity.append(
            _cash_flow_point_from_metric(
                metric,
                title="Cash flow anchor",
                summary=(
                    f"{metric.name} of {metric.value} is the core allocation capacity signal."
                ),
            )
        )
    return _SynthesizedCapitalAllocation(
        capex=capex,
        buybacks=capital_allocation.buybacks,
        dividends=capital_allocation.dividends,
        debt=debt,
        liquidity=liquidity,
    )


def _cash_flow_red_flags_with_backfill(
    red_flags: list[_SynthesizedPoint],
    metrics: list[_SynthesizedMetric],
) -> list[_SynthesizedPoint]:
    if red_flags:
        return red_flags
    ocf = _synthesized_metric_by_name(metrics, ("operating cash flow",))
    fcf = _synthesized_metric_by_name(metrics, ("free cash flow",))
    capex = _synthesized_metric_by_name(metrics, ("capital expenditures", "capex"))
    current_ratio = _synthesized_metric_by_name(metrics, ("current ratio",))
    anchor = fcf or ocf or capex or current_ratio
    if anchor is None:
        return []
    watch_items = []
    if fcf is not None and capex is not None:
        watch_items.append(f"whether {fcf.name.lower()} stays above capex after reinvestment")
    elif ocf is not None and capex is not None:
        watch_items.append(
            f"whether {ocf.name.lower()} continues to fund capex without balance sheet strain"
        )
    elif current_ratio is not None:
        watch_items.append(
            f"whether liquidity remains stable around a current ratio of {current_ratio.value}"
        )
    else:
        watch_items.append(f"whether {anchor.name.lower()} remains durable next quarter")
    return [
        _SynthesizedPoint(
            title="Watch next cash signal",
            summary=(
                "Watch " + watch_items[0] + "; a deterioration would change the cash quality read."
            ),
            source_ids=anchor.source_ids,
            citation_status=anchor.citation_status,
        )
    ]


def _synthesized_metric_by_name(
    metrics: list[_SynthesizedMetric],
    needles: tuple[str, ...],
) -> _SynthesizedMetric | None:
    for metric in metrics:
        normalized_name = _normalize_metric_name(metric.name)
        if any(needle in normalized_name for needle in needles):
            return metric
    return None


def _cash_flow_point_from_metric(
    metric: _SynthesizedMetric,
    *,
    title: str,
    summary: str,
) -> _SynthesizedPoint:
    return _SynthesizedPoint(
        title=title,
        summary=summary,
        source_ids=metric.source_ids,
        citation_status=metric.citation_status,
    )


def _facts_metric_records(state: AgentState) -> list[dict[str, Any]]:
    return cash_flow_metric_records_from_facts(state.evidence_memory.facts)


def _first_source_id(state: AgentState) -> str:
    for source_ref in state.evidence_memory.source_refs:
        source_id = source_ref.get("source_id")
        if source_id:
            return str(source_id)
    return ""


def _summary_from_provider_point(point: dict[str, object], text: str) -> str:
    parts = [text]
    investor_relevance = point.get("investor_relevance")
    evidence_limit = point.get("evidence_limit")
    strengths = point.get("strengths")
    weaknesses = point.get("weaknesses")
    investor_implication = point.get("investor_implication")
    if investor_relevance:
        parts.append(f"Investor relevance: {investor_relevance}")
    if evidence_limit:
        parts.append(f"Evidence limit: {evidence_limit}")
    if strengths:
        parts.append(f"Strengths: {strengths}")
    if weaknesses:
        parts.append(f"Weaknesses: {weaknesses}")
    if investor_implication:
        parts.append(f"Investor implication: {investor_implication}")
    return " ".join(str(part).strip() for part in parts if str(part).strip())


def _clean_mapping_keys(value: dict[str, Any]) -> dict[str, Any]:
    return {_clean_key(key): item for key, item in value.items()}


def _clean_key(value: object) -> str:
    normalized = " ".join(str(value).strip().strip(".:").split())
    normalized = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", normalized)
    return normalized.replace(" ", "_").lower()


def _title_from_provider_point(point: dict[str, object]) -> str | None:
    if {"strengths", "weaknesses", "investor_implication"}.intersection(point):
        return "Allocation discipline"
    if "item" in point:
        return "Capex"
    if "assessment" in point:
        return "Allocation discipline"
    if "flag" in point:
        return "Red flag"
    return None


def _title_from_text(value: str, *, max_words: int = 5) -> str:
    words = re.findall(r"[A-Za-z0-9$%]+(?:[-'][A-Za-z0-9$%]+)?", value)
    if not words:
        return "Analytical point"
    return " ".join(words[:max_words]).capitalize()


def _earnings_verdict_from_text(value: str) -> str:
    normalized = value.lower()
    if "negative" in normalized or "bearish" in normalized or "pressure" in normalized:
        return "negative"
    if "positive" in normalized or "strong" in normalized or "grew" in normalized:
        if "mixed" not in normalized and "but" not in normalized:
            return "positive"
    return "mixed"


def _cash_quality_from_text(value: str) -> str:
    normalized = value.lower()
    if re.search(r"\b(unassessable|not assessable|insufficient|missing evidence)\b", normalized):
        return "no"
    if re.search(r"\b(weak|weakness|deteriorat(?:e|ed|ing)|unfunded)\b", normalized):
        return "no"
    if (
        "mixed" in normalized
        or "caveat" in normalized
        or "but" in normalized
        or "not pristine" in normalized
        or "strained" in normalized
        or "strain" in normalized
        or "pressure" in normalized
        or "volatile" in normalized
    ):
        return "mixed"
    if "high_quality" in normalized:
        return "yes"
    if re.search(
        r"\b(yes|strong|exceptional|positive|funded|supports?|backed|covered|solid)\b",
        normalized,
    ):
        return "yes"
    return "unclear"


def _cash_quality_rating_with_text_guardrail(rating: str, inferred_rating: str) -> str:
    normalized_rating = rating if rating in {"yes", "mixed", "no", "unclear"} else "unclear"
    if inferred_rating == "unclear":
        return normalized_rating
    if normalized_rating == "unclear":
        return inferred_rating
    if normalized_rating != inferred_rating:
        return inferred_rating
    return normalized_rating


def _complete_sentence_headline(value: str, *, max_chars: int = 120) -> str:
    text = " ".join(str(value or "").split())
    first_sentence = re.match(r"^(.+?[.!?])\s+(?=[A-Z])", text)
    if first_sentence:
        return first_sentence.group(1)
    if len(text) <= max_chars:
        return text
    sentence_boundaries = [
        match.end(1) for match in re.finditer(r"(.+?[.!?])\s+(?=[A-Z])", text[: max_chars + 1])
    ]
    if sentence_boundaries:
        return text[: sentence_boundaries[-1]]
    return text[:max_chars].rstrip(" ,;:-") + "."


def _driver_durability_from_text(value: str) -> str:
    normalized = value.lower()
    if "temporary" in normalized or "transient" in normalized:
        return "temporary"
    if "mixed" in normalized:
        return "mixed"
    if (
        "durable" in normalized
        or "structural" in normalized
        or "platform" in normalized
        or "installed base" in normalized
        or "engagement" in normalized
    ):
        return "durable"
    return "unclear"


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
            system_prompt=_company_profile_system_prompt(request.language),
            user_prompt=_company_profile_user_prompt(state, business_summary, request.language),
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


def _system_prompt(language: str = "en") -> str:
    if _is_zh_locale(language):
        return (
            "你是一名金融研究报告综合器。只返回一个 JSON 对象。"
            "只能使用提供的证据。不要展示思维链。"
            "每个字段都必须严格匹配请求的 JSON schema。"
        )
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


def _company_profile_system_prompt(language: str = "en") -> str:
    if _is_zh_locale(language):
        return (
            "你撰写面向投资者的简洁公司画像。只返回一个 JSON 对象。"
            "只能使用提供的公司事实。不要展示思维链。"
        )
    return (
        "You write concise investor-facing company profiles. Return one JSON object only. "
        "Use only the provided company facts. Do not include chain-of-thought."
    )


def _company_profile_user_prompt(
    state: AgentState,
    business_summary: str,
    language: str = "en",
) -> str:
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
    if _is_zh_locale(language):
        return (
            "请用 1-2 句话写一段面向投资者的公司画像。\n"
            "只使用已提供的公司事实。\n"
            "在信息可用时，说明业务身份、核心产品和主要市场。\n"
            "不要写创始历史、总部、零售渠道，也不要展开成完整产品清单。\n"
            '只返回 JSON: {"summary": "..."}。\n'
            f"Ticker: {state.ticker}\n"
            f"Facts: {_json_safe(facts)}\n"
            f"Business summary: {business_summary}"
        )
    return (
        "Write a 1-2 sentence investor-facing company profile.\n"
        "Use only the provided company facts.\n"
        "When available, mention the business identity, core products, and primary markets.\n"
        "Do not include founding history, headquarters, retail channels, or exhaustive product lists.\n"
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
    evidence_refs = _aliased_source_refs(_limit_source_refs(source_refs))
    evidence_lines = _evidence_lines(evidence_refs, source_refs)
    allowed_source_ids = [source_ref.source_id for source_ref in evidence_refs]
    if _is_zh_locale(request.language):
        return (
            "请生成业务驱动深挖所需的 typed task sections。\n"
            "只返回 JSON。凡是需要对象或数组的位置，不要用字符串代替。\n"
            f"Allowed source_ids: {_json_safe(allowed_source_ids)}.\n"
            "不要编造 source_ids。不要引用上面未列出的事实、概念或 node id。\n"
            "请严格使用以下结构：\n"
            "{\n"
            '  "driver_thesis": {"headline": "...", "durability": '
            '"durable|mixed|temporary|unclear", "summary": "..."},\n'
            '  "driver_map": {\n'
            '    "revenue_bridge": {"title": "...", "summary": "...", '
            '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"},\n'
            '    "segment_momentum": {"title": "...", "summary": "...", '
            '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"},\n'
            '    "margin_and_mix": {"title": "...", "summary": "...", '
            '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"},\n'
            '    "demand_signals": {"title": "...", "summary": "...", '
            '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}\n'
            "  },\n"
            '  "claims": [{"text": "...", "source_ids": ["..."], '
            '"citation_status": "supported|partial|missing|unverified"}]\n'
            "}\n"
            "driver_map 的四个字段都是单个段落 point，不要返回数组。"
            "每段 summary 写 3-5 句，说明结论、证据、投资含义和证据限制。\n"
            "所有 source_ids 都必须来自已提供的证据。\n"
            "如果证据稀薄，也要保持同样的对象/数组结构，但文案要谨慎。\n"
            "四段分别回答 revenue bridge、segment momentum、margin and mix、demand signals。"
            "SEC filing、company facts、market data 和已收集第三方来源都可以作为补充证据，"
            "但必须使用 allowed source_ids。监管、法律或市场风险只能作为反证写入相关段落。\n"
            f"Ticker: {state.ticker}\n"
            f"Task: {request.task_type.value}\n"
            f"Business signals: {_json_safe(state.evidence_memory.business_signals)}\n"
            f"Coverage: status={state.coverage.status}; "
            f"evidence_count={state.coverage.evidence_count}; "
            f"citation_coverage={state.coverage.citation_coverage}\n"
            "Evidence:\n" + "\n".join(evidence_lines)
        )
    return (
        "Generate typed task sections for business driver deep dive.\n"
        "Return JSON only. Do not use strings where objects or arrays are required.\n"
        f"Allowed source_ids: {_json_safe(allowed_source_ids)}.\n"
        "Do not invent source_ids. Do not reference facts, concepts, or node ids that are not listed above.\n"
        "Use this structure exactly:\n"
        "{\n"
        '  "driver_thesis": {"headline": "...", "durability": '
        '"durable|mixed|temporary|unclear", "summary": "..."},\n'
        '  "driver_map": {\n'
        '    "revenue_bridge": {"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"},\n'
        '    "segment_momentum": {"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"},\n'
        '    "margin_and_mix": {"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"},\n'
        '    "demand_signals": {"title": "...", "summary": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}\n'
        "  },\n"
        '  "claims": [{"text": "...", "source_ids": ["..."], '
        '"citation_status": "supported|partial|missing|unverified"}]\n'
        "}\n"
        "Each driver_map field is one paragraph point, not an array. Each summary should "
        "be 3-5 sentences covering conclusion, evidence, investor relevance, and evidence limits.\n"
        "All source_ids must come from the evidence provided.\n"
        "If evidence is sparse, keep the same object and array structure, but stay cautious in the wording.\n"
        "The four paragraphs must cover revenue bridge, segment momentum, margin and mix, "
        "and demand signals. SEC filing, company facts, market data, and collected third-party "
        "sources may all supplement the analysis, but every cited fact must use an allowed source_id. "
        "Regulatory, legal, or market-risk evidence should be used only as counter-evidence inside the relevant paragraph.\n"
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
    evidence_refs = _aliased_source_refs(_limit_source_refs(source_refs))
    evidence_lines = _evidence_lines(evidence_refs, source_refs)
    allowed_source_ids = [source_ref.source_id for source_ref in evidence_refs]
    if _is_zh_locale(request.language):
        return (
            "请生成现金流与资本配置所需的 typed task sections。\n"
            "只返回 JSON。凡是需要对象或数组的位置，不要用字符串代替。\n"
            f"Allowed source_ids: {_json_safe(allowed_source_ids)}.\n"
            "不要编造 source_ids。不要引用上面未列出的事实、概念或 node id。\n"
            "请严格使用以下结构：\n"
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
            "capital_allocation 的每个分类都必须是 point 数组，每个 point 包含 title、summary、source_ids 和 citation_status。\n"
            "所有 source_ids 都必须来自已提供的证据。\n"
            "如果证据稀薄，也要保持同样的对象/数组结构，但文案要谨慎。\n"
            "当证据里出现相关内容时，要优先把经营现金流、资本开支、回购、分红、债务和流动性拆成独立的 capital_allocation 分类。\n"
            "不要把所有资本回报相关证据都合并成 liquidity。\n"
            f"Ticker: {state.ticker}\n"
            f"Task: {request.task_type.value}\n"
            f"Facts: {_json_safe(state.evidence_memory.facts)}\n"
            f"Metric evidence: {_json_safe(state.evidence_memory.metric_evidence)}\n"
            f"Coverage: status={state.coverage.status}; "
            f"evidence_count={state.coverage.evidence_count}; "
            f"citation_coverage={state.coverage.citation_coverage}\n"
            "Evidence:\n" + "\n".join(evidence_lines)
        )
    return (
        "Generate typed task sections for cash flow and capital allocation.\n"
        "Return JSON only. Do not use strings where objects or arrays are required.\n"
        f"Allowed source_ids: {_json_safe(allowed_source_ids)}.\n"
        "Do not invent source_ids. Do not reference facts, concepts, or node ids that are not listed above.\n"
        "Use this structure exactly:\n"
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
        "Each capital_allocation category must be a point array, and each point must include title, summary, source_ids, and citation_status.\n"
        "All source_ids must come from the evidence provided.\n"
        "If evidence is sparse, keep the same object and array structure, but stay cautious in the wording.\n"
        "When relevant evidence exists, split operating cash flow, capex, buybacks, dividends, debt, and liquidity into separate capital_allocation categories.\n"
        "Do not merge every capital return signal into liquidity.\n"
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
    evidence_refs = _aliased_source_refs(_limit_source_refs(source_refs))
    evidence_lines = _evidence_lines(evidence_refs, source_refs)
    allowed_source_ids = [source_ref.source_id for source_ref in evidence_refs]
    facts = state.evidence_memory.facts
    if _is_zh_locale(request.language):
        return (
            "请生成最新财报分析所需的 typed JSON。\n"
            "只返回 evidence-dense JSON。凡是需要对象或数组的位置，不要用字符串代替。\n"
            f"Allowed source_ids: {_json_safe(allowed_source_ids)}.\n"
            "不要编造 source_ids。不要引用上面未列出的事实、概念或 node id。\n"
            "请严格使用以下结构：\n"
            "{\n"
            '  "company_profile": {"summary": "...", "source_ids": ["..."], '
            '"citation_status": "supported|partial|missing|unverified"},\n'
            '  "topline_verdict": {"headline": "...", "summary": "...", '
            '"verdict": "positive|mixed|negative", "confidence": "high|medium|low"},\n'
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
            '  "quality_of_quarter": {"growth_quality": null, "margin_quality": null, '
            '"cash_quality": null, "one_time_items": null},\n'
            '  "drivers_and_draggers": {"drivers": [], "draggers": []},\n'
            '  "bull_bear_read": {"bull_case": [], "bear_case": [], "balanced_read": null},\n'
            '  "watch_next": [{"title": "...", "metric": "...", "why_it_matters": "...", '
            '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}],\n'
            '  "claims": [{"text": "...", "source_ids": ["..."], '
            '"citation_status": "supported|partial|missing|unverified"}]\n'
            "}\n"
            "company_profile 在可用时必须使用 Facts.business_summary、businessSummary、market_business_summary、marketBusinessSummary 或 description。\n"
            "如果不存在这类 profile 事实，就把 company_profile 设为 null；不要从 filing snippet 或 risk-factor evidence 里硬拼公司画像。\n"
            "每个 profile、point、metric 和 claim 都只能使用已提供证据中的 source_ids。\n"
            "如果证据稀薄，也要保持同样的对象/数组结构，但文案要谨慎。\n"
            "当证据稀薄时，请用保守措辞。\n"
            "topline_verdict.summary 必须是 3-5 句，覆盖方向、核心数字、驱动和疑点。\n"
            "每个可见 point 的 summary 使用 2-4 句，避免一句话 item。\n"
            "successful report 尽量包含 3-6 个 KPI metrics、3-5 个变化点、2-4 个 drivers、1-3 个 draggers、2 个 bull_case、2 个 bear_case 和 3 个 watch_next。\n"
            "financial_dashboard.metrics 尽量使用 Metric evidence 里的数值。KPI 数值优先采用 SEC companyfacts 的 metric value，而不是 table snippet。\n"
            "如果 Metric evidence 已经包含数值和单位，不要说这个 metric 没有被提取。\n"
            "在 latest earnings 中，优先关注 revenue、gross margin、operating income、net income、EPS、operating cash flow、free cash flow 和 capex。\n"
            "把经营结果证据放进 topline_verdict、key_takeaways、financial_dashboard 和 driver_snapshot。\n"
            "把季度质量证据放进 quality_of_quarter；把正向驱动和拖累因素拆进 drivers_and_draggers。\n"
            "bull_bear_read 必须保持平衡，不要输出目标价、买卖建议或交易指令。\n"
            "watch_next 必须说明下一季要观察的 metric 或 filing clue。\n"
            "风险披露证据默认只放进 risk_snapshot，除非完全没有经营结果证据。\n"
            f"Ticker: {state.ticker}\n"
            f"Task: {request.task_type.value}\n"
            f"Facts: {_json_safe(facts)}\n"
            f"Metric evidence: {_json_safe(state.evidence_memory.metric_evidence)}\n"
            f"Coverage: status={state.coverage.status}; "
            f"evidence_count={state.coverage.evidence_count}; "
            f"citation_coverage={state.coverage.citation_coverage}\n"
            "Evidence:\n" + "\n".join(evidence_lines)
        )
    return (
        "Generate typed JSON for the latest earnings task sections.\n"
        "Return evidence-dense JSON only. Do not use strings where objects or arrays are required.\n"
        f"Allowed source_ids: {_json_safe(allowed_source_ids)}.\n"
        "Do not invent source_ids. Do not reference facts, concepts, or node ids that are not listed above.\n"
        "Use this structure exactly:\n"
        "{\n"
        '  "company_profile": {"summary": "...", "source_ids": ["..."], '
        '"citation_status": "supported|partial|missing|unverified"},\n'
        '  "topline_verdict": {"headline": "...", "summary": "...", '
        '"verdict": "positive|mixed|negative", "confidence": "high|medium|low"},\n'
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
        '  "quality_of_quarter": {"growth_quality": null, "margin_quality": null, '
        '"cash_quality": null, "one_time_items": null},\n'
        '  "drivers_and_draggers": {"drivers": [], "draggers": []},\n'
        '  "bull_bear_read": {"bull_case": [], "bear_case": [], "balanced_read": null},\n'
        '  "watch_next": [{"title": "...", "metric": "...", "why_it_matters": "...", '
        '"source_ids": ["..."], "citation_status": "supported|partial|missing|unverified"}],\n'
        '  "claims": [{"text": "...", "source_ids": ["..."], '
        '"citation_status": "supported|partial|missing|unverified"}]\n'
        "}\n"
        "When available, company_profile must use Facts.business_summary, businessSummary, market_business_summary, marketBusinessSummary, or description.\n"
        "If no such profile fact exists, set company_profile to null; do not stitch a company profile from filing snippets or risk-factor evidence.\n"
        "Each profile, point, metric, and claim may only use source_ids already present in the evidence.\n"
        "If evidence is sparse, keep the same object and array structure, but stay cautious in the wording.\n"
        "When evidence is sparse, use conservative phrasing.\n"
        "topline_verdict.summary must be 3-5 sentences covering direction, core numbers, drivers, and doubts.\n"
        "Each visible point summary should be 2-4 sentences; avoid one-sentence items.\n"
        "A successful report should include 3-6 KPI metrics, 3-5 what-changed points, 2-4 drivers, 1-3 draggers, 2 bull_case points, 2 bear_case points, and 3 watch_next items when evidence supports them.\n"
        "financial_dashboard.metrics should prefer the numeric values in Metric evidence. KPI values should come from SEC companyfacts metric values when available, not table snippets.\n"
        "If Metric evidence already contains a value and unit, do not say the metric was not extracted.\n"
        "For latest earnings, prioritize revenue, gross margin, operating income, net income, EPS, operating cash flow, free cash flow, and capex.\n"
        "Place operating result evidence in topline_verdict, key_takeaways, financial_dashboard, and driver_snapshot.\n"
        "Place quarter-quality evidence in quality_of_quarter; split positive drivers and draggers into drivers_and_draggers.\n"
        "Do not provide price targets, buy/sell recommendations, or trading instructions.\n"
        "watch_next must name the next quarter metric or filing clue to monitor.\n"
        "Risk disclosure evidence should default to risk_snapshot unless there is no operating result evidence at all.\n"
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


def _limit_source_refs(source_refs: list[SourceRef], *, max_refs: int = 8) -> list[SourceRef]:
    if len(source_refs) <= max_refs:
        return source_refs
    trimmed: list[SourceRef] = []
    preferred_sections = {
        "md&a",
        "management discussion and analysis",
        "liquidity and capital resources",
        "cash flows",
        "net sales",
        "segment information",
        "business",
        "sec companyfacts",
    }
    seen_sections: set[str] = set()
    for source_ref in source_refs:
        section_key = source_ref.section.strip().lower()
        if section_key in preferred_sections and section_key not in seen_sections:
            trimmed.append(source_ref)
            seen_sections.add(section_key)
        if len(trimmed) >= max_refs:
            return trimmed
    for source_ref in source_refs:
        if source_ref in trimmed:
            continue
        trimmed.append(source_ref)
        if len(trimmed) >= max_refs:
            break
    return trimmed


def _alias_source_refs_by_id(source_refs: list[SourceRef]) -> dict[str, SourceRef]:
    refs_by_id: dict[str, SourceRef] = {}
    for index, source_ref in enumerate(source_refs, start=1):
        refs_by_id[f"src_{index}"] = source_ref
        refs_by_id[source_ref.source_id] = source_ref
        if source_ref.accession_number:
            refs_by_id.setdefault(source_ref.accession_number, source_ref)
        if source_ref.source_id and ":sec_companyfacts:" in source_ref.source_id:
            refs_by_id.setdefault("sec_companyfacts", source_ref)
        if source_ref.section.strip().lower() == "sec companyfacts":
            refs_by_id.setdefault("sec_companyfacts", source_ref)
        for alias in _source_ref_aliases(source_ref, index):
            refs_by_id.setdefault(alias, source_ref)
    return refs_by_id


def _aliased_source_refs(source_refs: list[SourceRef]) -> list[SourceRef]:
    return [
        source_ref.model_copy(update={"source_id": f"src_{index}"})
        for index, source_ref in enumerate(source_refs, start=1)
    ]


def _source_ref_aliases(source_ref: SourceRef, index: int) -> list[str]:
    aliases = [
        f"{source_ref.accession_number}:src_{index}" if source_ref.accession_number else "",
    ]
    if source_ref.source_id:
        aliases.append(_strip_source_ref_suffix(source_ref.source_id))
        aliases.extend(_strip_source_ref_suffix(part) for part in source_ref.source_id.split(":"))
        aliases.append(_source_ref_short_alias(source_ref.source_id))
    if source_ref.accession_number:
        aliases.append(
            _source_ref_short_alias(f"{source_ref.accession_number}:{source_ref.source_id}")
        )
    return [alias for alias in aliases if alias]


def _source_ref_short_alias(source_id: str) -> str:
    normalized = source_id.strip().replace("::", ":")
    if not normalized:
        return ""
    parts = normalized.split(":")
    if len(parts) < 2:
        return normalized
    accession = parts[0]
    tail = ":".join(parts[1:])
    if tail.startswith("sec_companyfacts"):
        return f"{accession}:sec_companyfacts"
    if tail.startswith("unknown:full-filing"):
        return f"{accession}:unknown:full-filing"
    if tail.startswith("full-filing"):
        return f"{accession}:full-filing"
    if tail.startswith("md-a"):
        return f"{accession}:md-a"
    return f"{accession}:{parts[1]}"


def _strip_source_ref_suffix(source_id: str) -> str:
    normalized = source_id.strip()
    if not normalized:
        return ""
    parts = normalized.split(":")
    if len(parts) <= 2:
        return normalized
    return ":".join(parts[:2])


def _sanitize_latest_earnings_source_ids(
    payload: _LatestEarningsSynthesis,
    source_refs_by_id: dict[str, SourceRef],
) -> None:
    if payload.company_profile is not None:
        _sanitize_source_ids(payload.company_profile, source_refs_by_id)
    for point in [
        *payload.key_takeaways,
        *payload.driver_snapshot,
        *payload.risk_snapshot,
        *_quality_of_quarter_points(payload.quality_of_quarter),
        *_drivers_and_draggers_points(payload.drivers_and_draggers),
        *_bull_bear_read_points(payload.bull_bear_read),
    ]:
        _sanitize_source_ids(point, source_refs_by_id)
    for metric in payload.financial_dashboard.metrics:
        _sanitize_source_ids(metric, source_refs_by_id)
    for item in payload.watch_next:
        _sanitize_source_ids(item, source_refs_by_id)
    for claim in payload.claims:
        _sanitize_source_ids(claim, source_refs_by_id)


def _quality_of_quarter_points(
    value: _SynthesizedQualityOfQuarter | None,
) -> list[_SynthesizedPoint]:
    if value is None:
        return []
    return [
        point
        for point in [
            value.growth_quality,
            value.margin_quality,
            value.cash_quality,
            value.one_time_items,
        ]
        if point is not None
    ]


def _drivers_and_draggers_points(
    value: _SynthesizedDriversAndDraggers | None,
) -> list[_SynthesizedPoint]:
    if value is None:
        return []
    return [*value.drivers, *value.draggers]


def _bull_bear_read_points(
    value: _SynthesizedBullBearRead | None,
) -> list[_SynthesizedPoint]:
    if value is None:
        return []
    return [
        *value.bull_case,
        *value.bear_case,
        *([value.balanced_read] if value.balanced_read is not None else []),
    ]


def _sanitize_business_driver_source_ids(
    payload: _BusinessDriverSynthesis,
    source_refs_by_id: dict[str, SourceRef],
) -> set[int]:
    backfill_excluded_points: set[int] = set()
    for point in _driver_map_points(payload.driver_map):
        if _sanitize_business_driver_point_text(point):
            backfill_excluded_points.add(id(point))
        _sanitize_source_ids(point, source_refs_by_id)
        if _sanitize_business_driver_point_source_ids(point, source_refs_by_id):
            if _is_business_driver_partial_placeholder(point):
                continue
            backfill_excluded_points.add(id(point))
    for claim in payload.claims:
        if _is_noisy_business_driver_text(claim.text):
            claim.source_ids = []
            claim.citation_status = CitationStatus.UNVERIFIED
        _sanitize_source_ids(claim, source_refs_by_id)
        _sanitize_business_driver_claim_source_ids(claim, source_refs_by_id)
    payload.claims = [
        claim for claim in payload.claims if not _is_noisy_business_driver_text(claim.text)
    ]
    return backfill_excluded_points


def _sanitize_business_driver_point_text(point: _SynthesizedPoint) -> bool:
    if not _is_noisy_business_driver_text(point.summary):
        return False
    point.summary = _strip_noisy_business_driver_fragments(point.summary)
    if _is_noisy_business_driver_text(point.summary):
        point.summary = _BUSINESS_DRIVER_PARTIAL_PLACEHOLDER
        point.source_ids = []
        point.citation_status = CitationStatus.UNVERIFIED
        return True
    return False


def _sanitize_business_driver_point_source_ids(
    point: _SynthesizedPoint,
    source_refs_by_id: dict[str, SourceRef],
) -> bool:
    original_ids = list(point.source_ids)
    point.source_ids = [
        source_id
        for source_id in original_ids
        if source_id in source_refs_by_id
        and not _is_noisy_business_driver_source_ref(source_refs_by_id[source_id])
    ]
    if original_ids and not point.source_ids:
        point.citation_status = CitationStatus.UNVERIFIED
        return True
    elif (
        len(point.source_ids) < len(original_ids)
        and point.citation_status == CitationStatus.SUPPORTED
    ):
        point.citation_status = CitationStatus.PARTIAL
    return False


def _sanitize_business_driver_claim_source_ids(
    claim: _SynthesizedClaim,
    source_refs_by_id: dict[str, SourceRef],
) -> None:
    original_ids = list(claim.source_ids)
    claim.source_ids = [
        source_id
        for source_id in original_ids
        if source_id in source_refs_by_id
        and not _is_noisy_business_driver_source_ref(source_refs_by_id[source_id])
    ]
    if original_ids and not claim.source_ids:
        claim.citation_status = CitationStatus.UNVERIFIED
    elif (
        len(claim.source_ids) < len(original_ids)
        and claim.citation_status == CitationStatus.SUPPORTED
    ):
        claim.citation_status = CitationStatus.PARTIAL


def _backfill_business_driver_point_source_ids(
    payload: _BusinessDriverSynthesis,
    source_refs: list[SourceRef],
    excluded_point_ids: set[int],
    language: str | None,
    source_refs_by_id: dict[str, SourceRef],
) -> None:
    lens_terms = {
        "revenue_bridge": (
            "revenue",
            "sales",
            "growth",
            "increased",
            "declined",
        ),
        "segment_momentum": (
            "segment",
            "services",
            "service",
            "product",
            "geography",
            "region",
        ),
        "margin_and_mix": (
            "margin",
            "gross margin",
            "operating margin",
            "net margin",
            "gross profit",
            "mix",
            "pricing",
            "price",
            "cost",
            "costs",
            "expense",
            "expenses",
            "cost of revenue",
            "operating income",
            "profit",
            "profitability",
        ),
        "demand_signals": (
            "demand",
            "customer",
            "installed base",
            "orders",
            "backlog",
            "unit",
            "growth",
        ),
    }
    clean_refs = [
        source_ref
        for source_ref in source_refs
        if not _is_noisy_business_driver_source_ref(source_ref)
    ]
    for lens_name, point in (
        ("revenue_bridge", payload.driver_map.revenue_bridge),
        ("segment_momentum", payload.driver_map.segment_momentum),
        ("margin_and_mix", payload.driver_map.margin_and_mix),
        ("demand_signals", payload.driver_map.demand_signals),
    ):
        if point is None or id(point) in excluded_point_ids:
            continue
        placeholder_summary = _is_business_driver_partial_placeholder(point)
        if point.source_ids:
            matched_refs = [
                source_refs_by_id[source_id]
                for source_id in point.source_ids
                if source_id in source_refs_by_id
                and not _is_noisy_business_driver_source_ref(source_refs_by_id[source_id])
            ][:3]
        else:
            matched_refs = _business_driver_backfill_source_refs(
                clean_refs,
                lens_terms[lens_name],
            )
            point.source_ids = [
                source_ref.source_id for source_ref in matched_refs if source_ref.source_id
            ][:3]
        if not point.source_ids or not matched_refs:
            continue
        if placeholder_summary:
            point.summary = _business_driver_backfill_summary(
                lens_name,
                matched_refs,
                language,
            )
            point.citation_status = CitationStatus.PARTIAL
        if point.citation_status in {
            CitationStatus.SUPPORTED,
            CitationStatus.UNVERIFIED,
        }:
            point.citation_status = CitationStatus.PARTIAL
    _localize_business_driver_placeholders(payload, language)


def _business_driver_backfill_source_refs(
    source_refs: list[SourceRef],
    terms: tuple[str, ...],
) -> list[SourceRef]:
    matches = [
        source_ref
        for source_ref in source_refs
        if source_ref.source_id
        and any(term in f"{source_ref.section} {source_ref.snippet}".lower() for term in terms)
    ]
    if matches:
        return matches[:3]
    return [source_ref for source_ref in source_refs[:1] if source_ref.source_id]


def _business_driver_backfill_summary(
    lens_name: str,
    source_refs: list[SourceRef],
    language: str | None,
) -> str:
    evidence_hint = _business_driver_evidence_hint(source_refs)
    if _is_zh_locale(language):
        summaries = {
            "revenue_bridge": (
                "收入桥接证据仍然不完整，但现有 filing 证据指向"
                f"{evidence_hint}。在缺少完整分业务收入拆分前，"
                "这应被视为有证据约束的方向性判断。"
            ),
            "segment_momentum": (
                "分部动能证据仍然不完整，但现有 filing 证据指向"
                f"{evidence_hint}。在缺少完整分部增速与利润率前，"
                "这应被视为有证据约束的方向性判断。"
            ),
            "margin_and_mix": (
                "利润率与组合证据仍然不完整，但现有 filing 证据指向"
                f"{evidence_hint}。在缺少完整分部利润率或产品组合拆分前，"
                "这应被视为有证据约束的方向性判断。"
            ),
            "demand_signals": (
                "需求信号证据仍然不完整，但现有 filing 证据指向"
                f"{evidence_hint}。在缺少订单、积压、销量或留存数据前，"
                "这应被视为有证据约束的方向性判断。"
            ),
        }
        return summaries[lens_name]

    summaries = {
        "revenue_bridge": (
            "Revenue bridge evidence remains partial, but the available filing evidence "
            f"points to {evidence_hint}. Treat this as a directional read until "
            "segment-level revenue detail is available."
        ),
        "segment_momentum": (
            "Segment momentum evidence remains partial, but the available filing evidence "
            f"points to {evidence_hint}. Treat this as a directional read until "
            "complete segment growth detail is available."
        ),
        "margin_and_mix": (
            "Margin and mix evidence remains partial, but the available filing evidence "
            f"points to {evidence_hint}. Treat this as a directional read until "
            "complete segment margin or product mix detail is available."
        ),
        "demand_signals": (
            "Demand evidence remains partial, but the available filing evidence "
            f"points to {evidence_hint}. Treat this as a directional read until "
            "orders, backlog, volume, or retention detail is available."
        ),
    }
    return summaries[lens_name]


def _business_driver_evidence_hint(source_refs: list[SourceRef]) -> str:
    for source_ref in source_refs:
        snippet = source_ref.snippet.strip()
        if not snippet:
            continue
        return _trim_sentence(snippet, max_chars=180)
    return "the clean evidence currently retrieved"


def _trim_sentence(text: str, *, max_chars: int) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def _is_business_driver_partial_placeholder(point: _SynthesizedPoint) -> bool:
    return point.summary.strip() == _BUSINESS_DRIVER_PARTIAL_PLACEHOLDER


def _localize_business_driver_placeholders(
    payload: _BusinessDriverSynthesis,
    language: str | None,
) -> None:
    if not _is_zh_locale(language):
        return
    for lens_name, point in (
        ("revenue_bridge", payload.driver_map.revenue_bridge),
        ("segment_momentum", payload.driver_map.segment_momentum),
        ("margin_and_mix", payload.driver_map.margin_and_mix),
        ("demand_signals", payload.driver_map.demand_signals),
    ):
        if point is not None and _is_business_driver_partial_placeholder(point):
            point.summary = _business_driver_backfill_summary(lens_name, [], language)


def _sanitize_cash_flow_source_ids(
    payload: _CashFlowSynthesis,
    source_refs_by_id: dict[str, SourceRef],
) -> None:
    for metric in payload.cash_metrics:
        _sanitize_source_ids(metric, source_refs_by_id)
    for point in [
        *_capital_allocation_points(payload.capital_allocation),
        *payload.allocation_discipline,
        *payload.red_flags,
    ]:
        _sanitize_source_ids(point, source_refs_by_id)
    for claim in payload.claims:
        _sanitize_source_ids(claim, source_refs_by_id)


def _sanitize_source_ids(
    item: _SynthesizedCompanyProfile | _SynthesizedPoint | _SynthesizedMetric | _SynthesizedClaim,
    source_refs_by_id: dict[str, SourceRef],
) -> None:
    original_ids = list(item.source_ids)
    item.source_ids = [source_id for source_id in original_ids if source_id in source_refs_by_id]
    if original_ids and not item.source_ids:
        item.citation_status = CitationStatus.UNVERIFIED
    elif (
        len(item.source_ids) < len(original_ids)
        and item.citation_status == CitationStatus.SUPPORTED
    ):
        item.citation_status = CitationStatus.PARTIAL


def _coverage(
    payload: _LatestEarningsSynthesis,
    source_refs: list[SourceRef],
) -> TaskSectionCoverage:
    return _latest_coverage(
        payload,
        source_refs,
        _quality_of_quarter_from_payload(payload.quality_of_quarter, {}),
        _drivers_and_draggers_from_payload(payload.drivers_and_draggers, {}),
        _bull_bear_read_from_payload(payload.bull_bear_read, {}),
        payload.watch_next,
        [
            EvidenceBoundMetric(
                name=metric.name,
                value=metric.value,
                period=metric.period,
                interpretation=metric.interpretation,
                evidence_refs=[],
                citation_status=metric.citation_status,
            )
            for metric in payload.financial_dashboard.metrics
        ],
    )


def _latest_coverage(
    payload: _LatestEarningsSynthesis,
    source_refs: list[SourceRef],
    quality_of_quarter: QualityOfQuarter | None,
    drivers_and_draggers: DriversAndDraggers | None,
    bull_bear_read: BullBearRead | None,
    watch_next: list[WatchNextItem],
    dashboard_metrics: list[EvidenceBoundMetric],
) -> TaskSectionCoverage:
    missing_sections = []
    if payload.company_profile is None:
        missing_sections.append("company_profile")
    if not payload.key_takeaways:
        missing_sections.append("key_takeaways")
    if not dashboard_metrics:
        missing_sections.append("financial_dashboard.metrics")
    if not payload.driver_snapshot:
        missing_sections.append("driver_snapshot")
    if not payload.risk_snapshot:
        missing_sections.append("risk_snapshot")
    if quality_of_quarter is None or not _quality_of_quarter_points(quality_of_quarter):
        missing_sections.append("quality_of_quarter")
    if drivers_and_draggers is None or not (
        drivers_and_draggers.drivers or drivers_and_draggers.draggers
    ):
        missing_sections.append("drivers_and_draggers")
    if bull_bear_read is None or not (
        bull_bear_read.bull_case
        or bull_bear_read.bear_case
        or bull_bear_read.balanced_read is not None
    ):
        missing_sections.append("bull_bear_read")
    if not watch_next:
        missing_sections.append("watch_next")
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
    for field_name in (
        "revenue_bridge",
        "segment_momentum",
        "margin_and_mix",
        "demand_signals",
    ):
        if getattr(payload.driver_map, field_name) is None:
            missing_sections.append(field_name)
    if not source_refs:
        missing_sections.append("evidence_refs")
    return TaskSectionCoverage(
        status="complete" if not missing_sections else "partial",
        missing_sections=missing_sections,
        evidence_count=len(source_refs),
    )


def _driver_map_points(driver_map: _SynthesizedDriverMap) -> list[_SynthesizedPoint]:
    return [
        point
        for point in [
            driver_map.revenue_bridge,
            driver_map.segment_momentum,
            driver_map.margin_and_mix,
            driver_map.demand_signals,
        ]
        if point is not None
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


def _final_dashboard_metrics(
    metrics: list[_SynthesizedMetric],
    state: AgentState,
    source_refs_by_id: dict[str, SourceRef],
) -> list[EvidenceBoundMetric]:
    final_metrics = [
        _metric_with_evidence_guardrail(metric, state, source_refs_by_id) for metric in metrics
    ]
    return [
        metric for metric in final_metrics if not _is_placeholder_evidence_metric(metric)
    ] or _dashboard_metrics_from_fact_evidence(state, source_refs_by_id)


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


def _dashboard_metrics_from_fact_evidence(
    state: AgentState,
    source_refs_by_id: dict[str, SourceRef],
) -> list[EvidenceBoundMetric]:
    synthesized_metrics: list[EvidenceBoundMetric] = []
    for record in state.evidence_memory.metric_evidence:
        if not _has_fact_value(record):
            continue
        source_id = str(record.get("source_id") or "").strip()
        source_ref = source_refs_by_id.get(source_id)
        if source_ref is None:
            continue
        name = str(record.get("metric") or record.get("normalized_metric") or "Metric")
        synthesized_metrics.append(
            EvidenceBoundMetric(
                name=name,
                value=_metric_evidence_value(record),
                period=_metric_evidence_period(record),
                interpretation=_metric_evidence_interpretation(record, source_ref),
                evidence_refs=[_evidence_ref(source_ref)],
                citation_status=CitationStatus.SUPPORTED,
            )
        )
    return synthesized_metrics[:3]


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
    return record.get("value") is not None and str(record.get("source") or "") in {
        "sec_companyfacts",
        "preloaded_financial_facts",
    }


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
    if isinstance(value, int | float) and unit.lower() in {"x", "ratio"}:
        return f"{float(value):.2f}x"
    if isinstance(value, int | float) and unit.lower() in {"pure", "percent", "percentage"}:
        return f"{float(value) * 100:.1f}%"
    if isinstance(value, int | float):
        formatted = _compact_number(value)
    elif isinstance(value, str) and value.strip().replace(".", "", 1).isdigit():
        formatted = _compact_number(float(value))
    else:
        formatted = str(value)
    if unit == "USD" and not formatted.startswith("$"):
        return f"${formatted}"
    return formatted


def _format_metric_display_value(value: object) -> str:
    raw_value = "" if value is None else str(value)
    trimmed_value = raw_value.strip()
    if not trimmed_value:
        return raw_value
    if re.search(r"[%]|(?:\b|[0-9])(k|m|b|t|million|billion|trillion)\b", trimmed_value, re.I):
        return raw_value
    numeric_match = re.fullmatch(
        r"([$€£¥])?\s*(-?\d[\d,]*(?:\.\d+)?)\s*(USD|EUR|GBP|JPY|CNY)?",
        trimmed_value,
        re.I,
    )
    if numeric_match is None:
        return raw_value
    leading_currency, raw_number, trailing_currency = numeric_match.groups()
    numeric_value = float(raw_number.replace(",", ""))
    if abs(numeric_value) < 10_000:
        return raw_value
    symbol = leading_currency or _currency_symbol(trailing_currency) or "$"
    return f"{symbol}{_compact_number(numeric_value)}"


def _currency_symbol(currency_code: str | None) -> str:
    if currency_code is None:
        return ""
    return {
        "USD": "$",
        "EUR": "€",
        "GBP": "£",
        "JPY": "¥",
        "CNY": "¥",
    }.get(currency_code.upper(), "")


def _is_unsupported_placeholder_metric(metric: object) -> bool:
    if not isinstance(metric, dict):
        return False
    source_ids = metric.get("source_ids")
    has_sources = isinstance(source_ids, list) and bool(source_ids)
    if has_sources:
        return False
    return _metric_value_needs_evidence(
        str(metric.get("value") or ""),
        str(metric.get("interpretation") or ""),
    )


def _is_placeholder_evidence_metric(metric: EvidenceBoundMetric) -> bool:
    return _metric_value_needs_evidence(metric.value, metric.interpretation)


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
    return normalize_metric_name(metric)


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
            f"snippet={_clip(source_ref.snippet, 360)}"
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
