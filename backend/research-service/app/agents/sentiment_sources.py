from __future__ import annotations

import html
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterable
from datetime import datetime
from enum import StrEnum
from threading import Lock
from urllib import request as url_request
from urllib.parse import urlencode

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("uvicorn.error")

JsonTransport = Callable[[str, float, dict[str, str]], dict[str, object]]
TextTransport = Callable[[str, float, dict[str, str]], str]
Clock = Callable[[], float]

_USER_AGENT = "spring-alpha/1.0 sentiment-agent"
_STOCKTWITS_API = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_YAHOO_NEWS_API = "https://query2.finance.yahoo.com/v1/finance/search?{query}"
_REDDIT_SEARCH_API = "https://www.reddit.com/r/{subreddit}/search.json?{query}"
_REDDIT_SEARCH_RSS = "https://www.reddit.com/r/{subreddit}/search.rss?{query}"
_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}
_REDDIT_CACHE_LOCK = Lock()
_REDDIT_CACHE: dict[tuple[str, tuple[str, ...], int], tuple[float, SentimentSourceBlock]] = {}
_REDDIT_CACHE_TTL_SECONDS = 600.0
_REDDIT_DEGRADED_CACHE_TTL_SECONDS = 60.0
DEFAULT_REDDIT_SUBREDDITS = ("wallstreetbets", "stocks", "investing")


class SentimentSourceStatus(StrEnum):
    OK = "ok"
    EMPTY = "empty"
    DEGRADED = "degraded"


class SentimentSourceBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    status: SentimentSourceStatus
    content: str
    item_count: int = Field(default=0, ge=0)
    degraded_reason: str | None = None


