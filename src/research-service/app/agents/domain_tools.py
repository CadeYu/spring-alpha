import re

from app.contracts.agent import AgentState, ToolResult
from app.contracts.tools import (
    BusinessSignalsInput,
    CitationVerificationInput,
    CompanyFactsInput,
    FilingSectionSearchInput,
    FinalizeReportInput,
    MetricEvidenceInput,
)
from app.rag.llamaindex_pipeline import LlamaIndexRagPipeline, RetrieveEvidenceResult


class DeterministicResearchToolService:
    def get_company_facts(self, tool_input: CompanyFactsInput, state: AgentState) -> ToolResult:
        return ToolResult.ok(
            data={
                "ticker": state.ticker,
                "task_type": state.task_type.value,
                "period": tool_input.period or "latest_quarter",
                "metrics": tool_input.metrics,
            }
        )

    def search_filing_sections(
        self,
        tool_input: FilingSectionSearchInput,
        state: AgentState,
    ) -> ToolResult:
        source_ref = {
            "source_id": f"{state.run_id}:filing:1",
            "section": tool_input.sections[0],
            "snippet": "Evidence placeholder from the selected filing section.",
            "citation_status": "unverified",
        }
        return ToolResult.ok(
            data={
                "query": tool_input.query,
                "retrieved_nodes": [
                    {
                        "node_id": source_ref["source_id"],
                        **source_ref,
                    }
                ],
            },
            source_refs=[source_ref],
        )

    def search_metric_evidence(
        self,
        tool_input: MetricEvidenceInput,
        state: AgentState,
    ) -> ToolResult:
        metric = tool_input.metrics[0]
        source_ref = {
            "source_id": f"{state.run_id}:metric:1",
            "section": "Financial Statements",
            "snippet": f"Evidence placeholder for {metric}.",
            "citation_status": "unverified",
        }
        return ToolResult.ok(
            data={
                "records": [
                    {
                        "metric": metric,
                        "period": tool_input.period or "latest_quarter",
                        "source_id": source_ref["source_id"],
                    }
                ]
            },
            source_refs=[source_ref],
        )

    def get_business_signals(
        self,
        tool_input: BusinessSignalsInput,
        state: AgentState,
    ) -> ToolResult:
        return ToolResult.ok(
            data={
                "records": [
                    {
                        "signal": "business_driver_placeholder",
                        "signal_types": tool_input.signal_types,
                        "summary": "Business signal placeholder from deterministic runner.",
                    }
                ]
            }
        )

    def verify_citations(
        self,
        tool_input: CitationVerificationInput,
        state: AgentState,
    ) -> ToolResult:
        records = [
            _score_claim_against_sources(claim, tool_input.source_refs)
            for claim in tool_input.claims
        ]
        source_refs = _source_refs_with_citation_status(tool_input.source_refs, records)
        return ToolResult.ok(
            data={
                "records": records,
                "claim_count": len(tool_input.claims),
                "source_ref_count": len(tool_input.source_refs),
            },
            source_refs=source_refs,
        )

    def finalize_report(self, tool_input: FinalizeReportInput, state: AgentState) -> ToolResult:
        return ToolResult.ok(
            data={
                "coverage": tool_input.coverage,
                "draft_sections": tool_input.draft_sections,
                "tool_name": "finalize_report",
                "ticker": state.ticker,
                "task_type": state.task_type.value,
            }
        )


