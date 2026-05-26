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
