# Testing Plan

This document defines the executable testing strategy for Spring Alpha. The goal is not just to verify that pages render, but to make sure the full chain remains reliable under real-world conditions: FMP latency, SEC parsing changes, vector-store dimension drift, SSE streaming, model schema drift, BYOK failures, and degraded-source fallback behavior.

## Current Progress

Last updated: 2026-03-09

Automated test status:

- Backend: `34/34 pass`
- Frontend: `11/11 pass`
- E2E Smoke: `2/2 pass`
- Total: `47/47 pass`

Completed files:

- [x] `backend/src/test/java/com/springalpha/backend/controller/SecControllerTest.java`
- [x] `backend/src/test/java/com/springalpha/backend/service/FinancialAnalysisServiceTest.java`
- [x] `backend/src/test/java/com/springalpha/backend/service/SecServiceTest.java`
- [x] `backend/src/test/java/com/springalpha/backend/service/strategy/BaseAiStrategyTest.java`
- [x] `backend/src/test/java/com/springalpha/backend/service/validation/AnalysisReportValidatorTest.java`
- [x] `backend/src/test/java/com/springalpha/backend/financial/service/FmpFinancialDataServiceTest.java`
- [x] `frontend/src/app/page.test.tsx`
- [x] `frontend/src/components/pdf/pdf.test.tsx`
- [x] `frontend/e2e/smoke.spec.ts`

Latest verified commands:

- [x] `cd backend && mvn -Dtest=SecControllerTest,SecServiceTest,FinancialAnalysisServiceTest,BaseAiStrategyTest,AnalysisReportValidatorTest,FmpFinancialDataServiceTest test`
- [x] `cd frontend && npm test`
- [x] `cd frontend && npm run test:e2e`
- [x] `cd frontend && npx tsc --noEmit`
- [x] `cd frontend && npm run lint`

Remaining high-priority gaps:

- [x] frontend stale SSE chunk isolation / overlap prevention
- [x] backend/controller SSE integration tests
- [x] `SecService` parsing tests
- [x] PDF rendering assertions
- [x] E2E smoke suite
- [ ] manual release checklist signoff record
- [x] CI workflow and local unified check command

The project depends on external services, so "万无一失" here means:

- deterministic logic is covered by automated tests
- unstable external-provider behavior is covered by controlled integration tests and manual release checks
- each failure mode has a known expected UI/backend outcome

## 1. Test Objectives

The suite must protect these business-critical guarantees:

1. Financial numbers come from FMP and are not hallucinated.
2. SEC/RAG failures never produce fake citations.
3. First-run vector ingestion degrades gracefully; second-run retrieval recovers.
4. BYOK/OpenAI failures are explicit and do not hang the UI.
5. Repeated user actions do not corrupt state or mix old/new SSE results.
6. Report metadata shows the correct ticker, company name, filing period, and date.

## 2. Test Pyramid

### 2.1 Unit Tests

Use unit tests for deterministic logic only.

Backend targets:

- `backend/src/main/java/com/springalpha/backend/service/validation/AnalysisReportValidator.java`
- `backend/src/main/java/com/springalpha/backend/service/strategy/BaseAiStrategy.java`
- `backend/src/main/java/com/springalpha/backend/financial/service/FmpFinancialDataService.java`
- `backend/src/main/java/com/springalpha/backend/service/rag/VectorRagService.java`

Frontend targets:

- `frontend/src/app/page.tsx`
- `frontend/src/components/analysis/ExecutiveSummary.tsx`
- source citation/degraded-state rendering
- report header metadata rendering

### 2.2 Integration Tests

Use integration tests to verify controller-to-service behavior without hitting real FMP/SEC/OpenAI.

Backend integration targets:

- `backend/src/main/java/com/springalpha/backend/controller/SecController.java`
- `backend/src/main/java/com/springalpha/backend/service/FinancialAnalysisService.java`
- `backend/src/main/java/com/springalpha/backend/service/SecService.java`

Requirements:

- mock FMP responses
- mock SEC responses
- mock LLM responses
- simulate vector-store dimension mismatch
- simulate first-run/no-vector and second-run/has-vector

### 2.3 End-to-End Tests

Use a thin smoke suite to validate the actual user journey in browser context.

Primary goals:

- analysis submission
- language switch
- model switch
- BYOK validation
- SSE partial updates
- degraded-source rendering
- PDF trigger path

### 2.4 Manual Regression

Manual checks remain required before release because:

- SEC HTML shape changes over time
- FMP availability and latency vary
- ChatAnywhere/OpenAI/Groq limits are externally controlled
- PDF layout quality is visual, not purely structural

## 3. Test Environments