class LlamaIndexResearchToolService(DeterministicResearchToolService):
    def __init__(self, rag_pipeline: LlamaIndexRagPipeline) -> None:
        self._rag_pipeline = rag_pipeline

    def search_filing_sections(
        self,
        tool_input: FilingSectionSearchInput,
        state: AgentState,
    ) -> ToolResult:
        result = self._rag_pipeline.retrieve_evidence(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            query=tool_input.query,
            sections=tool_input.sections,
            top_k=tool_input.limit,
        )
        source_refs = [source_ref.model_dump(mode="json") for source_ref in result.source_refs]
        if not source_refs:
            return ToolResult.empty(
                data={"query": tool_input.query, "retrieved_nodes": []},
                degraded_reason="No filing section evidence matched the query.",
                latency_ms=result.latency_ms,
            )
        return ToolResult.ok(
            data={
                "query": tool_input.query,
                "retrieved_nodes": _retrieved_nodes(result),
                "fallback_status": result.fallback_status.value,
            },
            latency_ms=result.latency_ms,
            source_refs=source_refs,
        )

    def search_metric_evidence(
        self,
        tool_input: MetricEvidenceInput,
        state: AgentState,
    ) -> ToolResult:
        query = tool_input.query or " ".join(tool_input.metrics)
        result = self._rag_pipeline.retrieve_evidence(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            query=query,
            sections=_preferred_metric_sections(tool_input.metrics),
            top_k=5,
        )
        source_refs = [source_ref.model_dump(mode="json") for source_ref in result.source_refs]
        if not source_refs:
            return ToolResult.empty(
                data={"records": [], "retrieved_nodes": []},
                degraded_reason="No metric evidence matched the query.",
                latency_ms=result.latency_ms,
            )
        return ToolResult.ok(
            data={
                "records": [
                    {
                        "metric": metric,
                        "period": tool_input.period or "latest_quarter",
                        "source_id": source_refs[0]["source_id"],
                    }
                    for metric in tool_input.metrics
                ],
                "retrieved_nodes": _retrieved_nodes(result),
                "fallback_status": result.fallback_status.value,
            },
            latency_ms=result.latency_ms,
            source_refs=source_refs,
        )


def _score_claim_against_sources(
    claim: dict[str, object],
    source_refs: list[dict[str, object]],
) -> dict[str, object]:
    claim_terms = _content_terms(str(claim.get("text", "")))
    best_overlap = 0.0
    best_source_id: str | None = None
    for source_ref in source_refs:
        source_terms = _content_terms(str(source_ref.get("snippet", "")))
        if not claim_terms or not source_terms:
            continue
        overlap = len(claim_terms & source_terms) / len(claim_terms)
        if overlap > best_overlap:
            best_overlap = overlap
            best_source_id = str(source_ref.get("source_id", "unknown"))

    status = "missing"
    if best_overlap >= 0.75:
        status = "supported"
    elif best_overlap >= 0.35:
        status = "partial"

    return {
        "claim_id": str(claim.get("claim_id", "unknown")),
        "status": status,
        "support_score": round(best_overlap, 4),
        "source_id": best_source_id,
    }


def _source_refs_with_citation_status(
    source_refs: list[dict[str, object]],
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    best_status = _best_citation_status(records)
    return [
        {
            **source_ref,
            "citation_status": best_status,
        }
        for source_ref in source_refs
    ]


def _best_citation_status(records: list[dict[str, object]]) -> str:
    statuses = [str(record.get("status", "missing")) for record in records]
    if "supported" in statuses:
        return "supported"
    if "partial" in statuses:
        return "partial"
    return "missing"


def _content_terms(text: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "because",
        "by",
        "for",
        "in",
        "of",
        "the",
        "to",
    }
    return {
        term
        for term in re.findall(r"[a-z0-9]+", text.lower())
        if len(term) > 2 and term not in stop_words
    }


def _retrieved_nodes(result: RetrieveEvidenceResult) -> list[dict[str, object]]:
    return [node.model_dump(mode="json") for node in result.retrieved_nodes]


def _preferred_metric_sections(metrics: list[str]) -> list[str]:
    joined = " ".join(metrics).lower()
    if any(term in joined for term in ("cash", "capex", "buyback", "repurchase", "debt")):
        return ["Liquidity and Capital Resources", "Cash Flow Statement"]
    if any(term in joined for term in ("revenue", "margin", "income", "expense")):
        return ["MD&A", "Net Sales", "Segment Information"]
    return ["MD&A", "Financial Statements"]
