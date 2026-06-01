from __future__ import annotations

import re

_ZH_MARKET_CLASSIFICATION_LABELS = {
    "technology": "科技",
    "software - infrastructure": "基础设施软件",
    "software infrastructure": "基础设施软件",
    "software - application": "应用软件",
    "software application": "应用软件",
    "semiconductors": "半导体",
    "financial services": "金融服务",
    "basic materials": "基础材料",
    "specialty chemicals": "特种化学品",
    "consumer defensive": "防御消费",
    "beverages - non - alcoholic": "非酒精饮料",
    "beverages - non-alcoholic": "非酒精饮料",
    "beverages non alcoholic": "非酒精饮料",
    "industrials": "工业",
    "infrastructure operations": "基础设施运营",
    "credit services": "信贷与支付服务",
    "banks - diversified": "综合银行",
    "consumer cyclical": "可选消费",
    "auto manufacturers": "汽车制造",
    "healthcare": "医疗健康",
    "healthcare plans": "医疗保险计划",
    "consumer electronics": "消费电子",
    "internet content & information": "互联网内容与信息",
    "internet retail": "互联网零售",
    "entertainment": "娱乐内容",
    "restaurants": "餐饮",
    "aerospace & defense": "航空航天与国防",
    "oil & gas integrated": "综合油气",
    "communication services": "通信服务",
}


def localize_market_classification(
    sector: str | None,
    industry: str | None = None,
) -> str:
    labels = [
        localize_market_label(value)
        for value in (sector, industry)
        if str(value or "").strip()
    ]
    return " / ".join(label for label in labels if label)


def localize_market_label(value: str | None) -> str:
    text = " ".join(str(value or "").replace("_", " ").split()).strip()
    if not text:
        return ""
    return _ZH_MARKET_CLASSIFICATION_LABELS.get(text.lower(), text)


def localize_market_classifications_in_text(text: str) -> str:
    localized = str(text or "")
    for source, replacement in sorted(
        _ZH_MARKET_CLASSIFICATION_LABELS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        localized = re.sub(rf"\b{re.escape(source)}\b", replacement, localized, flags=re.I)
    return localized


def summarize_english_business_snippet_for_zh(text: str) -> str:
    normalized = " ".join(str(text or "").split()).strip()
    if not normalized:
        return normalized
    lower = normalized.lower()
    segment_markers = (
        "operates through",
        "segment provides",
        "segments:",
        "compute & networking",
        "graphics",
        "business segments",
    )
    if "segment" in lower and any(marker in lower for marker in segment_markers):
        return (
            "已检索到分部或业务线披露片段，说明公司存在可追踪的业务线暴露，"
            "但当前中文摘要仅作为方向性证据。"
        )
    profile_markers = (
        "operates as",
        "provides",
        "sells",
        "designs",
        "manufactures",
    )
    if any(marker in lower for marker in profile_markers) and _english_word_count(normalized) >= 8:
        return "已检索到英文业务摘要，说明公司具备可分析的产品、客户或市场暴露线索。"
    return normalized


def _english_word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z][A-Za-z\-]{2,}", text))
