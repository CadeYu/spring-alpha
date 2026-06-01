from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.agents.structured_facts import normalize_metric_name, structured_metric_records_from_facts
from app.agents.zh_text_helpers import localize_market_classification
from app.contracts.agent import AgentState

BUSINESS_DRIVER_CORE_METRICS = [
    "revenue",
    "segment revenue",
    "gross margin",
    "operating margin",
    "operating income",
    "net income",
]

BUSINESS_DRIVER_FACT_METRICS = [
    "revenue",
    "gross margin",
    "operating margin",
    "operating income",
    "net income",
]


class BusinessDriverFactsContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    company: str = ""
    sector: str = ""
    industry: str = ""
    business_summary: str = ""
    revenue: str = ""
    gross_margin: str = ""
    operating_margin: str = ""
    net_margin: str = ""
    operating_income: str = ""
    demand_signal: str = ""
    market_context: str = ""

    @property
    def has_signal(self) -> bool:
        return any(
            (
                self.company,
                self.business_summary,
                self.revenue,
                self.gross_margin,
                self.operating_margin,
                self.net_margin,
                self.operating_income,
                self.demand_signal,
                self.market_context,
            )
        )


def business_driver_facts_brief(state: AgentState, language: str | None) -> str:
    lines = ["Business driver facts brief:"]
    profile_items = _business_driver_profile_items(state)
    if profile_items:
        lines.append("Company and market brief:")
        lines.extend(f"- {item}" for item in profile_items)
    metric_items = _business_driver_metric_items(state)
    if metric_items:
        lines.append("Financial facts brief:")
        lines.extend(f"- {item}" for item in metric_items[:8])
    signal_items = _business_driver_signal_items(state)
    if signal_items:
        lines.append("Business signal brief:")
        lines.extend(f"- {item}" for item in signal_items[:4])
    market_items = _business_driver_market_context_items(state)
    if market_items:
        lines.append("Market context brief:")
        lines.extend(f"- {item}" for item in market_items[:6])
    if len(lines) == 1:
        lines.append(
            "- No structured facts were available."
            if not _is_zh_locale(language)
            else "- 没有可用的结构化 facts。"
        )
    if _is_zh_locale(language):
        lines.append(
            "当 segment 或 RAG 证据不完整时，请用这份 brief 写谨慎的方向性判断；"
            "除非句子有 allowed source_id 支撑，否则 citation_status 使用 partial 或 unverified。"
        )
    else:
        lines.append(
            "Use this brief for cautious directional conclusions when segment or RAG "
            "evidence is incomplete; label citation_status as partial or unverified "
            "unless an allowed source_id supports the sentence."
        )
    return "\n".join(lines)


def business_driver_facts_context(state: AgentState) -> BusinessDriverFactsContext:
    facts = state.evidence_memory.facts
    metrics = {
        normalize_metric_name(str(record.get("metric") or record.get("name") or "")): record
        for record in [
            *_normalized_business_driver_metric_records(state.evidence_memory.metric_evidence),
            *_normalized_business_driver_metric_records(structured_metric_records_from_facts(facts)),
        ]
        if record.get("value") is not None
    }
    return BusinessDriverFactsContext(
        company=_first_fact_text(facts, ("company_name", "companyName", "name", "longName")),
        sector=_first_fact_text(facts, ("sector", "market_sector")),
        industry=_first_fact_text(facts, ("industry", "market_industry")),
        business_summary=_company_profile_raw_summary_from_facts(state),
        revenue=_business_driver_metric_value(metrics, "revenue"),
        gross_margin=_business_driver_metric_value(metrics, "gross margin"),
        operating_margin=_business_driver_metric_value(metrics, "operating margin"),
        net_margin=_business_driver_metric_value(metrics, "net margin"),
        operating_income=_business_driver_metric_value(metrics, "operating income"),
        demand_signal=_business_driver_first_signal_summary(state),
        market_context=_business_driver_first_market_context_summary(state),
    )


