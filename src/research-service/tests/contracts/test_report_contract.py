import pytest
from pydantic import ValidationError

from app.contracts.report import EvidenceAwareReport


def test_report_contract_rejects_unknown_task_type() -> None:
    with pytest.raises(ValidationError):
        EvidenceAwareReport.model_validate(
            {
                "run_id": "run_contract_001",
                "ticker": "TSLA",
                "task_type": "unknown_task",
                "sections": {},
                "claims": [],
            }
        )


def test_report_contract_requires_typed_task_sections() -> None:
    with pytest.raises(ValidationError):
        EvidenceAwareReport.model_validate(
            {
                "run_id": "run_contract_002",
                "ticker": "AAPL",
                "task_type": "business_driver_deep_dive",
                "sections": {},
                "claims": [],
            }
        )


def test_report_contract_accepts_business_driver_task_sections() -> None:
    report = EvidenceAwareReport.model_validate(
        {
            "run_id": "run_contract_003",
            "ticker": "AAPL",
            "task_type": "business_driver_deep_dive",
            "task_sections": {
                "schema_version": "task_sections.v1",
                "task_type": "business_driver_deep_dive",
                "coverage": {
                    "status": "complete",
                    "missing_sections": [],
                    "evidence_count": 1,
                },
                "driver_thesis": {
                    "headline": "Services drove growth",
                    "durability": "durable",
                    "summary": "Services growth appears durable.",
                },
                "driver_map": {
                    "product": [
                        {
                            "title": "Services",
                            "summary": "Services revenue increased.",
                            "evidence_refs": [],
                            "citation_status": "supported",
                        }
                    ],
                    "segment": [],
                    "geography": [],
                    "demand": [],
                    "pricing": [],
                    "customer": [],
                    "strategy": [],
                },
                "positive_signals": [],
                "negative_signals": [],
                "watchlist": ["Monitor Services adoption."],
            },
            "claims": [],
        }
    )

    assert report.task_sections.task_type == "business_driver_deep_dive"
