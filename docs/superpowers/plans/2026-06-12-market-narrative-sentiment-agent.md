# Market Narrative Sentiment Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the weak business-driver analyst lane with a TradingAgents-style market narrative and sentiment analyst while keeping the existing `business_driver_deep_dive` task id compatible during the migration.

**Architecture:** The research-service will stop using SEC/RAG-driven tool-calling for this lane. It will prefetch Yahoo Finance news, StockTwits messages, and Reddit discussion blocks before invoking the LLM, then synthesize a structured sentiment report. Backend and frontend contracts will add sentiment-native typed sections while retaining legacy business-driver section compatibility for old cached reports.

**Tech Stack:** Python FastAPI research-service, LangChain chat model adapter, Pydantic typed contracts, Java Spring backend mapper, Next.js/React frontend, Vitest/pytest/JUnit tests.

---

## Product Decision

The current `business_driver_deep_dive` agent tries to infer business drivers from SEC/RAG/company facts. That does not match the user-facing expectation for many tickers, creates thin or generic output, and overlaps with latest earnings and cash-flow lanes. The replacement lane is:

- English title: `Market Narrative & Sentiment`
- Chinese title: `市场叙事与情绪`
- Existing task id: `business_driver_deep_dive` for API compatibility
- Agent name: `Sentiment analyst`
- Primary sources: Yahoo Finance news, StockTwits, Reddit
- Explicit non-goal: fundamental business-driver proof from SEC/RAG

## Acceptance Criteria

1. Running `business_driver_deep_dive` must not require `search_filing_sections`, `search_metric_evidence`, `get_business_signals`, `build_evidence_pack`, RAG, or Qdrant.
2. The agent must prefetch three data blocks before final synthesis: Yahoo Finance news, StockTwits, and Reddit.
3. Each source must degrade gracefully with a visible unavailable/no-data marker instead of raising the run into failure.
4. The final typed sections must include `sentimentHeader`, `narrativeSnapshot`, `bullBearNarrative`, `sourceDivergence`, and `noiseWarnings`.
5. The LLM prompt must forbid inventing Reddit/X/StockTwits content when a source block is unavailable or empty.
6. Chinese output must use Chinese UI copy and Chinese report prose, while preserving proper nouns such as Yahoo Finance, StockTwits, Reddit, Bullish, Bearish, and ticker symbols.
7. Old cached reports with `driverThesis` / `driverMap` must still render without a blank page.
8. Frontend task card and report UI must no longer say “Business Driver Deep Dive” / “业务驱动深挖” for the active lane.
9. Tool timeline should show sentiment-source collection events instead of business-driver SEC/RAG tools.
10. Tests must cover source degradation, structured payload normalization, frontend rendering, and legacy compatibility.
11. After implementation, run: `uv run pytest -q`, targeted frontend tests, Java tests if mapper contracts change, and `git diff --check`.

## Files And Responsibilities

### Backend research-service

- Modify `backend/research-service/app/contracts/report.py`
  - Add sentiment-native Pydantic models.
  - Keep legacy business-driver models only for compatibility if needed.

- Create `backend/research-service/app/agents/sentiment_sources.py`
  - Fetch and format Yahoo Finance news, StockTwits, and Reddit blocks.
  - Return typed source blocks with status and degraded reason.

- Replace or heavily rewrite `backend/research-service/app/agents/business_driver_agent.py`
  - Keep exported function name `run_business_driver_agent` for workflow compatibility.
  - Internally implement prefetch-plus-synthesis sentiment flow.
  - Remove old SEC/RAG tool-calling path.

- Modify `backend/research-service/app/agents/report_synthesizer.py`
  - Normalize sentiment payloads into new typed sections.
  - Keep legacy fallback path for old `driverThesis` / `driverMap` payloads only if required by tests.
  - Remove the obsolete standalone business-driver LLM synthesis prompt so this lane cannot accidentally fall back to SEC/RAG business-driver generation.

- Modify `backend/research-service/app/agents/research_workflow.py`
  - Remove business-driver-specific noisy retrieval cleanup and timeout fallback paths that only exist for old SEC/RAG business driver logic.
  - Preserve generic degraded behavior.

- Delete if unused after replacement:
  - Old standalone business-driver prompt and synthesis entry points in `report_synthesizer.py`.
  - Old business-driver-only tests whose assertions encode SEC/RAG driver behavior.
  - Keep `backend/research-service/app/agents/business_driver_quality.py` as a legacy compatibility helper while `driverThesis` / `driverMap` cached reports can still be normalized and rendered.

### Java backend

- Modify `backend/src/main/java/com/springalpha/backend/financial/contract/AnalysisReport.java`
  - Add sentiment-native section classes.
  - Keep legacy fields ignored or optional for compatibility.

