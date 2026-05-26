from __future__ import annotations

import json
import logging

from app.agents.business_driver_agent import BusinessDriverAgentError
from app.agents.llm_gateway import OpenAiCompatibleLlmClient
from app.agents.research_workflow import ResearchAgentWorkflow, _fallback_report_from_state
from app.contracts.agent import (
    AgentEvent,
    AgentPhase,
    AgentRequest,
    AgentRunStatus,
    AgentState,
    EvidenceMemory,
    LlmProvider,
    TaskPolicy,
    ToolStatus,
)
from app.contracts.research_task import ResearchTaskType


class _FakeReport:
    def model_dump(self, mode: str = "json") -> dict[str, str]:
        return {"summary": "ok"}


def _fake_transport(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": "{}",
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


def _make_client() -> OpenAiCompatibleLlmClient:
    return OpenAiCompatibleLlmClient(
        LlmProvider.SILICONFLOW,
        "sk-test",
        base_url="https://example.com/v1",
        transport=_fake_transport,
    )


def _make_state() -> AgentState:
    return AgentState(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="en",
        provider=LlmProvider.SILICONFLOW,
        model="Pro/moonshotai/Kimi-K2.6",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["toplineVerdict"],
        ),
        tool_events=[
            AgentEvent(
                run_id="run_1",
                task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
                phase=AgentPhase.BUILD_EVIDENCE_PLAN,
                status=ToolStatus.OK,
                summary="Planned evidence collection.",
                event_kind="reasoning",
                agent_name="Earnings agent",
                model_name="Pro/moonshotai/Kimi-K2.6",
                latency_ms=41,
            ),
            AgentEvent(
                run_id="run_1",
                task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
                phase=AgentPhase.COLLECT_FINANCIAL_FACTS,
                status=ToolStatus.OK,
                summary="Collected company facts.",
                event_kind="tool",
                agent_name="Earnings agent",
                model_name="Pro/moonshotai/Kimi-K2.6",
                tool_name="get_company_facts",
                latency_ms=118,
            ),
            AgentEvent(
                run_id="run_1",
                task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
                phase=AgentPhase.DRAFT_REPORT_SECTIONS,
                status=ToolStatus.OK,
                summary="Synthesized final report sections.",
                event_kind="reasoning",
                agent_name="Earnings agent",
                model_name="Pro/moonshotai/Kimi-K2.6",
                latency_ms=612,
                usage={"prompt_tokens": 10, "completion_tokens": 22},
            ),
        ],
    )


def test_research_workflow_logs_stage_summary(caplog, monkeypatch) -> None:
    workflow = ResearchAgentWorkflow(llm_client=_make_client())
    request = AgentRequest(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="en",
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model="Pro/moonshotai/Kimi-K2.6",
        llm_api_key="sk-test",
    )
    state = _make_state()

    def fake_run_task_agent(request_arg, state_arg, llm_client_arg):
        return _FakeReport(), state

    monkeypatch.setattr(workflow, "_run_task_agent", fake_run_task_agent)
    caplog.set_level(logging.INFO, logger="uvicorn.error")

    result = workflow.run(request)

    assert result.status == AgentRunStatus.OK
    assert any(
        "research_agent_stage_summary" in record.message
        and "planning_ms=41" in record.message
        and "tool_ms=118" in record.message
        and "synthesis_ms=612" in record.message
        for record in caplog.records
    )


def test_cash_flow_timeout_fallback_preserves_typed_sections_from_evidence() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="TSLA",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
    )
    state = AgentState(
        run_id="run_1",
        ticker="TSLA",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["cashQualityVerdict"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "sec_companyfacts",
                    "metric": "operating cash flow",
                    "value": 4664000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "concept": "NetCashProvidedByUsedInOperatingActivities",
                    "source_id": "src_1",
                }
            ],
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "SEC companyfacts",
                    "snippet": "Operating cash flow was $4.7B in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_2",
                    "section": "Liquidity and Capital Resources",
                    "snippet": (
                        "Capital allocation included disciplined buybacks and "
                        "liquidity management."
                    ),
                    "citation_status": "supported",
                }
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Cash flow agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    assert report.task_sections.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION
    assert report.task_sections.coverage.status == "partial"
    assert report.task_sections.cash_metrics[0].value == "$4.7B"
    assert report.task_sections.cash_metrics[0].interpretation.startswith(
        "SEC companyfacts concept"
    )
    assert report.task_sections.cash_metrics[0].evidence_refs
    assert report.task_sections.capital_allocation.liquidity
    assert report.sections["synthesis"] == "deterministic_fallback"
    assert "final LLM synthesis failed" not in report.sections["summary"]
    assert len(report.claims) >= 2