def business_driver_facts_backfill_summary(
    lens_name: str,
    context: BusinessDriverFactsContext,
    language: str | None,
) -> str:
    if _is_zh_locale(language):
        company = context.company or "该公司"
        profile = _business_driver_profile_hint(context, language)
        revenue = context.revenue or "当前未披露可量化收入"
        margin = (
            context.gross_margin
            or context.operating_margin
            or context.net_margin
            or context.operating_income
            or "当前未披露可量化利润率"
        )
        demand = (
            context.demand_signal
            or context.market_context
            or profile
            or "可用业务画像"
        )
        summaries = {
            "revenue_bridge": (
                f"{company} 最新收入为 {revenue}，这是判断业务动能的第一层锚点。"
                f"{profile} 投资上更重要的是看收入增长是否来自可持续需求，"
                "并在后续披露中验证分业务或区域拆分质量。"
            ),
            "segment_momentum": (
                f"{company} 的分部动能应先从产品、客户和业务线暴露入手。{profile}"
                "如果后续披露显示核心业务线与总收入同向改善，收入质量会更可信；"
                "若增长只集中在单一业务，则持续性需要重新验证。"
            ),
            "margin_and_mix": (
                f"{company} 的利润率锚点为 {margin}，需要和收入 {revenue} 一起判断。"
                "投资者应关注收入增长能否转化为经营杠杆，以及产品组合、定价和成本"
                "是否继续支撑利润率韧性。"
            ),
            "demand_signals": (
                f"{company} 的需求观察先看收入 {revenue} 与业务暴露是否同向，"
                f"当前可用信号指向 {demand}。后续需要用订单、积压、销量或留存数据"
                "确认需求韧性，而不是只看单季收入规模。"
            ),
        }
        return summaries[lens_name]

    company = context.company or "the company"
    profile = _business_driver_profile_hint(context, language)
    revenue = context.revenue or "the available revenue base"
    margin = (
        context.gross_margin
        or context.operating_margin
        or context.net_margin
        or context.operating_income
        or "the available margin and profitability facts"
    )
    demand = (
        context.demand_signal
        or context.market_context
        or profile
        or "the available business profile"
    )
    summaries = {
        "revenue_bridge": (
            f"{company}'s revenue bridge needs more segment evidence, but structured facts "
            f"show revenue of {revenue}. {profile} This supports a directional conclusion: "
            "anchor the growth read in the reported revenue base, then wait for business-line "
            "or geography detail to validate quality."
        ),
        "segment_momentum": (
            f"{company}'s segment momentum evidence is incomplete, but the business profile "
            f"shows {profile}. That lets the read fall back to product and business-line "
            "exposure instead of a blank conclusion. Treat it as directional until segment "
            "revenue or segment margin evidence is available."
        ),
        "margin_and_mix": (
            f"{company}'s margin and mix evidence is incomplete, but structured facts provide "
            f"a margin anchor of {margin}. Against revenue of {revenue}, the key read is "
            "whether top-line scale converts into durable profitability. Treat it as "
            "directional until product mix, cost, or segment margin detail is available."
        ),
        "demand_signals": (
            f"{company}'s direct demand evidence is incomplete, but the available business "
            f"or market signal points to {demand}. Without orders, backlog, volume, or "
            f"retention data, revenue of {revenue} and business exposure are the demand proxy. "
            "This is not full demand proof, but it is stronger than an empty evidence statement."
        ),
    }
    return summaries[lens_name]


