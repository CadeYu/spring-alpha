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
from app.contracts.tools import CompanyFactsInput, FilingSectionSearchInput, MetricEvidenceInput
from app.rag.llamaindex_pipeline import LlamaIndexRagPipeline


class CashFlowAgentError(RuntimeError):
    def __init__(self, message: str, *, state: AgentState) -> None:
        super().__init__(message)
        self.state = state


class CompanyFactsSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str | None = Field(default="latest_quarter")
    metrics: list[str] = Field(default_factory=list)


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


def run_cash_flow_agent(
    *,
    request: AgentRequest,
    state: AgentState,
    llm: BaseChatModel,
    tool_service: ResearchToolService,
    rag_pipeline: LlamaIndexRagPipeline | None = None,
    max_iterations: int = 8,
) -> tuple[dict[str, Any], AgentState]:
    if request.task_type != ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        raise CashFlowAgentError(
            f"Unsupported cash flow task: {request.task_type.value}",
            state=state,
        )

    runtime_state = state

    def set_runtime_state(next_state: AgentState) -> None:
        nonlocal runtime_state
        runtime_state = next_state

    tools = _cash_flow_tools(
        request=request,
        state_getter=lambda: runtime_state,
        state_setter=set_runtime_state,
        tool_service=tool_service,
        rag_pipeline=rag_pipeline,
    )
    payload = run_tool_calling_graph_agent(
        agent_name="Cash flow agent",
        state_getter=lambda: runtime_state,
        state_setter=set_runtime_state,
        llm=llm,
        tools=tools,
        required_tools={
            "get_company_facts",
            "search_filing_sections",
            "search_metric_evidence",
        },
        tool_prompt=_tool_prompt(),
        final_prompt=_final_prompt(),
        initial_instruction=_cash_flow_instruction(request, state),
        final_instruction=_final_cash_flow_instruction(request, state),
        planned_tool_calls=[
            {
                "name": "get_company_facts",
                "args": {
                    "metrics": [
                        "operating cash flow",
                        "capital expenditures",
                        "buybacks",
                    ],
                    "period": "latest_quarter",
                },
            },
            {"name": "search_metric_evidence", "args": {}},
            {
                "name": "build_evidence_pack",
                "args": {"focus": "operating cash flow capex buybacks liquidity", "top_k": 5},
            },
        ],
        error_factory=lambda message, error_state: CashFlowAgentError(
            message,
            state=error_state,
        ),
        max_iterations=max_iterations,
    )
    return payload, runtime_state


def _cash_flow_tools(
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
            metrics=metrics
            or [
                "operating cash flow",
                "capital expenditures",
                "buybacks",
            ],
        )
        next_state, payload = _run_domain_tool(
            state_getter(),
            "get_company_facts",
            "Collected company facts for cash flow.",
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
            "Searched filing sections for cash flow.",
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
        requested_metrics = metrics or [
            "operating cash flow",
            "capital expenditures",
            "buybacks",
        ]
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
            "Searched metric evidence for cash flow.",
            tool_service.search_metric_evidence(tool_input, state_getter()),
            tool_input.model_dump(mode="json"),
        )
        state_setter(next_state)
        return payload

    tools = [
        StructuredTool.from_function(
            get_company_facts,
            name="get_company_facts",
            description="Return cash flow, capex, buyback, liquidity, and debt company facts.",
            args_schema=CompanyFactsSearchInput,
        ),
        StructuredTool.from_function(
            search_filing_sections,
            name="search_filing_sections",
            description=(
                "Search SEC filing sections for operating cash flow, capex, buybacks, "
                "dividends, debt, liquidity, and working capital evidence."
            ),
            args_schema=FilingSearchInput,
        ),
        StructuredTool.from_function(
            search_metric_evidence,
            name="search_metric_evidence",
            description="Return cash flow and capital allocation KPI evidence records.",
            args_schema=MetricSearchInput,
        ),
        create_agent_evidence_pack_tool(
            request=request,
            state_getter=state_getter,
            state_setter=state_setter,
            rag_pipeline=rag_pipeline,
            summary="Built SEC filing evidence pack for cash flow.",
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
        agent_name="Cash flow agent",
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
                "You are a cash flow and capital allocation analyst in a multi-agent "
                "financial research team. Work like a TradingAgents fundamentals analyst: "
                "gather enough tool evidence to judge whether earnings convert to cash and "
                "whether capital allocation compounds or leaks value. Focus "
                "on operating cash flow, free cash flow, capex, buybacks, dividends, debt, "
                "liquidity, and working capital. Call one useful tool at a time.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )


def _final_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are the research manager for the cash flow and capital allocation "
                "desk. Return one JSON object only. Do not call tools. Do not invent "
                "source_ids. Write like a concise investment memo: make the cash quality "
                "verdict explicit, explain the so what for investors, include "
                "counter-evidence where cash conversion or allocation discipline is mixed, "
                "and make uncertainty actionable through red flags. Keep prose "
                "investor-facing.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )


def _cash_flow_instruction(request: AgentRequest, state: AgentState) -> str:
    return (
        f"Analyze cash flow and capital allocation for {state.ticker}.\n"
        "Required workflow:\n"
        "1. Call get_company_facts for operating cash flow, capital expenditures, "
        "and buybacks.\n"
        "2. Call search_metric_evidence for operating cash flow, capital expenditures, "
        "and buybacks.\n"
        "3. Call build_evidence_pack for liquidity, cash flow statement, capital "
        "allocation, buybacks, dividends, debt, capex, and working capital evidence.\n"
        "Final JSON shape:\n"
        "{"
        '"cash_quality_verdict":{"headline":"...",'
        '"earnings_backed_by_cash":"yes|mixed|no|unclear","summary":"..."},'
        '"cash_metrics":[{"name":"...","value":"...","period":"...",'
        '"interpretation":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"}],'
        '"capital_allocation":{"capex":[],"buybacks":[],"dividends":[],"debt":[],'
        '"liquidity":[]},'
        '"allocation_discipline":[{"title":"...","summary":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"}],'
        '"red_flags":[{"title":"...","summary":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"}],'
        '"claims":[{"text":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"}]'
        "}\n"
        "Use only source_ids returned by tools. "
        f"Language: {request.language}"
    )


def _final_cash_flow_instruction(request: AgentRequest, state: AgentState) -> str:
    return (
        f"Write the cash flow and capital allocation report JSON for {state.ticker} from "
        "the evidence context.\n"
        "Return exactly these top-level keys: cash_quality_verdict, cash_metrics, "
        "capital_allocation, allocation_discipline, red_flags, claims.\n"
        "Write it as an investment memo, not a recap. cash_quality_verdict.summary must "
        "state the cash quality conclusion, the so what for investors, and the strongest "
        "counter-evidence if cash conversion or allocation discipline is mixed. red_flags "
        "must include what would change the conclusion next quarter when relevant.\n"
        "capital_allocation must contain capex, buybacks, dividends, debt, liquidity "
        "arrays. Do not use schema labels or placeholders as prose, including Evidence "
        "point, cash_quality_verdict, capital_allocation, red_flags, or N/A. Each section "
        "should connect cash evidence to investor relevance instead of restating metrics. "
        "Keep each array to at most 2 concise items. Every analytical point that cites "
        "evidence must use only source_ids present in evidence context.\n"
        f"Language: {request.language}"
    )
