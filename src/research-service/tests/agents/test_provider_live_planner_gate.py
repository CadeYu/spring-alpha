from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.agents.llm_gateway import LlmProvider
from scripts.write_provider_live_planner_artifact import (
    ProviderLivePlannerConfig,
    assert_provider_live_planner_gate,
    write_provider_live_planner_artifact,
)


def test_provider_live_planner_artifact_records_happy_path_context(tmp_path: Path) -> None:
    target = tmp_path / "provider-live-planner.json"
    decisions = [
        {
            "decision": "call_tool",
            "summary": "Search filing evidence first.",
            "tool_name": "search_filing_sections",
            "tool_input": {"sections": ["MD&A"], "query": "revenue gross margin services"},
        },
        {
            "decision": "finalize",
            "summary": "Evidence is enough for this live planner smoke.",
        },
    ]

    write_provider_live_planner_artifact(
        target,
        config=ProviderLivePlannerConfig(
            provider=LlmProvider.SILICONFLOW,
            model="test-live-planner",
            api_key="test-key",
        ),
        transport=_sequence_transport(decisions),
        strict=False,
    )

    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["stage"] == "stage_1_provider_live_planner"
    assert payload["provider"] == "siliconflow"
    assert payload["model"] == "test-live-planner"
    assert payload["status"] == "ok"
    assert payload["plannerEventCount"] >= 2
    assert payload["fallbackCount"] == 0
    assert payload["providerDecisionCount"] >= 1
    assert payload["hasPlannerContext"] is True
    assert payload["stopReason"] == "planner_finalize"
    assert "search_filing_sections" in payload["toolNames"]
    assert payload["finalReportTaskType"] == "latest_earnings_readout"
    assert payload["events"][0]["planner_context"]["remaining_steps"] == 5


def test_provider_live_planner_artifact_records_disallowed_tool_fallback(
    tmp_path: Path,
) -> None:
    target = tmp_path / "provider-live-planner-fallback.json"
    decisions = [
        {
            "decision": "call_tool",
            "summary": "Try a disallowed business signal tool.",
            "tool_name": "get_business_signals",
            "tool_input": {"signal_types": ["demand"]},
        },
        {
            "decision": "finalize",
            "summary": "Fallback evidence is enough.",
        },
    ]

    write_provider_live_planner_artifact(
        target,
        config=ProviderLivePlannerConfig(
            provider=LlmProvider.SILICONFLOW,
            model="test-live-planner",
            api_key="test-key",
        ),
        transport=_sequence_transport(decisions),
        strict=False,
    )

    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["status"] == "degraded"
    assert payload["fallbackCount"] == 1
    assert payload["hasPlannerContext"] is True
    assert payload["stopReason"] == "planner_finalize"
    assert any("not allowed" in reason for reason in payload["degradedReasons"])
    assert payload["events"][0]["tool_name"] is None
    assert payload["events"][1]["tool_name"] == "get_company_facts"


def test_provider_live_planner_strict_gate_rejects_budget_exhaustion_without_evidence_tool() -> (
    None
):
    payload = {
        "stage": "stage_1_provider_live_planner",
        "provider": "siliconflow",
        "model": "test-live-planner",
        "status": "degraded",
        "eventCount": 16,
        "plannerEventCount": 5,
        "toolNames": ["get_company_facts"],
        "fallbackCount": 0,
        "providerDecisionCount": 5,
        "hasPlannerContext": True,
        "stopReason": "step_budget_exhausted",
        "elapsedMs": 1000,
        "finalReportTaskType": "latest_earnings_readout",
        "degradedReasons": ["Planner step budget exhausted after 5 steps."],
        "events": [],
    }

    try:
        assert_provider_live_planner_gate(payload, strict=True)
    except RuntimeError as exc:
        assert "must stop via planner finalize or coverage stop" in str(exc)
    else:
        raise AssertionError("strict provider live planner gate should reject budget exhaustion")


def test_provider_live_planner_strict_gate_rejects_all_fallback_runs() -> None:
    payload = {
        "stage": "stage_1_provider_live_planner",
        "provider": "siliconflow",
        "model": "test-live-planner",
        "status": "degraded",
        "eventCount": 17,
        "plannerEventCount": 9,
        "toolNames": ["get_company_facts", "search_filing_sections", "search_metric_evidence"],
        "fallbackCount": 4,
        "providerDecisionCount": 0,
        "hasPlannerContext": True,
        "stopReason": "coverage_stop",
        "elapsedMs": 1000,
        "finalReportTaskType": "latest_earnings_readout",
        "degradedReasons": ["Planner failed: The read operation timed out"],
        "events": [],
    }

    try:
        assert_provider_live_planner_gate(payload, strict=True)
    except RuntimeError as exc:
        assert "must accept at least one provider planner decision" in str(exc)
    else:
        raise AssertionError("strict provider live planner gate should reject all-fallback runs")


def test_provider_live_planner_writes_artifact_before_strict_gate_failure(
    tmp_path: Path,
) -> None:
    target = tmp_path / "provider-live-planner-failed.json"

    try:
        write_provider_live_planner_artifact(
            target,
            config=ProviderLivePlannerConfig(
                provider=LlmProvider.SILICONFLOW,
                model="test-live-planner",
                api_key="test-key",
            ),
            transport=_failing_transport,
        )
    except RuntimeError as exc:
        assert "must accept at least one provider planner decision" in str(exc)
    else:
        raise AssertionError("strict provider live planner gate should reject failed runs")

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["stage"] == "stage_1_provider_live_planner"
    assert payload["providerDecisionCount"] == 0


def _sequence_transport(
    decisions: list[dict[str, Any]],
) -> Any:
    calls: list[dict[str, object]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        index = min(len(calls) - 1, len(decisions) - 1)
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(decisions[index]),
                    }
                }
            ],
            "usage": {"total_tokens": 12},
        }

    return transport


def _failing_transport(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, object]:
    raise TimeoutError("provider timed out")
