from __future__ import annotations

from typing import Any

from app.agents.llm_gateway import LlmClient, LlmRequest, LlmResponse
from app.agents.report_synthesizer import (
    _business_driver_prompt,
    _cash_flow_prompt,
    _company_profile_system_prompt,
    _company_profile_user_prompt,
    _evidence_lines,
    _normalize_business_driver_payload,
    _normalize_cash_flow_payload,
    _sanitize_user_text,
    _system_prompt,
    _user_prompt,
    build_business_driver_report_from_payload,
    build_cash_flow_report_from_payload,
    build_latest_earnings_report_from_payload,
    synthesize_latest_earnings_payload,
)
from app.contracts.agent import (
    AgentRequest,
    AgentState,
    CoverageState,
    EvidenceMemory,
    TaskPolicy,
    default_task_policy,
)
from app.contracts.report import SourceRef
from app.contracts.research_task import ResearchTaskType


class _DummyClient(LlmClient):
    provider = None  # type: ignore[assignment]

    def complete_json(self, request: LlmRequest) -> LlmResponse:  # pragma: no cover - helper
        raise NotImplementedError


def _make_state(language: str = "zh") -> AgentState:
    return AgentState(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language=language,
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            allowed_tools=[
                "get_company_facts",
                "search_filing_sections",
                "search_metric_evidence",
            ],
            required_outputs=[
                "toplineVerdict",
                "keyTakeaways",
                "financialDashboard",
                "driverSnapshot",
                "riskSnapshot",
            ],
        ),
        evidence_memory=EvidenceMemory(
            facts={
                "business_summary": "Apple designs consumer electronics and services.",
            },
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "business_summary",
                    "snippet": "Apple designs consumer electronics and services.",
                }
            ],
        ),
        coverage=CoverageState(status="complete", evidence_count=1, citation_coverage="complete"),
    )


