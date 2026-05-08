from app.agents.domain_tools import DeterministicResearchToolService, LlamaIndexResearchToolService
from app.agents.tool_registry import default_tool_registry
from app.contracts.agent import AgentState, ToolCall, default_task_policy
from app.contracts.research_task import ResearchTaskType
from app.contracts.tools import CitationVerificationInput
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline


def test_default_tool_registry_delegates_business_logic_to_domain_service() -> None:
    service = DeterministicResearchToolService()
    registry = default_tool_registry(service)
    state = AgentState(
        run_id="run_domain_001",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    updated = registry.execute(
        state,
        ToolCall(
            run_id=state.run_id,
            task_type=state.task_type,
            step_index=0,
            tool_name="search_filing_sections",
            tool_input={
                "sections": ["MD&A"],
                "query": "revenue margin drivers",
            },
            summary="Search filing evidence.",
        ),
    )

    assert updated.evidence_memory.source_refs[0]["source_id"] == "run_domain_001:filing:1"
    assert updated.retrieval_records[0]["tool_name"] == "search_filing_sections"


def test_llamaindex_domain_service_returns_live_section_evidence() -> None:
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000001",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased because demand improved and installed base engagement expanded.

Item 1A. Risk Factors
Supply constraints and competition could affect future results.
""",
        )
    )
    service = LlamaIndexResearchToolService(pipeline)
    registry = default_tool_registry(service)
    state = AgentState(
        run_id="run_domain_rag_001",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    updated = registry.execute(
        state,
        ToolCall(
            run_id=state.run_id,
            task_type=state.task_type,
            step_index=0,
            tool_name="search_filing_sections",
            tool_input={
                "sections": ["MD&A"],
                "query": "services revenue demand installed base",
            },
            summary="Search live filing evidence.",
        ),
    )

    source_ref = updated.evidence_memory.source_refs[0]
    retrieved_node = updated.retrieval_records[0]["retrieved_nodes"][0]

    assert source_ref["section"] == "MD&A"
    assert "Services revenue increased" in source_ref["snippet"]
    assert source_ref["filing_date"] == "2026-04-30"
    assert source_ref["accession_number"] == "0000320193-26-000001"
    assert retrieved_node["rerank_reason"] == "section_filtered_financial_lexical_overlap"


def test_llamaindex_domain_service_passes_requested_sections_to_rag_pipeline() -> None:
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000005",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue grew because services demand improved.

Item 1A. Risk Factors
Revenue revenue revenue revenue could be affected by supply constraints.
""",
        )
    )
    service = LlamaIndexResearchToolService(pipeline)
    registry = default_tool_registry(service)
    state = AgentState(
        run_id="run_domain_section_filter",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    updated = registry.execute(
        state,
        ToolCall(
            run_id=state.run_id,
            task_type=state.task_type,
            step_index=0,
            tool_name="search_filing_sections",
            tool_input={
                "sections": ["MD&A"],
                "query": "revenue services demand",
            },
            summary="Search requested section evidence.",
        ),
    )

    assert updated.evidence_memory.source_refs[0]["section"] == "MD&A"
    assert "supply constraints" not in updated.evidence_memory.source_refs[0]["snippet"]


def test_llamaindex_domain_service_returns_live_metric_evidence() -> None:
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000002",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue grew because services revenue, gross margin, and operating income improved.

Consolidated Statements of Cash Flows
Operating cash flow funded capital expenditures and share repurchases.
""",
        )
    )
    service = LlamaIndexResearchToolService(pipeline)
    registry = default_tool_registry(service)
    state = AgentState(
        run_id="run_domain_rag_metric",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    updated = registry.execute(
        state,
        ToolCall(
            run_id=state.run_id,
            task_type=state.task_type,
            step_index=0,
            tool_name="search_metric_evidence",
            tool_input={
                "metrics": ["revenue", "gross margin"],
                "period": "latest_quarter",
                "query": "revenue gross margin operating income",
            },
            summary="Search live metric evidence.",
        ),
    )

    source_ref = updated.evidence_memory.source_refs[0]
    metric_records = updated.evidence_memory.metric_evidence
    retrieved_node = updated.retrieval_records[0]["retrieved_nodes"][0]

    assert source_ref["section"] == "MD&A"
    assert "Revenue grew" in source_ref["snippet"]
    assert metric_records == [
        {
            "metric": "revenue",
            "period": "latest_quarter",
            "source_id": source_ref["source_id"],
        },
        {
            "metric": "gross margin",
            "period": "latest_quarter",
            "source_id": source_ref["source_id"],
        },
    ]
    assert retrieved_node["metadata"]["filing_type"] == "10-Q"


def test_domain_service_scores_claim_citation_support() -> None:
    service = DeterministicResearchToolService()
    state = AgentState(
        run_id="run_citation_001",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    result = service.verify_citations(
        CitationVerificationInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            claims=[
                {
                    "claim_id": "claim_supported",
                    "text": "Services revenue increased because demand improved.",
                },
                {
                    "claim_id": "claim_partial",
                    "text": (
                        "Services revenue increased because demand improved, margins expanded, "
                        "and new hardware channels accelerated."
                    ),
                },
                {
                    "claim_id": "claim_missing",
                    "text": "Hardware revenue declined because channel inventory rose.",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "MD&A",
                    "snippet": (
                        "Services revenue increased because demand improved and "
                        "installed base engagement expanded."
                    ),
                }
            ],
        ),
        state,
    )

    records = {record["claim_id"]: record for record in result.data["records"]}

    assert records["claim_supported"]["status"] == "supported"
    assert records["claim_partial"]["status"] == "partial"
    assert records["claim_missing"]["status"] == "missing"
    assert result.source_refs[0]["citation_status"] == "supported"
