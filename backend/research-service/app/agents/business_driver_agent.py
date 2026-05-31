import json
from collections.abc import Callable
from time import perf_counter
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, ConfigDict, Field

from app.agents.business_driver_quality import (
    BUSINESS_DRIVER_CORE_METRICS,
    BUSINESS_DRIVER_FACT_METRICS,
    business_driver_facts_brief,
)
from app.agents.domain_tools import ResearchToolService
from app.agents.evidence_pack_tool import create_agent_evidence_pack_tool
from app.agents.tool_calling_graph import run_tool_calling_graph_agent
from app.contracts.agent import AgentEvent, AgentPhase, AgentRequest, AgentState
from app.contracts.research_task import ResearchTaskType
from app.contracts.tools import (
    BusinessSignalsInput,
    CompanyFactsInput,
    FilingSectionSearchInput,
    MarketContextInput,
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


class MarketContextSearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    context_types: list[str] = Field(default_factory=list)


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
                    "metrics": BUSINESS_DRIVER_FACT_METRICS,
                    "period": "latest_quarter",
                },
            },
            {
                "name": "get_market_context",
                "args": {
                    "context_types": [
                        "profile",
                        "valuation",
                        "quote",
                        "technical",
                        "news",
                        "sentiment",
                        "macro",
                    ],
                },
            },
            {
                "name": "search_metric_evidence",
                "args": {
                    "metrics": BUSINESS_DRIVER_CORE_METRICS,
                    "period": "latest_quarter",
                },
            },
            {
                "name": "build_evidence_pack",
                "args": {
                    "focus": "revenue bridge segment momentum margin mix demand signals",
                    "top_k": 5,
                },
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
            metrics=metrics or BUSINESS_DRIVER_FACT_METRICS,
        )
        started_at = perf_counter()
        tool_result = tool_service.get_company_facts(tool_input, state_getter())
        tool_latency_ms = int((perf_counter() - started_at) * 1000)
        next_state, payload = _run_domain_tool(
            state_getter(),
            "get_company_facts",
            "Collected company facts for business drivers.",
            tool_result,
            tool_input.model_dump(mode="json"),
            tool_latency_ms=tool_latency_ms,
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
        started_at = perf_counter()
        tool_result = tool_service.search_filing_sections(tool_input, state_getter())
        tool_latency_ms = int((perf_counter() - started_at) * 1000)
        next_state, payload = _run_domain_tool(
            state_getter(),
            "search_filing_sections",
            "Searched filing sections for business drivers.",
            tool_result,
            tool_input.model_dump(mode="json"),
            tool_latency_ms=tool_latency_ms,
        )
        state_setter(next_state)
        return payload

    def search_metric_evidence(
        metrics: list[str] | None = None,
        period: str | None = "latest_quarter",
        query: str | None = None,
    ) -> str:
        requested_metrics = metrics or BUSINESS_DRIVER_CORE_METRICS
        tool_input = MetricEvidenceInput(
            run_id=request.run_id,
            ticker=request.ticker,
            task_type=request.task_type,
            metrics=requested_metrics,
            period=period,
            query=query,
        )
        started_at = perf_counter()
        tool_result = tool_service.search_metric_evidence(tool_input, state_getter())
        tool_latency_ms = int((perf_counter() - started_at) * 1000)
        next_state, payload = _run_domain_tool(
            state_getter(),
            "search_metric_evidence",
            "Searched metric evidence for business drivers.",
            tool_result,
            tool_input.model_dump(mode="json"),
            tool_latency_ms=tool_latency_ms,
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
        started_at = perf_counter()
        tool_result = tool_service.get_business_signals(tool_input, state_getter())
        tool_latency_ms = int((perf_counter() - started_at) * 1000)
        next_state, payload = _run_domain_tool(
            state_getter(),
            "get_business_signals",
            "Extracted business driver signals.",
            tool_result,
            tool_input.model_dump(mode="json"),
            tool_latency_ms=tool_latency_ms,
        )
        state_setter(next_state)
        return payload

    def get_market_context(context_types: list[str] | None = None) -> str:
        tool_input = MarketContextInput(
            run_id=request.run_id,
            ticker=request.ticker,
            task_type=request.task_type,
            context_types=context_types or [],
        )
        started_at = perf_counter()
        tool_result = tool_service.get_market_context(tool_input, state_getter())
        tool_latency_ms = int((perf_counter() - started_at) * 1000)
        next_state, payload = _run_domain_tool(
            state_getter(),
            "get_market_context",
            "Collected market, sentiment, technical, and macro context.",
            tool_result,
            tool_input.model_dump(mode="json"),
            tool_latency_ms=tool_latency_ms,
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
            get_market_context,
            name="get_market_context",
            description=(
                "Return preloaded market context such as business profile, valuation, quote, "
                "technical trend, news headlines, market sentiment, and macro context."
            ),
            args_schema=MarketContextSearchInput,
        ),
        StructuredTool.from_function(
            search_filing_sections,
            name="search_filing_sections",
            description=(
                "Search SEC filing sections for revenue bridge, segment momentum, "
                "margin and mix, and demand signals evidence."
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
    *,
    tool_latency_ms: int | None = None,
) -> tuple[AgentState, str]:
    started_at = perf_counter()
    latency_ms = tool_latency_ms if tool_latency_ms is not None else result.latency_ms
    if latency_ms <= 0:
        latency_ms = int((perf_counter() - started_at) * 1000)
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
        latency_ms=latency_ms,
        degraded_reason=result.degraded_reasons[0] if result.degraded_reasons else None,
    )
    evidence_memory = state.evidence_memory.model_copy(deep=True)
    if result.source_refs:
        evidence_memory.source_refs.extend(result.source_refs)
    if tool_name == "get_company_facts":
        evidence_memory.facts.update(result.data)
    if tool_name == "get_market_context":
        evidence_memory.market_context.update(result.data)
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
    if tool_name in {"get_company_facts", "get_market_context"}:
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
                "to investors. Focus on revenue bridge, segment momentum, margin and mix, "
                "and demand signals. Do not over-index "
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
                "mixed, and make uncertainty explicit inside the relevant paragraph. Keep prose "
                "investor-facing.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )


def _business_driver_instruction(request: AgentRequest, state: AgentState) -> str:
    facts_brief = business_driver_facts_brief(state, request.language)
    if _is_zh_locale(request.language):
        return (
            f"请分析 {state.ticker} 的业务驱动因素。\n"
            "Required workflow:\n"
            "1. 调用 get_company_facts 获取 company profile 和核心 revenue facts。\n"
            "2. 调用 get_market_context 获取 valuation、quote、technical、news、sentiment "
            "和 macro context。\n"
            "3. 调用 search_metric_evidence 获取 revenue、segment revenue、margin "
            "和 profitability KPIs。\n"
            "4. 调用 build_evidence_pack 获取 revenue bridge、segment momentum、margin and mix "
            "和 demand signals 证据。\n"
            "5. 在 filing 或 metric evidence 已存在后调用 get_business_signals。\n"
            f"{facts_brief}\n"
            "Final JSON shape:\n"
            "{"
            '"driver_thesis":{"headline":"...","durability":"durable|mixed|temporary|unclear",'
            '"summary":"..."},'
            '"driver_map":{"revenue_bridge":{"title":"...","summary":"...","source_ids":["..."],'
            '"citation_status":"supported|partial|missing|unverified"},'
            '"segment_momentum":{"title":"...","summary":"...","source_ids":["..."],'
            '"citation_status":"supported|partial|missing|unverified"},'
            '"margin_and_mix":{"title":"...","summary":"...","source_ids":["..."],'
            '"citation_status":"supported|partial|missing|unverified"},'
            '"demand_signals":{"title":"...","summary":"...","source_ids":["..."],'
            '"citation_status":"supported|partial|missing|unverified"}},'
            '"claims":[{"text":"...","source_ids":["..."],'
            '"citation_status":"supported|partial|missing|unverified"}]'
            "}\n"
            "driver_map 的四个字段都是单段 point，不要返回数组。只能使用工具返回的 source_ids。"
            "如果 segment 或 RAG 证据不完整，也要基于结构化 facts brief 给出谨慎的方向性判断，"
            "不要输出 No evidence、无法判断 或类似占位句。"
            f"Language: {request.language}"
        )
    return (
        f"Analyze business drivers for {state.ticker}.\n"
        "Required workflow:\n"
        "1. Call get_company_facts for company profile and core revenue facts.\n"
        "2. Call get_market_context for valuation, quote, technical, news, sentiment, "
        "and macro context.\n"
        "3. Call search_metric_evidence for revenue, segment revenue, margin, and "
        "profitability KPIs.\n"
        "4. Call build_evidence_pack for revenue bridge, segment momentum, margin and mix, "
        "and demand signals evidence.\n"
        "5. Call get_business_signals after filing or metric evidence exists.\n"
        f"{facts_brief}\n"
        "Final JSON shape:\n"
        "{"
        '"driver_thesis":{"headline":"...","durability":"durable|mixed|temporary|unclear",'
        '"summary":"..."},'
        '"driver_map":{"revenue_bridge":{"title":"...","summary":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"},'
        '"segment_momentum":{"title":"...","summary":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"},'
        '"margin_and_mix":{"title":"...","summary":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"},'
        '"demand_signals":{"title":"...","summary":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"}},'
        '"claims":[{"text":"...","source_ids":["..."],'
        '"citation_status":"supported|partial|missing|unverified"}]'
        "}\n"
        "Each driver_map field is a single paragraph point, not an array. "
        "Use only source_ids returned by tools. "
        "If segment or RAG evidence is incomplete, use the structured facts brief to write "
        "a cautious directional conclusion. Do not output No evidence, unable to determine, "
        "or similar placeholders. "
        f"Language: {request.language}"
    )


def _final_business_driver_instruction(request: AgentRequest, state: AgentState) -> str:
    facts_brief = business_driver_facts_brief(state, request.language)
    if _is_zh_locale(request.language):
        return (
            f"请基于 evidence context 为 {state.ticker} 写出 business driver report JSON。\n"
            "只返回这些顶层 keys: driver_thesis, driver_map, claims。\n"
            "写成投资备忘录，而不是简单复述。driver_thesis.summary 必须说明经营结论、"
            "对投资者的意义，以及如果证据 mixed 时最强的反证。\n"
            "driver_map 必须包含 revenue_bridge, segment_momentum, margin_and_mix, "
            "demand_signals 四个单段 point。每段 summary 写 3-5 句，覆盖结论、证据、"
            "投资含义和证据限制。不要编造事实。"
            "不要把 schema labels 或 placeholders 写进正文，包括 Evidence point, Business driver thesis, "
            "driver_map 或 N/A。任何引用证据的分析点都只能使用 evidence context 中存在的 source_ids。\n"
            f"{facts_brief}\n"
            "如果 evidence context 的 segment 或 RAG 证据不完整，也要基于 facts brief 写方向性结论，"
            "不要输出 No evidence、无法判断 或类似占位句。\n"
            f"Language: {request.language}"
        )
    return (
        f"Write the business driver report JSON for {state.ticker} from the evidence context.\n"
        "Return exactly these top-level keys: driver_thesis, driver_map, claims.\n"
        "Write it as an investment memo, not a recap. driver_thesis.summary must state "
        "the operating conclusion, the so what for investors, and the strongest "
        "counter-evidence if the evidence is mixed.\n"
        "driver_map must contain four single paragraph points: revenue_bridge, "
        "segment_momentum, margin_and_mix, and demand_signals. Each summary should be "
        "3-5 sentences covering conclusion, evidence, investor relevance, and evidence "
        "limits. Do not invent facts. Do not use schema labels or placeholders as prose, "
        "including Evidence point, Business driver thesis, driver_map, or N/A. "
        "Every analytical point that cites evidence must use only source_ids present in "
        "evidence context.\n"
        f"{facts_brief}\n"
        "If segment or RAG evidence is incomplete, use the structured facts brief to write "
        "a cautious directional conclusion. Do not output No evidence, unable to determine, "
        "or similar placeholders.\n"
        f"Language: {request.language}"
    )


def _is_zh_locale(language: str | None) -> bool:
    return str(language or "").lower().startswith("zh")
