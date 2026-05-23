from __future__ import annotations

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents.tool_calling_graph import (
    _evidence_context,
    _invoke_and_parse_final_payload,
    _json_response_llm,
)


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


def test_compact_synthesis_keeps_enough_completion_budget_for_cash_flow_json() -> None:
    llm = _CopyableLlm(compact_synthesis=True)

    copied = _json_response_llm(llm)

    assert copied.update["max_tokens"] == 1536
    assert copied.update["response_format"] == {"type": "json_object"}
    assert copied.update["timeout_seconds"] == 24


def test_final_payload_retries_after_invalid_json() -> None:
    final_chain = _FlakyFinalChain(
        [
            AIMessage(content='{"driver_thesis": {"headline": "Growth'),
            AIMessage(
                content=(
                    '{"driver_thesis": {"headline": "Growth", '
                    '"summary": "Revenue improved."}}'
                )
            ),
        ]
    )

    final_result, payload = _invoke_and_parse_final_payload(
        final_chain=final_chain,
        final_messages=[HumanMessage(content="Return JSON only.")],
        attempts=2,
        agent_name="Business driver agent",
        raise_error=_raise_test_error,
    )

    assert final_chain.calls == 2
    assert isinstance(final_result, AIMessage)
    assert payload["driver_thesis"]["summary"] == "Revenue improved."


def test_final_payload_does_not_retry_after_provider_timeout() -> None:
    final_chain = _FlakyFinalChain(
        [
            TimeoutError("The read operation timed out"),
            AIMessage(
                content=(
                    '{"cash_quality_verdict": '
                    '{"summary": "Cash generation recovered."}}'
                )
            ),
        ]
    )

    try:
        _invoke_and_parse_final_payload(
            final_chain=final_chain,
            final_messages=[HumanMessage(content="Return JSON only.")],
            attempts=2,
            agent_name="Cash flow agent",
            raise_error=_raise_test_error,
        )
    except AssertionError as error:
        assert "timed out" in str(error)
    else:
        raise AssertionError("expected timeout to stop final synthesis retries")

    assert final_chain.calls == 1


class _CopyableLlm:
    def __init__(
        self,
        *,
        compact_synthesis: bool,
        update: dict[str, object] | None = None,
    ) -> None:
        self.compact_synthesis = compact_synthesis
        self.update = update or {}

    def model_copy(self, *, update: dict[str, object]) -> _CopyableLlm:
        return _CopyableLlm(
            compact_synthesis=self.compact_synthesis,
            update=update,
        )


class _FlakyFinalChain:
    def __init__(self, results: list[object]) -> None:
        self.results = results
        self.calls = 0

    def invoke(self, payload: dict[str, object]) -> object:
        del payload
        result = self.results[self.calls]
        self.calls += 1
        if isinstance(result, Exception):
            raise result
        return result


def _raise_test_error(message: str) -> None:
    raise AssertionError(message)