def fetch_yahoo_finance_news(
    ticker: str,
    *,
    transport: JsonTransport | None = None,
    limit: int = 10,
    timeout: float = 8.0,
) -> SentimentSourceBlock:
    normalized = ticker.upper()
    fetch = transport or _json_transport
    query = urlencode({"q": normalized, "quotesCount": 0, "newsCount": limit})
    try:
        payload = fetch(
            _YAHOO_NEWS_API.format(query=query),
            timeout,
            {"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
    except Exception as exc:
        return _degraded_block("yahoo_news", normalized, exc)

    raw_items = payload.get("news")
    items = raw_items if isinstance(raw_items, list) else []
    lines: list[str] = []
    for item in items[:limit]:
        if not isinstance(item, dict):
            continue
        title = _clean_text(item.get("title"))
        if not title:
            continue
        publisher = _clean_text(item.get("publisher")) or "unknown publisher"
        published = _format_epoch_date(item.get("providerPublishTime"))
        link = _clean_text(item.get("link"))
        suffix = f" · {link}" if link else ""
        lines.append(f"[{published} · {publisher}] {title}{suffix}")

    if not lines:
        return _empty_block(
            "yahoo_news",
            normalized,
            f"<no Yahoo Finance news found for {normalized}>",
        )
    return SentimentSourceBlock(
        source="yahoo_news",
        status=SentimentSourceStatus.OK,
        item_count=len(lines),
        content="\n".join(lines),
    )


def fetch_stocktwits_messages(
    ticker: str,
    *,
    transport: JsonTransport | None = None,
    limit: int = 30,
    timeout: float = 8.0,
) -> SentimentSourceBlock:
    normalized = ticker.upper()
    fetch = transport or _json_transport
    try:
        payload = fetch(
            _STOCKTWITS_API.format(ticker=normalized),
            timeout,
            {"User-Agent": _USER_AGENT, "Accept": "application/json"},
        )
    except Exception as exc:
        return _degraded_block("stocktwits", normalized, exc)

    raw_messages = payload.get("messages")
    messages = raw_messages if isinstance(raw_messages, list) else []
    if not messages:
        return _empty_block(
            "stocktwits",
            normalized,
            f"<no StockTwits messages found for ${normalized}>",
        )

    bullish = bearish = unlabeled = 0
    lines: list[str] = []
    for message in messages[:limit]:
        if not isinstance(message, dict):
            continue
        sentiment = _stocktwits_sentiment(message)
        if sentiment == "Bullish":
            bullish += 1
        elif sentiment == "Bearish":
            bearish += 1
        else:
            unlabeled += 1
            sentiment = "no-label"
        created = _clean_text(message.get("created_at")) or "unknown time"
        user = _clean_text((message.get("user") or {}).get("username")) or "unknown"
        body = _truncate(_clean_text(message.get("body")), 280)
        if body:
            lines.append(f"[{created} · @{user} · {sentiment}] {body}")

    total = bullish + bearish + unlabeled
    if total == 0:
        return _empty_block(
            "stocktwits",
            normalized,
            f"<no usable StockTwits messages found for ${normalized}>",
        )
    summary = (
        f"Bullish: {bullish} ({_pct(bullish, total)}%) · "
        f"Bearish: {bearish} ({_pct(bearish, total)}%) · "
        f"Unlabeled: {unlabeled} · Total: {total} most-recent messages"
    )
    return SentimentSourceBlock(
        source="stocktwits",
        status=SentimentSourceStatus.OK,
        item_count=total,
        content=summary + "\n\n" + "\n".join(lines),
    )


def fetch_reddit_discussion(
    ticker: str,
    *,
    subreddits: Iterable[str] = DEFAULT_REDDIT_SUBREDDITS,
    transport: JsonTransport | None = None,
    text_transport: TextTransport | None = None,
    limit_per_subreddit: int = 5,
    timeout: float = 8.0,
    inter_request_delay: float = 0.25,
    cache_ttl_seconds: float | None = None,
    degraded_cache_ttl_seconds: float | None = None,
    clock: Clock = time.time,
) -> SentimentSourceBlock:
    normalized = ticker.upper()
    subreddit_tuple = tuple(subreddits)
    ttl = _REDDIT_CACHE_TTL_SECONDS if cache_ttl_seconds is None else cache_ttl_seconds
    degraded_ttl = (
        _REDDIT_DEGRADED_CACHE_TTL_SECONDS
        if degraded_cache_ttl_seconds is None
        else degraded_cache_ttl_seconds
    )
    cache_enabled = ttl > 0 or degraded_ttl > 0
    cache_key = (normalized, subreddit_tuple, limit_per_subreddit)
    if cache_enabled:
        cached_block = _get_reddit_cache(cache_key, now=clock())
        if cached_block is not None:
            return cached_block
    fetch = transport or _json_transport
    fetch_text = text_transport or _text_transport
    blocks: list[str] = []
    total_items = 0
    degraded_reasons: list[str] = []

    for index, subreddit in enumerate(subreddit_tuple):
        if index > 0 and inter_request_delay > 0:
            time.sleep(inter_request_delay)
        query = urlencode(
            {
                "q": normalized,
                "restrict_sr": "on",
                "sort": "new",
                "t": "week",
                "limit": limit_per_subreddit,
            }
        )
        try:
            payload = fetch(
                _REDDIT_SEARCH_API.format(subreddit=subreddit, query=query),
                timeout,
                {"User-Agent": _USER_AGENT, "Accept": "application/json"},
            )
            posts = _reddit_posts(payload)
        except Exception as exc:
            logger.warning(
                "reddit json fetch failed subreddit=%s ticker=%s error=%s; trying rss fallback",
                subreddit,
                normalized,
                exc,
            )
            try:
                rss_text = fetch_text(
                    _REDDIT_SEARCH_RSS.format(subreddit=subreddit, query=query),
                    timeout,
                    {"User-Agent": _USER_AGENT, "Accept": "application/atom+xml,text/xml"},
                )
                posts = _reddit_posts_from_rss(rss_text, limit_per_subreddit)
            except Exception as rss_exc:
                degraded_reasons.append(
                    f"r/{subreddit}: {type(exc).__name__}; RSS {type(rss_exc).__name__}"
                )
                blocks.append(
                    f"r/{subreddit}: <unavailable: {type(exc).__name__}; "
                    f"RSS {type(rss_exc).__name__}>"
                )
                continue
        if not posts:
            blocks.append(
                f"r/{subreddit}: <no posts found mentioning {normalized} in the past 7 days>"
            )
            continue
        total_items += len(posts)
        via_rss = any(post.get("source") == "rss" for post in posts)
        header = f"r/{subreddit} — {len(posts)} recent posts mentioning {normalized}"
        if via_rss:
            header += " (via RSS feed; scores/comments unavailable)"
        lines = [header + ":"]
        for post in posts[:limit_per_subreddit]:
            title = _truncate(_clean_text(post.get("title")), 180)
            score = _optional_int(post.get("score"))
            comments = _optional_int(post.get("num_comments"))
            created = _format_epoch_date(post.get("created_utc"))
            selftext = _truncate(_clean_text(post.get("selftext")), 240)
            meta = created
            if score is not None and comments is not None:
                meta += f" · {score}↑ · {comments}c"
            lines.append(f"  [{meta}] {title}")
            if selftext:
                lines.append(f"    body excerpt: {selftext}")
        blocks.append("\n".join(lines))

    if total_items == 0 and degraded_reasons:
        block = SentimentSourceBlock(
            source="reddit",
            status=SentimentSourceStatus.DEGRADED,
            item_count=0,
            content="\n\n".join(blocks),
            degraded_reason="; ".join(degraded_reasons),
        )
        if cache_enabled:
            _store_reddit_cache(cache_key, block, now=clock(), ttl_seconds=degraded_ttl)
        return block
    if total_items == 0:
        block = _empty_block(
            "reddit",
            normalized,
            "\n\n".join(blocks)
            or f"<no Reddit posts found mentioning {normalized} in the past 7 days>",
        )
        if cache_enabled:
            _store_reddit_cache(cache_key, block, now=clock(), ttl_seconds=ttl)
        return block
    block = SentimentSourceBlock(
        source="reddit",
        status=SentimentSourceStatus.OK,
        item_count=total_items,
        content="\n\n".join(blocks),
        degraded_reason="; ".join(degraded_reasons) or None,
    )
    if cache_enabled:
        _store_reddit_cache(cache_key, block, now=clock(), ttl_seconds=ttl)
    return block


def fetch_market_sentiment_sources(ticker: str) -> list[SentimentSourceBlock]:
    return [
        fetch_yahoo_finance_news(ticker),
        fetch_stocktwits_messages(ticker),
        fetch_reddit_discussion(ticker),
    ]


def render_sentiment_source_blocks(blocks: list[SentimentSourceBlock]) -> str:
    rendered: list[str] = []
    for block in blocks:
        rendered.append(
            "\n".join(
                [
                    f"### {block.source}",
                    f"status: {block.status.value}",
                    f"item_count: {block.item_count}",
                    f"degraded_reason: {block.degraded_reason or ''}",
                    "<source_content>",
                    block.content,
                    "</source_content>",
                ]
            )
        )
    return "\n\n".join(rendered)


def _json_transport(url: str, timeout: float, headers: dict[str, str]) -> dict[str, object]:
    req = url_request.Request(url, headers=headers)
    with url_request.urlopen(req, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("sentiment source response must be a JSON object")
    return payload


def _text_transport(url: str, timeout: float, headers: dict[str, str]) -> str:
    req = url_request.Request(url, headers=headers)
    with url_request.urlopen(req, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def _get_reddit_cache(
    cache_key: tuple[str, tuple[str, ...], int],
    *,
    now: float,
) -> SentimentSourceBlock | None:
    with _REDDIT_CACHE_LOCK:
        cached = _REDDIT_CACHE.get(cache_key)
        if cached is None:
            return None
        expires_at, block = cached
        if expires_at <= now:
            _REDDIT_CACHE.pop(cache_key, None)
            return None
        return block.model_copy(deep=True)


def _store_reddit_cache(
    cache_key: tuple[str, tuple[str, ...], int],
    block: SentimentSourceBlock,
    *,
    now: float,
    ttl_seconds: float,
) -> None:
    if ttl_seconds <= 0:
        return
    with _REDDIT_CACHE_LOCK:
        _REDDIT_CACHE[cache_key] = (now + ttl_seconds, block.model_copy(deep=True))


def _degraded_block(source: str, ticker: str, exc: Exception) -> SentimentSourceBlock:
    logger.warning(
        "sentiment source fetch failed source=%s ticker=%s error=%s",
        source,
        ticker,
        exc,
    )
    reason = f"{type(exc).__name__}: {exc}"
    return SentimentSourceBlock(
        source=source,
        status=SentimentSourceStatus.DEGRADED,
        item_count=0,
        content=f"<{source} unavailable for {ticker}: {type(exc).__name__}>",
        degraded_reason=reason,
    )


def _empty_block(source: str, ticker: str, content: str) -> SentimentSourceBlock:
    return SentimentSourceBlock(
        source=source,
        status=SentimentSourceStatus.EMPTY,
        item_count=0,
        content=content,
        degraded_reason=f"No usable {source} items for {ticker}.",
    )


def _stocktwits_sentiment(message: dict[str, object]) -> str | None:
    entities = message.get("entities")
    if not isinstance(entities, dict):
        return None
    sentiment = entities.get("sentiment")
    if not isinstance(sentiment, dict):
        return None
    raw = sentiment.get("basic")
    return str(raw) if raw else None


def _reddit_posts(payload: dict[str, object]) -> list[dict[str, object]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    children = data.get("children")
    if not isinstance(children, list):
        return []
    posts: list[dict[str, object]] = []
    for child in children:
        if not isinstance(child, dict):
            continue
        post = child.get("data")
        if isinstance(post, dict):
            posts.append(post)
    return posts


def _reddit_posts_from_rss(rss_text: str, limit: int) -> list[dict[str, object]]:
    root = ET.fromstring(rss_text)
    posts: list[dict[str, object]] = []
    for entry in root.findall("atom:entry", _ATOM_NS)[:limit]:
        title = entry.find("atom:title", _ATOM_NS)
        published = entry.find("atom:published", _ATOM_NS)
        content = entry.find("atom:content", _ATOM_NS)
        posts.append(
            {
                "title": title.text if title is not None and title.text else "",
                "score": None,
                "num_comments": None,
                "created_utc": _parse_atom_timestamp(
                    published.text if published is not None else None
                ),
                "selftext": _strip_reddit_html(
                    content.text if content is not None and content.text else ""
                ),
                "source": "rss",
            }
        )
    return posts


def _parse_atom_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        return int(datetime.fromisoformat(normalized).timestamp())
    except (TypeError, ValueError):
        return None


def _strip_reddit_html(value: str) -> str:
    if not value:
        return ""
    if "<!-- SC_OFF -->" in value and "<!-- SC_ON -->" in value:
        value = value.split("<!-- SC_OFF -->", 1)[1].split("<!-- SC_ON -->", 1)[0]
    text = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(text).split())


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).replace("\n", " ").split())


def _truncate(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _format_epoch_date(value: object) -> str:
    timestamp = _optional_int(value)
    if timestamp is None:
        return "unknown date"
    return time.strftime("%Y-%m-%d", time.gmtime(timestamp))


def _optional_int(value: object) -> int | None:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _pct(part: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(100 * part / total)
