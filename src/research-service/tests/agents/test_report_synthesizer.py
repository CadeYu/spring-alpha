from app.agents.deterministic_workflow import DeterministicAgentWorkflow
from app.agents.llm_gateway import StaticJsonLlmClient
from app.agents.report_synthesizer import (
    ReportSynthesisError,
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
