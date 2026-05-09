import pytest
from fastapi.testclient import TestClient

from app.agents.deterministic_workflow import DeterministicAgentWorkflow
from app.agents.domain_tools import SecCompanyFactsProvider
from app.agents.llm_gateway import LlmClient, StaticJsonLlmClient
from app.agents.tool_registry import default_tool_registry
from app.contracts.agent import AgentRunStatus, LlmProvider
from app.contracts.research_task import ResearchTaskType
from app.main import create_app
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline, PgVectorStoreConfig


def test_health_endpoint_reports_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "spring-alpha-research-service",
        "version": "0.1.0",
    }


def test_agent_run_endpoint_invokes_bounded_workflow() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_001",
            "ticker": "tsla",
            "task_type": "business_driver_deep_dive",
            "language": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "run_api_001"
    assert payload["task_type"] == "business_driver_deep_dive"
    assert payload["status"] == AgentRunStatus.OK
    assert payload["events"]
    assert payload["final_report"]["ticker"] == "TSLA"


@pytest.mark.parametrize(
    ("task_type", "expected_tools"),
    [
        (
            ResearchTaskType.LATEST_EARNINGS_READOUT,
            {
                "get_company_facts",
                "search_filing_sections",
                "search_metric_evidence",
                "verify_citations",
                "finalize_report",
            },
        ),
        (
            ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            {
                "search_filing_sections",
                "search_metric_evidence",
                "get_business_signals",
                "verify_citations",
                "finalize_report",
            },
        ),
        (
            ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            {
                "get_company_facts",
                "search_filing_sections",
                "search_metric_evidence",
                "verify_citations",
                "finalize_report",
            },
        ),
    ],
)
def test_agent_run_endpoint_uses_deterministic_tool_loop(
    task_type: ResearchTaskType,
    expected_tools: set[str],
) -> None:
    client = TestClient(create_app())

    response = client.post(
        "/agent/runs",
        json={
            "run_id": f"run_api_{task_type.value}",
            "ticker": "aapl",
            "task_type": task_type.value,
            "language": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    tool_names = {event["tool_name"] for event in payload["events"] if event["tool_name"]}

    assert payload["status"] == AgentRunStatus.OK
    assert expected_tools.issubset(tool_names)
    assert "collect_financial_facts" not in tool_names
    assert "retrieve_evidence" not in tool_names
    assert any(event["phase"] == "build_evidence_plan" for event in payload["events"])
    assert any(event["phase"] == "validate_claims" for event in payload["events"])
    assert payload["final_report"]["task_sections"]["task_type"] == task_type.value
    assert payload["final_report"]["task_sections"]["coverage"]["evidence_count"] > 0
    assert payload["final_report"]["retrieval_records"]


def test_agent_run_endpoint_can_use_llm_planner_for_first_tool_call() -> None:
    class SequenceLlmClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, request):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return StaticJsonLlmClient(
                    {
                        "decision": "call_tool",
                        "summary": "LLM planner selected MD&A evidence.",
                        "tool_name": "search_filing_sections",
                        "tool_input": {
                            "sections": ["MD&A"],
                            "query": "services demand",
                        },
                    }
                ).complete_json(request)
            return StaticJsonLlmClient(
                {
                    "decision": "finalize",
                    "summary": "Single planned tool call is enough.",
                }
            ).complete_json(request)

    client = TestClient(create_app(DeterministicAgentWorkflow(llm_client=SequenceLlmClient())))

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_llm_planner",
            "ticker": "aapl",
            "task_type": "business_driver_deep_dive",
            "language": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == AgentRunStatus.OK
    assert payload["events"][0]["summary"].startswith(
        "Plan next step: LLM planner selected MD&A evidence."
    )
    assert "[planner_context" in payload["events"][0]["summary"]
    assert payload["events"][0]["planner_context"] == {
        "remaining_steps": 5,
        "remaining_tool_calls": 5,
        "coverage_status": "degraded",
        "evidence_count": 0,
        "citation_coverage": "missing",
    }
    assert payload["events"][1]["tool_name"] == "search_filing_sections"
    assert payload["final_report"]["task_sections"]["task_type"] == "business_driver_deep_dive"


def test_agent_run_endpoint_builds_request_scoped_llm_planner_from_provider_config() -> None:
    created: list[tuple[LlmProvider, str]] = []

    def factory(provider: LlmProvider, api_key: str) -> LlmClient:
        created.append((provider, api_key))
        return StaticJsonLlmClient(
            {
                "decision": "call_tool",
                "summary": "Provider planner selected business signals.",
                "tool_name": "get_business_signals",
                "tool_input": {"signal_types": ["product", "demand"]},
            },
            provider=provider,
        )

    client = TestClient(create_app(llm_client_factory=factory))

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_provider_planner",
            "ticker": "aapl",
            "task_type": "business_driver_deep_dive",
            "language": "en",
            "llm_provider": "siliconflow",
            "llm_model": "Pro/moonshotai/Kimi-K2.6",
            "llm_api_key": "secret",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert created == [(LlmProvider.SILICONFLOW, "secret")]
    assert payload["events"][0]["summary"].startswith(
        "Plan next step: Provider planner selected business signals."
    )
    assert "[planner_context" in payload["events"][0]["summary"]
    assert payload["events"][1]["tool_name"] == "get_business_signals"
    assert "secret" not in response.text


def test_agent_run_endpoint_uses_request_scoped_llm_for_latest_earnings_synthesis() -> None:
    class PlanningAndSynthesisClient:
        provider = LlmProvider.SILICONFLOW

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, request):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return StaticJsonLlmClient(
                    {
                        "decision": "call_tool",
                        "summary": "Provider planner selected filing evidence.",
                        "tool_name": "search_filing_sections",
                        "tool_input": {
                            "sections": ["MD&A"],
                            "query": "services revenue demand",
                        },
                    },
                    provider=self.provider,
                ).complete_json(request)
            if self.calls == 2:
                return StaticJsonLlmClient(
                    {
                        "decision": "finalize",
                        "summary": "Evidence is ready for synthesis.",
                    },
                    provider=self.provider,
                ).complete_json(request)
            return StaticJsonLlmClient(
                {
                    "topline_verdict": {
                        "headline": "Provider synthesis produced an evidence-bound readout",
                        "summary": "The final report was synthesized from cited filing evidence.",
                        "verdict": "mixed",
                    },
                    "key_takeaways": [
                        {
                            "title": "Services evidence",
                            "summary": "Services revenue is tied to the cited MD&A evidence.",
                            "source_ids": ["run_api_provider_synthesis:filing:1"],
                            "citation_status": "supported",
                        }
                    ],
                    "financial_dashboard": {
                        "metrics": [
                            {
                                "name": "Revenue",
                                "value": "Evidence-backed",
                                "interpretation": (
                                    "Revenue context is grounded in the cited snippet."
                                ),
                                "source_ids": ["run_api_provider_synthesis:filing:1"],
                                "citation_status": "supported",
                            }
                        ],
                        "chart_focus": ["revenue"],
                    },
                    "driver_snapshot": [
                        {
                            "title": "Demand",
                            "summary": "Demand is the cited driver for the readout.",
                            "source_ids": ["run_api_provider_synthesis:filing:1"],
                            "citation_status": "supported",
                        }
                    ],
                    "risk_snapshot": [
                        {
                            "title": "Evidence scope",
                            "summary": (
                                "The report stays cautious because evidence is concentrated."
                            ),
                            "source_ids": ["run_api_provider_synthesis:filing:1"],
                            "citation_status": "partial",
                        }
                    ],
                    "claims": [
                        {
                            "text": "Services revenue evidence supports a mixed readout.",
                            "source_ids": ["run_api_provider_synthesis:filing:1"],
                            "citation_status": "supported",
                        }
                    ],
                },
                provider=self.provider,
            ).complete_json(request)

    created: list[PlanningAndSynthesisClient] = []

    def factory(provider: LlmProvider, api_key: str) -> LlmClient:
        assert provider == LlmProvider.SILICONFLOW
        assert api_key == "secret"
        client = PlanningAndSynthesisClient()
        created.append(client)
        return client

    client = TestClient(create_app(llm_client_factory=factory))

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_provider_synthesis",
            "ticker": "aapl",
            "task_type": "latest_earnings_readout",
            "language": "en",
            "llm_provider": "siliconflow",
            "llm_model": "Pro/moonshotai/Kimi-K2.6",
            "llm_api_key": "secret",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert created[0].calls == 3
    assert payload["final_report"]["sections"]["synthesis"] == "llm"
    assert payload["final_report"]["task_sections"]["topline_verdict"]["headline"] == (
        "Provider synthesis produced an evidence-bound readout"
    )
    assert "secret" not in response.text


