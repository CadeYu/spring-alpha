import json
from typing import Any

from app.agents.domain_tools import (
    LlamaIndexResearchToolService,
    SecCompanyFactsProvider,
    YahooCompanyProfileProvider,
)
from app.agents.llm_gateway import OpenAiCompatibleLlmClient
from app.agents.research_workflow import ResearchAgentWorkflow
from app.contracts.agent import (
    AgentRequest,
    AgentRunStatus,
    AgentState,
    LlmProvider,
    default_task_policy,
)
from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline


def test_cash_flow_agent_uses_langgraph_tool_workflow() -> None:
    calls: list[dict[str, object]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        tool_messages = _tool_messages(payload)
        if "tools" not in payload:
            source_id = _first_source_id_from_calls(calls)
            return _content_response(
                {
                    "cash_quality_verdict": {
                        "headline": "Cash generation supports the earnings base",
                        "earnings_backed_by_cash": "yes",
                        "summary": (
                            "Operating cash flow evidence supports the reported earnings base."
                        ),
                    },
                    "cash_metrics": [
                        {
                            "name": "Operating Cash Flow",
                            "value": "$32.0B",
                            "period": "latest_quarter",
                            "interpretation": "Cash generation remained healthy.",
                            "source_ids": [source_id],
                            "citation_status": "supported",
                        }
                    ],
                    "capital_allocation": {
                        "capex": [],
                        "buybacks": [],
                        "dividends": [],
                        "debt": [],
                        "liquidity": [],
                    },
                    "allocation_discipline": [],
                    "red_flags": [],
                    "claims": [
                        {
                            "text": "Cash generation supports the earnings base.",
                            "source_ids": [source_id],
                            "citation_status": "supported",
                        }
                    ],
                }
            )
        if not tool_messages:
            return _tool_call_response(
                "call_facts",
                "get_company_facts",
                {
                    "metrics": [
                        "operating cash flow",
                        "capital expenditures",
                        "buybacks",
                    ]
                },
            )
        if len(tool_messages) == 1:
            return _tool_call_response(
                "call_filing",
                "search_filing_sections",
                {
                    "sections": ["Liquidity and Capital Resources", "Cash Flow Statement"],
                    "query": "operating cash flow capex buybacks dividends debt liquidity",
                    "limit": 5,
                },
            )
        if len(tool_messages) == 2:
            return _tool_call_response(
                "call_metrics",
                "search_metric_evidence",
                {
                    "metrics": ["operating cash flow", "capital expenditures"],
                    "query": "operating cash flow capital expenditures buybacks",
                },
            )
        raise AssertionError("unexpected tool planning request")

    result = _workflow(transport).run(_cash_flow_request("run_cash_graph"))

    assert len(calls) == 1
    assert "tools" not in calls[-1]
    assert result.status == AgentRunStatus.OK
    assert result.final_report is not None
    assert result.final_report["sections"]["synthesis"] == "llm"
    assert result.final_report["task_sections"]["cash_quality_verdict"]["headline"] == (
        "Cash generation supports the earnings base"
    )
    assert [event.tool_name for event in result.events if event.tool_name] == [
        "get_company_facts",
        "search_metric_evidence",
        "build_evidence_pack",
    ]
    assert any(event.event_kind == "reasoning" for event in result.events)
    evidence_context = _evidence_context_from_final_payload(calls[-1])
    evidence_pack = _tool_content(evidence_context, "build_evidence_pack")["evidence_pack"]
    metric_facts = evidence_pack["metric_facts"]
    assert any(
        fact["source_type"] == "sec_companyfacts"
        and fact["metric"] == "operating cash flow"
        and fact["value"] == 32000000000
        for fact in metric_facts
    )
    assert any(
        fact["source_type"] == "sec_companyfacts"
        and fact["metric"] == "capital expenditures"
        and fact["value"] == 3000000000
        for fact in metric_facts
    )
    assert any(
        fact["source_type"] == "metric_evidence"
        and fact["metric"] == "buybacks"
        and fact["source_id"].endswith(":sec_companyfacts:buybacks")
        for fact in metric_facts
    )
    assert any(
        fact["source_type"] == "yahoo_profile"
        and fact["business_summary"].startswith("Apple designs consumer devices")
        and fact["sector"] == "Technology"
        for fact in metric_facts
    )


def test_cash_flow_agent_uses_standard_timeout_for_final_synthesis() -> None:
    calls: list[dict[str, object]] = []
    final_timeouts: list[int] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        tool_messages = _tool_messages(payload)
        if "tools" not in payload:
            final_timeouts.append(timeout_seconds)
            source_id = _first_source_id_from_calls(calls)
            return _content_response(
                {
                    "cash_quality_verdict": {
                        "headline": "Cash conversion is durable",
                        "earnings_backed_by_cash": "yes",
                        "summary": "Cash conversion supports the investment case.",
                    },
                    "cash_metrics": [
                        {
                            "name": "Operating Cash Flow",
                            "value": "$32.0B",
                            "period": "latest_quarter",
                            "interpretation": "Operating cash flow remained resilient.",
                            "source_ids": [source_id],
                            "citation_status": "supported",
                        }
                    ],
                    "capital_allocation": {
                        "capex": [],
                        "buybacks": [],
                        "dividends": [],
                        "debt": [],
                        "liquidity": [],
                    },
                    "allocation_discipline": [],
                    "red_flags": [],
                    "claims": [],
                }
            )
        if not tool_messages:
            return _tool_call_response("call_facts", "get_company_facts", {})
        if len(tool_messages) == 1:
            return _tool_call_response(
                "call_filing",
                "search_filing_sections",
                {
                    "sections": ["Liquidity and Capital Resources"],
                    "query": "operating cash flow capex buybacks liquidity",
                },
            )
        if len(tool_messages) == 2:
            return _tool_call_response("call_metrics", "search_metric_evidence", {})
        raise AssertionError("unexpected tool planning request")

    result = _workflow(transport).run(_cash_flow_request("run_cash_standard_timeout"))

    assert result.status == AgentRunStatus.OK
    assert final_timeouts == [75]
    assert calls[-1]["max_tokens"] == 4096


def test_cash_flow_agent_retries_when_final_json_is_invalid() -> None:
    calls: list[dict[str, object]] = []
    final_attempts = 0

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        nonlocal final_attempts
        calls.append(payload)
        tool_messages = _tool_messages(payload)
        if "tools" not in payload:
            final_attempts += 1
            if final_attempts == 1:
                return {
                    "choices": [
                        {"message": {"content": '{"cash_quality_verdict":{"headline":"Cash'}}
                    ]
                }
            source_id = _first_source_id_from_calls(calls)
            return _content_response(
                {
                    "cash_quality_verdict": {
                        "headline": "Cash generation supports the earnings base",
                        "earnings_backed_by_cash": "yes",
                        "summary": "Operating cash flow evidence supports reported earnings.",
                    },
                    "cash_metrics": [
                        {
                            "name": "Operating Cash Flow",
                            "value": "$32.0B",
                            "period": "latest_quarter",
                            "interpretation": "Cash generation remained healthy.",
                            "source_ids": [source_id],
                            "citation_status": "supported",
                        }
                    ],
                    "capital_allocation": {
                        "capex": [],
                        "buybacks": [],
                        "dividends": [],
                        "debt": [],
                        "liquidity": [],
                    },
                    "allocation_discipline": [],
                    "red_flags": [],
                    "claims": [
                        {
                            "text": "Cash generation supports the earnings base.",
                            "source_ids": [source_id],
                            "citation_status": "supported",
                        }
                    ],
                }
            )
        if not tool_messages:
            return _tool_call_response("call_facts", "get_company_facts", {})
        if len(tool_messages) == 1:
            return _tool_call_response(
                "call_filing",
                "search_filing_sections",
                {
                    "sections": ["Liquidity and Capital Resources"],
                    "query": "operating cash flow capex buybacks liquidity",
                },
            )
        if len(tool_messages) == 2:
            return _tool_call_response("call_metrics", "search_metric_evidence", {})
        raise AssertionError("unexpected tool planning request")

    result = _workflow(transport).run(_cash_flow_request("run_cash_json_retry"))

    assert final_attempts == 2
    assert result.status == AgentRunStatus.OK
    assert result.final_report is not None
    assert result.final_report["task_sections"]["cash_quality_verdict"]["headline"] == (
        "Cash generation supports the earnings base"
    )


def test_cash_flow_agent_retries_when_final_synthesis_times_out() -> None:
    calls: list[dict[str, object]] = []
    final_attempts = 0

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        nonlocal final_attempts
        calls.append(payload)
        tool_messages = _tool_messages(payload)
        if "tools" not in payload:
            final_attempts += 1
            if final_attempts == 1:
                raise TimeoutError("final synthesis timeout")
            source_id = _first_source_id_from_calls(calls)
            return _content_response(
                {
                    "cash_quality_verdict": {
                        "headline": "Cash generation recovered after retry",
                        "earnings_backed_by_cash": "yes",
                        "summary": "Operating cash flow evidence supports the cash view.",
                    },
                    "cash_metrics": [
                        {
                            "name": "Operating Cash Flow",
                            "value": "$32.0B",
                            "period": "latest_quarter",
                            "interpretation": "Cash generation remained healthy.",
                            "source_ids": [source_id],
                            "citation_status": "supported",
                        }
                    ],
                    "capital_allocation": {
                        "capex": [],
                        "buybacks": [],
                        "dividends": [],
                        "debt": [],
                        "liquidity": [],
                    },
                    "allocation_discipline": [],
                    "red_flags": [],
                    "claims": [],
                }
            )
        if not tool_messages:
            return _tool_call_response("call_facts", "get_company_facts", {})
        if len(tool_messages) == 1:
            return _tool_call_response("call_metrics", "search_metric_evidence", {})
        if len(tool_messages) == 2:
            return _tool_call_response(
                "call_pack",
                "build_evidence_pack",
                {"focus": "operating cash flow capex buybacks liquidity", "top_k": 5},
            )
        raise AssertionError("unexpected tool planning request")

    result = _workflow(transport).run(_cash_flow_request("run_cash_timeout_retry"))

    assert final_attempts == 2
    assert result.status == AgentRunStatus.OK
    assert result.final_report is not None
    assert result.final_report["task_sections"]["cash_quality_verdict"]["headline"] == (
        "Cash generation recovered after retry"
    )


def test_cash_flow_agent_keeps_completed_report_ok_when_evidence_is_partial() -> None:
    calls: list[dict[str, object]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        if "tools" not in payload:
            source_id = _first_source_id_from_calls(calls)
            return _content_response(
                {
                    "cash_quality_verdict": {
                        "headline": "Cash generation is investable despite thin evidence",
                        "earnings_backed_by_cash": "mixed",
                        "summary": "Operating cash flow evidence is usable, while missing buyback facts limit allocation confidence.",
                    },
                    "cash_metrics": [
                        {
                            "name": "Operating Cash Flow",
                            "value": "$32.0B",
                            "period": "latest_quarter",
                            "interpretation": "Operating cash flow anchors the cash quality view.",
                            "source_ids": [source_id],
                            "citation_status": "supported",
                        }
                    ],
                    "capital_allocation": {
                        "capex": [],
                        "buybacks": [],
                        "dividends": [],
                        "debt": [],
                        "liquidity": [],
                    },
                    "allocation_discipline": [],
                    "red_flags": [],
                    "claims": [],
                }
            )
        raise AssertionError("planned cash flow graph should not call tool-planning LLM")

    workflow = ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            LlamaIndexRagPipeline(),
            facts_provider=SecCompanyFactsProvider(
                transport=_fake_sec_transport_without_buybacks,
                profile_provider=YahooCompanyProfileProvider(transport=_fake_yahoo_transport),
            ),
        ),
        llm_client=OpenAiCompatibleLlmClient(
            LlmProvider.SILICONFLOW,
            api_key="secret",
            base_url="https://example.test/v1",
            transport=transport,
        ),
        rag_pipeline=LlamaIndexRagPipeline(),
    )

    result = workflow.run(_cash_flow_request("run_cash_partial_evidence"))

    assert result.final_report is not None
    assert result.status == AgentRunStatus.OK
    assert result.retryable is False
    assert any("missing metrics" in reason for reason in result.degraded_reasons)
    assert any(event.status == "partial" for event in result.events)


