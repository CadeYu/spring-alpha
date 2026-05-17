from uuid import UUID

from llama_index.core.schema import NodeWithScore, TextNode
from pytest import MonkeyPatch

from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import (
    DatabaseConnection,
    DeterministicFinancialEmbeddingBackend,
    FilingDocument,
    GeminiEmbeddingBackend,
    InMemoryVectorStore,
    LlamaIndexRagPipeline,
    PgVectorStore,
    PgVectorStoreConfig,
    ProviderEmbeddingFallbackBackend,
    QdrantClientAdapter,
    QdrantVectorStore,
    QdrantVectorStoreConfig,
    RetrievalFallbackStatus,
    SectionAwareFilingParser,
    build_embedding_backend_from_env,
    build_production_rag_pipeline_from_env,
    build_vector_store_from_env,
)

FILING_TEXT = """
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue increased because demand improved and pricing remained disciplined.
The company discussed guidance and operating expenses.

Item 1A. Risk Factors
Competition, supply constraints, and regulation could affect future results.

Liquidity and Capital Resources
Operating cash flow funded capital expenditures and share repurchases.
Debt maturities remain manageable.
"""

NOISY_FILING_TEXT = """
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue grew modestly while management discussed pricing and product demand.

Item 1A. Risk Factors
Revenue revenue revenue revenue revenue could be affected by competition and regulation.

Liquidity and Capital Resources
Net cash provided by operating activities funded capital expenditures and repurchases
of common stock.
Debt maturities remain manageable and liquidity remains strong.
"""


def test_section_parser_extracts_sec_sections_with_metadata() -> None:
    filing = _filing_document()

    sections = SectionAwareFilingParser().parse(filing)

    assert [section.section for section in sections] == [
        "MD&A",
        "Risk Factors",
        "Liquidity and Capital Resources",
    ]
    assert sections[0].filing_type == "10-Q"
    assert sections[0].accession_number == "0000000000-26-000001"
    assert "Revenue increased" in sections[0].text


def test_pipeline_ingests_sections_as_llamaindex_text_nodes() -> None:
    pipeline = LlamaIndexRagPipeline()

    nodes = pipeline.ingest_filing(_filing_document())

    assert nodes
    assert all(isinstance(node, TextNode) for node in nodes)
    assert nodes[0].metadata["ticker"] == "TSLA"
    assert nodes[0].metadata["section"] == "MD&A"
    assert nodes[0].metadata["filing_type"] == "10-Q"
    assert nodes[0].metadata["accession_number"] == "0000000000-26-000001"


def test_pipeline_splits_long_sections_into_overlapping_windows() -> None:
    pipeline = LlamaIndexRagPipeline(
        section_chunk_max_chars=180,
        section_chunk_overlap_sentences=1,
    )
    filing = FilingDocument(
        ticker="AAPL",
        filing_type="10-Q",
        filing_date="2026-04-30",
        accession_number="0000000000-26-000040",
        text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue commentary was broad and included product demand context.
Services net sales increased because installed base engagement improved.
Segment operating income benefited from services mix and pricing discipline.
Liquidity commentary was not the focus of this operating section.
""",
    )

    nodes = pipeline.ingest_filing(filing)

    assert len(nodes) > 1
    assert {node.metadata["section"] for node in nodes} == {"MD&A"}
    assert all(node.metadata["section_chunk_count"] == len(nodes) for node in nodes)
    assert [node.metadata["section_chunk_index"] for node in nodes] == list(range(len(nodes)))
    assert any(
        "Services net sales increased" in nodes[index].get_content()
        and "Services net sales increased" in nodes[index + 1].get_content()
        for index in range(len(nodes) - 1)
    )


def test_pipeline_retrieves_relevant_window_not_entire_long_section() -> None:
    pipeline = LlamaIndexRagPipeline(
        section_chunk_max_chars=190,
        section_chunk_overlap_sentences=1,
    )
    filing = FilingDocument(
        ticker="AAPL",
        filing_type="10-Q",
        filing_date="2026-04-30",
        accession_number="0000000000-26-000041",
        text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Risk-style macro commentary mentioned regulation and supply uncertainty.
Services net sales increased because installed base engagement and subscriptions improved.
iPhone net sales reflected disciplined pricing and resilient demand.
Capital allocation commentary belonged elsewhere and should not dominate this window.
""",
    )
    pipeline.ingest_filing(filing)

    result = pipeline.retrieve_evidence(
        run_id="run_window_retrieval",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="services subscriptions installed base demand pricing",
        sections=["MD&A"],
        top_k=1,
    )

    assert result.source_refs
    assert "Services net sales increased" in result.source_refs[0].snippet
    assert "Capital allocation commentary" not in result.source_refs[0].snippet
    assert len(result.retrieved_nodes[0].text) < len(filing.text)


