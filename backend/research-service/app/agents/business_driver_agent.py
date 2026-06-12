from __future__ import annotations

import json
from time import perf_counter
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from app.agents.llm_gateway import _parse_json_text
from app.agents.sentiment_sources import (
    SentimentSourceBlock,
    SentimentSourceStatus,
    fetch_market_sentiment_sources,
)
from app.agents.tool_calling_graph import _json_response_llm
from app.contracts.agent import AgentEvent, AgentPhase, AgentRequest, AgentState, ToolStatus
from app.contracts.research_task import ResearchTaskType

_SENTIMENT_FINAL_MAX_TOKENS = 1536
_SENTIMENT_FINAL_TIMEOUT_SECONDS = 75
_SENTIMENT_SOURCE_CONTEXT_MAX_LINES = 5
_SENTIMENT_SOURCE_CONTEXT_LINE_LIMIT = 220
_SENTIMENT_RETRY_CONTEXT_MAX_LINES = 3
_SENTIMENT_RETRY_CONTEXT_LINE_LIMIT = 160


class BusinessDriverAgentError(RuntimeError):
    def __init__(self, message: str, *, state: AgentState) -> None:
        super().__init__(message)
        self.state = state


_SENTIMENT_JSON_SHAPE = json.dumps(
    {
        "sentiment_header": {
            "overall_band": (
                "Bullish|Mildly Bullish|Neutral|Mixed|Mildly Bearish|Bearish"
            ),
            "overall_score": 0,
            "confidence": "low|medium|high",
            "summary": "...",
        },
        "narrative_snapshot": {
            "title": "...",
            "summary": "...",
            "source_ids": [
                "sentiment:yahoo_news",
                "sentiment:stocktwits",
                "sentiment:reddit",
            ],
            "citation_status": "supported|partial|missing|unverified",
        },
        "bull_bear_narrative": {
            "bull_case": "...",
            "bear_case": "...",
            "balanced_read": "...",
        },
        "source_divergence": {
            "summary": "...",
            "news_direction": "bullish|mixed|bearish|thin|unavailable",
            "stocktwits_direction": "bullish|mixed|bearish|thin|unavailable",
            "reddit_direction": "bullish|mixed|bearish|thin|unavailable",
        },
        "noise_warnings": ["..."],
        "claims": [],
    },
    ensure_ascii=True,
    indent=2,
)


def run_business_driver_agent(
    *,
    request: AgentRequest,
    state: AgentState,
    llm: BaseChatModel,
    tool_service: object | None = None,
    rag_pipeline: object | None = None,
    max_iterations: int = 1,
) -> tuple[dict[str, Any], AgentState]:
    if request.task_type != ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        raise BusinessDriverAgentError(
            f"Unsupported sentiment task: {request.task_type.value}",
            state=state,
        )

    runtime_state = state
    blocks = fetch_market_sentiment_sources(state.ticker)
    for block in blocks:
        runtime_state = _append_source_event(runtime_state, block)

    final_llm = _sentiment_json_response_llm(llm)
    started_at = perf_counter()
    final_messages = [
        SystemMessage(content=_system_instruction(request)),
        HumanMessage(
            content=_business_driver_instruction(
                request,
                runtime_state,
                source_blocks=blocks,
            )
        ),
    ]
    result, payload = _invoke_and_parse_sentiment_payload(
        final_llm=final_llm,
        final_messages=final_messages,
        request=request,
        state=runtime_state,
        source_blocks=blocks,
    )

    runtime_state = _append_synthesis_event(
        runtime_state,
        result,
        latency_ms=int((perf_counter() - started_at) * 1000),
    )
    return payload, runtime_state


