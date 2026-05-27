from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

CASH_FLOW_CORE_METRICS = (
    "net income",
    "operating cash flow",
    "capital expenditures",
    "free cash flow",
    "current ratio",
    "total debt",
    "cash and short term investments",
)

_FACT_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "net income": ("netIncome", "net_income"),
    "operating cash flow": ("operatingCashFlow", "operating_cash_flow"),
    "capital expenditures": ("capitalExpenditures", "capital_expenditures"),
    "free cash flow": ("freeCashFlow", "free_cash_flow"),
    "current ratio": ("currentRatio", "current_ratio"),
    "total debt": ("totalDebt", "total_debt"),
    "cash and short term investments": (
        "cashAndShortTermInvestments",
        "cash_and_short_term_investments",
    ),
    "current assets": ("currentAssets", "current_assets"),
    "current liabilities": ("currentLiabilities", "current_liabilities"),
}

_UNITS_BY_METRIC = {
    "current ratio": "x",
}

_METRIC_ALIASES: dict[str, str] = {
    "total revenue": "revenue",
    "total revenues": "revenue",
    "net sales": "revenue",
    "operating income loss": "operating income",
    "operating cashflow": "operating cash flow",
    "operating cash flows": "operating cash flow",
    "cash flow from operations": "operating cash flow",
    "cash from operations": "operating cash flow",
    "capital expenditure": "capital expenditures",
    "capex": "capital expenditures",
    "cash cash equivalents and short term investments": ("cash and short term investments"),
    "cash and cash equivalents": "cash and short term investments",
    "short term investments and cash": "cash and short term investments",
    "share buybacks": "buybacks",
    "stock buybacks": "buybacks",
}


def normalize_metric_name(metric: str) -> str:
    text = str(metric or "").strip()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = text.replace("&", " and ")
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    text = re.sub(r"[/_-]+", " ", text)
    normalized = re.sub(r"\s+", " ", text.lower()).strip()
    return _METRIC_ALIASES.get(normalized, normalized)


def structured_metric_records_from_facts(
    facts: Mapping[str, Any],
) -> list[dict[str, Any]]:
    records = [
        *_explicit_metric_records(facts),
        *_top_level_metric_records(facts),
        *_quarterly_metric_records(facts),
    ]
    return _dedupe_records_by_metric(records)


def cash_flow_metric_records_from_facts(
    facts: Mapping[str, Any],
) -> list[dict[str, Any]]:
    records_by_metric = {
        normalize_metric_name(str(record.get("name") or "")): record
        for record in structured_metric_records_from_facts(facts)
    }
    return [
        records_by_metric[metric]
        for metric in CASH_FLOW_CORE_METRICS
        if metric in records_by_metric
    ]


def _explicit_metric_records(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    metrics = facts.get("metrics")
    if not isinstance(metrics, list):
        return []
    records: list[dict[str, Any]] = []
    for metric in metrics:
        if not isinstance(metric, Mapping):
            continue
        name = normalize_metric_name(str(metric.get("name") or ""))
        if not name or metric.get("value") is None:
            continue
        record = dict(metric)
        record["name"] = name
        record.setdefault("source", "preloaded_financial_facts")
        records.append(record)
    return records


def _top_level_metric_records(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    period = _optional_str(facts.get("period"))
    filed = _optional_str(facts.get("filing_date")) or _optional_str(facts.get("filingDate"))
    records = [
        _record_from_mapping(
            facts,
            metric,
            period=period,
            filed=filed,
            source="preloaded_financial_facts",
        )
        for metric in CASH_FLOW_CORE_METRICS
    ]
    return [record for record in records if record is not None]


def _quarterly_metric_records(facts: Mapping[str, Any]) -> list[dict[str, Any]]:
    snapshots = facts.get("quarterlyFinancials") or facts.get("quarterly_financials")
    if not isinstance(snapshots, list):
        return []
    snapshot = _best_quarterly_snapshot(snapshots)
    if snapshot is None:
        return []
    period = _optional_str(snapshot.get("periodEnd")) or _optional_str(snapshot.get("period_end"))
    records = [
        _record_from_mapping(
            snapshot,
            metric,
            period=period,
            source="preloaded_financial_facts",
        )
        for metric in CASH_FLOW_CORE_METRICS
    ]
    return [record for record in records if record is not None]


def _record_from_mapping(
    mapping: Mapping[str, Any],
    metric: str,
    *,
    period: str | None,
    source: str,
    filed: str | None = None,
) -> dict[str, Any] | None:
    value = _metric_value(mapping, metric)
    if value is None:
        return None
    record: dict[str, Any] = {
        "name": metric,
        "value": value,
        "source": source,
    }
    unit = _UNITS_BY_METRIC.get(metric, "USD")
    if unit:
        record["unit"] = unit
    if period:
        record["period"] = period
    if filed:
        record["filed"] = filed
    return record


def _metric_value(mapping: Mapping[str, Any], metric: str) -> Any:
    direct_value = _first_mapping_value(mapping, _FACT_FIELD_ALIASES.get(metric, ()))
    if direct_value is not None:
        return direct_value
    if metric == "current ratio":
        current_assets = _numeric_value(
            _first_mapping_value(mapping, _FACT_FIELD_ALIASES["current assets"])
        )
        current_liabilities = _numeric_value(
            _first_mapping_value(mapping, _FACT_FIELD_ALIASES["current liabilities"])
        )
        if current_assets is not None and current_liabilities not in (None, 0):
            return current_assets / current_liabilities
    if metric == "free cash flow":
        operating_cash_flow = _numeric_value(
            _first_mapping_value(mapping, _FACT_FIELD_ALIASES["operating cash flow"])
        )
        capex = _numeric_value(
            _first_mapping_value(mapping, _FACT_FIELD_ALIASES["capital expenditures"])
        )
        if operating_cash_flow is not None and capex is not None:
            return operating_cash_flow - abs(capex)
    return None


def _best_quarterly_snapshot(snapshots: list[Any]) -> Mapping[str, Any] | None:
    candidates = [snapshot for snapshot in snapshots if isinstance(snapshot, Mapping)]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda snapshot: (_snapshot_score(snapshot), _snapshot_period(snapshot)),
    )


def _snapshot_score(snapshot: Mapping[str, Any]) -> int:
    return sum(
        1 for metric in CASH_FLOW_CORE_METRICS if _metric_value(snapshot, metric) is not None
    )


def _snapshot_period(snapshot: Mapping[str, Any]) -> str:
    return (
        _optional_str(snapshot.get("periodEnd")) or _optional_str(snapshot.get("period_end")) or ""
    )


def _first_mapping_value(mapping: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe_records_by_metric(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for record in records:
        name = normalize_metric_name(str(record.get("name") or ""))
        if not name or name in seen:
            continue
        record["name"] = name
        seen.add(name)
        deduped.append(record)
    return deduped
