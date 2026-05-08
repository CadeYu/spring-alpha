# Research Service Tool Contracts

## 目标

本文档定义 Spring Alpha Python Research Service 的 Agent tool 设计边界。当前文件是设计表，不包含业务实现。

核心原则：

- Domain tools are typed Python services.
- LangGraph tool adapters are optional wrappers.
- LlamaIndex owns RAG retrieval internals.
- Tool input and output must be serializable.
- Tool results must support eval, replay, and citation verification.

## Tool Layering

工具分为两层。

```text
Domain Tool
  -> Typed Python service
  -> Pydantic input schema
  -> Pydantic output schema
  -> Direct pytest and eval runner access

LangGraph Tool Adapter
  -> Optional tool-calling wrapper
  -> Converts graph/tool-call input into domain schema
  -> Converts domain output into JSON-safe result
```

业务逻辑不得只存在于 tool adapter 中。adapter 只做参数转换、权限检查、事件记录和错误归一化。

## Tool Categories

| Category | Tool | Input Contract | Output Contract | Owner |
| --- | --- | --- | --- | --- |
| Identity | `resolve_ticker` | `ResolveTickerInput` | `ResolveTickerOutput` | `CompanyIdentityService` |
| Identity | `get_company_profile` | `CompanyProfileInput` | `CompanyProfileOutput` | `CompanyProfileService` |
| Financial Facts | `get_company_facts` | `CompanyFactsInput` | `CompanyFactsOutput` | `FinancialFactsClient` |
| Financial Facts | `get_financial_snapshot` | `FinancialSnapshotInput` | `FinancialSnapshotOutput` | `FinancialSnapshotService` |
| Financial Facts | `get_historical_metrics` | `HistoricalMetricsInput` | `HistoricalMetricsOutput` | `FinancialHistoryService` |
| Filing | `get_latest_filing` | `LatestFilingInput` | `LatestFilingOutput` | `FilingClient` |
| Filing | `get_filing_sections` | `FilingSectionsInput` | `FilingSectionsOutput` | `FilingSectionService` |
| Filing | `get_filing_metadata` | `FilingMetadataInput` | `FilingMetadataOutput` | `FilingClient` |
| RAG | `retrieve_evidence` | `RetrieveEvidenceInput` | `RetrieveEvidenceOutput` | `RagService` |
| RAG | `retrieve_by_section` | `RetrieveBySectionInput` | `RetrieveEvidenceOutput` | `RagService` |
| RAG | `retrieve_by_metric` | `RetrieveByMetricInput` | `RetrieveEvidenceOutput` | `RagService` |
| RAG | `retrieve_more_like_this` | `RetrieveMoreLikeThisInput` | `RetrieveEvidenceOutput` | `RagService` |
| Extraction | `extract_business_drivers` | `ExtractBusinessDriversInput` | `ExtractBusinessDriversOutput` | `SignalExtractionService` |
| Extraction | `extract_cash_flow_signals` | `ExtractCashFlowSignalsInput` | `ExtractCashFlowSignalsOutput` | `SignalExtractionService` |
| Extraction | `extract_margin_signals` | `ExtractMarginSignalsInput` | `ExtractMarginSignalsOutput` | `SignalExtractionService` |
| Validation | `validate_citations` | `ValidateCitationsInput` | `ValidateCitationsOutput` | `CitationVerifier` |
| Validation | `validate_numbers` | `ValidateNumbersInput` | `ValidateNumbersOutput` | `NumberVerifier` |
| Validation | `validate_claim_support` | `ValidateClaimSupportInput` | `ValidateClaimSupportOutput` | `ClaimSupportVerifier` |
| Finalization | `finalize_report` | `FinalizeReportInput` | `FinalizeReportOutput` | `ReportAssembler` |

## MVP Allowed Tool Sets

### Latest Earnings Readout

