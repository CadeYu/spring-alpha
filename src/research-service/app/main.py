import logging
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future
from hashlib import sha256
from os import getenv
from threading import Lock
from time import perf_counter
from typing import Any

from fastapi import FastAPI

from app.agents.domain_tools import (
    LlamaIndexResearchToolService,
    SecCompanyFactsProvider,
    YahooCompanyProfileProvider,
)
from app.agents.llm_gateway import (
    LlmClient,
    create_llm_client,
    default_model_for_provider,
)
from app.agents.research_workflow import ResearchAgentWorkflow
from app.contracts.agent import AgentRequest, BoundedAgentResult, LlmProvider
from app.rag.llamaindex_pipeline import FilingDocument, build_production_rag_pipeline_from_env

SERVICE_NAME = "spring-alpha-research-service"
SERVICE_VERSION = "0.1.0"
logger = logging.getLogger("uvicorn.error")


AgentWorkflow = ResearchAgentWorkflow
LlmClientFactory = Callable[[LlmProvider, str], LlmClient]
_REQUEST_PIPELINE_CACHE: OrderedDict[str, Any] = OrderedDict()
_REQUEST_PIPELINE_IN_FLIGHT: dict[str, Future[Any]] = {}
_REQUEST_PIPELINE_CACHE_LOCK = Lock()


def create_app(
    workflow: AgentWorkflow | None = None,
    *,
    llm_client_factory: LlmClientFactory | None = None,
    facts_provider: SecCompanyFactsProvider | None = None,
) -> FastAPI:
    client_factory = llm_client_factory or (
        lambda provider, api_key: create_llm_client(provider, api_key=api_key)
    )
    default_facts_provider = facts_provider or _default_facts_provider()
    app = FastAPI(title=SERVICE_NAME, version=SERVICE_VERSION)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": SERVICE_VERSION,
        }

    @app.post("/agent/runs", response_model=BoundedAgentResult)
    def run_agent(request: AgentRequest) -> BoundedAgentResult:
        started_at = perf_counter()
        logger.info(
            "agent_run_start run_id=%s ticker=%s task_type=%s filings=%s provider=%s",
            request.run_id,
            request.ticker,
            request.task_type.value,
            len(request.filings),
            request.llm_provider.value if request.llm_provider else "none",
        )
        try:
            if workflow is None and request.llm_provider is not None and request.llm_api_key:
                model = request.llm_model or default_model_for_provider(request.llm_provider)
                request_scoped_workflow = _workflow_for_request_filings(
                    request.model_copy(update={"llm_model": model}),
                    workflow,
                    llm_client=client_factory(request.llm_provider, request.llm_api_key),
                    facts_provider=default_facts_provider,
                )
                result = request_scoped_workflow.run(
                    request.model_copy(update={"llm_model": model})
                )
            else:
                request_workflow = _workflow_for_request_filings(
                    request,
                    workflow,
                    facts_provider=default_facts_provider,
                )
                result = request_workflow.run(request)
            logger.info(
                "agent_run_complete run_id=%s status=%s latency_ms=%s events=%s",
                request.run_id,
                result.status.value,
                _elapsed_ms(started_at),
                len(result.events),
            )
            return result
        except Exception:
            logger.exception(
                "agent_run_failed run_id=%s latency_ms=%s",
                request.run_id,
                _elapsed_ms(started_at),
            )
            raise

    return app


def _workflow_for_request_filings(
    request: AgentRequest,
    configured_workflow: AgentWorkflow | None,
    *,
    llm_client: LlmClient | None = None,
    facts_provider: SecCompanyFactsProvider | None = None,
) -> AgentWorkflow:
    if configured_workflow is not None:
        return configured_workflow
    if not request.filings:
        return ResearchAgentWorkflow(
            tool_service=LlamaIndexResearchToolService(
                build_production_rag_pipeline_from_env(),
                facts_provider=facts_provider,
            ),
            llm_client=llm_client,
        )

    pipeline = _cached_request_pipeline(request)
    return ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(pipeline, facts_provider=facts_provider),
        llm_client=llm_client,
        rag_pipeline=pipeline,
    )


