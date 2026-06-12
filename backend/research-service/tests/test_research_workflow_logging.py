from __future__ import annotations

import json
import logging

from app.agents.business_driver_agent import BusinessDriverAgentError
from app.agents.cash_flow_agent import CashFlowAgentError
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
    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return {"summary": "ok", "retrieval_records": []}


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


def test_market_sentiment_result_preserves_source_fetch_records(monkeypatch) -> None:
    workflow = ResearchAgentWorkflow(llm_client=_make_client())
    request = AgentRequest(
        run_id="run_1",
        ticker="NVDA",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="zh",
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model="Pro/moonshotai/Kimi-K2.6",
        llm_api_key="sk-test",
    )
    state = AgentState(
        run_id="run_1",
        ticker="BBY",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="zh",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            allowed_tools=[
                "get_market_context",
            ],
            required_outputs=[
                "sentimentHeader",
                "narrativeSnapshot",
                "bullBearNarrative",
                "sourceDivergence",
            ],
        ),
        retrieval_records=[
            {
                "tool_name": "fetch_stocktwits",
                "status": "ok",
                "source": "stocktwits",
                "item_count": 4,
                "source_ref_count": 1,
            }
        ],
    )

    def fake_run_task_agent(request_arg, state_arg, llm_client_arg):
        report = _FakeReport()
        return report, state

    monkeypatch.setattr(workflow, "_run_task_agent", fake_run_task_agent)

    result = workflow.run(request)

    serialized = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
    assert result.final_report is not None
    assert result.final_report["retrieval_records"] == result.retrieval_records
    assert result.retrieval_records[0]["tool_name"] == "fetch_stocktwits"
    assert result.retrieval_records[0]["source"] == "stocktwits"
    assert "fetch_stocktwits" in serialized


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
                        "Capital allocation included disciplined buybacks and liquidity management."
                    ),
                    "citation_status": "supported",
                },
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