def _sentiment_json_response_llm(llm: BaseChatModel) -> BaseChatModel:
    if hasattr(llm, "model_copy"):
        return llm.model_copy(
            update={
                "tools": [],
                "tool_choice": None,
                "max_tokens": _SENTIMENT_FINAL_MAX_TOKENS,
                "response_format": {"type": "json_object"},
                "timeout_seconds": _SENTIMENT_FINAL_TIMEOUT_SECONDS,
            }
        )
    return _json_response_llm(llm)


def _invoke_and_parse_sentiment_payload(
    *,
    final_llm: BaseChatModel,
    final_messages: list[BaseMessage],
    request: AgentRequest,
    state: AgentState,
    source_blocks: list[SentimentSourceBlock],
) -> tuple[AIMessage, dict[str, Any]]:
    last_error: Exception | None = None
    for attempt in range(2):
        attempt_messages = (
            final_messages
            if attempt == 0
            else _retry_sentiment_messages(
                request,
                state,
                source_blocks=source_blocks,
                last_error=last_error,
            )
        )
        try:
            result = final_llm.invoke(attempt_messages)
        except Exception as exc:
            last_error = exc
            continue
        if not isinstance(result, AIMessage):
            raise BusinessDriverAgentError(
                "Sentiment analyst final LLM did not return an AIMessage",
                state=state,
            )
        try:
            payload = _parse_json_text(_message_content_to_text(result.content))
        except Exception as exc:
            last_error = exc
            continue
        return result, payload

    if isinstance(last_error, json.JSONDecodeError):
        raise BusinessDriverAgentError(
            f"Sentiment analyst final JSON was invalid: {last_error}",
            state=state,
        ) from last_error
    raise BusinessDriverAgentError(
        f"Sentiment analyst final synthesis failed: {last_error}",
        state=state,
    ) from last_error


def _retry_sentiment_messages(
    request: AgentRequest,
    state: AgentState,
    *,
    source_blocks: list[SentimentSourceBlock],
    last_error: Exception | None,
) -> list[BaseMessage]:
    source_context = _compact_sentiment_source_context(
        source_blocks,
        max_lines=_SENTIMENT_RETRY_CONTEXT_MAX_LINES,
        line_limit=_SENTIMENT_RETRY_CONTEXT_LINE_LIMIT,
    )
    retry_notice = (
        f"The previous attempt failed: {last_error}. "
        "Return one smaller valid JSON object only."
    )
    if _is_zh_locale(request.language):
        return [
            SystemMessage(
                content=(
                    "你是市场叙事与情绪分析师。只基于预抓取来源输出 JSON，"
                    "不要编造新闻、Reddit、X 或 StockTwits 内容。"
                )
            ),
            HumanMessage(
                content=(
                    f"{retry_notice}\n"
                    "字段只保留 sentiment_header、narrative_snapshot、bull_bear_narrative、"
                    "source_divergence、noise_warnings、claims。"
                    "每个字段用 1-2 句中文，专有名词保持英文，数组最多 3 项。\n"
                    f"Ticker: {state.ticker}\n"
                    f"Language: {request.language}\n"
                    "Compact source blocks:\n"
                    f"{source_context}"
                )
            ),
        ]
    return [
        SystemMessage(
            content=(
                "You are a market narrative and sentiment analyst. Use only the "
                "prefetched sources. Return JSON only."
            )
        ),
        HumanMessage(
            content=(
                f"{retry_notice}\n"
                "Keep fields sentiment_header, narrative_snapshot, bull_bear_narrative, "
                "source_divergence, noise_warnings, and claims. Use 1-2 sentences per "
                "field, arrays with at most 3 items, and no markdown.\n"
                f"Ticker: {state.ticker}\n"
                f"Language: {request.language}\n"
                "Compact source blocks:\n"
                f"{source_context}"
            )
        ),
    ]


