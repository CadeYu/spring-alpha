from __future__ import annotations

from app.agents.domain_tools import (
    LlamaIndexResearchToolService,
    ResearchToolService,
    SecCompanyFactsProvider,
)
from app.agents.evidence_pack_tool import create_agent_evidence_pack_tool
from app.contracts.agent import AgentState, EvidenceMemory, TaskPolicy, ToolStatus
from app.contracts.report import SourceRef
from app.contracts.research_task import ResearchTaskType
from app.contracts.tools import (
    CompanyFactsInput,
    FilingSectionSearchInput,
    MarketContextInput,
    MetricEvidenceInput,
)
from app.rag.llamaindex_pipeline import RetrievalFallbackStatus, RetrieveEvidenceResult


class _FailingFactsProvider(SecCompanyFactsProvider):
    def __init__(self) -> None:
        self.calls = 0

    def fetch_company_facts(
        self,
        *,
        ticker: str,
        period: str | None,
        metrics: list[str],
    ) -> dict[str, object]:
        self.calls += 1
        raise AssertionError("preloaded complete facts should be reused")


class _MissingMappingFactsProvider(SecCompanyFactsProvider):
    def __init__(self) -> None:
        self.calls = 0

    def fetch_company_facts(
        self,
        *,
        ticker: str,
        period: str | None,
        metrics: list[str],
    ) -> dict[str, object]:
        self.calls += 1
        raise ValueError(f"SEC ticker mapping not found for {ticker}")


class _CountingPipeline:
    def __init__(self) -> None:
        self.calls = 0
        self.queries: list[str] = []

    def retrieve_evidence(self, **kwargs):
        self.calls += 1
        self.queries.append(str(kwargs["query"]))
        raise AssertionError("metric evidence should use preloaded facts before RAG")


class _RecordingPipeline:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def retrieve_evidence(self, **kwargs):
        self.queries.append(str(kwargs["query"]))
        source_ref = SourceRef(
            source_id=f"{kwargs['run_id']}:rag:{len(self.queries)}",
            section="Cash Flow Statement",
            snippet=f"Fallback evidence for {kwargs['query']}.",
        )
        return RetrieveEvidenceResult(
            run_id=str(kwargs["run_id"]),
            ticker=str(kwargs["ticker"]),
            task_type=kwargs["task_type"],
            query=str(kwargs["query"]),
            retrieved_nodes=[],
            source_refs=[source_ref],
            fallback_status=RetrievalFallbackStatus.NONE,
        )


class _EvidencePackRecordingPipeline:
    def __init__(self) -> None:
        self.queries: list[str] = []

    def retrieve_evidence(self, **kwargs):
        self.queries.append(str(kwargs["query"]))
        source_ref = SourceRef(
            source_id=f"{kwargs['run_id']}:rag:{len(self.queries)}",
            section="MD&A",
            snippet=f"Evidence for {kwargs['query']}.",
        )
        return RetrieveEvidenceResult(
            run_id=str(kwargs["run_id"]),
            ticker=str(kwargs["ticker"]),
            task_type=kwargs["task_type"],
            query=str(kwargs["query"]),
            retrieved_nodes=[],
            source_refs=[source_ref],
            fallback_status=RetrievalFallbackStatus.NONE,
        )


