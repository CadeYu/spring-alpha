from app.agents import domain_tools
from app.agents.domain_tools import (
    LlamaIndexResearchToolService,
    ResearchToolService,
    SecCompanyFactsProvider,
    YahooCompanyProfileProvider,
)
from app.contracts.agent import AgentState, default_task_policy
from app.contracts.research_task import ResearchTaskType
from app.contracts.tools import (
    BusinessSignalsInput,
    CompanyFactsInput,
    FilingSectionSearchInput,
    MetricEvidenceInput,
)
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline


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
    state = AgentState(
        run_id="run_domain_rag_001",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    result = service.search_filing_sections(
        FilingSectionSearchInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            sections=["MD&A"],
            query="services revenue demand installed base",
        ),
        state,
    )

    source_ref = result.source_refs[0]
    retrieved_node = result.data["retrieved_nodes"][0]

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
    state = AgentState(
        run_id="run_domain_section_filter",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    result = service.search_filing_sections(
        FilingSectionSearchInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            sections=["MD&A"],
            query="revenue services demand",
        ),
        state,
    )

    assert result.source_refs[0]["section"] == "MD&A"
    assert "supply constraints" not in result.source_refs[0]["snippet"]


def test_business_driver_domain_service_guards_against_market_risk_drift() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000007",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased because demand improved and installed base engagement expanded.
Product revenue benefited from iPhone demand and disciplined pricing.

Quantitative and Qualitative Disclosures About Market Risk
Derivative instruments may be used to hedge foreign exchange and interest rate risk.
""",
        )
    )
    service = LlamaIndexResearchToolService(pipeline)
    state = AgentState(
        run_id="run_domain_business_guardrail",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        task_policy=default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE),
    )

    result = service.search_filing_sections(
        tool_input=FilingSectionSearchInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            sections=["MD&A"],
            query="derivative hedging market risk",
            limit=1,
        ),
        state=state,
    )

    assert result.source_refs
    assert result.source_refs[0]["section"] == "MD&A"
    assert "Services revenue increased" in result.source_refs[0]["snippet"]
    assert "Derivative instruments" not in result.source_refs[0]["snippet"]


def test_business_driver_domain_service_prioritizes_operating_drivers_over_compliance() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000009",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services net sales increased because customer engagement, installed base growth, and subscription demand improved.
Products net sales benefited from iPhone demand, channel inventory normalization, and disciplined pricing.
Segment operating income improved as Services mix expanded.

Item 1. Business
Complying with emerging and changing requirements causes substantial costs and may require product design changes.
""",
        )
    )
    service = LlamaIndexResearchToolService(pipeline)
    state = AgentState(
        run_id="run_domain_business_operating_priority",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        task_policy=default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE),
    )

    result = service.search_filing_sections(
        tool_input=FilingSectionSearchInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            sections=["MD&A", "Business"],
            query="product segment demand pricing customers strategy",
            limit=1,
        ),
        state=state,
    )

    assert result.source_refs
    snippet = str(result.source_refs[0]["snippet"])
    assert "Services net sales increased" in snippet
    assert "Complying with emerging" not in snippet


def test_cash_flow_domain_service_expands_allocation_terms() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000008",
            text="""
Liquidity and Capital Resources
Net cash provided by operating activities funded capital expenditures, payments for dividends and dividend equivalents, and repurchases of common stock.
Debt maturities remain manageable and liquidity remains strong.
""",
        )
    )
    service = LlamaIndexResearchToolService(pipeline)
    state = AgentState(
        run_id="run_domain_cash_guardrail",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
    )

    result = service.search_metric_evidence(
        tool_input=MetricEvidenceInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            metrics=["operating cash flow"],
            period="latest_quarter",
            query="cash flow",
        ),
        state=state,
    )

    assert result.source_refs
    snippet = str(result.source_refs[0]["snippet"])
    assert "capital expenditures" in snippet
    assert "repurchases of common stock" in snippet
    assert "dividends" in snippet


