from __future__ import annotations

from typing import Any

from app.agents import business_driver_agent
from app.agents.business_driver_agent import _business_driver_instruction, run_business_driver_agent
from app.contracts.agent import AgentRequest, AgentState, EvidenceMemory, TaskPolicy
from app.contracts.research_task import ResearchTaskType


def test_business_driver_instruction_includes_structured_facts_brief() -> None:
    request = _make_request(language="zh")
    state = _make_state(language="zh").model_copy(
        update={
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
                business_signals=[
                    {
                        "summary": "Data center accelerator demand remained a key signal.",
                    }
                ],
            )
        }
    )

    instruction = _business_driver_instruction(request, state)

    assert "Business driver facts brief:" in instruction
    assert "Financial facts brief:" in instruction
    assert "Advanced Micro Devices, Inc." in instruction
    assert "revenue: $7.4B" in instruction
    assert "gross margin: 52.0%" in instruction
    assert "Data center accelerator demand remained a key signal." in instruction
    assert "不要输出 No evidence、无法判断 或类似占位句" in instruction


def test_business_driver_agent_requests_margin_and_profitability_metrics(
    monkeypatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_graph_agent(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "driver_thesis": {
                "headline": "Growth needs margin context.",
                "durability": "mixed",
                "summary": "Growth needs margin context.",
            },
            "driver_map": {},
            "claims": [],
        }

    monkeypatch.setattr(
        business_driver_agent,
        "run_tool_calling_graph_agent",
        fake_graph_agent,
    )

    run_business_driver_agent(
        request=_make_request(language="en"),
        state=_make_state(language="en"),
        llm=object(),  # type: ignore[arg-type]
        tool_service=object(),  # type: ignore[arg-type]
    )

    planned_calls = captured["planned_tool_calls"]
    assert any(call["name"] == "get_market_context" for call in planned_calls)
    metric_call = next(call for call in planned_calls if call["name"] == "search_metric_evidence")
    assert metric_call["args"]["metrics"] == [
        "revenue",
        "segment revenue",
        "gross margin",
        "operating margin",
        "operating income",
        "net income",
    ]
    facts_call = next(call for call in planned_calls if call["name"] == "get_company_facts")
    assert facts_call["args"]["metrics"] == [
        "revenue",
        "gross margin",
        "operating margin",
        "operating income",
        "net income",
    ]


def _make_request(language: str) -> AgentRequest:
    return AgentRequest(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language=language,
    )


def _make_state(language: str) -> AgentState:
    return AgentState(
        run_id="run_1",
        ticker="AMD",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language=language,
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            allowed_tools=[
                "search_filing_sections",
                "search_metric_evidence",
                "get_business_signals",
            ],
            required_outputs=["driverThesis", "driverMap"],
        ),
    )
