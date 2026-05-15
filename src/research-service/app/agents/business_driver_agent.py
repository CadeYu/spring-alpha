import json
from collections.abc import Callable
from time import perf_counter
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from app.agents.domain_tools import ResearchToolService
from app.agents.evidence_pack_tool import create_agent_evidence_pack_tool
from app.agents.tool_calling_graph import run_tool_calling_graph_agent
from app.contracts.agent import AgentEvent, AgentPhase, AgentRequest, AgentState
from app.contracts.research_task import ResearchTaskType
from app.contracts.tools import (
    BusinessSignalsInput,
    CompanyFactsInput,
    FilingSectionSearchInput,
    MetricEvidenceInput,
)
from app.rag.llamaindex_pipeline import LlamaIndexRagPipeline


class BusinessDriverAgentError(RuntimeError):
    def __init__(self, message: str, *, state: AgentState) -> None:
        super().__init__(message)
        self.state = state


class FilingSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sections: list[str] = Field(min_length=1)
    query: str = Field(min_length=1)
    limit: int = Field(default=5, ge=1, le=20)


class MetricSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[str] = Field(default_factory=list)
    period: str | None = None
    query: str | None = None


class BusinessSignalsSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_types: list[str] = Field(default_factory=list)


class CompanyFactsSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str | None = Field(default="latest_quarter")
    metrics: list[str] = Field(default_factory=list)


def run_business_driver_agent(
    *,
    request: AgentRequest,
    state: AgentState,
    llm: BaseChatModel,
    tool_service: ResearchToolService,
    rag_pipeline: LlamaIndexRagPipeline | None = None,
    max_iterations: int = 8,
) -> tuple[dict[str, Any], AgentState]:
    if request.task_type != ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        raise BusinessDriverAgentError(
            f"Unsupported business driver task: {request.task_type.value}",
            state=state,
        )

    runtime_state = state

    def set_runtime_state(next_state: AgentState) -> None:
        nonlocal runtime_state
        runtime_state = next_state

    tools = _business_driver_tools(
        request=request,
        state_getter=lambda: runtime_state,
        state_setter=set_runtime_state,
        tool_service=tool_service,
        rag_pipeline=rag_pipeline,
    )
    payload = run_tool_calling_graph_agent(
        agent_name="Business driver agent",
        state_getter=lambda: runtime_state,
        state_setter=set_runtime_state,
        llm=llm,
        tools=tools,
        required_tools={
            "search_filing_sections",
            "search_metric_evidence",
            "get_business_signals",
        },
        tool_prompt=_tool_prompt(),
        final_prompt=_final_prompt(),
        initial_instruction=_business_driver_instruction(request, state),
        final_instruction=_final_business_driver_instruction(request, state),
        planned_tool_calls=[
            {
                "name": "get_company_facts",
                "args": {
                    "metrics": ["revenue"],
                    "period": "latest_quarter",
                },
            },
            {"name": "search_metric_evidence", "args": {}},
            {
                "name": "build_evidence_pack",
                "args": {"focus": "product segment demand pricing strategy", "top_k": 5},
            },
            {"name": "get_business_signals", "args": {}},
        ],
        error_factory=lambda message, error_state: BusinessDriverAgentError(
            message,
            state=error_state,
        ),
        max_iterations=max_iterations,
    )
    return payload, runtime_state


