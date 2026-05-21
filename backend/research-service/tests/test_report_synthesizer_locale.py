from __future__ import annotations

from typing import Any

from app.agents.llm_gateway import LlmClient, LlmRequest, LlmResponse
from app.agents.report_synthesizer import (
    _business_driver_prompt,
    _cash_flow_prompt,
    _company_profile_system_prompt,
    _company_profile_user_prompt,
    _sanitize_user_text,
    _system_prompt,
    _user_prompt,
    synthesize_latest_earnings_payload,
)
from app.contracts.agent import AgentState, CoverageState, EvidenceMemory, TaskPolicy
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