| Phase | Allowed Tools |
| --- | --- |
| Identity | `resolve_ticker`, `get_company_profile` |
| Facts | `get_financial_snapshot`, `get_historical_metrics` |
| Filing | `get_latest_filing`, `get_filing_metadata` |
| Evidence | `retrieve_evidence`, `retrieve_by_section` |
| Extraction | `extract_business_drivers`, `extract_margin_signals` |
| Validation | `validate_numbers`, `validate_citations`, `validate_claim_support` |
| Finalization | `finalize_report` |

### Business Driver Deep Dive

| Phase | Allowed Tools |
| --- | --- |
| Identity | `resolve_ticker`, `get_company_profile` |
| Filing | `get_latest_filing`, `get_filing_sections` |
| Evidence | `retrieve_by_section`, `retrieve_more_like_this` |
| Extraction | `extract_business_drivers` |
| Validation | `validate_claim_support`, `validate_citations` |
| Finalization | `finalize_report` |

### Cash Flow and Capital Allocation

| Phase | Allowed Tools |
| --- | --- |
| Identity | `resolve_ticker`, `get_company_profile` |
| Facts | `get_financial_snapshot`, `get_historical_metrics` |
| Filing | `get_latest_filing`, `get_filing_sections` |
| Evidence | `retrieve_by_metric`, `retrieve_by_section`, `retrieve_evidence` |
| Extraction | `extract_cash_flow_signals` |
| Validation | `validate_numbers`, `validate_claim_support`, `validate_citations` |
| Finalization | `finalize_report` |

## Common Input Fields

Most tool input schemas should support:

| Field | Type | Required | Purpose |
| --- | --- | --- | --- |
| `run_id` | string | yes | Correlates tool calls, traces, eval artifacts, and logs |
| `ticker` | string | yes | Public ticker symbol |
| `task_type` | string | yes | MVP task type |
| `fiscal_period` | string | no | Optional period constraint |
| `filing_accession` | string | no | Optional SEC filing constraint |
| `section_filters` | array | no | SEC section constraints |
| `top_k` | integer | no | Retrieval result count |
| `budget` | object | no | Optional timeout, token, and cost budget |

## Common Output Fields

Most tool output schemas should support:

| Field | Type | Required | Purpose |
| --- | --- | --- | --- |
| `status` | string | yes | `ok`, `partial`, `empty`, `degraded`, or `error` |
| `data` | object | yes | Typed tool result payload |
| `events` | array | no | Structured event summaries |
| `latency_ms` | integer | yes | Runtime latency |
| `source_refs` | array | no | Source references used by the tool |
| `degraded_reasons` | array | no | Explicit reasons for partial output |
| `metrics` | object | no | Retrieval, cost, token, or validation metrics |

## Citation Status

Citation status must be explicit and conservative.

| Status | Meaning |
| --- | --- |
| `supported` | Evidence directly supports the claim |
| `partial` | Evidence supports part of the claim or requires caveats |
| `missing` | No adequate evidence was found |
| `unverified` | Verification did not run or could not complete |

## Error Policy

Tools must not throw raw provider exceptions across graph boundaries. They should return structured degraded or error outputs unless the graph itself cannot continue.

Required error fields:

- `error_code`
- `error_message`
- `retryable`
- `degraded_reason`
- `source`

## Adapter Policy

LangGraph or LangChain-style adapters may be used only at the boundary.

Allowed:

- Wrapping a typed domain service as a graph tool.
- Mapping Pydantic schemas into tool input schemas.
- Emitting structured tool events.

Not allowed:

- Storing business logic only in the adapter.
- Returning untyped strings for evidence records.
- Hiding retrieval metadata from eval runners.
- Emitting raw chain-of-thought.

## Evaluation Requirements

Every RAG-related tool call should produce enough metadata for later evaluation:

- Query text.
- Query rewrite text when applicable.
- Retrieved node ids.
- Section metadata.
- Filing metadata.
- Score and rerank score when available.
- Latency.
- Fallback status.
- Empty result status.

The eval runner should be able to call domain tools directly without LangGraph.
