import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import LlamaIndexRagPipeline, RetrieveEvidenceResult


class SecEvidenceSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        description="Investor-facing evidence query for SEC filing sections.",
    )
    sections: list[str] = Field(
        default_factory=list,
        description="Preferred SEC sections, such as MD&A or Risk Factors.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of evidence snippets to return.",
    )


def create_sec_evidence_search_tool(
    *,
    rag_pipeline: LlamaIndexRagPipeline,
    run_id: str,
    ticker: str,
    task_type: ResearchTaskType,
) -> StructuredTool:
    def search_sec_evidence(query: str, sections: list[str] | None = None, top_k: int = 5) -> str:
        """Search SEC filing evidence and return compact source snippets as JSON."""
        result = rag_pipeline.retrieve_evidence(
            run_id=run_id,
            ticker=ticker,
            task_type=task_type,
            query=query,
            sections=sections or None,
            top_k=top_k,
        )
        return json.dumps(_compact_evidence_payload(result), ensure_ascii=True)

    return StructuredTool.from_function(
        search_sec_evidence,
        name="search_sec_evidence",
        description=(
            "Search SEC filing evidence. Returns source snippets only; it does not write "
            "analysis, verdicts, forecasts, or recommendations."
        ),
        args_schema=SecEvidenceSearchInput,
    )


def _compact_evidence_payload(result: RetrieveEvidenceResult) -> dict[str, object]:
    source_refs_by_id = {source_ref.source_id: source_ref for source_ref in result.source_refs}
    evidence = []
    for node in result.retrieved_nodes:
        source_ref = source_refs_by_id.get(node.node_id)
        evidence.append(
            {
                "source_id": node.node_id,
                "section": str(node.metadata.get("section", "unknown")),
                "snippet": source_ref.snippet if source_ref is not None else node.text[:500],
                "filing_type": _optional_str(node.metadata.get("filing_type")),
                "filing_date": _optional_str(node.metadata.get("filing_date")),
                "accession_number": _optional_str(node.metadata.get("accession_number")),
                "score": round(node.rerank_score, 4),
                "rerank_reason": node.rerank_reason,
            }
        )
    return {
        "run_id": result.run_id,
        "ticker": result.ticker,
        "task_type": result.task_type.value,
        "query": result.query,
        "fallback_status": result.fallback_status.value,
        "latency_ms": result.latency_ms,
        "evidence": evidence,
    }


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