def _system_instruction(request: AgentRequest) -> str:
    if _is_zh_locale(request.language):
        return (
            "你是多智能体投资研究系统里的市场叙事与情绪分析师。"
            "你的任务不是证明公司基本面，而是基于已经预抓取的 Yahoo Finance news、"
            "StockTwits messages 和 Reddit discussion，判断市场当前如何讨论这个 ticker。"
            "只返回 JSON。"
        )
    return (
        "You are the market narrative and sentiment analyst in a multi-agent "
        "investment research system. Your job is not to prove fundamentals. "
        "Use the pre-fetched Yahoo Finance news, StockTwits messages, and Reddit "
        "discussion to explain how the market is currently talking about this ticker. "
        "Return JSON only."
    )


def _business_driver_instruction(
    request: AgentRequest,
    state: AgentState,
    *,
    source_blocks: list[SentimentSourceBlock] | None = None,
) -> str:
    blocks = source_blocks or []
    source_context = _compact_sentiment_source_context(blocks) if blocks else ""
    if _is_zh_locale(request.language):
        return (
            f"请为 {state.ticker} 生成“市场叙事与情绪”typed task sections。\n"
            "数据源只允许使用下面预抓取的 Yahoo Finance news、StockTwits messages "
            "和 Reddit discussion。\n"
            "不要编造 Reddit、X、StockTwits 或新闻内容；如果某个来源 unavailable、empty "
            "或样本很少，必须在 confidence、source_divergence 或 noise_warnings 里说明。\n"
            "不要写成财报基本面分析，不要使用 SEC/RAG/company facts 作为默认证据。\n"
            "中文输出为主，但 Yahoo Finance、StockTwits、Reddit、Bullish、Bearish "
            "和 ticker 保持英文。\n"
            "Return JSON shape:\n"
            f"{_SENTIMENT_JSON_SHAPE}\n"
            "每个结论都要明确来自哪个来源，不要泛泛而谈。\n\n"
            f"Ticker: {state.ticker}\n"
            f"Language: {request.language}\n"
            "Prefetched source blocks:\n"
            f"{source_context}"
        )
    return (
        f"Generate typed task sections for {state.ticker} Market Narrative & Sentiment.\n"
        "Only use the pre-fetched Yahoo Finance news, StockTwits messages, and Reddit "
        "discussion below.\n"
        "Do not invent Reddit, X, StockTwits, or news content. If a source is unavailable, "
        "empty, or thin, disclose that in confidence, source_divergence, or noise_warnings.\n"
        "Do not write a fundamental earnings report. Do not rely on SEC/RAG/company facts "
        "as default evidence.\n"
        "Return JSON only with this shape:\n"
        f"{_SENTIMENT_JSON_SHAPE}\n"
        "Make every conclusion source-specific and investor-facing.\n\n"
        f"Ticker: {state.ticker}\n"
        f"Language: {request.language}\n"
        "Prefetched source blocks:\n"
        f"{source_context}"
    )


def _compact_sentiment_source_context(
    blocks: list[SentimentSourceBlock],
    *,
    max_lines: int = _SENTIMENT_SOURCE_CONTEXT_MAX_LINES,
    line_limit: int = _SENTIMENT_SOURCE_CONTEXT_LINE_LIMIT,
) -> str:
    compacted: list[dict[str, Any]] = []
    for block in blocks:
        compacted.append(
            {
                "source": block.source,
                "status": block.status.value,
                "item_count": block.item_count,
                "degraded_reason": block.degraded_reason or "",
                "key_lines": _sentiment_key_lines(
                    block,
                    max_lines=max_lines,
                    line_limit=line_limit,
                ),
            }
        )
    return json.dumps(compacted, ensure_ascii=False, indent=2)


def _sentiment_key_lines(
    block: SentimentSourceBlock,
    *,
    max_lines: int = _SENTIMENT_SOURCE_CONTEXT_MAX_LINES,
    line_limit: int = _SENTIMENT_SOURCE_CONTEXT_LINE_LIMIT,
) -> list[str]:
    lines = [line.strip() for line in block.content.splitlines() if line.strip()]
    return [_clip_sentiment_line(line, line_limit) for line in lines[:max_lines]]


