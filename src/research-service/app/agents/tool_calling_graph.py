import json
from collections.abc import Callable
from typing import Any, Literal, NoReturn, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import StructuredTool
from langgraph.graph import END, StateGraph

from app.agents.llm_gateway import _parse_json_text
from app.contracts.agent import AgentState


class ToolCallingAgentError(RuntimeError):
    def __init__(self, message: str, *, state: AgentState) -> None:
        super().__init__(message)
        self.state = state


class ToolCallingGraphState(TypedDict):
    messages: list[BaseMessage]
    called_tool_names: set[str]
    payload: dict[str, Any] | None
    next_step: Literal["call_model", "execute_tools", "synthesize"]


class PlannedToolCall(TypedDict):
    name: str
    args: dict[str, Any]


def run_tool_calling_graph_agent(
    *,
    agent_name: str,
    state_getter: Callable[[], AgentState],
    llm: BaseChatModel,
    tools: list[StructuredTool],
    required_tools: set[str],
    tool_prompt: ChatPromptTemplate,
    final_prompt: ChatPromptTemplate,
    initial_instruction: str,
    final_instruction: str | None = None,
    planned_tool_calls: list[PlannedToolCall] | None = None,
    error_factory: Callable[[str, AgentState], Exception],
    max_iterations: int = 8,
) -> dict[str, Any]:
    tools_by_name = {tool.name: tool for tool in tools}
    final_llm = _json_response_llm(llm)
    final_chain = final_prompt | final_llm

    if planned_tool_calls is not None:
        return _run_planned_tool_graph(
            agent_name=agent_name,
            tools_by_name=tools_by_name,
            planned_tool_calls=planned_tool_calls,
            final_chain=final_chain,
            compact_synthesis=bool(getattr(final_llm, "compact_synthesis", False)),
            initial_instruction=initial_instruction,
            final_instruction=final_instruction,
            state_getter=state_getter,
            error_factory=error_factory,
        )

    def call_model(graph_state: ToolCallingGraphState) -> ToolCallingGraphState:
        if len(graph_state["messages"]) > max_iterations * 2:
            _raise(f"{agent_name} exceeded tool-call iteration budget")
        tool_chain = tool_prompt | llm.bind_tools(tools, tool_choice="auto")
        try:
            result = tool_chain.invoke({"messages": graph_state["messages"]})
        except Exception as exc:
            _raise(f"{agent_name} tool planning failed: {exc}")
        if not isinstance(result, AIMessage):
            _raise(f"{agent_name} LLM did not return an AIMessage")
        messages = [*graph_state["messages"], result]
        if result.tool_calls:
            return {**graph_state, "messages": messages, "next_step": "execute_tools"}
        missing_tools = required_tools - graph_state["called_tool_names"]
        if missing_tools:
            _raise(
                f"{agent_name} returned no tool calls before required evidence: "
                + ", ".join(sorted(missing_tools))
            )
        try:
            payload = _parse_json_text(_message_content_to_text(result.content))
        except Exception:
            return {**graph_state, "messages": messages, "next_step": "synthesize"}
        return {
            **graph_state,
            "messages": messages,
            "payload": payload,
            "next_step": "synthesize",
        }

    def execute_tools(graph_state: ToolCallingGraphState) -> ToolCallingGraphState:
        last_message = graph_state["messages"][-1]
        if not isinstance(last_message, AIMessage):
            _raise(f"{agent_name} cannot execute tools without an AIMessage")
        called_tool_names = set(graph_state["called_tool_names"])
        messages = list(graph_state["messages"])
        for tool_call in last_message.tool_calls:
            tool_name = str(tool_call.get("name") or "")
            tool = tools_by_name.get(tool_name)
            if tool is None:
                _raise(f"Unknown {agent_name} tool: {tool_name}")
            called_tool_names.add(tool_name)
            try:
                tool_output = tool.invoke(tool_call.get("args") or {})
            except Exception as exc:
                _raise(f"{agent_name} tool failed: {tool_name}: {exc}")
            messages.append(
                ToolMessage(
                    content=tool_output,
                    tool_call_id=str(tool_call.get("id") or tool_name),
                    name=tool_name,
                )
            )
        next_step: Literal["call_model", "execute_tools", "synthesize"] = (
            "synthesize" if required_tools.issubset(called_tool_names) else "call_model"
        )
        return {
            **graph_state,
            "messages": messages,
            "called_tool_names": called_tool_names,
            "next_step": next_step,
        }

    def synthesize(graph_state: ToolCallingGraphState) -> ToolCallingGraphState:
        if graph_state["payload"] is not None:
            return graph_state
        final_messages = [
            HumanMessage(content=final_instruction or initial_instruction),
            HumanMessage(
                content=_evidence_context(
                    graph_state["messages"],
                    compact=bool(getattr(final_llm, "compact_synthesis", False)),
                )
            ),
        ]
        try:
            final_result = _invoke_final_chain_with_retry(
                final_chain,
                final_messages,
                attempts=2 if bool(getattr(final_llm, "compact_synthesis", False)) else 1,
            )
        except Exception as exc:
            _raise(f"{agent_name} final synthesis failed: {exc}")
        if not isinstance(final_result, AIMessage):
            _raise(f"{agent_name} final LLM did not return an AIMessage")
        try:
            payload = _parse_json_text(_message_content_to_text(final_result.content))
        except Exception as exc:
            _raise(f"{agent_name} final JSON was invalid: {exc}")
        return {
            **graph_state,
            "messages": [*graph_state["messages"], final_result],
            "payload": payload,
        }

    def route(graph_state: ToolCallingGraphState) -> str:
        return graph_state["next_step"]

    def _raise(message: str) -> NoReturn:
        raise error_factory(message, state_getter())

    graph = StateGraph(ToolCallingGraphState)
    graph.add_node("call_model", call_model)  # type: ignore[call-overload]
    graph.add_node("execute_tools", execute_tools)  # type: ignore[call-overload]
    graph.add_node("synthesize", synthesize)  # type: ignore[call-overload]
    graph.set_entry_point("call_model")
    graph.add_conditional_edges(
        "call_model",
        route,
        {
            "execute_tools": "execute_tools",
            "synthesize": "synthesize",
            "call_model": "call_model",
        },
    )
    graph.add_conditional_edges(
        "execute_tools",
        route,
        {
            "call_model": "call_model",
            "synthesize": "synthesize",
            "execute_tools": "execute_tools",
        },
    )
    graph.add_edge("synthesize", END)

    result = graph.compile().invoke(
        {
            "messages": [HumanMessage(content=initial_instruction)],
            "called_tool_names": set(),
            "payload": None,
            "next_step": "call_model",
        }
    )
    payload = result.get("payload")
    if not isinstance(payload, dict):
        _raise(f"{agent_name} did not produce a final payload")
    return payload