def test_user_prompts_switch_to_chinese_for_zh_language() -> None:
    state = _make_state(language="zh")
    source_refs = []

    latest_prompt = _user_prompt(
        request=_make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "zh"),
        state=state,
        source_refs=source_refs,
    )
    business_prompt = _business_driver_prompt(
        request=_make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state=state.model_copy(update={"task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE}),
        source_refs=source_refs,
    )
    cash_prompt = _cash_flow_prompt(
        request=_make_request(
            ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            "zh",
        ),
        state=state.model_copy(update={"task_type": ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION}),
        source_refs=source_refs,
    )

    assert "latest earnings task sections" not in latest_prompt.lower()
    assert "business driver deep dive" not in business_prompt.lower()
    assert "cash flow and capital allocation" not in cash_prompt.lower()
    assert "请生成最新财报分析所需的 typed JSON。" in latest_prompt
    assert "请生成业务驱动深挖所需的 typed task sections。" in business_prompt
    assert "请生成现金流与资本配置所需的 typed task sections。" in cash_prompt
    assert "Concise investor-facing company profile." not in latest_prompt
    assert "Short evidence-bound earnings verdict." not in latest_prompt
    assert "Evidence-bound takeaway." not in latest_prompt
    assert "Operating driver backed by evidence." not in latest_prompt
    assert "Risk backed by evidence." not in latest_prompt
    assert "请用 1-2 句话写一段面向投资者的公司画像。" not in latest_prompt


def test_prompts_remain_english_for_en_language() -> None:
    state = _make_state()

    assert _system_prompt("en").startswith("You are a financial research report synthesizer")
    assert _company_profile_system_prompt("en").startswith("You write concise investor-facing")
    assert "Write a 1-2 sentence investor-facing company profile" in _company_profile_user_prompt(
        state,
        "Apple designs consumer electronics and services.",
        "en",
    )
    assert "Concise investor-facing company profile." in str(
        synthesize_latest_earnings_payload("en")
    )


def test_synthesis_payload_switches_to_chinese_for_zh_language() -> None:
    payload = synthesize_latest_earnings_payload("zh")

    assert payload["company_profile"]["summary"] == "简洁的面向投资者的公司画像。"
    assert payload["topline_verdict"]["headline"] == "有证据支撑的简要财报判断。"
    assert payload["financial_dashboard"]["metrics"][0]["interpretation"] == "这个 KPI 的含义。"


def test_latest_earnings_rich_sections_are_preserved_in_typed_contract() -> None:
    state = _make_state(language="zh")
    payload = {
        "company_profile": {
            "summary": "Apple designs consumer electronics and services.",
            "source_ids": ["src_1"],
            "citation_status": "supported",
        },
        "topline_verdict": {
            "headline": "Revenue growth improved but margin pressure kept the quarter mixed.",
            "summary": (
                "Revenue improved because demand was resilient. Gross margin still needs "
                "watching because cost pressure remains visible. Operating income gives "
                "the quarter enough support, but the next quarter needs confirmation."
            ),
            "verdict": "mixed",
            "confidence": "medium",
        },
        "key_takeaways": [
            {
                "title": "Revenue improved",
                "summary": "Revenue grew against a mixed demand backdrop. The improvement is useful, but it needs confirmation from segment trends.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "revenue",
                    "value": "$94.0B",
                    "period": "latest_quarter",
                    "interpretation": "Revenue is the main top-line anchor.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "operating_income",
                    "value": "$28.0B",
                    "period": "latest_quarter",
                    "interpretation": "Operating income shows profit conversion.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "operating_cash_flow",
                    "value": "$24.0B",
                    "period": "latest_quarter",
                    "interpretation": "Cash flow checks earnings quality.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
            ],
            "chart_focus": ["revenue", "operating_income", "operating_cash_flow"],
        },
        "driver_snapshot": [
            {
                "title": "Services support mix",
                "summary": "Services provide a steadier contribution than hardware. This helps offset uneven device demand.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "risk_snapshot": [
            {
                "title": "Margin pressure remains visible",
                "summary": "The quarter still has pressure points. Investors should check whether cost pressure eases next quarter.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "quality_of_quarter": {
            "growth_quality": {
                "title": "Growth quality",
                "summary": "Growth looks useful but not one-dimensional. It should be judged together with margin and cash conversion.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            },
            "margin_quality": {
                "title": "Margin quality",
                "summary": "Margin quality is mixed because revenue improved while cost pressure still matters.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            },
            "cash_quality": {
                "title": "Cash quality",
                "summary": "Cash conversion supports the quarter because operating cash flow remains visible.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            },
            "one_time_items": None,
        },
        "drivers_and_draggers": {
            "drivers": [
                {
                    "title": "Demand resilience",
                    "summary": "Demand was resilient enough to support revenue. The point is strongest when paired with KPI evidence.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ],
            "draggers": [
                {
                    "title": "Cost pressure",
                    "summary": "Cost pressure still limits the quality of the quarter. It keeps the verdict from being cleanly positive.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ],
        },
        "bull_bear_read": {
            "bull_case": [
                {
                    "title": "Revenue base is durable",
                    "summary": "The bull case is that revenue has enough support to remain durable. Services mix can make that support less cyclical.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ],
            "bear_case": [
                {
                    "title": "Margin recovery is not proven",
                    "summary": "The bear case is that margin pressure can absorb revenue upside. That keeps the investment read balanced.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ],
            "balanced_read": {
                "title": "Balanced read",
                "summary": "The quarter is mixed because growth and cash support are real, but margin pressure remains unresolved.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            },
        },
        "watch_next": [
            {
                "title": "Watch operating margin",
                "metric": "operating_margin",
                "why_it_matters": "Operating margin will show whether revenue growth converts into higher quality earnings.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "claims": [
            {
                "text": "The quarter was mixed but evidence-backed.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
    }

    report = build_latest_earnings_report_from_payload(
        _make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "zh"),
        state,
        payload,
    )

    sections = report.task_sections
    assert sections.topline_verdict.confidence == "medium"
    assert sections.quality_of_quarter.growth_quality.title == "Growth quality"
    assert sections.quality_of_quarter.one_time_items is None
    assert sections.drivers_and_draggers.drivers[0].title == "Demand resilience"
    assert sections.drivers_and_draggers.draggers[0].title == "Cost pressure"
    assert sections.bull_bear_read.bull_case[0].title == "Revenue base is durable"
    assert sections.bull_bear_read.bear_case[0].title == "Margin recovery is not proven"
    assert sections.bull_bear_read.balanced_read.title == "Balanced read"
    assert sections.watch_next[0].metric == "operating_margin"
    assert sections.watch_next[0].evidence_refs[0].source_id == "src_1"


def test_latest_earnings_backfills_rich_sections_when_model_omits_them() -> None:
    state = _make_state(language="en")
    payload = {
        "company_profile": {
            "summary": "Apple designs consumer electronics and services.",
            "source_ids": ["src_1"],
            "citation_status": "supported",
        },
        "topline_verdict": {
            "headline": "Revenue growth improved but margin pressure kept the read balanced.",
            "summary": (
                "Revenue improved and gave the quarter a stronger top-line anchor. "
                "Margin pressure still needs monitoring. The next quarter should confirm "
                "whether the improvement converts into better earnings quality."
            ),
            "verdict": "mixed",
            "confidence": "medium",
        },
        "key_takeaways": [
            {
                "title": "Revenue improved",
                "summary": "Revenue growth gave the quarter a stronger top-line anchor. It should still be checked against margin conversion.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "Revenue",
                    "value": "$94.0B",
                    "period": "latest_quarter",
                    "interpretation": "Revenue is the main growth anchor.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "Operating margin",
                    "value": "28.4%",
                    "period": "latest_quarter",
                    "interpretation": "Operating margin checks conversion quality.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "Operating cash flow",
                    "value": "$24.0B",
                    "period": "latest_quarter",
                    "interpretation": "Operating cash flow checks earnings quality.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
            ],
            "chart_focus": ["revenue", "operating_margin", "operating_cash_flow"],
        },
        "driver_snapshot": [
            {
                "title": "Services support mix",
                "summary": "Services provided a steadier operating driver. That helps offset uneven hardware demand.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "risk_snapshot": [
            {
                "title": "Margin pressure remains visible",
                "summary": "Margin pressure remains the main drag on earnings quality. It keeps the read balanced rather than cleanly positive.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "claims": [],
    }

    report = build_latest_earnings_report_from_payload(
        _make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "en"),
        state,
        payload,
    )

    sections = report.task_sections
    assert sections.coverage.status == "complete"
    assert sections.quality_of_quarter.growth_quality.title == "Growth quality"
    assert sections.quality_of_quarter.margin_quality.title == "Margin quality"
    assert sections.quality_of_quarter.cash_quality.title == "Cash quality"
    assert sections.drivers_and_draggers.drivers[0].title == "Services support mix"
    assert sections.drivers_and_draggers.draggers[0].title == "Margin pressure remains visible"
    assert sections.bull_bear_read.bull_case[0].title == ("Bull case: Services support mix")
    assert sections.bull_bear_read.bear_case[0].title == (
        "Bear case: Margin pressure remains visible"
    )
    assert sections.bull_bear_read.bull_case[0].summary != (
        sections.drivers_and_draggers.drivers[0].summary
    )
    assert sections.bull_bear_read.bear_case[0].summary != (
        sections.drivers_and_draggers.draggers[0].summary
    )
    assert "Constructive read:" in sections.bull_bear_read.bull_case[0].summary
    assert "Cautious read:" in sections.bull_bear_read.bear_case[0].summary
    assert sections.bull_bear_read.balanced_read.title == "Balanced read"
    assert [item.metric for item in sections.watch_next] == [
        "Revenue",
        "Operating margin",
        "Operating cash flow",
    ]


def test_latest_earnings_rich_section_backfills_respect_chinese_locale() -> None:
    state = _make_state(language="zh")
    payload = {
        "company_profile": {
            "summary": "NVIDIA provides accelerated computing platforms and related software.",
            "source_ids": ["src_1"],
            "citation_status": "supported",
        },
        "topline_verdict": {
            "headline": "NVDA 本季收入和利润率仍然强劲。",
            "summary": "收入增长和利润率仍是本季判断的核心，现金流需要继续观察。",
            "verdict": "positive",
            "confidence": "medium",
        },
        "key_takeaways": [
            {
                "title": "收入增长仍是主线",
                "summary": "收入增长继续支撑本季财报判断，但下一季仍需要确认需求和利润率的延续性。",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "Revenue",
                    "value": "$35.1B",
                    "period": "latest_quarter",
                    "interpretation": "Revenue anchors the demand read.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "Gross Margin",
                    "value": "74.6%",
                    "period": "latest_quarter",
                    "interpretation": "Gross margin shows pricing and mix quality.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "Operating Cash Flow",
                    "value": "$16.6B",
                    "period": "latest_quarter",
                    "interpretation": "Operating cash flow checks earnings quality.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
            ],
            "chart_focus": ["revenue", "gross_margin", "operating_cash_flow"],
        },
        "driver_snapshot": [
            {
                "title": "数据中心需求支撑增长",
                "summary": "数据中心需求是收入增长的主要支撑，下一季需要确认订单和供给能否延续。",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "risk_snapshot": [
            {
                "title": "利润率高位延续风险",
                "summary": "利润率已经处在高位，后续需要观察产品组合和成本变化是否带来压力。",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "claims": [],
    }

    report = build_latest_earnings_report_from_payload(
        _make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "zh"),
        state,
        payload,
    )

    serialized = report.model_dump_json()
    assert "Growth quality" not in serialized
    assert "Margin quality" not in serialized
    assert "Cash quality" not in serialized
    assert "Bull case" not in serialized
    assert "Bear case" not in serialized
    assert "Constructive read:" not in serialized
    assert "Cautious read:" not in serialized
    assert "Balanced read" not in serialized
    assert "The reported quarter screens" not in serialized
    sections = report.task_sections
    assert sections.quality_of_quarter.growth_quality.title == "增长质量"
    assert sections.quality_of_quarter.margin_quality.title == "利润率质量"
    assert sections.quality_of_quarter.cash_quality.title == "现金质量"
    assert sections.bull_bear_read.bull_case[0].title.startswith("看多逻辑")
    assert sections.bull_bear_read.bear_case[0].title.startswith("看空逻辑")
    assert sections.bull_bear_read.balanced_read.title == "均衡判断"


def test_latest_earnings_reported_metric_placeholder_respects_chinese_locale() -> None:
    state = _make_state(language="zh")
    payload = {
        "company_profile": {
            "summary": "NVIDIA provides accelerated computing platforms and related software.",
            "source_ids": ["src_1"],
            "citation_status": "supported",
        },
        "topline_verdict": {
            "headline": "NVDA 本季收入仍是核心指标。",
            "summary": "收入指标已经被抽取，但模型没有提供完整解释。",
            "verdict": "mixed",
            "confidence": "medium",
        },
        "key_takeaways": [
            {
                "title": "收入指标可用",
                "summary": "收入数据可用于判断本季需求状态。",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "Revenue",
                    "value": "$35.1B",
                    "period": "latest_quarter",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ],
            "chart_focus": ["revenue"],
        },
        "driver_snapshot": [],
        "risk_snapshot": [],
        "claims": [],
    }

    report = build_latest_earnings_report_from_payload(
        _make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "zh"),
        state,
        payload,
    )

    metric = report.task_sections.financial_dashboard.metrics[0]
    assert metric.interpretation == "已报告指标。"
    assert "Reported metric." not in report.model_dump_json()


def test_latest_earnings_watch_next_metric_backfill_respects_chinese_locale() -> None:
    state = _make_state(language="zh")
    payload = {
        "company_profile": {
            "summary": "NVIDIA provides accelerated computing platforms and related software.",
            "source_ids": ["src_1"],
            "citation_status": "supported",
        },
        "topline_verdict": {
            "headline": "NVDA latest quarter stayed strong but needs follow-through.",
            "summary": (
                "Revenue and gross margin remain central to the latest quarter read. "
                "The next report should clarify whether operating leverage keeps improving."
            ),
            "verdict": "positive",
            "confidence": "medium",
        },
        "key_takeaways": [
            {
                "title": "Revenue stayed central",
                "summary": "Revenue is the primary demand signal in the latest quarter.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "Revenue",
                    "value": "$35.1B",
                    "period": "latest_quarter",
                    "interpretation": "Revenue anchors the demand read.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "Gross Margin",
                    "value": "74.6%",
                    "period": "latest_quarter",
                    "interpretation": "Gross margin shows pricing and mix quality.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "Operating Income",
                    "value": "$21.9B",
                    "period": "latest_quarter",
                    "interpretation": "Operating income shows leverage quality.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
            ],
            "chart_focus": ["revenue", "gross_margin", "operating_income"],
        },
        "driver_snapshot": [],
        "risk_snapshot": [],
        "claims": [],
    }

    report = build_latest_earnings_report_from_payload(
        _make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "zh"),
        state,
        payload,
    )

    why_text = "\n".join(item.why_it_matters for item in report.task_sections.watch_next)
    assert "latest-quarter evidence" not in why_text
    assert "next report should show" not in why_text
    assert "下一季报告" in why_text
    assert [item.metric for item in report.task_sections.watch_next] == [
        "Revenue",
        "Gross Margin",
        "Operating Income",
    ]


def test_latest_earnings_backfills_top_level_summary_when_model_summary_is_too_short() -> None:
    state = _make_state(language="zh")
    payload = {
        "company_profile": {
            "summary": "Best Buy sells consumer electronics and services through stores and digital channels.",
            "source_ids": ["src_1"],
            "citation_status": "supported",
        },
        "topline_verdict": {
            "headline": "BBY FY26 Q3业绩呈现",
            "summary": "BBY FY26 Q3业绩呈现",
            "verdict": "mixed",
            "confidence": "medium",
        },
        "key_takeaways": [
            {
                "title": "Revenue pressure remained visible",
                "summary": (
                    "Revenue pressure remained visible, but the quarter still showed "
                    "enough operating evidence to separate demand weakness from execution."
                ),
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "Revenue",
                    "value": "$9.67B",
                    "period": "latest_quarter",
                    "interpretation": (
                        "Revenue remains the main pressure point and should be read "
                        "against comparable sales and operating margin."
                    ),
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "Operating income",
                    "value": "$198M",
                    "period": "latest_quarter",
                    "interpretation": (
                        "Operating income shows whether cost discipline is offsetting "
                        "weaker sales momentum."
                    ),
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
            ],
            "chart_focus": ["Revenue", "Operating income"],
        },
        "driver_snapshot": [
            {
                "title": "Comparable sales pressure",
                "summary": (
                    "Comparable sales pressure remains the central operating driver. "
                    "The next read should test whether demand stabilizes across categories."
                ),
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "risk_snapshot": [
            {
                "title": "Margin conversion risk",
                "summary": (
                    "Margin conversion remains a risk because lower sales can absorb "
                    "cost discipline and limit earnings recovery."
                ),
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "claims": [],
    }

    report = build_latest_earnings_report_from_payload(
        _make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "zh"),
        state,
        payload,
    )

    assert report.sections["summary"] != "BBY FY26 Q3业绩呈现"
    assert len(report.sections["summary"]) > 120
    assert "Revenue pressure remained visible" in report.sections["summary"]
    assert "Comparable sales pressure" in report.sections["summary"]


def test_latest_earnings_repairs_incomplete_topline_verdict_text() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "ticker": "CVX",
            "evidence_memory": EvidenceMemory(
                facts={
                    "business_summary": (
                        "Chevron explores, produces, refines, and markets energy products."
                    )
                },
                source_refs=[
                    {
                        "source_id": "src_1",
                        "section": "Results of Operations",
                        "snippet": (
                            "Revenue declined while upstream realization and downstream "
                            "margins created a mixed earnings backdrop."
                        ),
                        "citation_status": "supported",
                    }
                ],
            ),
        }
    )
    payload = {
        "company_profile": {
            "summary": "Chevron explores, produces, refines, and markets energy products.",
            "source_ids": ["src_1"],
            "citation_status": "supported",
        },
        "topline_verdict": {
            "headline": "CVX FY2026 Q1财报呈现",
            "summary": "CVX FY2026 Q1财报呈现",
            "verdict": "mixed",
            "confidence": "medium",
        },
        "key_takeaways": [
            {
                "title": "收入和利润率共同决定本季质量",
                "summary": (
                    "收入变化需要和上游实现价格、下游利润率一起阅读。"
                    "这使本季更像混合质量的财报，而不是单一方向的增长故事。"
                ),
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "Revenue",
                    "value": "$47.6B",
                    "period": "2026-Q1",
                    "interpretation": "收入是判断能源需求和价格实现的第一层锚点。",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "Operating income",
                    "value": "$5.1B",
                    "period": "2026-Q1",
                    "interpretation": "经营利润检验收入能否转化为盈利质量。",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
            ],
            "chart_focus": ["Revenue", "Operating income"],
        },
        "driver_snapshot": [
            {
                "title": "上游价格实现仍是核心变量",
                "summary": "上游价格实现决定收入质量，后续需要观察油气价格和产量是否同向改善。",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "risk_snapshot": [
            {
                "title": "下游利润率波动仍需跟踪",
                "summary": "下游利润率波动可能抵消收入规模，对下一季盈利质量构成主要不确定性。",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            }
        ],
        "claims": [],
    }

    report = build_latest_earnings_report_from_payload(
        _make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "zh"),
        state,
        payload,
    )

    verdict = report.task_sections.topline_verdict
    assert verdict.headline != "CVX FY2026 Q1财报呈现"
    assert verdict.summary != "CVX FY2026 Q1财报呈现"
    assert not verdict.headline.endswith("财报呈现")
    assert "收入和利润率共同决定本季质量" in verdict.summary
    assert "上游价格实现仍是核心变量" in verdict.summary


def test_business_driver_reviewer_rewrites_template_thesis_headline() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                facts={
                    "company_name": "Advanced Micro Devices, Inc.",
                    "market_sector": "Technology",
                    "market_industry": "Semiconductors",
                    "business_summary": (
                        "AMD designs CPUs, GPUs, adaptive computing products, and "
                        "data-center accelerators."
                    ),
                    "metrics": [
                        {
                            "name": "revenue",
                            "value": 7438000000,
                            "unit": "USD",
                            "period": "2026-Q1",
                        },
                        {
                            "name": "gross margin",
                            "value": 0.52,
                            "unit": "percent",
                            "period": "2026-Q1",
                        },
                    ],
                },
                metric_evidence=[
                    {
                        "metric": "revenue",
                        "value": 7438000000,
                        "unit": "USD",
                        "fact_period": "2026-Q1",
                    },
                    {
                        "metric": "gross margin",
                        "value": 0.52,
                        "unit": "percent",
                        "fact_period": "2026-Q1",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "结构化 facts 支撑方向性业务判断",
                "durability": "mixed",
                "summary": (
                    "结构化 facts 已提供收入和利润率锚点，业务驱动结论应写成方向性判断。"
                    "投资者需要继续观察增长和利润率韧性。"
                ),
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "收入桥接",
                    "summary": "收入桥接要看增长是否能延续到下一季经营质量。",
                    "citation_status": "partial",
                },
                "segment_momentum": {
                    "title": "分部动能",
                    "summary": "分部动能需要用产品和客户暴露来补充判断。",
                    "citation_status": "partial",
                },
                "margin_and_mix": {
                    "title": "利润率与组合",
                    "summary": "利润率与组合决定收入是否能转化为经营杠杆。",
                    "citation_status": "partial",
                },
                "demand_signals": {
                    "title": "需求信号",
                    "summary": "需求信号需要和收入增长、产品暴露交叉验证。",
                    "citation_status": "partial",
                },
            },
            "claims": [],
        },
    )

    thesis = report.task_sections.driver_thesis
    assert thesis.headline != "结构化 facts 支撑方向性业务判断"
    assert thesis.headline != "业务驱动证据优先结论"
    assert "AMD" in thesis.headline or "Advanced Micro Devices" in thesis.headline
    assert "$7.4B" in thesis.summary
    assert "52.0%" in thesis.summary


def test_business_driver_template_headline_rewrites_even_when_summary_is_long() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "ticker": "NVDA",
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                facts={
                    "company_name": "NVIDIA Corporation",
                    "market_sector": "Technology",
                    "market_industry": "Semiconductors",
                    "metrics": [
                        {
                            "name": "revenue",
                            "value": 81615000000,
                            "unit": "USD",
                            "period": "FY2027-Q1",
                        },
                        {
                            "name": "gross margin",
                            "value": 0.7493,
                            "unit": "pure",
                            "period": "FY2027-Q1",
                        },
                        {
                            "name": "operating margin",
                            "value": 0.6557,
                            "unit": "pure",
                            "period": "FY2027-Q1",
                        },
                    ],
                },
                metric_evidence=[
                    {
                        "metric": "revenue",
                        "value": 81615000000,
                        "unit": "USD",
                        "fact_period": "FY2027-Q1",
                        "source": "preloaded_financial_facts",
                    },
                    {
                        "metric": "gross margin",
                        "value": 0.7493,
                        "unit": "pure",
                        "fact_period": "FY2027-Q1",
                        "source": "preloaded_financial_facts",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "业务驱动证据优先结论",
                "durability": "mixed",
                "summary": (
                    "NVDA 的证据收集已完成，当前报告先以已验证的 SEC 指标和 filing "
                    "片段形成保守结论；这份结论应视为证据优先版本，后续需要继续观察。"
                ),
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "收入桥接基于收入规模和利润率锚点，投资者需要观察增长是否延续。",
                    "citation_status": "partial",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "分部动能需要结合产品线暴露和数据中心需求来判断。",
                    "citation_status": "partial",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "利润率与组合决定收入能否转化为经营杠杆。",
                    "citation_status": "partial",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "需求信号需要和收入增长、客户场景交叉验证。",
                    "citation_status": "partial",
                },
            },
            "claims": [],
        },
    )

    thesis = report.task_sections.driver_thesis
    serialized = report.model_dump_json()
    assert thesis.headline != "业务驱动证据优先结论"
    assert "NVIDIA" in thesis.headline or "NVIDIA" in thesis.summary
    assert "$81.6B" in thesis.summary
    assert "74.9%" in thesis.summary
    assert "业务驱动证据优先结论" not in serialized


def test_business_driver_zh_backfill_never_uses_english_available_placeholders() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "ticker": "JPM",
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                facts={
                    "company_name": "JPMorgan Chase & Co.",
                    "market_sector": "Financial Services",
                    "market_industry": "Banks - Diversified",
                },
                source_refs=[],
                metric_evidence=[],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "No evidence for this lens.",
                "durability": "unclear",
                "summary": "证据不足，无法判断。",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "No evidence for this lens.",
                    "citation_status": "missing",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "No evidence for this lens.",
                    "citation_status": "missing",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "No evidence for this lens.",
                    "citation_status": "missing",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "No evidence for this lens.",
                    "citation_status": "missing",
                },
            },
            "claims": [],
        },
    )

    serialized = report.model_dump_json()
    assert "the available" not in serialized
    assert "available revenue" not in serialized
    assert "available margin" not in serialized
    assert "可用收入数据" in serialized
    assert "可用利润率" in serialized
    assert "无法判断" not in serialized


def test_business_driver_zh_visible_copy_removes_internal_retrieval_terms() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "ticker": "UNH",
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                facts={
                    "company_name": "UnitedHealth Group Inc.",
                    "market_sector": "Healthcare",
                    "market_industry": "Healthcare Plans",
                    "metrics": [
                        {
                            "name": "revenue",
                            "value": 111721000000,
                            "unit": "USD",
                            "period": "FY2026-Q1",
                        },
                        {
                            "name": "gross margin",
                            "value": 0.8852,
                            "unit": "pure",
                            "period": "FY2026-Q1",
                        },
                    ],
                },
                metric_evidence=[
                    {
                        "metric": "revenue",
                        "value": 111721000000,
                        "unit": "USD",
                        "fact_period": "FY2026-Q1",
                        "source": "preloaded_financial_facts",
                    },
                    {
                        "metric": "gross margin",
                        "value": 0.8852,
                        "unit": "pure",
                        "fact_period": "FY2026-Q1",
                        "source": "preloaded_financial_facts",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "UnitedHealth 业务驱动需要用 RAG 和 facts 判断",
                "durability": "mixed",
                "summary": (
                    "业务驱动结论不能只依赖 RAG 命中的 segment 片段；"
                    "结构化 facts 已提供收入和利润率锚点，因此当前 thesis 应写成方向性判断。"
                ),
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": (
                        "Structured yfinance facts reports revenue of 111721000000 USD "
                        "for FY2026 Q1 filed 2026-05-05."
                    ),
                    "citation_status": "partial",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "segment revenue 未稳定抽取，不能作为强结论。",
                    "citation_status": "partial",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": (
                        "Structured yfinance facts reports gross margin of 0.8852 pure "
                        "for FY2026 Q1 filed 2026-05-05."
                    ),
                    "citation_status": "partial",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "facts 和 market context 仍需要 source_ids 支撑。",
                    "citation_status": "partial",
                },
            },
            "claims": [],
        },
    )

    sections = report.task_sections
    points = sections.driver_map
    assert points.revenue_bridge is not None
    assert points.segment_momentum is not None
    assert points.margin_and_mix is not None
    assert points.demand_signals is not None
    visible_text = " ".join(
        [
            sections.driver_thesis.headline,
            sections.driver_thesis.summary,
            points.revenue_bridge.summary,
            points.segment_momentum.summary,
            points.margin_and_mix.summary,
            points.demand_signals.summary,
        ]
    )
    assert "RAG" not in visible_text
    assert "facts" not in visible_text
    assert "thesis" not in visible_text
    assert "Structured yfinance facts reports" not in visible_text
    assert "segment revenue" not in visible_text
    assert "收入为 $111.7B" in visible_text
    assert "毛利率为 88.5%" in visible_text
    assert "分部收入" in visible_text


def test_latest_earnings_rewrites_weak_evidence_phrasing_in_extended_sections() -> None:
    report = build_latest_earnings_report_from_payload(
        _make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "zh"),
        _make_state(language="zh").model_copy(
            update={
                "ticker": "V",
                "task_type": ResearchTaskType.LATEST_EARNINGS_READOUT,
                "evidence_memory": EvidenceMemory(
                    metric_evidence=[
                        {
                            "source": "preloaded_financial_facts",
                            "metric": "revenue",
                            "value": 11230000000,
                            "unit": "USD",
                            "fact_period": "FY2026-Q2",
                            "source_id": "src_revenue",
                        },
                        {
                            "source": "preloaded_financial_facts",
                            "metric": "gross margin",
                            "value": 0.813,
                            "unit": "pure",
                            "fact_period": "FY2026-Q2",
                            "source_id": "src_margin",
                        },
                    ],
                    source_refs=[
                        {
                            "source_id": "src_revenue",
                            "section": "yfinance structured snapshot",
                            "snippet": "Revenue was $11.2B.",
                            "citation_status": "supported",
                        },
                        {
                            "source_id": "src_margin",
                            "section": "yfinance structured snapshot",
                            "snippet": "Gross margin was 81.3%.",
                            "citation_status": "supported",
                        },
                    ],
                ),
            }
        ),
        {
            "company_profile": {
                "summary": "Visa 是全球支付技术公司。",
                "source_ids": ["src_revenue"],
                "citation_status": "supported",
            },
            "topline_verdict": {
                "headline": "Visa FY2026 Q2 财报呈现强劲增长。",
                "summary": "Visa FY2026 Q2 营收和利润率均保持强劲。",
                "verdict": "positive",
                "confidence": "medium",
            },
            "key_takeaways": [
                {
                    "title": "增长",
                    "summary": "Revenue 为 $11.2B，说明支付网络仍有规模动能。",
                    "source_ids": ["src_revenue"],
                    "citation_status": "supported",
                }
            ],
            "financial_dashboard": {
                "metrics": [
                    {
                        "name": "Revenue",
                        "value": "$11.2B",
                        "period": "FY2026-Q2",
                        "interpretation": "收入规模是增长质量锚点。",
                        "source_ids": ["src_revenue"],
                        "citation_status": "supported",
                    }
                ],
                "chart_focus": ["revenue"],
            },
            "driver_snapshot": [
                {
                    "title": "支付量",
                    "summary": "文件未披露具体支付量或跨境交易增速，无法判断是量价齐升。",
                    "source_ids": ["src_revenue"],
                    "citation_status": "partial",
                }
            ],
            "risk_snapshot": [],
            "quality_of_quarter": None,
            "drivers_and_draggers": {
                "drivers": [
                    {
                        "title": "支付量",
                        "summary": "文件未披露具体支付量或跨境交易增速，无法判断是量价齐升。",
                        "source_ids": ["src_revenue"],
                        "citation_status": "partial",
                    }
                ],
                "draggers": [],
            },
            "bull_bear_read": {
                "bull_case": [
                    {
                        "title": "积极情景",
                        "summary": "积极情景: 文件未披露具体支付量，无法判断是量价齐升。",
                        "source_ids": ["src_revenue"],
                        "citation_status": "partial",
                    }
                ],
                "bear_case": [],
                "balanced_read": None,
            },
            "watch_next": [],
            "claims": [],
        },
    )

    serialized = report.model_dump_json()
    assert "无法判断" not in serialized
    assert "证据不足" not in serialized
    assert "仍需用后续披露验证" in serialized


def test_latest_earnings_zh_metric_backfills_use_investor_copy_not_short_labels() -> None:
    report = build_latest_earnings_report_from_payload(
        _make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "zh"),
        _make_state(language="zh").model_copy(
            update={
                "ticker": "AAPL",
                "task_type": ResearchTaskType.LATEST_EARNINGS_READOUT,
                "evidence_memory": EvidenceMemory(
                    metric_evidence=[
                        {
                            "source": "preloaded_financial_facts",
                            "metric": "revenue",
                            "value": 111184000000,
                            "unit": "USD",
                            "fact_period": "FY2026-Q2",
                            "source_id": "src_revenue",
                        },
                        {
                            "source": "preloaded_financial_facts",
                            "metric": "gross margin",
                            "value": 0.493,
                            "unit": "pure",
                            "fact_period": "FY2026-Q2",
                            "source_id": "src_margin",
                        },
                    ],
                    source_refs=[
                        {
                            "source_id": "src_revenue",
                            "section": "structured snapshot",
                            "snippet": "Revenue was $111.2B.",
                            "citation_status": "supported",
                        },
                        {
                            "source_id": "src_margin",
                            "section": "structured snapshot",
                            "snippet": "Gross margin was 49.3%.",
                            "citation_status": "supported",
                        },
                    ],
                ),
            }
        ),
        {
            "company_profile": None,
            "topline_verdict": {
                "headline": "AAPL 本季收入和利润率共同支撑财报质量。",
                "summary": "AAPL 本季收入和利润率共同支撑财报质量。",
                "verdict": "mixed",
                "confidence": "medium",
            },
            "key_takeaways": [],
            "financial_dashboard": {"metrics": [], "chart_focus": []},
            "driver_snapshot": [],
            "risk_snapshot": [],
            "quality_of_quarter": None,
            "drivers_and_draggers": None,
            "bull_bear_read": None,
            "watch_next": [],
            "claims": [],
        },
    )

    metric_names = [metric.name for metric in report.task_sections.financial_dashboard.metrics]
    assert "收入" in metric_names
    assert "毛利率" in metric_names
    assert "Revenue" not in metric_names
    assert "Gross Margin" not in metric_names

    quality = report.task_sections.quality_of_quarter
    assert quality is not None
    assert quality.growth_quality is not None
    assert "Revenue 为" not in quality.growth_quality.summary
    assert "收入为 $111.2B" in quality.growth_quality.summary
    assert len(quality.growth_quality.summary) >= 45
    assert "下一季" in quality.growth_quality.summary


def test_cash_flow_short_capital_allocation_points_are_expanded_from_metrics() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="CRM",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="CRM",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
        evidence_memory=EvidenceMemory(
            facts={
                "metrics": [
                    {"name": "operating cash flow", "value": 6710000000, "unit": "USD"},
                    {"name": "capital expenditures", "value": 145000000, "unit": "USD"},
                    {"name": "free cash flow", "value": 6565000000, "unit": "USD"},
                    {"name": "current ratio", "value": 0.79, "unit": "x"},
                    {"name": "total debt", "value": 10300000000, "unit": "USD"},
                    {
                        "name": "cash and short term investments",
                        "value": 8940000000,
                        "unit": "USD",
                    },
                ]
            },
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "yfinance structured snapshot",
                    "snippet": "Structured yfinance cash flow metrics.",
                    "citation_status": "supported",
                }
            ],
        ),
    )
    payload = {
        "cash_quality_verdict": {
            "headline": "CRM 现金质量高。",
            "earnings_backed_by_cash": "yes",
            "summary": "CRM 自由现金流强劲。",
        },
        "cash_metrics": [],
        "capital_allocation": {
            "capex": [{"title": "资本支出", "summary": "资本支出"}],
            "debt": [{"title": "总债务", "summary": "总债务"}],
            "liquidity": [{"title": "流动比率", "summary": "流动比率"}],
        },
        "allocation_discipline": [],
        "red_flags": [],
        "claims": [],
    }

    report = build_cash_flow_report_from_payload(request, state, payload)
    points = [
        *report.task_sections.capital_allocation.capex,
        *report.task_sections.capital_allocation.debt,
        *report.task_sections.capital_allocation.liquidity,
    ]

    assert points
    assert all(len(point.summary) >= 30 for point in points)
    serialized = report.model_dump_json()
    assert '"summary":"资本支出"' not in serialized
    assert '"summary":"总债务"' not in serialized
    assert '"summary":"流动比率"' not in serialized
    assert "$145.0M" in serialized
    assert "$10.3B" in serialized
    assert "0.79x" in serialized


def test_chinese_company_profile_does_not_echo_raw_english_business_summary() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "ticker": "NVDA",
            "evidence_memory": EvidenceMemory(
                facts={
                    "business_summary": (
                        "NVIDIA Corporation provides graphics, compute, and networking "
                        "solutions in the United States, Taiwan, China, and internationally."
                    )
                },
                source_refs=[
                    {
                        "source_id": "src_1",
                        "section": "business_summary",
                        "snippet": (
                            "NVIDIA Corporation provides graphics, compute, and networking "
                            "solutions in the United States, Taiwan, China, and internationally."
                        ),
                        "citation_status": "supported",
                    }
                ],
            ),
        }
    )
    payload = {
        "company_profile": {
            "summary": (
                "NVIDIA Corporation provides graphics, compute, and networking solutions "
                "in the United States, Taiwan, China, and internationally."
            ),
            "source_ids": ["src_1"],
            "citation_status": "supported",
        },
        "topline_verdict": {
            "headline": "NVDA 本季收入和利润率仍然强劲。",
            "summary": "收入增长和利润率仍是本季判断的核心，现金流需要继续观察。",
            "verdict": "positive",
            "confidence": "medium",
        },
        "key_takeaways": [],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "Revenue",
                    "value": "$44.1B",
                    "period": "2026-Q1",
                    "interpretation": "收入是需求强度的第一层锚点。",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ],
            "chart_focus": ["Revenue"],
        },
        "driver_snapshot": [],
        "risk_snapshot": [],
        "claims": [],
    }

    report = build_latest_earnings_report_from_payload(
        _make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "zh"),
        state,
        payload,
    )

    profile = report.task_sections.company_profile
    assert profile is not None
    assert "provides graphics" not in profile.summary
    assert "United States" not in profile.summary
    assert "NVIDIA" in profile.summary
    assert "业务" in profile.summary


def test_cash_flow_positive_verdict_uses_investor_dense_summary() -> None:
    report = build_cash_flow_report_from_payload(
        _make_request(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION, "zh"),
        _make_state(language="zh").model_copy(
            update={
                "ticker": "AMD",
                "task_type": ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
                "evidence_memory": EvidenceMemory(
                    source_refs=[
                        {
                            "source_id": "src_1",
                            "section": "Cash flows",
                            "snippet": "Operating cash flow and free cash flow were both positive.",
                            "citation_status": "supported",
                        }
                    ],
                ),
            }
        ),
        {
            "cash_quality_verdict": {
                "headline": "盈利有现金生成支撑。",
                "earnings_backed_by_cash": "yes",
                "summary": (
                    "AMD 经营现金流和自由现金流均为正，管理层具备真实资本配置能力。"
                ),
            },
            "cash_metrics": [
                {
                    "name": "Operating cash flow",
                    "value": "$1.3B",
                    "period": "2026-Q1",
                    "interpretation": "经营现金流为正，说明利润质量至少有现金验证。",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                {
                    "name": "Free cash flow",
                    "value": "$950M",
                    "period": "2026-Q1",
                    "interpretation": "自由现金流为正，说明再投资后仍有资金弹性。",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
            ],
            "capital_allocation": {},
            "allocation_discipline": [],
            "red_flags": [],
            "claims": [],
        },
    )

    verdict = report.task_sections.cash_quality_verdict
    assert verdict.headline != "盈利有现金生成支撑。"
    assert verdict.summary != "AMD 经营现金流和自由现金流均为正，管理层具备真实资本配置能力。"
    assert "经营现金流" in verdict.summary
    assert "自由现金流" in verdict.summary
    assert "投资" in verdict.summary


def test_latest_earnings_prompt_requests_evidence_dense_memo_sections() -> None:
    prompt = _user_prompt(
        request=_make_request(ResearchTaskType.LATEST_EARNINGS_READOUT, "en"),
        state=_make_state(language="en"),
        source_refs=[],
    )

    assert "Return evidence-dense JSON only" in prompt
    assert "Return compact JSON" not in prompt
    assert "quality_of_quarter" in prompt
    assert "drivers_and_draggers" in prompt
    assert "bull_bear_read" in prompt
    assert "watch_next" in prompt
    assert "Do not provide price targets, buy/sell recommendations" in prompt


def test_sanitize_user_text_rewrites_placeholder_availability_language() -> None:
    text = _sanitize_user_text(
        "Capital expenditures data was not available in the retrieved evidence."
    )

    assert text == "Capital expenditures coverage remains thin in the retrieved sources."


def test_evidence_lines_are_compact_and_do_not_repeat_large_context() -> None:
    source_refs = [
        SourceRef(
            source_id=f"src_{index}",
            section="MD&A",
            snippet="Revenue increased because demand improved. " * 12,
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0001",
        )
        for index in range(1, 4)
    ]

    lines = _evidence_lines(source_refs)

    assert len(lines) == 3
    assert all("original_source_id" in line for line in lines)
    assert all(len(line) < 900 for line in lines)


def test_business_driver_claims_dict_payload_is_normalized_to_list() -> None:
    payload = _normalize_business_driver_payload(
        {
            "driver_thesis": {
                "headline": "Operating leverage is improving.",
                "durability": "durable",
                "summary": "Operating leverage is improving.",
            },
            "driver_map": {"product": []},
            "positive_signals": [],
            "negative_signals": [],
            "watchlist": ["Watch operating margin"],
            "claims": {
                "revenue_growth": {
                    "text": "Revenue growth remains resilient.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                "margin": {
                    "summary": "Margins are expanding.",
                    "source_id": "src_2",
                },
            },
        }
    )

    assert isinstance(payload["claims"], list)
    assert [claim["text"] for claim in payload["claims"]] == [
        "Revenue growth remains resilient.",
        "Margins are expanding.",
    ]
    assert payload["claims"][0]["source_ids"] == ["src_1"]
    assert payload["claims"][1]["source_ids"] == ["src_2"]


def test_business_driver_single_claim_dict_payload_is_normalized_to_list() -> None:
    payload = _normalize_business_driver_payload(
        {
            "driver_thesis": {
                "headline": "Operating leverage is improving.",
                "durability": "durable",
                "summary": "Operating leverage is improving.",
            },
            "driver_map": {"product": []},
            "positive_signals": [],
            "negative_signals": [],
            "watchlist": [],
            "claims": {
                "text": "Revenue growth remains resilient.",
                "source_id": "src_1",
                "citation_status": "supported",
            },
        }
    )

    assert isinstance(payload["claims"], list)
    assert len(payload["claims"]) == 1
    assert payload["claims"][0]["text"] == "Revenue growth remains resilient."
    assert payload["claims"][0]["source_ids"] == ["src_1"]


def test_business_driver_report_uses_four_evidence_bound_paragraphs() -> None:
    state = _make_state(language="en").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                source_refs=[
                    {
                        "source_id": "src_1",
                        "section": "MD&A",
                        "snippet": "Services revenue and margin mix supported growth.",
                        "citation_status": "supported",
                    }
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "en"),
        state,
        {
            "driver_thesis": {
                "headline": "Services mix supports the operating thesis.",
                "durability": "mixed",
                "summary": "Services and mix explain the current operating setup.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue growth was anchored by Services and product mix.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Services carried the cleaner segment signal.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Mix was the clearest margin bridge.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Demand evidence was constructive but not complete.",
                    "source_ids": ["src_1"],
                    "citation_status": "partial",
                },
            },
            "claims": [],
        },
    )

    sections = report.task_sections
    assert sections.driver_map.revenue_bridge is not None
    assert sections.driver_map.revenue_bridge.title == "Revenue bridge"
    assert sections.driver_map.revenue_bridge.evidence_refs
    assert sections.driver_map.revenue_bridge.evidence_refs[0].source_id == "src_1"
    assert sections.driver_map.segment_momentum is not None
    assert sections.driver_map.segment_momentum.evidence_refs
    assert sections.driver_map.margin_and_mix is not None
    assert sections.driver_map.margin_and_mix.evidence_refs
    assert sections.driver_map.demand_signals is not None
    assert sections.driver_map.demand_signals.evidence_refs
    assert sections.coverage.missing_sections == []
    assert not hasattr(sections, "watchlist")


def test_business_driver_prompt_includes_structured_facts_brief() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                facts={
                    "company_name": "NVIDIA Corporation",
                    "market_sector": "Technology",
                    "market_industry": "Semiconductors",
                    "business_summary": (
                        "NVIDIA sells accelerated computing platforms for data center, "
                        "gaming, professional visualization, and automotive markets."
                    ),
                    "metrics": [
                        {
                            "name": "revenue",
                            "value": 44062000000,
                            "unit": "USD",
                            "period": "2026-04-27",
                        },
                        {
                            "name": "gross margin",
                            "value": 0.613,
                            "unit": "percent",
                            "period": "2026-04-27",
                        },
                        {
                            "name": "operating income",
                            "value": 26422000000,
                            "unit": "USD",
                            "period": "2026-04-27",
                        },
                    ],
                },
                metric_evidence=[
                    {
                        "metric": "revenue",
                        "value": 44062000000,
                        "unit": "USD",
                        "fact_period": "2026-04-27",
                        "source": "sec_companyfacts",
                    },
                    {
                        "metric": "gross margin",
                        "value": 0.613,
                        "unit": "percent",
                        "fact_period": "2026-04-27",
                        "source": "preloaded_financial_facts",
                    },
                ],
                business_signals=[
                    {
                        "theme": "data center demand",
                        "summary": "Data center demand remained the main growth signal.",
                    }
                ],
            ),
        }
    )

    prompt = _business_driver_prompt(
        request=_make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state=state,
        source_refs=[],
    )

    assert "Business driver facts brief:" in prompt
    assert "Financial facts brief:" in prompt
    assert "NVIDIA Corporation" in prompt
    assert "Technology" in prompt
    assert "Semiconductors" in prompt
    assert "revenue: $44.1B" in prompt
    assert "gross margin: 61.3%" in prompt
    assert "Data center demand remained the main growth signal." in prompt
    assert "如果 segment 或 RAG 证据不完整" in prompt