def test_get_company_facts_reuses_preloaded_complete_facts_without_fetching() -> None:
    provider = _FailingFactsProvider()
    service = LlamaIndexResearchToolService(_CountingPipeline(), facts_provider=provider)  # type: ignore[arg-type]
    state = _state_with_facts(
        metrics=[
            {"name": "revenue", "value": 25_500_000_000, "unit": "USD"},
            {"name": "gross margin", "value": 0.1823, "unit": "pure"},
            {"name": "operating income", "value": 2_100_000_000, "unit": "USD"},
        ]
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

    assert result.status == ToolStatus.OK
    assert provider.calls == 0
    assert result.data["source"] == "preloaded_financial_facts"
    assert result.data["metrics"] == state.evidence_memory.facts["metrics"]


def test_get_company_facts_returns_preloaded_partial_facts_when_sec_mapping_is_missing() -> None:
    provider = _MissingMappingFactsProvider()
    service = LlamaIndexResearchToolService(_CountingPipeline(), facts_provider=provider)  # type: ignore[arg-type]
    state = _state_with_facts(
        metrics=[
            {"name": "revenue", "value": 7_100_000_000, "unit": "USD"},
        ]
    ).model_copy(update={"ticker": "PARA"})

    result = service.get_company_facts(
        CompanyFactsInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            period="latest_quarter",
            metrics=["revenue", "gross margin", "operating income"],
        ),
        state.model_copy(update={"task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE}),
    )

    assert provider.calls == 1
    assert result.status == ToolStatus.PARTIAL
    assert result.data["ticker"] == "PARA"
    assert result.data["source"] == "preloaded_financial_facts"
    assert result.data["metrics"] == state.evidence_memory.facts["metrics"]
    assert result.data["missing_metrics"] == ["gross margin", "operating income"]
    assert "SEC ticker mapping not found for PARA" in result.degraded_reasons[0]


def test_get_company_facts_returns_empty_when_sec_mapping_is_missing_without_preloaded_facts() -> (
    None
):
    provider = _MissingMappingFactsProvider()
    service = LlamaIndexResearchToolService(_CountingPipeline(), facts_provider=provider)  # type: ignore[arg-type]
    state = _state_with_facts(metrics=[]).model_copy(
        update={
            "ticker": "DFS",
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(facts={}),
        }
    )

    result = service.get_company_facts(
        CompanyFactsInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            period="latest_quarter",
            metrics=["revenue", "gross margin"],
        ),
        state,
    )

    assert provider.calls == 1
    assert result.status == ToolStatus.EMPTY
    assert result.data["ticker"] == "DFS"
    assert result.data["metrics"] == ["revenue", "gross margin"]
    assert "SEC ticker mapping not found for DFS" in result.degraded_reasons[0]


def test_search_metric_evidence_uses_preloaded_facts_without_rag_when_all_metrics_exist() -> None:
    pipeline = _CountingPipeline()
    service = LlamaIndexResearchToolService(pipeline, facts_provider=None)  # type: ignore[arg-type]
    state = _state_with_facts(
        metrics=[
            {
                "name": "operating cash flow",
                "value": 4_200_000_000,
                "unit": "USD",
                "period": "2026Q2",
                "source": "sec_companyfacts",
            },
            {
                "name": "capital expenditures",
                "value": -1_100_000_000,
                "unit": "USD",
                "period": "2026Q2",
                "source": "sec_companyfacts",
            },
            {
                "name": "buybacks",
                "value": -800_000_000,
                "unit": "USD",
                "period": "2026Q2",
                "source": "sec_companyfacts",
            },
        ]
    )

    result = service.search_metric_evidence(
        MetricEvidenceInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            metrics=["operating cash flow", "capital expenditures", "buybacks"],
            period="latest_quarter",
        ),
        state.model_copy(update={"task_type": ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION}),
    )

    assert result.status == ToolStatus.OK
    assert pipeline.calls == 0
    assert len(result.data["records"]) == 3
    assert {record["source"] for record in result.data["records"]} == {"sec_companyfacts"}
    assert all(":sec_companyfacts:" in ref["source_id"] for ref in result.source_refs)


def test_search_metric_evidence_labels_yfinance_preloaded_facts_as_yfinance_metrics() -> None:
    pipeline = _CountingPipeline()
    service = LlamaIndexResearchToolService(pipeline, facts_provider=None)  # type: ignore[arg-type]
    state = _state_with_facts(
        metrics=[
            {
                "name": "revenue",
                "value": 151_144_000,
                "unit": "USD",
                "period": "FY2026 Q1",
                "source": "preloaded_financial_facts",
            },
            {
                "name": "gross margin",
                "value": 0.2906,
                "unit": "pure",
                "period": "FY2026 Q1",
                "source": "preloaded_financial_facts",
            },
            {
                "name": "operating income",
                "value": -12_991_000,
                "unit": "USD",
                "period": "FY2026 Q1",
                "source": "preloaded_financial_facts",
            },
        ]
    )

    result = service.search_metric_evidence(
        MetricEvidenceInput(
            run_id=state.run_id,
            ticker="AAOI",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            metrics=["revenue", "gross margin", "operating income"],
            period="latest_quarter",
        ),
        state,
    )

    assert result.status == ToolStatus.OK
    assert pipeline.calls == 0
    assert {record["source"] for record in result.data["records"]} == {
        "preloaded_financial_facts"
    }
    assert all(":yfinance_metric:" in ref["source_id"] for ref in result.source_refs)
    assert not any(":sec_companyfacts:" in ref["source_id"] for ref in result.source_refs)


