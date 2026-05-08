from llama_index.core.schema import TextNode
from pytest import MonkeyPatch

from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import (
    DeterministicFinancialEmbeddingBackend,
    FilingDocument,
    GeminiEmbeddingBackend,
    LlamaIndexRagPipeline,
    ProviderEmbeddingFallbackBackend,
    RetrievalFallbackStatus,
    SectionAwareFilingParser,
    build_embedding_backend_from_env,
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