def test_agent_run_endpoint_lets_live_planner_finalize_after_observing_first_tool() -> None:
    class SequenceLlmClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, request):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return StaticJsonLlmClient(
                    {
                        "decision": "call_tool",
                        "summary": "Collect only MD&A evidence.",
                        "tool_name": "search_filing_sections",
                        "tool_input": {
                            "sections": ["MD&A"],
                            "query": "revenue margin evidence",
                        },
                    }
                ).complete_json(request)
            return StaticJsonLlmClient(
                {
                    "decision": "finalize",
                    "summary": "Evidence is enough for this bounded smoke run.",
                }
            ).complete_json(request)

    llm_client = SequenceLlmClient()
    client = TestClient(create_app(DeterministicAgentWorkflow(llm_client=llm_client)))

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_planner_finalize",
            "ticker": "aapl",
            "task_type": "latest_earnings_readout",
            "language": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    tool_names = [event["tool_name"] for event in payload["events"] if event["tool_name"]]

    assert llm_client.calls == 2
    assert tool_names == ["search_filing_sections", "search_filing_sections"]
    assert any(
        event["phase"] == "finalize_report"
        and event["summary"].startswith(
            "Planner finalized: Evidence is enough for this bounded smoke run."
        )
        and "[planner_context" in event["summary"]
        for event in payload["events"]
    )