def test_base_search_metric_evidence_uses_raw_yfinance_quarterly_facts() -> None:
    service = ResearchToolService(facts_provider=None)
    state = AgentState(
        run_id="run_1",
        ticker="BRK-B",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            allowed_tools=[
                "get_company_facts",
                "search_filing_sections",
                "search_metric_evidence",
            ],
            required_outputs=["cashQualityVerdict", "cashMetrics"],
        ),
        evidence_memory=EvidenceMemory(
            facts={
                "ticker": "BRK-B",
                "quarterlyFinancials": [
                    {
                        "periodEnd": "2026-03-31",
                        "netIncome": 12300000000,
                        "operatingCashFlow": 16000000000,
                        "capitalExpenditures": 1900000000,
                        "freeCashFlow": 14100000000,
                        "cashAndShortTermInvestments": 334000000000,
                        "currentAssets": 430000000000,
                        "currentLiabilities": 106000000000,
                        "totalDebt": 128000000000,
                    }
                ],
            }
        ),
    )

    result = service.search_metric_evidence(
        MetricEvidenceInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            metrics=[
                "net income",
                "operating cash flow",
                "capital expenditures",
                "free cash flow",
                "current ratio",
                "total debt",
                "cash and short term investments",
            ],
            period="latest_quarter",
        ),
        state,
    )

    assert result.status == ToolStatus.OK
    assert len(result.data["records"]) == 7
    assert {record["source"] for record in result.data["records"]} == {"preloaded_financial_facts"}
    assert result.data["records"][4]["value"] == 430000000000 / 106000000000
    assert all(ref["section"] == "yfinance structured snapshot" for ref in result.source_refs)


def test_search_metric_evidence_retrieves_only_missing_metrics_when_facts_are_partial() -> None:
    pipeline = _RecordingPipeline()
    service = LlamaIndexResearchToolService(pipeline, facts_provider=None)  # type: ignore[arg-type]
    state = _state_with_facts(
        metrics=[
            {
                "name": "operating cash flow",
                "value": 4_200_000_000,
                "unit": "USD",
                "period": "2026Q2",
                "source": "sec_companyfacts",
            },
        ]
    )

    result = service.search_metric_evidence(
        MetricEvidenceInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            metrics=["operating cash flow", "capital expenditures", "buybacks"],
            period="latest_quarter",
        ),
        state.model_copy(update={"task_type": ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION}),
    )

    assert result.status == ToolStatus.OK
    assert len(pipeline.queries) == 1
    assert not any(query.startswith("operating cash flow") for query in pipeline.queries)
    assert "operating cash flow" in {
        record["normalized_metric"] for record in result.data["records"]
    }


def test_search_filing_sections_uses_a_tighter_cash_flow_query_budget() -> None:
    pipeline = _RecordingPipeline()
    service = LlamaIndexResearchToolService(pipeline, facts_provider=None)  # type: ignore[arg-type]
    state = _state_with_facts(metrics=[])

    result = service.search_filing_sections(
        FilingSectionSearchInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            sections=["MD&A"],
            query="cash flow liquidity debt maturities",
            limit=5,
        ),
        state.model_copy(update={"task_type": ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION}),
    )

    assert result.status == ToolStatus.OK
    assert len(pipeline.queries) == 2


def test_build_evidence_pack_uses_two_task_queries_for_latest_earnings() -> None:
    pipeline = _EvidencePackRecordingPipeline()
    state = _state_with_facts(
        metrics=[
            {"name": "revenue", "value": 25_500_000_000, "unit": "USD"},
            {"name": "gross margin", "value": 0.1823, "unit": "pure"},
            {"name": "operating income", "value": 2_100_000_000, "unit": "USD"},
        ]
    ).model_copy(update={"task_type": ResearchTaskType.LATEST_EARNINGS_READOUT})
    tool = create_agent_evidence_pack_tool(
        request=type(
            "Request",
            (),
            {
                "run_id": state.run_id,
                "ticker": state.ticker,
                "task_type": state.task_type,
            },
        )(),
        state_getter=lambda: state,
        state_setter=lambda next_state: None,
        rag_pipeline=pipeline,  # type: ignore[arg-type]
        summary="Built SEC filing evidence pack for latest earnings.",
        run_domain_tool=lambda current_state, tool_name, summary, result, tool_input=None: (
            current_state,
            "{}",
        ),
    )

    tool.invoke({"focus": "revenue margins", "top_k": 5})

    assert len(pipeline.queries) == 1
    assert "revenue" in pipeline.queries[0]


