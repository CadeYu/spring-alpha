from __future__ import annotations

from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline


class LengthBiasedEmbeddingBackend:
    def embed(self, text: str) -> dict[str, float]:
        if len(text) < 120:
            return {"dim_0": 1.0, "dim_1": 0.0}
        if len(text) > 360:
            return {"dim_0": 1.0, "dim_1": 0.0}
        return {"dim_0": 0.0, "dim_1": 1.0}


def test_hybrid_pipeline_prioritizes_sparse_evidence_over_dense_noise() -> None:
    pipeline = LlamaIndexRagPipeline(
        enable_hybrid_retrieval=True,
        embedding_backend=LengthBiasedEmbeddingBackend(),
    )
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000040",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Cash flow liquidity debt maturities were discussed alongside capital allocation, pricing,
customer behavior, and product demand. The discussion repeated those same words many times
while adding broad filler about operations, execution, margin discipline, and resilience.
The section remains long enough for dense retrieval to overvalue it when sparse evidence is weak.

Liquidity and Capital Resources
Cash flow liquidity debt maturities were manageable and capital allocation remained disciplined.
""",
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_sparse_rescue",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        query="cash flow liquidity debt maturities",
        sections=["MD&A", "Liquidity and Capital Resources"],
        top_k=1,
    )

    assert result.source_refs
    assert result.source_refs[0].section == "Liquidity and Capital Resources"
    assert "manageable" in result.source_refs[0].snippet