def test_cash_flow_timeout_fallback_uses_structured_cash_report_shape() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="INTC",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
    )
    state = AgentState(
        run_id="run_1",
        ticker="INTC",
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
                    "source": "yfinance",
                    "metric": "net income",
                    "value": -3728000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_net_income",
                },
                {
                    "source": "yfinance",
                    "metric": "operating cash flow",
                    "value": 1100000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_ocf",
                },
                {
                    "source": "yfinance",
                    "metric": "capital expenditures",
                    "value": 3640000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_capex",
                },
                {
                    "source": "yfinance",
                    "metric": "free cash flow",
                    "value": -2540000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_fcf",
                },
                {
                    "source": "yfinance",
                    "metric": "current ratio",
                    "value": 2.31,
                    "unit": "x",
                    "fact_period": "2026-Q1",
                    "source_id": "src_current_ratio",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_net_income",
                    "section": "yfinance income statement",
                    "snippet": "Net income was -$3.7B.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_ocf",
                    "section": "yfinance cash flow statement",
                    "snippet": "Operating cash flow was $1.1B.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_capex",
                    "section": "yfinance cash flow statement",
                    "snippet": "Capital expenditures were $3.6B.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_fcf",
                    "section": "yfinance cash flow statement",
                    "snippet": "Free cash flow was -$2.5B.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_current_ratio",
                    "section": "yfinance balance sheet",
                    "snippet": "Current ratio was 2.31x.",
                    "citation_status": "supported",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Cash flow agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    serialized = report.model_dump_json()
    assert "Evidence-backed fallback cash view" not in serialized
    assert "Cash flow evidence anchor" not in serialized
    assert report.task_sections.capital_allocation.buybacks == []
    assert report.task_sections.capital_allocation.dividends == []
    assert (
        report.task_sections.cash_quality_verdict.headline == "Cash quality is pressured by capex."
    )
    assert len(report.task_sections.cash_metrics) >= 4
    assert report.task_sections.capital_allocation.capex
    assert report.task_sections.capital_allocation.liquidity
    assert report.task_sections.red_flags


def test_cash_flow_timeout_fallback_respects_chinese_locale() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["cashQualityVerdict"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "sec_companyfacts",
                    "metric": "net income",
                    "value": 709000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "concept": "NetIncomeLoss",
                    "source_id": "src_net_income",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "operating cash flow",
                    "value": 920000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "concept": "NetCashProvidedByUsedInOperatingActivities",
                    "source_id": "src_ocf",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "capital expenditures",
                    "value": 120000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "concept": "PaymentsToAcquirePropertyPlantAndEquipment",
                    "source_id": "src_capex",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "free cash flow",
                    "value": 800000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_fcf",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "current ratio",
                    "value": 2.31,
                    "unit": "ratio",
                    "fact_period": "2026-Q1",
                    "source_id": "src_current_ratio",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_net_income",
                    "section": "SEC companyfacts",
                    "snippet": "Net income was $709M.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_ocf",
                    "section": "SEC companyfacts",
                    "snippet": "Operating cash flow was $920M.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_capex",
                    "section": "SEC companyfacts",
                    "snippet": "Capital expenditures were $120M.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_fcf",
                    "section": "SEC companyfacts",
                    "snippet": "Free cash flow was $800M.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_current_ratio",
                    "section": "SEC companyfacts",
                    "snippet": "Current ratio was 2.31x.",
                    "citation_status": "supported",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Cash flow agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    serialized = report.model_dump_json()
    assert "Earnings are supported by cash generation." not in serialized
    assert "Cash quality is pressured by capex." not in serialized
    assert "Cash quality needs more evidence." not in serialized
    assert "Capex and reinvestment" not in serialized
    assert "Balance sheet resilience" not in serialized
    assert "Watch next" not in serialized
    verdict = report.task_sections.cash_quality_verdict
    assert verdict.headline != "盈利有现金生成支撑。"
    assert (
        verdict.summary
        != "AMD 经营现金流和自由现金流均为正，管理层具备真实资本配置能力。"
    )
    assert "经营现金流" in verdict.summary
    assert "自由现金流" in verdict.summary
    assert "资本开支" in verdict.summary
    assert "投资" in verdict.summary
    assert len(verdict.summary) >= 70
    assert "资本开支与再投资" in serialized
    assert "资产负债表韧性" in serialized
    assert "观察下一季" in serialized


def test_cash_flow_timeout_with_metric_evidence_returns_grounded_fallback(monkeypatch) -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="NOK",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model="Pro/moonshotai/Kimi-K2.6",
        llm_api_key="sk-test",
    )
    state = AgentState(
        run_id="run_1",
        ticker="NOK",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
        provider=LlmProvider.SILICONFLOW,
        model="Pro/moonshotai/Kimi-K2.6",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            allowed_tools=[
                "get_company_facts",
                "search_metric_evidence",
            ],
            required_outputs=["cashQualityVerdict"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "yfinance_metric",
                    "metric": "operating cash flow",
                    "value": 783000000,
                    "unit": "USD",
                    "fact_period": "Q1 2026",
                    "source_id": "src_ocf",
                },
                {
                    "source": "yfinance_metric",
                    "metric": "free cash flow",
                    "value": 629000000,
                    "unit": "USD",
                    "fact_period": "Q1 2026",
                    "source_id": "src_fcf",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_ocf",
                    "section": "yfinance structured snapshot",
                    "snippet": "Q1 2026 operating cash flow was $783.0M.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_fcf",
                    "section": "yfinance structured snapshot",
                    "snippet": "Q1 2026 free cash flow was $629.0M.",
                    "citation_status": "supported",
                },
            ],
        ),
    )
    workflow = ResearchAgentWorkflow(llm_client=_make_client())

    def fake_run_task_agent(*args, **kwargs):
        raise CashFlowAgentError(
            "Cash flow agent final synthesis failed: The read operation timed out",
            state=state,
        )

    monkeypatch.setattr(workflow, "_run_task_agent", fake_run_task_agent)

    result = workflow.run(request)

    assert result.status == AgentRunStatus.OK
    assert result.degraded_reasons == []
    assert result.final_report is not None
    serialized = json.dumps(result.final_report, ensure_ascii=False)
    assert "经营现金流" in serialized
    assert "final synthesis failed" not in serialized


