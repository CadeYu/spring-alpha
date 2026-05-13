from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.contracts.research_task import ResearchTaskType


class BaseToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    ticker: str = Field(min_length=1, max_length=16)
    task_type: ResearchTaskType

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, value: str) -> str:
        return value.strip().upper()


class CompanyFactsInput(BaseToolInput):
    period: str | None = None
    metrics: list[str] = Field(default_factory=list)


class FilingSectionSearchInput(BaseToolInput):
    sections: list[str] = Field(min_length=1)
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class MetricEvidenceInput(BaseToolInput):
    metrics: list[str] = Field(min_length=1)
    period: str | None = None
    query: str | None = None


class BusinessSignalsInput(BaseToolInput):
    signal_types: list[str] = Field(default_factory=list)

