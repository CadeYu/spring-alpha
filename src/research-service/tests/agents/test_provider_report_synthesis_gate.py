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
    assert payload["citedSourceIds"] == ["provider_report_synthesis_smoke:filing:1"]
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
    assert payload["citedSourceIds"] == ["provider_report_synthesis_smoke:filing:1"]
    assert payload["headline"] == "Services engagement is the main cited driver"


def _synthesis_transport(
    url: str,
    payload: dict[str, object],
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(_synthesis_payload()),
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
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(_business_driver_synthesis_payload()),
                }
            }
        ],
        "usage": {"total_tokens": 100},
    }


def _synthesis_payload() -> dict[str, Any]:
    source_id = "provider_report_synthesis_smoke:filing:1"
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


def _business_driver_synthesis_payload() -> dict[str, Any]:
    source_id = "provider_report_synthesis_smoke:filing:1"
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