def test_cash_flow_agent_returns_transparent_partial_state_when_final_llm_fails() -> None:
    calls: list[dict[str, object]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        if "tools" not in payload:
            raise TimeoutError("provider timed out during final cash flow synthesis")
        tool_messages = _tool_messages(payload)
        if not tool_messages:
            return _tool_call_response(
                "call_facts",
                "get_company_facts",
                {"metrics": ["operating cash flow", "capital expenditures", "buybacks"]},
            )
        if len(tool_messages) == 1:
            return _tool_call_response(
                "call_filing",
                "search_filing_sections",
                {
                    "sections": ["Liquidity and Capital Resources"],
                    "query": "operating cash flow capex buybacks liquidity",
                },
            )
        if len(tool_messages) == 2:
            return _tool_call_response(
                "call_metrics",
                "search_metric_evidence",
                {"metrics": ["operating cash flow", "capital expenditures"]},
            )
        raise AssertionError("unexpected tool planning request")

    result = _workflow(transport).run(_cash_flow_request("run_cash_partial"))

    assert len(calls) == 2
    assert result.status == AgentRunStatus.DEGRADED
    assert result.final_report is None
    assert "provider timed out during final cash flow synthesis" in result.degraded_reasons[0]
    assert result.retryable is True
    assert len(result.retrieval_records) == 3
    assert [event.tool_name for event in result.events if event.tool_name] == [
        "get_company_facts",
        "search_metric_evidence",
        "build_evidence_pack",
    ]
    assert result.events[-1].phase == "degraded"


def test_cash_flow_final_prompt_requires_investment_memo_quality_structure() -> None:
    from app.agents.cash_flow_agent import _final_cash_flow_instruction

    instruction = _final_cash_flow_instruction(
        _cash_flow_request("run_cash_prompt"),
        AgentState(
            run_id="run_cash_prompt",
            ticker="AAPL",
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
            task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
        ),
    )
    normalized_instruction = instruction.lower()

    for expected in (
        "investment memo",
        "counter-evidence",
        "what would change the conclusion",
        "so what",
        "source_ids",
    ):
        assert expected in normalized_instruction
    assert "debate" not in normalized_instruction


def _workflow(transport: Any) -> ResearchAgentWorkflow:
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000001",
            text="""
Liquidity and Capital Resources
Net cash provided by operating activities improved as cash collections remained strong.
Cash Flow Statement
Capital expenditures and share repurchases were managed within the capital return program.
""",
        )
    )
    return ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            pipeline,
            facts_provider=SecCompanyFactsProvider(
                transport=_fake_sec_transport,
                profile_provider=YahooCompanyProfileProvider(transport=_fake_yahoo_transport),
            ),
        ),
        llm_client=OpenAiCompatibleLlmClient(
            LlmProvider.SILICONFLOW,
            api_key="secret",
            base_url="https://example.test/v1",
            transport=transport,
        ),
        rag_pipeline=pipeline,
    )


