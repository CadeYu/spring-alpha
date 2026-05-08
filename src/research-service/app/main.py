from collections.abc import Callable

from fastapi import FastAPI

from app.agents.bounded_workflow import BoundedAgentWorkflow
from app.agents.deterministic_workflow import DeterministicAgentWorkflow
from app.agents.domain_tools import LlamaIndexResearchToolService
from app.agents.llm_gateway import (
    LlmClient,
    create_llm_client,
    default_model_for_provider,
)
from app.agents.tool_registry import default_tool_registry
from app.contracts.agent import AgentRequest, BoundedAgentResult, LlmProvider
from app.rag.llamaindex_pipeline import FilingDocument, build_production_rag_pipeline_from_env

SERVICE_NAME = "spring-alpha-research-service"
SERVICE_VERSION = "0.1.0"


AgentWorkflow = BoundedAgentWorkflow | DeterministicAgentWorkflow
LlmClientFactory = Callable[[LlmProvider, str], LlmClient]


def create_app(
    workflow: AgentWorkflow | None = None,
    *,
    llm_client_factory: LlmClientFactory | None = None,
) -> FastAPI:
    client_factory = llm_client_factory or (
        lambda provider, api_key: create_llm_client(provider, api_key=api_key)
    )
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
        request_workflow = _workflow_for_request_filings(request, workflow)
        if workflow is None and request.llm_provider is not None and request.llm_api_key:
            model = request.llm_model or default_model_for_provider(request.llm_provider)
            request_scoped_workflow = _workflow_for_request_filings(
                request.model_copy(update={"llm_model": model}),
                workflow,
                llm_client=client_factory(request.llm_provider, request.llm_api_key),
            )
            return request_scoped_workflow.run(request.model_copy(update={"llm_model": model}))
        return request_workflow.run(request)

    return app


def _workflow_for_request_filings(
    request: AgentRequest,
    configured_workflow: AgentWorkflow | None,
    *,
    llm_client: LlmClient | None = None,
) -> AgentWorkflow:
    if configured_workflow is not None:
        return configured_workflow
    if not request.filings:
        return DeterministicAgentWorkflow(llm_client=llm_client)

    pipeline = build_production_rag_pipeline_from_env()
    for filing in request.filings:
        pipeline.ingest_filing(
            FilingDocument(
                ticker=filing.ticker,
                filing_type=filing.filing_type,
                filing_date=filing.filing_date,
                accession_number=filing.accession_number,
                text=filing.text,
            )
        )
    return DeterministicAgentWorkflow(
        registry=default_tool_registry(LlamaIndexResearchToolService(pipeline)),
        llm_client=llm_client,
    )


app = create_app()