### 3.1 Local Development

Purpose:

- fast feedback while coding
- compile/type/lint checks
- unit tests
- mocked integration tests

Commands:

```bash
cd backend && mvn -o -DskipTests compile
cd backend && mvn -o test
cd frontend && npm run lint
cd frontend && npx tsc --noEmit
```

Note:

- local Maven test execution may still fail if the machine is missing cached test dependencies
- this should be treated as an environment issue, not a code-quality pass

### 3.2 CI Environment

Purpose:

- block obvious regressions
- run deterministic tests only

Recommended CI gates:

1. backend compile
2. backend unit/integration tests with mocks
3. frontend lint
4. frontend typecheck
5. frontend component tests
6. one E2E smoke test against mocked/stable backend responses

### 3.3 Pre-Release Manual Environment

Purpose:

- verify real external-provider behavior
- verify real Neon/PGVector state
- verify first-run vs second-run vector behavior

## 4. Critical Scenarios

### 4.1 Happy Path

Run for:

- `AAPL`
- `MSFT`
- `TSLA`

For each:

- `zh`
- `en`
- `chatanywhere`
- `groq`

Expected:

- report renders completely
- title includes ticker + company full name + period/date
- no fake citation placeholders
- charts load
- no infinite loading

### 4.2 OpenAI BYOK

Cases:

- no key entered
- invalid key
- key with quota/rate-limit failure
- valid key

Expected:

- missing key blocks request before backend call
- invalid key shows explicit failure
- 429/quota errors are surfaced clearly
- valid key completes analysis

### 4.3 First-Run Vector Ingestion

Case:

- ticker has no existing vector chunks

Expected:

- SEC fetch succeeds
- raw filing text fallback is used
- UI shows degraded-source explanation
- background vector ingestion starts and finishes

### 4.4 Second-Run RAG Recovery

Case:

- rerun the same ticker after first-run ingestion completes

Expected:

- backend logs `already in vector DB, using semantic search`
- backend logs successful vector retrieval
- UI shows real citations instead of degraded-source card

### 4.5 Vector Dimension Drift

Case:

- database contains an old `vector_store.embedding` dimension

Expected:

- startup detects mismatch
- table is rebuilt once
- subsequent ingestion uses current dimension
- no repeated `3072 vs 768` failures

### 4.6 SEC Failure

Simulate:

- search fails
- primary document parse fails
- HTML download fails

Expected:

- analysis degrades to FMP-only
- no citations shown
- UI states that SEC evidence was unavailable

### 4.7 FMP Failure / Timeout

Simulate:

- read timeout
- partial endpoint failure
- ratio endpoint failure only

Expected:

- request fails quickly instead of hanging
- logs show explicit timeout/failure
- UI shows error or partial fallback, depending on endpoint role

### 4.8 Repeated User Actions

Cases:

- double-click analyze
- rapidly switch `TSLA -> AAPL -> MSFT`
- click again while prior request is streaming

Expected:

- old analysis request is aborted
- old history request is aborted
- final page only reflects the latest ticker/request
- no mixed SSE chunks

## 5. Backend Automated Test Plan

### 5.1 AnalysisReportValidator

Add tests for:

- [x] valid citation -> `VERIFIED`
- [x] placeholder citation -> removed
- [ ] empty excerpt -> removed
- [x] source missing -> `UNVERIFIED` or filtered
- [x] duplicate citation -> deduplicated

### 5.2 BaseAiStrategy

Add tests for:

- [ ] unwrap `analysisReport` root
- [ ] parse markdown fenced JSON
- [x] fix array/string mismatches
- [x] normalize Chinese sentiment values to canonical English
- [x] build `coreThesis` from legacy summary
- [x] suppress citations when evidence is unavailable
- [x] preserve explicit `sourceContext`
- [x] backfill legacy summary from thesis headline when needed

### 5.3 FmpFinancialDataService

Add tests for:

- [x] company name extraction from income statement
- [ ] company name fallback via profile endpoint
- [x] period resolution from year/date fields
- [x] filing date extraction
- [ ] fetch timeout does not block forever
- [ ] ratio endpoint failure does not kill full analysis facts

### 5.4 FinancialAnalysisService

Add tests for:

- [x] no vectors -> degraded mode + background ingestion
- [x] existing vectors -> semantic retrieval path
- [x] vector dimension mismatch -> delete/reset/reingest path
- [x] evidence unavailable -> `sourceContext=DEGRADED`
- [x] initial SSE skeleton includes metadata fields

### 5.5 SecService

Add tests for:

- [x] index page parsing
- [x] primary document link parsing
- [x] iXBRL viewer link normalization
- [x] HTML cleaning preserves useful text
- [x] MD&A location fallback behavior