def test_cash_flow_zh_fallback_localizes_metric_outlook_copy() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="JPM",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="JPM",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["cashQualityVerdict"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "yfinance",
                    "metric": "net income",
                    "value": 14640000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_income",
                },
                {
                    "source": "yfinance",
                    "metric": "operating cash flow",
                    "value": -251800000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_ocf",
                },
                {
                    "source": "yfinance",
                    "metric": "free cash flow",
                    "value": -211800000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_fcf",
                },
                {
                    "source": "yfinance",
                    "metric": "total debt",
                    "value": 516812000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_debt",
                },
                {
                    "source": "yfinance",
                    "metric": "cash and short term investments",
                    "value": 312100000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "source_id": "src_cash",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_income",
                    "section": "structured snapshot",
                    "snippet": "Net income was $14.6B.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_ocf",
                    "section": "structured cash flow",
                    "snippet": "Operating cash flow was -$251.8B.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_fcf",
                    "section": "structured cash flow",
                    "snippet": "Free cash flow was -$211.8B.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_debt",
                    "section": "structured balance sheet",
                    "snippet": (
                        "Structured yfinance facts reports total debt of "
                        "516812000000.0 USD for latest_quarter filed 2026-05-01."
                    ),
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_cash",
                    "section": "structured balance sheet",
                    "snippet": "Cash and short-term investments were $312.1B.",
                    "citation_status": "supported",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Cash flow agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    serialized = report.model_dump_json()
    for leaked in [
        "should be read as",
        "operating cash flow",
        "free cash flow",
        "capital expenditures",
        "current ratio",
        "total debt",
        "cash and short-term investments",
        "Structured yfinance facts reports",
        "latest_quarter",
        "filed",
    ]:
        assert leaked not in serialized
    assert "经营现金流" in serialized
    assert "自由现金流" in serialized
    assert "总债务" in serialized
    assert "现金及短期投资" in serialized


def test_cash_flow_zh_fallback_localizes_missing_metric_boundaries() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="PAYX",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="PAYX",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            allowed_tools=["get_company_facts", "search_metric_evidence"],
            required_outputs=["cashQualityVerdict"],
        ),
        evidence_memory=EvidenceMemory(
            metric_evidence=[
                {
                    "source": "yfinance",
                    "metric": "net income",
                    "value": 519300000,
                    "unit": "USD",
                    "fact_period": "2026-Q3",
                    "source_id": "src_income",
                },
                {
                    "source": "yfinance",
                    "metric": "operating cash flow",
                    "value": 1557100000,
                    "unit": "USD",
                    "fact_period": "2026-Q3",
                    "source_id": "src_ocf",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "capital expenditures",
                    "value": 131300000,
                    "unit": "USD",
                    "fact_period": "2026-Q3",
                    "source_id": "src_capex",
                },
                {
                    "source": "yfinance",
                    "metric": "free cash flow",
                    "value": None,
                    "unit": "USD",
                    "fact_period": "2026-Q3",
                    "source_id": "src_fcf",
                },
                {
                    "source": "yfinance",
                    "metric": "current ratio",
                    "value": None,
                    "unit": "ratio",
                    "fact_period": "2026-Q3",
                    "source_id": "src_current",
                },
                {
                    "source": "yfinance",
                    "metric": "total debt",
                    "value": None,
                    "unit": "USD",
                    "fact_period": "2026-Q3",
                    "source_id": "src_debt",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_income",
                    "section": "structured snapshot",
                    "snippet": "Net income was $519.3M.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_ocf",
                    "section": "structured cash flow",
                    "snippet": (
                        "Structured yfinance facts reports operating cash flow of "
                        "1557100000 USD for 2026Q3 filed 2026-03-26."
                    ),
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_capex",
                    "section": "SEC companyfacts",
                    "snippet": (
                        "SEC companyfacts concept "
                        "PaymentsToAcquirePropertyPlantAndEquipment."
                    ),
                    "citation_status": "supported",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Cash flow agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    serialized = report.model_dump_json()
    for leaked in [
        "free cash flow",
        "current ratio",
        "total debt",
        "Structured yfinance facts reports",
        "SEC companyfacts concept",
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "filed",
    ]:
        assert leaked not in serialized
    assert "自由现金流" in serialized
    assert "流动比率" in serialized
    assert "总债务" in serialized
    assert "SEC 公司事实指标" in serialized


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


def test_latest_earnings_timeout_fallback_respects_chinese_locale() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="NVDA",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="NVDA",
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
                    "value": 35100000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "source_id": "src_1",
                },
                {
                    "source": "sec_companyfacts",
                    "metric": "operating income",
                    "value": 21869000000,
                    "unit": "USD",
                    "fact_period": "2026-Q1",
                    "concept": "OperatingIncomeLoss",
                    "source_id": "src_2",
                },
            ],
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "SEC companyfacts",
                    "snippet": "Revenue was $35.1B in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_2",
                    "section": "Risk Factors",
                    "snippet": "Customer concentration and supply constraints remain key risks.",
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
    assert "Evidence-backed fallback earnings view" not in serialized
    assert "Evidence-backed fallback" not in serialized
    assert "evidence anchor" not in serialized
    assert "risk watch" not in serialized
    assert "Risk Factors risk watch" not in serialized
    assert "证据兜底财报判断" not in serialized
    assert "最终综合" not in serialized
    assert "收入、利润率与现金流需要同步验证" in serialized
    assert "增长质量" in serialized
    assert "风险观察" in serialized
    sections = report.task_sections
    assert "收入为 $35.1B" in sections.topline_verdict.summary
    assert "经营利润为 $21.9B" in sections.topline_verdict.summary
    assert len(sections.key_takeaways) >= 2
    assert all(len(item.summary) >= 35 for item in sections.key_takeaways[:2])


def test_fallback_summary_hides_internal_missing_metric_markers() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="AAPL",
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
        reason="Earnings agent final synthesis failed: The read operation timed out",
    )

    assert report is not None
    assert "Not extracted" not in report.sections["summary"]
    assert "未在当前证据包中稳定抽取" in report.sections["summary"]
    assert "收入：$111.2B" in report.sections["summary"]