def _cached_request_pipeline(request: AgentRequest):
    cache_key = _request_pipeline_cache_key(request)
    with _REQUEST_PIPELINE_CACHE_LOCK:
        pipeline = _REQUEST_PIPELINE_CACHE.get(cache_key)
        if pipeline is None:
            future = _REQUEST_PIPELINE_IN_FLIGHT.get(cache_key)
            if future is None:
                future = Future()
                _REQUEST_PIPELINE_IN_FLIGHT[cache_key] = future
                builder = True
            else:
                builder = False
        else:
            _REQUEST_PIPELINE_CACHE.move_to_end(cache_key)
            return pipeline

    if not builder:
        return future.result()

    try:
        pipeline_started_at = perf_counter()
        pipeline = build_production_rag_pipeline_from_env()
        _ingest_request_filings(request, pipeline)
        logger.info(
            "agent_rag_pipeline_ready run_id=%s latency_ms=%s",
            request.run_id,
            _elapsed_ms(pipeline_started_at),
        )
        with _REQUEST_PIPELINE_CACHE_LOCK:
            _store_request_pipeline(cache_key, pipeline)
            future.set_result(pipeline)
            _REQUEST_PIPELINE_IN_FLIGHT.pop(cache_key, None)
        return pipeline
    except Exception as error:
        with _REQUEST_PIPELINE_CACHE_LOCK:
            future.set_exception(error)
            _REQUEST_PIPELINE_IN_FLIGHT.pop(cache_key, None)
        raise


def _store_request_pipeline(cache_key: str, pipeline: Any) -> None:
    _REQUEST_PIPELINE_CACHE[cache_key] = pipeline
    _REQUEST_PIPELINE_CACHE.move_to_end(cache_key)
    max_entries = _request_pipeline_cache_max_entries()
    while len(_REQUEST_PIPELINE_CACHE) > max_entries:
        _REQUEST_PIPELINE_CACHE.popitem(last=False)


def _ingest_request_filings(request: AgentRequest, pipeline) -> None:
    for filing in request.filings:
        ingest_started_at = perf_counter()
        pipeline.ingest_filing(
            FilingDocument(
                ticker=filing.ticker,
                filing_type=filing.filing_type,
                filing_date=filing.filing_date,
                accession_number=filing.accession_number,
                text=filing.text,
            )
        )
        logger.info(
            "agent_rag_ingest_complete run_id=%s ticker=%s chars=%s latency_ms=%s",
            request.run_id,
            filing.ticker,
            len(filing.text),
            _elapsed_ms(ingest_started_at),
        )


def _request_pipeline_cache_key(request: AgentRequest) -> str:
    filing_fingerprint = sha256()
    for filing in request.filings:
        filing_fingerprint.update(filing.ticker.upper().encode("utf-8"))
        filing_fingerprint.update(b"\0")
        filing_fingerprint.update(filing.filing_type.encode("utf-8"))
        filing_fingerprint.update(b"\0")
        filing_fingerprint.update((filing.filing_date or "").encode("utf-8"))
        filing_fingerprint.update(b"\0")
        filing_fingerprint.update((filing.accession_number or "").encode("utf-8"))
        filing_fingerprint.update(b"\0")
        filing_fingerprint.update(filing.text.encode("utf-8"))
        filing_fingerprint.update(b"\0")
    return f"{request.ticker.upper()}:{filing_fingerprint.hexdigest()}"


def _request_pipeline_cache_max_entries() -> int:
    raw_value = getenv("AGENT_PIPELINE_CACHE_MAX_ENTRIES", "3")
    try:
        return max(1, int(raw_value))
    except ValueError:
        logger.warning(
            "Invalid AGENT_PIPELINE_CACHE_MAX_ENTRIES=%s, using default of 3",
            raw_value,
        )
        return 3


def _elapsed_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def _default_facts_provider() -> SecCompanyFactsProvider:
    try:
        return SecCompanyFactsProvider(profile_provider=YahooCompanyProfileProvider())
    except TypeError:
        return SecCompanyFactsProvider()


app = create_app()
