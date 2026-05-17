import logging
from collections.abc import Callable
from time import perf_counter

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

    pipeline_started_at = perf_counter()
    pipeline = build_production_rag_pipeline_from_env()
    logger.info(
        "agent_rag_pipeline_ready run_id=%s latency_ms=%s",
        request.run_id,
        _elapsed_ms(pipeline_started_at),
    )
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
    return ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(pipeline, facts_provider=facts_provider),
        llm_client=llm_client,
        rag_pipeline=pipeline,
    )


def _elapsed_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def _default_facts_provider() -> SecCompanyFactsProvider:
    try:
        return SecCompanyFactsProvider(profile_provider=YahooCompanyProfileProvider())
    except TypeError:
        return SecCompanyFactsProvider()


app = create_app()
