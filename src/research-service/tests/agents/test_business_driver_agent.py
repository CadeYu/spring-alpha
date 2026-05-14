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


def test_business_driver_agent_uses_langgraph_tool_workflow() -> None:
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
            source_id = _first_source_id_from_final_payload(payload)
            return _content_response(
                {
                    "driver_thesis": {
                        "headline": "Services demand is the durable driver",
                        "durability": "durable",
                        "summary": (
                            "Services demand and installed-base engagement are the clearest "
                            "operating drivers."
                        ),
                    },
                    "driver_map": {
                        "product": [],
                        "segment": [
                            {
                                "title": "Services momentum",
                                "summary": (
                                    "Services revenue and engagement evidence point to "
                                    "sustained demand."
                                ),
                                "source_ids": [source_id],
                                "citation_status": "supported",
                            }
                        ],
                        "geography": [],
                        "demand": [],
                        "pricing": [],
                        "customer": [],
                        "strategy": [],
                    },
                    "positive_signals": [],
                    "negative_signals": [],
                    "watchlist": [
                        "Watch whether services growth broadens beyond installed-base engagement."
                    ],
                    "claims": [
                        {
                            "text": "Services demand is the primary business driver.",
                            "source_ids": [source_id],
                            "citation_status": "supported",
                        }
                    ],
                }
            )
        if not tool_messages:
            return _tool_call_response(
                "call_filing",
                "search_filing_sections",
                {
                    "sections": ["MD&A", "Segment Information"],
                    "query": "services installed base product demand pricing strategy",
                    "limit": 5,
                },
            )
        if len(tool_messages) == 1:
            return _tool_call_response(
                "call_metric",
                "search_metric_evidence",
                {
                    "metrics": ["revenue", "segment revenue"],
                    "query": "revenue segment revenue services products",
                },
            )
        if len(tool_messages) == 2:
            return _tool_call_response(
                "call_signals",
                "get_business_signals",
                {"signal_types": ["product", "segment", "demand", "strategy"]},
            )
        raise AssertionError("unexpected tool planning request")

    result = _workflow(transport).run(_business_request("run_business_graph"))

    assert len(calls) == 1
    assert "tools" not in calls[-1]
    assert result.status == AgentRunStatus.OK
    assert result.final_report is not None
    assert result.final_report["sections"]["synthesis"] == "llm"
    assert result.final_report["task_sections"]["driver_thesis"]["headline"] == (
        "Services demand is the durable driver"
    )
    assert [event.tool_name for event in result.events if event.tool_name] == [
        "get_company_facts",
        "search_metric_evidence",
        "build_evidence_pack",
        "get_business_signals",
    ]
    assert any(event.event_kind == "reasoning" for event in result.events)
    evidence_context = _evidence_context_from_final_payload(calls[-1])
    evidence_pack = _tool_content(evidence_context, "build_evidence_pack")["evidence_pack"]
    metric_facts = evidence_pack["metric_facts"]
    assert any(
        fact["source_type"] == "yahoo_profile"
        and fact["business_summary"].startswith("Apple designs consumer devices")
        and fact["sector"] == "Technology"
        for fact in metric_facts
    )
    assert any(
        fact["source_type"] == "metric_evidence"
        and fact["metric"] == "revenue"
        and fact["source_id"].endswith(":sec_companyfacts:revenue")
        for fact in metric_facts
    )


def test_business_driver_agent_returns_transparent_partial_state_when_final_llm_fails() -> None:
    calls: list[dict[str, object]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        if "tools" not in payload:
            raise TimeoutError("provider timed out during final business synthesis")
        tool_messages = _tool_messages(payload)
        if not tool_messages:
            return _tool_call_response(
                "call_filing",
                "search_filing_sections",
                {
                    "sections": ["MD&A", "Segment Information"],
                    "query": "services installed base product demand pricing strategy",
                },
            )
        if len(tool_messages) == 1:
            return _tool_call_response(
                "call_metric",
                "search_metric_evidence",
                {"metrics": ["revenue", "segment revenue"]},
            )
        if len(tool_messages) == 2:
            return _tool_call_response(
                "call_signals",
                "get_business_signals",
                {"signal_types": ["segment", "demand"]},
            )
        raise AssertionError("unexpected tool planning request")

    result = _workflow(transport).run(_business_request("run_business_partial"))

    assert len(calls) == 1
    assert result.status == AgentRunStatus.DEGRADED
    assert result.final_report is None
    assert "provider timed out during final business synthesis" in result.degraded_reasons[0]
    assert result.retryable is True
    assert len(result.retrieval_records) == 4
    assert [event.tool_name for event in result.events if event.tool_name] == [
        "get_company_facts",
        "search_metric_evidence",
        "build_evidence_pack",
        "get_business_signals",
    ]
    assert result.events[-1].phase == "degraded"
    assert any(
        event.summary == "Built SEC filing evidence pack for business drivers."
        for event in result.events
    )


def test_business_driver_final_prompt_requires_investment_memo_quality_structure() -> None:
    from app.agents.business_driver_agent import _final_business_driver_instruction

    instruction = _final_business_driver_instruction(
        _business_request("run_business_prompt"),
        AgentState(
            run_id="run_business_prompt",
            ticker="AAPL",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            task_policy=default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE),
        ),
    )
    normalized_instruction = instruction.lower()

    for expected in (
        "investment memo",
        "counter-evidence",
        "what would change the conclusion",
        "so what",
        "at least four driver_map lenses",
        "bullish",
        "bearish",
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
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services net sales increased as installed base engagement, customer demand, and product
mix improved.
Segment Information
Services revenue was supported by subscriptions and customer engagement across major markets.
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


def _business_request(run_id: str) -> AgentRequest:
    return AgentRequest(
        run_id=run_id,
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        llm_provider=LlmProvider.SILICONFLOW,
        llm_model="test-model",
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


def _first_source_id_from_final_payload(payload: dict[str, object]) -> str:
    messages = payload["messages"]
    assert isinstance(messages, list)
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, str) or "Evidence context JSON:" not in content:
            continue
        evidence_payload = json.loads(content.split("Evidence context JSON:", 1)[1].strip())
        for tool_payload in evidence_payload:
            source_id = _source_id_from_value(tool_payload)
            if source_id:
                return source_id
    raise AssertionError("No source id found in final payload")


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


def _source_id_from_value(value: object) -> str | None:
    if isinstance(value, dict):
        raw_source_id = value.get("source_id") or value.get("node_id")
        if raw_source_id:
            return str(raw_source_id)
        for nested in value.values():
            source_id = _source_id_from_value(nested)
            if source_id:
                return source_id
    if isinstance(value, list):
        for item in value:
            source_id = _source_id_from_value(item)
            if source_id:
                return source_id
    return None


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
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "label": "Revenue",
                    "units": {
                        "USD": [
                            {
                                "val": 90000000000,
                                "fy": 2026,
                                "fp": "Q1",
                                "form": "10-Q",
                                "filed": "2026-02-01",
                                "accn": "0000320193-26-000001",
                            }
                        ]
                    },
                }
            }
        },
    }


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