def test_agent_run_endpoint_verifies_final_claim_citations() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_citation_scoring",
            "ticker": "aapl",
            "task_type": "latest_earnings_readout",
            "language": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    claim = payload["final_report"]["claims"][0]

    assert claim["citation_status"] in {"supported", "partial"}
    assert claim["source_refs"]
    assert claim["source_refs"][0]["citation_status"] in {"supported", "partial"}


def test_agent_run_endpoint_can_use_live_rag_tool_registry() -> None:
    from app.agents.domain_tools import LlamaIndexResearchToolService

    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000003",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased because demand improved and installed base engagement expanded.
Gross margin benefited from mix.
Earnings dashboard metrics include revenue, gross margin, and operating income.
""",
        )
    )
    workflow = DeterministicAgentWorkflow(
        registry=default_tool_registry(LlamaIndexResearchToolService(pipeline))
    )
    client = TestClient(create_app(workflow))

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_live_rag_registry",
            "ticker": "aapl",
            "task_type": "latest_earnings_readout",
            "language": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    source_refs = payload["final_report"]["claims"][0]["source_refs"]

    assert payload["status"] == AgentRunStatus.OK
    assert source_refs
    assert source_refs[0]["source_id"].startswith("AAPL:0000320193-26-000003")
    assert "Evidence placeholder" not in source_refs[0]["snippet"]


def test_agent_run_endpoint_ingests_request_filings_into_live_rag_tools() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_request_filing_rag",
            "ticker": "aapl",
            "task_type": "latest_earnings_readout",
            "language": "en",
            "filings": [
                {
                    "ticker": "AAPL",
                    "filing_type": "10-Q",
                    "filing_date": "2026-04-30",
                    "accession_number": "0000320193-26-000004",
                    "text": """
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased because demand improved and installed base engagement expanded.
Earnings dashboard metrics include revenue, gross margin, and operating income.
""",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    source_refs = payload["final_report"]["claims"][0]["source_refs"]

    assert payload["status"] == AgentRunStatus.OK
    assert source_refs
    assert source_refs[0]["source_id"].startswith("AAPL:0000320193-26-000004")
    assert "Services revenue increased" in source_refs[0]["snippet"]
    assert "Evidence placeholder" not in source_refs[0]["snippet"]


def test_agent_run_endpoint_uses_sec_company_facts_with_request_filings() -> None:
    client = TestClient(
        create_app(facts_provider=SecCompanyFactsProvider(transport=fake_sec_transport))
    )

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_request_filing_facts",
            "ticker": "aapl",
            "task_type": "latest_earnings_readout",
            "language": "en",
            "filings": [
                {
                    "ticker": "AAPL",
                    "filing_type": "10-Q",
                    "filing_date": "2026-04-30",
                    "accession_number": "0000320193-26-000006",
                    "text": """
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased because demand improved and installed base engagement expanded.
Gross margin benefited from mix.
Earnings dashboard metrics include revenue, gross margin, and operating income.
""",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    facts = payload["final_report"]["sections"]["facts"]

    fact_tools = [
        record
        for record in payload["final_report"]["retrieval_records"]
        if record["tool_name"] == "get_company_facts"
    ]
    assert facts["source"] == "sec_companyfacts"
    assert facts["metrics"][0]["name"] == "revenue"
    assert facts["metrics"][0]["value"] == 90000000000
    assert fact_tools
    assert fact_tools[0]["metric_count"] == 2
    assert fact_tools[0]["fact_source"] == "sec_companyfacts"


def test_agent_run_endpoint_uses_production_rag_pipeline_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RAG_VECTOR_STORE_PROVIDER", raising=False)
    monkeypatch.setenv("RAG_VECTOR_DATABASE_URL", "postgresql://example")
    monkeypatch.setenv("RAG_VECTOR_TABLE_NAME", "rag_chunks")
    monkeypatch.setenv("RAG_EMBEDDING_DIMENSION", "3")
    captured: dict[str, object] = {}

    class RecordingPgVectorStore:
        def __init__(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            captured["config"] = kwargs["config"]
            self._memory_store = None

        def upsert(self, node):  # type: ignore[no-untyped-def]
            return None

        def search(self, *, query, nodes, top_k):  # type: ignore[no-untyped-def]
            return []

    monkeypatch.setattr(
        "app.rag.llamaindex_pipeline.PgVectorStore",
        RecordingPgVectorStore,
    )

    client = TestClient(create_app())
    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_pgvector_default",
            "ticker": "aapl",
            "task_type": "business_driver_deep_dive",
            "language": "en",
            "filings": [
                {
                    "ticker": "AAPL",
                    "filing_type": "10-Q",
                    "filing_date": "2026-04-30",
                    "accession_number": "0000320193-26-000005",
                    "text": """
Segment Information
Services demand improved across enterprise customers.
""",
                }
            ],
        },
    )

    assert response.status_code == 200
    config = captured["config"]
    assert isinstance(config, PgVectorStoreConfig)
    assert config.database_url == "postgresql://example"
    assert config.table_name == "rag_chunks"
    assert config.embedding_dimension == 3


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
                                    "val": 90000000000,
                                    "fy": 2026,
                                    "fp": "Q1",
                                    "form": "10-Q",
                                    "filed": "2026-02-01",
                                    "accn": "0000320193-26-000001",
                                }
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
                                }
                            ]
                        },
                    },
                }
            },
        }
    raise AssertionError(f"Unexpected SEC URL: {url}")