def test_pipeline_retrieves_task_relevant_source_refs() -> None:
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(_filing_document())

    result = pipeline.retrieve_evidence(
        run_id="run_rag_001",
        ticker="TSLA",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        query="operating cash flow capex debt liquidity",
        top_k=2,
    )

    assert result.query == "operating cash flow capex debt liquidity"
    assert result.fallback_status == RetrievalFallbackStatus.NONE
    assert result.retrieved_nodes
    assert result.source_refs
    assert result.source_refs[0].section == "Liquidity and Capital Resources"
    assert result.source_refs[0].filing_type == "10-Q"
    assert result.source_refs[0].citation_status == "unverified"
    assert result.retrieved_nodes[0].rerank_score >= result.retrieved_nodes[0].retrieval_score
    assert result.retrieved_nodes[0].rerank_score > 0
    assert result.retrieved_nodes[0].rerank_reason


def test_pipeline_prefers_requested_sections_over_noisy_keyword_matches() -> None:
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000020",
            text=NOISY_FILING_TEXT,
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_section_filter",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        query="revenue demand pricing",
        sections=["MD&A"],
        top_k=2,
    )

    assert result.source_refs
    assert result.source_refs[0].section == "MD&A"
    assert "competition and regulation" not in result.source_refs[0].snippet
    assert result.retrieved_nodes[0].rerank_reason == "section_filtered_financial_lexical_overlap"


def test_pipeline_expands_financial_query_terms_for_metric_evidence() -> None:
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000021",
            text=NOISY_FILING_TEXT,
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_query_expansion",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        query="operating cash flow capex buybacks",
        sections=["Liquidity and Capital Resources", "Cash Flow Statement"],
        top_k=1,
    )

    assert result.source_refs
    assert result.source_refs[0].section == "Liquidity and Capital Resources"
    assert "capital expenditures" in result.source_refs[0].snippet
    assert "repurchases of common stock" in result.source_refs[0].snippet


def test_business_driver_retrieval_prefers_operating_drivers_over_market_risk() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000030",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased due to higher customer engagement, stronger installed base
growth, and subscription demand.
Product revenue benefited from iPhone demand and disciplined pricing.

Quantitative and Qualitative Disclosures About Market Risk
Derivative instruments may be used to hedge foreign exchange and interest rate risk.
""",
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_business_quality",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="services product segment demand pricing customers strategy",
        sections=["MD&A", "Business", "Segment Information"],
        top_k=1,
    )

    assert result.source_refs
    assert result.source_refs[0].section == "MD&A"
    assert "Services revenue increased" in result.source_refs[0].snippet
    assert "Derivative instruments" not in result.source_refs[0].snippet


def test_business_driver_retrieval_prefers_sales_driver_window_over_compliance_window() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000032",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services net sales increased because customer engagement, installed base growth, and
subscription demand improved.
iPhone net sales reflected stronger customer demand and disciplined pricing.
Segment operating income improved as Services mix expanded.

Item 1. Business
Complying with emerging and changing requirements causes substantial costs and may
require changes to product designs and services.
""",
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_business_sales_window",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="product segment demand pricing customers strategy",
        sections=["MD&A", "Business", "Segment Information"],
        top_k=1,
    )

    assert result.source_refs
    assert "Services net sales increased" in result.source_refs[0].snippet
    assert "Complying with emerging" not in result.source_refs[0].snippet


def test_cash_allocation_query_expands_to_repurchase_dividend_and_capex_terms() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000031",
            text="""
Liquidity and Capital Resources
Net cash provided by operating activities funded capital expenditures, payments for
dividends and dividend equivalents, and repurchases of common stock.
The company also discussed liquidity and debt maturities.

Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue increased because product demand improved.
""",
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_cash_allocation_quality",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        query="cash flow capex buybacks dividends debt liquidity",
        sections=["Liquidity and Capital Resources", "Cash Flow Statement"],
        top_k=1,
    )

    assert result.source_refs
    assert result.source_refs[0].section == "Liquidity and Capital Resources"
    assert "capital expenditures" in result.source_refs[0].snippet
    assert "repurchases of common stock" in result.source_refs[0].snippet
    assert "dividends" in result.source_refs[0].snippet


