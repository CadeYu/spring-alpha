from app.agents.deterministic_workflow import DeterministicAgentWorkflow
from app.agents.llm_gateway import StaticJsonLlmClient
from app.agents.report_synthesizer import (
    ReportSynthesisError,
    synthesize_business_driver_report,
    synthesize_cash_flow_report,
    synthesize_latest_earnings_report,
)
from app.contracts.agent import (
    AgentRequest,
    AgentRunStatus,
    AgentState,
    LlmProvider,
    default_task_policy,
)
from app.contracts.research_task import ResearchTaskType


def test_synthesizer_builds_latest_earnings_sections_from_evidence() -> None:
    state = state_with_evidence()
    client = StaticJsonLlmClient(
        {
            "topline_verdict": {
                "headline": "Services demand is carrying a mixed earnings setup",
                "summary": "Services demand improved, while the evidence base remains narrow.",
                "verdict": "mixed",
            },
            "key_takeaways": [
                {
                    "title": "Services demand improved",
                    "summary": "Management commentary points to stronger services demand.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ],
            "financial_dashboard": {
                "metrics": [
                    {
                        "name": "Revenue",
                        "value": "Evidence-backed",
                        "period": "latest_quarter",
                        "interpretation": "Revenue context is tied to the cited MD&A evidence.",
                        "source_ids": ["src_1"],
                        "citation_status": "supported",
                    }
                ],
                "chart_focus": ["revenue", "gross margin"],
            },
            "driver_snapshot": [
                {
                    "title": "Demand",
                    "summary": "Installed base engagement supported services demand.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ],
            "risk_snapshot": [
                {
                    "title": "Evidence depth",
                    "summary": (
                        "The synthesis should stay cautious because only one source was cited."
                    ),
                    "source_ids": ["src_1"],
                    "citation_status": "partial",
                }
            ],
            "claims": [
                {
                    "text": "Services demand improved based on management commentary.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ],
        }
    )

    report = synthesize_latest_earnings_report(request(), state, client)

    assert report.task_sections.topline_verdict.headline == (
        "Services demand is carrying a mixed earnings setup"
    )
    assert report.task_sections.key_takeaways[0].evidence_refs[0].source_id == "src_1"
    assert report.claims[0].source_refs[0].source_id == "src_1"
    assert "Deterministic latest earnings" not in report.claims[0].text


def test_synthesizer_rejects_unknown_source_ids() -> None:
    state = state_with_evidence()
    client = StaticJsonLlmClient(
        {
            "topline_verdict": {
                "headline": "Unsupported headline",
                "summary": "This cites a source that was never retrieved.",
                "verdict": "mixed",
            },
            "key_takeaways": [
                {
                    "title": "Unsupported point",
                    "summary": "The source id is not part of evidence memory.",
                    "source_ids": ["made_up_source"],
                    "citation_status": "supported",
                }
            ],
            "financial_dashboard": {"metrics": [], "chart_focus": []},
            "driver_snapshot": [],
            "risk_snapshot": [],
            "claims": [
                {
                    "text": "This claim cites a fabricated source.",
                    "source_ids": ["made_up_source"],
                    "citation_status": "supported",
                }
            ],
        }
    )

    try:
        synthesize_latest_earnings_report(request(), state, client)
    except ReportSynthesisError as exc:
        assert "Unknown source_id" in str(exc)
    else:
        raise AssertionError("synthesizer should reject unknown source ids")


def test_synthesizer_builds_business_driver_sections_from_evidence() -> None:
    state = state_with_business_driver_evidence()
    client = StaticJsonLlmClient(
        {
            "driver_thesis": {
                "headline": "Services engagement is the primary business driver",
                "durability": "mixed",
                "summary": "The cited filing evidence points to services demand and engagement.",
            },
            "driver_map": {
                "product": [
                    {
                        "title": "Services",
                        "summary": "Services demand improved according to the filing.",
                        "source_ids": ["driver_src_1"],
                        "citation_status": "supported",
                    }
                ],
                "segment": [],
                "geography": [],
                "demand": [
                    {
                        "title": "Installed base",
                        "summary": "Installed base engagement expanded.",
                        "source_ids": ["driver_src_1"],
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
                    "summary": "Demand commentary is positive but evidence remains narrow.",
                    "source_ids": ["driver_src_1"],
                    "citation_status": "partial",
                }
            ],
            "negative_signals": [],
            "watchlist": ["Track whether services engagement persists next quarter."],
            "claims": [
                {
                    "text": "Services engagement is a key business driver.",
                    "source_ids": ["driver_src_1"],
                    "citation_status": "supported",
                }
            ],
        }
    )

    report = synthesize_business_driver_report(business_driver_request(), state, client)

    assert report.task_sections.driver_thesis.headline == (
        "Services engagement is the primary business driver"
    )
    assert report.task_sections.driver_map.product[0].evidence_refs[0].source_id == ("driver_src_1")
    assert report.task_sections.watchlist == [
        "Track whether services engagement persists next quarter."
    ]
    assert report.sections == {
        "summary": "The cited filing evidence points to services demand and engagement.",
        "synthesis": "llm",
    }
    assert report.claims[0].source_refs[0].source_id == "driver_src_1"


def test_business_driver_synthesizer_rejects_unknown_source_ids() -> None:
    state = state_with_business_driver_evidence()
    client = StaticJsonLlmClient(
        {
            "driver_thesis": {
                "headline": "Unsupported driver thesis",
                "durability": "mixed",
                "summary": "This cites a fabricated source.",
            },
            "driver_map": {
                "product": [
                    {
                        "title": "Unsupported",
                        "summary": "This source id is not available.",
                        "source_ids": ["missing_driver_source"],
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
            "watchlist": [],
            "claims": [],
        }
    )

    try:
        synthesize_business_driver_report(business_driver_request(), state, client)
    except ReportSynthesisError as exc:
        assert "Unknown source_id" in str(exc)
    else:
        raise AssertionError("business driver synthesizer should reject unknown source ids")


def test_synthesizer_builds_cash_flow_sections_from_evidence() -> None:
    state = state_with_cash_flow_evidence()
    client = StaticJsonLlmClient(cash_flow_synthesis_payload("cash_src_1"))

    report = synthesize_cash_flow_report(cash_flow_request(), state, client)

    assert report.task_sections.cash_quality_verdict.headline == (
        "Operating cash flow supports capital returns"
    )
    assert report.task_sections.cash_quality_verdict.earnings_backed_by_cash == "mixed"
    assert report.task_sections.cash_metrics[0].name == "Operating cash flow"
    assert report.task_sections.cash_metrics[0].evidence_refs[0].source_id == "cash_src_1"
    assert report.task_sections.capital_allocation.buybacks[0].evidence_refs[0].source_id == (
        "cash_src_1"
    )
    assert report.sections == {
        "summary": "Cash generation funded capex and buybacks, with liquidity still cited.",
        "synthesis": "llm",
    }
    assert report.claims[0].source_refs[0].source_id == "cash_src_1"


def test_cash_flow_synthesizer_rejects_unknown_source_ids() -> None:
    state = state_with_cash_flow_evidence()
    client = StaticJsonLlmClient(cash_flow_synthesis_payload("missing_cash_source"))

    try:
        synthesize_cash_flow_report(cash_flow_request(), state, client)
    except ReportSynthesisError as exc:
        assert "Unknown source_id" in str(exc)
    else:
        raise AssertionError("cash flow synthesizer should reject unknown source ids")


def test_synthesizer_prompt_contains_evidence_not_raw_trace() -> None:
    class RecordingClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.prompt = ""

        def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
            self.prompt = llm_request.user_prompt
            return StaticJsonLlmClient(
                {
                    "topline_verdict": {
                        "headline": "Evidence-bound headline",
                        "summary": "Evidence-bound summary.",
                        "verdict": "mixed",
                    },
                    "key_takeaways": [],
                    "financial_dashboard": {"metrics": [], "chart_focus": []},
                    "driver_snapshot": [],
                    "risk_snapshot": [],
                    "claims": [],
                }
            ).complete_json(llm_request)

    state = state_with_evidence()
    client = RecordingClient()

    synthesize_latest_earnings_report(request(), state, client)

    assert "src_1" in client.prompt
    assert "Services revenue increased" in client.prompt
    assert "planner_context" not in client.prompt
    assert "secret" not in client.prompt
    assert "scratchpad" not in client.prompt


def test_synthesizer_uses_short_source_aliases_in_provider_prompt() -> None:
    class RecordingClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.prompt = ""

        def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
            self.prompt = llm_request.user_prompt
            return StaticJsonLlmClient(
                {
                    "topline_verdict": {
                        "headline": "Alias source ids are stable",
                        "summary": "The provider cited a short source alias.",
                        "verdict": "mixed",
                    },
                    "key_takeaways": [
                        {
                            "title": "Alias",
                            "summary": "Short aliases reduce source id copying errors.",
                            "source_ids": ["src_1"],
                            "citation_status": "supported",
                        }
                    ],
                    "financial_dashboard": {"metrics": [], "chart_focus": []},
                    "driver_snapshot": [],
                    "risk_snapshot": [],
                    "claims": [
                        {
                            "text": "The cited source alias maps back to the original source.",
                            "source_ids": ["src_1"],
                            "citation_status": "supported",
                        }
                    ],
                }
            ).complete_json(llm_request)

    long_source_id = "AAPL:0000320193-26-000013:md-a:0:73f365bd8dfb"
    state = state_with_evidence().model_copy(
        update={
            "evidence_memory": state_with_evidence().evidence_memory.model_copy(
                update={
                    "source_refs": [
                        {
                            "source_id": long_source_id,
                            "section": "MD&A",
                            "snippet": "Services revenue increased because demand improved.",
                            "citation_status": "unverified",
                        }
                    ]
                }
            )
        }
    )
    client = RecordingClient()

    report = synthesize_latest_earnings_report(request(), state, client)

    assert 'Allowed source_ids: ["src_1"]' in client.prompt
    assert f"original_source_id={long_source_id}" in client.prompt
    assert report.claims[0].source_refs[0].source_id == long_source_id


def test_synthesizer_retries_transient_llm_json_failure() -> None:
    class FlakyClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                raise ValueError("bad provider JSON")
            return StaticJsonLlmClient(
                {
                    "topline_verdict": {
                        "headline": "Evidence-bound retry succeeded",
                        "summary": "The retry produced a valid synthesized report.",
                        "verdict": "mixed",
                    },
                    "key_takeaways": [],
                    "financial_dashboard": {"metrics": [], "chart_focus": []},
                    "driver_snapshot": [],
                    "risk_snapshot": [],
                    "claims": [
                        {
                            "text": "Retry synthesis cited the available source.",
                            "source_ids": ["src_1"],
                            "citation_status": "supported",
                        }
                    ],
                }
            ).complete_json(llm_request)

    client = FlakyClient()

    report = synthesize_latest_earnings_report(request(), state_with_evidence(), client)

    assert client.calls == 2
    assert report.task_sections.topline_verdict.headline == "Evidence-bound retry succeeded"
    assert report.sections == {
        "summary": "The retry produced a valid synthesized report.",
        "synthesis": "llm",
    }


def test_synthesizer_accepts_numeric_metric_values_from_provider() -> None:
    client = StaticJsonLlmClient(
        {
            "topline_verdict": {
                "headline": "Numeric facts were normalized",
                "summary": "The provider returned numeric metric values that were normalized.",
                "verdict": "mixed",
            },
            "key_takeaways": [],
            "financial_dashboard": {
                "metrics": [
                    {
                        "name": "Revenue",
                        "value": 219659000000,
                        "period": "latest_quarter",
                        "interpretation": "Revenue came from cited company facts.",
                        "source_ids": ["src_1"],
                        "citation_status": "supported",
                    }
                ],
                "chart_focus": ["revenue"],
            },
            "driver_snapshot": [],
            "risk_snapshot": [],
            "claims": [
                {
                    "text": "Revenue was grounded in the cited source.",
                    "source_ids": ["src_1"],
                    "citation_status": "supported",
                }
            ],
        }
    )

    report = synthesize_latest_earnings_report(request(), state_with_evidence(), client)

    assert report.task_sections.financial_dashboard.metrics[0].value == "219659000000"


def test_agent_uses_synthesized_latest_earnings_report_when_llm_is_available() -> None:
    class PlanningAndSynthesisClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return StaticJsonLlmClient(
                    {
                        "decision": "call_tool",
                        "summary": "Search evidence before synthesis.",
                        "tool_name": "search_filing_sections",
                        "tool_input": {"sections": ["MD&A"], "query": "revenue margin demand"},
                    }
                ).complete_json(llm_request)
            if self.calls == 2:
                return StaticJsonLlmClient(
                    {
                        "decision": "finalize",
                        "summary": "Evidence is ready for synthesis.",
                    }
                ).complete_json(llm_request)
            return StaticJsonLlmClient(
                {
                    "topline_verdict": {
                        "headline": "Services demand supports a mixed earnings readout",
                        "summary": "The report uses cited filing evidence instead of a template.",
                        "verdict": "mixed",
                    },
                    "key_takeaways": [
                        {
                            "title": "Demand evidence",
                            "summary": "The cited filing section supports the demand readout.",
                            "source_ids": ["run_agent_synth:filing:1"],
                            "citation_status": "supported",
                        }
                    ],
                    "financial_dashboard": {
                        "metrics": [
                            {
                                "name": "Revenue",
                                "value": "Evidence-backed",
                                "interpretation": (
                                    "Revenue is discussed in the cited filing context."
                                ),
                                "source_ids": ["run_agent_synth:filing:1"],
                                "citation_status": "supported",
                            }
                        ],
                        "chart_focus": ["revenue"],
                    },
                    "driver_snapshot": [
                        {
                            "title": "Services",
                            "summary": "Services demand is the main cited driver.",
                            "source_ids": ["run_agent_synth:filing:1"],
                            "citation_status": "supported",
                        }
                    ],
                    "risk_snapshot": [
                        {
                            "title": "Evidence concentration",
                            "summary": "The report should stay cautious with one cited section.",
                            "source_ids": ["run_agent_synth:filing:1"],
                            "citation_status": "partial",
                        }
                    ],
                    "claims": [
                        {
                            "text": "Services demand supports a mixed latest earnings readout.",
                            "source_ids": ["run_agent_synth:filing:1"],
                            "citation_status": "supported",
                        }
                    ],
                }
            ).complete_json(llm_request)

    client = PlanningAndSynthesisClient()
    workflow = DeterministicAgentWorkflow(
        llm_client=client,
        report_synthesis_client=client,
        enable_report_synthesis=True,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_agent_synth",
            ticker="AAPL",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        )
    )

    assert result.final_report is not None
    assert result.status == AgentRunStatus.OK
    assert result.final_report["task_sections"]["topline_verdict"]["headline"] == (
        "Services demand supports a mixed earnings readout"
    )
    assert result.final_report["sections"]["synthesis"] == "llm"
    assert "Deterministic latest earnings" not in result.final_report["claims"][0]["text"]


def test_agent_uses_synthesized_business_driver_report_when_llm_is_available() -> None:
    class PlanningAndSynthesisClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return StaticJsonLlmClient(
                    {
                        "decision": "call_tool",
                        "summary": "Search business driver evidence.",
                        "tool_name": "search_filing_sections",
                        "tool_input": {
                            "sections": ["MD&A"],
                            "query": "services demand engagement",
                        },
                    }
                ).complete_json(llm_request)
            if self.calls == 2:
                return StaticJsonLlmClient(
                    {
                        "decision": "finalize",
                        "summary": "Business driver evidence is ready for synthesis.",
                    }
                ).complete_json(llm_request)
            return StaticJsonLlmClient(
                {
                    "driver_thesis": {
                        "headline": "Services demand is the core business driver",
                        "durability": "mixed",
                        "summary": "The synthesized report uses cited filing evidence.",
                    },
                    "driver_map": {
                        "product": [
                            {
                                "title": "Services",
                                "summary": "Services demand is tied to cited evidence.",
                                "source_ids": ["run_agent_business_synth:filing:1"],
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
                    "positive_signals": [
                        {
                            "title": "Demand",
                            "summary": "Demand is positive but should be monitored.",
                            "source_ids": ["run_agent_business_synth:filing:1"],
                            "citation_status": "partial",
                        }
                    ],
                    "negative_signals": [],
                    "watchlist": ["Watch whether demand persists."],
                    "claims": [
                        {
                            "text": "Services demand is the core business driver.",
                            "source_ids": ["run_agent_business_synth:filing:1"],
                            "citation_status": "supported",
                        }
                    ],
                }
            ).complete_json(llm_request)

    client = PlanningAndSynthesisClient()
    workflow = DeterministicAgentWorkflow(
        llm_client=client,
        report_synthesis_client=client,
        enable_report_synthesis=True,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_agent_business_synth",
            ticker="AAPL",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        )
    )

    assert result.final_report is not None
    assert result.status == AgentRunStatus.OK
    assert result.final_report["sections"]["synthesis"] == "llm"
    assert result.final_report["task_sections"]["driver_thesis"]["headline"] == (
        "Services demand is the core business driver"
    )
    assert (
        result.final_report["task_sections"]["driver_map"]["product"][0]["evidence_refs"][0][
            "source_id"
        ]
        == "run_agent_business_synth:filing:1"
    )


def test_agent_uses_synthesized_cash_flow_report_when_llm_is_available() -> None:
    class PlanningAndSynthesisClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return StaticJsonLlmClient(
                    {
                        "decision": "call_tool",
                        "summary": "Collect cash flow company facts.",
                        "tool_name": "get_company_facts",
                        "tool_input": {
                            "period": "latest_quarter",
                            "metrics": ["operating cash flow", "capex"],
                        },
                    }
                ).complete_json(llm_request)
            if self.calls == 2:
                return StaticJsonLlmClient(
                    {
                        "decision": "call_tool",
                        "summary": "Search cash flow and capital allocation evidence.",
                        "tool_name": "search_filing_sections",
                        "tool_input": {
                            "sections": ["Cash Flows", "MD&A"],
                            "query": "operating cash flow capex buybacks liquidity",
                        },
                    }
                ).complete_json(llm_request)
            if self.calls == 3:
                return StaticJsonLlmClient(
                    {
                        "decision": "finalize",
                        "summary": "Cash evidence is ready for synthesis.",
                    }
                ).complete_json(llm_request)
            return StaticJsonLlmClient(
                cash_flow_synthesis_payload("run_agent_cash_synth:filing:1")
            ).complete_json(llm_request)

    client = PlanningAndSynthesisClient()
    workflow = DeterministicAgentWorkflow(
        llm_client=client,
        report_synthesis_client=client,
        enable_report_synthesis=True,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_agent_cash_synth",
            ticker="AAPL",
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        )
    )

    assert result.final_report is not None
    assert result.status == AgentRunStatus.OK
    assert result.final_report["sections"]["synthesis"] == "llm"
    assert result.final_report["task_sections"]["cash_quality_verdict"]["headline"] == (
        "Operating cash flow supports capital returns"
    )
    assert (
        result.final_report["task_sections"]["capital_allocation"]["buybacks"][0]["evidence_refs"][
            0
        ]["source_id"]
        == "run_agent_cash_synth:filing:1"
    )


def test_agent_falls_back_to_deterministic_report_when_synthesis_is_invalid() -> None:
    class InvalidSynthesisClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                return StaticJsonLlmClient(
                    {
                        "decision": "call_tool",
                        "summary": "Search evidence before synthesis.",
                        "tool_name": "search_filing_sections",
                        "tool_input": {"sections": ["MD&A"], "query": "revenue margin demand"},
                    }
                ).complete_json(llm_request)
            if self.calls == 2:
                return StaticJsonLlmClient(
                    {
                        "decision": "finalize",
                        "summary": "Evidence is ready for synthesis.",
                    }
                ).complete_json(llm_request)
            return StaticJsonLlmClient(
                {
                    "topline_verdict": {
                        "headline": "Bad source",
                        "summary": "This response cites a fabricated source.",
                        "verdict": "mixed",
                    },
                    "key_takeaways": [
                        {
                            "title": "Bad source",
                            "summary": "This source id should be rejected.",
                            "source_ids": ["fake_source"],
                            "citation_status": "supported",
                        }
                    ],
                    "financial_dashboard": {"metrics": [], "chart_focus": []},
                    "driver_snapshot": [],
                    "risk_snapshot": [],
                    "claims": [],
                }
            ).complete_json(llm_request)

    client = InvalidSynthesisClient()
    workflow = DeterministicAgentWorkflow(
        llm_client=client,
        report_synthesis_client=client,
        enable_report_synthesis=True,
    )

    result = workflow.run(
        AgentRequest(
            run_id="run_agent_synth_fallback",
            ticker="AAPL",
            task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        )
    )

    assert result.status == AgentRunStatus.DEGRADED
    assert result.final_report is not None
    assert result.final_report["sections"]["summary"].startswith("Deterministic latest earnings")
    assert any("Report synthesis failed" in reason for reason in result.degraded_reasons)


def request() -> AgentRequest:
    return AgentRequest(
        run_id="run_synthesis_001",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        llm_provider=LlmProvider.OPENAI,
        llm_model="test-model",
        llm_api_key="secret",
    )


def business_driver_request() -> AgentRequest:
    return AgentRequest(
        run_id="run_business_synthesis_001",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        llm_provider=LlmProvider.OPENAI,
        llm_model="test-model",
        llm_api_key="secret",
    )


def cash_flow_request() -> AgentRequest:
    return AgentRequest(
        run_id="run_cash_synthesis_001",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        llm_provider=LlmProvider.OPENAI,
        llm_model="test-model",
        llm_api_key="secret",
    )


def state_with_evidence() -> AgentState:
    state = AgentState(
        run_id="run_synthesis_001",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        provider=LlmProvider.OPENAI,
        model="test-model",
        task_policy=default_task_policy(ResearchTaskType.LATEST_EARNINGS_READOUT),
    )
    return state.model_copy(
        update={
            "evidence_memory": state.evidence_memory.model_copy(
                update={
                    "facts": {"period": "latest_quarter", "metrics": ["revenue"]},
                    "source_refs": [
                        {
                            "source_id": "src_1",
                            "section": "MD&A",
                            "snippet": (
                                "Services revenue increased because demand improved "
                                "and installed base engagement expanded."
                            ),
                            "filing_type": "10-Q",
                            "filing_date": "2026-04-30",
                            "accession_number": "0000320193-26-000001",
                            "citation_status": "supported",
                        }
                    ],
                }
            ),
            "retrieval_records": [
                {
                    "tool_name": "search_filing_sections",
                    "status": "ok",
                    "source_ref_count": 1,
                }
            ],
        }
    )


def state_with_business_driver_evidence() -> AgentState:
    state = AgentState(
        run_id="run_business_synthesis_001",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        provider=LlmProvider.OPENAI,
        model="test-model",
        task_policy=default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE),
    )
    return state.model_copy(
        update={
            "evidence_memory": state.evidence_memory.model_copy(
                update={
                    "source_refs": [
                        {
                            "source_id": "driver_src_1",
                            "section": "MD&A",
                            "snippet": (
                                "Services demand improved because installed base "
                                "engagement expanded across customers."
                            ),
                            "filing_type": "10-Q",
                            "filing_date": "2026-04-30",
                            "accession_number": "0000320193-26-000010",
                            "citation_status": "supported",
                        }
                    ],
                    "business_signals": [
                        {
                            "signal": "services_engagement",
                            "summary": "Installed base engagement expanded.",
                        }
                    ],
                }
            ),
            "retrieval_records": [
                {
                    "tool_name": "search_filing_sections",
                    "status": "ok",
                    "source_ref_count": 1,
                }
            ],
        }
    )


def state_with_cash_flow_evidence() -> AgentState:
    state = AgentState(
        run_id="run_cash_synthesis_001",
        ticker="AAPL",
        task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        provider=LlmProvider.OPENAI,
        model="test-model",
        task_policy=default_task_policy(ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION),
    )
    return state.model_copy(
        update={
            "evidence_memory": state.evidence_memory.model_copy(
                update={
                    "facts": {
                        "period": "latest_quarter",
                        "metrics": [
                            {
                                "name": "operating cash flow",
                                "value": "29000000000",
                                "unit": "USD",
                            }
                        ],
                    },
                    "source_refs": [
                        {
                            "source_id": "cash_src_1",
                            "section": "Cash Flow Statement",
                            "snippet": (
                                "Operating cash flow funded capital expenditures and "
                                "share repurchases while liquidity remained strong."
                            ),
                            "filing_type": "10-Q",
                            "filing_date": "2026-04-30",
                            "accession_number": "0000320193-26-000020",
                            "citation_status": "supported",
                        }
                    ],
                    "metric_evidence": [
                        {
                            "metric": "operating cash flow",
                            "period": "latest_quarter",
                            "source_id": "cash_src_1",
                        }
                    ],
                }
            ),
            "retrieval_records": [
                {
                    "tool_name": "get_company_facts",
                    "status": "ok",
                    "metric_count": 1,
                    "fact_source": "sec_companyfacts",
                    "source_ref_count": 0,
                },
                {
                    "tool_name": "search_filing_sections",
                    "status": "ok",
                    "source_ref_count": 1,
                },
            ],
        }
    )


def cash_flow_synthesis_payload(source_id: str) -> dict[str, object]:
    return {
        "cash_quality_verdict": {
            "headline": "Operating cash flow supports capital returns",
            "earnings_backed_by_cash": "mixed",
            "summary": "Cash generation funded capex and buybacks, with liquidity still cited.",
        },
        "cash_metrics": [
            {
                "name": "Operating cash flow",
                "value": "Evidence-backed",
                "period": "latest_quarter",
                "interpretation": "Operating cash flow is tied to the cited cash flow evidence.",
                "source_ids": [source_id],
                "citation_status": "supported",
            }
        ],
        "capital_allocation": {
            "capex": [
                {
                    "title": "Capex",
                    "summary": "Capital expenditures were funded by operating cash flow.",
                    "source_ids": [source_id],
                    "citation_status": "supported",
                }
            ],
            "buybacks": [
                {
                    "title": "Share repurchases",
                    "summary": "Share repurchases were cited as a use of cash.",
                    "source_ids": [source_id],
                    "citation_status": "supported",
                }
            ],
            "dividends": [],
            "debt": [],
            "liquidity": [
                {
                    "title": "Liquidity",
                    "summary": "Liquidity remained strong in the cited evidence.",
                    "source_ids": [source_id],
                    "citation_status": "partial",
                }
            ],
        },
        "allocation_discipline": [
            {
                "title": "Funding discipline",
                "summary": "The cited evidence links cash generation to capital returns.",
                "source_ids": [source_id],
                "citation_status": "supported",
            }
        ],
        "red_flags": [],
        "claims": [
            {
                "text": "Operating cash flow funded capex and share repurchases.",
                "source_ids": [source_id],
                "citation_status": "supported",
            }
        ],
    }
