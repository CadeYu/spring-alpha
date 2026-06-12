from __future__ import annotations

from threading import Event, Thread
from urllib.error import HTTPError

from app.agents.sentiment_sources import (
    SentimentSourceStatus,
    fetch_reddit_discussion,
    fetch_stocktwits_messages,
    fetch_yahoo_finance_news,
)


def test_stocktwits_formats_bullish_bearish_counts() -> None:
    def transport(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
        assert "streams/symbol/NVDA.json" in url
        assert timeout > 0
        assert headers["Accept"] == "application/json"
        return {
            "messages": [
                {
                    "created_at": "2026-06-12T01:00:00Z",
                    "user": {"username": "bull_one"},
                    "entities": {"sentiment": {"basic": "Bullish"}},
                    "body": "$NVDA demand still looks strong.",
                },
                {
                    "created_at": "2026-06-12T01:01:00Z",
                    "user": {"username": "risk_check"},
                    "entities": {"sentiment": {"basic": "Bearish"}},
                    "body": "Valuation risk is rising.",
                },
            ]
        }

    block = fetch_stocktwits_messages("nvda", transport=transport)

    assert block.source == "stocktwits"
    assert block.status == SentimentSourceStatus.OK
    assert block.item_count == 2
    assert "Bullish: 1" in block.content
    assert "Bearish: 1" in block.content
    assert "@bull_one" in block.content
    assert "$NVDA demand still looks strong." in block.content


def test_reddit_formats_discussion_posts_from_json() -> None:
    def transport(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
        assert "reddit.com/r/stocks/search.json" in url
        return {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "AAPL services narrative",
                            "score": 42,
                            "num_comments": 7,
                            "created_utc": 1781200000,
                            "selftext": "Investors are debating services growth.",
                        }
                    }
                ]
            }
        }

    block = fetch_reddit_discussion(
        "AAPL",
        subreddits=("stocks",),
        transport=transport,
        inter_request_delay=0,
        rate_limit_interval_seconds=0,
    )

    assert block.source == "reddit"
    assert block.status == SentimentSourceStatus.OK
    assert block.item_count == 1
    assert "r/stocks" in block.content
    assert "AAPL services narrative" in block.content
    assert "42" in block.content
    assert "Investors are debating services growth." in block.content


def test_reddit_falls_back_to_rss_when_json_search_is_blocked() -> None:
    seen_urls: list[str] = []

    def json_transport(
        url: str, timeout: float, headers: dict[str, str]
    ) -> dict[str, object]:
        seen_urls.append(url)
        assert headers["Accept"] == "application/json"
        raise HTTPError(url, 403, "Blocked", hdrs=None, fp=None)

    def text_transport(url: str, timeout: float, headers: dict[str, str]) -> str:
        seen_urls.append(url)
        assert "reddit.com/r/wallstreetbets/search.rss" in url
        assert "User-Agent" in headers
        return """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>NVDA retail sentiment after earnings</title>
    <published>2026-06-12T08:15:00Z</published>
    <content type="html">
      &lt;!-- SC_OFF --&gt;
      &lt;p&gt;Traders are debating AI demand and valuation risk.&lt;/p&gt;
      &lt;!-- SC_ON --&gt;
    </content>
  </entry>
</feed>"""

    block = fetch_reddit_discussion(
        "NVDA",
        subreddits=("wallstreetbets",),
        transport=json_transport,
        text_transport=text_transport,
        inter_request_delay=0,
        rate_limit_interval_seconds=0,
    )

    assert seen_urls[0].endswith("/search.json?q=NVDA&restrict_sr=on&sort=new&t=week&limit=5")
    assert "/search.rss?" in seen_urls[1]
    assert block.source == "reddit"
    assert block.status == SentimentSourceStatus.OK
    assert block.item_count == 1
    assert block.degraded_reason is None
    assert "via RSS feed; scores/comments unavailable" in block.content
    assert "NVDA retail sentiment after earnings" in block.content
    assert "Traders are debating AI demand and valuation risk." in block.content
    assert "↑ ·" not in block.content