def test_business_driver_placeholder_is_recovered_from_structured_facts() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                facts={
                    "company_name": "NVIDIA Corporation",
                    "market_sector": "Technology",
                    "market_industry": "Semiconductors",
                    "business_summary": (
                        "NVIDIA sells accelerated computing platforms for data center, "
                        "gaming, professional visualization, and automotive markets."
                    ),
                    "metrics": [
                        {
                            "name": "revenue",
                            "value": 44062000000,
                            "unit": "USD",
                            "period": "2026-04-27",
                        },
                        {
                            "name": "gross margin",
                            "value": 0.613,
                            "unit": "percent",
                            "period": "2026-04-27",
                        },
                    ],
                },
                metric_evidence=[
                    {
                        "metric": "revenue",
                        "value": 44062000000,
                        "unit": "USD",
                        "fact_period": "2026-04-27",
                        "source": "sec_companyfacts",
                    },
                    {
                        "metric": "gross margin",
                        "value": 0.613,
                        "unit": "percent",
                        "fact_period": "2026-04-27",
                        "source": "preloaded_financial_facts",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Evidence is thin.",
                "durability": "unclear",
                "summary": "No evidence for this lens.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "No evidence for this lens.",
                    "citation_status": "missing",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Unable to determine from the retrieved RAG chunks.",
                    "citation_status": "missing",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "证据不足，无法判断。",
                    "citation_status": "missing",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Insufficient evidence.",
                    "citation_status": "missing",
                },
            },
            "claims": [],
        },
    )

    points = [
        report.task_sections.driver_map.revenue_bridge,
        report.task_sections.driver_map.segment_momentum,
        report.task_sections.driver_map.margin_and_mix,
        report.task_sections.driver_map.demand_signals,
    ]
    assert all(point is not None for point in points)
    combined = " ".join(point.summary for point in points if point is not None)
    assert "No evidence for this lens" not in combined
    assert "Unable to determine" not in combined
    assert "Insufficient evidence" not in combined
    assert "无法判断" not in combined
    assert "NVIDIA" in combined
    assert "$44.1B" in combined
    assert "61.3%" in combined
    assert "方向性判断" in combined
    assert all(point.citation_status == "partial" for point in points if point is not None)