def test_latest_earnings_timeout_fallback_backfills_rich_memo_sections() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="TSLA",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="en",
    )
    state = AgentState(
        run_id="run_1",
        ticker="TSLA",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="en",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["toplineVerdict"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "sec_companyfacts",
                    "metric": "revenue",
                    "value": 21301000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "source_id": "src_1",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "operating income",
                    "value": 399000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "concept": "OperatingIncomeLoss",
                    "source_id": "src_2",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "operating cash flow",
                    "value": 2242000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "concept": "NetCashProvidedByUsedInOperatingActivities",
                    "source_id": "src_3",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "SEC companyfacts",
                    "snippet": "Revenue was $21.3B in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_2",
                    "section": "SEC companyfacts",
                    "snippet": "Operating income was $399M in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_3",
                    "section": "SEC companyfacts",
                    "snippet": "Operating cash flow was $2.2B in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_4",
                    "section": "Risk Factors",
                    "snippet": (
                        "Automotive margin pressure and demand uncertainty remain key risks."
                    ),
                    "citation_status": "partial",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Earnings agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    sections = report.task_sections
    assert sections.task_type == ResearchTaskType.LATEST_EARNINGS_READOUT
    assert sections.coverage.status == "partial"
    assert sections.quality_of_quarter is not None
    assert sections.quality_of_quarter.growth_quality is not None
    assert sections.quality_of_quarter.margin_quality is not None
    assert sections.quality_of_quarter.cash_quality is not None
    assert sections.drivers_and_draggers is not None
    assert sections.drivers_and_draggers.drivers
    assert sections.drivers_and_draggers.draggers
    assert sections.drivers_and_draggers.drivers[0].title == "Revenue evidence anchor"
    assert sections.drivers_and_draggers.draggers[0].title == "Risk Factors risk watch"
    assert "Evidence-backed metric signal" not in report.model_dump_json()
    assert "Synthesis risk" not in report.model_dump_json()
    assert sections.bull_bear_read is not None
    assert sections.bull_bear_read.bull_case
    assert sections.bull_bear_read.bear_case
    assert sections.bull_bear_read.balanced_read is not None
    assert len(sections.watch_next) == 3
    assert report.sections["synthesis"] == "deterministic_fallback"


def test_fallback_summary_hides_internal_missing_metric_markers() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="zh",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["driverThesis"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "sec_companyfacts",
                    "metric": "revenue",
                    "value": 111184000000,
                    "unit": "USD",
                    "fact_period": "2026-Q2",
                    "source_id": "src_1",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "segment revenue",
                    "value": None,
                    "unit": "USD",
                    "fact_period": "2026-Q2",
                    "source_id": "src_2",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "SEC companyfacts",
                    "snippet": "Revenue was $111.2B in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_2",
                    "section": "Business overview",
                    "snippet": "Segment detail was not stable enough for direct extraction.",
                    "citation_status": "partial",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Business driver agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    assert "Not extracted" not in report.sections["summary"]
    assert "未在当前证据包中稳定抽取" in report.sections["summary"]
    assert "revenue: $111.2B" in report.sections["summary"]


def test_business_driver_timeout_fallback_uses_paragraph_sections() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="en",
    )
    state = AgentState(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="en",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["driverThesis"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "sec_companyfacts",
                    "metric": "revenue",
                    "value": 111184000000,
                    "unit": "USD",
                    "fact_period": "2026-Q2",
                    "source_id": "src_1",
                }
            ],
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "SEC companyfacts",
                    "snippet": "Revenue was $111.2B in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_2",
                    "section": "Business overview",
                    "snippet": "Services and installed base strength supported demand.",
                    "citation_status": "supported",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Business driver agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    sections = report.task_sections
    assert sections.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE
    assert sections.driver_map.revenue_bridge is not None
    assert sections.driver_map.revenue_bridge.title == "Revenue bridge evidence"
    assert sections.driver_map.segment_momentum is not None
    assert sections.driver_map.segment_momentum.title == "Segment momentum evidence"
    assert sections.driver_map.margin_and_mix is not None
    assert sections.driver_map.margin_and_mix.title == "Margin and mix evidence"
    assert sections.driver_map.demand_signals is not None
    assert sections.driver_map.demand_signals.title == "Demand signal evidence"
    assert "Revenue was $111.2B" in sections.driver_map.revenue_bridge.summary
    assert "Services and installed base" in sections.driver_map.demand_signals.summary
    assert "Review the final LLM synthesis" not in report.model_dump_json()
    assert "watchlist" not in report.model_dump_json()
    assert "positive_signals" not in report.model_dump_json()


def test_business_driver_timeout_fallback_builds_distinct_evidence_paragraphs() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="zh",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["driverThesis"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "sec_companyfacts",
                    "metric": "revenue",
                    "value": 7438000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "source_id": "src_revenue",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "gross margin",
                    "value": 0.52,
                    "unit": "pure",
                    "fact_period": "2026-Q1",
                    "concept": "GrossProfitMargin",
                    "source_id": "src_margin",
                },
            ],
            business_signals=[
                {
                    "signal_type": "segment",
                    "summary": "Data Center segment revenue increased as EPYC demand improved.",
                    "source_id": "src_segment",
                    "citation_status": "supported",
                },
                {
                    "signal_type": "demand",
                    "summary": "Customer demand for AI accelerators remained strong.",
                    "source_id": "src_demand",
                    "citation_status": "supported",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_revenue",
                    "section": "SEC companyfacts",
                    "snippet": "Revenue was $7.4B in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_segment",
                    "section": "Segment Information",
                    "snippet": "Data Center segment revenue increased as EPYC demand improved.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_margin",
                    "section": "Results of Operations",
                    "snippet": "Gross margin expanded because product mix improved.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_demand",
                    "section": "MD&A",
                    "snippet": "Customer demand for AI accelerators remained strong.",
                    "citation_status": "supported",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Business driver agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    sections = report.task_sections
    assert sections.driver_thesis.summary.startswith("AMD 的业务驱动结论")
    assert sections.driver_map.revenue_bridge is not None
    assert "revenue: $7.4B" in sections.driver_map.revenue_bridge.summary
    assert "Revenue was $7.4B" in sections.driver_map.revenue_bridge.summary
    assert sections.driver_map.segment_momentum is not None
    assert "Data Center segment" in sections.driver_map.segment_momentum.summary
    assert sections.driver_map.margin_and_mix is not None
    assert "Gross margin expanded" in sections.driver_map.margin_and_mix.summary
    assert sections.driver_map.demand_signals is not None
    assert "AI accelerators" in sections.driver_map.demand_signals.summary
    serialized = report.model_dump_json()
    assert "not fully synthesized" not in serialized
    assert "final LLM" not in serialized


def test_business_driver_timeout_with_evidence_returns_grounded_fallback(monkeypatch) -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="zh",
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model="Pro/moonshotai/Kimi-K2.6",
        llm_api_key="sk-test",
    )
    state = AgentState(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="zh",
        provider=LlmProvider.SILICONFLOW,
        model="Pro/moonshotai/Kimi-K2.6",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["driverThesis"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "sec_companyfacts",
                    "metric": "revenue",
                    "value": 7438000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_revenue",
                }
            ],
            source_refs=[
                {
                    "source_id": "src_revenue",
                    "section": "SEC companyfacts",
                    "snippet": "Revenue was $7.4B in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_demand",
                    "section": "MD&A",
                    "snippet": "Customer demand for AI accelerators remained strong.",
                    "citation_status": "supported",
                },
            ],
        ),
    )
    workflow = ResearchAgentWorkflow(llm_client=_make_client())

    def fake_run_task_agent(*args, **kwargs):
        raise BusinessDriverAgentError(
            "Business driver agent final synthesis failed: The read operation timed out",
            state=state,
        )

    monkeypatch.setattr(workflow, "_run_task_agent", fake_run_task_agent)

    result = workflow.run(request)

    assert result.status == AgentRunStatus.OK
    assert result.degraded_reasons == []
    assert result.final_report is not None
    serialized = json.dumps(result.final_report, ensure_ascii=False)
    assert "业务驱动结论" in serialized
    assert "final synthesis failed" not in serialized


def test_fallback_report_hides_internal_missing_metric_markers_everywhere() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="BAC",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="BAC",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="zh",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["toplineVerdict"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "sec_companyfacts",
                    "metric": "revenue",
                    "value": 28150000000,
                    "unit": "USD",
                    "fact_period": "2026-Q2",
                    "source_id": "src_1",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "gross margin",
                    "value": None,
                    "unit": "USD",
                    "fact_period": "2026-Q2",
                    "source_id": "src_2",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "SEC companyfacts",
                    "snippet": "Revenue was $28.2B in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_2",
                    "section": "SEC companyfacts",
                    "snippet": "Gross margin was not stable enough for direct extraction.",
                    "citation_status": "partial",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Earnings agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    serialized = report.model_dump_json()
    assert "Not extracted" not in serialized
