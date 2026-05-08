import os
from uuid import uuid4

import pytest

from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import (
    DeterministicFinancialEmbeddingBackend,
    FilingDocument,
    LlamaIndexRagPipeline,
    PgVectorStore,
    PgVectorStoreConfig,
)


@pytest.mark.integration
def test_pgvector_store_retrieves_rag_evidence_against_real_database() -> None:
    database_url = os.getenv("RAG_PGVECTOR_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("RAG_PGVECTOR_TEST_DATABASE_URL is required for PGVector integration tests")

    table_name = f"rag_it_{uuid4().hex}"
    embedding_backend = DeterministicFinancialEmbeddingBackend()
    store = PgVectorStore(
        config=PgVectorStoreConfig(
            database_url=database_url,
            table_name=table_name,
            embedding_dimension=32,
        ),
        embedding_backend=embedding_backend,
    )
    store.initialize_schema()
    pipeline = LlamaIndexRagPipeline(
        enable_hybrid_retrieval=True,
        embedding_backend=embedding_backend,
        vector_store=store,
    )
    pipeline.ingest_filing(
        FilingDocument(
            ticker="MSFT",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000030",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Management discussed revenue and operating income trends.

Segment Information
Azure, server products, and enterprise services drove Intelligent Cloud growth.
""",
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_pgvector_integration",
        ticker="MSFT",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="platform support",
        sections=["Segment Information"],
        top_k=1,
    )

    assert result.source_refs
    assert result.source_refs[0].section == "Segment Information"
    assert "Azure" in result.source_refs[0].snippet
