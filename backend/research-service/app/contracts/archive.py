from pathlib import PurePath
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.agent import AgentEvent, AgentRunStatus, BoundedAgentResult
from app.contracts.research_task import ResearchTaskType


class CitationValidationArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str = "not_run"


class EvalArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    metric: str | None = None
    value: Any | None = None


class ReportArchiveArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    run_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1, max_length=16)
    task_type: ResearchTaskType
    status: AgentRunStatus
    agent_events: list[AgentEvent]
    degraded_reasons: list[str] = Field(default_factory=list)
    final_report: dict[str, Any] | None = None
    retrieval_records: list[dict[str, Any]] = Field(default_factory=list)
    citation_validation: CitationValidationArtifact = Field(
        default_factory=CitationValidationArtifact
    )
    eval_artifacts: list[EvalArtifact] = Field(default_factory=list)

    @classmethod
    def from_agent_result(
        cls,
        result: BoundedAgentResult,
        *,
        ticker: str | None = None,
        retrieval_records: list[dict[str, Any]] | None = None,
        citation_validation: CitationValidationArtifact | dict[str, Any] | None = None,
        eval_artifacts: list[EvalArtifact | dict[str, Any]] | None = None,
    ) -> Self:
        final_report = result.final_report or {}
        archive_ticker = str(ticker or final_report.get("ticker", "UNKNOWN")).upper()
        archive_retrieval_records = (
            retrieval_records
            if retrieval_records is not None
            else final_report.get("retrieval_records", [])
        )
        archive_citation_validation = (
            citation_validation
            if isinstance(citation_validation, CitationValidationArtifact)
            else CitationValidationArtifact.model_validate(citation_validation or {})
        )
        archive_eval_artifacts = [
            item if isinstance(item, EvalArtifact) else EvalArtifact.model_validate(item)
            for item in (eval_artifacts or [])
        ]

        return cls(
            run_id=result.run_id,
            ticker=archive_ticker,
            task_type=result.task_type,
            status=result.status,
            agent_events=result.events,
            degraded_reasons=result.degraded_reasons,
            final_report=result.final_report,
            retrieval_records=list(archive_retrieval_records)
            if isinstance(archive_retrieval_records, list)
            else [],
            citation_validation=archive_citation_validation,
            eval_artifacts=archive_eval_artifacts,
        )


def safe_archive_file_name(run_id: str) -> str:
    path = PurePath(run_id)
    if path.name != run_id or run_id in {"", ".", ".."}:
        raise ValueError("Archive run_id must be a single safe file name segment.")
    return f"{run_id}.json"
