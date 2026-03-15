#!/usr/bin/env python3

import json
import sys
from typing import Any


def normalize_number(value: Any):
    if value is None:
        return None

    try:
        if value != value:
            return None
    except Exception:
        pass

    try:
        return float(value)
    except Exception:
        return None


def normalize_period_end(value: Any) -> str | None:
    if value is None:
        return None

    if hasattr(value, "strftime"):
        try:
            return value.strftime("%Y-%m-%d")
        except Exception:
            pass

    text = str(value).strip()
    if not text:
        return None
    return text.split(" ")[0]


def read_statement_value(frame, labels, column):
    if frame is None or getattr(frame, "empty", True):
        return None

    for label in labels:
        if label in frame.index:
            try:
                value = frame.at[label, column]
            except Exception:
                continue
            normalized = normalize_number(value)
            if normalized is not None:
                return normalized
    return None


def collect_quarterly_financials(income_stmt, cashflow_stmt):
    statements = {}

    for frame in [income_stmt, cashflow_stmt]:
        if frame is None or getattr(frame, "empty", True):
            continue

        for column in frame.columns:
            period_end = normalize_period_end(column)
            if not period_end:
                continue

            snapshot = statements.setdefault(
                period_end,
                {
                    "periodEnd": period_end,
                    "revenue": None,
                    "grossProfit": None,
                    "operatingIncome": None,
                    "netIncome": None,
                    "operatingCashFlow": None,
                    "freeCashFlow": None,
                },
            )

            if snapshot["revenue"] is None:
                snapshot["revenue"] = read_statement_value(
                    income_stmt,
                    ["Total Revenue", "Operating Revenue"],
                    column,
                )
            if snapshot["grossProfit"] is None:
                snapshot["grossProfit"] = read_statement_value(income_stmt, ["Gross Profit"], column)
            if snapshot["operatingIncome"] is None:
                snapshot["operatingIncome"] = read_statement_value(income_stmt, ["Operating Income"], column)
            if snapshot["netIncome"] is None:
                snapshot["netIncome"] = read_statement_value(
                    income_stmt,
                    ["Net Income", "Net Income From Continuing Operation Net Minority Interest"],
                    column,
                )
            if snapshot["operatingCashFlow"] is None:
                snapshot["operatingCashFlow"] = read_statement_value(
                    cashflow_stmt,
                    ["Operating Cash Flow"],
                    column,
                )
            if snapshot["freeCashFlow"] is None:
                snapshot["freeCashFlow"] = read_statement_value(
                    cashflow_stmt,
                    ["Free Cash Flow"],
                    column,
                )

    return sorted(statements.values(), key=lambda item: item["periodEnd"], reverse=True)


def main() -> int:
    if len(sys.argv) < 2:
        print("Ticker argument is required.", file=sys.stderr)
        return 2

    ticker = sys.argv[1].strip().upper()
    if not ticker:
        print("Ticker argument is empty.", file=sys.stderr)
        return 2

    try:
        import yfinance as yf
    except ModuleNotFoundError:
        print("Python package 'yfinance' is not installed.", file=sys.stderr)
        return 3

    stock = yf.Ticker(ticker)

    info = {}
    fast_info = {}
    history = None
    quarterly_income_stmt = None
    quarterly_cashflow = None
    errors = []

    try:
        info = stock.info or {}
    except Exception as exc:
        errors.append(f"info: {exc}")

    try:
        fast_info = dict(stock.fast_info or {})
    except Exception as exc:
        errors.append(f"fast_info: {exc}")

    try:
        history = stock.history(period="5d", auto_adjust=False)
    except Exception as exc:
        errors.append(f"history: {exc}")

    try:
        quarterly_income_stmt = stock.quarterly_income_stmt
    except Exception as exc:
        errors.append(f"quarterly_income_stmt: {exc}")

    try:
        quarterly_cashflow = stock.quarterly_cashflow
    except Exception as exc:
        errors.append(f"quarterly_cashflow: {exc}")

    company_name = info.get("shortName") or info.get("longName") or info.get("displayName")
    sector = info.get("sectorDisp") or info.get("sector")
    industry = info.get("industryDisp") or info.get("industry")
    security_type = info.get("quoteType") or info.get("typeDisp")
    business_summary = info.get("longBusinessSummary") or info.get("description")
    latest_price = (
        info.get("currentPrice")
        or info.get("regularMarketPrice")
        or fast_info.get("lastPrice")
        or fast_info.get("regularMarketPrice")
    )
    market_cap = info.get("marketCap") or fast_info.get("marketCap")
    price_to_earnings_ratio = normalize_number(info.get("trailingPE"))
    if price_to_earnings_ratio is None:
        trailing_eps = normalize_number(info.get("trailingEps"))
        if latest_price is not None and trailing_eps not in (None, 0):
            try:
                price_to_earnings_ratio = float(latest_price) / float(trailing_eps)
            except Exception:
                price_to_earnings_ratio = None
    price_to_book_ratio = normalize_number(info.get("priceToBook"))

    if latest_price is None and history is not None and not history.empty:
        try:
            latest_price = float(history["Close"].dropna().iloc[-1])
        except Exception:
            pass

    quarterly_financials = collect_quarterly_financials(quarterly_income_stmt, quarterly_cashflow)

    payload = {
        "profileAvailable": company_name is not None,
        "quoteAvailable": latest_price is not None,
        "valuationAvailable": price_to_earnings_ratio is not None or price_to_book_ratio is not None,
        "companyName": company_name,
        "sector": sector,
        "industry": industry,
        "securityType": security_type,
        "latestPrice": latest_price,
        "marketCap": market_cap,
        "priceToEarningsRatio": price_to_earnings_ratio,
        "priceToBookRatio": price_to_book_ratio,
        "quarterlyFinancials": quarterly_financials,
        "message": None if not errors else "; ".join(errors),
        "businessSummary": business_summary,
    }

    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
