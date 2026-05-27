# Cash Flow Agent Refactor Design

## Goal

Refactor the Cash Flow & Capital Allocation agent into a yfinance-first,
structured-data analyst report. The report should read like a focused
fundamentals analyst note while preserving Spring Alpha's typed dashboard
contract.

## Product Shape

The cash flow agent answers one question:

```text
Can this business turn earnings into durable cash, and is management allocating that cash well?
```

The main report should use seven visible sections:

1. Cash Quality Verdict
2. Cash Flow Bridge
3. Capex and Reinvestment
4. Balance Sheet Resilience and Debt
5. Risk Signals and Watch Next
6. Key Cash Metrics Table
7. Final Analyst Outlook

Shareholder returns are not a standalone top-level section. Buybacks and
dividends may appear as table rows, risk signals, or analyst commentary only
when the structured source provides useful data.

## Data Source Priority

Cash flow analysis should prefer structured data over RAG.

```text
Primary: yfinance structured financial statements and profile data
Fallback: SEC companyfacts
Optional supplement: SEC filing RAG narrative
```

The yfinance source should provide, when available:

- quarterly income statement values: revenue, operating income, net income
- quarterly cash flow values: operating cash flow, capex, free cash flow
- balance sheet and profile values: cash, current assets, current liabilities,
  current ratio, total debt, market cap, sector, industry

SEC companyfacts remains the official fallback and citation source when
yfinance lacks a field or when the Java backend already preloaded SEC facts.

RAG is not allowed to block the main cash flow report. It may add explanation
from MD&A, Liquidity and Capital Resources, debt maturity, capex rationale, or
working-capital commentary.

## Empty Value Policy

The main report should not render empty dashboard slots.

```text
If a section has enough structured data, render it.
If a section does not have enough data, omit it or fold the limitation into Risk Signals.
If a field is missing, record it in coverage or diagnostics, not as a main card.
```

User-facing copy should avoid phrases such as:

- No evidence for this lens.
- This dimension has no evidence.
- Evidence-backed fallback cash view.
- Cash flow evidence anchor.

Missing fields should be visible only through coverage metadata, developer
diagnostics, or a compact "Data Coverage" note.

## Typed Contract Mapping

The existing `CashFlowCapitalAllocationSections` contract remains compatible.

```text
cashQualityVerdict      -> Cash Quality Verdict
cashMetrics             -> Key Cash Metrics Table and Cash Flow Bridge
capitalAllocation.capex -> Capex and Reinvestment, only when populated
capitalAllocation.debt  -> Balance Sheet Resilience and Debt, only when populated
capitalAllocation.liquidity -> Balance Sheet Resilience and Debt, only when populated
allocationDiscipline    -> Final Analyst Outlook support points
redFlags                -> Risk Signals and Watch Next
```

The `capitalAllocation.buybacks` and `capitalAllocation.dividends` arrays may
remain in the contract for backward compatibility, but the redesigned main UI
must not render them as fixed empty cards.

## Report Layout

```text
+------------------------------------------------------------+
| AAPL Cash Flow & Capital Allocation Report                 |
| Latest period | Source: yfinance primary, SEC fallback     |
+------------------------------------------------------------+
| 1. Cash Quality Verdict                                    |
| 2. Cash Flow Bridge                                        |
| 3. Capex and Reinvestment                                  |
| 4. Balance Sheet Resilience and Debt                       |
| 5. Risk Signals and Watch Next                             |
+------------------------------------------------------------+
| Key Cash Metrics Table                                     |
+------------------------------------------------------------+
| Final Analyst Outlook                                      |
+------------------------------------------------------------+
```

## Acceptance Criteria

- A cash flow report can complete without RAG.
- A cash flow report can complete when final LLM synthesis times out.
- The primary report never renders fixed empty cards for buybacks, dividends,
  debt, or liquidity.
- The Cash Flow Bridge includes at least operating cash flow, capex, and free
  cash flow when those fields exist.
- The Key Cash Metrics Table renders only real metrics with useful values.
- Fallback output reads like an analyst note, not a schema placeholder.
- Local tests cover yfinance-first cash flow facts, deterministic fallback, and
  frontend omission of empty sections.

## Suggested Commit Message

```text
Refactor cash flow agent around structured fundamentals
```
