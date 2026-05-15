from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.contracts.agent import LlmProvider
from app.contracts.research_task import ResearchTaskType
from scripts.write_provider_report_synthesis_artifact import (
    ProviderReportSynthesisConfig,
    write_provider_report_synthesis_artifact,
)


def test_provider_report_synthesis_artifact_records_llm_final_report(
    tmp_path: Path,
) -> None:
    target = tmp_path / "provider-report-synthesis.json"

    write_provider_report_synthesis_artifact(
        target,
        config=ProviderReportSynthesisConfig(
            provider=LlmProvider.SILICONFLOW,
            model="test-synthesis-model",
            api_key="test-key",
        ),
        transport=_synthesis_transport,
    )

    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["stage"] == "stage_1_provider_report_synthesis"
    assert payload["provider"] == "siliconflow"
    assert payload["model"] == "test-synthesis-model"
    assert payload["synthesis"] == "llm"
    assert payload["finalReportTaskType"] == "latest_earnings_readout"
    assert payload["claimCount"] == 1
    assert payload["citedSourceIds"]
    assert payload["headline"] == "Provider synthesis turned evidence into a cited readout"


def test_provider_report_synthesis_artifact_supports_business_driver_task(
    tmp_path: Path,
) -> None:
    target = tmp_path / "provider-business-driver-synthesis.json"

    write_provider_report_synthesis_artifact(
        target,
        config=ProviderReportSynthesisConfig(
            provider=LlmProvider.SILICONFLOW,
            model="test-synthesis-model",
            api_key="test-key",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        ),
        transport=_business_driver_synthesis_transport,
    )

    payload = json.loads(target.read_text(encoding="utf-8"))

    assert payload["stage"] == "stage_1_provider_report_synthesis"
    assert payload["provider"] == "siliconflow"
    assert payload["model"] == "test-synthesis-model"
    assert payload["synthesis"] == "llm"
    assert payload["finalReportTaskType"] == "business_driver_deep_dive"
    assert payload["claimCount"] == 1
    assert payload["citedSourceIds"]
    assert payload["headline"] == "Services engagement is the main cited driver"


def _synthesis_transport(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, object]:
    source_id = _first_source_id_from_tool_messages(payload)
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(_synthesis_payload(source_id)),
                }
            }
        ],
        "usage": {"total_tokens": 100},
    }


def _business_driver_synthesis_transport(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, object]:
    source_id = _first_source_id_from_tool_messages(payload)
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(_business_driver_synthesis_payload(source_id)),
                }
            }
        ],
        "usage": {"total_tokens": 100},
    }


def _synthesis_payload(source_id: str) -> dict[str, Any]:
    return {
        "topline_verdict": {
            "headline": "Provider synthesis turned evidence into a cited readout",
            "summary": "The provider synthesized a cautious readout from one evidence point.",
            "verdict": "mixed",
        },
        "key_takeaways": [
            {
                "title": "Evidence-backed demand",
                "summary": "The cited filing section supports demand commentary.",
                "source_ids": [source_id],
                "citation_status": "supported",
            }
        ],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "Revenue",
                    "value": "Evidence-backed",
                    "interpretation": "Revenue context is tied to cited evidence.",
                    "source_ids": [source_id],
                    "citation_status": "supported",
                }
            ],
            "chart_focus": ["revenue"],
        },
        "driver_snapshot": [
            {
                "title": "Demand",
                "summary": "Demand is the cited driver.",
                "source_ids": [source_id],
                "citation_status": "supported",
            }
        ],
        "risk_snapshot": [
            {
                "title": "Evidence scope",
                "summary": "The synthesis remains cautious with one source.",
                "source_ids": [source_id],
                "citation_status": "partial",
            }
        ],
        "claims": [
            {
                "text": "Demand commentary supports a mixed readout.",
                "source_ids": [source_id],
                "citation_status": "supported",
            }
        ],
    }


def _business_driver_synthesis_payload(source_id: str) -> dict[str, Any]:
    return {
        "driver_thesis": {
            "headline": "Services engagement is the main cited driver",
            "durability": "mixed",
            "summary": "The provider tied the driver thesis to cited filing evidence.",
        },
        "driver_map": {
            "product": [
                {
                    "title": "Services",
                    "summary": "Services demand is supported by the cited filing section.",
                    "source_ids": [source_id],
                    "citation_status": "supported",
                }
            ],
            "segment": [],
            "geography": [],
            "demand": [
                {
                    "title": "Engagement",
                    "summary": "Engagement was cited as a demand driver.",
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
                "summary": "The evidence supports a positive demand signal.",
                "source_ids": [source_id],
                "citation_status": "supported",
            }
        ],
        "negative_signals": [],
        "watchlist": ["Track whether cited services demand persists."],
        "claims": [
            {
                "text": "Services engagement is a cited business driver.",
                "source_ids": [source_id],
                "citation_status": "supported",
            }
        ],
    }


def _first_source_id_from_tool_messages(payload: dict[str, object]) -> str:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        raise AssertionError("LLM payload messages are required")
    for message in reversed(messages):
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        if message.get("role") == "tool":
            source_id = _first_source_id_from_tool_payload(json.loads(content))
            if source_id:
                return source_id
        if message.get("role") == "user" and content.startswith("Evidence context JSON:"):
            evidence_context = json.loads(content.split("Evidence context JSON:", 1)[1])
            if isinstance(evidence_context, list):
                for item in evidence_context:
                    if not isinstance(item, dict):
                        continue
                    tool_content = item.get("content")
                    if isinstance(tool_content, dict):
                        source_id = _first_source_id_from_tool_payload(tool_content)
                        if source_id:
                            return source_id
    raise AssertionError("At least one source id is required")


def _first_source_id_from_tool_payload(tool_payload: dict[str, object]) -> str | None:
    for key in ("records", "retrieved_nodes", "source_refs"):
        records = tool_payload.get(key)
        if not isinstance(records, list):
            continue
        for record in records:
            if not isinstance(record, dict):
                continue
            source_id = record.get("source_id") or record.get("node_id")
            if source_id:
                return str(source_id)
    evidence_pack = tool_payload.get("evidence_pack")
    if isinstance(evidence_pack, dict):
        filing_evidence = evidence_pack.get("filing_evidence")
        if isinstance(filing_evidence, list):
            for record in filing_evidence:
                if isinstance(record, dict) and record.get("source_id"):
                    return str(record["source_id"])
    return None