def test_business_driver_thesis_placeholder_is_recovered_from_structured_facts() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                facts={
                    "company_name": "Advanced Micro Devices, Inc.",
                    "market_sector": "Technology",
                    "market_industry": "Semiconductors",
                    "business_summary": (
                        "AMD designs CPUs, GPUs, adaptive computing products, and "
                        "data-center accelerators."
                    ),
                    "metrics": [
                        {
                            "name": "revenue",
                            "value": 7438000000,
                            "unit": "USD",
                            "period": "2026-Q1",
                        },
                        {
                            "name": "gross margin",
                            "value": 0.52,
                            "unit": "percent",
                            "period": "2026-Q1",
                        },
                    ],
                },
                metric_evidence=[
                    {
                        "metric": "revenue",
                        "value": 7438000000,
                        "unit": "USD",
                        "fact_period": "2026-Q1",
                        "source": "sec_companyfacts",
                    },
                    {
                        "metric": "gross margin",
                        "value": 0.52,
                        "unit": "percent",
                        "fact_period": "2026-Q1",
                        "source": "preloaded_financial_facts",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "No evidence for this lens.",
                "durability": "unclear",
                "summary": "证据不足，无法判断。",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue bridge is directional.",
                    "citation_status": "partial",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Segment momentum is directional.",
                    "citation_status": "partial",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Margin and mix is directional.",
                    "citation_status": "partial",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Demand signals are directional.",
                    "citation_status": "partial",
                },
            },
            "claims": [],
        },
    )

    thesis = report.task_sections.driver_thesis
    assert "No evidence" not in thesis.headline
    assert "无法判断" not in thesis.summary
    assert "Advanced Micro Devices" in thesis.summary
    assert "$7.4B" in thesis.summary
    assert "52.0%" in thesis.summary
    assert "方向性判断" in thesis.summary
    assert report.sections is not None
    assert report.sections["summary"] == thesis.summary