def _run_planned_tool_graph(
    *,
    agent_name: str,
    tools_by_name: dict[str, StructuredTool],
    planned_tool_calls: list[PlannedToolCall],
    final_chain: Any,
    compact_synthesis: bool,
    initial_instruction: str,
    final_instruction: str | None,
    state_getter: Callable[[], AgentState],
    error_factory: Callable[[str, AgentState], Exception],
) -> dict[str, Any]:
    def execute_plan(graph_state: ToolCallingGraphState) -> ToolCallingGraphState:
        messages = list(graph_state["messages"])
        called_tool_names = set(graph_state["called_tool_names"])
        for index, tool_call in enumerate(planned_tool_calls, start=1):
            tool_name = tool_call["name"]
            tool = tools_by_name.get(tool_name)
            if tool is None:
                _raise(f"Unknown {agent_name} planned tool: {tool_name}")
            try:
                tool_output = tool.invoke(tool_call.get("args") or {})
            except Exception as exc:
                _raise(f"{agent_name} planned tool failed: {tool_name}: {exc}")
            called_tool_names.add(tool_name)
            messages.append(
                ToolMessage(
                    content=tool_output,
                    tool_call_id=f"planned_{index}_{tool_name}",
                    name=tool_name,
                )
            )
        return {
            **graph_state,
            "messages": messages,
            "called_tool_names": called_tool_names,
            "next_step": "synthesize",
        }

    def synthesize(graph_state: ToolCallingGraphState) -> ToolCallingGraphState:
        final_messages = [
            HumanMessage(content=final_instruction or initial_instruction),
            HumanMessage(
                content=_evidence_context(
                    graph_state["messages"],
                    compact=compact_synthesis,
                )
            ),
        ]
        try:
            final_result = _invoke_final_chain_with_retry(
                final_chain,
                final_messages,
                attempts=2 if compact_synthesis else 1,
            )
        except Exception as exc:
            _raise(f"{agent_name} final synthesis failed: {exc}")
        if not isinstance(final_result, AIMessage):
            _raise(f"{agent_name} final LLM did not return an AIMessage")
        try:
            payload = _parse_json_text(_message_content_to_text(final_result.content))
        except Exception as exc:
            _raise(f"{agent_name} final JSON was invalid: {exc}")
        return {
            **graph_state,
            "messages": [*graph_state["messages"], final_result],
            "payload": payload,
        }

    def _raise(message: str) -> NoReturn:
        raise error_factory(message, state_getter())

    graph = StateGraph(ToolCallingGraphState)
    graph.add_node("execute_plan", execute_plan)  # type: ignore[call-overload]
    graph.add_node("synthesize", synthesize)  # type: ignore[call-overload]
    graph.set_entry_point("execute_plan")
    graph.add_edge("execute_plan", "synthesize")
    graph.add_edge("synthesize", END)
    result = graph.compile().invoke(
        {
            "messages": [HumanMessage(content=initial_instruction)],
            "called_tool_names": set(),
            "payload": None,
            "next_step": "call_model",
        }
    )
    payload = result.get("payload")
    if not isinstance(payload, dict):
        _raise(f"{agent_name} did not produce a final payload")
    return payload


