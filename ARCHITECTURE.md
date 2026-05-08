# Spring Alpha Architecture

## 目标

本文档描述新版 Spring Alpha 的目录结构、依赖方向和技术栈边界。当前阶段只定义架构约束，不实现业务逻辑。

新版 Spring Alpha 的核心形态是：

- Next.js 负责产品界面与可视化。
- Spring Boot 负责主 API、SSE、历史记录和旧链路回退。
- Python Research Service 负责 Agent 与 LlamaIndex RAG。
- PostgreSQL / PGVector 作为统一持久化与向量存储。

## 目录结构

当前已有目录：

```text
spring-alpha/
  AGENTS.md
  ARCHITECTURE.md
  VERIFY.md
  docs/
    spec.md
    decisions.md
    ui-guidelines.md
  planning/
    FEATURES.json
    TASKS.md
    PROGRESS.md
  src/
  tests/
  scripts/
    verify.sh
    dev.sh
  .github/workflows/
    ci.yml
  backend/
    src/main/java/com/springalpha/backend/
    src/main/resources/
    pom.xml
  frontend/
    src/
    e2e/
    package.json
```

规划中的 Python sidecar 目录：

```text
spring-alpha/
  src/research-service/
    app/
      api/
      agents/
      rag/
      evals/
      contracts/
      persistence/
      observability/
    tests/
    pyproject.toml
    uv.lock
```

规划中的职责边界：

```text
frontend/src/
  User workflow, task cards, dashboard, evidence trail, eval dashboard.

backend/src/main/java/com/springalpha/backend/
  API gateway, SSE relay, existing financial data services, fallback path.

src/research-service/app/agents/
  LangGraph state machines and bounded agent workflows.

src/research-service/app/rag/
  LlamaIndex ingestion, parsing, retrieval, rerank, source packaging.

src/research-service/app/evals/
  RAG datasets, metrics, experiment runners, report artifacts.

src/research-service/app/contracts/
  Typed request, response, event, and report schemas shared with Java.

src/research-service/app/persistence/
  SQLAlchemy models, repositories, and migration boundaries.
```

## 依赖方向

依赖方向必须保持单向，避免跨层循环依赖。

```text
Browser
  -> Next.js frontend
  -> Spring Boot backend
  -> Python research-service
  -> PostgreSQL / PGVector
```

允许的调用关系：

- Frontend 可以调用 Spring Boot API 和 Next.js route handlers。
- Spring Boot 可以调用 Python Research Service。
- Python Research Service 可以调用 SEC、Spring Boot 暴露的内部 API、PostgreSQL / PGVector 和模型提供商。
- Frontend 不直接调用 Python Research Service。
- Python Research Service 不依赖 Frontend。
- RAG eval runner 可以读取数据库和实验 fixtures，但不能改变产品 API contract。

禁止的调用关系：

- Frontend 直接访问数据库。
- Frontend 直接访问 Python Agent API。
- Python Research Service 反向调用 Frontend。
- RAG 层直接写 UI-specific data shape。
- Agent 层绕过 RAG contract 直接拼接 citation 状态。

## 技术栈

### Product Runtime

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Frontend | Next.js, React, TypeScript, Tailwind, Recharts | Task cards, dashboard, evidence trail, eval dashboard |
| Backend | Java 21, Spring Boot, WebFlux, JPA, Spring AI | Main API, SSE relay, history, current analysis path, fallback |
| Database | PostgreSQL, PGVector | Financial data, vectors, run records, eval records |

### Research Runtime

| Layer | Technology | Responsibility |
| --- | --- | --- |
| API | FastAPI, Uvicorn, Pydantic v2 | Typed Agent/RAG API for Spring Boot |
| Agent | LangGraph | Bounded ReAct, state graph, checkpoint, stream events |
| RAG | LlamaIndex | SEC ingestion, parsing, nodes, retrieval, rerank, source packaging |
| HTTP | httpx | Calls to Java, SEC, and external providers |
| Persistence | SQLAlchemy 2, Alembic | Python-side run, event, and eval storage |
| Packaging | uv | Reproducible Python dependency management |

### RAG Lab

| Layer | Technology | Responsibility |
| --- | --- | --- |
| Retrieval eval | LlamaIndex eval | Retrieval-level experiments |
| Report metrics | Ragas | Context precision, context recall, faithfulness, answer relevance |
| Regression | pytest, pytest-asyncio, optional DeepEval | Local and CI quality gates |
| Observability | structlog, OpenTelemetry, optional Langfuse | Agent events, retrieval trace, latency, cost |

