import json

from app.agents.domain_tools import LlamaIndexResearchToolService, SecCompanyFactsProvider
from app.agents.llm_gateway import OpenAiCompatibleLlmClient
from app.agents.research_workflow import ResearchAgentWorkflow
from app.contracts.agent import AgentRequest, LlmProvider
from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline


def test_latest_earnings_workflow_uses_langchain_tool_calling_agent() -> None:
    calls: list[dict[str, object]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        if "tools" not in payload:
            final_payload = {
                "company_profile": {
                    "summary": (
                        "Apple designs consumer devices, software, and services for a "
                        "global installed base."
                    ),
                    "source_ids": [],
                    "citation_status": "unverified",
                },
                "topline_verdict": {
                    "headline": "Services and margin evidence frame the quarter",
                    "summary": (
                        "Revenue and gross margin evidence point to a mixed but "
                        "evidence-backed latest earnings readout."
                    ),
                    "verdict": "mixed",
                },
                "key_takeaways": [],
                "financial_dashboard": {
                    "metrics": [
                        {
                            "name": "Revenue",
                            "value": "Not extracted",
                            "period": "latest_quarter",
                            "interpretation": "Provider stayed cautious.",
                            "source_ids": ["src_1"],
                            "citation_status": "partial",
                        }
                    ],
                    "chart_focus": ["revenue"],
                },
                "driver_snapshot": [],
                "risk_snapshot": [],
                "claims": [],
            }
            return {
                "choices": [
                    {
                        "message": {
                            "content": f"```json\n{json.dumps(final_payload)}\n```"
                        }
                    }
                ]
            }
        messages = payload["messages"]
        tool_messages = [
            message
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        ]
        if not tool_messages:
            return _tool_call_response(
                "call_facts",
                "get_company_facts",
                {"metrics": ["revenue", "gross margin", "operating income"]},
            )
        if len(tool_messages) == 1:
            return _tool_call_response(
                "call_metrics",
                "search_metric_evidence",
                {
                    "metrics": ["revenue", "gross margin", "operating income"],
                    "query": "revenue gross margin operating income",
                },
            )
        raise AssertionError("unexpected tool planning request")

    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000001",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue and gross margin improved as Services demand increased.
""",
        )
    )
    llm_client = OpenAiCompatibleLlmClient(
        LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )
    workflow = ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            pipeline,
            facts_provider=SecCompanyFactsProvider(transport=_fake_sec_transport),
        ),
        llm_client=llm_client,
        rag_pipeline=pipeline,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_earnings_agent",
            ticker="AAPL",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            llm_provider=LlmProvider.SILICONFLOW,
            llm_model="test-model",
            llm_api_key="secret",
        )
    )

    assert len(calls) == 1
    assert "tools" not in calls[-1]
    final_messages = calls[-1]["messages"]
    assert [
        message["role"]
        for message in final_messages
        if isinstance(message, dict)
    ] == ["system", "user", "user"]
    assert all(
        not (isinstance(message, dict) and message.get("role") == "tool")
        for message in final_messages
    )
    assert calls[-1]["response_format"] == {"type": "json_object"}
    assert calls[-1]["max_tokens"] == 1280
    assert result.final_report is not None
    task_sections = result.final_report["task_sections"]
    assert task_sections["topline_verdict"]["headline"] == (
        "Services and margin evidence frame the quarter"
    )
    assert task_sections["financial_dashboard"]["metrics"][0]["value"] == "$90.0B"
    assert result.final_report["sections"]["synthesis"] == "llm"
    event_tool_names = [event.tool_name for event in result.events]
    assert event_tool_names == ["get_company_facts", "search_metric_evidence"]


def test_latest_earnings_uses_planned_evidence_collection_not_llm_tool_planning() -> None:
    calls: list[dict[str, object]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        if "tools" in payload:
            return _tool_call_response("repeat_facts", "get_company_facts", {})
        return _content_response(
            {
                "company_profile": {
                    "summary": "Apple sells devices, software, and services.",
                    "source_ids": [],
                    "citation_status": "unverified",
                },
                "topline_verdict": {
                    "headline": "Planned evidence collection worked",
                    "summary": (
                        "The report was synthesized after deterministic evidence collection."
                    ),
                    "verdict": "mixed",
                },
                "key_takeaways": [],
                "financial_dashboard": {"metrics": [], "chart_focus": []},
                "driver_snapshot": [],
                "risk_snapshot": [],
                "claims": [],
            }
        )

    pipeline = LlamaIndexRagPipeline()
    llm_client = OpenAiCompatibleLlmClient(
        LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )
    workflow = ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            pipeline,
            facts_provider=SecCompanyFactsProvider(transport=_fake_sec_transport),
        ),
        llm_client=llm_client,
        rag_pipeline=pipeline,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_earnings_planned_tools",
            ticker="AAPL",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            llm_provider=LlmProvider.SILICONFLOW,
            llm_model="test-model",
            llm_api_key="secret",
        )
    )

    assert len(calls) == 1
    assert "tools" not in calls[0]
    assert result.final_report is not None
    assert [event.tool_name for event in result.events] == [
        "get_company_facts",
        "search_metric_evidence",
    ]


def test_deepseek_flash_final_synthesis_uses_compact_budget() -> None:
    calls: list[dict[str, object]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        return _content_response(
            {
                "company_profile": "Apple designs devices, software, and services.",
                "topline_verdict": {
                    "headline": "Compact synthesis worked",
                    "summary": "The final response used the compact DS budget.",
                    "verdict": "mixed",
                },
                "key_takeaways": [],
                "financial_dashboard": {"metrics": [], "chart_focus": []},
                "driver_snapshot": [],
                "risk_snapshot": [],
                "claims": [],
            }
        )

    pipeline = LlamaIndexRagPipeline()
    llm_client = OpenAiCompatibleLlmClient(
        LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )
    workflow = ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            pipeline,
            facts_provider=SecCompanyFactsProvider(transport=_fake_sec_transport),
        ),
        llm_client=llm_client,
        rag_pipeline=pipeline,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_earnings_deepseek_compact",
            ticker="AAPL",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            llm_provider=LlmProvider.SILICONFLOW,
            llm_model="deepseek-ai/DeepSeek-V4-Flash",
            llm_api_key="secret",
        )
    )

    assert result.final_report is not None
    assert calls[-1]["max_tokens"] == 768
    evidence_context = calls[-1]["messages"][-1]["content"]
    assert isinstance(evidence_context, str)
    assert len(evidence_context) < 2600


def test_final_synthesis_retries_without_rerunning_tools() -> None:
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
        final_attempts += 1
        if final_attempts == 1:
            raise TimeoutError("transient final synthesis timeout")
        return _content_response(
            {
                "company_profile": "Apple designs devices, software, and services.",
                "topline_verdict": {
                    "headline": "Retry recovered final synthesis",
                    "summary": "The second final synthesis attempt produced JSON.",
                    "verdict": "mixed",
                },
                "key_takeaways": [],
                "financial_dashboard": {"metrics": [], "chart_focus": []},
                "driver_snapshot": [],
                "risk_snapshot": [],
                "claims": [],
            }
        )

    pipeline = LlamaIndexRagPipeline()
    llm_client = OpenAiCompatibleLlmClient(
        LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )
    workflow = ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            pipeline,
            facts_provider=SecCompanyFactsProvider(transport=_fake_sec_transport),
        ),
        llm_client=llm_client,
        rag_pipeline=pipeline,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_earnings_retry_final",
            ticker="AAPL",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            llm_provider=LlmProvider.SILICONFLOW,
            llm_model="deepseek-ai/DeepSeek-V4-Flash",
            llm_api_key="secret",
        )
    )

    assert result.final_report is not None
    assert result.final_report["task_sections"]["topline_verdict"]["headline"] == (
        "Retry recovered final synthesis"
    )
    assert final_attempts == 2
    assert [event.tool_name for event in result.events] == [
        "get_company_facts",
        "search_metric_evidence",
    ]


def test_latest_earnings_metric_tool_defaults_missing_llm_arguments() -> None:
    calls: list[dict[str, object]] = []

    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        calls.append(payload)
        if "tools" not in payload:
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "company_profile": {
                                        "summary": "Apple sells devices, software, and services.",
                                        "source_ids": [],
                                        "citation_status": "unverified",
                                    },
                                    "topline_verdict": {
                                        "headline": "Default metric evidence worked",
                                        "summary": "The agent recovered from missing tool args.",
                                        "verdict": "mixed",
                                    },
                                    "key_takeaways": [],
                                    "financial_dashboard": {
                                        "metrics": [
                                            {
                                                "name": "Revenue",
                                                "value": "Not extracted",
                                                "period": "latest_quarter",
                                                "interpretation": "Fallback metric args were used.",
                                                "source_ids": [],
                                                "citation_status": "partial",
                                            }
                                        ],
                                        "chart_focus": ["revenue"],
                                    },
                                    "driver_snapshot": [],
                                    "risk_snapshot": [],
                                    "claims": [],
                                }
                            )
                        }
                    }
                ]
            }
        tool_messages = [
            message
            for message in payload["messages"]
            if isinstance(message, dict) and message.get("role") == "tool"
        ]
        if not tool_messages:
            return _tool_call_response(
                "call_facts",
                "get_company_facts",
                {"metrics": ["revenue", "gross margin", "operating income"]},
            )
        if len(tool_messages) == 1:
            return _tool_call_response("call_metrics", "search_metric_evidence", {})
        raise AssertionError("unexpected tool planning request")

    pipeline = LlamaIndexRagPipeline()
    llm_client = OpenAiCompatibleLlmClient(
        LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )
    workflow = ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            pipeline,
            facts_provider=SecCompanyFactsProvider(transport=_fake_sec_transport),
        ),
        llm_client=llm_client,
        rag_pipeline=pipeline,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_earnings_default_metric_args",
            ticker="AAPL",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            llm_provider=LlmProvider.SILICONFLOW,
            llm_model="test-model",
            llm_api_key="secret",
        )
    )

    assert result.final_report is not None
    assert [event.tool_name for event in result.events] == [
        "get_company_facts",
        "search_metric_evidence",
    ]


def test_latest_earnings_failure_preserves_collected_tool_events() -> None:
    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        tool_messages = [
            message
            for message in payload["messages"]
            if isinstance(message, dict) and message.get("role") == "tool"
        ]
        if not tool_messages:
            return _tool_call_response("call_facts", "get_company_facts", {})
        if len(tool_messages) == 1:
            return _tool_call_response("call_metrics", "search_metric_evidence", {})
        raise TimeoutError("final synthesis timeout")

    pipeline = LlamaIndexRagPipeline()
    llm_client = OpenAiCompatibleLlmClient(
        LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )
    workflow = ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            pipeline,
            facts_provider=SecCompanyFactsProvider(transport=_fake_sec_transport),
        ),
        llm_client=llm_client,
        rag_pipeline=pipeline,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_earnings_preserve_events",
            ticker="AAPL",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            llm_provider=LlmProvider.SILICONFLOW,
            llm_model="test-model",
            llm_api_key="secret",
        )
    )

    assert result.final_report is None
    assert result.retryable is True
    assert [event.tool_name for event in result.events if event.tool_name] == [
        "get_company_facts",
        "search_metric_evidence",
    ]
    assert result.events[-1].degraded_reason is not None


def test_latest_earnings_mapping_failure_preserves_collected_tool_events() -> None:
    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        return _content_response(
            {
                "company_profile": "Apple designs devices, software, and services.",
                "topline_verdict": {
                    "headline": "Mapping failure should preserve evidence",
                    "summary": "The final payload intentionally has an invalid claim.",
                    "verdict": "mixed",
                },
                "key_takeaways": [],
                "financial_dashboard": {"metrics": [], "chart_focus": []},
                "driver_snapshot": [],
                "risk_snapshot": [],
                "claims": [123],
            }
        )

    pipeline = LlamaIndexRagPipeline()
    llm_client = OpenAiCompatibleLlmClient(
        LlmProvider.SILICONFLOW,
        api_key="secret",
        base_url="https://example.test/v1",
        transport=transport,
    )
    workflow = ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            pipeline,
            facts_provider=SecCompanyFactsProvider(transport=_fake_sec_transport),
        ),
        llm_client=llm_client,
        rag_pipeline=pipeline,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_earnings_preserve_mapping_failure",
            ticker="AAPL",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
            llm_provider=LlmProvider.SILICONFLOW,
            llm_model="test-model",
            llm_api_key="secret",
        )
    )

    assert result.final_report is None
    assert result.retryable is True
    assert [event.tool_name for event in result.events if event.tool_name] == [
        "get_company_facts",
        "search_metric_evidence",
    ]
    assert result.events[-1].phase.value == "degraded"


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