def test_business_driver_reviewer_rewrites_generic_chinese_points() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                facts={
                    "company_name": "Advanced Micro Devices, Inc.",
                    "market_sector": "Technology",
                    "market_industry": "Semiconductors",
                    "business_summary": (
                        "AMD designs CPUs, GPUs, adaptive computing products, and "
                        "data-center accelerators."
                    ),
                    "metrics": [
                        {
                            "name": "revenue",
                            "value": 7438000000,
                            "unit": "USD",
                            "period": "2026-Q1",
                        },
                        {
                            "name": "gross margin",
                            "value": 0.52,
                            "unit": "percent",
                            "period": "2026-Q1",
                        },
                    ],
                    "news_headlines": [
                        "AI infrastructure demand remains the key market debate."
                    ],
                    "technical_trend": "Shares trade above the 50-day moving average.",
                    "macro_context": "Higher rates keep long-duration growth multiples under scrutiny.",
                },
                metric_evidence=[
                    {
                        "metric": "revenue",
                        "value": 7438000000,
                        "unit": "USD",
                        "fact_period": "2026-Q1",
                        "source": "sec_companyfacts",
                    },
                    {
                        "metric": "gross margin",
                        "value": 0.52,
                        "unit": "percent",
                        "fact_period": "2026-Q1",
                        "source": "preloaded_financial_facts",
                    },
                ],
                business_signals=[
                    {
                        "summary": "AI accelerator demand remained the main growth signal.",
                    }
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Business driver thesis",
                "durability": "unclear",
                "summary": "Business driver evidence shows revenue and demand.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue bridge is important for investors.",
                    "citation_status": "unverified",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Segment momentum is important for investors.",
                    "citation_status": "unverified",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Margin and mix is important for investors.",
                    "citation_status": "unverified",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Demand signals are important for investors.",
                    "citation_status": "unverified",
                },
            },
            "claims": [],
        },
    )

    points = [
        report.task_sections.driver_map.revenue_bridge,
        report.task_sections.driver_map.segment_momentum,
        report.task_sections.driver_map.margin_and_mix,
        report.task_sections.driver_map.demand_signals,
    ]
    combined = " ".join(point.summary for point in points if point is not None)
    assert "Revenue bridge is important" not in combined
    assert "Segment momentum is important" not in combined
    assert "Margin and mix is important" not in combined
    assert "Demand signals are important" not in combined
    assert "Advanced Micro Devices" in combined
    assert "$7.4B" in combined
    assert "52.0%" in combined
    assert "投资" in combined
    assert "AI accelerator demand" not in combined
    assert all(point.citation_status == "partial" for point in points if point is not None)


def test_business_driver_report_backfills_clean_refs_when_synthesis_omits_source_ids() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                source_refs=[
                    {
                        "source_id": "src_revenue",
                        "section": "SEC companyfacts",
                        "snippet": "Revenue increased because cloud demand improved.",
                        "citation_status": "supported",
                    },
                    {
                        "source_id": "src_segment",
                        "section": "Segment information",
                        "snippet": "Services segment revenue grew faster than products.",
                        "citation_status": "supported",
                    },
                    {
                        "source_id": "src_table",
                        "section": "Segment table",
                        "snippet": "| | | 6,402 | | | 15,509 | | | Services | Products | ---|---",
                        "citation_status": "supported",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Cloud demand supports the thesis.",
                "durability": "mixed",
                "summary": (
                    "Cloud demand and services mix support the current business-driver read."
                ),
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue growth was anchored by cloud demand.",
                    "citation_status": "supported",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Services segment momentum was the cleaner growth signal.",
                    "citation_status": "supported",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Services mix provided the margin signal.",
                    "citation_status": "supported",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Cloud demand remains the clearest demand signal.",
                    "citation_status": "unverified",
                },
            },
            "claims": [],
        },
    )

    points = [
        report.task_sections.driver_map.revenue_bridge,
        report.task_sections.driver_map.segment_momentum,
        report.task_sections.driver_map.margin_and_mix,
        report.task_sections.driver_map.demand_signals,
    ]
    assert all(point is not None for point in points)
    assert all(point.evidence_refs for point in points if point is not None)
    assert {
        evidence_ref.source_id
        for point in points
        if point is not None
        for evidence_ref in point.evidence_refs
    } <= {"src_revenue", "src_segment"}
    assert all(point.citation_status == "partial" for point in points if point is not None)


def test_business_driver_report_recovers_partial_placeholder_with_clean_lens_refs() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                source_refs=[
                    {
                        "source_id": "src_margin",
                        "section": "Margins and expenses",
                        "snippet": (
                            "Gross margin expanded as operating expenses grew slower "
                            "than revenue and product mix improved."
                        ),
                        "citation_status": "supported",
                    },
                    {
                        "source_id": "src_revenue",
                        "section": "Results of operations",
                        "snippet": "Revenue increased because enterprise customer demand improved.",
                        "citation_status": "supported",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Revenue growth and margin discipline both matter.",
                "durability": "mixed",
                "summary": "Revenue growth is constructive, while margin evidence is partial.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue growth came from enterprise demand.",
                    "source_ids": ["src_revenue"],
                    "citation_status": "supported",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Enterprise customer demand remained the cleaner segment signal.",
                    "source_ids": ["src_revenue"],
                    "citation_status": "supported",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Evidence for this business-driver lens remains partial.",
                    "citation_status": "unverified",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Enterprise customer demand remained constructive.",
                    "source_ids": ["src_revenue"],
                    "citation_status": "supported",
                },
            },
            "claims": [],
        },
    )

    point = report.task_sections.driver_map.margin_and_mix
    assert point is not None
    assert point.evidence_refs
    assert point.evidence_refs[0].source_id == "src_margin"
    assert point.citation_status == "partial"
    assert point.summary != "Evidence for this business-driver lens remains partial."
    assert "利润率" in point.summary