def test_market_sentiment_timeout_fallback_uses_sentiment_sections_only() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="NVDA",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="NVDA",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="zh",
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            allowed_tools=["get_market_context"],
            required_outputs=[
                "sentimentHeader",
                "narrativeSnapshot",
                "bullBearNarrative",
                "sourceDivergence",
            ],
        ),
        evidence_memory=EvidenceMemory(
            source_refs=[
                {
                    "source_id": "sentiment:yahoo_news",
                    "section": "yahoo_news",
                    "snippet": "Yahoo Finance: AI demand remains the main market narrative.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "sentiment:stocktwits",
                    "section": "stocktwits",
                    "snippet": "Bullish: 8 (80%) · Bearish: 2 (20%).",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_revenue",
                    "section": "SEC companyfacts",
                    "snippet": "Revenue was $26.0B in the quarter.",
                    "citation_status": "supported",
                },
                {
                    "source_id": "src_table",
                    "section": "Table of Contents",
                    "snippet": "| | | 6,402 | | | 15,509 | ---|---",
                    "citation_status": "supported",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Sentiment analyst final synthesis failed: The read operation timed out",
    )

    assert report is not None
    sections = report.task_sections
    assert sections.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE
    assert sections.sentiment_header is not None
    assert sections.sentiment_header.overall_band == "Mixed"
    assert sections.sentiment_header.confidence == "low"
    assert sections.narrative_snapshot is not None
    assert sections.bull_bear_narrative is not None
    assert sections.source_divergence is not None
    assert sections.source_divergence.news_direction == "mixed"
    assert sections.source_divergence.stocktwits_direction == "mixed"
    assert sections.source_divergence.reddit_direction == "unavailable"
    assert sections.driver_thesis is None
    assert sections.driver_map is None
    serialized = report.model_dump_json()
    assert "市场叙事与情绪分析未完成最终 LLM 合成" in serialized
    assert "sentiment:yahoo_news" in serialized
    assert "sentiment:stocktwits" in serialized
    assert "Revenue was $26.0B" not in serialized
    assert "Table of Contents" not in serialized
    assert "---|---" not in serialized


def test_market_sentiment_timeout_with_evidence_returns_typed_fallback(monkeypatch) -> None:
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
            allowed_tools=["get_market_context"],
            required_outputs=["sentimentHeader"],
        ),
        evidence_memory=EvidenceMemory(
            source_refs=[
                {
                    "source_id": "sentiment:reddit",
                    "section": "reddit",
                    "snippet": "r/stocks: AMD discussion is thin this week.",
                    "citation_status": "partial",
                }
            ],
        ),
    )
    workflow = ResearchAgentWorkflow(llm_client=_make_client())

    def fake_run_task_agent(*args, **kwargs):
        raise BusinessDriverAgentError(
            "Sentiment analyst final synthesis failed: The read operation timed out",
            state=state,
        )

    monkeypatch.setattr(workflow, "_run_task_agent", fake_run_task_agent)

    result = workflow.run(request)

    assert result.status == AgentRunStatus.OK
    assert result.degraded_reasons == []
    assert result.final_report is not None
    serialized = json.dumps(result.final_report, ensure_ascii=False)
    assert "市场叙事与情绪分析未完成最终 LLM 合成" in serialized
    task_sections = result.final_report["task_sections"]
    assert task_sections["sentiment_header"] is not None
    assert task_sections["driver_map"] is None
    assert task_sections["driver_thesis"] is None
    assert "业务驱动结论" not in serialized
    assert "final synthesis failed" not in serialized


def test_market_sentiment_fallback_summary_does_not_describe_social_sources_as_sec() -> None:
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
            allowed_tools=["get_market_context"],
            required_outputs=["sentimentHeader"],
        ),
        evidence_memory=EvidenceMemory(
            source_refs=[
                {
                    "source_id": "sentiment:yahoo_news",
                    "section": "yahoo_news",
                    "snippet": (
                        "[2026-06-12 · Yahoo Finance] Apple news highlights "
                        "AI integration and iPhone growth."
                    ),
                    "citation_status": "supported",
                },
                {
                    "source_id": "sentiment:stocktwits",
                    "section": "stocktwits",
                    "snippet": "Bullish: 12; Bearish: 2; Unlabeled: 16.",
                    "citation_status": "supported",
                },
            ],
        ),
    )

    report = _fallback_report_from_state(
        request,
        state,
        reason="Sentiment analyst final synthesis failed: The read operation timed out",
    )

    assert report is not None
    serialized = report.model_dump_json()
    assert "市场叙事与情绪分析未完成最终 LLM 合成" in serialized
    assert "Yahoo Finance" in serialized
    assert "StockTwits" in serialized
    assert "SEC 指标" not in serialized
    assert "披露片段" not in serialized
    assert "财报" not in serialized


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
