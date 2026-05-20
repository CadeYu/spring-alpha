from __future__ import annotations

from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline


def test_retrieve_evidence_reuses_cached_result_for_identical_request() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=False)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AMD",
            filing_type="10-Q",
            filing_date="2026-03-31",
            accession_number="0001",
            text=(
                "Item 2. Management's Discussion and Analysis of Financial Condition "
                "and Results of Operations\n"
                "Revenue increased because data center GPU sales and client processor "
                "demand improved. Operating income expanded as gross margin improved."
            ),
        )
    )
    retrieve_calls = 0
    original_retrieve_candidates = pipeline._retrieve_candidates

    def counting_retrieve_candidates(**kwargs):
        nonlocal retrieve_calls
        retrieve_calls += 1
        return original_retrieve_candidates(**kwargs)

    pipeline._retrieve_candidates = counting_retrieve_candidates  # type: ignore[method-assign]

    first_result = pipeline.retrieve_evidence(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        query="revenue operating income",
        sections=["MD&A"],
        top_k=3,
    )
    second_result = pipeline.retrieve_evidence(
        run_id="run_2",
        ticker="AMD",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        query="revenue operating income",
        sections=["MD&A"],
        top_k=3,
    )

    assert retrieve_calls == 1
    assert first_result.run_id == "run_1"
    assert second_result.run_id == "run_2"
    assert first_result.retrieved_nodes == second_result.retrieved_nodes
    assert first_result.source_refs == second_result.source_refs