def _clip_sentiment_line(line: str, limit: int) -> str:
    if len(line) <= limit:
        return line
    if limit <= 3:
        return line[:limit]
    return f"{line[: limit - 3].rstrip()}..."


def _append_source_event(state: AgentState, block: SentimentSourceBlock) -> AgentState:
    tool_name = _tool_name_for_source(block.source)
    status = _tool_status(block.status)
    source_ref = {
        "source_id": f"sentiment:{block.source}",
        "section": block.source,
        "snippet": block.content[:500],
        "citation_status": (
            "supported" if block.status == SentimentSourceStatus.OK else "unverified"
        ),
    }
    event = AgentEvent(
        run_id=state.run_id,
        task_type=state.task_type,
        phase=AgentPhase.RETRIEVE_EVIDENCE,
        status=status,
        summary=_event_summary(block),
        tool_name=tool_name,
        event_kind="tool",
        agent_name="Sentiment analyst",
        model_name=state.model,
        tool_input={"source": block.source, "ticker": state.ticker},
        latency_ms=0,
        degraded_reason=block.degraded_reason,
    )
    evidence_memory = state.evidence_memory.model_copy(deep=True)
    evidence_memory.source_refs.append(source_ref)
    next_state = state.model_copy(
        update={
            "step_index": state.step_index + 1,
            "tool_call_count": state.tool_call_count + 1,
            "evidence_memory": evidence_memory,
            "tool_events": [*state.tool_events, event],
            "retrieval_records": [
                *state.retrieval_records,
                {
                    "tool_name": tool_name,
                    "step_index": state.step_index,
                    "status": status.value,
                    "source": block.source,
                    "item_count": block.item_count,
                    "source_ref_count": 1,
                },
            ],
            "degraded_reasons": (
                [*state.degraded_reasons, block.degraded_reason]
                if block.degraded_reason and block.status == SentimentSourceStatus.DEGRADED
                else state.degraded_reasons
            ),
        }
    )
    return next_state


def _append_synthesis_event(
    state: AgentState,
    message: AIMessage,
    *,
    latency_ms: int,
) -> AgentState:
    metadata = message.response_metadata if isinstance(message.response_metadata, dict) else {}
    event = AgentEvent(
        run_id=state.run_id,
        task_type=state.task_type,
        phase=AgentPhase.DRAFT_REPORT_SECTIONS,
        status=ToolStatus.OK,
        summary="Sentiment analyst synthesized the market narrative sections.",
        event_kind="reasoning",
        agent_name="Sentiment analyst",
        model_name=state.model,
        latency_ms=latency_ms or _int_value(metadata.get("latency_ms")),
        usage=_dict_value(metadata.get("usage")),
    )
    return state.model_copy(update={"tool_events": [*state.tool_events, event]})


def _tool_name_for_source(source: str) -> str:
    return {
        "yahoo_news": "fetch_yahoo_news",
        "stocktwits": "fetch_stocktwits",
        "reddit": "fetch_reddit",
    }.get(source, f"fetch_{source}")


def _tool_status(status: SentimentSourceStatus) -> ToolStatus:
    if status == SentimentSourceStatus.OK:
        return ToolStatus.OK
    if status == SentimentSourceStatus.EMPTY:
        return ToolStatus.EMPTY
    return ToolStatus.DEGRADED


def _event_summary(block: SentimentSourceBlock) -> str:
    labels = {
        "yahoo_news": "Collected Yahoo Finance news for market sentiment.",
        "stocktwits": "Collected StockTwits messages for retail sentiment.",
        "reddit": "Collected Reddit discussion for community sentiment.",
    }
    return labels.get(block.source, f"Collected {block.source} for market sentiment.")


def _message_content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    return json.dumps(content, ensure_ascii=True)


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _dict_value(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _is_zh_locale(language: str | None) -> bool:
    return str(language or "").lower().startswith("zh")