def test_metric_evidence_records_include_sec_companyfacts_values() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000021",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Net sales increased because services revenue improved.
Gross margin expanded as Services mix improved.
Operating income increased with disciplined expense management.
""",
        )
    )
    service = LlamaIndexResearchToolService(pipeline)
    state = AgentState(
        run_id="run_domain_metric_values",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )
    state = state.model_copy(
        update={
            "evidence_memory": state.evidence_memory.model_copy(
                update={
                    "facts": {
                        "period": "latest_quarter",
                        "metrics": [
                            {
                                "name": "revenue",
                                "value": 95359000000,
                                "unit": "USD",
                                "period": "2026Q2",
                                "form": "10-Q",
                                "filed": "2026-05-01",
                                "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                            },
                            {
                                "name": "gross margin",
                                "value": 45000000000,
                                "unit": "USD",
                                "period": "2026Q2",
                                "form": "10-Q",
                                "filed": "2026-05-01",
                                "concept": "GrossProfit",
                            },
                        ],
                    }
                }
            )
        }
    )

    result = service.search_metric_evidence(
        tool_input=MetricEvidenceInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            metrics=["revenue", "gross margin"],
            period="latest_quarter",
            query="revenue gross margin operating income",
        ),
        state=state,
    )

    records = result.data["records"]
    assert records[0]["metric"] == "revenue"
    assert records[0]["value"] == 95359000000
    assert records[0]["unit"] == "USD"
    assert records[0]["source"] == "sec_companyfacts"
    assert records[1]["metric"] == "gross margin"
    assert records[1]["value"] == 45000000000
    assert "snippet" in records[1]
    assert records[0]["source_id"].endswith(":sec_companyfacts:revenue")
    assert records[1]["source_id"].endswith(":sec_companyfacts:gross-margin")
    fact_refs = [
        ref
        for ref in result.source_refs
        if str(ref.get("section")) == "SEC companyfacts"
    ]
    assert len(fact_refs) == 2
    assert str(fact_refs[0]["snippet"]).startswith(
        "SEC companyfacts RevenueFromContractWithCustomerExcludingAssessedTax reports revenue of 95359000000 USD"
    )


def test_latest_quarter_companyfacts_prefers_instant_quarter_frame_over_ytd_fact() -> None:
    companyfacts = {
        "facts": {
            "us-gaap": {
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "val": 219659000000,
                                "fy": 2026,
                                "fp": "Q2",
                                "form": "10-Q",
                                "filed": "2026-05-01",
                                "accn": "0000320193-26-000002",
                            },
                            {
                                "val": 111184000000,
                                "fy": 2026,
                                "fp": "Q2",
                                "form": "10-Q",
                                "filed": "2026-05-01",
                                "accn": "0000320193-26-000002",
                                "frame": "CY2026Q1",
                            },
                        ]
                    },
                }
            }
        }
    }

    record = domain_tools._latest_metric_record(
        companyfacts,
        "revenue",
        "latest_quarter",
    )

    assert record is not None
    assert record["value"] == 111184000000
    assert record["period"] == "2026Q2"


def test_cash_flow_domain_service_collects_diverse_allocation_evidence() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000018",
            text="""