## 6. Frontend Automated Test Plan

### 6.1 `page.tsx`

Add tests for:

- [x] clicking analyze starts request
- [ ] clicking again aborts previous request
- [x] history request abort does not overwrite new state
- [x] SSE partial merge preserves earlier good fields
- [x] degraded-source state shows warning card
- [x] grounded citation state hides degraded warning
- [x] title renders `ticker + companyName + period + filingDate`
- [x] BYOK request includes saved OpenAI key

### 6.2 Citation Area

Add tests for:

- [x] no citations + degraded state
- [x] real citations + verification status
- [x] placeholder citations never rendered

### 6.3 PDF Path

Add checks for:

- [x] title metadata is present
- [x] degraded-source note appears when citations unavailable
- [x] citations render when available

## 7. E2E Smoke Suite

Use a small smoke suite, not a huge matrix.

Minimum cases:

1. [x] free-model grounded report path with mocked SSE/history
2. [ ] `TSLA`, Chinese, first run, degraded-source visible
3. [ ] `TSLA`, Chinese, second run, citations visible
4. [x] OpenAI BYOK selected with no key -> inline validation error
5. [ ] Rapid ticker switch -> final ticker wins
6. [ ] PDF download button enabled after report load

If external-provider instability makes CI flaky, run these with mocked backend responses in CI and reserve real-provider verification for manual release checks.

## 8. Manual Release Checklist

Run this before every deployment:

### 8.1 Startup

- backend starts cleanly
- `vector_store` dimension matches expected config
- no startup bean conflicts

### 8.2 Free Models

- `AAPL`, `chatanywhere`, `zh`
- `MSFT`, `groq`, `en`

Verify:

- complete report
- no fake citations
- no hanging requests

### 8.3 RAG Recovery

- clear/reseed one ticker if needed
- run `TSLA` once
- wait for ingestion completion
- run `TSLA` again

Verify:

- first run shows degraded-source notice
- second run shows grounded citations

### 8.4 BYOK

- no key
- invalid key
- valid key

Verify:

- inline validation
- clear error messages
- no silent fallback to wrong model

### 8.5 UI/Content

- title shows company full name, period, and date
- zh/en both read correctly
- source card text matches backend state
- charts load without console errors

### 8.6 PDF

- download succeeds
- metadata/title correct
- no missing sections

### 8.7 Signoff Record Template

Copy this block for each release candidate and mark the real-provider checks you actually ran:

```md
Release Candidate: __________
Date: __________
Tester: __________
Frontend Commit: __________
Backend Commit: __________

Automated Gates
- [ ] backend deterministic tests pass
- [ ] frontend unit/component tests pass
- [ ] frontend lint passes
- [ ] frontend typecheck passes
- [ ] E2E smoke passes

Real-Provider Checks
- [ ] AAPL / zh / chatanywhere
- [ ] MSFT / en / groq
- [ ] TSLA first run shows degraded-source notice
- [ ] TSLA second run shows grounded citations
- [ ] OpenAI BYOK invalid key shows explicit error
- [ ] OpenAI BYOK valid key completes analysis
- [ ] PDF export opens with correct metadata

Notes
- External provider incidents observed: __________
- Remaining known risks accepted for release: __________
- Go / No-Go: __________
```

## 9. Failure Classification

Every major failure should map to one of these buckets:

1. `FMP_UNAVAILABLE`
2. `SEC_FETCH_FAILED`
3. `RAG_NOT_READY`
4. `VECTOR_DIMENSION_MISMATCH`
5. `MODEL_RATE_LIMIT`
6. `MODEL_INVALID_KEY`
7. `MODEL_SCHEMA_DRIFT`
8. `FRONTEND_ABORT_OR_STALE_STATE`

This classification should appear in logs and, where user-facing, in friendly UI copy.

## 10. Release Gate Recommendation

Do not ship unless all of these are true:

- backend compile passes
- frontend typecheck passes
- frontend lint passes
- backend deterministic tests pass
- no fake citations are rendered in degraded mode
- first-run/second-run TSLA behavior is verified
- BYOK invalid-key behavior is verified

## 11. Immediate Next Steps

To operationalize this document, implement in this order:

1. [x] backend unit tests for validator, strategy normalization, FMP metadata parsing
2. [x] frontend tests for `page.tsx` abort/SSE/degraded-state logic
3. [x] backend integration tests for first-run vs second-run TSLA flow
4. [x] frontend stale SSE isolation tests
5. [x] `SecService` tests
6. [x] small E2E smoke suite
7. [x] release checklist signoff process