def test_business_driver_placeholder_recovery_respects_english_locale() -> None:
    state = _make_state(language="en").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                source_refs=[
                    {
                        "source_id": "src_margin",
                        "section": "Margins and expenses",
                        "snippet": (
                            "Operating margin improved because operating expenses "
                            "grew slower than revenue."
                        ),
                        "citation_status": "supported",
                    }
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "en"),
        state,
        {
            "driver_thesis": {
                "headline": "Margin discipline matters.",
                "durability": "mixed",
                "summary": "Margin evidence is partial but useful.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue evidence remains partial.",
                    "citation_status": "unverified",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Segment evidence remains partial.",
                    "citation_status": "unverified",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Evidence for this business-driver lens remains partial.",
                    "citation_status": "unverified",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Demand evidence remains partial.",
                    "citation_status": "unverified",
                },
            },
            "claims": [],
        },
    )

    point = report.task_sections.driver_map.margin_and_mix
    assert point is not None
    assert point.evidence_refs
    assert point.citation_status == "partial"
    assert "Margin and mix evidence remains partial" in point.summary
    assert "利润率" not in point.summary


def test_business_driver_report_recovers_placeholder_after_invalid_source_ids() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                source_refs=[
                    {
                        "source_id": "src_bank_margin",
                        "section": "Business segment highlights",
                        "snippet": (
                            "Net interest income and provision expense drove the "
                            "banking profitability mix."
                        ),
                        "citation_status": "supported",
                    }
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Banking profitability mix needs evidence.",
                "durability": "mixed",
                "summary": "The bank margin read is partial.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue evidence remains partial.",
                    "citation_status": "unverified",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Segment evidence remains partial.",
                    "citation_status": "unverified",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Evidence for this business-driver lens remains partial.",
                    "source_ids": ["missing_source_id"],
                    "citation_status": "supported",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Demand evidence remains partial.",
                    "citation_status": "unverified",
                },
            },
            "claims": [],
        },
    )

    point = report.task_sections.driver_map.margin_and_mix
    assert point is not None
    assert point.evidence_refs
    assert point.evidence_refs[0].source_id == "src_bank_margin"
    assert point.citation_status == "partial"
    assert point.summary != "Evidence for this business-driver lens remains partial."


def test_business_driver_report_recovers_bank_margin_refs_not_accounting_noise() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                source_refs=[
                    {
                        "source_id": "src_bank_margin",
                        "section": "Business segment highlights",
                        "snippet": (
                            "Principal transactions revenue, net interest income, "
                            "provision expense, and noninterest expense shape the "
                            "banking profitability mix."
                        ),
                        "citation_status": "supported",
                    }
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Bank margin mix needs segment evidence.",
                "durability": "mixed",
                "summary": "Bank profitability depends on net interest and fee mix.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue evidence remains partial.",
                    "citation_status": "unverified",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Segment evidence remains partial.",
                    "citation_status": "unverified",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Evidence for this business-driver lens remains partial.",
                    "source_ids": ["src_bank_margin"],
                    "citation_status": "supported",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Demand evidence remains partial.",
                    "citation_status": "unverified",
                },
            },
            "claims": [],
        },
    )

    point = report.task_sections.driver_map.margin_and_mix
    assert point is not None
    assert point.evidence_refs
    assert point.evidence_refs[0].source_id == "src_bank_margin"
    assert point.citation_status == "partial"
    assert point.summary != "Evidence for this business-driver lens remains partial."


def test_business_driver_noisy_ref_placeholder_recovery_uses_zh_backfill() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                source_refs=[
                    {
                        "source_id": "src_margin",
                        "section": "Margins and expenses",
                        "snippet": (
                            "Operating margin improved because expenses, cost "
                            "discipline, and profit mix grew slower than revenue."
                        ),
                        "citation_status": "supported",
                    },
                    {
                        "source_id": "src_table",
                        "section": "Noisy table",
                        "snippet": "| | | 6,402 | | | 15,509 | | | ---|---",
                        "citation_status": "supported",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Margin evidence needs cleanup.",
                "durability": "mixed",
                "summary": "Margin evidence needs cleanup.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue evidence remains partial.",
                    "citation_status": "unverified",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Segment evidence remains partial.",
                    "citation_status": "unverified",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Evidence for this business-driver lens remains partial.",
                    "source_ids": ["src_table"],
                    "citation_status": "supported",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Demand evidence remains partial.",
                    "citation_status": "unverified",
                },
            },
            "claims": [],
        },
    )

    point = report.task_sections.driver_map.margin_and_mix
    assert point is not None
    assert point.evidence_refs
    assert point.evidence_refs[0].source_id == "src_margin"
    assert point.citation_status == "partial"
    assert "Evidence for this business-driver lens remains partial" not in point.summary
    assert "利润率" in point.summary
    assert "| | |" not in point.model_dump_json()


def test_business_driver_zh_placeholder_without_refs_is_localized() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(source_refs=[]),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Evidence is thin.",
                "durability": "mixed",
                "summary": "Evidence is thin.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue evidence remains partial.",
                    "citation_status": "unverified",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Segment evidence remains partial.",
                    "citation_status": "unverified",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Evidence for this business-driver lens remains partial.",
                    "citation_status": "unverified",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Demand evidence remains partial.",
                    "citation_status": "unverified",
                },
            },
            "claims": [],
        },
    )

    point = report.task_sections.driver_map.margin_and_mix
    assert point is not None
    assert point.evidence_refs == []
    assert point.citation_status == "unverified"
    assert "Evidence for this business-driver lens remains partial" not in point.summary
    assert "利润率" in point.summary


def test_business_driver_report_filters_noisy_synthesis_text_and_refs() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                source_refs=[
                    {
                        "source_id": "src_clean",
                        "section": "MD&A",
                        "snippet": "Services revenue and installed base demand supported growth.",
                        "citation_status": "supported",
                    },
                    {
                        "source_id": "src_table",
                        "section": "Segment table",
                        "snippet": ("| | | 6,402 | | | 15,509 | | | Services | Products | ---|---"),
                        "citation_status": "supported",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Services demand supports the thesis.",
                "durability": "mixed",
                "summary": "Services demand supports the thesis.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": (
                        "营收增长来自服务业务，但原始表格包含 | | | 6,402 | | | "
                        "15,509 | | | Services | Products | ---|--- 噪声。"
                    ),
                    "source_ids": ["src_table"],
                    "citation_status": "supported",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Services revenue and installed base demand supported growth.",
                    "source_ids": ["src_clean"],
                    "citation_status": "supported",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": "Mix evidence remains partial.",
                    "source_ids": ["src_clean"],
                    "citation_status": "partial",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Installed base demand supported growth.",
                    "source_ids": ["src_clean"],
                    "citation_status": "supported",
                },
            },
            "claims": [
                {
                    "text": "The same noisy table | | | 6,402 | | | should not leak.",
                    "source_ids": ["src_table"],
                    "citation_status": "supported",
                }
            ],
        },
    )

    serialized = report.model_dump_json()
    sections = report.task_sections
    assert sections.driver_map.revenue_bridge is not None
    assert "| | |" not in serialized
    assert "---|---" not in serialized
    assert sections.driver_map.revenue_bridge.evidence_refs == []
    assert sections.driver_map.revenue_bridge.citation_status == "unverified"
    assert all("| | |" not in claim.text for claim in report.claims)


def test_business_driver_report_filters_footnote_and_table_of_contents_refs() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                source_refs=[
                    {
                        "source_id": "src_vz_clean",
                        "section": "MD&A demand",
                        "snippet": (
                            "Wireless service revenue increased as fixed wireless access "
                            "and fiber broadband demand supported customer additions."
                        ),
                        "citation_status": "supported",
                    },
                    {
                        "source_id": "src_vz_footnote",
                        "section": "Segment footnotes",
                        "snippet": (
                            "FWA broadband, Fios internet and other fiber-based services. "
                            "(2) Other revenue primarily includes revenue from wireline "
                            "products, wholesale and other services."
                        ),
                        "citation_status": "supported",
                    },
                    {
                        "source_id": "src_bby_table",
                        "section": "Table of Contents",
                        "snippet": (
                            "23 Table of Contents International segment revenue mix "
                            "percentages and comparable sales percentage changes by "
                            "revenue category were as follows: | | | Computing and Mobile "
                            "Phones | Consumer Electronics | Appliances | Entertainment |"
                        ),
                        "citation_status": "supported",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Demand evidence is mixed.",
                "durability": "mixed",
                "summary": "Demand evidence is mixed.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Wireless service revenue increased on broadband demand.",
                    "source_ids": ["src_vz_clean"],
                    "citation_status": "supported",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": (
                        "International segment revenue mix percentages were listed in a "
                        "Table of Contents fragment."
                    ),
                    "source_ids": ["src_bby_table"],
                    "citation_status": "supported",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": (
                        "Other revenue primarily includes revenue from wireline products "
                        "and wholesale services."
                    ),
                    "source_ids": ["src_vz_footnote"],
                    "citation_status": "supported",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Broadband demand supported customer additions.",
                    "source_ids": ["src_vz_clean", "src_vz_footnote"],
                    "citation_status": "supported",
                },
            },
            "claims": [],
        },
    )

    serialized = report.model_dump_json()
    assert "Other revenue primarily includes" not in serialized
    assert "Table of Contents" not in serialized
    assert "Wireless service revenue increased" in serialized
    sections = report.task_sections.driver_map
    assert sections.segment_momentum is not None
    assert all(ref.source_id != "src_bby_table" for ref in sections.segment_momentum.evidence_refs)
    assert sections.margin_and_mix is not None
    assert all(ref.source_id != "src_vz_footnote" for ref in sections.margin_and_mix.evidence_refs)
    assert sections.demand_signals is not None
    assert [ref.source_id for ref in sections.demand_signals.evidence_refs] == ["src_vz_clean"]


def test_business_driver_report_filters_low_information_pipe_refs_and_claim_citations() -> None:
    state = _make_state(language="zh").model_copy(
        update={
            "task_type": ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            "evidence_memory": EvidenceMemory(
                source_refs=[
                    {
                        "source_id": "src_clean",
                        "section": "MD&A demand",
                        "snippet": (
                            "Wireless service revenue increased as broadband demand "
                            "supported customer additions."
                        ),
                        "citation_status": "supported",
                    },
                    {
                        "source_id": "src_pipe",
                        "section": "Revenue and Contract Costs",
                        "snippet": (
                            "Revenue and Contract Costs | | | We earn revenue from "
                            "contracts with customers, primarily through the provision "
                            "of telecommunications and other services."
                        ),
                        "citation_status": "supported",
                    },
                ],
            ),
        }
    )

    report = build_business_driver_report_from_payload(
        _make_request(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, "zh"),
        state,
        {
            "driver_thesis": {
                "headline": "Demand evidence is mixed.",
                "durability": "mixed",
                "summary": "Demand evidence is mixed.",
            },
            "driver_map": {
                "revenue_bridge": {
                    "title": "Revenue bridge",
                    "summary": "Wireless service revenue increased on broadband demand.",
                    "source_ids": ["src_clean", "src_pipe"],
                    "citation_status": "supported",
                },
                "segment_momentum": {
                    "title": "Segment momentum",
                    "summary": "Segment evidence remains partial.",
                    "source_ids": ["src_pipe"],
                    "citation_status": "supported",
                },
                "margin_and_mix": {
                    "title": "Margin and mix",
                    "summary": (
                        "利润率证据指向 Revenue and Contract Costs | | | We earn "
                        "revenue from contracts with customers."
                    ),
                    "source_ids": ["src_pipe"],
                    "citation_status": "supported",
                },
                "demand_signals": {
                    "title": "Demand signals",
                    "summary": "Broadband demand supported customer additions.",
                    "source_ids": ["src_clean"],
                    "citation_status": "supported",
                },
            },
            "claims": [
                {
                    "text": "Wireless service revenue increased on broadband demand.",
                    "source_ids": ["src_clean", "src_pipe"],
                    "citation_status": "supported",
                }
            ],
        },
    )

    serialized = report.model_dump_json()
    assert "| | |" not in serialized
    assert "Revenue and Contract Costs" not in serialized
    assert len(report.claims) == 1
    assert [ref.source_id for ref in report.claims[0].source_refs] == ["src_clean"]
    assert report.claims[0].citation_status == "partial"
    sections = report.task_sections.driver_map
    assert sections.revenue_bridge is not None
    assert [ref.source_id for ref in sections.revenue_bridge.evidence_refs] == ["src_clean"]
    assert sections.revenue_bridge.citation_status == "partial"
    assert sections.margin_and_mix is not None
    assert sections.margin_and_mix.citation_status == "unverified"


