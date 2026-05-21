from __future__ import annotations

from collections import OrderedDict
from threading import Event, Thread
from unittest.mock import Mock

from app import main as app_main
from app.contracts.agent import AgentFilingDocument, AgentRequest, LlmProvider
from app.contracts.research_task import ResearchTaskType


def test_request_filings_reuse_the_same_pipeline_for_identical_payloads(monkeypatch):
    app_main._REQUEST_PIPELINE_CACHE.clear()
    build_calls = Mock()

    class FakePipeline:
        def __init__(self) -> None:
            self.ingested: list[AgentFilingDocument] = []

        def ingest_filing(self, filing: AgentFilingDocument) -> None:
            self.ingested.append(filing)

    fake_pipeline = FakePipeline()

    def fake_build_production_rag_pipeline_from_env():
        build_calls()
        return fake_pipeline

    monkeypatch.setattr(
        app_main,
        "build_production_rag_pipeline_from_env",
        fake_build_production_rag_pipeline_from_env,
    )

    request = AgentRequest(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="en",
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model="deepseek-ai/deepseek-v4-flash",
        llm_api_key="sk-test",
        filings=[
            AgentFilingDocument(
                ticker="AAPL",
                filing_type="10-Q",
                filing_date="2026-03-31",
                accession_number="0001",
                text="Revenue grew.",
            )
        ],
    )

    workflow_one = app_main._workflow_for_request_filings(request, None)
    workflow_two = app_main._workflow_for_request_filings(request, None)

    assert build_calls.call_count == 1
    assert len(fake_pipeline.ingested) == 1
    assert workflow_one._rag_pipeline is fake_pipeline  # type: ignore[attr-defined]
    assert workflow_two._rag_pipeline is fake_pipeline  # type: ignore[attr-defined]


def test_request_pipeline_cache_evicts_oldest_entry_when_full(monkeypatch):
    app_main._REQUEST_PIPELINE_CACHE = OrderedDict()
    app_main._REQUEST_PIPELINE_IN_FLIGHT.clear()
    monkeypatch.setenv("AGENT_PIPELINE_CACHE_MAX_ENTRIES", "1")

    build_calls = Mock()

    class FakePipeline:
        def __init__(self, name: str) -> None:
            self.name = name
            self.ingested: list[AgentFilingDocument] = []

        def ingest_filing(self, filing: AgentFilingDocument) -> None:
            self.ingested.append(filing)

    pipelines = {
        "AAPL": FakePipeline("AAPL"),
        "MSFT": FakePipeline("MSFT"),
    }

    def fake_build_production_rag_pipeline_from_env():
        build_calls()
        current_ticker = "AAPL" if build_calls.call_count == 1 else "MSFT"
        return pipelines[current_ticker]

    monkeypatch.setattr(
        app_main,
        "build_production_rag_pipeline_from_env",
        fake_build_production_rag_pipeline_from_env,
    )

    base_request = dict(
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="en",
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model="deepseek-ai/deepseek-v4-flash",
        llm_api_key="sk-test",
        filings=[
            AgentFilingDocument(
                ticker="AAPL",
                filing_type="10-Q",
                filing_date="2026-03-31",
                accession_number="0001",
                text="Revenue grew.",
            )
        ],
    )

    first_request = AgentRequest(run_id="run_1", ticker="AAPL", **base_request)
    second_request = AgentRequest(
        run_id="run_2",
        ticker="MSFT",
        **{
            **base_request,
            "filings": [
                AgentFilingDocument(
                    ticker="MSFT",
                    filing_type="10-Q",
                    filing_date="2026-03-31",
                    accession_number="0002",
                    text="Revenue grew.",
                )
            ],
        },
    )

    app_main._workflow_for_request_filings(first_request, None)
    app_main._workflow_for_request_filings(second_request, None)

    assert build_calls.call_count == 2
    assert list(app_main._REQUEST_PIPELINE_CACHE.keys()) == [
        app_main._request_pipeline_cache_key(second_request),
    ]


def test_request_pipeline_cache_reuses_one_in_flight_build_for_same_key(monkeypatch):
    app_main._REQUEST_PIPELINE_CACHE = OrderedDict()
    app_main._REQUEST_PIPELINE_IN_FLIGHT.clear()
    monkeypatch.setenv("AGENT_PIPELINE_CACHE_MAX_ENTRIES", "3")

    build_calls = Mock()
    build_started = Event()
    allow_build_to_finish = Event()

    class FakePipeline:
        def __init__(self) -> None:
            self.ingested: list[AgentFilingDocument] = []

        def ingest_filing(self, filing: AgentFilingDocument) -> None:
            self.ingested.append(filing)

    fake_pipeline = FakePipeline()

    def fake_build_production_rag_pipeline_from_env():
        build_calls()
        build_started.set()
        allow_build_to_finish.wait(timeout=2)
        return fake_pipeline

    monkeypatch.setattr(
        app_main,
        "build_production_rag_pipeline_from_env",
        fake_build_production_rag_pipeline_from_env,
    )

    request = AgentRequest(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="en",
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model="deepseek-ai/deepseek-v4-flash",
        llm_api_key="sk-test",
        filings=[
            AgentFilingDocument(
                ticker="AAPL",
                filing_type="10-Q",
                filing_date="2026-03-31",
                accession_number="0001",
                text="Revenue grew.",
            )
        ],
    )

    results: list[object] = []

    def build_pipeline() -> None:
        results.append(app_main._cached_request_pipeline(request))

    first_thread = Thread(target=build_pipeline)
    second_thread = Thread(target=build_pipeline)
    first_thread.start()
    assert build_started.wait(timeout=2)
    second_thread.start()
    allow_build_to_finish.set()
    first_thread.join(timeout=2)
    second_thread.join(timeout=2)

    assert build_calls.call_count == 1
    assert len(results) == 2
    assert all(result is fake_pipeline for result in results)
