<div align="center">

# Spring Alpha: Multi-Agent Earnings Research Workbench

**A full-stack AI agent system for US earnings research.**

Spring Alpha combines **Spring Boot**, **Next.js**, **Python FastAPI Research Service**, **LangGraph/LangChain**, **LlamaIndex RAG**, and **PGVector** into a ticker-first research workbench. Enter a stock ticker, run three specialized research agents in sequence, and get auditable, structured, interactive earnings research grounded in SEC filings, company facts, and market enrichment data.

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Java](https://img.shields.io/badge/Java-21-orange.svg)](https://openjdk.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.2-6DB33F?logo=spring&logoColor=white)](https://spring.io/projects/spring-boot)
[![FastAPI](https://img.shields.io/badge/FastAPI-Research%20Service-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agent%20Runtime-1f6feb)](https://www.langchain.com/langgraph)
[![PGVector](https://img.shields.io/badge/PGVector-RAG-4169E1?logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)

[English](./README_EN.md) | [中文](./README.md)

</div>

---

## News

- The three core research lanes are implemented: Latest Earnings Readout, Business Driver Deep Dive, and Cash Flow & Capital Allocation.
- The agent runtime has been upgraded to a LangChain/LangGraph-style tool-calling graph. Legacy deterministic report fallback is no longer the production path.
- RAG has been narrowed into a controllable tool: SEC filing evidence and SEC/Yahoo metric facts are assembled into an EvidencePack before final LLM synthesis.
- The frontend is now a ticker-first workbench: the default view is a market candlestick chart, and users select reports from the left-side agent panel.
- The `Messages & Tools` sidebar renders the agent timeline with reasoning/tool events, model name, token usage, tool input, and latency.
- The RAG UI only shows live telemetry from the current run. Offline benchmark scores are not presented as real-time ticker quality.
- Latest real full-stack E2E sweep: `30 passed (57.7m)` across 30 large-cap tickers.

> Spring Alpha is a research and engineering project. It is not financial, investment, or trading advice. Outputs depend on provider behavior, data availability, filing quality, and retrieval quality.

## Spring Alpha Framework

Spring Alpha borrows the role-based decomposition of real research teams, but it does not run debates and it does not trade. A complex earnings research request is decomposed into three specialized agents. Each agent has its own question, tool set, evidence context, and typed report schema.

<p align="center">
  <img src="assets/readme/spring-alpha-framework.svg" width="100%" alt="Spring Alpha Framework">
</p>

### Agent Team

<p align="center">
  <img src="assets/readme/spring-alpha-agent-team.svg" width="100%" alt="Spring Alpha Agent Team">
</p>

#### 1. Latest Earnings Readout

Answers: “Was the latest quarter good or bad?” It focuses on company profile, earnings verdict, core KPIs, what changed, and what to watch next.

Main outputs:

- Company Profile
- Earnings Verdict
- KPI Strip
- What Changed
- Watch Next

#### 2. Business Driver Deep Dive

Answers: “What is driving the business, and are those drivers durable?” It separates evidence into product, segment, geography, demand, pricing, customer, and strategy lenses.

Main outputs:

- Thesis
- Driver Map
- Impact Table
- Signals
- Watchlist

#### 3. Cash Flow & Capital Allocation

Answers: “Are earnings backed by cash, and is capital allocation healthy?” It focuses on operating cash flow, capex, buybacks, dividends, debt, liquidity, and red flags.

Main outputs:

- Cash Quality
- Cash Flow Bridge
- Capital Allocation Scorecard
- Allocation Discipline
- Red Flags

## Evidence and RAG Design

Spring Alpha does not treat RAG as a heavy black box. RAG is a tool the agents can call to turn SEC filing text into a bounded EvidencePack.

<p align="center">
  <img src="assets/readme/spring-alpha-rag-flow.svg" width="100%" alt="Spring Alpha EvidencePack RAG Flow">
</p>

The evidence flow above shows how SEC filings are cleaned, parsed into sections, converted into LlamaIndex nodes, retrieved through PGVector, merged with SEC/Yahoo metric facts, packed into an EvidencePack, and sent to the LLM for typed final synthesis.

The frontend RAG panel only shows live telemetry that can be proven from the current run:

- Evidence Retrieved
- Evidence Used
- Metric Facts
- Sections Covered
- Retrieval Latency
- Empty Retrieval
- Evidence Pack Size

Offline metrics such as Recall@5, Context Precision, and Section Accuracy belong to regression suites. They are not shown as real-time quality scores for the current ticker.

## Product Experience

The user enters a ticker and clicks Analyze. Spring Alpha then:

1. Loads the market candlestick chart as the default view.
2. Runs the three agents in sequence.
3. Shows each agent's completion state in the left panel.
4. Shows the agent timeline in `Messages & Tools`.
5. Lets the user click any agent report to inspect task-specific research.
6. Shows current-run RAG telemetry in Developer diagnostics.

<p align="center">
  <img src="assets/readme/spring-alpha-product-workbench.svg" width="100%" alt="Spring Alpha Product Workbench">
</p>

## Installation and Local Development

### Prerequisites

- Java 21+
- Node.js 20+
- Maven or `backend/mvnw`
- Docker Desktop or OrbStack
- `uv` for the Python research service

### Clone

```bash
git clone https://github.com/your-org/spring-alpha.git
cd spring-alpha
```

### Environment

Copy the example file and fill in your own keys:

```bash
cp .env.example .env
```

Common variables:

```bash
SILICONFLOW_API_KEY=sk-...
SILICONFLOW_MODEL=Pro/moonshotai/Kimi-K2.6
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
RAG_EMBEDDING_PROVIDER=deterministic
RAG_VECTOR_TABLE_NAME=rag_chunks
```

For local manual testing, the UI also supports BYOK. Paste the provider key in the browser; it is stored in localStorage and forwarded with analysis requests.

### Start the backend stack

Recommended local backend path:

```bash
/usr/bin/env bash scripts/start-backend-stack.sh
```

This starts:

- PGVector on `127.0.0.1:5433`
- Python Research Service on `127.0.0.1:8090`
- Spring Boot backend on `127.0.0.1:8082`

### Start the frontend

```bash
cd frontend
npm install
BACKEND_URL=http://127.0.0.1:8082 npm run dev -- --hostname 127.0.0.1 --port 3001
```

Open:

```text
http://127.0.0.1:3001/app
```

### Docker Compose

```bash
cp .env.example .env
docker compose up -d --build
```

The compose profile starts PGVector, Research Service, Spring Boot backend, and Next.js frontend. In compose mode the backend service uses port `8081` inside the Docker network; local script mode uses `8082` to avoid conflicts.

## Provider Support

The runtime uses an OpenAI-compatible LLM gateway. Current UI providers:

| Provider | Default model path | Notes |
| --- | --- | --- |
| SiliconFlow | `Pro/moonshotai/Kimi-K2.6` | Primary live E2E provider |
| OpenAI | `gpt-4o-mini` by env default | OpenAI-compatible path |
| Gemini | `gemini-2.5-pro` by env default | Via OpenAI-compatible endpoint |

For SiliconFlow, the project has been tuned around:

- `Pro/moonshotai/Kimi-K2.6`
- `deepseek-ai/DeepSeek-V4-Flash`

Kimi K2.6 is currently preferred for full agent E2E quality and stability.

## Project Structure

```text
spring-alpha/
  backend/                         Spring Boot API, SEC/Yahoo boundary, SSE contract
  frontend/                        Next.js research workbench
  src/research-service/            FastAPI + LangGraph + LlamaIndex RAG sidecar
  scripts/                         local stack and verification scripts
  docs/                            architecture notes and task contracts
  docker-compose.yml               PGVector + research service + backend + frontend
```

Key files:

```text
frontend/src/components/app/earnings-analyst-app.tsx
frontend/src/components/app/rag-eval-dashboard.tsx
frontend/src/app/api/sec/analyze/[ticker]/route.ts
backend/src/main/java/com/springalpha/backend/service/FinancialAnalysisService.java
backend/src/main/java/com/springalpha/backend/service/research/ResearchAgentReportMapper.java
src/research-service/app/agents/research_workflow.py
src/research-service/app/agents/tool_calling_graph.py
src/research-service/app/rag/llamaindex_pipeline.py
```

## Testing

### Frontend unit tests

```bash
cd frontend
npm test
```

### Frontend E2E

```bash
cd frontend
npm run test:e2e
```

### Research Service tests

```bash
cd src/research-service
uv run pytest
```

### Backend tests

```bash
cd backend
./mvnw test
```

### Live provider gates

These tests call external providers and should be run manually:

```bash
PROVIDER=siliconflow SILICONFLOW_API_KEY="$SILICONFLOW_API_KEY" \
  scripts/verify-provider-tool-e2e.sh
```

For full manual frontend/backend validation, start the backend stack and frontend, then run Playwright against the local app with your provider key.

## Current Boundaries

- This is not a trading bot and does not place orders.
- The system does not expose hidden chain-of-thought; it exposes structured agent events, tool names, usage, and latency.
- Some tickers may show `LIMITED` source context when SEC companyfacts lacks specific metrics such as gross margin, capex, or buybacks.
- Provider latency and rate limits can affect live runs.
- RAG telemetry is runtime observability, not an online accuracy/recall score.

## Roadmap

- Improve metric facts coverage for sectors with non-standard statements.
- Add richer company profile and segment KPI extraction.
- Add optional earnings call transcript tools.
- Add persistent run archive and replayable agent timeline.
- Add broader benchmark suites for RAG and report quality.

## Contributing

Issues and pull requests are welcome. The most useful contributions are:

- Better SEC filing section parsing
- More robust metric normalization
- Provider compatibility improvements
- UI polish for dense financial workflows
- RAG evaluation datasets and edge cases

## Acknowledgements

Spring Alpha's multi-agent research workflow [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents).

TradingAgents demonstrates how complex financial research can be decomposed across specialized agents and presented with a clear tool-calling trace. Spring Alpha takes a different product boundary: it focuses on US earnings research, SEC filing evidence, metric facts, EvidencePack RAG, and auditable research reports. It does not include debate, portfolio management, or automated trade execution.

## License

This project is released under the MIT License.
