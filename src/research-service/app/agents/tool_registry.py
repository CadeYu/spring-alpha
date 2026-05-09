from collections.abc import Callable, Iterable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agents.domain_tools import DeterministicResearchToolService
from app.contracts.agent import (
    MVP_TOOL_NAMES,
    AgentEvent,
    AgentPhase,
    AgentRunStatus,
    AgentState,
    ToolCall,
    ToolResult,
    ToolStatus,
)
from app.contracts.tools import (
    BusinessSignalsInput,
    CitationVerificationInput,
    CompanyFactsInput,
    FilingSectionSearchInput,
    FinalizeReportInput,
    MetricEvidenceInput,
)

ToolHandler = Callable[[Any, AgentState], ToolResult | BaseModel | dict[str, Any]]


@dataclass(frozen=True)
class RegisteredTool:
    name: str
    input_model: type[BaseModel]
    handler: ToolHandler
    output_model: type[BaseModel] = ToolResult
    description: str = ""
    timeout_seconds: int = 10
    requires_evidence: bool = False

    def __post_init__(self) -> None:
        if self.name not in MVP_TOOL_NAMES:
            raise ValueError(f"Unsupported tool: {self.name}")


class ToolRegistry:
    def __init__(self, tools: Iterable[RegisteredTool]) -> None:
        registered_tools = list(tools)
        self._tools = {tool.name: tool for tool in registered_tools}
        if len(self._tools) != len(registered_tools):
            raise ValueError("Tool names must be unique")

    @property
    def tool_names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def execute(self, state: AgentState, call: ToolCall) -> AgentState:
        if state.tool_call_count >= state.task_policy.max_tool_calls:
            return self._degrade(
                state,
                call,
                status=ToolStatus.DEGRADED,
                reason=(f"Tool budget exhausted after {state.task_policy.max_tool_calls} calls."),
            )

        tool = self._tools.get(call.tool_name)
        if tool is None:
            return self._degrade(
                state,
                call,
                status=ToolStatus.DEGRADED,
                reason=f"Unknown tool {call.tool_name}.",
            )

        if call.tool_name not in state.task_policy.allowed_tools:
            return self._degrade(
                state,
                call,
                status=ToolStatus.DEGRADED,
                reason=f"Tool {call.tool_name} is not allowed for {state.task_type.value}.",
            )

        try:
            tool_input = tool.input_model.model_validate(_tool_input_payload(state, call))
        except ValidationError as exc:
            return self._degrade(
                state,
                call,
                status=ToolStatus.ERROR,
                reason=f"Invalid input for {call.tool_name}: {_compact_validation_error(exc)}",
            )

        started_at = perf_counter()
        try:
            raw_result = tool.handler(tool_input, state)
            result = _validate_tool_result(tool.output_model, raw_result)
        except Exception as exc:
            return self._degrade(
                state,
                call,
                status=ToolStatus.ERROR,
                reason=f"Tool {call.tool_name} failed: {exc}",
            )

        latency_ms = result.latency_ms or int((perf_counter() - started_at) * 1000)
        result = result.model_copy(update={"latency_ms": latency_ms})
        return _append_success(state, call, result)

    def _degrade(
        self,
        state: AgentState,
        call: ToolCall,
        *,
        status: ToolStatus,
        reason: str,
    ) -> AgentState:
        event = AgentEvent(
            run_id=state.run_id,
            task_type=state.task_type,
            phase=AgentPhase.DEGRADED,
            status=status,
            summary=call.summary,
            tool_name=call.tool_name,
            degraded_reason=reason,
        )
        return state.model_copy(
            update={
                "status": AgentRunStatus.DEGRADED,
                "degraded_reasons": [*state.degraded_reasons, reason],
                "tool_events": [*state.tool_events, event],
            }
        )


class DeterministicToolRunner:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def run(self, state: AgentState, calls: Iterable[ToolCall]) -> AgentState:
        current = state
        for call in calls:
            current = self._registry.execute(current, call)
            if current.status == AgentRunStatus.DEGRADED:
                break
        return current


def default_tool_registry(service: DeterministicResearchToolService | None = None) -> ToolRegistry:
    domain_service = service or DeterministicResearchToolService()
    return ToolRegistry(
        [
            RegisteredTool(
                name="get_company_facts",
                input_model=CompanyFactsInput,
                handler=domain_service.get_company_facts,
                description="Return deterministic company facts.",
            ),
            RegisteredTool(
                name="search_filing_sections",
                input_model=FilingSectionSearchInput,
                handler=domain_service.search_filing_sections,
                description="Return deterministic filing section evidence.",
                requires_evidence=True,
            ),
            RegisteredTool(
                name="search_metric_evidence",
                input_model=MetricEvidenceInput,
                handler=domain_service.search_metric_evidence,
                description="Return deterministic metric evidence.",
                requires_evidence=True,
            ),
            RegisteredTool(
                name="get_business_signals",
                input_model=BusinessSignalsInput,
                handler=domain_service.get_business_signals,
                description="Return deterministic business signals.",
            ),
            RegisteredTool(
                name="verify_citations",
                input_model=CitationVerificationInput,
                handler=domain_service.verify_citations,
                description="Return deterministic citation checks.",
            ),
            RegisteredTool(
                name="finalize_report",
                input_model=FinalizeReportInput,
                handler=domain_service.finalize_report,
                description="Return deterministic finalization payload.",
            ),
        ]
    )


