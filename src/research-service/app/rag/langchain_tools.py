import json

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import LlamaIndexRagPipeline, RetrieveEvidenceResult


class EvidencePackFilingContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filing_type: str | None = None
    filing_date: str | None = None
    accession_number: str | None = None


class EvidencePackItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    source_type: str
    section: str
    snippet: str
    filing_type: str | None = None
    filing_date: str | None = None
    accession_number: str | None = None
    score: float
    relevance_note: str


class EvidencePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    ticker: str
    task_type: str
    query: str
    filing_context: EvidencePackFilingContext
    metric_facts: list[dict[str, object]] = Field(default_factory=list)
    filing_evidence: list[EvidencePackItem] = Field(default_factory=list)
    retrieval_status: str
    latency_ms: int


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


class EvidencePackInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    focus: str | None = Field(
        default=None,
        description="Optional investor-facing focus for the evidence pack.",
    )
    top_k: int = Field(
        default=5,
        ge=1,
        le=8,
        description="Maximum number of evidence snippets to return.",
    )


MAX_EVIDENCE_PACK_ITEMS = 4
MAX_EVIDENCE_PACK_SNIPPET_CHARS = 360


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


def create_evidence_pack_tool(
    *,
    rag_pipeline: LlamaIndexRagPipeline,
    run_id: str,
    ticker: str,
    task_type: ResearchTaskType,
) -> StructuredTool:
    def build_evidence_pack(focus: str | None = None, top_k: int = 5) -> str:
        """Build a compact SEC evidence pack for the current research task."""
        template = _evidence_pack_template(task_type, focus)
        budgeted_top_k = _budgeted_top_k(top_k)
        results = [
            rag_pipeline.retrieve_evidence(
                run_id=run_id,
                ticker=ticker,
                task_type=task_type,
                query=query,
                sections=template["sections"],
                top_k=budgeted_top_k,
            )
            for query in template["queries"]
        ]
        pack = _merge_evidence_pack_results(results, top_k=budgeted_top_k)
        return json.dumps(pack, ensure_ascii=True)

    return StructuredTool.from_function(
        build_evidence_pack,
        name="build_evidence_pack",
        description=(
            "Build one compact Evidence Pack for the current research task using fixed "
            "SEC filing query templates. Returns evidence only, not analysis."
        ),
        args_schema=EvidencePackInput,
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
        "evidence_pack": _evidence_pack_from_result(result).model_dump(mode="json"),
    }


def _merge_evidence_pack_results(
    results: list[RetrieveEvidenceResult],
    *,
    top_k: int,
) -> dict[str, object]:
    if not results:
        return {"evidence_pack": None, "source_refs": []}
    primary = results[0]
    items_by_source_id: dict[str, dict[str, object]] = {}
    source_refs_by_id: dict[str, dict[str, object]] = {}
    for result in results:
        pack = _evidence_pack_from_result(result)
        for item in pack.filing_evidence:
            if item.source_id not in items_by_source_id:
                items_by_source_id[item.source_id] = _budget_evidence_item(
                    item.model_dump(mode="json")
                )
        for source_ref in result.source_refs:
            source_refs_by_id[source_ref.source_id] = source_ref.model_dump(mode="json")
    evidence_items = sorted(
        items_by_source_id.values(),
        key=lambda item: _float_score(item.get("score")),
        reverse=True,
    )[:top_k]
    evidence_pack = EvidencePack(
        run_id=primary.run_id,
        ticker=primary.ticker,
        task_type=primary.task_type.value,
        query=_merge_pack_queries(results),
        filing_context=_filing_context_from_raw_items(evidence_items),
        metric_facts=[],
        filing_evidence=[EvidencePackItem.model_validate(item) for item in evidence_items],
        retrieval_status=_merged_retrieval_status(results, evidence_items),
        latency_ms=sum(result.latency_ms for result in results),
    )
    return {
        "evidence_pack": evidence_pack.model_dump(mode="json"),
        "source_refs": list(source_refs_by_id.values()),
    }


