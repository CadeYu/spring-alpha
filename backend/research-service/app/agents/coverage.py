from pydantic import BaseModel, ConfigDict, Field

from app.contracts.agent import AgentState, CoverageState


class CoverageCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    coverage: CoverageState
    should_finalize: bool
    degraded_reasons: list[str] = Field(default_factory=list)


def check_coverage(state: AgentState) -> CoverageCheckResult:
    evidence_count = len(state.evidence_memory.source_refs)
    has_citation_results = bool(state.evidence_memory.citation_results)
    if evidence_count == 0:
        return CoverageCheckResult(
            coverage=CoverageState(
                status="degraded",
                missing_outputs=list(state.task_policy.required_outputs),
                evidence_count=0,
                citation_coverage="missing",
            ),
            should_finalize=False,
            degraded_reasons=["No evidence source refs were collected."],
        )

    return CoverageCheckResult(
        coverage=CoverageState(
            status="complete",
            missing_outputs=[],
            evidence_count=evidence_count,
            citation_coverage="partial" if has_citation_results else "missing",
        ),
        should_finalize=has_citation_results,
    )
