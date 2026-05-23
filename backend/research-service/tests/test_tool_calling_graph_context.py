from __future__ import annotations

import json

from langchain_core.messages import ToolMessage

from app.agents.tool_calling_graph import _evidence_context


def test_compact_evidence_context_deduplicates_evidence_pack_payload() -> None:
    long_snippet = "Operating cash flow and capital allocation evidence. " * 20
    payload = {
        "evidence_pack": {
            "run_id": "run_1",
            "ticker": "AAPL",
            "task_type": "cash_flow_capital_allocation",
            "query": "cash quality liquidity buybacks capex working capital " * 8,
            "filing_context": {
                "filing_type": "10-Q",
                "filing_date": "2026-04-30",
                "accession_number": "0001",
            },
            "metric_facts": [
                {
                    "source_type": "sec_companyfacts",
                    "metric": f"metric_{index}",
                    "value": 1000 + index,
                    "unit": "USD",
                    "period": "2026-Q1",
                }
                for index in range(6)
            ],
            "filing_evidence": [
                {
                    "source_id": f"src_{index}",
                    "source_type": "sec_filing",
                    "section": "Liquidity and Capital Resources",
                    "snippet": long_snippet,
                    "filing_type": "10-Q",
                    "filing_date": "2026-04-30",
                    "accession_number": "0001",
                    "score": 0.9,
                    "relevance_note": "cash flow match",
                }
                for index in range(5)
            ],
            "retrieval_status": "ok",
            "latency_ms": 123,
        },
        "source_refs": [
            {
                "source_id": f"src_{index}",
                "section": "Liquidity and Capital Resources",
                "snippet": long_snippet,
                "citation_status": "supported",
            }
            for index in range(5)
        ],
        "retrieved_nodes": [{"node_id": "node_1", "text": long_snippet * 2}],
    }

    context = _evidence_context(
        [
            ToolMessage(
                content=json.dumps(payload),
                tool_call_id="planned_1_build_evidence_pack",
                name="build_evidence_pack",
            )
        ],
        compact=True,
    )
    items = json.loads(context.removeprefix("Evidence context JSON:\n"))

    assert len(context) < 1800
    assert "source_refs" not in items[0]["content"]
    assert "retrieved_nodes" not in context
    assert len(items[0]["content"]["evidence_pack"]["filing_evidence"]) == 3
    assert all(
        len(item["snippet"]) <= 180
        for item in items[0]["content"]["evidence_pack"]["filing_evidence"]
    )
