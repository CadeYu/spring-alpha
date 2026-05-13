from llama_index.core.schema import TextNode
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
Services revenue increased due to higher customer engagement, stronger installed base growth, and subscription demand.
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
Services net sales increased because customer engagement, installed base growth, and subscription demand improved.
iPhone net sales reflected stronger customer demand and disciplined pricing.
Segment operating income improved as Services mix expanded.

Item 1. Business
Complying with emerging and changing requirements causes substantial costs and may require changes to product designs and services.
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
Net cash provided by operating activities funded capital expenditures, payments for dividends and dividend equivalents, and repurchases of common stock.
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
The Company believes its balances of cash, cash equivalents and marketable securities, along with cash generated by ongoing operations and continued access to debt markets, will be sufficient to satisfy its cash requirements and capital return program over the next 12 months and beyond.
Cash used in investing activities included capital expenditures.
Cash used in financing activities included repurchases of common stock and payments for dividends and dividend equivalents.
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


class FixedEmbeddingBackend:
    def __init__(self, vector: dict[str, float]) -> None:
        self.vector = vector

    def embed(self, text: str) -> dict[str, float]:
        return self.vector


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