def _message_content_to_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    return json.dumps(content, ensure_ascii=True)


def _json_response_llm(llm: BaseChatModel) -> BaseChatModel:
    if hasattr(llm, "model_copy"):
        compact_synthesis = bool(getattr(llm, "compact_synthesis", False))
        return llm.model_copy(
            update={
                "tools": [],
                "tool_choice": None,
                "max_tokens": 768 if compact_synthesis else 1280,
                "response_format": {"type": "json_object"},
                "timeout_seconds": 45,
            }
        )
    return llm


def _invoke_final_chain_with_retry(
    final_chain: Any,
    final_messages: list[HumanMessage],
    *,
    attempts: int,
) -> Any:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            return final_chain.invoke({"messages": final_messages})
        except Exception as exc:
            last_error = exc
    raise last_error or RuntimeError("Final synthesis failed")


def _evidence_context(messages: list[BaseMessage], *, compact: bool = False) -> str:
    tool_payloads = [
        {
            "tool_name": str(getattr(message, "name", "") or ""),
            "content": _compact_tool_content(
                _message_content_to_text(message.content),
                compact=compact,
            ),
        }
        for message in messages
        if message.type == "tool"
    ]
    return "Evidence context JSON:\n" + json.dumps(tool_payloads, ensure_ascii=True)


def _compact_tool_content(content: str, *, compact: bool = False) -> Any:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return content[:800] if compact else content[:2000]
    return _trim_json_value(parsed, compact=compact)


def _trim_json_value(value: Any, *, compact: bool = False) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _trim_json_value(nested, compact=compact)
            for key, nested in value.items()
            if key not in {"retrieved_nodes"}
        }
    if isinstance(value, list):
        limit = 4 if compact else 8
        return [_trim_json_value(item, compact=compact) for item in value[:limit]]
    if isinstance(value, str):
        max_length = 240 if compact else 600
        return value if len(value) <= max_length else value[:max_length]
    return value