def test_reddit_discussion_reuses_cached_block_within_ttl() -> None:
    calls = 0
    now = 1_000.0

    def transport(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        title = f"NVDA cached sentiment sample {calls}"
        return {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": title,
                            "score": 10 + calls,
                            "num_comments": 3,
                            "created_utc": 1781200000,
                            "selftext": "Investors are debating AI demand.",
                        }
                    }
                ]
            }
        }

    def clock() -> float:
        return now

    first = fetch_reddit_discussion(
        "NVDA",
        subreddits=("stocks",),
        transport=transport,
        inter_request_delay=0,
        cache_ttl_seconds=60,
        rate_limit_interval_seconds=0,
        clock=clock,
    )
    second = fetch_reddit_discussion(
        "NVDA",
        subreddits=("stocks",),
        transport=transport,
        inter_request_delay=0,
        cache_ttl_seconds=60,
        rate_limit_interval_seconds=0,
        clock=clock,
    )
    now = 1_061.0
    third = fetch_reddit_discussion(
        "NVDA",
        subreddits=("stocks",),
        transport=transport,
        inter_request_delay=0,
        cache_ttl_seconds=60,
        rate_limit_interval_seconds=0,
        clock=clock,
    )

    assert calls == 2
    assert "NVDA cached sentiment sample 1" in first.content
    assert "NVDA cached sentiment sample 1" in second.content
    assert "NVDA cached sentiment sample 2" in third.content


def test_reddit_discussion_caches_degraded_block_for_short_ttl() -> None:
    calls = 0
    now = 2_000.0

    def transport(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise TimeoutError("reddit json timed out")

    def text_transport(url: str, timeout: float, headers: dict[str, str]) -> str:
        raise TimeoutError("reddit rss timed out")

    def clock() -> float:
        return now

    first = fetch_reddit_discussion(
        "TSLA",
        subreddits=("stocks",),
        transport=transport,
        text_transport=text_transport,
        inter_request_delay=0,
        cache_ttl_seconds=600,
        degraded_cache_ttl_seconds=30,
        rate_limit_interval_seconds=0,
        clock=clock,
    )
    second = fetch_reddit_discussion(
        "TSLA",
        subreddits=("stocks",),
        transport=transport,
        text_transport=text_transport,
        inter_request_delay=0,
        cache_ttl_seconds=600,
        degraded_cache_ttl_seconds=30,
        rate_limit_interval_seconds=0,
        clock=clock,
    )
    now = 2_031.0
    third = fetch_reddit_discussion(
        "TSLA",
        subreddits=("stocks",),
        transport=transport,
        text_transport=text_transport,
        inter_request_delay=0,
        cache_ttl_seconds=600,
        degraded_cache_ttl_seconds=30,
        rate_limit_interval_seconds=0,
        clock=clock,
    )

    assert calls == 2
    assert first.status == SentimentSourceStatus.DEGRADED
    assert second.status == SentimentSourceStatus.DEGRADED
    assert third.status == SentimentSourceStatus.DEGRADED


def test_reddit_discussion_uses_stale_success_when_refresh_is_rate_limited() -> None:
    calls = 0
    now = 3_000.0

    def transport(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "AMD stale but useful Reddit sample",
                                "score": 12,
                                "num_comments": 4,
                                "created_utc": 1781200000,
                                "selftext": "Investors are debating AI GPU traction.",
                            }
                        }
                    ]
                }
            }
        raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)

    def text_transport(url: str, timeout: float, headers: dict[str, str]) -> str:
        raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)

    def clock() -> float:
        return now

    first = fetch_reddit_discussion(
        "AMD",
        subreddits=("stocks",),
        transport=transport,
        text_transport=text_transport,
        inter_request_delay=0,
        cache_ttl_seconds=30,
        stale_ttl_seconds=3_600,
        rate_limit_interval_seconds=0,
        clock=clock,
    )
    now = 3_031.0
    second = fetch_reddit_discussion(
        "AMD",
        subreddits=("stocks",),
        transport=transport,
        text_transport=text_transport,
        inter_request_delay=0,
        cache_ttl_seconds=30,
        stale_ttl_seconds=3_600,
        rate_limit_interval_seconds=0,
        clock=clock,
    )

    assert calls == 2
    assert first.status == SentimentSourceStatus.OK
    assert second.status == SentimentSourceStatus.OK
    assert "AMD stale but useful Reddit sample" in second.content
    assert "stale reddit cache" in (second.degraded_reason or "")