Liquidity and Capital Resources
The Company believes cash, cash equivalents, marketable securities, and access to debt markets provide sufficient liquidity.
Net cash provided by operating activities remained strong during the quarter.
Capital expenditures reflected payments to acquire property, plant and equipment.
The Company returned capital through repurchases of common stock and dividends.
Debt maturities remain manageable.
""",
        )
    )
    service = LlamaIndexResearchToolService(pipeline)
    state = AgentState(
        run_id="run_domain_cash_diverse",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
    )

    result = service.search_filing_sections(
        tool_input=FilingSectionSearchInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            sections=["Liquidity and Capital Resources"],
            query="cash flow capex buybacks dividends debt liquidity",
            limit=5,
        ),
        state=state,
    )

    snippets = " ".join(str(ref["snippet"]).lower() for ref in result.source_refs)
    assert "operating activities" in snippets
    assert "capital expenditures" in snippets
    assert "repurchases of common stock" in snippets
    assert "dividends" in snippets
    assert "debt" in snippets
    assert len(result.source_refs) >= 2


def test_latest_earnings_domain_service_prioritizes_operating_results_over_risk() -> None:
    pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000019",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Net sales increased because services revenue, product demand, and gross margin improved.

Item 1A. Risk Factors
The Company expects these trends to intensify and materially adversely affect demand.
""",
        )
    )
    service = LlamaIndexResearchToolService(pipeline)
    state = AgentState(
        run_id="run_domain_latest_operating",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    result = service.search_filing_sections(
        tool_input=FilingSectionSearchInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            sections=["MD&A", "Risk Factors"],
            query="latest earnings revenue margin drivers risks",
            limit=1,
        ),
        state=state,
    )

    assert result.source_refs
    assert result.source_refs[0]["section"] == "MD&A"
    assert "Net sales increased" in result.source_refs[0]["snippet"]
    assert "materially adversely affect demand" not in result.source_refs[0]["snippet"]


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
    state = AgentState(
        run_id="run_domain_rag_metric",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )

    result = service.search_metric_evidence(
        MetricEvidenceInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            metrics=["revenue", "gross margin"],
            period="latest_quarter",
            query="revenue gross margin operating income",
        ),
        state,
    )

    source_ref = result.source_refs[0]
    metric_records = result.data["records"]
    retrieved_node = result.data["retrieved_nodes"][0]

    assert source_ref["section"] == "MD&A"
    assert "Revenue grew" in source_ref["snippet"]
    assert metric_records[0]["metric"] == "revenue"
    assert metric_records[0]["normalized_metric"] == "revenue"
    assert metric_records[0]["period"] == "latest_quarter"
    assert metric_records[0]["source_id"] == source_ref["source_id"]
    assert "Revenue grew" in str(metric_records[0]["snippet"])
    assert metric_records[1]["metric"] == "gross margin"
    assert metric_records[1]["normalized_metric"] == "gross margin"
    assert metric_records[1]["source_id"] == source_ref["source_id"]
    assert retrieved_node["metadata"]["filing_type"] == "10-Q"


def test_domain_service_extracts_business_signals_from_existing_evidence() -> None:
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000006",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased because demand improved and installed base engagement expanded.
Gross margin benefited from favorable mix and pricing.