def _append_success(state: AgentState, call: ToolCall, result: ToolResult) -> AgentState:
    event = AgentEvent(
        run_id=state.run_id,
        task_type=state.task_type,
        phase=_phase_for_tool(call.tool_name),
        status=result.status,
        summary=call.summary,
        tool_name=call.tool_name,
        latency_ms=result.latency_ms,
        degraded_reason=_first_reason(result),
    )
    evidence_memory = state.evidence_memory.model_copy(deep=True)
    if result.source_refs:
        evidence_memory.source_refs.extend(result.source_refs)
    if call.tool_name == "get_company_facts":
        evidence_memory.facts.update(result.data)
    elif call.tool_name == "search_metric_evidence":
        evidence_memory.metric_evidence.extend(_records_from_result(result))
    elif call.tool_name == "get_business_signals":
        evidence_memory.business_signals.extend(_records_from_result(result))
    elif call.tool_name == "verify_citations":
        evidence_memory.citation_results.extend(_records_from_result(result))

    retrieval_records = [
        *state.retrieval_records,
        {
            "tool_name": call.tool_name,
            "step_index": call.step_index,
            "status": result.status.value,
            "latency_ms": result.latency_ms,
            "source_ref_count": len(result.source_refs),
            **_retrieval_payload(result),
        },
    ]
    return state.model_copy(
        update={
            "status": (
                AgentRunStatus.DEGRADED
                if result.status in {ToolStatus.DEGRADED, ToolStatus.ERROR}
                else state.status
            ),
            "step_index": state.step_index + 1,
            "tool_call_count": state.tool_call_count + 1,
            "evidence_memory": evidence_memory,
            "retrieval_records": retrieval_records,
            "tool_events": [*state.tool_events, event],
            "degraded_reasons": [
                *state.degraded_reasons,
                *result.degraded_reasons,
            ],
        }
    )


def _validate_tool_result(output_model: type[BaseModel], raw_result: Any) -> ToolResult:
    if isinstance(raw_result, ToolResult):
        result = raw_result
    elif isinstance(raw_result, BaseModel):
        result = ToolResult.model_validate(raw_result.model_dump(mode="json"))
    else:
        result = ToolResult.model_validate(raw_result)
    output_model.model_validate(result.model_dump(mode="json"))
    return result


def _phase_for_tool(tool_name: str) -> AgentPhase:
    phases = {
        "get_company_facts": AgentPhase.COLLECT_FINANCIAL_FACTS,
        "search_filing_sections": AgentPhase.RETRIEVE_EVIDENCE,
        "search_metric_evidence": AgentPhase.RETRIEVE_EVIDENCE,
        "get_business_signals": AgentPhase.EXTRACT_SIGNALS,
        "verify_citations": AgentPhase.VALIDATE_CLAIMS,
        "finalize_report": AgentPhase.FINALIZE_REPORT,
    }
    return phases.get(tool_name, AgentPhase.DEGRADED)


def _records_from_result(result: ToolResult) -> list[dict[str, Any]]:
    records = result.data.get("records")
    if isinstance(records, list):
        return [record for record in records if isinstance(record, dict)]
    return [result.data] if result.data else []


def _first_reason(result: ToolResult) -> str | None:
    return result.degraded_reasons[0] if result.degraded_reasons else None


def _retrieval_payload(result: ToolResult) -> dict[str, Any]:
    retrieved_nodes = result.data.get("retrieved_nodes")
    if isinstance(retrieved_nodes, list):
        return {"retrieved_nodes": retrieved_nodes}
    records = result.data.get("records")
    if isinstance(records, list) and any(
        isinstance(record, dict) and "signal_type" in record for record in records
    ):
        signal_types = sorted(
            {
                str(record["signal_type"])
                for record in records
                if isinstance(record, dict) and record.get("signal_type")
            }
        )
        return {
            "signal_count": len(records),
            "signal_types": signal_types,
        }
    metrics = result.data.get("metrics")
    if isinstance(metrics, list):
        payload: dict[str, Any] = {"metric_count": len(metrics)}
        source = result.data.get("source")
        if isinstance(source, str):
            payload["fact_source"] = source
        missing_metrics = result.data.get("missing_metrics")
        if isinstance(missing_metrics, list):
            payload["missing_metric_count"] = len(missing_metrics)
        return payload
    return {}


def _tool_input_payload(state: AgentState, call: ToolCall) -> dict[str, Any]:
    payload = {
        "run_id": state.run_id,
        "ticker": state.ticker,
        "task_type": state.task_type,
        **call.tool_input,
    }
    if call.tool_name != "verify_citations":
        return payload
    source_refs = payload.get("source_refs") or state.evidence_memory.source_refs
    claims = payload.get("claims") or [
        {
            "claim_id": f"{state.run_id}:claim:1",
            "text": _claim_text_for_task(state),
        }
    ]
    return {
        **payload,
        "claims": claims,
        "source_refs": source_refs,
    }


def _claim_text_for_task(state: AgentState) -> str:
    if state.evidence_memory.source_refs:
        snippet = state.evidence_memory.source_refs[0].get("snippet")
        if isinstance(snippet, str) and snippet.strip():
            return snippet
    summaries = {
        "latest_earnings_readout": "Revenue and margin drivers are supported by filing evidence.",
        "business_driver_deep_dive": "Business drivers are supported by filing evidence.",
        "cash_flow_capital_allocation": (
            "Cash flow and capital allocation are supported by filing evidence."
        ),
    }
    return summaries[state.task_type.value]


def _compact_validation_error(exc: ValidationError) -> str:
    first_error = exc.errors()[0]
    location = ".".join(str(item) for item in first_error.get("loc", []))
    message = str(first_error.get("msg", "validation failed"))
    return f"{location}: {message}" if location else message
