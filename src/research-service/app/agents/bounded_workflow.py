import operator
from collections.abc import Callable
from typing import Annotated, Any, Protocol, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from app.contracts.agent import (
    AgentEvent,
    AgentPhase,
    AgentRequest,
    AgentRunStatus,
    BoundedAgentResult,
    RepairAction,
    ToolResult,
    ToolStatus,
)
from app.contracts.report import (
    CitationStatus,
    EvidenceAwareReport,
    EvidenceBoundClaim,
    SourceRef,
    TaskSpecificSections,
)
from app.contracts.research_task import ResearchTaskType

ToolCallback = Callable[[AgentRequest, dict[str, Any]], ToolResult]


class WorkflowState(TypedDict):
    request: AgentRequest
    events: Annotated[list[AgentEvent], operator.add]
    degraded_reasons: Annotated[list[str], operator.add]
    data: dict[str, Any]
    repair_count: int
    validation_action: RepairAction
    final_report: dict[str, Any] | None
    status: AgentRunStatus


class AgentToolset(Protocol):
    def collect_financial_facts(self, request: AgentRequest) -> ToolResult:
        raise NotImplementedError

    def collect_filing_metadata(self, request: AgentRequest) -> ToolResult:
        raise NotImplementedError

    def retrieve_evidence(
        self,
        request: AgentRequest,
        data: dict[str, Any],
        repair_count: int,
    ) -> ToolResult:
        raise NotImplementedError

    def extract_signals(self, request: AgentRequest, data: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def draft_report_sections(self, request: AgentRequest, data: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def validate_claims(self, request: AgentRequest, data: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    def finalize_report(self, request: AgentRequest, data: dict[str, Any]) -> ToolResult:
        raise NotImplementedError


class DefaultAgentToolset:
    def collect_financial_facts(self, request: AgentRequest) -> ToolResult:
        return ToolResult.ok(
            {
                "ticker": request.ticker,
                "currency": "USD",
                "period": "latest_quarter",
            }
        )

    def collect_filing_metadata(self, request: AgentRequest) -> ToolResult:
        return ToolResult.ok(
            {
                "ticker": request.ticker,
                "filing_type": "10-Q",
                "filing_date": None,
                "accession_number": None,
            }
        )

    def retrieve_evidence(
        self,
        request: AgentRequest,
        data: dict[str, Any],
        repair_count: int,
    ) -> ToolResult:
        evidence_plan = data.get("evidence_plan", {})
        topics = evidence_plan.get("topics", [])
        return ToolResult.ok(
            {
                "query": " ".join(cast(list[str], topics)),
                "repair_count": repair_count,
                "retrieved_nodes": [
                    {
                        "node_id": f"{request.run_id}:node:1",
                        "section": evidence_plan.get("primary_section", "MD&A"),
                        "snippet": "Evidence placeholder from the selected filing section.",
                        "filing_type": data.get("filing_metadata", {}).get("filing_type"),
                        "filing_date": data.get("filing_metadata", {}).get("filing_date"),
                        "accession_number": data.get("filing_metadata", {}).get("accession_number"),
                        "citation_status": "unverified",
                    }
                ],
            }
        )

    def extract_signals(self, request: AgentRequest, data: dict[str, Any]) -> ToolResult:
        return ToolResult.ok(
            {
                "signals": [
                    {
                        "task_type": request.task_type.value,
                        "summary": "Structured signal extraction placeholder.",
                    }
                ]
            }
        )

    def draft_report_sections(self, request: AgentRequest, data: dict[str, Any]) -> ToolResult:
        return ToolResult.ok(
            {
                "sections": {
                    "summary": "Draft report section placeholder.",
                    "evidence": "Evidence-backed section placeholder.",
                }
            }
        )

    def validate_claims(self, request: AgentRequest, data: dict[str, Any]) -> ToolResult:
        retrieval_records = cast(list[dict[str, Any]], data.get("retrieval_records", []))
        latest_retrieval = retrieval_records[-1] if retrieval_records else {}
        if latest_retrieval.get("status") != ToolStatus.OK.value:
            return ToolResult.partial(
                {
                    "repair_action": RepairAction.RETRIEVE_MORE.value,
                    "reason": "evidence_gap",
                },
                degraded_reason="Evidence coverage is incomplete.",
            )

        return ToolResult.ok({"repair_action": RepairAction.FINALIZE.value})

    def finalize_report(self, request: AgentRequest, data: dict[str, Any]) -> ToolResult:
        sections = cast(dict[str, Any], data.get("draft_report_sections", {}).get("sections", {}))
        source_refs = _source_refs_from_retrieval_records(data)
        citation_status = source_refs[0].citation_status if source_refs else CitationStatus.MISSING
        claims = [
            EvidenceBoundClaim(
                claim_id=f"{request.run_id}:claim:1",
                text=sections.get("summary", "Report generated without a draft summary."),
                citation_status=citation_status,
                source_refs=source_refs,
            )
        ]
        report = EvidenceAwareReport(
            run_id=request.run_id,
            ticker=request.ticker,
            task_type=request.task_type,
            task_sections=cast(
                TaskSpecificSections,
                _task_sections_from_request(
                    request,
                    sections.get("summary", "Draft report section placeholder."),
                    source_refs,
                    citation_status,
                ),
            ),
            sections=sections,
            claims=claims,
            retrieval_records=cast(list[dict[str, Any]], data.get("retrieval_records", [])),
        )
        return ToolResult.ok(report.model_dump(mode="json"))


class BoundedAgentWorkflow:
    def __init__(self, toolset: AgentToolset | None = None) -> None:
        self.toolset = toolset or DefaultAgentToolset()
        self.graph = self._build_graph().compile()

    def run(self, request: AgentRequest) -> BoundedAgentResult:
        initial_state = WorkflowState(
            request=request,
            events=[],
            degraded_reasons=[],
            data={},
            repair_count=0,
            validation_action=RepairAction.FINALIZE,
            final_report=None,
            status=AgentRunStatus.OK,
        )
        final_state = cast(WorkflowState, self.graph.invoke(initial_state))
        status = (
            AgentRunStatus.DEGRADED
            if final_state["degraded_reasons"]
            else final_state.get("status", AgentRunStatus.OK)
        )
        return BoundedAgentResult(
            run_id=request.run_id,
            task_type=request.task_type,
            status=status,
            events=final_state["events"],
            degraded_reasons=final_state["degraded_reasons"],
            final_report=final_state.get("final_report"),
        )

    def _build_graph(self) -> Any:
        graph = StateGraph(WorkflowState)
        graph.add_node("resolve_task", self._resolve_task)
        graph.add_node("collect_financial_facts", self._collect_financial_facts)
        graph.add_node("collect_filing_metadata", self._collect_filing_metadata)
        graph.add_node("build_evidence_plan", self._build_evidence_plan)
        graph.add_node("retrieve_evidence", self._retrieve_evidence)
        graph.add_node("extract_signals", self._extract_signals)
        graph.add_node("draft_report_sections", self._draft_report_sections)
        graph.add_node("validate_claims", self._validate_claims)
        graph.add_node("mark_degraded", self._mark_degraded)
        graph.add_node("finalize_report", self._finalize_report)

        graph.add_edge(START, "resolve_task")
        graph.add_edge("resolve_task", "collect_financial_facts")
        graph.add_edge("collect_financial_facts", "collect_filing_metadata")
        graph.add_edge("collect_filing_metadata", "build_evidence_plan")
        graph.add_edge("build_evidence_plan", "retrieve_evidence")
        graph.add_edge("retrieve_evidence", "extract_signals")
        graph.add_edge("extract_signals", "draft_report_sections")
        graph.add_edge("draft_report_sections", "validate_claims")
        graph.add_conditional_edges(
            "validate_claims",
            self._route_after_validation,
            {
                "retrieve_evidence": "retrieve_evidence",
                "mark_degraded": "mark_degraded",
                "finalize_report": "finalize_report",
            },
        )
        graph.add_edge("mark_degraded", "finalize_report")
        graph.add_edge("finalize_report", END)
        return graph

    def _resolve_task(self, state: WorkflowState) -> dict[str, Any]:
        request = state["request"]
        profile = _task_profile(request.task_type)
        data = dict(state["data"])
        data["task_profile"] = profile
        return {
            "data": data,
            "events": [
                self._event(
                    request,
                    AgentPhase.RESOLVE_TASK,
                    ToolStatus.OK,
                    f"Resolved task profile for {request.task_type.value}.",
                )
            ],
        }

    def _collect_financial_facts(self, state: WorkflowState) -> dict[str, Any]:
        return self._run_tool(
            state,
            AgentPhase.COLLECT_FINANCIAL_FACTS,
            "collect_financial_facts",
            "financial_facts",
            lambda request, data: self.toolset.collect_financial_facts(request),
        )

    def _collect_filing_metadata(self, state: WorkflowState) -> dict[str, Any]:
        return self._run_tool(
            state,
            AgentPhase.COLLECT_FILING_METADATA,
            "collect_filing_metadata",
            "filing_metadata",
            lambda request, data: self.toolset.collect_filing_metadata(request),
        )

    def _build_evidence_plan(self, state: WorkflowState) -> dict[str, Any]:
        request = state["request"]
        profile = cast(dict[str, Any], state["data"].get("task_profile", {}))
        data = dict(state["data"])
        data["evidence_plan"] = {
            "primary_section": profile.get("primary_section", "MD&A"),
            "topics": profile.get("topics", []),
            "allowed_repair_actions": [
                RepairAction.RETRIEVE_MORE.value,
                RepairAction.REWRITE_QUERY.value,
                RepairAction.VALIDATE_CLAIM.value,
                RepairAction.FALLBACK_TO_RAW_FILING.value,
                RepairAction.MARK_PARTIAL_SUPPORT.value,
                RepairAction.FINALIZE.value,
            ],
            "max_evidence_repair_loops": request.max_evidence_repair_loops,
        }
        return {
            "data": data,
            "events": [
                self._event(
                    request,
                    AgentPhase.BUILD_EVIDENCE_PLAN,
                    ToolStatus.OK,
                    "Built bounded evidence plan.",
                )
            ],
        }

    def _retrieve_evidence(self, state: WorkflowState) -> dict[str, Any]:
        request = state["request"]
        try:
            result = self.toolset.retrieve_evidence(request, state["data"], state["repair_count"])
        except Exception as exc:
            return self._tool_error_update(
                request,
                AgentPhase.RETRIEVE_EVIDENCE,
                "retrieve_evidence",
                exc,
            )

        data = dict(state["data"])
        retrieval_records = list(cast(list[dict[str, Any]], data.get("retrieval_records", [])))
        retrieval_records.append(
            {
                "status": result.status.value,
                "data": result.data,
                "latency_ms": result.latency_ms,
                "source_refs": result.source_refs,
                "metrics": result.metrics,
            }
        )
        data["retrieval_records"] = retrieval_records
        return {
            "data": data,
            "events": [
                self._event(
                    request,
                    AgentPhase.RETRIEVE_EVIDENCE,
                    result.status,
                    "Retrieved evidence records.",
                    tool_name="retrieve_evidence",
                    latency_ms=result.latency_ms,
                    degraded_reason=_first_reason(result),
                )
            ],
        }

    def _extract_signals(self, state: WorkflowState) -> dict[str, Any]:
        return self._run_tool(
            state,
            AgentPhase.EXTRACT_SIGNALS,
            "extract_signals",
            "extracted_signals",
            lambda request, data: self.toolset.extract_signals(request, data),
        )

    def _draft_report_sections(self, state: WorkflowState) -> dict[str, Any]:
        return self._run_tool(
            state,
            AgentPhase.DRAFT_REPORT_SECTIONS,
            "draft_report_sections",
            "draft_report_sections",
            lambda request, data: self.toolset.draft_report_sections(request, data),
        )

    def _validate_claims(self, state: WorkflowState) -> dict[str, Any]:
        request = state["request"]
        try:
            result = self.toolset.validate_claims(request, state["data"])
        except Exception as exc:
            return self._tool_error_update(
                request,
                AgentPhase.VALIDATE_CLAIMS,
                "validate_claims",
                exc,
            )

        action = RepairAction(result.data.get("repair_action", RepairAction.FINALIZE.value))
        data = dict(state["data"])
        data["validation_results"] = result.data
        update: dict[str, Any] = {
            "data": data,
            "events": [
                self._event(
                    request,
                    AgentPhase.VALIDATE_CLAIMS,
                    result.status,
                    "Validated draft claims against available evidence.",
                    tool_name="validate_claims",
                    latency_ms=result.latency_ms,
                    degraded_reason=_first_reason(result),
                )
            ],
        }

        if action == RepairAction.FINALIZE:
            update["validation_action"] = RepairAction.FINALIZE
            return update

        if action in {
            RepairAction.FALLBACK_TO_RAW_FILING,
            RepairAction.MARK_PARTIAL_SUPPORT,
        }:
            update["validation_action"] = action
            update["status"] = AgentRunStatus.DEGRADED
            update["degraded_reasons"] = result.degraded_reasons or [
                f"Validation requested {action.value}."
            ]
            return update

        if state["repair_count"] < request.max_evidence_repair_loops:
            update["repair_count"] = state["repair_count"] + 1
            update["validation_action"] = action
            return update

        update["validation_action"] = RepairAction.MARK_PARTIAL_SUPPORT
        update["status"] = AgentRunStatus.DEGRADED
        update["degraded_reasons"] = [
            "Evidence coverage remained incomplete after bounded repair loops."
        ]
        return update

    def _mark_degraded(self, state: WorkflowState) -> dict[str, Any]:
        request = state["request"]
        reason = (
            state["degraded_reasons"][-1]
            if state["degraded_reasons"]
            else "Evidence coverage remained incomplete after bounded repair loops."
        )
        update: dict[str, Any] = {
            "status": AgentRunStatus.DEGRADED,
            "events": [
                self._event(
                    request,
                    AgentPhase.DEGRADED,
                    ToolStatus.DEGRADED,
                    "Marked run as degraded.",
                    degraded_reason=reason,
                )
            ],
        }
        if not state["degraded_reasons"]:
            update["degraded_reasons"] = [reason]
        return update

    def _finalize_report(self, state: WorkflowState) -> dict[str, Any]:
        request = state["request"]
        try:
            result = self.toolset.finalize_report(request, state["data"])
        except Exception as exc:
            return self._tool_error_update(
                request,
                AgentPhase.FINALIZE_REPORT,
                "finalize_report",
                exc,
            )

        status = (
            AgentRunStatus.DEGRADED
            if state["status"] == AgentRunStatus.DEGRADED or state["degraded_reasons"]
            else AgentRunStatus.OK
        )
        return {
            "final_report": result.data,
            "status": status,
            "events": [
                self._event(
                    request,
                    AgentPhase.FINALIZE_REPORT,
                    result.status,
                    "Finalized bounded agent report.",
                    tool_name="finalize_report",
                    latency_ms=result.latency_ms,
                    degraded_reason=_first_reason(result),
                )
            ],
        }

    def _route_after_validation(self, state: WorkflowState) -> str:
        action = state["validation_action"]
        if action in {
            RepairAction.RETRIEVE_MORE,
            RepairAction.REWRITE_QUERY,
            RepairAction.VALIDATE_CLAIM,
        }:
            return "retrieve_evidence"
        if action in {
            RepairAction.FALLBACK_TO_RAW_FILING,
            RepairAction.MARK_PARTIAL_SUPPORT,
        }:
            return "mark_degraded"
        return "finalize_report"

    def _run_tool(
        self,
        state: WorkflowState,
        phase: AgentPhase,
        tool_name: str,
        data_key: str,
        callback: ToolCallback,
    ) -> dict[str, Any]:
        request = state["request"]
        try:
            result = callback(request, state["data"])
        except Exception as exc:
            return self._tool_error_update(request, phase, tool_name, exc)

        data = dict(state["data"])
        data[data_key] = result.data
        return {
            "data": data,
            "events": [
                self._event(
                    request,
                    phase,
                    result.status,
                    f"Completed {tool_name}.",
                    tool_name=tool_name,
                    latency_ms=result.latency_ms,
                    degraded_reason=_first_reason(result),
                )
            ],
            "degraded_reasons": result.degraded_reasons
            if result.status in {ToolStatus.DEGRADED, ToolStatus.ERROR}
            else [],
        }

    def _tool_error_update(
        self,
        request: AgentRequest,
        phase: AgentPhase,
        tool_name: str,
        exc: Exception,
    ) -> dict[str, Any]:
        reason = f"{tool_name} failed: {exc}"
        return {
            "status": AgentRunStatus.DEGRADED,
            "degraded_reasons": [reason],
            "events": [
                self._event(
                    request,
                    phase,
                    ToolStatus.ERROR,
                    f"{tool_name} failed and was converted to degraded output.",
                    tool_name=tool_name,
                    degraded_reason=reason,
                ),
                self._event(
                    request,
                    AgentPhase.DEGRADED,
                    ToolStatus.DEGRADED,
                    "Marked run as degraded.",
                    degraded_reason=reason,
                ),
            ],
        }

    def _event(
        self,
        request: AgentRequest,
        phase: AgentPhase,
        status: ToolStatus,
        summary: str,
        *,
        tool_name: str | None = None,
        latency_ms: int = 0,
        degraded_reason: str | None = None,
    ) -> AgentEvent:
        return AgentEvent(
            run_id=request.run_id,
            task_type=request.task_type,
            phase=phase,
            status=status,
            summary=summary,
            tool_name=tool_name,
            latency_ms=latency_ms,
            degraded_reason=degraded_reason,
        )


def _first_reason(result: ToolResult) -> str | None:
    return result.degraded_reasons[0] if result.degraded_reasons else None


def _source_refs_from_retrieval_records(data: dict[str, Any]) -> list[SourceRef]:
    source_refs: list[SourceRef] = []
    retrieval_records = cast(list[dict[str, Any]], data.get("retrieval_records", []))
    for retrieval_record in retrieval_records:
        record_data = cast(dict[str, Any], retrieval_record.get("data", {}))
        for node in cast(list[dict[str, Any]], record_data.get("retrieved_nodes", [])):
            node_id = str(node.get("node_id", "unknown"))
            section = str(node.get("section", "unknown"))
            snippet = str(node.get("snippet", ""))
            if not snippet:
                continue
            source_refs.append(
                SourceRef(
                    source_id=node_id,
                    section=section,
                    snippet=snippet,
                    filing_type=cast(str | None, node.get("filing_type")),
                    filing_date=cast(str | None, node.get("filing_date")),
                    accession_number=cast(str | None, node.get("accession_number")),
                    citation_status=_citation_status_from_value(node.get("citation_status")),
                )
            )
    return source_refs


def _citation_status_from_value(value: Any) -> CitationStatus:
    try:
        return CitationStatus(value)
    except (TypeError, ValueError):
        return CitationStatus.UNVERIFIED


def _task_sections_from_request(
    request: AgentRequest,
    summary: str,
    source_refs: list[SourceRef],
    citation_status: CitationStatus,
) -> dict[str, Any]:
    evidence_refs = [
        {
            "section": source_ref.section,
            "excerpt": source_ref.snippet,
            "filing_date": source_ref.filing_date,
            "accession_number": source_ref.accession_number,
            "source_id": source_ref.source_id,
        }
        for source_ref in source_refs
    ]
    point = {
        "title": "Evidence-backed placeholder",
        "summary": summary,
        "evidence_refs": evidence_refs,
        "citation_status": citation_status.value,
    }
    coverage = {
        "status": "complete" if evidence_refs else "degraded",
        "missing_sections": [] if evidence_refs else ["evidence_refs"],
        "evidence_count": len(evidence_refs),
    }
    base = {
        "schema_version": "task_sections.v1",
        "task_type": request.task_type.value,
        "coverage": coverage,
    }

    if request.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        return {
            **base,
            "driver_thesis": {
                "headline": "Business drivers require evidence review",
                "durability": "unclear",
                "summary": summary,
            },
            "driver_map": {
                "product": [point],
                "segment": [],
                "geography": [],
                "demand": [],
                "pricing": [],
                "customer": [],
                "strategy": [],
            },
            "positive_signals": [point],
            "negative_signals": [],
            "watchlist": ["Review company-specific driver evidence."],
        }

    if request.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        metric = {
            "name": "Cash quality",
            "value": "See evidence",
            "interpretation": summary,
            "evidence_refs": evidence_refs,
            "citation_status": citation_status.value,
        }
        return {
            **base,
            "cash_quality_verdict": {
                "headline": "Cash quality requires evidence review",
                "earnings_backed_by_cash": "unclear",
                "summary": summary,
            },
            "cash_metrics": [metric],
            "capital_allocation": {
                "capex": [],
                "buybacks": [],
                "dividends": [],
                "debt": [],
                "liquidity": [point],
            },
            "allocation_discipline": [point],
            "red_flags": [],
        }

    metric = {
        "name": "Latest earnings context",
        "value": "See evidence",
        "interpretation": summary,
        "evidence_refs": evidence_refs,
        "citation_status": citation_status.value,
    }
    return {
        **base,
        "topline_verdict": {
            "headline": "Latest earnings readout requires evidence review",
            "summary": summary,
            "verdict": "mixed",
        },
        "key_takeaways": [point],
        "financial_dashboard": {
            "metrics": [metric],
            "chart_focus": ["revenue", "margin", "cash flow"],
        },
        "driver_snapshot": [point],
        "risk_snapshot": [],
    }


def _task_profile(task_type: ResearchTaskType) -> dict[str, Any]:
    profiles: dict[ResearchTaskType, dict[str, Any]] = {
        ResearchTaskType.LATEST_EARNINGS_READOUT: {
            "primary_section": "MD&A",
            "topics": ["MD&A", "financial statements", "earnings narrative", "guidance"],
        },
        ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE: {
            "primary_section": "Business Drivers",
            "topics": ["products", "segments", "demand", "pricing", "customers", "strategy"],
        },
        ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION: {
            "primary_section": "Cash Flow and Capital Allocation",
            "topics": ["cash flow", "capex", "buybacks", "debt", "liquidity"],
        },
    }
    return profiles[task_type]
