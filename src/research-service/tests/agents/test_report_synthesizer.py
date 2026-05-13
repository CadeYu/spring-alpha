import app.agents.report_synthesizer as report_synthesizer
from app.agents.llm_gateway import StaticJsonLlmClient
from app.agents.report_synthesizer import (
    ReportSynthesisError,
    build_business_driver_report_from_payload,
    build_cash_flow_report_from_payload,
    build_latest_earnings_report_from_payload,
    synthesize_business_driver_report,
    synthesize_cash_flow_report,
    synthesize_company_profile,
    synthesize_latest_earnings_report,
)
from app.contracts.agent import (
    AgentRequest,
    AgentState,
    LlmProvider,
    default_task_policy,
)
from app.contracts.report import CitationStatus
from app.contracts.research_task import ResearchTaskType


class CapturingLlmClient:
    provider = LlmProvider.OPENAI

    def __init__(self, content: dict[str, object]) -> None:
        self._delegate = StaticJsonLlmClient(content)
        self.user_prompt: str | None = None

    def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
        self.user_prompt = llm_request.user_prompt
        return self._delegate.complete_json(llm_request)


class TimeoutCapturingLlmClient:
    provider = LlmProvider.OPENAI

    def __init__(self, content: dict[str, object]) -> None:
        self._delegate = StaticJsonLlmClient(content)
        self.timeout_seconds: int | None = None

    def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
        self.timeout_seconds = llm_request.timeout_seconds
        return self._delegate.complete_json(llm_request)


class ProfileFallbackLlmClient:
    provider = LlmProvider.OPENAI

    def __init__(self) -> None:
        self.user_prompts: list[str] = []
        self.timeout_seconds: list[int] = []

    def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
        self.user_prompts.append(llm_request.user_prompt)
        self.timeout_seconds.append(llm_request.timeout_seconds)
        if "Write a concise investor-facing company profile" in llm_request.user_prompt:
            return StaticJsonLlmClient(
                {
                    "summary": (
                        "Apple Inc. is a global consumer technology company anchored by "
                        "iPhone, Mac, iPad, wearables, and a growing services ecosystem."
                    )
                }
            ).complete_json(llm_request)
        raise ValueError("full report synthesis unavailable")


def latest_earnings_synthesis_payload(source_id: str) -> dict[str, object]:
    return {
        "topline_verdict": {
            "headline": "Evidence-bound timeout test",
            "summary": "The synthesized report used bounded provider timing.",
            "verdict": "mixed",
        },
        "key_takeaways": [],
        "financial_dashboard": {"metrics": [], "chart_focus": []},
        "driver_snapshot": [],
        "risk_snapshot": [],
        "claims": [
            {
                "text": "The synthesized report cited available evidence.",
                "source_ids": [source_id],
                "citation_status": "supported",
            }
        ],
    }


def test_synthesizer_uses_bounded_default_timeout() -> None:
    client = TimeoutCapturingLlmClient(latest_earnings_synthesis_payload("src_1"))

    synthesize_latest_earnings_report(request(), state_with_evidence(), client)

    assert client.timeout_seconds == 5


def test_synthesizer_timeout_can_be_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AGENT_SYNTHESIS_TIMEOUT_SECONDS", "12")
    client = TimeoutCapturingLlmClient(latest_earnings_synthesis_payload("src_1"))

    synthesize_latest_earnings_report(request(), state_with_evidence(), client)

    assert client.timeout_seconds == 12