- Modify `backend/src/main/java/com/springalpha/backend/financial/contract/ResearchTaskProfile.java`
  - Update title, description, search terms, and required section names.

- Modify `backend/src/main/java/com/springalpha/backend/service/research/ResearchAgentReportMapper.java`
  - Sanitize sentiment evidence refs without applying old business-driver SEC noise heuristics.

### Frontend

- Modify `frontend/src/types/AnalysisReport.ts`
  - Add sentiment-native section interfaces.
  - Preserve legacy `BusinessDriverSections` shape as a union/compat type if needed.

- Modify `frontend/src/components/app/earnings-analyst-app.tsx`
  - Update task label and icon if appropriate.
  - Replace typed business-driver section renderer with sentiment report renderer.
  - Keep a legacy renderer branch for old cached reports.

- Modify `frontend/src/lib/agentTimelineCopy.ts`
  - Localize sentiment analyst events.

- Update tests in `frontend/src/app/page.test.tsx` and related component tests.

## Implementation Tasks

### Task 1: Backend source fetchers

- [ ] Write tests in `backend/research-service/tests/test_sentiment_sources.py` for StockTwits, Reddit, and Yahoo news formatting with mocked transports.
- [ ] Implement `sentiment_sources.py` with short timeouts, graceful degraded source blocks, and no API keys.
- [ ] Verify tests fail before implementation and pass after implementation.

### Task 2: Sentiment report contract

- [ ] Write tests in `backend/research-service/tests/test_report_synthesizer_locale.py` proving sentiment payload normalizes into typed sections.
- [ ] Add Pydantic models: `SentimentHeader`, `BullBearNarrative`, `SourceDivergence`, `MarketNarrativeSentimentSections`.
- [ ] Update `TaskSpecificSections` discriminator while keeping the task id `business_driver_deep_dive`.
- [ ] Verify old legacy payload still normalizes and renders.

### Task 3: Replace business-driver agent internals

- [ ] Rewrite tests in `backend/research-service/tests/test_business_driver_agent_quality.py` so they expect sentiment source prefetch, not SEC/RAG tools.
- [ ] Change `run_business_driver_agent` to collect Yahoo news, StockTwits, Reddit, add tool events, and make one final LLM call.
- [ ] Ensure prompt says to use unavailable markers honestly and never invent missing social data.
- [ ] Keep exported error class and function names for workflow compatibility.

### Task 4: Remove dead business-driver SEC/RAG code

- [ ] Run `rg` to find remaining references to `business_driver_quality` and old business-driver fallback helpers.
- [ ] Delete unused old prompt/synthesis entry points only after all references are gone.
- [ ] Keep helper modules that are still referenced by legacy `driverThesis` / `driverMap` normalization.
- [ ] Simplify `research_workflow.py` by removing old business-driver retrieval cleanup and fallback section builders.

### Task 5: Java mapper and task profile

- [ ] Add Java section classes for sentiment-native typed sections.
- [ ] Update task profile labels to `Market Narrative & Sentiment` / source-focused wording.
- [ ] Add or update mapper tests so sentiment sections survive object conversion.

### Task 6: Frontend UI and compatibility

- [ ] Update task card labels: `Market Narrative & Sentiment` / `市场叙事与情绪`.
- [ ] Replace the report component with sentiment-specific blocks:
  - Sentiment header
  - Narrative snapshot
  - Bull vs bear narrative
  - Source divergence
  - Noise warnings
- [ ] Keep legacy render branch for old `driverThesis` / `driverMap` reports.
- [ ] Update frontend tests to assert new copy and no old business-driver title in the active task card.

### Task 7: Verification and cleanup

- [ ] Run `uv run pytest -q` in `backend/research-service`.
- [ ] Run targeted frontend tests for app rendering and timeline copy.
- [ ] Run Java backend tests if Java contracts changed.
- [ ] Run `git diff --check`.
- [ ] Commit with message: `feat: replace business driver with sentiment analyst`.

## Validation Matrix

| Case | Expected |
|---|---|
| AAPL with all sources available | GROUNDED report with sentiment band, score, confidence, source divergence |
| Ticker with no Reddit posts | Report still succeeds and says Reddit sample is insufficient |
| StockTwits unavailable | Report still succeeds and lowers confidence |
| Chinese language | Main prose is Chinese, proper nouns remain English |
| Old cached business-driver report | UI renders legacy sections without blank page |
| No filings/RAG available | Sentiment agent still runs because it does not depend on SEC/RAG |

## Non-Goals

- Do not add paid news APIs.
- Do not add Twitter/X integration in v1.
- Do not rename the public task id in v1.
- Do not make this agent issue final buy/sell recommendations.