def _cash_flow_request(run_id: str, model: str = "test-model") -> AgentRequest:
    return AgentRequest(
        run_id=run_id,
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model=model,
        llm_api_key="secret",
    )


def _tool_messages(payload: dict[str, object]) -> list[object]:
    messages = payload["messages"]
    assert isinstance(messages, list)
    return [
        message
        for message in messages
        if isinstance(message, dict) and message.get("role") == "tool"
    ]


def _first_source_id(tool_messages: list[object]) -> str:
    for message in tool_messages:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        payload = json.loads(content)
        for key in ("retrieved_nodes", "records"):
            values = payload.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                if isinstance(value, dict) and value.get("source_id"):
                    return str(value["source_id"])
    raise AssertionError("No source id found in tool messages")


def _first_source_id_from_calls(calls: list[dict[str, object]]) -> str:
    for payload in reversed(calls):
        try:
            return _first_source_id(_tool_messages(payload))
        except AssertionError:
            continue
    return "sec_companyfacts"


def _evidence_context_from_final_payload(payload: dict[str, object]) -> list[dict[str, Any]]:
    messages = payload["messages"]
    assert isinstance(messages, list)
    content = messages[-1]["content"]
    assert isinstance(content, str)
    return json.loads(content.split("Evidence context JSON:", 1)[1].strip())


