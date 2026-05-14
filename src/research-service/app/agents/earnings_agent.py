from __future__ import annotations

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
from app.agents.report_synthesizer import synthesize_latest_earnings_payload
from app.agents.tool_calling_graph import run_tool_calling_graph_agent
from app.contracts.agent import AgentEvent, AgentPhase, AgentRequest, AgentState
from app.contracts.research_task import ResearchTaskType
from app.contracts.tools import CompanyFactsInput, MetricEvidenceInput
from app.rag.llamaindex_pipeline import LlamaIndexRagPipeline


class EarningsAgentError(RuntimeError):
    def __init__(self, message: str, *, state: AgentState) -> None:
        super().__init__(message)
        self.state = state


class CompanyFactsSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str | None = Field(default="latest_quarter")
    metrics: list[str] = Field(default_factory=list)


class MetricEvidenceSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metrics: list[str] = Field(default_factory=list)
    period: str | None = Field(default="latest_quarter")
    query: str | None = None


def run_latest_earnings_agent(
    *,
    request: AgentRequest,
    state: AgentState,
    llm: BaseChatModel,
    tool_service: ResearchToolService,
    rag_pipeline: LlamaIndexRagPipeline | None = None,
    max_iterations: int = 6,
) -> tuple[dict[str, Any], AgentState]:
    if request.task_type != ResearchTaskType.LATEST_EARNINGS_READOUT:
        raise EarningsAgentError(
            f"Unsupported earnings agent task: {request.task_type.value}",
            state=state,
        )

    runtime_state = state
    tools = _latest_earnings_tools(
        request=request,
        state_getter=lambda: runtime_state,
        state_setter=lambda next_state: _set_runtime_state(next_state),
        tool_service=tool_service,
        rag_pipeline=rag_pipeline,
    )

    def _set_runtime_state(next_state: AgentState) -> None:
        nonlocal runtime_state
        runtime_state = next_state

    payload = run_tool_calling_graph_agent(
        agent_name="Earnings agent",
        state_getter=lambda: runtime_state,
        state_setter=_set_runtime_state,
        llm=llm,
        tools=tools,
        required_tools={"get_company_facts", "search_metric_evidence"},
        tool_prompt=_tool_prompt(),
        final_prompt=_final_prompt(),
        initial_instruction=_initial_earnings_instruction(request, runtime_state),
        final_instruction=_final_earnings_instruction(request, runtime_state),
        planned_tool_calls=[
            {"name": "get_company_facts", "args": {}},
            {"name": "search_metric_evidence", "args": {}},
            {"name": "build_evidence_pack", "args": {}},
        ],
        error_factory=lambda message, error_state: EarningsAgentError(
            message,
            state=error_state,
        ),
        max_iterations=max_iterations,
    )
    return payload, runtime_state


def _latest_earnings_tools(
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
            metrics=metrics or ["revenue", "gross margin", "operating income"],
        )
        next_state, payload = _run_domain_tool(
            state_getter(),
            "get_company_facts",
            "Collected company facts for latest earnings.",
            tool_service.get_company_facts(tool_input, state_getter()),
            tool_input.model_dump(mode="json"),
        )
        state_setter(next_state)
        return payload

    def search_metric_evidence(
        metrics: list[str] | None = None,
        period: str | None = "latest_quarter",
        query: str | None = None,
    ) -> str:
        requested_metrics = metrics or ["revenue", "gross margin", "operating income"]
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
            "Searched KPI evidence for latest earnings.",
            tool_service.search_metric_evidence(tool_input, state_getter()),
            tool_input.model_dump(mode="json"),
        )
        state_setter(next_state)
        return payload

    tools = [
        StructuredTool.from_function(
            get_company_facts,
            name="get_company_facts",
            description="Return structured SEC company facts and optional market profile facts.",
            args_schema=CompanyFactsSearchInput,
        ),
        StructuredTool.from_function(
            search_metric_evidence,
            name="search_metric_evidence",
            description="Return KPI evidence records and related source snippets.",
            args_schema=MetricEvidenceSearchInput,
        ),
        create_agent_evidence_pack_tool(
            request=request,
            state_getter=state_getter,
            state_setter=state_setter,
            rag_pipeline=rag_pipeline,
            summary="Built SEC filing evidence pack for latest earnings.",
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
        agent_name="Earnings agent",
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
        "serialized_length": len(json.dumps(evidence_pack, sort_keys=True)),
    }


def _initial_earnings_instruction(request: AgentRequest, state: AgentState) -> str:
    return (
        f"Analyze latest earnings for {state.ticker}.\n"
        "First call get_company_facts. Then call search_metric_evidence for revenue, "
        "gross margin, and operating income. Then call build_evidence_pack once for "
        "operating result drivers. After tool results, return final JSON only.\n"
        "Final JSON must match this shape exactly:\n"
        f"{json.dumps(synthesize_latest_earnings_payload(), ensure_ascii=True)}\n"
        "Use only source_ids returned by tools. Company Profile should be concise and "
        "based on company facts or market profile facts, not RAG snippets.\n"
        f"Language: {request.language}"
    )


def _final_earnings_instruction(request: AgentRequest, state: AgentState) -> str:
    return (
        f"Write the latest earnings report JSON for {state.ticker} from the evidence context.\n"
        "Return exactly these top-level keys: company_profile, topline_verdict, "
        "key_takeaways, financial_dashboard, driver_snapshot, risk_snapshot, claims.\n"
        "Write it as an investment memo, not a metric recap. topline_verdict.summary "
        "must state the earnings conclusion, the so what for investors, and the strongest "
        "counter-evidence if the evidence is mixed. key_takeaways must answer what changed; "
        "risk_snapshot must answer watch next with what would change the conclusion next "
        "quarter.\n"
        "company_profile must be a concise business identity based on company facts or "
        "market profile facts, never filing risk snippets. Use concise one-sentence prose. "
        "Do not use schema labels or placeholders as prose, including Evidence point, "
        "Company profile unavailable, KPI Strip, What Changed, Watch Next, or N/A. "
        "Every array item must use title and summary fields, not headline/body/item. "
        "Use only source_ids present in evidence context; use [] when no citation is needed. "
        "Keep arrays to at most 2 items each.\n"
        "financial_dashboard.metrics should include Revenue, Gross Margin, and Operating Income "
        "when evidence exists.\n"
        f"Language: {request.language}"
    )


def _tool_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an earnings analyst. Use the provided tools to gather company "
                "facts, SEC filing evidence, and KPI evidence. Call only the next tool "
                "needed for evidence collection.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )


def _final_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are the research manager for the earnings desk. Return compact JSON "
                "only. Do not call tools. Do not invent source_ids. Write like a concise "
                "investment memo: give a verdict, explain the so what, include "
                "counter-evidence, and make the next watch item actionable. Keep every "
                "prose field investor-facing.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