def test_business_driver_payload_folds_legacy_lenses_into_paragraph_fields() -> None:
    payload = _normalize_business_driver_payload(
        {
            "driver_thesis": {
                "headline": "Demand improved.",
                "durability": "mixed",
                "summary": "Demand improved.",
            },
            "driver_map": {
                "product": [
                    {
                        "title": "Product demand",
                        "summary": "Product demand supported revenue.",
                        "source_id": "src_1",
                    }
                ],
                "segment": [
                    {
                        "title": "Services",
                        "summary": "Services were the cleaner segment signal.",
                        "source_id": "src_2",
                    }
                ],
                "pricing": [
                    {
                        "title": "Mix",
                        "summary": "Mix supported margin.",
                        "source_id": "src_3",
                    }
                ],
                "demand": [
                    {
                        "title": "Demand",
                        "summary": "Demand remained resilient.",
                        "source_id": "src_4",
                    }
                ],
            },
            "positive_signals": [],
            "negative_signals": [],
            "watchlist": ["Track demand."],
            "claims": [],
        }
    )

    assert payload["driver_map"]["revenue_bridge"]["title"] == "Product demand"
    assert payload["driver_map"]["segment_momentum"]["title"] == "Services"
    assert payload["driver_map"]["margin_and_mix"]["title"] == "Mix"
    assert payload["driver_map"]["demand_signals"]["title"] == "Demand"
    assert "positive_signals" not in payload
    assert "watchlist" not in payload


def test_business_driver_payload_accepts_camel_case_driver_map() -> None:
    payload = _normalize_business_driver_payload(
        {
            "driverThesis": {
                "headline": "Revenue mix improved.",
                "durability": "mixed",
                "summary": "Revenue mix improved with partial evidence.",
            },
            "driverMap": {
                "revenueBridge": {
                    "title": "Revenue bridge",
                    "summary": "Revenue bridge improved.",
                    "sourceIds": ["src_1"],
                    "citationStatus": "supported",
                },
                "demandSignals": {
                    "title": "Demand",
                    "summary": "Demand evidence was constructive.",
                    "sourceIds": ["src_2"],
                    "citationStatus": "partial",
                },
            },
            "claims": [],
        }
    )

    assert payload["driver_map"]["revenue_bridge"]["title"] == "Revenue bridge"
    assert payload["driver_map"]["revenue_bridge"]["source_ids"] == ["src_1"]
    assert payload["driver_map"]["demand_signals"]["title"] == "Demand"
    assert payload["driver_map"]["demand_signals"]["citation_status"] == "partial"


def test_cash_flow_capital_allocation_backfills_empty_point_summaries() -> None:
    payload = _normalize_cash_flow_payload(
        {
            "cash_quality_verdict": {
                "headline": "Cash flow is mixed.",
                "earnings_backed_by_cash": "mixed",
                "summary": "Cash flow is mixed but still supported by operating cash generation.",
            },
            "cash_metrics": [],
            "capital_allocation": {
                "capex": [
                    {
                        "title": "Capex intensity",
                        "summary": "",
                        "investor_implication": "Capex remains the main reinvestment use of cash.",
                        "source_ids": ["src_1"],
                    }
                ],
                "buybacks": [
                    {
                        "title": "Buybacks",
                        "summary": "",
                        "value": "$0",
                        "period": "latest quarter",
                        "source_ids": ["src_2"],
                    }
                ],
            },
            "allocation_discipline": [
                {
                    "title": "Discipline",
                    "summary": "",
                    "strengths": "Liquidity remains adequate.",
                    "weaknesses": "Capital intensity is elevated.",
                }
            ],
            "red_flags": [],
            "claims": [],
        }
    )

    capex = payload["capital_allocation"]["capex"][0]
    buybacks = payload["capital_allocation"]["buybacks"][0]
    discipline = payload["allocation_discipline"][0]
    assert (
        capex["summary"] == "Investor implication: Capex remains the main reinvestment use of cash."
    )
    assert buybacks["summary"] == "Value was $0 for latest quarter."
    assert "Liquidity remains adequate" in discipline["summary"]


def test_cash_flow_metric_object_values_are_normalized_to_display_values() -> None:
    payload = _normalize_cash_flow_payload(
        {
            "cash_quality_verdict": {
                "headline": "Cash generation remains positive.",
                "earnings_backed_by_cash": "yes",
                "summary": "Cash generation remains positive.",
            },
            "cash_metrics": [
                {
                    "name": "operating_cash_flow",
                    "value": {
                        "value": 2156000000,
                        "unit": "USD",
                        "period": "2026Q1",
                    },
                    "interpretation": "Operating cash flow anchors cash conversion.",
                    "source_ids": ["src_1"],
                },
                {
                    "name": "free_cash_flow",
                    "value": {
                        "value": 664000000,
                        "unit": "USD",
                        "period": "2026Q1",
                    },
                    "interpretation": "Free cash flow remains positive.",
                    "source_ids": ["src_2"],
                },
                {
                    "name": "share_repurchases",
                    "value": {
                        "value": 0,
                        "unit": "USD",
                        "period": "2026Q1",
                    },
                    "interpretation": "No share repurchases were reported.",
                    "source_ids": ["src_3"],
                },
            ],
            "capital_allocation": {},
            "allocation_discipline": [],
            "red_flags": [],
            "claims": [],
        }
    )

    metric_values = [metric["value"] for metric in payload["cash_metrics"]]
    assert metric_values == ["$2.2B", "$664.0M", "$0"]
    assert all("value" not in value and "unit" not in value for value in metric_values)


def test_cash_flow_qualitative_metric_is_moved_to_allocation_discipline() -> None:
    payload = _normalize_cash_flow_payload(
        {
            "cash_quality_verdict": {
                "headline": "Cash conversion is mixed.",
                "earnings_backed_by_cash": "mixed",
                "summary": "Cash conversion is mixed.",
            },
            "cash_metrics": [
                {
                    "name": "operating_cash_flow",
                    "value": {
                        "value": 2156000000,
                        "unit": "USD",
                        "period": "2026Q1",
                    },
                    "interpretation": "Operating cash flow anchors cash conversion.",
                    "source_ids": ["src_1"],
                },
                {
                    "name": "cash_conversion_quality",
                    "value": "mixed - cash flow exists but quality remains thin.",
                    "interpretation": "Qualitative assessment should not render as a KPI.",
                    "source_ids": ["src_2"],
                },
            ],
            "capital_allocation": {},
            "allocation_discipline": [],
            "red_flags": [],
            "claims": [],
        }
    )

    metric_names = [metric["name"] for metric in payload["cash_metrics"]]
    assert metric_names == ["operating_cash_flow"]
    assert payload["cash_metrics"][0]["value"] == "$2.2B"
    assert payload["allocation_discipline"][0]["title"] == "cash_conversion_quality"
    assert (
        payload["allocation_discipline"][0]["summary"]
        == "mixed - cash flow exists but quality remains thin."
    )


def test_cash_flow_fact_backfill_keeps_core_metrics_and_adds_resilience_points() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
    )
    state = AgentState(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
        evidence_memory=EvidenceMemory(
            facts={
                "metrics": [
                    {
                        "name": "net income",
                        "value": 29578000000,
                        "unit": "USD",
                        "period": "2026-03-31",
                    },
                    {
                        "name": "operating cash flow",
                        "value": 28702000000,
                        "unit": "USD",
                        "period": "2026-03-31",
                    },
                    {
                        "name": "capital expenditures",
                        "value": 1971000000,
                        "unit": "USD",
                        "period": "2026-03-31",
                    },
                    {
                        "name": "free cash flow",
                        "value": 26731000000,
                        "unit": "USD",
                        "period": "2026-03-31",
                    },
                    {
                        "name": "current ratio",
                        "value": 1.0704,
                        "unit": "x",
                        "period": "2026-03-31",
                    },
                    {
                        "name": "total debt",
                        "value": 84711000000,
                        "unit": "USD",
                        "period": "2026-03-31",
                    },
                    {
                        "name": "cash and short term investments",
                        "value": 45572000000,
                        "unit": "USD",
                        "period": "2026-03-31",
                    },
                ]
            },
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "yfinance structured snapshot",
                    "snippet": "Structured quarterly yfinance cash flow and balance sheet facts.",
                    "citation_status": "supported",
                }
            ],
        ),
    )
    payload = {
        "cash_quality_verdict": {
            "headline": "Cash generation is strong.",
            "earnings_backed_by_cash": "yes",
            "summary": "Cash generation is strong and supported by free cash flow.",
        },
        "cash_metrics": [
            {
                "name": "Metric",
                "value": "available",
                "interpretation": "placeholder",
                "source_ids": [],
            }
        ],
        "capital_allocation": {
            "capex": [
                {
                    "title": "Capex is modest",
                    "summary": "Capex is modest against operating cash flow.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ]
        },
        "allocation_discipline": [],
        "red_flags": [],
        "claims": [],
    }

    report = build_cash_flow_report_from_payload(request, state, payload)
    metric_names = [metric.name.lower() for metric in report.task_sections.cash_metrics]

    assert metric_names == [
        "net income",
        "operating cash flow",
        "capital expenditures",
        "free cash flow",
        "current ratio",
        "total debt",
        "cash and short term investments",
    ]
    assert report.task_sections.capital_allocation.capex
    assert report.task_sections.capital_allocation.debt
    assert report.task_sections.capital_allocation.liquidity
    assert report.task_sections.capital_allocation.buybacks == []
    assert report.task_sections.capital_allocation.dividends == []


def test_cash_flow_partial_llm_metrics_are_completed_from_structured_facts() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
    )
    state = AgentState(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
        evidence_memory=EvidenceMemory(
            facts={
                "metrics": [
                    {"name": "net income", "value": 1384000000, "unit": "USD"},
                    {"name": "operating cash flow", "value": 2957000000, "unit": "USD"},
                    {"name": "capital expenditures", "value": 132000000, "unit": "USD"},
                    {"name": "free cash flow", "value": 2825000000, "unit": "USD"},
                    {"name": "current ratio", "value": 2.49, "unit": "x"},
                    {"name": "total debt", "value": 3027000000, "unit": "USD"},
                    {
                        "name": "cash and short term investments",
                        "value": 7572000000,
                        "unit": "USD",
                    },
                ]
            },
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "yfinance structured snapshot",
                    "snippet": "Structured yfinance cash flow and balance sheet metrics.",
                    "citation_status": "supported",
                }
            ],
        ),
    )
    payload = {
        "cash_quality_verdict": {
            "headline": "AMD cash quality is strong.",
            "earnings_backed_by_cash": "yes",
            "summary": "Operating cash flow covers earnings.",
        },
        "cash_metrics": [
            {
                "name": "Operating Cash Flow / Net Income",
                "value": "2.1x",
                "interpretation": "Cash conversion is strong.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            },
            {
                "name": "Free Cash Flow",
                "value": "$2.8B",
                "interpretation": "Free cash flow is positive.",
                "source_ids": ["src_1"],
                "citation_status": "supported",
            },
        ],
        "capital_allocation": {"liquidity": []},
        "allocation_discipline": [],
        "red_flags": [],
        "claims": [],
    }

    report = build_cash_flow_report_from_payload(request, state, payload)
    metric_names = [metric.name.lower() for metric in report.task_sections.cash_metrics]

    assert "net income" in metric_names
    assert "operating cash flow" in metric_names
    assert "capital expenditures" in metric_names
    assert "current ratio" in metric_names
    assert "total debt" in metric_names
    assert "cash and short term investments" in metric_names


def test_cash_flow_raw_yfinance_quarterly_facts_are_completed_as_core_metrics() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="BRK-B",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
    )
    state = AgentState(
        run_id="run_1",
        ticker="BRK-B",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
        evidence_memory=EvidenceMemory(
            facts={
                "ticker": "BRK-B",
                "companyName": "Berkshire Hathaway Inc.",
                "quarterlyFinancials": [
                    {
                        "periodEnd": "2026-03-31",
                        "netIncome": 12300000000,
                        "operatingCashFlow": 16000000000,
                        "capitalExpenditures": 1900000000,
                        "freeCashFlow": 14100000000,
                        "cashAndShortTermInvestments": 334000000000,
                        "currentAssets": 430000000000,
                        "currentLiabilities": 106000000000,
                        "totalDebt": 128000000000,
                    }
                ],
            },
            source_refs=[],
        ),
    )
    payload = {
        "cash_quality_verdict": {
            "headline": "Berkshire cash quality is resilient.",
            "earnings_backed_by_cash": "mixed",
            "summary": "Cash quality should be anchored in structured financial facts.",
        },
        "cash_metrics": [
            {
                "name": "Net income (latest quarter)",
                "value": "$12.3B",
                "interpretation": "Net income was reported in the latest quarter.",
                "source_ids": [],
                "citation_status": "supported",
            }
        ],
        "capital_allocation": {},
        "allocation_discipline": [],
        "red_flags": [],
        "claims": [],
    }

    report = build_cash_flow_report_from_payload(request, state, payload)
    metric_names = [metric.name.lower() for metric in report.task_sections.cash_metrics]

    assert metric_names == [
        "net income",
        "operating cash flow",
        "capital expenditures",
        "free cash flow",
        "current ratio",
        "total debt",
        "cash and short term investments",
    ]
    assert "net income (latest quarter)" not in metric_names
    current_ratio = next(
        metric
        for metric in report.task_sections.cash_metrics
        if metric.name.lower() == "current ratio"
    )
    assert current_ratio.value == "4.06x"
    assert report.task_sections.capital_allocation.capex
    assert report.task_sections.capital_allocation.debt
    assert report.task_sections.capital_allocation.liquidity


