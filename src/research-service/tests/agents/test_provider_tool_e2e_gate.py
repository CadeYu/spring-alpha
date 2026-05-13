from __future__ import annotations

import json
from pathlib import Path

from app.contracts.agent import LlmProvider
from app.contracts.research_task import ResearchTaskType
from scripts.write_provider_tool_e2e_artifact import (
    ProviderToolE2EConfig,
    assert_provider_tool_e2e_gate,
    write_provider_tool_e2e_artifact,
)


def test_provider_tool_e2e_gate_supports_business_driver_signals(tmp_path: Path) -> None:
    target = tmp_path / "provider-tool-business-driver.json"

    write_provider_tool_e2e_artifact(
        target,
        config=ProviderToolE2EConfig(
            provider=LlmProvider.SILICONFLOW,
            model="test-tool-model",
            api_key="test-key",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        ),
        synthesis_transport=_business_driver_synthesis_transport,
    )

    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["stage"] == "stage_1_provider_tool_e2e"
    assert payload["provider"] == "siliconflow"
    assert payload["model"] == "test-tool-model"
    assert payload["status"] == "ok"
    assert payload["synthesis"] == "llm"
    assert payload["finalReportTaskType"] == "business_driver_deep_dive"
    assert payload["ragSourceRefCount"] > 0
    assert payload["signalCount"] > 0
    assert "get_business_signals" in payload["toolNames"]


def test_provider_tool_e2e_gate_rejects_business_driver_without_signals() -> None:
    payload = {
        "stage": "stage_1_provider_tool_e2e",
        "status": "ok",
        "synthesis": "llm",
        "finalReportTaskType": "business_driver_deep_dive",
        "ragSourceRefCount": 1,
        "signalCount": 0,
        "toolNames": ["search_filing_sections"],
    }

    try:
        assert_provider_tool_e2e_gate(payload)
    except RuntimeError as exc:
        assert str(exc) == "provider tool E2E returned no business signals"
    else:
        raise AssertionError("business driver provider tool gate should require signals")


def test_provider_tool_e2e_gate_supports_cash_flow_synthesis(tmp_path: Path) -> None:
    target = tmp_path / "provider-tool-cash-flow.json"

    write_provider_tool_e2e_artifact(
        target,
        config=ProviderToolE2EConfig(
            provider=LlmProvider.SILICONFLOW,
            model="test-tool-model",
            api_key="test-key",
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        ),
        synthesis_transport=_cash_flow_synthesis_transport,
    )

    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["stage"] == "stage_1_provider_tool_e2e"
    assert payload["status"] == "ok"
    assert payload["synthesis"] == "llm"
    assert payload["finalReportTaskType"] == "cash_flow_capital_allocation"
    assert payload["factSource"] == "sec_companyfacts"
    assert payload["factMetricCount"] > 0
    assert payload["ragSourceRefCount"] > 0
    assert payload["metricEvidenceCount"] > 0
    assert "search_metric_evidence" in payload["toolNames"]


def test_provider_tool_e2e_gate_rejects_cash_flow_without_metric_evidence() -> None:
    payload = {
        "stage": "stage_1_provider_tool_e2e",
        "status": "ok",
        "synthesis": "llm",
        "finalReportTaskType": "cash_flow_capital_allocation",
        "factSource": "sec_companyfacts",
        "factMetricCount": 1,
        "ragSourceRefCount": 1,
        "metricEvidenceCount": 0,
        "toolNames": ["get_company_facts", "search_filing_sections"],
    }

    try:
        assert_provider_tool_e2e_gate(payload)
    except RuntimeError as exc:
        assert str(exc) == "provider tool E2E returned no metric evidence"
    else:
        raise AssertionError("cash flow provider tool gate should require metric evidence")


def _business_driver_synthesis_transport(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, object]:
    source_id = _first_allowed_source_id(payload)
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "driver_thesis": {
                                "headline": "Services demand is the cited driver",
                                "durability": "mixed",
                                "summary": (
                                    "The report ties services demand and engagement "
                                    "to filing evidence."
                                ),
                            },
                            "driver_map": {
                                "product": [
                                    {
                                        "title": "Services",
                                        "summary": "Services revenue is cited as a driver.",
                                        "source_ids": [source_id],
                                        "citation_status": "supported",
                                    }
                                ],
                                "segment": [],
                                "geography": [],
                                "demand": [
                                    {
                                        "title": "Engagement",
                                        "summary": "Engagement expansion supports demand.",
                                        "source_ids": [source_id],
                                        "citation_status": "supported",
                                    }
                                ],
                                "pricing": [],
                                "customer": [],
                                "strategy": [],
                            },
                            "positive_signals": [
                                {
                                    "title": "Demand",
                                    "summary": "Demand improved in the cited filing section.",
                                    "source_ids": [source_id],
                                    "citation_status": "supported",
                                }
                            ],
                            "negative_signals": [],
                            "watchlist": ["Track whether engagement remains durable."],
                            "claims": [
                                {
                                    "text": "Services demand is supported by cited evidence.",
                                    "source_ids": [source_id],
                                    "citation_status": "supported",
                                }
                            ],
                        }
                    ),
                }
            }
        ],
        "usage": {"total_tokens": 100},
    }


def _cash_flow_synthesis_transport(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, object]:
    source_id = _first_allowed_source_id(payload)
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "cash_quality_verdict": {
                                "headline": "Operating cash flow funds capital returns",
                                "earnings_backed_by_cash": "mixed",
                                "summary": (
                                    "The cited evidence links operating cash flow to "
                                    "capex and buybacks."
                                ),
                            },
                            "cash_metrics": [
                                {
                                    "name": "Operating cash flow",
                                    "value": "Evidence-backed",
                                    "period": "latest_quarter",
                                    "interpretation": (
                                        "Operating cash flow is grounded in cited evidence."
                                    ),
                                    "source_ids": [source_id],
                                    "citation_status": "supported",
                                }
                            ],
                            "capital_allocation": {
                                "capex": [
                                    {
                                        "title": "Capex",
                                        "summary": "Capex was cited as a use of cash.",
                                        "source_ids": [source_id],
                                        "citation_status": "supported",
                                    }
                                ],
                                "buybacks": [
                                    {
                                        "title": "Buybacks",
                                        "summary": "Buybacks were cited as capital returns.",
                                        "source_ids": [source_id],
                                        "citation_status": "supported",
                                    }
                                ],
                                "dividends": [],
                                "debt": [],
                                "liquidity": [],
                            },
                            "allocation_discipline": [
                                {
                                    "title": "Cash discipline",
                                    "summary": "Capital returns were funded by cash flow.",
                                    "source_ids": [source_id],
                                    "citation_status": "supported",
                                }
                            ],
                            "red_flags": [],
                            "claims": [
                                {
                                    "text": "Operating cash flow funded capex and buybacks.",
                                    "source_ids": [source_id],
                                    "citation_status": "supported",
                                }
                            ],
                        }
                    ),
                }
            }
        ],
        "usage": {"total_tokens": 100},
    }


def _first_allowed_source_id(payload: dict[str, object]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise AssertionError("LLM payload messages are required")
    for message in reversed(messages):
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        payload = json.loads(content)
        for key in ("records", "retrieved_nodes"):
            records = payload.get(key)
            if not isinstance(records, list):
                continue
            for record in records:
                if not isinstance(record, dict):
                    continue
                source_id = record.get("source_id") or record.get("node_id")
                if source_id:
                    return str(source_id)
    raise AssertionError("At least one source id is required")