def test_reddit_discussion_short_circuits_after_repeated_rate_limits() -> None:
    calls = 0
    now = 4_000.0

    def transport(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)

    def text_transport(url: str, timeout: float, headers: dict[str, str]) -> str:
        raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)

    def clock() -> float:
        return now

    first = fetch_reddit_discussion(
        "ALB",
        subreddits=("stocks",),
        transport=transport,
        text_transport=text_transport,
        inter_request_delay=0,
        cache_ttl_seconds=0,
        degraded_cache_ttl_seconds=0,
        stale_ttl_seconds=0,
        circuit_breaker_seconds=120,
        rate_limit_interval_seconds=0,
        clock=clock,
    )
    second = fetch_reddit_discussion(
        "ALGN",
        subreddits=("stocks",),
        transport=transport,
        text_transport=text_transport,
        inter_request_delay=0,
        cache_ttl_seconds=0,
        degraded_cache_ttl_seconds=0,
        stale_ttl_seconds=0,
        circuit_breaker_seconds=120,
        rate_limit_interval_seconds=0,
        clock=clock,
    )

    assert calls == 1
    assert first.status == SentimentSourceStatus.DEGRADED
    assert second.status == SentimentSourceStatus.DEGRADED
    assert "reddit public endpoints temporarily rate limited" in second.content
    assert "circuit breaker" in (second.degraded_reason or "")


def test_reddit_discussion_coalesces_concurrent_fetches_for_same_key() -> None:
    calls = 0
    entered_fetch = Event()
    release = Event()

    def transport(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        entered_fetch.set()
        release.wait(timeout=2)
        return {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "PLTR one shared Reddit fetch",
                            "score": 22,
                            "num_comments": 6,
                            "created_utc": 1781200000,
                            "selftext": "Investors are debating government AI demand.",
                        }
                    }
                ]
            }
        }

    results: list[str] = []
    errors: list[BaseException] = []

    def worker() -> None:
        try:
            block = fetch_reddit_discussion(
                "PLTR",
                subreddits=("stocks",),
                transport=transport,
                inter_request_delay=0,
                cache_ttl_seconds=60,
                rate_limit_interval_seconds=0,
            )
            results.append(block.content)
        except BaseException as exc:
            errors.append(exc)

    first = Thread(target=worker)
    first.start()
    assert entered_fetch.wait(timeout=2)
    second = Thread(target=worker)
    second.start()
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not errors
    assert calls == 1
    assert len(results) == 2
    assert all("PLTR one shared Reddit fetch" in content for content in results)


def test_yahoo_news_formats_headlines() -> None:
    def transport(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
        assert "finance/search" in url
        return {
            "news": [
                {
                    "title": "Microsoft AI demand supports cloud narrative",
                    "publisher": "Yahoo Finance",
                    "providerPublishTime": 1781200000,
                    "link": "https://example.com/msft",
                }
            ]
        }

    block = fetch_yahoo_finance_news("MSFT", transport=transport)

    assert block.source == "yahoo_news"
    assert block.status == SentimentSourceStatus.OK
    assert block.item_count == 1
    assert "Microsoft AI demand supports cloud narrative" in block.content
    assert "Yahoo Finance" in block.content


def test_source_fetcher_degrades_on_transport_failure() -> None:
    def transport(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
        raise TimeoutError("read operation timed out")

    block = fetch_stocktwits_messages("TSLA", transport=transport)

    assert block.source == "stocktwits"
    assert block.status == SentimentSourceStatus.DEGRADED
    assert block.item_count == 0
    assert "unavailable" in block.content.lower()
    assert "TimeoutError" in (block.degraded_reason or "")