def _business_driver_tools(
    *,
    request: AgentRequest,
    state_getter: Callable[[], AgentState],
    state_setter: Callable[[AgentState], None],
    tool_service: ResearchToolService,
    rag_pipeline: LlamaIndexRagPipeline | None,
) -> list[StructuredTool]:
    def get_company_facts(
        period: str | None = "latest_quarter",
        metrics: list[str] | None = None,
    ) -> str:
        tool_input = CompanyFactsInput(
            run_id=request.run_id,
            ticker=request.ticker,
            task_type=request.task_type,
            period=period,
            metrics=metrics or ["revenue"],
        )
        next_state, payload = _run_domain_tool(
            state_getter(),
            "get_company_facts",
            "Collected company facts for business drivers.",
            tool_service.get_company_facts(tool_input, state_getter()),
            tool_input.model_dump(mode="json"),
        )
        state_setter(next_state)
        return payload

    def search_filing_sections(sections: list[str], query: str, limit: int = 5) -> str:
        tool_input = FilingSectionSearchInput(
            run_id=request.run_id,
            ticker=request.ticker,
            task_type=request.task_type,
            sections=sections,
            query=query,
            limit=limit,
        )
        next_state, payload = _run_domain_tool(
            state_getter(),
            "search_filing_sections",
            "Searched filing sections for business drivers.",
            tool_service.search_filing_sections(tool_input, state_getter()),
            tool_input.model_dump(mode="json"),
        )
        state_setter(next_state)
        return payload

    def search_metric_evidence(
        metrics: list[str] | None = None,
        period: str | None = "latest_quarter",
        query: str | None = None,
    ) -> str:
        requested_metrics = metrics or ["revenue", "segment revenue"]
        tool_input = MetricEvidenceInput(
            run_id=request.run_id,
            ticker=request.ticker,
            task_type=request.task_type,
            metrics=requested_metrics,
            period=period,
            query=query,
        )
        next_state, payload = _run_domain_tool(
            state_getter(),
            "search_metric_evidence",
            "Searched metric evidence for business drivers.",
            tool_service.search_metric_evidence(tool_input, state_getter()),
            tool_input.model_dump(mode="json"),
        )
        state_setter(next_state)
        return payload

    def get_business_signals(signal_types: list[str] | None = None) -> str:
        tool_input = BusinessSignalsInput(
            run_id=request.run_id,
            ticker=request.ticker,
            task_type=request.task_type,
            signal_types=signal_types or [],
        )
        next_state, payload = _run_domain_tool(
            state_getter(),
            "get_business_signals",
            "Extracted business driver signals.",
            tool_service.get_business_signals(tool_input, state_getter()),
            tool_input.model_dump(mode="json"),
        )
        state_setter(next_state)
        return payload

    tools = [
        StructuredTool.from_function(
            get_company_facts,
            name="get_company_facts",
            description="Return company profile and core revenue facts for business drivers.",
            args_schema=CompanyFactsSearchInput,
        ),
        StructuredTool.from_function(
            search_filing_sections,
            name="search_filing_sections",
            description=(
                "Search SEC filing sections for product, segment, geography, demand, "
                "pricing, customer, and strategy evidence."
            ),
            args_schema=FilingSearchInput,
        ),
        StructuredTool.from_function(
            search_metric_evidence,
            name="search_metric_evidence",
            description="Return revenue and segment KPI evidence records with source ids.",
            args_schema=MetricSearchInput,
        ),
        StructuredTool.from_function(
            get_business_signals,
            name="get_business_signals",
            description=(
                "Extract business driver signals from already collected filing and metric "
                "evidence."
            ),
            args_schema=BusinessSignalsSearchInput,
        ),
        create_agent_evidence_pack_tool(
            request=request,
            state_getter=state_getter,
            state_setter=state_setter,
            rag_pipeline=rag_pipeline,
            summary="Built SEC filing evidence pack for business drivers.",
            run_domain_tool=_run_domain_tool,
        ),
    ]
    return tools


def _run_domain_tool(
    state: AgentState,
    tool_name: str,
    summary: str,
    result: Any,
    tool_input: dict[str, Any] | None = None,
) -> tuple[AgentState, str]:
    started_at = perf_counter()
    event = AgentEvent(
        run_id=state.run_id,
        task_type=state.task_type,
        phase=_phase_for_tool(tool_name),
        status=result.status,
        summary=summary,
        tool_name=tool_name,
        event_kind="tool",
        agent_name="Business driver agent",
        model_name=state.model,
        tool_input=tool_input or {},
        latency_ms=result.latency_ms or int((perf_counter() - started_at) * 1000),
        degraded_reason=result.degraded_reasons[0] if result.degraded_reasons else None,
    )
    evidence_memory = state.evidence_memory.model_copy(deep=True)
    if result.source_refs:
        evidence_memory.source_refs.extend(result.source_refs)
    if tool_name == "get_company_facts":
        evidence_memory.facts.update(result.data)
    if tool_name == "search_metric_evidence":
        evidence_memory.metric_evidence.extend(_records_from_result(result.data))
    if tool_name == "get_business_signals":
        evidence_memory.business_signals.extend(_records_from_result(result.data))
    next_state = state.model_copy(
        update={
            "tool_call_count": state.tool_call_count + 1,
            "step_index": state.step_index + 1,
            "evidence_memory": evidence_memory,
            "tool_events": [*state.tool_events, event],
            "retrieval_records": [
                *state.retrieval_records,
                {
                    "tool_name": tool_name,
                    "step_index": state.step_index,
                    "status": result.status.value,
                    "latency_ms": event.latency_ms,
                    "source_ref_count": len(result.source_refs),
                    **_retrieval_payload(result.data),
                },
            ],
            "degraded_reasons": [*state.degraded_reasons, *result.degraded_reasons],
        }
    )
    return next_state, json.dumps(result.data, ensure_ascii=True)


def _phase_for_tool(tool_name: str) -> AgentPhase:
    if tool_name == "get_company_facts":
        return AgentPhase.COLLECT_FINANCIAL_FACTS
    if tool_name == "get_business_signals":
        return AgentPhase.EXTRACT_SIGNALS
    return AgentPhase.RETRIEVE_EVIDENCE


def _records_from_result(data: dict[str, Any]) -> list[dict[str, Any]]:
    records = data.get("records")
    if isinstance(records, list):
        return [record for record in records if isinstance(record, dict)]
    return []


