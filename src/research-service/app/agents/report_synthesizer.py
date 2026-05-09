from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.llm_gateway import LlmClient, LlmRequest
from app.contracts.agent import AgentRequest, AgentState
from app.contracts.report import (
    CitationStatus,
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


def synthesize_latest_earnings_report(
    request: AgentRequest,
    state: AgentState,
    client: LlmClient,
) -> EvidenceAwareReport:
    if request.task_type != ResearchTaskType.LATEST_EARNINGS_READOUT:
        raise ReportSynthesisError(f"Unsupported synthesis task: {request.task_type.value}")

    source_refs = _source_refs_from_state(state)
    source_refs_by_id = {source_ref.source_id: source_ref for source_ref in source_refs}
    response = client.complete_json(
        LlmRequest(
            run_id=request.run_id,
            provider=client.provider,
            model=request.llm_model,
            task_type=request.task_type,
            system_prompt=_system_prompt(),
            user_prompt=_user_prompt(request, state, source_refs),
            state=state,
            timeout_seconds=60,
        )
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


def _system_prompt() -> str:
    return (
        "You are a financial research report synthesizer. Return one JSON object only. "
        "Use only the provided evidence. Do not include chain-of-thought. "
        "Every field must match the requested JSON schema exactly."
    )


def _user_prompt(
    request: AgentRequest,
    state: AgentState,
    source_refs: list[SourceRef],
) -> str:
    evidence_lines = [
        (
            f"- source_id={source_ref.source_id}; section={source_ref.section}; "
            f"filing_type={source_ref.filing_type}; filing_date={source_ref.filing_date}; "
            f"snippet={_clip(source_ref.snippet)}"
        )
        for source_ref in source_refs
    ]
    facts = state.evidence_memory.facts
    return (
        "Generate typed latest earnings task sections.\n"
        "Return JSON only. Do not use strings where objects or arrays are required.\n"
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
    return str(value)
