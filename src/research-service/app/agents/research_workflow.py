import logging
from time import perf_counter
from typing import Any

from app.agents.business_driver_agent import BusinessDriverAgentError, run_business_driver_agent
from app.agents.cash_flow_agent import CashFlowAgentError, run_cash_flow_agent
from app.agents.domain_tools import ResearchToolService
from app.agents.earnings_agent import EarningsAgentError, run_latest_earnings_agent
from app.agents.llm_gateway import LlmClient, OpenAiCompatibleLlmClient
from app.agents.report_synthesizer import (
    build_business_driver_report_from_payload,
    build_cash_flow_report_from_payload,
    build_latest_earnings_report_from_payload,
)
from app.contracts.agent import (
    AgentEvent,
    AgentPhase,
    AgentRequest,
    AgentRunStatus,
    AgentState,
    BoundedAgentResult,
    ToolStatus,
    default_task_policy,
)
from app.contracts.report import EvidenceAwareReport
from app.contracts.research_task import ResearchTaskType

logger = logging.getLogger("uvicorn.error")


class ResearchAgentWorkflow:
    def __init__(
        self,
        *,
        tool_service: ResearchToolService | None = None,
        llm_client: LlmClient | None = None,
        rag_pipeline: Any | None = None,
    ) -> None:
        self._tool_service = tool_service or ResearchToolService()
        self._llm_client = llm_client
        self._rag_pipeline = rag_pipeline

    def run(self, request: AgentRequest) -> BoundedAgentResult:
        state = AgentState(
            run_id=request.run_id,
            ticker=request.ticker,
            task_type=request.task_type,
            language=request.language,
            provider=self._llm_client.provider if self._llm_client else None,
            model=request.llm_model if self._llm_client else None,
            task_policy=default_task_policy(request.task_type),
        )
        if request.facts:
            state = state.model_copy(
                update={
                    "evidence_memory": state.evidence_memory.model_copy(
                        update={"facts": dict(request.facts)}
                    )
                }
            )

        if not isinstance(self._llm_client, OpenAiCompatibleLlmClient):
            state = _append_degraded_event(
                state,
                "OpenAI-compatible LLM client is required for tool-calling research agents.",
            )
            return _result(request, state, final_report=None)

        started_at = perf_counter()
        try:
            final_report, state = self._run_task_agent(request, state, self._llm_client)
        except EarningsAgentError as exc:
            state = _append_degraded_event(
                exc.state,
                f"Earnings research agent failed. {exc}",
                degraded_reason=f"Earnings research agent failed: {exc}",
            )
            final_report = None
        except BusinessDriverAgentError as exc:
            state = _append_degraded_event(
                exc.state,
                f"Business driver research agent failed. {exc}",
                degraded_reason=f"Business driver research agent failed: {exc}",
            )
            final_report = None
        except CashFlowAgentError as exc:
            state = _append_degraded_event(
                exc.state,
                f"Cash flow research agent failed. {exc}",
                degraded_reason=f"Cash flow research agent failed: {exc}",
            )
            final_report = None
        except Exception as exc:
            state = _append_degraded_event(
                state,
                f"Tool-calling research agent failed. {exc}",
                degraded_reason=f"Tool-calling research agent failed: {exc}",
            )
            final_report = None
        logger.info(
            "research_agent_complete run_id=%s task_type=%s latency_ms=%s events=%s",
            request.run_id,
            request.task_type.value,
            int((perf_counter() - started_at) * 1000),
            len(state.tool_events),
        )
        return _result(request, state, final_report=final_report)

    def _run_task_agent(
        self,
        request: AgentRequest,
        state: AgentState,
        llm_client: OpenAiCompatibleLlmClient,
    ) -> tuple[EvidenceAwareReport, AgentState]:
        chat_model = llm_client.as_chat_model(model=request.llm_model, timeout_seconds=20)
        if request.task_type == ResearchTaskType.LATEST_EARNINGS_READOUT:
            payload, agent_state = run_latest_earnings_agent(
                request=request,
                state=state,
                llm=chat_model,
                tool_service=self._tool_service,
                rag_pipeline=self._rag_pipeline,
            )
            try:
                return (
                    build_latest_earnings_report_from_payload(request, agent_state, payload),
                    agent_state,
                )
            except Exception as exc:
                raise EarningsAgentError(str(exc), state=agent_state) from exc
        if request.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
            payload, agent_state = run_business_driver_agent(
                request=request,
                state=state,
                llm=chat_model,
                tool_service=self._tool_service,
                rag_pipeline=self._rag_pipeline,
            )
            try:
                return (
                    build_business_driver_report_from_payload(request, agent_state, payload),
                    agent_state,
                )
            except Exception as exc:
                raise BusinessDriverAgentError(str(exc), state=agent_state) from exc
        if request.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
            payload, agent_state = run_cash_flow_agent(
                request=request,
                state=state,
                llm=chat_model,
                tool_service=self._tool_service,
                rag_pipeline=self._rag_pipeline,
            )
            try:
                return (
                    build_cash_flow_report_from_payload(request, agent_state, payload),
                    agent_state,
                )
            except Exception as exc:
                raise CashFlowAgentError(str(exc), state=agent_state) from exc
        raise ValueError(f"Unsupported research task: {request.task_type.value}")


def _append_degraded_event(
    state: AgentState,
    summary: str,
    *,
    degraded_reason: str | None = None,
) -> AgentState:
    reason = degraded_reason or summary
    event = AgentEvent(
        run_id=state.run_id,
        task_type=state.task_type,
        phase=AgentPhase.DEGRADED,
        status=ToolStatus.DEGRADED,
        summary=summary,
        degraded_reason=reason,
    )
    return state.model_copy(
        update={
            "status": AgentRunStatus.DEGRADED,
            "degraded_reasons": [*state.degraded_reasons, reason],
            "tool_events": [*state.tool_events, event],
        }
    )


def _result(
    request: AgentRequest,
    state: AgentState,
    *,
    final_report: EvidenceAwareReport | None,
) -> BoundedAgentResult:
    status = (
        AgentRunStatus.DEGRADED
        if state.degraded_reasons or state.status == AgentRunStatus.DEGRADED
        else AgentRunStatus.OK
    )
    return BoundedAgentResult(
        run_id=request.run_id,
        task_type=request.task_type,
        status=status,
        events=state.tool_events,
        degraded_reasons=state.degraded_reasons,
        retrieval_records=state.retrieval_records,
        retryable=status == AgentRunStatus.DEGRADED,
        final_report=final_report.model_dump(mode="json") if final_report is not None else None,
    )