def _retrieval_payload(data: dict[str, Any]) -> dict[str, Any]:
    metrics = data.get("metrics")
    if isinstance(metrics, list):
        return {"fact_source": data.get("source"), "record_count": len(metrics)}
    retrieved_nodes = data.get("retrieved_nodes")
    if isinstance(retrieved_nodes, list):
        return {"retrieved_nodes": retrieved_nodes}
    records = data.get("records")
    if isinstance(records, list):
        return {"record_count": len(records)}
    evidence_pack = data.get("evidence_pack")
    if isinstance(evidence_pack, dict):
        return {"evidence_pack": _evidence_pack_summary(evidence_pack)}
    return {}


def _evidence_pack_summary(evidence_pack: dict[str, Any]) -> dict[str, Any]:
    filing_evidence = evidence_pack.get("filing_evidence")
    metric_facts = evidence_pack.get("metric_facts")
    filing_items = filing_evidence if isinstance(filing_evidence, list) else []
    metric_items = metric_facts if isinstance(metric_facts, list) else []
    source_types: dict[str, int] = {}
    sections: set[str] = set()
    for item in filing_items:
        if not isinstance(item, dict):
            continue
        section = item.get("section")
        if section:
            sections.add(str(section))
    for item in metric_items:
        if not isinstance(item, dict):
            continue
        source_type = str(item.get("source_type") or "unknown")
        source_types[source_type] = source_types.get(source_type, 0) + 1
    return {
        "retrieval_status": evidence_pack.get("retrieval_status"),
        "filing_evidence_count": len(filing_items),
        "metric_fact_count": len(metric_items),
        "metric_fact_source_types": source_types,
        "sections": sorted(sections),
        "serialized_length": len(json.dumps(evidence_pack, sort_keys=True)),
    }


def _tool_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a business analyst in a multi-agent financial research team. "
                "Work like a TradingAgents fundamentals analyst: gather enough tool "
                "evidence to explain what actually moved the business and why it matters "
                "to investors. Focus on product, segment, geography, demand, pricing, "
                "customer behavior, competitive position, and strategy. Do not over-index "
                "on generic risk or compliance language. Call one useful tool at a time.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )


def _final_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are the research manager for the business driver desk. Return one "
                "JSON object only. Do not call tools. Do not invent source_ids. Write like "
                "a concise investment memo: make the operating thesis explicit, explain "
                "the so what for investors, include counter-evidence where the evidence is "
                "mixed, and make uncertainty actionable through the watchlist. Keep prose "
                "investor-facing.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )


def _business_driver_instruction(request: AgentRequest, state: AgentState) -> str:
    return (
        f"Analyze business drivers for {state.ticker}.\n"
        "Required workflow:\n"
        "1. Call get_company_facts for company profile and core revenue facts.\n"
        "2. Call search_metric_evidence for revenue, segment revenue, and any available "
        "driver KPIs.\n"
        "3. Call build_evidence_pack for product, segment, geography, demand, pricing, "
        "customer, and strategy evidence.\n"
        "4. Call get_business_signals after filing or metric evidence exists.\n"
        "Final JSON shape:\n"
        "{"
        '"driver_thesis":{"headline":"...","durability":"durable|mixed|temporary|unclear",'
        '"summary":"..."},'
        '"driver_map":{"product":[],"segment":[],"geography":[],"demand":[],"pricing":[],'
        '"customer":[],"strategy":[]},'
        '"positive_signals":[{"title":"...","summary":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"}],'
        '"negative_signals":[{"title":"...","summary":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"}],'
        '"watchlist":["..."],'
        '"claims":[{"text":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"}]'
        "}\n"
        "Use only source_ids returned by tools. "
        f"Language: {request.language}"
    )


def _final_business_driver_instruction(request: AgentRequest, state: AgentState) -> str:
    return (
        f"Write the business driver report JSON for {state.ticker} from the evidence context.\n"
        "Return exactly these top-level keys: driver_thesis, driver_map, positive_signals, "
        "negative_signals, watchlist, claims.\n"
        "Write it as an investment memo, not a recap. driver_thesis.summary must state "
        "the operating conclusion, the so what for investors, and the strongest "
        "counter-evidence if the evidence is mixed. The watchlist must include what would "
        "change the conclusion next quarter.\n"
        "driver_map must contain product, segment, geography, demand, pricing, customer, "
        "strategy arrays. Cover at least four driver_map lenses when evidence exists, "
        "and leave unsupported lenses empty rather than inventing facts. positive_signals "
        "should be bullish evidence; negative_signals should be bearish evidence or "
        "counter-evidence. Do not use schema labels or placeholders as prose, including "
        "Evidence point, Business driver thesis, driver_map, positive_signals, or N/A. "
        "Every section should explain conclusion, investor relevance, and the evidence "
        "limit or counter-evidence when material. Keep each array to at most 2 concise "
        "items. Every analytical point that cites evidence must use only source_ids "
        "present in evidence context.\n"
        f"Language: {request.language}"
    )