def business_driver_thesis_backfill(
    context: BusinessDriverFactsContext,
    language: str | None,
) -> tuple[str, str, str]:
    if _is_zh_locale(language):
        company = context.company or "该公司"
        revenue = context.revenue or "当前未披露可量化收入"
        margin = (
            context.gross_margin
            or context.operating_margin
            or context.net_margin
            or context.operating_income
            or "当前未披露可量化利润率"
        )
        profile = _business_driver_profile_hint(context, language)
        headline = f"{company} 业务驱动需要同时验证收入、利润率、需求韧性与分部质量"
        summary = (
            f"{company} 的业务驱动结论应同时看收入 {revenue} 与利润率锚点 {margin}。"
            f"{profile} 对投资者来说，关键不是单季收入数字本身，而是收入规模、"
            "业务暴露和利润率能否共同说明经营质量；后续披露需要继续验证分部收入、"
            "产品组合和需求指标。"
        )
        return headline, "mixed", summary

    company = context.company or "the company"
    revenue = context.revenue or "the available revenue base"
    margin = (
        context.gross_margin
        or context.operating_margin
        or context.net_margin
        or context.operating_income
        or "the available margin facts"
    )
    profile = _business_driver_profile_hint(context, language)
    headline = f"{company} revenue and margin anchors drive the business read"
    summary = (
        f"{company}'s business-driver thesis should not depend only on retrieved segment "
        f"RAG snippets; structured facts already provide revenue of {revenue} and a "
        f"margin or profitability anchor of {margin}. {profile} The thesis should be "
        "directional: use reported revenue scale, business exposure, and margin anchors "
        "to judge operating quality, then wait for finer segment revenue, product mix, "
        "and demand indicators to validate it."
    )
    return headline, "mixed", summary


def _business_driver_profile_items(state: AgentState) -> list[str]:
    facts = state.evidence_memory.facts
    items: list[str] = []
    for label, keys in (
        ("Company", ("company_name", "companyName", "name", "longName")),
        ("Sector", ("sector", "market_sector")),
        ("Industry", ("industry", "market_industry")),
    ):
        value = _first_fact_text(facts, keys)
        if value:
            items.append(f"{label}: {_clip(value, 180)}")
    business_summary = _company_profile_raw_summary_from_facts(state)
    if business_summary:
        items.append(f"Business summary: {_clip(business_summary, 360)}")
    return items


def _business_driver_metric_items(state: AgentState) -> list[str]:
    records = [
        *_normalized_business_driver_metric_records(state.evidence_memory.metric_evidence),
        *_normalized_business_driver_metric_records(
            structured_metric_records_from_facts(state.evidence_memory.facts)
        ),
    ]
    items: list[str] = []
    seen: set[str] = set()
    preferred_metrics = {
        "revenue",
        "gross margin",
        "operating margin",
        "net margin",
        "operating income",
        "net income",
        "operating cash flow",
        "free cash flow",
    }
    for record in records:
        metric = str(record.get("metric") or record.get("name") or "").strip()
        normalized = normalize_metric_name(metric)
        if not normalized or normalized in seen:
            continue
        if normalized not in preferred_metrics and len(seen) >= 6:
            continue
        value = _metric_evidence_value(record)
        period = _metric_evidence_period(record)
        source = str(record.get("source") or "").strip()
        item = f"{normalized}: {value}"
        if period:
            item += f" ({period})"
        if source:
            item += f"; source={source}"
        items.append(item)
        seen.add(normalized)
    return items


def _normalized_business_driver_metric_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized_records: list[dict[str, Any]] = []
    for record in records:
        metric = str(
            record.get("metric")
            or record.get("normalized_metric")
            or record.get("name")
            or ""
        )
        normalized = normalize_metric_name(metric)
        if not normalized or record.get("value") is None:
            continue
        normalized_record = dict(record)
        normalized_record["metric"] = normalized
        normalized_records.append(normalized_record)
    return normalized_records


def _business_driver_signal_items(state: AgentState) -> list[str]:
    items: list[str] = []
    for signal in state.evidence_memory.business_signals:
        if not isinstance(signal, dict):
            continue
        summary = str(
            signal.get("summary")
            or signal.get("text")
            or signal.get("signal")
            or signal.get("theme")
            or ""
        ).strip()
        if summary:
            items.append(_clip(summary, 220))
    return items