def test_cash_allocation_snippet_keeps_capital_return_window() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000033",
            text="""
Liquidity and Capital Resources
The Company believes its balances of cash, cash equivalents and marketable securities,
along with cash generated by ongoing operations and continued access to debt markets,
will be sufficient to satisfy its cash requirements and capital return program over the
next 12 months and beyond.
Cash used in investing activities included capital expenditures.
Cash used in financing activities included repurchases of common stock and payments for
dividends and dividend equivalents.
""",
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_cash_window",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        query="operating cash flow capex buybacks dividends debt liquidity",
        sections=["Liquidity and Capital Resources", "Cash Flow Statement"],
        top_k=1,
    )

    assert result.source_refs
    assert "capital return program" in result.source_refs[0].snippet
    assert "capital expenditures" in result.source_refs[0].snippet
    assert "repurchases of common stock" in result.source_refs[0].snippet
    assert "dividends" in result.source_refs[0].snippet


def test_hybrid_pipeline_recovers_semantic_matches_without_exact_lexical_overlap() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="MSFT",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000023",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Management discussed revenue and operating income trends.

Segment Information
Intelligent Cloud growth was driven by Azure, server products, and enterprise services.
""",
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_hybrid_semantic",
        ticker="MSFT",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="enterprise support cloud platform",
        sections=["Segment Information"],
        top_k=1,
    )

    assert result.source_refs
    assert result.source_refs[0].section == "Segment Information"
    assert "Azure" in result.source_refs[0].snippet
    assert result.retrieved_nodes[0].rerank_reason == "hybrid_section_vector_lexical_overlap"


def test_hybrid_pipeline_uses_vector_similarity_boundary_for_semantic_retrieval() -> None:
    filing = FilingDocument(
        ticker="MSFT",
        filing_type="10-Q",
        filing_date="2026-04-30",
        accession_number="0000000000-26-000024",
        text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Management discussed revenue and operating income trends.

Segment Information
Azure, server products, and enterprise services drove Intelligent Cloud growth.
""",
    )
    lexical_pipeline = LlamaIndexRagPipeline()
    lexical_pipeline.ingest_filing(filing)
    hybrid_pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    hybrid_pipeline.ingest_filing(filing)

    lexical_result = lexical_pipeline.retrieve_evidence(
        run_id="run_lexical_miss",
        ticker="MSFT",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="platform support",
        sections=["Segment Information"],
        top_k=1,
    )
    hybrid_result = hybrid_pipeline.retrieve_evidence(
        run_id="run_vector_semantic",
        ticker="MSFT",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="platform support",
        sections=["Segment Information"],
        top_k=1,
    )

    assert lexical_result.fallback_status == RetrievalFallbackStatus.EMPTY
    assert hybrid_result.fallback_status == RetrievalFallbackStatus.NONE
    assert hybrid_result.source_refs[0].section == "Segment Information"
    assert "Azure" in hybrid_result.source_refs[0].snippet
    assert hybrid_result.retrieved_nodes[0].rerank_reason == (
        "hybrid_section_vector_lexical_overlap"
    )


