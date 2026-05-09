from app.agents.domain_tools import (
    DeterministicResearchToolService,
    LlamaIndexResearchToolService,
    SecCompanyFactsProvider,
)
from app.agents.tool_registry import default_tool_registry
from app.contracts.agent import AgentState, ToolCall, default_task_policy
from app.contracts.research_task import ResearchTaskType
from app.contracts.tools import CitationVerificationInput, CompanyFactsInput
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


def test_domain_service_returns_sec_company_facts() -> None:
    service = DeterministicResearchToolService(
        facts_provider=SecCompanyFactsProvider(transport=fake_sec_transport)
    )
    state = AgentState(
        run_id="run_domain_facts",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    result = service.get_company_facts(
        CompanyFactsInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            period="latest_quarter",
            metrics=["revenue", "gross margin", "operating cash flow"],
        ),
        state,
    )

    assert result.status == "ok"
    assert result.data["source"] == "sec_companyfacts"
    assert result.data["period"] == "latest_quarter"
    assert result.data["metrics"] == [
        {
            "name": "revenue",
            "label": "Revenue from Contract with Customer, Excluding Assessed Tax",
            "value": 90000000000,
            "unit": "USD",
            "period": "2026Q1",
            "fy": 2026,
            "fp": "Q1",
            "form": "10-Q",
            "filed": "2026-02-01",
            "accession_number": "0000320193-26-000001",
            "taxonomy": "us-gaap",
            "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
        },
        {
            "name": "gross margin",
            "label": "Gross Profit",
            "value": 41000000000,
            "unit": "USD",
            "period": "2026Q1",
            "fy": 2026,
            "fp": "Q1",
            "form": "10-Q",
            "filed": "2026-02-01",
            "accession_number": "0000320193-26-000001",
            "taxonomy": "us-gaap",
            "concept": "GrossProfit",
        },
        {
            "name": "operating cash flow",
            "label": "Net Cash Provided by Used in Operating Activities",
            "value": 29000000000,
            "unit": "USD",
            "period": "2026Q1",
            "fy": 2026,
            "fp": "Q1",
            "form": "10-Q",
            "filed": "2026-02-01",
            "accession_number": "0000320193-26-000001",
            "taxonomy": "us-gaap",
            "concept": "NetCashProvidedByUsedInOperatingActivities",
        },
    ]


def test_domain_service_marks_company_facts_partial_when_metrics_are_missing() -> None:
    service = DeterministicResearchToolService(
        facts_provider=SecCompanyFactsProvider(transport=fake_sec_transport)
    )
    state = AgentState(
        run_id="run_domain_facts_missing",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    result = service.get_company_facts(
        CompanyFactsInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            period="latest_quarter",
            metrics=["free cash flow"],
        ),
        state,
    )

    assert result.status == "partial"
    assert result.data["metrics"] == []
    assert result.data["missing_metrics"] == ["free cash flow"]
    assert result.degraded_reasons == ["SEC company facts missing metrics: free cash flow"]


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


def fake_sec_transport(url: str, timeout_seconds: float) -> dict[str, object]:
    if url.endswith("/company_tickers.json"):
        return {
            "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        }
    if url.endswith("/CIK0000320193.json"):
        return {
            "cik": 320193,
            "entityName": "Apple Inc.",
            "facts": {
                "us-gaap": {
                    "RevenueFromContractWithCustomerExcludingAssessedTax": {
                        "label": "Revenue from Contract with Customer, Excluding Assessed Tax",
                        "units": {
                            "USD": [
                                {
                                    "val": 88000000000,
                                    "fy": 2025,
                                    "fp": "Q4",
                                    "form": "10-Q",
                                    "filed": "2025-11-01",
                                    "accn": "0000320193-25-000010",
                                    "frame": "CY2025Q4",
                                },
                                {
                                    "val": 90000000000,
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-02-01",
                                    "accn": "0000320193-26-000001",
                                    "frame": "CY2026Q1",
                                },
                            ]
                        },
                    },
                    "GrossProfit": {
                        "label": "Gross Profit",
                        "units": {
                            "USD": [
                                {
                                    "val": 41000000000,
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-02-01",
                                    "accn": "0000320193-26-000001",
                                    "frame": "CY2026Q1",
                                }
                            ]
                        },
                    },
                    "NetCashProvidedByUsedInOperatingActivities": {
                        "label": "Net Cash Provided by Used in Operating Activities",
                        "units": {
                            "USD": [
                                {
                                    "val": 29000000000,
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-02-01",
                                    "accn": "0000320193-26-000001",
                                    "frame": "CY2026Q1",
                                }
                            ]
                        },
                    },
                }
            },
        }
    raise AssertionError(f"Unexpected SEC URL: {url}")
