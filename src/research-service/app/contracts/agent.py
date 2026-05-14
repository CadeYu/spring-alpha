from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contracts.research_task import ResearchTaskType

MVP_TOOL_NAMES = frozenset(
    {
        "get_company_facts",
        "search_filing_sections",
        "search_metric_evidence",
        "get_business_signals",
    }
)


class AgentRunStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degraded"
    ERROR = "error"


class ToolStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    EMPTY = "empty"
    DEGRADED = "degraded"
    ERROR = "error"


class AgentPhase(StrEnum):
    RESOLVE_TASK = "resolve_task"
    COLLECT_FINANCIAL_FACTS = "collect_financial_facts"
    COLLECT_FILING_METADATA = "collect_filing_metadata"
    BUILD_EVIDENCE_PLAN = "build_evidence_plan"
    RETRIEVE_EVIDENCE = "retrieve_evidence"
    EXTRACT_SIGNALS = "extract_signals"
    DRAFT_REPORT_SECTIONS = "draft_report_sections"
    VALIDATE_CLAIMS = "validate_claims"
    DEGRADED = "degraded"


class RepairAction(StrEnum):
    RETRIEVE_MORE = "retrieve_more"
    REWRITE_QUERY = "rewrite_query"
    VALIDATE_CLAIM = "validate_claim"
    FALLBACK_TO_RAW_FILING = "fallback_to_raw_filing"
    MARK_PARTIAL_SUPPORT = "mark_partial_support"
    FINALIZE = "finalize"


class LlmProvider(StrEnum):
    SILICONFLOW = "siliconflow"
    OPENAI = "openai"
    GEMINI = "gemini"


class AgentFilingDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=16)
    filing_type: str = Field(min_length=1, max_length=32)
    filing_date: str | None = None
    accession_number: str | None = None
    text: str = Field(min_length=1)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1, max_length=16)
    task_type: ResearchTaskType
    language: str = Field(default="en", min_length=2, max_length=8)
    max_evidence_repair_loops: int = Field(default=2, ge=0, le=3)
    llm_provider: LlmProvider | None = None
    llm_model: str | None = Field(default=None, min_length=1, max_length=128)
    llm_api_key: str | None = Field(default=None, min_length=1, exclude=True, repr=False)
    facts: dict[str, Any] = Field(default_factory=dict)
    filings: list[AgentFilingDocument] = Field(default_factory=list)

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("llm_model", "llm_api_key", mode="before")
    @classmethod
    def blank_optional_string_to_none(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_type: ResearchTaskType
    phase: AgentPhase
    status: ToolStatus
    summary: str
    tool_name: str | None = None
    event_kind: Literal["reasoning", "tool"] = "tool"
    agent_name: str | None = None
    model_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = Field(default=0, ge=0)
    degraded_reason: str | None = None


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ToolStatus
    data: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int = Field(default=0, ge=0)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    degraded_reasons: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def ok(
        cls,
        data: dict[str, Any] | None = None,
        *,
        latency_ms: int = 0,
        source_refs: list[dict[str, Any]] | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> "ToolResult":
        return cls(
            status=ToolStatus.OK,
            data=data or {},
            latency_ms=latency_ms,
            source_refs=source_refs or [],
            metrics=metrics or {},
        )

    @classmethod
    def empty(
        cls,
        data: dict[str, Any] | None = None,
        *,
        degraded_reason: str,
        latency_ms: int = 0,
    ) -> "ToolResult":
        return cls(
            status=ToolStatus.EMPTY,
            data=data or {},
            latency_ms=latency_ms,
            degraded_reasons=[degraded_reason],
        )

    @classmethod
    def partial(
        cls,
        data: dict[str, Any] | None = None,
        *,
        degraded_reason: str,
        latency_ms: int = 0,
    ) -> "ToolResult":
        return cls(
            status=ToolStatus.PARTIAL,
            data=data or {},
            latency_ms=latency_ms,
            degraded_reasons=[degraded_reason],
        )


class ToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    input_schema: str = Field(min_length=1)
    output_schema: str = Field(min_length=1)
    timeout_seconds: int = Field(default=10, gt=0, le=120)
    requires_evidence: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if normalized not in MVP_TOOL_NAMES:
            raise ValueError(f"Unsupported tool spec: {value}")
        return normalized


class TaskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_type: ResearchTaskType
    allowed_tools: list[str] = Field(min_length=1)
    required_outputs: list[str] = Field(min_length=1)
    max_steps: int = Field(default=5, ge=1, le=10)
    max_tool_calls: int = Field(default=5, ge=1, le=12)
    max_repair_loops: int = Field(default=2, ge=0, le=3)
    degraded_policy: Literal["finalize_degraded"] = "finalize_degraded"

    @model_validator(mode="after")
    def validate_policy(self) -> "TaskPolicy":
        unknown_tools = [
            tool_name for tool_name in self.allowed_tools if tool_name not in MVP_TOOL_NAMES
        ]
        if unknown_tools:
            raise ValueError(f"Unsupported tools for task policy: {', '.join(unknown_tools)}")
        if len(set(self.allowed_tools)) != len(self.allowed_tools):
            raise ValueError("Task policy allowed_tools must be unique")
        if len(set(self.required_outputs)) != len(self.required_outputs):
            raise ValueError("Task policy required_outputs must be unique")
        return self


class CoverageState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["complete", "partial", "degraded"] = "partial"
    missing_outputs: list[str] = Field(default_factory=list)
    evidence_count: int = Field(default=0, ge=0)
    citation_coverage: Literal["complete", "partial", "missing"] = "missing"


class EvidenceMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[dict[str, Any]] = Field(default_factory=list)
    metric_evidence: list[dict[str, Any]] = Field(default_factory=list)
    business_signals: list[dict[str, Any]] = Field(default_factory=list)
    citation_results: list[dict[str, Any]] = Field(default_factory=list)


class AgentState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1, max_length=16)
    task_type: ResearchTaskType
    status: AgentRunStatus = AgentRunStatus.OK
    language: str = Field(default="en", min_length=2, max_length=8)
    provider: LlmProvider | None = None
    model: str | None = None
    task_policy: TaskPolicy
    step_index: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    evidence_memory: EvidenceMemory = Field(default_factory=EvidenceMemory)
    retrieval_records: list[dict[str, Any]] = Field(default_factory=list)
    tool_events: list[AgentEvent] = Field(default_factory=list)
    draft_sections: dict[str, Any] | None = None
    coverage: CoverageState = Field(default_factory=CoverageState)
    degraded_reasons: list[str] = Field(default_factory=list)
    final_report: dict[str, Any] | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class BoundedAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_type: ResearchTaskType
    status: AgentRunStatus
    events: list[AgentEvent]
    degraded_reasons: list[str] = Field(default_factory=list)
    retrieval_records: list[dict[str, Any]] = Field(default_factory=list)
    retryable: bool = False
    final_report: dict[str, Any] | None = None


def default_task_policy(task_type: ResearchTaskType) -> TaskPolicy:
    policies = {
        ResearchTaskType.LATEST_EARNINGS_READOUT: TaskPolicy(
            task_type=task_type,
            allowed_tools=[
                "get_company_facts",
                "search_filing_sections",
                "search_metric_evidence",
            ],
            required_outputs=[
                "toplineVerdict",
                "keyTakeaways",
                "financialDashboard",
                "driverSnapshot",
                "riskSnapshot",
            ],
            max_steps=5,
            max_tool_calls=5,
            max_repair_loops=2,
        ),
        ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE: TaskPolicy(
            task_type=task_type,
            allowed_tools=[
                "search_filing_sections",
                "search_metric_evidence",
                "get_business_signals",
            ],
            required_outputs=[
                "driverThesis",
                "driverMap",
                "positiveSignals",
                "negativeSignals",
                "watchlist",
            ],
            max_steps=7,
            max_tool_calls=7,
            max_repair_loops=2,
        ),
        ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION: TaskPolicy(
            task_type=task_type,
            allowed_tools=[
                "get_company_facts",
                "search_filing_sections",
                "search_metric_evidence",
            ],
            required_outputs=[
                "cashQualityVerdict",
                "cashMetrics",
                "capitalAllocation",
                "allocationDiscipline",
                "redFlags",
            ],
            max_steps=5,
            max_tool_calls=5,
            max_repair_loops=2,
        ),
    }
    return policies[task_type]