def test_synthesizer_retries_can_be_configured(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AGENT_SYNTHESIS_RETRIES", "2")

    class FailingClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
            self.calls += 1
            raise ValueError("provider unavailable")

    client = FailingClient()

    try:
        report_synthesizer._complete_synthesis_json(  # noqa: SLF001
            client,
            report_synthesizer.LlmRequest(
                run_id="run_timeout_test",
                provider=client.provider,
                model="test-model",
                task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
                system_prompt="Return JSON.",
                user_prompt="Return JSON.",
                state=state_with_evidence(),
                timeout_seconds=35,
            ),
        )
    except ReportSynthesisError:
        pass

    assert client.calls == 2


def test_synthesizer_builds_latest_earnings_sections_from_evidence() -> None:
    state = state_with_evidence()
    client = StaticJsonLlmClient(
        {
            "company_profile": {
                "summary": (
                    "Apple designs consumer devices, software, and services for a global "
                    "installed base."
                ),
                "source_ids": ["src_1"],
                "citation_status": "supported",
            },
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
    assert report.task_sections.company_profile is not None
    assert report.task_sections.company_profile.summary.startswith("Apple designs")
    assert report.task_sections.company_profile.evidence_refs[0].source_id == "src_1"
    assert report.task_sections.key_takeaways[0].evidence_refs[0].source_id == "src_1"
    assert report.claims[0].source_refs[0].source_id == "src_1"
    assert "Deterministic latest earnings" not in report.claims[0].text


def test_synthesizer_normalizes_deepseek_string_profile_and_claims() -> None:
    state = state_with_evidence()

    report = build_latest_earnings_report_from_payload(
        request(),
        state,
        {
            "company_profile": (
                "Apple Inc. designs consumer devices, software, and services for a "
                "global installed base."
            ),
            "topline_verdict": {
                "headline": "Services demand frames the quarter",
                "summary": "Evidence points to stronger services demand.",
                "verdict": "mixed",
            },
            "key_takeaways": [],
            "financial_dashboard": {"metrics": [], "chart_focus": []},
            "driver_snapshot": [],
            "risk_snapshot": [],
            "claims": [
                "Services demand improved based on management commentary.",
                "The evidence base remains limited to the cited filing context.",
            ],
        },
    )

    assert report.task_sections.company_profile is not None
    assert report.task_sections.company_profile.summary.startswith("Apple Inc. designs")
    assert report.task_sections.company_profile.citation_status == CitationStatus.UNVERIFIED
    assert report.claims[0].text == (
        "Services demand improved based on management commentary."
    )
    assert report.claims[0].citation_status == CitationStatus.UNVERIFIED


def test_synthesizer_normalizes_deepseek_object_cash_metrics() -> None:
    state = state_with_cash_flow_evidence()

    report = build_cash_flow_report_from_payload(
        cash_flow_request(),
        state,
        {
            "cash_quality_verdict": {
                "headline": "Cash generation supports earnings quality",
                "earnings_backed_by_cash": "yes",
                "summary": "Operating cash flow supports the earnings base.",
            },
            "cash_metrics": {
                "operating_cash_flow": "$32.0B",
                "capital_expenditures": "$3.0B",
            },
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
        },
    )

    assert [metric.name for metric in report.task_sections.cash_metrics] == [
        "operating_cash_flow",
        "capital_expenditures",
    ]
    assert report.task_sections.cash_metrics[0].value == "$32.0B"


def test_synthesizer_normalizes_provider_signal_points() -> None:
    state = state_with_business_driver_evidence()

    report = build_business_driver_report_from_payload(
        business_driver_request(),
        state,
        {
            "driver_thesis": {
                "headline": "Services demand is the primary driver",
                "durability": "durable",
                "summary": "Services demand and engagement are the clearest drivers.",
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
            "positive_signals": [
                {
                    "signal": "Services revenue and gross margin expansion",
                    "source_id": "driver_src_1",
                }
            ],
            "negative_signals": [],
            "watchlist": [],
            "claims": [],
        },
    )

    assert report.task_sections.positive_signals[0].title == (
        "Services revenue and gross margin expansion"
    )
    assert report.task_sections.positive_signals[0].summary == (
        "Services revenue and gross margin expansion"
    )
    assert report.task_sections.positive_signals[0].evidence_refs[0].source_id == (
        "driver_src_1"
    )


def test_synthesizer_normalizes_provider_citation_status_aliases() -> None:
    state = state_with_evidence()
    client = StaticJsonLlmClient(
        {
            "company_profile": {
                "summary": "Apple designs consumer technology products and services.",
                "source_ids": ["src_1"],
                "citation_status": "verified",
            },
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
                    "citation_status": "verified",
                }
            ],
            "financial_dashboard": {
                "metrics": [
                    {
                        "name": "Revenue",
                        "value": "$90.0B",
                        "period": "latest_quarter",
                        "interpretation": "Revenue context is tied to cited evidence.",
                        "source_ids": ["src_1"],
                        "citation_status": "verified",
                    }
                ],
                "chart_focus": ["revenue"],
            },
            "driver_snapshot": [],
            "risk_snapshot": [],
            "claims": [
                {
                    "text": "Services demand improved based on management commentary.",
                    "source_ids": ["src_1"],
                    "citation_status": "verified",
                }
            ],
        }
    )

    report = synthesize_latest_earnings_report(request(), state, client)

    assert report.task_sections.company_profile.citation_status == CitationStatus.SUPPORTED
    assert report.task_sections.key_takeaways[0].citation_status == CitationStatus.SUPPORTED
    assert report.task_sections.financial_dashboard.metrics[0].citation_status == (
        CitationStatus.SUPPORTED
    )
    assert report.claims[0].citation_status == CitationStatus.SUPPORTED


def test_synthesizer_backfills_company_profile_from_facts_when_llm_omits_it() -> None:
    base_state = state_with_evidence()
    state = base_state.model_copy(
        update={
            "evidence_memory": base_state.evidence_memory.model_copy(
                update={
                    "facts": {
                        **base_state.evidence_memory.facts,
                        "business_summary": (
                            "Apple designs consumer devices, software, and services for "
                            "customers worldwide."
                        ),
                    }
                }
            )
        }
    )
    client = StaticJsonLlmClient(
        {
            "company_profile": None,
            "topline_verdict": {
                "headline": "Services demand is carrying a mixed earnings setup",
                "summary": "Services demand improved, while the evidence base remains narrow.",
                "verdict": "mixed",
            },
            "key_takeaways": [],
            "financial_dashboard": {"metrics": [], "chart_focus": []},
            "driver_snapshot": [],
            "risk_snapshot": [],
            "claims": [],
        }
    )

    report = synthesize_latest_earnings_report(request(), state, client)

    assert report.task_sections.company_profile is not None
    assert report.task_sections.company_profile.summary == (
        "Apple designs consumer devices, software, and services for customers worldwide."
    )
    assert report.task_sections.company_profile.evidence_refs == []
    assert report.task_sections.company_profile.citation_status == CitationStatus.UNVERIFIED


def test_company_profile_backfill_is_concise() -> None:
    long_summary = (
        "Apple Inc. designs, manufactures, and markets smartphones, personal computers, "
        "tablets, wearables, and accessories worldwide. "
        "The company offers iPhone, Mac, iPad, AirPods, Apple Watch, Apple TV, and "
        "HomePod, along with AppleCare, cloud services, App Store, advertising, and "
        "subscription services. "
        "It serves consumers, businesses, education, enterprise, and government markets "
        "through retail, online stores, direct sales, carriers, and resellers. "
        "The company was founded in 1976 and is headquartered in Cupertino, California."
    )
    base_state = state_with_evidence()
    state = base_state.model_copy(
        update={
            "evidence_memory": base_state.evidence_memory.model_copy(
                update={"facts": {"business_summary": long_summary}}
            )
        }
    )
    client = StaticJsonLlmClient(
        {
            "company_profile": None,
            "topline_verdict": {
                "headline": "Profile backfill",
                "summary": "Profile should be concise.",
                "verdict": "mixed",
            },
            "key_takeaways": [],
            "financial_dashboard": {"metrics": [], "chart_focus": []},
            "driver_snapshot": [],
            "risk_snapshot": [],
            "claims": [],
        }
    )

    report = synthesize_latest_earnings_report(request(), state, client)

    assert report.task_sections.company_profile is not None
    assert report.task_sections.company_profile.summary == (
        "Apple Inc. designs, manufactures, and markets smartphones, personal computers, "
        "tablets, wearables, and accessories worldwide. The company offers iPhone, Mac, "
        "iPad, AirPods, Apple Watch, Apple TV, and HomePod, along with AppleCare, cloud "
        "services, App Store, advertising, and subscription services."
    )


def test_company_profile_writer_uses_tradingagents_style_fundamentals_prompt() -> None:
    base_state = state_with_evidence()
    state = base_state.model_copy(
        update={
            "evidence_memory": base_state.evidence_memory.model_copy(
                update={
                    "facts": {
                        "company_name": "NVIDIA Corporation",
                        "market_sector": "Technology",
                        "market_industry": "Semiconductors",
                        "business_summary": (
                            "NVIDIA Corporation provides graphics, compute, and networking "
                            "solutions for gaming, data center, professional visualization, "
                            "automotive, and robotics markets."
                        ),
                    }
                }
            )
        }
    )
    client = CapturingLlmClient(
        {
            "summary": (
                "NVIDIA Corporation is a semiconductor and accelerated computing leader "
                "serving gaming, data center, AI, automotive, and robotics markets."
            )
        }
    )

    profile = synthesize_company_profile(request(), state, client)

    assert profile is not None
    assert profile.summary == (
        "NVIDIA Corporation is a semiconductor and accelerated computing leader serving "
        "gaming, data center, AI, automotive, and robotics markets."
    )
    assert client.user_prompt is not None
    assert "Write a concise investor-facing company profile" in client.user_prompt
    assert "Mention business identity, core products, and primary markets" in client.user_prompt
    assert "founding history" in client.user_prompt


def test_latest_earnings_prompt_keeps_risk_evidence_out_of_topline() -> None:
    state = state_with_evidence()
    client = CapturingLlmClient(
        {
            "topline_verdict": {
                "headline": "Services demand is carrying a mixed earnings setup",
                "summary": "Services demand improved, while risk disclosures remain separate.",
                "verdict": "mixed",
            },
            "key_takeaways": [],
            "financial_dashboard": {"metrics": [], "chart_focus": []},
            "driver_snapshot": [],
            "risk_snapshot": [],
            "claims": [],
        }
    )

    synthesize_latest_earnings_report(request(), state, client)

    assert client.user_prompt is not None
    assert "Risk disclosure evidence belongs only in risk_snapshot" in client.user_prompt


def test_latest_earnings_prompt_includes_metric_evidence_values() -> None:
    base_state = state_with_evidence()
    state = base_state.model_copy(
        update={
            "evidence_memory": base_state.evidence_memory.model_copy(
                update={
                    "metric_evidence": [
                        {
                            "metric": "revenue",
                            "normalized_metric": "revenue",
                            "value": 95359000000,
                            "unit": "USD",
                            "period": "latest_quarter",
                            "fact_period": "2026Q2",
                            "source": "sec_companyfacts",
                            "source_id": "src_1",
                        }
                    ]
                }
            )
        }
    )
    client = CapturingLlmClient(
        {
            "topline_verdict": {
                "headline": "Revenue is now visible to the earnings panel",
                "summary": "The dashboard can use numeric SEC companyfacts evidence.",
                "verdict": "positive",
            },
            "key_takeaways": [],
            "financial_dashboard": {
                "metrics": [
                    {
                        "name": "Revenue",
                        "value": "$95.4B",
                        "period": "2026Q2",
                        "interpretation": "Revenue is backed by SEC companyfacts evidence.",
                        "source_ids": ["src_1"],
                        "citation_status": "supported",
                    }
                ],
                "chart_focus": ["revenue"],
            },
            "driver_snapshot": [],
            "risk_snapshot": [],
            "claims": [],
        }
    )

    synthesize_latest_earnings_report(request(), state, client)

    assert client.user_prompt is not None
    assert "Metric evidence:" in client.user_prompt
    assert "95359000000" in client.user_prompt
    assert "sec_companyfacts" in client.user_prompt


def test_latest_earnings_prompt_instructs_kpi_strip_to_use_metric_values() -> None:
    state = state_with_evidence()
    client = CapturingLlmClient(
        {
            "topline_verdict": {
                "headline": "Metric evidence should drive KPI values",
                "summary": "The prompt tells the provider to use metric evidence values.",
                "verdict": "mixed",
            },
            "key_takeaways": [],
            "financial_dashboard": {
                "metrics": [
                    {
                        "name": "Revenue",
                        "value": "$95.4B",
                        "period": "2026Q2",
                        "interpretation": "Metric evidence drives the KPI strip.",
                        "source_ids": ["src_1"],
                        "citation_status": "supported",
                    }
                ],
                "chart_focus": ["revenue"],
            },
            "driver_snapshot": [],
            "risk_snapshot": [],
            "claims": [],
        }
    )

    synthesize_latest_earnings_report(request(), state, client)

    assert client.user_prompt is not None
    assert "Use Metric evidence values for financial_dashboard.metrics" in client.user_prompt
    assert "revenue, gross margin, and operating income" in client.user_prompt


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


def test_synthesizer_accepts_sec_companyfacts_source_alias() -> None:
    state = state_with_sec_companyfacts_evidence()
    payload = {
        "topline_verdict": {
            "headline": "Company facts can support the KPI view",
            "summary": "SEC company facts support the reported revenue value.",
            "verdict": "mixed",
        },
        "key_takeaways": [],
        "financial_dashboard": {
            "metrics": [
                {
                    "name": "Revenue",
                    "value": "$90.0B",
                    "period": "2026Q1",
                    "interpretation": "Revenue came from SEC company facts.",
                    "source_ids": ["sec_companyfacts"],
                    "citation_status": "supported",
                }
            ],
            "chart_focus": ["revenue"],
        },
        "driver_snapshot": [],
        "risk_snapshot": [],
        "claims": [
            {
                "text": "Revenue was supported by SEC company facts.",
                "source_ids": ["sec_companyfacts"],
                "citation_status": "supported",
            }
        ],
    }

    report = build_latest_earnings_report_from_payload(request(), state, payload)

    metric_ref = report.task_sections.financial_dashboard.metrics[0].evidence_refs[0]
    assert metric_ref.source_id == "run_synthesis_001:sec_companyfacts:revenue"
    assert report.claims[0].source_refs[0].source_id == (
        "run_synthesis_001:sec_companyfacts:revenue"
    )


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


def test_business_driver_prompt_prioritizes_operating_drivers_over_compliance() -> None:
    state = state_with_business_driver_evidence()
    client = CapturingLlmClient(
        {
            "driver_thesis": {
                "headline": "Services engagement is the primary business driver",
                "durability": "mixed",
                "summary": "The cited filing evidence points to services demand and engagement.",
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
            "watchlist": ["Monitor regulatory cost as a secondary risk."],
            "claims": [],
        }
    )

    synthesize_business_driver_report(business_driver_request(), state, client)

    assert client.user_prompt is not None
    assert "Prioritize operating drivers" in client.user_prompt
    assert "Regulatory, compliance, legal, or market-risk evidence belongs in risks" in (
        client.user_prompt
    )
    assert "must not be the main driver_thesis" in client.user_prompt


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


def test_business_driver_synthesizer_normalizes_node_payload_points() -> None:
    state = state_with_business_driver_evidence()
    source_id = state.evidence_memory.source_refs[0]["source_id"]
    payload = {
        "driver_thesis": {
            "headline": "Services engagement is the primary business driver",
            "durability": "mixed",
            "summary": "The cited filing evidence points to services demand and engagement.",
        },
        "driver_map": {
            "product": [
                {
                    "node_id": source_id,
                    "text": "Services revenue was supported by subscriptions and engagement.",
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
        "watchlist": ["Monitor whether services engagement persists."],
        "claims": [],
    }

    report = report_synthesizer.build_business_driver_report_from_payload(
        business_driver_request(),
        state,
        payload,
    )

    point = report.task_sections.driver_map.product[0]
    assert point.title == "Evidence node"
    assert point.summary == "Services revenue was supported by subscriptions and engagement."
    assert point.evidence_refs[0].source_id == source_id


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


def test_cash_flow_prompt_requires_separate_capital_allocation_categories() -> None:
    state = state_with_cash_flow_evidence()
    client = CapturingLlmClient(cash_flow_synthesis_payload("cash_src_1"))

    synthesize_cash_flow_report(cash_flow_request(), state, client)

    assert client.user_prompt is not None
    assert "separate capital_allocation categories" in client.user_prompt
    assert "Do not collapse all capital return evidence into liquidity" in client.user_prompt


def test_cash_flow_synthesizer_rejects_unknown_source_ids() -> None:
    state = state_with_cash_flow_evidence()
    client = StaticJsonLlmClient(cash_flow_synthesis_payload("missing_cash_source"))

    try:
        synthesize_cash_flow_report(cash_flow_request(), state, client)
    except ReportSynthesisError as exc:
        assert "Unknown source_id" in str(exc)
    else:
        raise AssertionError("cash flow synthesizer should reject unknown source ids")


def test_cash_flow_synthesizer_normalizes_value_payload_points() -> None:
    state = state_with_cash_flow_evidence()
    payload = cash_flow_synthesis_payload("cash_src_1")
    payload["capital_allocation"]["capex"] = [
        {
            "value": 3000000000,
            "period": "2026Q1",
            "source_ids": ["cash_src_1"],
            "citation_status": "supported",
        }
    ]

    report = report_synthesizer.build_cash_flow_report_from_payload(
        cash_flow_request(),
        state,
        payload,
    )

    point = report.task_sections.capital_allocation.capex[0]
    assert point.title == "Capital allocation item"
    assert point.summary == "Value was 3000000000 for 2026Q1."
    assert point.evidence_refs[0].source_id == "cash_src_1"


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


def test_synthesizer_does_not_retry_transient_llm_json_failure_by_default() -> None:
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

    try:
        synthesize_latest_earnings_report(request(), state_with_evidence(), client)
    except ReportSynthesisError:
        pass

    assert client.calls == 1


def test_synthesizer_retries_transient_llm_json_failure_when_configured(
    monkeypatch,
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AGENT_SYNTHESIS_RETRIES", "2")

    class FlakyClient:
        provider = LlmProvider.OPENAI

        def __init__(self) -> None:
            self.calls = 0

        def complete_json(self, llm_request):  # type: ignore[no-untyped-def]
            self.calls += 1
            if self.calls == 1:
                raise ValueError("bad provider JSON")
            return StaticJsonLlmClient(latest_earnings_synthesis_payload("src_1")).complete_json(
                llm_request
            )

    client = FlakyClient()

    report = synthesize_latest_earnings_report(request(), state_with_evidence(), client)

    assert client.calls == 2
    assert report.task_sections.topline_verdict.headline == "Evidence-bound timeout test"


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


def test_latest_earnings_metric_evidence_overrides_non_extracted_provider_value() -> None:
    base_state = state_with_evidence()
    state = base_state.model_copy(
        update={
            "evidence_memory": base_state.evidence_memory.model_copy(
                update={
                    "source_refs": [
                        {
                            "source_id": "fact_revenue",
                            "section": "SEC companyfacts",
                            "snippet": (
                                "SEC companyfacts "
                                "RevenueFromContractWithCustomerExcludingAssessedTax "
                                "reports revenue of 95359000000 USD for 2026Q2 filed 2026-05-01."
                            ),
                            "filing_type": "10-Q",
                            "filing_date": "2026-05-01",
                            "accession_number": "0000320193-26-000021",
                            "citation_status": "supported",
                        }
                    ],
                    "metric_evidence": [
                        {
                            "metric": "revenue",
                            "normalized_metric": "revenue",
                            "value": 95359000000,
                            "unit": "USD",
                            "fact_period": "2026Q2",
                            "source": "sec_companyfacts",
                            "source_id": "fact_revenue",
                            "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                        }
                    ],
                }
            )
        }
    )
    client = StaticJsonLlmClient(
        {
            "topline_verdict": {
                "headline": "Provider stayed cautious",
                "summary": "The provider did not use the metric evidence value.",
                "verdict": "mixed",
            },
            "key_takeaways": [],
            "financial_dashboard": {
                "metrics": [
                    {
                        "name": "Revenue",
                        "value": "Not discernible in provided snippet",
                        "period": "latest_quarter",
                        "interpretation": "Specific Financial Figures Not Extracted.",
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
    )

    report = synthesize_latest_earnings_report(request(), state, client)

    metric = report.task_sections.financial_dashboard.metrics[0]
    assert metric.value == "$95.4B"
    assert metric.period == "2026Q2"
    assert metric.citation_status == CitationStatus.SUPPORTED
    assert metric.evidence_refs[0].source_id == "fact_revenue"


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


def state_with_sec_companyfacts_evidence() -> AgentState:
    state = state_with_evidence()
    return state.model_copy(
        update={
            "evidence_memory": state.evidence_memory.model_copy(
                update={
                    "source_refs": [
                        {
                            "source_id": "run_synthesis_001:sec_companyfacts:revenue",
                            "section": "SEC companyfacts",
                            "snippet": "SEC companyfacts reports revenue of 90000000000 USD.",
                            "citation_status": "supported",
                        }
                    ],
                    "metric_evidence": [
                        {
                            "metric": "revenue",
                            "period": "2026Q1",
                            "source_id": "run_synthesis_001:sec_companyfacts:revenue",
                        }
                    ],
                }
            )
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