def _tool_content(evidence_context: list[dict[str, Any]], tool_name: str) -> dict[str, Any]:
    for payload in evidence_context:
        if payload.get("tool_name") == tool_name:
            content = payload.get("content")
            assert isinstance(content, dict)
            return content
    raise AssertionError(f"Tool content not found: {tool_name}")


def _tool_call_response(call_id: str, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments),
                            },
                        }
                    ],
                }
            }
        ]
    }


def _content_response(payload: dict[str, object]) -> dict[str, object]:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def _fake_sec_transport(url: str, timeout_seconds: float) -> dict[str, object]:
    if url.endswith("/company_tickers.json"):
        return {"0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."}}
    return {
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                "NetCashProvidedByUsedInOperatingActivities": {
                    "label": "Net Cash Provided by Operating Activities",
                    "units": {
                        "USD": [
                            {
                                "val": 32000000000,
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-02-01",
                                "accn": "0000320193-26-000001",
                            }
                        ]
                    },
                },
                "PaymentsToAcquirePropertyPlantAndEquipment": {
                    "label": "Payments to Acquire Property Plant and Equipment",
                    "units": {
                        "USD": [
                            {
                                "val": 3000000000,
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-02-01",
                                "accn": "0000320193-26-000001",
                            }
                        ]
                    },
                },
                "PaymentsForRepurchaseOfCommonStock": {
                    "label": "Payments for Repurchase of Common Stock",
                    "units": {
                        "USD": [
                            {
                                "val": 18000000000,
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-02-01",
                                "accn": "0000320193-26-000001",
                            }
                        ]
                    },
                },
            }
        },
    }


def _fake_sec_transport_without_buybacks(url: str, timeout_seconds: float) -> dict[str, object]:
    payload = _fake_sec_transport(url, timeout_seconds)
    if url.endswith("/company_tickers.json"):
        return payload
    facts = payload["facts"]
    assert isinstance(facts, dict)
    us_gaap = facts["us-gaap"]
    assert isinstance(us_gaap, dict)
    us_gaap.pop("PaymentsForRepurchaseOfCommonStock", None)
    return payload


def _fake_yahoo_transport(url: str, timeout_seconds: float) -> dict[str, object]:
    return {
        "quoteSummary": {
            "result": [
                {
                    "assetProfile": {
                        "longBusinessSummary": (
                            "Apple designs consumer devices, software, and services "
                            "for a global installed base."
                        ),
                        "sector": "Technology",
                        "industry": "Consumer Electronics",
                    },
                    "price": {
                        "longName": "Apple Inc.",
                        "quoteType": "EQUITY",
                    },
                }
            ]
        }
    }
