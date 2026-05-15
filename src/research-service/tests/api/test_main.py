import pytest
from fastapi.testclient import TestClient

from app.agents.domain_tools import SecCompanyFactsProvider
from app.agents.llm_gateway import LlmClient, OpenAiCompatibleLlmClient
from app.contracts.agent import AgentRunStatus, LlmProvider
from app.main import create_app
from app.rag.llamaindex_pipeline import PgVectorStoreConfig


def test_health_endpoint_reports_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "spring-alpha-research-service",
        "version": "0.1.0",
    }


def test_agent_run_endpoint_requires_tool_calling_llm() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_requires_llm",
            "ticker": "tsla",
            "task_type": "business_driver_deep_dive",
            "language": "en",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == AgentRunStatus.DEGRADED
    assert payload["final_report"] is None
    assert payload["events"][0]["phase"] == "degraded"
    assert "tool-calling" in payload["degraded_reasons"][0]


def test_agent_run_endpoint_uses_request_scoped_tool_calling_llm_for_latest_earnings() -> None:
    calls: list[dict[str, object]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        return _content_response(
            {
                "company_profile": {
                    "summary": "Apple designs consumer devices, software, and services.",
                    "source_ids": [],
                    "citation_status": "unverified",
                },
                "topline_verdict": {
                    "headline": "Provider synthesis produced an evidence-bound readout",
                    "summary": "The final report was synthesized from tool evidence.",
                    "verdict": "mixed",
                },
                "key_takeaways": [],
                "financial_dashboard": {
                    "metrics": [
                        {
                            "name": "Revenue",
                            "value": "Not extracted",
                            "period": "latest_quarter",
                            "interpretation": "Provider stayed cautious.",
                            "source_ids": [],
                            "citation_status": "partial",
                        }
                    ],
                    "chart_focus": ["revenue"],
                },
                "driver_snapshot": [],
                "risk_snapshot": [],
                "claims": [],
            }
        )

    def factory(provider: LlmProvider, api_key: str) -> LlmClient:
        assert provider == LlmProvider.SILICONFLOW
        assert api_key == "secret"
        return OpenAiCompatibleLlmClient(
            provider,
            api_key=api_key,
            base_url="https://example.test/v1",
            transport=transport,
        )

    client = TestClient(
        create_app(
            llm_client_factory=factory,
            facts_provider=SecCompanyFactsProvider(transport=fake_sec_transport),
        )
    )

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_provider_synthesis",
            "ticker": "aapl",
            "task_type": "latest_earnings_readout",
            "language": "en",
            "llm_provider": "siliconflow",
            "llm_model": "test-model",
            "llm_api_key": "secret",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    event_tool_names = [event["tool_name"] for event in payload["events"] if event["tool_name"]]

    assert len(calls) == 1
    assert "tools" not in calls[0]
    assert payload["status"] == AgentRunStatus.OK
    assert payload["final_report"]["sections"]["synthesis"] == "llm"
    assert payload["final_report"]["task_sections"]["topline_verdict"]["headline"] == (
        "Provider synthesis produced an evidence-bound readout"
    )
    assert payload["final_report"]["task_sections"]["financial_dashboard"]["metrics"][0][
        "value"
    ] == "$90.0B"
    assert event_tool_names == [
        "get_company_facts",
        "search_metric_evidence",
        "build_evidence_pack",
    ]
    assert "secret" not in response.text


def test_agent_run_endpoint_corrects_non_extracted_llm_metric_with_sec_companyfacts() -> None:
    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        return _content_response(
            {
                "topline_verdict": {
                    "headline": "Provider could not read table values",
                    "summary": "The provider stayed cautious about numeric values.",
                    "verdict": "mixed",
                },
                "key_takeaways": [],
                "financial_dashboard": {
                    "metrics": [
                        {
                            "name": "Revenue",
                            "value": "Not discernible in provided snippet",
                            "period": "latest_quarter",
                            "interpretation": "Specific Financial Figures Not Extracted.",
                            "source_ids": [],
                            "citation_status": "partial",
                        }
                    ],
                    "chart_focus": ["revenue"],
                },
                "driver_snapshot": [],
                "risk_snapshot": [],
                "claims": [],
            }
        )

    def factory(provider: LlmProvider, api_key: str) -> LlmClient:
        assert provider == LlmProvider.SILICONFLOW
        assert api_key == "secret"
        return OpenAiCompatibleLlmClient(
            provider,
            api_key=api_key,
            base_url="https://example.test/v1",
            transport=transport,
        )

    client = TestClient(
        create_app(
            llm_client_factory=factory,
            facts_provider=SecCompanyFactsProvider(transport=fake_sec_transport),
        )
    )

    response = client.post(
        "/agent/runs",
        json={
            "run_id": "run_api_fact_guardrail",
            "ticker": "aapl",
            "task_type": "latest_earnings_readout",
            "language": "en",
            "llm_provider": "siliconflow",
            "llm_model": "test-model",
            "llm_api_key": "secret",
            "filings": [
                {
                    "ticker": "AAPL",
                    "filing_type": "10-Q",
                    "filing_date": "2026-04-30",
                    "accession_number": "0000320193-26-000008",
                    "text": """
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue, gross margin, and operating income are discussed in a table.
""",
                }
            ],
        },
    )

    assert response.status_code == 200
    metric = response.json()["final_report"]["task_sections"]["financial_dashboard"][
        "metrics"
    ][0]
    assert metric["value"] == "$90.0B"
    assert metric["period"] == "2026Q1"
    assert metric["citation_status"] == "supported"
    assert metric["evidence_refs"][0]["section"] == "SEC companyfacts"


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
                    "OperatingIncomeLoss": {
                        "label": "Operating Income (Loss)",
                        "units": {
                            "USD": [
                                {
                                    "val": 28000000000,
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


def _content_response(payload: dict[str, object]) -> dict[str, object]:
    import json

    return {"choices": [{"message": {"content": json.dumps(payload)}}]}
