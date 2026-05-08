from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.agents.llm_gateway import LlmClient, LlmRequest
from app.contracts.agent import AgentState, ToolCall


class PlannerDecisionType(StrEnum):
    CALL_TOOL = "call_tool"
    FINALIZE = "finalize"
    DEGRADED = "degraded"


class PlannerDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: PlannerDecisionType
    summary: str = Field(min_length=1)
    tool_call: ToolCall | None = None
    degraded_reason: str | None = None


class _PlannerJson(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: PlannerDecisionType
    summary: str = Field(min_length=1)
    tool_name: str | None = None
    tool_input: dict[str, Any] = Field(default_factory=dict)


def plan_next_step(state: AgentState, client: LlmClient) -> PlannerDecision:
    if state.provider is None:
        return PlannerDecision(
            decision=PlannerDecisionType.DEGRADED,
            summary="Planner provider is not configured.",
            degraded_reason="Planner provider is not configured.",
        )

    try:
        response = client.complete_json(
            LlmRequest(
                run_id=state.run_id,
                provider=state.provider,
                model=state.model,
                task_type=state.task_type,
                system_prompt=_system_prompt(),
                user_prompt=_user_prompt(state),
                state=state,
                timeout_seconds=15,
            )
        )
        payload = _PlannerJson.model_validate(response.content)
        if payload.decision == PlannerDecisionType.FINALIZE:
            return PlannerDecision(
                decision=PlannerDecisionType.FINALIZE,
                summary=payload.summary,
            )
        if not payload.tool_name:
            raise ValueError("call_tool decision requires tool_name")
        return PlannerDecision(
            decision=PlannerDecisionType.CALL_TOOL,
            summary=payload.summary,
            tool_call=ToolCall(
                run_id=state.run_id,
                task_type=state.task_type,
                step_index=state.step_index,
                tool_name=payload.tool_name,
                tool_input=_normalize_tool_input(payload.tool_name, payload.tool_input, state),
                summary=payload.summary,
            ),
        )
    except (ValidationError, ValueError) as exc:
        reason = f"Planner JSON was invalid: {exc}"
        return PlannerDecision(
            decision=PlannerDecisionType.DEGRADED,
            summary=reason,
            degraded_reason=reason,
        )
    except Exception as exc:
        reason = f"Planner failed: {exc}"
        return PlannerDecision(
            decision=PlannerDecisionType.DEGRADED,
            summary=reason,
            degraded_reason=reason,
        )


def _normalize_tool_input(
    tool_name: str,
    tool_input: dict[str, Any],
    state: AgentState,
) -> dict[str, Any]:
    defaults: dict[str, dict[str, Any]] = {
        "get_company_facts": {
            "period": "latest_quarter",
            "metrics": ["revenue", "gross margin"],
        },
        "search_filing_sections": {
            "sections": ["MD&A"],
            "query": f"{state.task_type.value.replace('_', ' ')} evidence",
        },
        "search_metric_evidence": {
            "metrics": ["revenue"],
            "period": "latest_quarter",
            "query": f"{state.task_type.value.replace('_', ' ')} metrics",
        },
        "get_business_signals": {
            "signal_types": ["product", "segment", "demand", "pricing", "strategy"],
        },
        "verify_citations": {
            "claims": [],
            "source_refs": [],
        },
        "finalize_report": {
            "coverage": {},
            "draft_sections": {},
        },
    }
    if tool_name not in defaults:
        return tool_input
    return defaults[tool_name] | tool_input


def _system_prompt() -> str:
    return (
        "You are a bounded financial research planner. Return one JSON object only. "
        "Do not include markdown, prose, or chain-of-thought."
    )


def _user_prompt(state: AgentState) -> str:
    default_tool = state.task_policy.allowed_tools[0]
    remaining_steps = max(state.task_policy.max_steps - state.step_index, 0)
    remaining_tool_calls = max(state.task_policy.max_tool_calls - state.tool_call_count, 0)
    missing_outputs = (
        ", ".join(state.coverage.missing_outputs) if state.coverage.missing_outputs else "none"
    )
    return (
        "Choose the next tool for this task.\n"
        'Schema: {"decision":"call_tool","summary":"...","tool_name":"...","tool_input":{}}\n'
        'Or: {"decision":"finalize","summary":"..."}\n'
        f"Task: {state.task_type.value}\n"
        f"Allowed tools: {', '.join(state.task_policy.allowed_tools)}\n"
        f"Required outputs: {', '.join(state.task_policy.required_outputs)}\n"
        f"Coverage status: {state.coverage.status}\n"
        f"Evidence count: {state.coverage.evidence_count}\n"
        f"Citation coverage: {state.coverage.citation_coverage}\n"
        f"Missing outputs: {missing_outputs}\n"
        f"Remaining steps: {remaining_steps}\n"
        f"Remaining tool calls: {remaining_tool_calls}\n"
        f"Recommended first tool: {default_tool}\n"
        f'Return a call_tool decision for "{default_tool}" unless evidence is already sufficient.'
    )
