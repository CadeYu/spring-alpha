from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage

from app.agents import business_driver_agent
from app.agents.business_driver_agent import (
    _business_driver_instruction,
    run_business_driver_agent,
)
from app.agents.sentiment_sources import SentimentSourceBlock, SentimentSourceStatus
from app.contracts.agent import AgentRequest, AgentState, TaskPolicy
from app.contracts.research_task import ResearchTaskType


class _StaticSentimentLlm:
    model = "test-model"
    compact_synthesis = False

    def model_copy(self, update: dict[str, Any]) -> _StaticSentimentLlm:
        copied = _StaticSentimentLlm()
        copied.update = update
        return copied

    def invoke(self, payload: dict[str, Any]) -> AIMessage:
        messages = payload["messages"]
        prompt_text = "\n".join(str(message.content) for message in messages)
        assert "Yahoo Finance news" in prompt_text
        assert "StockTwits messages" in prompt_text
        assert "Reddit discussion" in prompt_text
        assert "Do not invent Reddit, X, StockTwits, or news content" in prompt_text
        return AIMessage(
            content=json.dumps(
                {
                    "sentiment_header": {
                        "overall_band": "Mixed",
                        "overall_score": 5.2,
                        "confidence": "medium",
                        "summary": "News and retail sentiment diverge.",
                    },
                    "narrative_snapshot": {
                        "title": "Mixed AI narrative",
                        "summary": (
                            "News is measured while StockTwits is bullish."
                        ),
                        "source_ids": ["sentiment:stocktwits"],
                        "citation_status": "supported",
                    },
                    "bull_bear_narrative": {
                        "bull_case": "Retail traders emphasize AI demand.",
                        "bear_case": "News flow flags valuation risk.",
                        "balanced_read": (
                            "Treat enthusiasm as sentiment, not proof."
                        ),
                    },
                    "source_divergence": {
                        "summary": "Sources diverge.",
                        "news_direction": "mixed",
                        "stocktwits_direction": "bullish",
                        "reddit_direction": "thin",
                    },
                    "noise_warnings": ["Reddit sample is thin."],
                    "claims": [],
                }
            ),
            response_metadata={"latency_ms": 11, "usage": {"total_tokens": 123}},
        )


def test_business_driver_instruction_is_market_sentiment_lane() -> None:
    instruction = _business_driver_instruction(_make_request(language="zh"), _make_state("zh"))

    assert "市场叙事与情绪" in instruction
    assert "Yahoo Finance" in instruction
    assert "StockTwits" in instruction
    assert "Reddit" in instruction
    assert "不要编造 Reddit、X、StockTwits 或新闻内容" in instruction
    assert "search_metric_evidence" not in instruction
    assert "build_evidence_pack" not in instruction


def test_sentiment_agent_prefetches_sources_without_sec_rag_tools(monkeypatch) -> None:
    blocks = [
        SentimentSourceBlock(
            source="yahoo_news",
            status=SentimentSourceStatus.OK,
            item_count=1,
            content="[2026-06-12 · Yahoo Finance] NVDA AI demand remains in focus.",
        ),
        SentimentSourceBlock(
            source="stocktwits",
            status=SentimentSourceStatus.OK,
            item_count=2,
            content="Bullish: 2 (100%) · Bearish: 0 (0%)",
        ),
        SentimentSourceBlock(
            source="reddit",
            status=SentimentSourceStatus.EMPTY,
            item_count=0,
            content="r/stocks: <no posts found mentioning NVDA in the past 7 days>",
        ),
    ]

    def fake_fetch_sources(ticker: str) -> list[SentimentSourceBlock]:
        assert ticker == "NVDA"
        return blocks

    monkeypatch.setattr(
        business_driver_agent,
        "fetch_market_sentiment_sources",
        fake_fetch_sources,
    )

    payload, state = run_business_driver_agent(
        request=_make_request(ticker="NVDA", language="en"),
        state=_make_state("en", ticker="NVDA"),
        llm=_StaticSentimentLlm(),  # type: ignore[arg-type]
        tool_service=object(),  # type: ignore[arg-type]
    )

    assert payload["sentiment_header"]["overall_band"] == "Mixed"
    assert payload["source_divergence"]["stocktwits_direction"] == "bullish"
    assert [event.tool_name for event in state.tool_events if event.tool_name] == [
        "fetch_yahoo_news",
        "fetch_stocktwits",
        "fetch_reddit",
    ]
    assert all(
        record["tool_name"]
        in {"fetch_yahoo_news", "fetch_stocktwits", "fetch_reddit"}
        for record in state.retrieval_records
    )
    assert "search_metric_evidence" not in {
        record["tool_name"] for record in state.retrieval_records
    }