def _business_driver_market_context_items(state: AgentState) -> list[str]:
    context = state.evidence_memory.market_context
    if not context:
        return []
    items: list[str] = []
    profile = context.get("profile")
    if isinstance(profile, dict):
        classification = " / ".join(
            str(profile.get(key) or "").strip()
            for key in ("sector", "industry")
            if str(profile.get(key) or "").strip()
        )
        if classification:
            items.append(f"Market profile: {_clip(classification, 180)}")
    valuation = context.get("valuation")
    if isinstance(valuation, dict):
        valuation_items = [
            f"{key}={value}"
            for key, value in valuation.items()
            if value not in (None, "", [], {})
        ]
        if valuation_items:
            items.append(f"Valuation: {_clip(', '.join(valuation_items), 220)}")
    quote = context.get("quote")
    if isinstance(quote, dict):
        quote_items = [
            f"{key}={value}" for key, value in quote.items() if value not in (None, "", [], {})
        ]
        if quote_items:
            items.append(f"Quote: {_clip(', '.join(quote_items), 220)}")
    for section_name, label, key in (
        ("technical", "Technical", "trend"),
        ("sentiment", "Sentiment", "summary"),
        ("macro", "Macro", "context"),
    ):
        section = context.get(section_name)
        if not isinstance(section, dict):
            continue
        value = str(section.get(key) or "").strip()
        if value:
            items.append(f"{label}: {_clip(value, 220)}")
    news = context.get("news")
    if isinstance(news, dict):
        headlines = news.get("headlines")
        if isinstance(headlines, list) and headlines:
            items.append(f"News: {_clip(str(headlines[0]), 220)}")
    return items


def _business_driver_first_market_context_summary(state: AgentState) -> str:
    items = _business_driver_market_context_items(state)
    return items[0] if items else ""


def _business_driver_metric_value(
    metrics: dict[str, dict[str, Any]],
    metric_name: str,
) -> str:
    record = metrics.get(normalize_metric_name(metric_name))
    if record is None:
        return ""
    return _metric_evidence_value(record)


def _business_driver_first_signal_summary(state: AgentState) -> str:
    signals = _business_driver_signal_items(state)
    return signals[0] if signals else ""


def _business_driver_profile_hint(
    context: BusinessDriverFactsContext,
    language: str | None = None,
) -> str:
    summary = _clip(context.business_summary, 220) if context.business_summary else ""
    classification = " / ".join(item for item in (context.sector, context.industry) if item)
    if _is_zh_locale(language):
        if classification:
            return (
                f"其行业暴露集中在 "
                f"{localize_market_classification(context.sector, context.industry)}。"
            )
        if summary:
            return "现有业务摘要提供了产品、客户和市场暴露线索。"
        return "投资者需要结合行业暴露和后续披露验证这条业务主线。"
    if summary and classification:
        return f"{summary} ({classification})."
    if summary:
        return summary
    if classification:
        return classification
    return "the available business profile"


def _company_profile_raw_summary_from_facts(state: AgentState) -> str:
    return str(
        state.evidence_memory.facts.get("business_summary")
        or state.evidence_memory.facts.get("businessSummary")
        or state.evidence_memory.facts.get("market_business_summary")
        or state.evidence_memory.facts.get("marketBusinessSummary")
        or state.evidence_memory.facts.get("description")
        or ""
    ).strip()


def _first_fact_text(facts: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = facts.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _metric_evidence_value(record: dict[str, Any]) -> str:
    value = record.get("value")
    unit = str(record.get("unit") or "").strip()
    if isinstance(value, int | float) and unit.lower() in {"x", "ratio"}:
        return f"{float(value):.2f}x"
    if isinstance(value, int | float) and unit.lower() in {"pure", "percent", "percentage"}:
        return f"{float(value) * 100:.1f}%"
    if isinstance(value, int | float):
        formatted = _compact_number(value)
    elif isinstance(value, str) and value.strip().replace(".", "", 1).isdigit():
        formatted = _compact_number(float(value))
    else:
        formatted = str(value)
    if unit == "USD" and not formatted.startswith("$"):
        return f"${formatted}"
    return formatted


def _metric_evidence_period(record: dict[str, Any]) -> str | None:
    period = record.get("fact_period") or record.get("period")
    return str(period) if period is not None else None


def _compact_number(value: int | float) -> str:
    abs_value = abs(float(value))
    for threshold, suffix in (
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ):
        if abs_value >= threshold:
            return f"{value / threshold:.1f}{suffix}"
    return f"{value:g}"


def _clip(text: str, limit: int = 700) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}..."


def _is_zh_locale(language: str | None) -> bool:
    return str(language or "").lower().startswith("zh")