## 数据与 Contract 边界

Spring Boot 与 Python Research Service 之间只通过 typed JSON contract 通信。

主要 contract 类型：

- Task request
- Agent event
- Retrieval record
- Citation status
- Analysis report
- Eval artifact

第一版应保持当前 AnalysisReport 兼容，同时扩展 Agent trace 和 Evidence metadata。

## Agent Loop

新版 Agent 采用外层确定性状态机加内层有限 Evidence ReAct loop。LangGraph 负责执行状态、checkpoint、stream events 和失败分支；LlamaIndex 负责 evidence retrieval 和 source packaging；LLM 只在受控节点里做计划、抽取、归纳和结构化生成。

第一版不做开放式 autonomous agent，也不让模型自由选择任意工具。每个 task type 都有固定的 allowed tools、retrieval profile、retry budget 和 degraded policy。

### Loop Flow

```text
Start
  -> Resolve Task
  -> Collect Financial Facts
  -> Collect Filing Metadata
  -> Build Evidence Plan
  -> Retrieve Evidence
  -> Extract Signals
  -> Draft Report Sections
  -> Validate Claims
      -> if evidence gap: Retrieve Evidence
      -> if number mismatch: Collect Financial Facts
      -> if weak citation: Retrieve Evidence
      -> if budget exceeded: Mark Degraded
  -> Finalize Report
```

### State Model

Agent state should be explicit and serializable:

- `run_id`
- `ticker`
- `task_type`
- `company_profile`
- `financial_facts`
- `filing_metadata`
- `evidence_plan`
- `retrieval_records`
- `extracted_signals`
- `draft_sections`
- `validation_results`
- `degraded_reasons`
- `final_report`
- `agent_events`

The state is the durable boundary for debugging, replay, eval, and session handoff. Nodes can add fields or enrich existing fields, but should not mutate unrelated state.

### Evidence ReAct Policy

The ReAct loop is evidence-centered, not chat-centered.

```text
Plan evidence needs
  -> Call allowed tool
  -> Observe structured result
  -> Check coverage
  -> Repair missing evidence if needed
  -> Stop or degrade
```

Allowed repair actions are controlled enums:

- `retrieve_more`
- `rewrite_query`
- `validate_claim`
- `fallback_to_raw_filing`
- `mark_partial_support`
- `finalize`

Guardrails:

- Maximum evidence repair loops: 2 to 3.
- Maximum tool calls per task: task-specific fixed budget.
- Timeout is enforced per node and per run.
- Cost and token usage must be recorded when available.
- Raw chain-of-thought must not be persisted or shown.
- User-facing trace must use event summaries, not hidden reasoning.

### Task Profiles

| Task Type | Primary Goal | Retrieval Profile | Validation Focus |
| --- | --- | --- | --- |
| Latest Earnings Readout | Full earnings dashboard | MD&A, financial statements, earnings narrative, guidance | Numbers, citations, section coverage |
| Business Driver Deep Dive | Product, segment, demand, pricing, customer, competition, strategy analysis | MD&A, business section, segment discussion, risk notes | Claim support, source diversity, citation quality |
| Cash Flow and Capital Allocation | Cash flow quality and capital allocation review | cash flow statement, liquidity, capital resources, buybacks, debt notes | Number consistency, period alignment, claim support |

### User-Facing Trace

Frontend should display:

- Current phase.
- Data sources used.
- Evidence count.
- Citation status.
- Degraded status.
- Validation summary.

Frontend must not display:

- Raw chain-of-thought.
- Private model scratchpad.
- Provider-specific internal prompts.

## Feature Flag 原则

新版 Agent/RAG 路径必须通过 feature flag 开启。

默认要求：

- Legacy Java analysis path remains available.
- Python Agent path can be disabled without breaking the product.
- RAG experiment stages can be compared against baseline.
- Degraded results must be explicit in API responses and UI state.

## 架构原则

- Product path and experiment path stay separated.
- LlamaIndex owns RAG data lifecycle.
- LangGraph owns Agent execution lifecycle.
- Spring Boot owns product API lifecycle.
- Next.js owns user interaction lifecycle.
- Evaluation artifacts must be reproducible.
- No generated report should claim metric improvement without recorded experiment data.