def test_sentiment_agent_recovers_json_when_provider_wraps_content(monkeypatch) -> None:
    blocks = [
        SentimentSourceBlock(
            source="yahoo_news",
            status=SentimentSourceStatus.OK,
            item_count=1,
            content="[2026-06-12 · Yahoo Finance] NVDA sentiment remains AI-led.",
        )
    ]

    class WrappedJsonLlm(_StaticSentimentLlm):
        def model_copy(self, update: dict[str, Any]) -> WrappedJsonLlm:
            copied = WrappedJsonLlm()
            copied.update = update
            return copied

        def invoke(self, payload: dict[str, Any]) -> AIMessage:
            return AIMessage(
                content=(
                    "Here is the JSON:\n"
                    "{\n"
                    '  "sentiment_header": {"overall_band": "Mixed", '
                    '"overall_score": 5.0, "confidence": "medium", '
                    '"summary": "Yahoo Finance is still AI-led."},\n'
                    '  "narrative_snapshot": {"title": "AI narrative", '
                    '"summary": "News frames NVDA around AI demand.", '
                    '"source_ids": ["sentiment:yahoo_news"], '
                    '"citation_status": "supported"},\n'
                    '  "bull_bear_narrative": {"bull_case": "AI demand remains visible.", '
                    '"bear_case": "The source sample is narrow.", '
                    '"balanced_read": "Treat the read as source-limited."},\n'
                    '  "source_divergence": {"summary": "Yahoo only.", '
                    '"news_direction": "mixed", "stocktwits_direction": "unavailable", '
                    '"reddit_direction": "unavailable"},\n'
                    '  "noise_warnings": ["Only one source returned data."],\n'
                    '  "claims": []\n'
                    "}\n"
                    "No other claims."
                )
            )

    monkeypatch.setattr(
        business_driver_agent,
        "fetch_market_sentiment_sources",
        lambda ticker: blocks,
    )

    payload, state = run_business_driver_agent(
        request=_make_request(ticker="NVDA", language="en"),
        state=_make_state("en", ticker="NVDA"),
        llm=WrappedJsonLlm(),  # type: ignore[arg-type]
    )

    assert payload["sentiment_header"]["summary"] == "Yahoo Finance is still AI-led."
    assert state.tool_events[-1].summary == (
        "Sentiment analyst synthesized the market narrative sections."
    )


def test_sentiment_agent_sends_compact_source_context_to_final_llm(monkeypatch) -> None:
    long_lines = "\n".join(
        f"[2026-06-12 · Yahoo Finance] NVDA headline {index}" for index in range(30)
    )
    blocks = [
        SentimentSourceBlock(
            source="yahoo_news",
            status=SentimentSourceStatus.OK,
            item_count=30,
            content=long_lines,
        )
    ]

    captured_prompt = []

    class CapturingLlm(_StaticSentimentLlm):
        def model_copy(self, update: dict[str, Any]) -> CapturingLlm:
            copied = CapturingLlm()
            copied.update = update
            return copied

        def invoke(self, payload: dict[str, Any]) -> AIMessage:
            messages = payload["messages"]
            captured_prompt.append("\n".join(str(message.content) for message in messages))
            return super().invoke(payload)

    llm = CapturingLlm()
    monkeypatch.setattr(
        business_driver_agent,
        "fetch_market_sentiment_sources",
        lambda ticker: blocks,
    )

    run_business_driver_agent(
        request=_make_request(ticker="NVDA", language="en"),
        state=_make_state("en", ticker="NVDA"),
        llm=llm,  # type: ignore[arg-type]
    )

    assert captured_prompt
    prompt_text = captured_prompt[-1]
    assert '"key_lines"' in prompt_text
    assert "headline 0" in prompt_text
    assert "headline 7" in prompt_text
    assert "headline 8" not in prompt_text
    assert "<source_content>" not in prompt_text


def _make_request(
    *,
    ticker: str = "AMD",
    language: str,
) -> AgentRequest:
    return AgentRequest(
        run_id="run_1",
        ticker=ticker,
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language=language,
    )


def _make_state(language: str, *, ticker: str = "AMD") -> AgentState:
    return AgentState(
        run_id="run_1",
        ticker=ticker,
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language=language,
        task_policy=TaskPolicy(
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            allowed_tools=[
                "get_market_context",
            ],
            required_outputs=[
                "sentimentHeader",
                "narrativeSnapshot",
                "bullBearNarrative",
                "sourceDivergence",
            ],
        ),
    )