def _evidence_pack_from_result(result: RetrieveEvidenceResult) -> EvidencePack:
    source_refs_by_id = {source_ref.source_id: source_ref for source_ref in result.source_refs}
    filing_items = []
    for node in result.retrieved_nodes:
        source_ref = source_refs_by_id.get(node.node_id)
        filing_items.append(
            EvidencePackItem(
                source_id=node.node_id,
                source_type="sec_filing",
                section=str(node.metadata.get("section", "unknown")),
                snippet=_truncate_text(
                    source_ref.snippet if source_ref is not None else node.text,
                    MAX_EVIDENCE_PACK_SNIPPET_CHARS,
                ),
                filing_type=_optional_str(node.metadata.get("filing_type")),
                filing_date=_optional_str(node.metadata.get("filing_date")),
                accession_number=_optional_str(node.metadata.get("accession_number")),
                score=round(node.rerank_score, 4),
                relevance_note=node.rerank_reason,
            )
        )
    return EvidencePack(
        run_id=result.run_id,
        ticker=result.ticker,
        task_type=result.task_type.value,
        query=_truncate_text(result.query, 520),
        filing_context=_filing_context_from_items(filing_items),
        metric_facts=[],
        filing_evidence=filing_items,
        retrieval_status=_evidence_pack_status(result),
        latency_ms=result.latency_ms,
    )


def _filing_context_from_raw_items(items: list[dict[str, object]]) -> EvidencePackFilingContext:
    if not items:
        return EvidencePackFilingContext()
    first_item = items[0]
    return EvidencePackFilingContext(
        filing_type=_optional_str(first_item.get("filing_type")),
        filing_date=_optional_str(first_item.get("filing_date")),
        accession_number=_optional_str(first_item.get("accession_number")),
    )


def _filing_context_from_items(items: list[EvidencePackItem]) -> EvidencePackFilingContext:
    if not items:
        return EvidencePackFilingContext()
    first_item = items[0]
    return EvidencePackFilingContext(
        filing_type=first_item.filing_type,
        filing_date=first_item.filing_date,
        accession_number=first_item.accession_number,
    )


def _evidence_pack_status(result: RetrieveEvidenceResult) -> str:
    if result.fallback_status.value == "none":
        return "ok"
    return result.fallback_status.value


def _merged_retrieval_status(
    results: list[RetrieveEvidenceResult],
    evidence_items: list[dict[str, object]],
) -> str:
    if any(result.fallback_status.value == "degraded" for result in results):
        return "degraded"
    if evidence_items:
        return "ok"
    return "empty"


def _evidence_pack_template(
    task_type: ResearchTaskType,
    focus: str | None,
) -> dict[str, list[str]]:
    focus_terms = f" {focus.strip()}" if focus and focus.strip() else ""
    if task_type == ResearchTaskType.LATEST_EARNINGS_READOUT:
        return {
            "sections": ["MD&A", "Net Sales", "Segment Information"],
            "queries": [
                (
                    "latest earnings evidence revenue gross margin operating income "
                    "net sales cost of sales expense discipline operating drivers"
                    + focus_terms
                ),
                (
                    "segment evidence products services geography demand pricing mix "
                    "operating income what changed"
                    + focus_terms
                ),
            ],
        }
    if task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        return {
            "sections": ["MD&A", "Business", "Net Sales", "Segment Information"],
            "queries": [
                (
                    "business driver evidence product segment customer demand pricing "
                    "volume mix channel geography what drove growth"
                    + focus_terms
                ),
                (
                    "strategy evidence services cloud data center AI subscriptions "
                    "enterprise customers competitive position"
                    + focus_terms
                ),
            ],
        }
    if task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        return {
            "sections": ["Liquidity and Capital Resources", "Cash Flows", "MD&A"],
            "queries": [
                "cash quality evidence operating cash flow free cash flow working capital"
                + focus_terms,
                (
                    "capital allocation evidence capex capital expenditures repurchases "
                    "dividends debt liquidity financing investing"
                )
                + focus_terms,
            ],
        }
    return {
        "sections": ["MD&A"],
        "queries": ["financial results operating drivers risks" + focus_terms],
    }


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _float_score(value: object) -> float:
    if isinstance(value, int | float | str):
        return float(value)
    return 0.0


def _budgeted_top_k(top_k: int) -> int:
    return max(1, min(top_k, MAX_EVIDENCE_PACK_ITEMS))


def _budget_evidence_item(item: dict[str, object]) -> dict[str, object]:
    snippet = item.get("snippet")
    if isinstance(snippet, str):
        item = {**item, "snippet": _truncate_text(snippet, MAX_EVIDENCE_PACK_SNIPPET_CHARS)}
    return item


def _merge_pack_queries(results: list[RetrieveEvidenceResult]) -> str:
    return _truncate_text(" | ".join(result.query for result in results), 700)


def _truncate_text(value: str, max_chars: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