def test_build_evidence_pack_labels_preloaded_metrics_as_yfinance_metrics() -> None:
    pipeline = _EvidencePackRecordingPipeline()
    state = _state_with_facts(
        metrics=[
            {
                "name": "revenue",
                "value": 151_144_000,
                "unit": "USD",
                "period": "FY2026 Q1",
                "source": "preloaded_financial_facts",
            },
        ]
    ).model_copy(update={"task_type": ResearchTaskType.LATEST_EARNINGS_READOUT})
    captured: dict[str, object] = {}

    tool = create_agent_evidence_pack_tool(
        request=type(
            "Request",
            (),
            {
                "run_id": state.run_id,
                "ticker": state.ticker,
                "task_type": state.task_type,
            },
        )(),
        state_getter=lambda: state,
        state_setter=lambda next_state: None,
        rag_pipeline=pipeline,  # type: ignore[arg-type]
        summary="Built SEC filing evidence pack for latest earnings.",
        run_domain_tool=lambda current_state, tool_name, summary, result, tool_input=None: (
            current_state,
            captured.setdefault("output", result.data) or "{}",
        ),
    )

    tool.invoke({"focus": "revenue", "top_k": 5})

    output = captured["output"]
    assert isinstance(output, dict)
    evidence_pack = output["evidence_pack"]
    assert isinstance(evidence_pack, dict)
    metric_facts = evidence_pack["metric_facts"]
    assert isinstance(metric_facts, list)
    assert any(
        fact.get("source_type") == "yfinance_metric" and fact.get("metric") == "revenue"
        for fact in metric_facts
        if isinstance(fact, dict)
    )


def test_get_market_context_returns_preloaded_market_context_without_network() -> None:
    service = ResearchToolService(facts_provider=None)
    state = _state_with_facts(metrics=[]).model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                facts={
                    "ticker": "AMD",
                    "company_name": "Advanced Micro Devices, Inc.",
                    "market_sector": "Technology",
                    "market_industry": "Semiconductors",
                    "business_summary": (
                        "AMD designs CPUs, GPUs, adaptive computing products, and "
                        "data-center accelerators."
                    ),
                    "market_cap": 265_000_000_000,
                    "trailing_pe": 44.2,
                    "regular_market_price": 162.5,
                    "fifty_two_week_change_percent": 0.28,
                    "technical_trend": "Shares trade above the 50-day moving average.",
                    "news_headlines": [
                        "Cloud customers increased accelerator deployments.",
                    ],
                    "sentiment_summary": "AI infrastructure demand is the main market debate.",
                    "macro_context": "Higher rates keep long-duration growth multiples under scrutiny.",
                }
            ),
        }
    )

    result = service.get_market_context(
        MarketContextInput(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            context_types=[
                "profile",
                "valuation",
                "technical",
                "news",
                "sentiment",
                "macro",
            ],
        ),
        state,
    )

    assert result.status == ToolStatus.OK
    assert result.data["profile"]["sector"] == "Technology"
    assert result.data["valuation"]["market_cap"] == 265_000_000_000
    assert result.data["technical"]["trend"] == "Shares trade above the 50-day moving average."
    assert result.data["news"]["headlines"] == [
        "Cloud customers increased accelerator deployments."
    ]
    assert result.data["sentiment"]["summary"] == (
        "AI infrastructure demand is the main market debate."
    )
    assert result.data["macro"]["context"] == (
        "Higher rates keep long-duration growth multiples under scrutiny."
    )
    assert result.source_refs[0]["source_id"] == "run_1:market_context:1"


def _state_with_facts(*, metrics: list[dict[str, object]]) -> AgentState:
    task_type = ResearchTaskType.LATEST_EARNINGS_READOUT
    return AgentState(
        run_id="run_1",
        ticker="AMD",
        task_type=task_type,
        task_policy=TaskPolicy(
            task_type=task_type,
            allowed_tools=[
                "get_company_facts",
                "search_filing_sections",
                "search_metric_evidence",
            ],
            required_outputs=[
                "toplineVerdict",
                "keyTakeaways",
                "financialDashboard",
            ],
        ),
        evidence_memory=EvidenceMemory(
            facts={
                "ticker": "AMD",
                "company_name": "Advanced Micro Devices, Inc.",
                "period": "2026Q2",
                "metrics": metrics,
            },
        ),
    )