Item 1A. Risk Factors
Supply constraints and competitive pressure could affect future results.
""",
        )
    )
    service = LlamaIndexResearchToolService(pipeline)
    state = AgentState(
        run_id="run_domain_business_signals",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        task_policy=default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE),
    )

    evidence_result = service.search_filing_sections(
        FilingSectionSearchInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            sections=["MD&A", "Risk Factors"],
            query="services demand installed base pricing supply constraints competition",
        ),
        state,
    )
    with_evidence = state.model_copy(
        update={
            "evidence_memory": state.evidence_memory.model_copy(
                update={"source_refs": evidence_result.source_refs}
            )
        }
    )
    result = service.get_business_signals(
        BusinessSignalsInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            signal_types=["product", "demand", "pricing", "risk"],
        ),
        with_evidence,
    )

    signal_records = result.data["records"]
    signal_types = {record["signal_type"] for record in signal_records}

    assert "business_driver_placeholder" not in str(signal_records)
    assert {"product", "demand"}.issubset(signal_types)
    assert any(record["signal_type"] == "pricing" for record in signal_records)
    assert all(record["source_id"] for record in signal_records)
    assert all(record["section"] in {"MD&A", "Risk Factors"} for record in signal_records)
    assert all(record["snippet"] for record in signal_records)
    assert all(record["citation_status"] == "unverified" for record in signal_records)


def test_domain_service_does_not_invent_business_signals_without_evidence() -> None:
    service = ResearchToolService()
    state = AgentState(
        run_id="run_domain_no_business_signals",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        task_policy=default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE),
    )

    result = service.get_business_signals(
        BusinessSignalsInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            signal_types=["demand"],
        ),
        state,
    )

    assert result.status == "empty"
    assert result.data == {"records": []}
    assert result.degraded_reasons == ["No evidence available for business signal extraction."]


def test_domain_service_returns_sec_company_facts() -> None:
    service = ResearchToolService(
        facts_provider=SecCompanyFactsProvider(
            transport=fake_sec_transport,
            profile_provider=YahooCompanyProfileProvider(transport=fake_yahoo_transport),
        )
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
    assert result.data["business_summary"].startswith(
        "Apple designs consumer electronics, software, and services"
    )
    assert result.data["marketBusinessSummary"] == result.data["business_summary"]
    assert result.data["profile_source"] == "yahoo_quote_summary"
    assert result.data["sector"] == "Technology"
    assert result.data["industry"] == "Consumer Electronics"
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
    service = ResearchToolService(
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


def test_domain_service_drops_stale_metrics_outside_latest_reporting_cohort() -> None:
    service = ResearchToolService(
        facts_provider=SecCompanyFactsProvider(transport=fake_stale_metric_sec_transport)
    )
    state = AgentState(
        run_id="run_domain_stale_metric",
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
            metrics=["revenue", "gross margin", "operating income"],
        ),
        state,
    )

    assert result.status == "partial"
    assert [metric["name"] for metric in result.data["metrics"]] == [
        "revenue",
        "operating income",
    ]
    assert result.data["missing_metrics"] == ["gross margin"]


def test_domain_service_accepts_common_llm_metric_aliases() -> None:
    service = ResearchToolService(
        facts_provider=SecCompanyFactsProvider(transport=fake_sec_transport)
    )
    state = AgentState(
        run_id="run_domain_facts_aliases",
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
            metrics=["totalRevenue", "grossProfit", "operatingIncome"],
        ),
        state,
    )

    assert result.status == "ok"
    assert [metric["name"] for metric in result.data["metrics"]] == [
        "revenue",
        "gross profit",
        "operating income",
    ]
    assert result.data["missing_metrics"] == []


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
                    "OperatingIncomeLoss": {
                        "label": "Operating Income",
                        "units": {
                            "USD": [
                                {
                                    "val": 28000000000,
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


def fake_stale_metric_sec_transport(url: str, timeout_seconds: float) -> dict[str, object]:
    payload = fake_sec_transport(url, timeout_seconds)
    if not url.endswith("/CIK0000320193.json"):
        return payload
    facts = payload["facts"]["us-gaap"]
    facts["GrossProfit"] = {
        "label": "Gross Profit",
        "units": {
            "USD": [
                {
                    "val": 999000000,
                    "fy": 2009,
                    "fp": "Q3",
                    "form": "10-Q",
                    "filed": "2009-10-23",
                    "accn": "0001193125-09-212134",
                    "frame": "CY2009Q3",
                }
            ]
        },
    }
    return payload


def fake_yahoo_transport(url: str, timeout_seconds: float) -> dict[str, object]:
    assert "quoteSummary/AAPL" in url
    return {
        "quoteSummary": {
            "result": [
                {
                    "assetProfile": {
                        "longBusinessSummary": (
                            "Apple designs consumer electronics, software, and services "
                            "for a global customer base."
                        ),
                        "sector": "Technology",
                        "industry": "Consumer Electronics",
                    },
                    "price": {
                        "longName": "Apple Inc.",
                        "quoteType": "EQUITY",
                    },
                }
            ],
            "error": None,
        }
    }
