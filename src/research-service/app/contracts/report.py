from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.research_task import ResearchTaskType


class CitationStatus(StrEnum):
    SUPPORTED = "supported"
    PARTIAL = "partial"
    MISSING = "missing"
    UNVERIFIED = "unverified"


class SourceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    section: str
    snippet: str
    citation_status: CitationStatus = CitationStatus.UNVERIFIED
    filing_type: str | None = None
    filing_date: str | None = None
    accession_number: str | None = None


class EvidenceBoundClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    text: str
    citation_status: CitationStatus
    source_refs: list[SourceRef] = Field(default_factory=list)


class TaskSectionCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["complete", "partial", "degraded"]
    missing_sections: list[str] = Field(default_factory=list)
    evidence_count: int = Field(ge=0)


class EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str
    excerpt: str
    filing_date: str | None = None
    accession_number: str | None = None
    source_id: str | None = None


class EvidenceBoundPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    summary: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    citation_status: CitationStatus


class EvidenceBoundMetric(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: str
    period: str | None = None
    interpretation: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    citation_status: CitationStatus


class BaseTaskSections(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["task_sections.v1"]
    task_type: ResearchTaskType
    coverage: TaskSectionCoverage


class ToplineVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    summary: str
    verdict: Literal["positive", "mixed", "negative"]


class LatestFinancialDashboard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[EvidenceBoundMetric] = Field(default_factory=list)
    chart_focus: list[str] = Field(default_factory=list)


class LatestEarningsSections(BaseTaskSections):
    task_type: Literal[ResearchTaskType.LATEST_EARNINGS_READOUT]
    topline_verdict: ToplineVerdict
    key_takeaways: list[EvidenceBoundPoint] = Field(default_factory=list)
    financial_dashboard: LatestFinancialDashboard
    driver_snapshot: list[EvidenceBoundPoint] = Field(default_factory=list)
    risk_snapshot: list[EvidenceBoundPoint] = Field(default_factory=list)


class DriverThesis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    durability: Literal["durable", "mixed", "temporary", "unclear"]
    summary: str


class DriverMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: list[EvidenceBoundPoint] = Field(default_factory=list)
    segment: list[EvidenceBoundPoint] = Field(default_factory=list)
    geography: list[EvidenceBoundPoint] = Field(default_factory=list)
    demand: list[EvidenceBoundPoint] = Field(default_factory=list)
    pricing: list[EvidenceBoundPoint] = Field(default_factory=list)
    customer: list[EvidenceBoundPoint] = Field(default_factory=list)
    strategy: list[EvidenceBoundPoint] = Field(default_factory=list)


class BusinessDriverSections(BaseTaskSections):
    task_type: Literal[ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE]
    driver_thesis: DriverThesis
    driver_map: DriverMap
    positive_signals: list[EvidenceBoundPoint] = Field(default_factory=list)
    negative_signals: list[EvidenceBoundPoint] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)


class CashQualityVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    headline: str
    earnings_backed_by_cash: Literal["yes", "mixed", "no", "unclear"]
    summary: str


class CapitalAllocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capex: list[EvidenceBoundPoint] = Field(default_factory=list)
    buybacks: list[EvidenceBoundPoint] = Field(default_factory=list)
    dividends: list[EvidenceBoundPoint] = Field(default_factory=list)
    debt: list[EvidenceBoundPoint] = Field(default_factory=list)
    liquidity: list[EvidenceBoundPoint] = Field(default_factory=list)


class CashFlowCapitalAllocationSections(BaseTaskSections):
    task_type: Literal[ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION]
    cash_quality_verdict: CashQualityVerdict
    cash_metrics: list[EvidenceBoundMetric] = Field(default_factory=list)
    capital_allocation: CapitalAllocation
    allocation_discipline: list[EvidenceBoundPoint] = Field(default_factory=list)
    red_flags: list[EvidenceBoundPoint] = Field(default_factory=list)


TaskSpecificSections = (
    LatestEarningsSections | BusinessDriverSections | CashFlowCapitalAllocationSections
)


class EvidenceAwareReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    ticker: str
    task_type: ResearchTaskType
    task_sections: TaskSpecificSections = Field(discriminator="task_type")
    sections: dict[str, Any] | None = None
    claims: list[EvidenceBoundClaim]
    retrieval_records: list[dict[str, Any]] = Field(default_factory=list)
