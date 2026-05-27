from __future__ import annotations

from typing import Any

from app.agents.llm_gateway import LlmClient, LlmRequest, LlmResponse
from app.agents.report_synthesizer import (
    _business_driver_prompt,
    _cash_flow_prompt,
    _normalize_cash_flow_payload,
    _company_profile_system_prompt,
    _company_profile_user_prompt,
    _evidence_lines,
    _normalize_business_driver_payload,
    _sanitize_user_text,
    _system_prompt,
    _user_prompt,
    build_business_driver_report_from_payload,
    build_latest_earnings_report_from_payload,
    synthesize_latest_earnings_payload,
)
from app.contracts.agent import AgentState, CoverageState, EvidenceMemory, TaskPolicy
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
    assert _company_profile_system_prompt("en").startswith(
        "You write concise investor-facing"
    )
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
    assert sections.bull_bear_read.bull_case[0].title == (
        "Bull case: Services support mix"
    )
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
    assert all(
        point.citation_status == "partial" for point in points if point is not None
    )


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
                        "snippet": (
                            "| | | 6,402 | | | 15,509 | | | Services | Products | ---|---"
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
    assert all(
        ref.source_id != "src_bby_table"
        for ref in sections.segment_momentum.evidence_refs
    )
    assert sections.margin_and_mix is not None
    assert all(
        ref.source_id != "src_vz_footnote"
        for ref in sections.margin_and_mix.evidence_refs
    )
    assert sections.demand_signals is not None
    assert [ref.source_id for ref in sections.demand_signals.evidence_refs] == [
        "src_vz_clean"
    ]


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
    assert capex["summary"] == "Investor implication: Capex remains the main reinvestment use of cash."
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
