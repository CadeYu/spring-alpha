from __future__ import annotations

import re
from typing import Literal, Protocol

from app.agents.business_driver_quality import (
    BusinessDriverFactsContext,
    business_driver_facts_backfill_summary,
    business_driver_facts_context,
    business_driver_thesis_backfill,
)
from app.agents.zh_text_helpers import localize_market_classification
from app.contracts.agent import AgentState
from app.contracts.report import CitationStatus, DriverThesis

DriverDurability = Literal["durable", "mixed", "temporary", "unclear"]


class BusinessDriverPointLike(Protocol):
    title: str
    summary: str
    source_ids: list[str]
    citation_status: CitationStatus


class BusinessDriverMapLike(Protocol):
    revenue_bridge: BusinessDriverPointLike | None
    segment_momentum: BusinessDriverPointLike | None
    margin_and_mix: BusinessDriverPointLike | None
    demand_signals: BusinessDriverPointLike | None


class BusinessDriverPayloadLike(Protocol):
    driver_thesis: DriverThesis
    driver_map: BusinessDriverMapLike


_GENERIC_SUMMARY_PATTERNS = (
    r"\b(revenue bridge|segment momentum|margin and mix|demand signals)\s+is important\b",
    r"\bis important for investors\b",
    r"\bevidence shows revenue and demand\b",
    r"\bbusiness driver evidence\b",
    r"\bkey driver\b",
    r"\bimportant factor\b",
    r"\bneeds to be monitored\b",
)

_TEMPLATE_THESIS_HEADLINES = {
    "结构化 facts 支撑方向性业务判断",
    "业务驱动证据优先结论",
    "structured facts support a directional business-driver read",
    "evidence-backed business driver thesis",
}

_ALLOWED_UPPERCASE_TERMS = {
    "AI",
    "AMD",
    "API",
    "CPU",
    "CPUs",
    "GPU",
    "GPUs",
    "KPI",
    "KPIs",
    "RAG",
    "SEC",
    "USD",
}


def review_business_driver_payload(
    payload: BusinessDriverPayloadLike,
    state: AgentState,
    language: str | None,
) -> None:
    context = business_driver_facts_context(state)
    if not context.has_signal:
        return
    _review_driver_thesis(payload.driver_thesis, context, language)
    for lens_name, point in _driver_map_points(payload.driver_map):
        if point is None:
            continue
        if _needs_business_driver_rewrite(point.summary, language):
            point.summary = _reviewer_summary(lens_name, context, language)
            point.source_ids = []
            point.citation_status = CitationStatus.PARTIAL


def _review_driver_thesis(
    thesis: DriverThesis,
    context: BusinessDriverFactsContext,
    language: str | None,
) -> None:
    if not (
        _needs_business_driver_rewrite(thesis.summary, language)
        or _needs_business_driver_rewrite(thesis.headline, language)
        or _is_template_thesis_headline(thesis.headline)
    ):
        return
    headline, durability, summary = business_driver_thesis_backfill(context, language)
    thesis.headline = headline
    thesis.durability = _driver_durability(durability)
    thesis.summary = summary


def _driver_map_points(
    driver_map: BusinessDriverMapLike,
) -> list[tuple[str, BusinessDriverPointLike | None]]:
    return [
        ("revenue_bridge", driver_map.revenue_bridge),
        ("segment_momentum", driver_map.segment_momentum),
        ("margin_and_mix", driver_map.margin_and_mix),
        ("demand_signals", driver_map.demand_signals),
    ]


def _needs_business_driver_rewrite(text: str, language: str | None) -> bool:
    normalized = " ".join(text.split()).strip()
    if len(normalized) < 80:
        return True
    lower = normalized.lower()
    if any(re.search(pattern, lower) for pattern in _GENERIC_SUMMARY_PATTERNS):
        return True
    if _is_zh_locale(language) and _english_leak_score(normalized) >= 4:
        return True
    if not _has_investor_meaning(normalized, language):
        return True
    return False


def _is_template_thesis_headline(value: str) -> bool:
    normalized = " ".join(value.split()).strip().lower()
    return normalized in _TEMPLATE_THESIS_HEADLINES


def _reviewer_summary(
    lens_name: str,
    context: BusinessDriverFactsContext,
    language: str | None,
) -> str:
    if _is_zh_locale(language):
        return _reviewer_zh_summary(lens_name, context)
    base = business_driver_facts_backfill_summary(lens_name, context, language)
    return (
        f"{base} For investors, the key question is not the single reported number but "
        "whether these structured facts keep converting into revenue quality, margin "
        "resilience, and durable demand; treat the conclusion as partial support rather "
        "than a complete evidence loop."
    )


def _reviewer_zh_summary(lens_name: str, context: BusinessDriverFactsContext) -> str:
    company = context.company or "该公司"
    revenue = context.revenue or "当前未披露可量化收入"
    margin = (
        context.gross_margin
        or context.operating_margin
        or context.net_margin
        or context.operating_income
        or "当前未披露可量化利润率"
    )
    profile = _zh_business_profile_hint(context)
    summaries = {
        "revenue_bridge": (
            f"{company} 最新收入为 {revenue}，这是判断业务动能的第一层锚点。"
            f"{profile} 投资上更重要的是看增长是否来自可持续需求，"
            "以及后续分业务或区域拆分能否验证收入质量。"
        ),
        "segment_momentum": (
            f"{company} 的分部动能应先从产品、客户和业务线暴露入手。{profile}"
            "如果核心业务线与总收入同向改善，收入质量会更可信；"
            "如果增长集中在单一业务，投资者需要重新验证持续性。"
        ),
        "margin_and_mix": (
            f"{company} 的利润率锚点为 {margin}，需要和收入 {revenue} 一起判断。"
            "投资者应关注收入增长能否转化为经营杠杆，以及产品组合、定价和成本"
            "是否继续支撑利润率韧性。"
        ),
        "demand_signals": (
            f"{company} 的需求观察先看收入 {revenue} 与业务暴露是否同向。"
            "投资者需要确认需求能否继续支撑收入质量和利润率韧性；"
            "后续应重点跟踪订单、积压、销量、留存或客户扩张数据。"
        ),
    }
    return summaries[lens_name]


def _zh_business_profile_hint(context: BusinessDriverFactsContext) -> str:
    classification = " / ".join(item for item in (context.sector, context.industry) if item)
    if classification:
        return (
            f"其行业暴露集中在 "
            f"{localize_market_classification(context.sector, context.industry)}。"
        )
    if context.business_summary:
        return "其业务摘要提供了产品和客户暴露线索。"
    return "投资者需要结合行业暴露和后续披露验证这条业务主线。"


def _english_leak_score(text: str) -> int:
    tokens = re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text)
    leaked = [
        token
        for token in tokens
        if token not in _ALLOWED_UPPERCASE_TERMS and not token.isupper()
    ]
    return len(leaked)


def _has_investor_meaning(text: str, language: str | None) -> bool:
    lower = text.lower()
    if _is_zh_locale(language):
        return any(term in text for term in ("投资", "估值", "利润率", "需求", "经营质量", "现金流"))
    return any(
        term in lower
        for term in (
            "investor",
            "valuation",
            "margin",
            "demand",
            "operating quality",
            "cash flow",
        )
    )


def _is_zh_locale(language: str | None) -> bool:
    return str(language or "").lower().startswith("zh")


def _driver_durability(value: str) -> DriverDurability:
    normalized = str(value or "").strip().lower()
    if normalized in {"durable", "mixed", "temporary", "unclear"}:
        return normalized  # type: ignore[return-value]
    return "mixed"