def test_cash_flow_empty_red_flags_are_backfilled_with_watch_next() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
    )
    state = AgentState(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
        evidence_memory=EvidenceMemory(
            facts={
                "metrics": [
                    {"name": "operating cash flow", "value": 28702000000, "unit": "USD"},
                    {"name": "capital expenditures", "value": 1971000000, "unit": "USD"},
                    {"name": "free cash flow", "value": 26731000000, "unit": "USD"},
                ]
            },
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "yfinance structured snapshot",
                    "snippet": "Structured yfinance cash flow metrics.",
                    "citation_status": "supported",
                }
            ],
        ),
    )
    payload = {
        "cash_quality_verdict": {
            "headline": "Cash quality is strong but not pristine.",
            "earnings_backed_by_cash": "mixed",
            "summary": "Cash generation is positive.",
        },
        "cash_metrics": [],
        "capital_allocation": {},
        "allocation_discipline": [],
        "red_flags": [],
        "claims": [],
    }

    report = build_cash_flow_report_from_payload(request, state, payload)

    assert report.task_sections.red_flags
    assert "Watch" in report.task_sections.red_flags[0].title


def test_cash_flow_fact_backfills_respect_chinese_locale() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
    )
    state = AgentState(
        run_id="run_1",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="zh",
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
        evidence_memory=EvidenceMemory(
            facts={
                "metrics": [
                    {"name": "operating cash flow", "value": 28702000000, "unit": "USD"},
                    {"name": "capital expenditures", "value": 1971000000, "unit": "USD"},
                    {"name": "free cash flow", "value": 26731000000, "unit": "USD"},
                    {"name": "total debt", "value": 98600000000, "unit": "USD"},
                    {
                        "name": "cash and short term investments",
                        "value": 53700000000,
                        "unit": "USD",
                    },
                    {"name": "current ratio", "value": 0.82, "unit": "ratio"},
                ]
            },
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "yfinance structured snapshot",
                    "snippet": "Structured yfinance cash flow metrics.",
                    "citation_status": "supported",
                }
            ],
        ),
    )
    payload = {
        "cash_quality_verdict": {
            "headline": "AAPL 现金质量稳健。",
            "earnings_backed_by_cash": "yes",
            "summary": "经营现金流和自由现金流均为正，现金生成能够支撑本季判断。",
        },
        "cash_metrics": [],
        "capital_allocation": {},
        "allocation_discipline": [],
        "red_flags": [],
        "claims": [],
    }

    report = build_cash_flow_report_from_payload(request, state, payload)

    sections = report.task_sections
    metric_names = [metric.name for metric in sections.cash_metrics]
    assert "经营现金流" in metric_names
    assert "自由现金流" in metric_names
    assert "资本开支" in metric_names
    assert "总债务" in metric_names
    assert "现金及短期投资" in metric_names
    assert "Operating Cash Flow" not in metric_names
    assert "Free Cash Flow" not in metric_names
    assert "Capital Expenditures" not in metric_names
    assert "Total Debt" not in metric_names

    visible_text = " ".join(
        [
            sections.cash_quality_verdict.summary,
            *(point.summary for point in sections.capital_allocation.capex),
            *(point.summary for point in sections.capital_allocation.debt),
            *(point.summary for point in sections.capital_allocation.liquidity),
            *(point.summary for point in sections.red_flags),
        ]
    )
    assert "was reported in structured financial facts" not in visible_text
    assert "Capex and reinvestment" not in visible_text
    assert "Debt load" not in visible_text
    assert "Balance sheet resilience" not in visible_text
    assert "Watch next cash signal" not in visible_text
    assert "Operating Cash Flow" not in visible_text
    assert "Free Cash Flow" not in visible_text
    assert "Capital Expenditures" not in visible_text
    assert "Current Ratio" not in visible_text
    assert "capex" not in visible_text.lower()
    assert "资本开支与再投资" in sections.capital_allocation.capex[0].title
    assert "债务负担" in sections.capital_allocation.debt[0].title
    assert "资产负债表韧性" in sections.capital_allocation.liquidity[0].title
    assert "观察下一季现金信号" in sections.red_flags[0].title


def test_cash_flow_unsupported_capital_points_are_removed_without_structured_metrics() -> None:
    request = AgentRequest(
        run_id="run_1",
        ticker="HD",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
    )
    state = AgentState(
        run_id="run_1",
        ticker="HD",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        language="en",
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
        evidence_memory=EvidenceMemory(
            facts={"metrics": []},
            source_refs=[
                {
                    "source_id": "src_1",
                    "section": "Financial Statements",
                    "snippet": "Evidence placeholder for net income.",
                    "citation_status": "unverified",
                }
            ],
        ),
    )
    payload = {
        "cash_quality_verdict": {
            "headline": "Cash quality is unverifiable.",
            "earnings_backed_by_cash": "unclear",
            "summary": "Structured cash flow evidence is missing.",
        },
        "cash_metrics": [],
        "capital_allocation": {
            "capex": [
                {
                    "title": "Capex placeholder",
                    "summary": "Capex appears manageable.",
                    "source_ids": ["src_1"],
                }
            ],
            "debt": [
                {
                    "title": "Debt placeholder",
                    "summary": "Debt appears manageable.",
                    "source_ids": ["src_1"],
                }
            ],
            "liquidity": [
                {
                    "title": "Liquidity placeholder",
                    "summary": "Liquidity appears adequate.",
                    "source_ids": ["src_1"],
                }
            ],
        },
        "allocation_discipline": [],
        "red_flags": [],
        "claims": [],
    }

    report = build_cash_flow_report_from_payload(request, state, payload)

    assert report.task_sections.capital_allocation.capex == []
    assert report.task_sections.capital_allocation.debt == []
    assert report.task_sections.capital_allocation.liquidity == []


def test_cash_flow_verdict_normalization_keeps_headline_complete_and_status_consistent() -> None:
    payload = _normalize_cash_flow_payload(
        {
            "cash_quality_verdict": {
                "headline": (
                    "Apple's cash quality is strong but not pristine. The company "
                    "generated $26.7B in free cash flow against $29.6B in net income."
                ),
                "earnings_backed_by_cash": "unclear",
                "summary": (
                    "Apple's cash quality is strong but not pristine. Free cash flow "
                    "covered most reported earnings, but operating cash flow trailed net income."
                ),
            },
            "cash_metrics": [],
            "capital_allocation": {},
            "allocation_discipline": [],
            "red_flags": [],
            "claims": [],
        }
    )

    verdict = payload["cash_quality_verdict"]
    assert verdict["headline"] == "Apple's cash quality is strong but not pristine."
    assert verdict["earnings_backed_by_cash"] == "mixed"


def test_cash_flow_verdict_normalization_overrides_conflicting_status() -> None:
    assert (
        _normalize_cash_flow_payload(
            {
                "cash_quality_verdict": {
                    "headline": "Exceptional cash quality.",
                    "earnings_backed_by_cash": "no",
                    "summary": "Exceptional cash quality and strong free cash flow conversion support earnings.",
                },
                "cash_metrics": [],
                "capital_allocation": {},
                "allocation_discipline": [],
                "red_flags": [],
                "claims": [],
            }
        )["cash_quality_verdict"]["earnings_backed_by_cash"]
        == "yes"
    )
    assert (
        _normalize_cash_flow_payload(
            {
                "cash_quality_verdict": {
                    "headline": "Oracle's cash quality is structurally strained.",
                    "earnings_backed_by_cash": "yes",
                    "summary": "Cash quality is structurally strained because capex and debt pressure free cash flow.",
                },
                "cash_metrics": [],
                "capital_allocation": {},
                "allocation_discipline": [],
                "red_flags": [],
                "claims": [],
            }
        )["cash_quality_verdict"]["earnings_backed_by_cash"]
        == "mixed"
    )
    assert (
        _normalize_cash_flow_payload(
            {
                "cash_quality_verdict": {
                    "earnings_backed_by_cash": "yes",
                    "summary": "Apple's cash quality is strong but not pristine.",
                },
                "cash_metrics": [],
                "capital_allocation": {},
                "allocation_discipline": [],
                "red_flags": [],
                "claims": [],
            }
        )["cash_quality_verdict"]["earnings_backed_by_cash"]
        == "mixed"
    )


def _make_request(task_type: ResearchTaskType, language: str) -> Any:
    return type(
        "Request",
        (),
        {
            "task_type": task_type,
            "ticker": "AAPL",
            "language": language,
            "run_id": "run_1",
        },
    )()
