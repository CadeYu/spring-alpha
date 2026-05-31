from __future__ import annotations

import re
from typing import Literal, Protocol

from app.agents.business_driver_quality import (
    BusinessDriverFactsContext,
    business_driver_facts_backfill_summary,
    business_driver_facts_context,
    business_driver_thesis_backfill,
)
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
    revenue = context.revenue or "可用收入数据"
    margin = (
        context.gross_margin
        or context.operating_margin
        or context.net_margin
        or context.operating_income
        or "可用利润率和盈利数据"
    )
    profile = _zh_business_profile_hint(context)
    summaries = {
        "revenue_bridge": (
            f"{company} 的收入桥接应先锚定结构化数据：最新收入为 {revenue}。"
            f"{profile} 这说明当前最重要的投资含义是判断增长是否来自可持续需求，"
            "而不是只看单季收入规模。由于分业务或区域拆分仍不完整，这一结论属于"
            "方向性判断，并应标记为部分支撑。"
        ),
        "segment_momentum": (
            f"{company} 的分部动能不能因为分部证据不足就留空；现有业务画像显示"
            f"{profile} 因此该段应退化为业务线暴露分析：看核心产品、客户场景和收入结构"
            "是否继续贡献增长。对投资者来说，重点是判断增长来源是否集中、是否可延续，"
            "目前结论仍是方向性判断。"
        ),
        "margin_and_mix": (
            f"{company} 的利润率与组合判断应锚定毛利率为 {margin}，并结合收入 {revenue} "
            "观察规模增长是否能转化为经营杠杆。对投资者来说，关键是收入质量和产品组合"
            "是否支撑利润率韧性，而不是只复述收入变化。由于成本项和分部利润率证据仍有限，"
            "该结论应视为部分支撑。"
        ),
        "demand_signals": (
            f"{company} 的直接需求指标仍不完整，但收入 {revenue}、业务暴露和市场语境"
            "可以作为需求代理。对投资者来说，关键是判断需求是否能继续支撑收入质量和"
            "利润率韧性，而不是让缺少订单、积压或销量数据导致空白结论。当前结论是"
            "方向性判断，后续需要更细的需求证据验证。"
        ),
    }
    return summaries[lens_name]


def _zh_business_profile_hint(context: BusinessDriverFactsContext) -> str:
    classification = " / ".join(item for item in (context.sector, context.industry) if item)
    if classification:
        return f"其行业暴露集中在 {classification}。"
    if context.business_summary:
        return "其业务摘要提供了产品和客户暴露线索。"
    return "现有资料已提供基础业务画像。"


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
