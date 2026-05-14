import json

from scripts.write_live_agent_quality_artifact import (
    quality_flags_for_report,
    summarize_evidence_pack,
)


def test_summarize_evidence_pack_reports_budget_and_metric_sources() -> None:
    pack = {
        "metric_facts": [
            {"source_type": "sec_companyfacts", "metric": "revenue"},
            {"source_type": "metric_evidence", "metric": "revenue"},
            {"source_type": "yahoo_profile", "company_name": "Apple Inc."},
        ],
        "filing_evidence": [
            {"snippet": "A" * 10},
            {"snippet": "B" * 20},
        ],
    }
    summary = summarize_evidence_pack(
        {
            "evidence_pack": pack,
        }
    )

    assert summary == {
        "filingEvidenceCount": 2,
        "metricFactCount": 3,
        "metricFactSourceTypes": {
            "metric_evidence": 1,
            "sec_companyfacts": 1,
            "yahoo_profile": 1,
        },
        "serializedLength": len(json.dumps(pack, sort_keys=True)),
        "snippetCharCount": 30,
    }


def test_quality_flags_for_report_catches_empty_and_generic_output() -> None:
    flags = quality_flags_for_report(
        {
            "task_sections": {
                "task_type": "business_driver_deep_dive",
                "driver_thesis": {
                    "headline": "N/A",
                    "summary": "This is important for investors.",
                    "durability": "unclear",
                },
                "driver_map": {
                    "product": [],
                    "segment": [],
                    "geography": [],
                    "demand": [],
                    "pricing": [],
                    "customer": [],
                    "strategy": [],
                },
                "positive_signals": [],
                "negative_signals": [],
                "watchlist": [],
            },
            "claims": [],
        }
    )

    assert "no_claims" in flags
    assert "empty_driver_map" in flags
    assert "placeholder_text" in flags
    assert "generic_investor_language" in flags


def test_quality_flags_do_not_flag_legitimate_evidence_point_phrase() -> None:
    flags = quality_flags_for_report(
        {
            "task_sections": {
                "task_type": "business_driver_deep_dive",
                "driver_thesis": {
                    "headline": "Cloud demand is durable",
                    "summary": "The evidence points to durable cloud demand.",
                    "durability": "durable",
                },
                "driver_map": {
                    "product": [{"title": "Cloud", "summary": "Cloud demand improved."}],
                    "segment": [],
                    "geography": [],
                    "demand": [],
                    "pricing": [],
                    "customer": [],
                    "strategy": [],
                },
                "positive_signals": [],
                "negative_signals": [],
                "watchlist": ["Watch capex conversion."],
            },
            "claims": [{"text": "Cloud demand improved."}],
        }
    )

    assert "placeholder_text" not in flags


def test_quality_flags_ignore_source_excerpt_placeholder_language() -> None:
    flags = quality_flags_for_report(
        {
            "task_sections": {
                "task_type": "cash_flow_capital_allocation",
                "cash_quality_verdict": {
                    "headline": "Cash flow is strong",
                    "earnings_backed_by_cash": "yes",
                    "summary": "Operating cash flow funded capital returns.",
                },
                "cash_metrics": [
                    {
                        "name": "Operating cash flow",
                        "value": "$10.0B",
                        "period": "latest_quarter",
                        "interpretation": "Cash conversion remained strong.",
                        "evidence_refs": [
                            {
                                "section": "SEC companyfacts",
                                "excerpt": "A raw source excerpt says not available.",
                            }
                        ],
                        "citation_status": "supported",
                    }
                ],
                "capital_allocation": {
                    "capex": [],
                    "buybacks": [{"title": "Buybacks", "summary": "Repurchases were funded."}],
                    "dividends": [],
                    "debt": [],
                    "liquidity": [],
                },
                "allocation_discipline": [],
                "red_flags": [],
            },
            "claims": [{"text": "Cash conversion remained strong."}],
            "retrieval_records": [{"raw": "placeholder from diagnostic record"}],
        }
    )

    assert "placeholder_text" not in flags