def test_embedding_backend_env_factory_defaults_to_deterministic(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_EMBEDDING_PROVIDER", raising=False)

    backend = build_embedding_backend_from_env()

    assert isinstance(backend, DeterministicFinancialEmbeddingBackend)
    assert backend.embed("platform support")


def test_embedding_backend_env_factory_defaults_to_gemini_when_api_key_exists(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")

    backend = build_embedding_backend_from_env()

    assert isinstance(backend, GeminiEmbeddingBackend)
    assert backend.api_key == "test-gemini-key"


def test_hybrid_pipeline_degrades_to_deterministic_embedding_when_provider_is_unconfigured(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "siliconflow")
    monkeypatch.delenv("RAG_EMBEDDING_API_KEY", raising=False)
    filing = FilingDocument(
        ticker="MSFT",
        filing_type="10-Q",
        filing_date="2026-04-30",
        accession_number="0000000000-26-000025",
        text="""
Segment Information
Azure, server products, and enterprise services drove Intelligent Cloud growth.
""",
    )
    pipeline = LlamaIndexRagPipeline(
        enable_hybrid_retrieval=True,
        embedding_backend=build_embedding_backend_from_env(),
    )
    pipeline.ingest_filing(filing)

    result = pipeline.retrieve_evidence(
        run_id="run_embedding_provider_fallback",
        ticker="MSFT",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="platform support",
        sections=["Segment Information"],
        top_k=1,
    )

    assert result.fallback_status == RetrievalFallbackStatus.NONE
    assert result.source_refs[0].section == "Segment Information"
    assert "Azure" in result.source_refs[0].snippet
    assert result.retrieved_nodes[0].rerank_reason == "hybrid_section_vector_lexical_overlap"


def test_hybrid_pipeline_uses_env_embedding_backend_by_default(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "siliconflow")
    monkeypatch.delenv("RAG_EMBEDDING_API_KEY", raising=False)
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)

    assert isinstance(pipeline.embedding_backend, ProviderEmbeddingFallbackBackend)
    assert pipeline.embedding_backend.provider.value == "siliconflow"
    assert "not configured" in pipeline.embedding_backend.degraded_reason


def test_embedding_backend_env_factory_builds_gemini_backend_when_configured(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("RAG_EMBEDDING_API_KEY", "test-key")

    backend = build_embedding_backend_from_env()

    assert isinstance(backend, GeminiEmbeddingBackend)
    assert backend.model == "gemini-embedding-001"


def test_gemini_embedding_backend_calls_embed_content_api() -> None:
    calls: list[tuple[str, dict[str, object]]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        calls.append((url, payload))
        assert timeout_seconds == 8.0
        return {"embedding": {"values": [0.25, -0.5, 0.75]}}

    backend = GeminiEmbeddingBackend(api_key="test-key", transport=transport)

    vector = backend.embed("platform support")

    assert vector == {"dim_0": 0.25, "dim_1": -0.5, "dim_2": 0.75}
    assert calls == [
        (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-embedding-001:embedContent?key=test-key",
            {
                "model": "models/gemini-embedding-001",
                "content": {"parts": [{"text": "platform support"}]},
            },
        )
    ]


def test_in_memory_vector_store_upserts_and_searches_nodes() -> None:
    store = InMemoryVectorStore(DeterministicFinancialEmbeddingBackend())
    node = TextNode(
        id_="node_1",
        text="Azure, server products, and enterprise services drove cloud growth.",
        metadata={"section": "Segment Information"},
    )

    store.upsert(node)
    results = store.search(query="platform support", nodes=[node], top_k=1)

    assert results
    assert results[0].node.node_id == "node_1"
    assert float(results[0].score or 0.0) > 0


def test_hybrid_pipeline_accepts_vector_store_boundary() -> None:
    store = InMemoryVectorStore(DeterministicFinancialEmbeddingBackend())
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True, vector_store=store)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="MSFT",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000026",
            text="""
Segment Information
Azure, server products, and enterprise services drove Intelligent Cloud growth.
""",
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_vector_store_boundary",
        ticker="MSFT",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="platform support",
        sections=["Segment Information"],
        top_k=1,
    )

    assert result.fallback_status == RetrievalFallbackStatus.NONE
    assert result.source_refs[0].section == "Segment Information"
    assert pipeline.vector_store is store


def test_hybrid_pipeline_degrades_when_embedding_provider_fails_during_ingest() -> None:
    pipeline = LlamaIndexRagPipeline(
        enable_hybrid_retrieval=True,
        embedding_backend=FailingEmbeddingBackend(),
    )

    nodes = pipeline.ingest_filing(
        FilingDocument(
            ticker="MSFT",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000027",
            text="""
Segment Information
Azure, server products, and enterprise services drove Intelligent Cloud growth.
""",
        )
    )
    result = pipeline.retrieve_evidence(
        run_id="run_vector_provider_failure",
        ticker="MSFT",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="Azure cloud growth",
        sections=["Segment Information"],
        top_k=1,
    )

    assert nodes
    assert result.fallback_status == RetrievalFallbackStatus.DEGRADED
    assert result.source_refs
    assert result.source_refs[0].section == "Segment Information"


def test_hybrid_pipeline_degrades_when_vector_search_fails() -> None:
    pipeline = LlamaIndexRagPipeline(
        enable_hybrid_retrieval=True,
        vector_store=FailingVectorSearchStore(),
    )
    pipeline.ingest_filing(
        FilingDocument(
            ticker="MSFT",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000028",
            text="""
Segment Information
Azure cloud demand improved as enterprise customers adopted platform services.
""",
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_vector_search_failure",
        ticker="MSFT",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        query="Azure cloud demand platform",
        sections=["Segment Information"],
        top_k=1,
    )

    assert result.fallback_status == RetrievalFallbackStatus.DEGRADED
    assert result.source_refs
    assert "Azure cloud demand" in result.source_refs[0].snippet


def test_pgvector_store_config_normalizes_table_and_dimension() -> None:
    config = PgVectorStoreConfig(
        database_url="postgresql://example",
        table_name=" rag_chunks ",
        embedding_dimension=3072,
    )

    assert config.table_name == "rag_chunks"
    assert config.embedding_dimension == 3072


def test_pgvector_store_upserts_nodes_with_normalized_embedding() -> None:
    connection = RecordingConnection()
    store = PgVectorStore(
        config=PgVectorStoreConfig(
            database_url="postgresql://example",
            table_name="rag_chunks",
            embedding_dimension=3,
        ),
        embedding_backend=FixedEmbeddingBackend({"dim_0": 1.0, "dim_1": 1.0, "dim_2": 1.0}),
        connection_factory=lambda _: connection,
    )
    node = TextNode(
        id_="node_1",
        text="Azure and enterprise services drove cloud growth.",
        metadata={
            "ticker": "MSFT",
            "filing_type": "10-Q",
            "filing_date": "2026-04-30",
            "accession_number": "0000000000-26-000026",
            "section": "Segment Information",
        },
    )

    store.upsert(node)

    assert connection.commits == 1
    upsert_sql, upsert_params = connection.executed[-1]
    metadata = upsert_params["metadata"]
    assert "INSERT INTO rag_chunks" in upsert_sql
    assert upsert_params["node_id"] == "node_1"
    assert upsert_params["embedding"] == "[0.5773502692,0.5773502692,0.5773502692]"
    assert _metadata_value(metadata, "section") == "Segment Information"


def test_pgvector_store_searches_candidates_by_node_id() -> None:
    connection = RecordingConnection(
        rows=[
            {
                "node_id": "node_1",
                "score": 0.82,
            }
        ]
    )
    store = PgVectorStore(
        config=PgVectorStoreConfig(
            database_url="postgresql://example",
            table_name="rag_chunks",
            embedding_dimension=3,
        ),
        embedding_backend=DeterministicFinancialEmbeddingBackend(),
        connection_factory=lambda _: connection,
    )
    nodes = [
        TextNode(
            id_="node_1",
            text="Azure cloud growth.",
            metadata={"section": "Segment Information"},
        ),
        TextNode(id_="node_2", text="Generic risk factors.", metadata={"section": "Risk Factors"}),
    ]

    results = store.search(query="platform support", nodes=nodes, top_k=1)

    assert len(results) == 1
    assert results[0].node.node_id == "node_1"
    assert results[0].score == 0.82
    search_sql, search_params = connection.executed[-1]
    assert "WHERE node_id = ANY(%(node_ids)s)" in search_sql
    assert search_params["node_ids"] == ["node_1", "node_2"]
    assert search_params["limit"] == 1


def test_pgvector_store_initializes_schema_when_requested() -> None:
    connection = RecordingConnection()
    store = PgVectorStore(
        config=PgVectorStoreConfig(
            database_url="postgresql://example",
            table_name="rag_chunks",
            embedding_dimension=3,
        ),
        embedding_backend=DeterministicFinancialEmbeddingBackend(),
        connection_factory=lambda _: connection,
    )

    store.initialize_schema()

    assert connection.commits == 1
    executed_sql = "\n".join(query for query, _ in connection.executed)
    assert "CREATE EXTENSION IF NOT EXISTS vector" in executed_sql
    assert "CREATE TABLE IF NOT EXISTS rag_chunks" in executed_sql
    assert "embedding vector(3) NOT NULL" in executed_sql
    assert "CREATE INDEX IF NOT EXISTS rag_chunks_embedding_idx" in executed_sql


def test_pgvector_store_skips_hnsw_index_for_high_dimension_embeddings() -> None:
    connection = RecordingConnection()
    store = PgVectorStore(
        config=PgVectorStoreConfig(
            database_url="postgresql://example",
            table_name="rag_chunks",
            embedding_dimension=3072,
        ),
        embedding_backend=DeterministicFinancialEmbeddingBackend(),
        connection_factory=lambda _: connection,
    )

    store.initialize_schema()

    executed_sql = "\n".join(query for query, _ in connection.executed)
    assert "embedding vector(3072) NOT NULL" in executed_sql
    assert "USING hnsw" not in executed_sql


def test_vector_store_env_factory_builds_pgvector_store_when_configured(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_VECTOR_STORE_PROVIDER", "pgvector")
    monkeypatch.setenv("RAG_VECTOR_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("RAG_VECTOR_TABLE_NAME", "rag_chunks")
    monkeypatch.setenv("RAG_EMBEDDING_DIMENSION", "3")

    store = build_vector_store_from_env(DeterministicFinancialEmbeddingBackend())

    assert isinstance(store, PgVectorStore)
    assert store.config.table_name == "rag_chunks"
    assert store.config.embedding_dimension == 3


def test_vector_store_env_factory_defaults_to_pgvector_when_database_url_exists(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_VECTOR_STORE_PROVIDER", raising=False)
    monkeypatch.setenv("RAG_VECTOR_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("RAG_VECTOR_TABLE_NAME", "rag_chunks")
    monkeypatch.setenv("RAG_EMBEDDING_DIMENSION", "3")

    store = build_vector_store_from_env(DeterministicFinancialEmbeddingBackend())

    assert isinstance(store, PgVectorStore)
    assert store.config.table_name == "rag_chunks"
    assert store.config.embedding_dimension == 3


def test_qdrant_vector_store_upserts_nodes_with_payload_and_embedding() -> None:
    client = RecordingQdrantClient()
    store = QdrantVectorStore(
        config=QdrantVectorStoreConfig(
            url="https://qdrant.example",
            api_key="test-key",
            collection_name="spring_alpha_rag_chunks",
            embedding_dimension=3,
        ),
        embedding_backend=FixedEmbeddingBackend({"dim_0": 1.0, "dim_1": 1.0, "dim_2": 1.0}),
        client_factory=lambda config: client,
    )
    node = TextNode(
        id_="node_1",
        text="Azure and enterprise services drove cloud growth.",
        metadata={"ticker": "MSFT", "section": "Segment Information"},
    )

    store.upsert(node)

    assert len(client.upserted_points) == 1
    point = client.upserted_points[0]
    assert str(UUID(str(point["id"]))) == point["id"]
    assert point["vector"] == [0.5773502692, 0.5773502692, 0.5773502692]
    assert point["payload"]["node_id"] == "node_1"
    assert point["payload"]["text"] == "Azure and enterprise services drove cloud growth."
    assert point["payload"]["metadata"]["section"] == "Segment Information"


def test_qdrant_vector_store_ensures_collection_before_upsert() -> None:
    client = RecordingQdrantClient()
    adapter = QdrantClientAdapter(client)
    adapter.ensure_collection(collection_name="spring_alpha_rag_chunks", vector_size=3)

    assert client.collection_checks == ["spring_alpha_rag_chunks"]
    assert client.created_collections == [
        {
            "collection_name": "spring_alpha_rag_chunks",
            "vector_size": 3,
            "on_disk_payload": True,
        }
    ]

    store = QdrantVectorStore(
        config=QdrantVectorStoreConfig(
            url="https://qdrant.example",
            api_key="test-key",
            collection_name="spring_alpha_rag_chunks",
            embedding_dimension=3,
        ),
        embedding_backend=FixedEmbeddingBackend({"dim_0": 1.0, "dim_1": 0.0, "dim_2": 0.0}),
        client_factory=lambda config: adapter,
    )

    store.upsert(
        TextNode(
            id_="node_1",
            text="Azure and enterprise services drove cloud growth.",
            metadata={"ticker": "MSFT", "section": "Segment Information"},
        )
    )

    assert len(client.upserted_points) == 1


def test_qdrant_vector_store_upsert_many_batches_points() -> None:
    client = RecordingQdrantClient()
    store = QdrantVectorStore(
        config=QdrantVectorStoreConfig(
            url="https://qdrant.example",
            api_key="test-key",
            collection_name="spring_alpha_rag_chunks",
            embedding_dimension=3,
        ),
        embedding_backend=FixedEmbeddingBackend({"dim_0": 1.0, "dim_1": 0.0, "dim_2": 0.0}),
        client_factory=lambda config: client,
    )

    store.upsert_many(
        [
            TextNode(id_="node_1", text="First node", metadata={"ticker": "MSFT"}),
            TextNode(id_="node_2", text="Second node", metadata={"ticker": "MSFT"}),
        ]
    )

    assert len(client.upserted_points) == 2
    assert client.upsert_call_count == 1
    assert {point["payload"]["node_id"] for point in client.upserted_points} == {
        "node_1",
        "node_2",
    }


def test_qdrant_vector_store_searches_candidate_node_ids() -> None:
    client = RecordingQdrantClient(
        search_results=[
            {
                "id": "node_1",
                "score": 0.91,
            }
        ]
    )
    store = QdrantVectorStore(
        config=QdrantVectorStoreConfig(
            url="https://qdrant.example",
            api_key="test-key",
            collection_name="spring_alpha_rag_chunks",
            embedding_dimension=3,
        ),
        embedding_backend=DeterministicFinancialEmbeddingBackend(),
        client_factory=lambda config: client,
    )
    nodes = [
        TextNode(id_="node_1", text="Azure cloud growth.", metadata={"section": "Segment"}),
        TextNode(id_="node_2", text="Generic risk factors.", metadata={"section": "Risk"}),
    ]

    results = store.search(query="platform support", nodes=nodes, top_k=1)

    assert len(results) == 1
    assert results[0].node.node_id == "node_1"
    assert results[0].score == 0.91
    assert client.search_requests[-1]["limit"] == 1
    assert client.search_requests[-1]["node_ids"] == ["node_1", "node_2"]


def test_vector_store_env_factory_builds_qdrant_store_when_configured(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setenv("RAG_VECTOR_STORE_PROVIDER", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "https://qdrant.example")
    monkeypatch.setenv("QDRANT_API_KEY", "test-key")
    monkeypatch.setenv("QDRANT_COLLECTION", "spring_alpha_rag_chunks")
    monkeypatch.setenv("RAG_EMBEDDING_DIMENSION", "3")
    monkeypatch.setattr(
        "app.rag.llamaindex_pipeline.QdrantClientAdapter.connect",
        lambda config: RecordingQdrantClient(),
    )

    store = build_vector_store_from_env(DeterministicFinancialEmbeddingBackend())

    assert isinstance(store, QdrantVectorStore)
    assert store.config.collection_name == "spring_alpha_rag_chunks"
    assert store.config.embedding_dimension == 3


def test_production_rag_pipeline_env_factory_enables_hybrid_retrieval(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_VECTOR_STORE_PROVIDER", raising=False)
    monkeypatch.delenv("RAG_VECTOR_DATABASE_URL", raising=False)
    monkeypatch.delenv("RAG_EMBEDDING_PROVIDER", raising=False)
    monkeypatch.delenv("RAG_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    pipeline = build_production_rag_pipeline_from_env()

    assert pipeline.enable_hybrid_retrieval is True
    assert isinstance(pipeline.vector_store, InMemoryVectorStore)
    assert isinstance(pipeline.embedding_backend, DeterministicFinancialEmbeddingBackend)


class RecordingConnection:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = rows or []
        self.executed: list[tuple[str, dict[str, object]]] = []
        self.commits = 0

    def execute(self, query: str, params: dict[str, object]) -> list[dict[str, object]]:
        self.executed.append((query, params))
        return self.rows

    def commit(self) -> None:
        self.commits += 1

    def close(self) -> None:
        pass


class RecordingQdrantClient:
    def __init__(self, search_results: list[dict[str, object]] | None = None) -> None:
        self.search_results = search_results or []
        self.upserted_points: list[dict[str, object]] = []
        self.upsert_call_count = 0
        self.search_requests: list[dict[str, object]] = []
        self.collection_checks: list[str] = []
        self.created_collections: list[dict[str, object]] = []

    def collection_exists(self, collection_name: str) -> bool:
        self.collection_checks.append(collection_name)
        return False

    def create_collection(
        self,
        *,
        collection_name: str,
        vectors_config: object,
        on_disk_payload: bool = False,
    ) -> bool:
        self.created_collections.append(
            {
                "collection_name": collection_name,
                "vector_size": getattr(vectors_config, "size", None),
                "on_disk_payload": on_disk_payload,
            }
        )
        return True

    def upsert_points(
        self,
        *,
        collection_name: str,
        points: list[dict[str, object]],
    ) -> None:
        self.upsert_call_count += 1
        self.upserted_points.extend(points)

    def upsert(
        self,
        *,
        collection_name: str,
        points: list[object],
        wait: bool = True,
        ordering: object | None = None,
        shard_key_selector: object | None = None,
        update_filter: object | None = None,
        update_mode: object | None = None,
        timeout: int | None = None,
        **kwargs: object,
    ) -> object:
        self.upsert_call_count += 1
        self.upserted_points.extend(
            [
                {
                    "collection_name": collection_name,
                    "wait": wait,
                    "points": points,
                    "ordering": ordering,
                    "shard_key_selector": shard_key_selector,
                    "update_filter": update_filter,
                    "update_mode": update_mode,
                    "timeout": timeout,
                    "kwargs": kwargs,
                }
            ]
        )
        return {"status": "ok"}

    def search_points(
        self,
        *,
        collection_name: str,
        vector: list[float],
        node_ids: list[str],
        limit: int,
    ) -> list[dict[str, object]]:
        self.search_requests.append(
            {
                "collection_name": collection_name,
                "vector": vector,
                "node_ids": node_ids,
                "limit": limit,
            }
        )
        return self.search_results


class FixedEmbeddingBackend:
    def __init__(self, vector: dict[str, float]) -> None:
        self.vector = vector

    def embed(self, text: str) -> dict[str, float]:
        return self.vector


class FailingEmbeddingBackend:
    def embed(self, text: str) -> dict[str, float]:
        raise RuntimeError("embedding provider rate limited")


class FailingVectorSearchStore:
    def upsert(self, node: TextNode) -> None:
        pass

    def search(
        self,
        *,
        query: str,
        nodes: list[TextNode],
        top_k: int,
    ) -> list[NodeWithScore]:
        raise RuntimeError("embedding provider rate limited")


def _assert_database_connection_shape(connection: DatabaseConnection) -> None:
    assert connection is not None


def _metadata_value(metadata: object, key: str) -> object:
    if isinstance(metadata, dict):
        return metadata[key]
    wrapped = getattr(metadata, "obj", None)
    if isinstance(wrapped, dict):
        return wrapped[key]
    raise AssertionError("Metadata parameter must be a dict or Jsonb wrapper")


def test_pipeline_source_ref_snippet_is_centered_on_matched_terms() -> None:
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000000000-26-000022",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
This opening paragraph describes generic company background, reporting conventions,
and broad market context.
It intentionally has no useful metric evidence for the retrieval query.
Services revenue increased because installed base engagement improved and pricing
remained disciplined.
Gross margin benefited from mix and lower component costs.
""",
        )
    )

    result = pipeline.retrieve_evidence(
        run_id="run_snippet_window",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        query="services revenue gross margin",
        sections=["MD&A"],
        top_k=1,
    )

    snippet = result.source_refs[0].snippet
    assert snippet.startswith("Services revenue increased")
    assert "Gross margin benefited" in snippet
    assert "generic company background" not in snippet


def test_parser_supports_10k_business_mda_and_cash_flow_headings() -> None:
    filing = FilingDocument(
        ticker="MSFT",
        filing_type="10-K",
        filing_date="2026-06-30",
        accession_number="0000000000-26-000010",
        text="""
Item 1. Business
The company sells productivity software and cloud services.

Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations
Management discussed revenue, operating income, and demand.

Consolidated Statements of Cash Flows
Net cash provided by operating activities funded capital expenditures.
""",
    )

    sections = SectionAwareFilingParser().parse(filing)

    assert [section.section for section in sections] == [
        "Business",
        "MD&A",
        "Cash Flow Statement",
    ]


def test_reingesting_same_filing_does_not_duplicate_node_ids() -> None:
    pipeline = LlamaIndexRagPipeline()

    first_nodes = pipeline.ingest_filing(_filing_document())
    second_nodes = pipeline.ingest_filing(_filing_document())

    assert first_nodes
    assert second_nodes == []


def _filing_document() -> FilingDocument:
    return FilingDocument(
        ticker="TSLA",
        filing_type="10-Q",
        filing_date="2026-04-30",
        accession_number="0000000000-26-000001",
        text=FILING_TEXT,
    )
