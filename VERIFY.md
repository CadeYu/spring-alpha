# Spring Alpha Verification Guide

## 目标

本文档定义新版 Spring Alpha 的 lint、test、build、e2e 运行方式。当前文件只定义验证入口，不代表所有命令已经通过。

## 前置要求

```text
Java 21+
Node.js 20+
npm
Maven
Python 3.12+
uv
PostgreSQL with PGVector
```

Python Research Service 是生产分析主路径。分析相关验证应优先覆盖 Java backend 到 Python `/agent/runs` 的 typed bridge；如果 Research Service 不可用，后端应返回明确 unavailable/degraded 错误。

## One-command Scripts

本项目保留两个顶层脚本入口：

```bash
./scripts/verify.sh
```

```bash
./scripts/dev.sh
```

```bash
./scripts/e2e-local.sh
```

```bash
./scripts/verify-research-service-bridge.sh
```

`verify.sh` 负责文档结构和轻量校验。`dev.sh` 负责打印本地开发启动方式。`e2e-local.sh` 负责 E2E 前的本地编排入口，默认运行 mocked E2E，需要跨服务时使用 `services` 模式。`verify-research-service-bridge.sh` 会启动 Python Research Service，并强制运行 Java WebClient 到 `/agent/runs` 的 typed contract 测试。

## Frontend

目录：

```bash
cd frontend
```

安装依赖：

```bash
npm install
```

Lint：

```bash
npm run lint
```

Unit tests：

```bash
npm run test
```

Build：

```bash
npm run build
```

E2E：

```bash
npm run test:e2e
```

E2E 通常需要前端与后端服务已启动。

## Backend

目录：

```bash
cd backend
```

Unit tests：

```bash
mvn test
```

Package：

```bash
mvn package
```

Run backend locally：

```bash
mvn spring-boot:run
```

## Python Research Service

目录规划：

```bash
cd src/research-service
```

初始化后建议使用：

```bash
uv sync
```

Lint：

```bash
uv run ruff check .
```

Format check：

```bash
uv run ruff format --check .
```

Type check：

```bash
uv run mypy app tests
```

Unit tests：

```bash
uv run pytest
```

RAG eval smoke test：

```bash
uv run pytest tests/evals -m smoke
```

PGVector-backed RAG production readiness gate：

```bash
../../scripts/verify-pgvector-rag-eval.sh
```

该门禁会启动临时 PGVector，生成 Stage 1 hard RAG artifact，并通过 Python
eval threshold 检查 primary hybrid retrieval 的 expected section hit rate、
expected term hit rate、top-1 section correctness、empty retrieval rate、bad
section leak rate 和 source payload size。

Provider-backed mini RAG eval gate，手动/optional live gate：

```bash
GEMINI_API_KEY="$GEMINI_API_KEY" ./scripts/verify-provider-mini-rag-eval.sh
```

该门禁会启动临时 PGVector，用 Gemini embeddings 跑 10-15 个 representative hard
cases，只验证 primary hybrid retrieval，并记录 retrieval quality、elapsed
time、embedding call count 和 estimated cost。它不属于默认 CI gate，避免外部
provider 成本、限流和可用性影响基础验证。

Provider-backed sample RAG eval gate，手动 release confidence gate：

```bash
RAG_PROVIDER_EVAL_SUITE=sample \
RAG_PROVIDER_EVAL_TREND_PATH="${TMPDIR:-/tmp}/spring-alpha-rag-provider-trends.jsonl" \
GEMINI_API_KEY="$GEMINI_API_KEY" \
./scripts/verify-provider-mini-rag-eval.sh
```

sample suite 会跑 18-24 个分层 cases，覆盖 ticker、task type 和 SEC section
类型，并可通过 `RAG_PROVIDER_EVAL_TREND_PATH` 追加 JSONL trend record。它仍然是
手动 gate，不属于默认 CI。

Provider live planner smoke gate，手动/optional live gate：

```bash
PROVIDER=siliconflow SILICONFLOW_API_KEY="$SILICONFLOW_API_KEY" ./scripts/verify-provider-live-planner.sh
```

如果未显式设置 `PROVIDER`，脚本会按 `SILICONFLOW_API_KEY`、`GEMINI_API_KEY`、
`OPENAI_API_KEY` 的顺序选择第一个可用 provider。该门禁验证真实 provider
planner 可以通过统一 `complete_json` 边界进入 bounded loop，并检查 events 中
保留 `planner_context`、tool execution、typed task sections 和 provider live
planner artifact。它不属于默认 CI gate，避免 provider 成本、限流和输出波动影响基础验证。

Provider report synthesis smoke gate，手动/optional live gate：

```bash
PROVIDER=siliconflow SILICONFLOW_API_KEY="$SILICONFLOW_API_KEY" ./scripts/verify-provider-report-synthesis.sh
```

也可以显式切到 business driver synthesis：

```bash
PROVIDER_REPORT_SYNTHESIS_TASK_TYPE=business_driver_deep_dive \
PROVIDER=siliconflow SILICONFLOW_API_KEY="$SILICONFLOW_API_KEY" \
./scripts/verify-provider-report-synthesis.sh
```

该门禁使用 deterministic planner 固定取证路径，只让真实 provider 负责 final
report synthesis。它验证最终 typed task sections 标记为 LLM synthesis、包含
claim、且 claim 只能引用 Agent evidence memory 中已有的 `source_id`。当前该
较小 synthesis-only gate 覆盖 latest earnings 和 business driver；cash flow 的完整
provider 验证走下方 Provider tool E2E gate，因为它需要同时验证 SEC facts、RAG
和 metric evidence。它不属于默认 CI gate，避免 provider 成本和输出波动影响基础验证。

Provider tool E2E smoke gate，手动/optional live gate：

```bash
PROVIDER=siliconflow SILICONFLOW_API_KEY="$SILICONFLOW_API_KEY" ./scripts/verify-provider-tool-e2e.sh
```

默认 task 是 latest earnings。该门禁会在同一次 Agent run 中组合真实 SEC
companyfacts tool、request-scoped RAG filing evidence、bounded planner 和 provider
final synthesis。它验证 facts 来源为 `sec_companyfacts`、RAG 返回 source refs，
且最终 report synthesis 为 LLM。

也可以显式切换到另外两个生产任务：

```bash
PROVIDER_TOOL_E2E_TASK_TYPE=business_driver_deep_dive \
PROVIDER=siliconflow SILICONFLOW_API_KEY="$SILICONFLOW_API_KEY" \
./scripts/verify-provider-tool-e2e.sh

PROVIDER_TOOL_E2E_TASK_TYPE=cash_flow_capital_allocation \
PROVIDER=siliconflow SILICONFLOW_API_KEY="$SILICONFLOW_API_KEY" \
./scripts/verify-provider-tool-e2e.sh
```

三个 task 的 provider tool E2E 验收边界不同：

- latest earnings：SEC companyfacts + RAG filing evidence + LLM final synthesis。
- business driver：RAG filing evidence + evidence-bound business signals + LLM final synthesis。
- cash flow：SEC companyfacts + RAG filing evidence + metric evidence + LLM final synthesis。

该 gate 是目前最接近生产主链路的 live smoke；它不属于默认 CI gate，避免
SEC/provider 网络波动、provider 成本和输出波动影响基础验证。Provider key 只能通过
运行时环境注入，不能写入仓库、测试快照、日志 artifact 或文档。

Release readiness dashboard artifact：

```bash
cd src/research-service
uv run python scripts/write_release_readiness_artifact.py \
  ../../frontend/src/data/rag-eval/stage1-hard.json \
  /path/to/provider-rag-summary.json \
  /path/to/provider-live-planner.json \
  /path/to/compose-full-e2e.json \
  ../../frontend/src/data/release-readiness.json
```

该 artifact 把 RAG hard gate、provider RAG sample gate、provider live planner
gate、provider tool E2E gate 和 compose full E2E summary 统一成 frontend checklist。
它是 release readiness 快照，不会替代各 gate 本身。

## Full Local Verification

当 Python Research Service 创建后，完整验证顺序建议为：

```bash
cd backend
mvn test
mvn package

cd ../frontend
npm run lint
npm run test
npm run build

cd ../src/research-service
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
uv run pytest
```

## E2E Service Startup

Mocked E2E：

```bash
./scripts/e2e-local.sh mocked
```

跨服务 E2E 准备：

```bash
./scripts/e2e-local.sh --print
./scripts/e2e-local.sh services
```

`services` 模式会启动：

- Python Research Service on `127.0.0.1:8090`
- Spring Boot backend on `127.0.0.1:8081`
- Playwright-managed frontend on `127.0.0.1:3000`

后端会带上 `RESEARCH_SERVICE_BASE_URL` 和 `RESEARCH_SERVICE_TIMEOUT`。Research Service 是后端分析主路径，因此该模式可以验证 Java backend 到 Python Research Service 的 typed client path。

更小的 Java -> Python bridge contract 验证：

```bash
./scripts/verify-research-service-bridge.sh
```

该脚本不启动完整 Spring Boot 应用，也不依赖数据库；它只验证 Java typed client 可以通过 HTTP 调用 Python deterministic `/agent/runs`，并把返回结果映射为前端可渲染的 `AnalysisReport.taskSections`。

Production analysis path gate:

- Spring Boot analysis requests always delegate report generation to Python Research Service.
- `RESEARCH_SERVICE_BASE_URL` and `RESEARCH_SERVICE_TIMEOUT` configure the required Python service boundary.
- There is no Java report-generation fallback or analysis feature flag.
- Research Service unavailable states must return explicit unavailable/degraded responses.

Compose full E2E gate:

```bash
./scripts/verify-compose-full-e2e.sh
```

该脚本使用隔离端口启动 Spring Boot backend、Python Research Service、PGVector
和 frontend，并等待 Research `/health`、backend `/api/sec/models` 与 frontend
`/app` 可访问。它验证生产主链路的服务拓扑和 PGVector wiring，而不是 Java
analysis fallback。

`services` 模式要求本地 shell 已配置数据库密码，因为 Spring Boot 当前会在启动时初始化 JPA：

```bash
export NEON_PASSWORD="..."
```

或：

```bash
export SPRING_DATASOURCE_PASSWORD="..."
```

## Verification Policy

- Docs-only changes should at least verify file existence and Markdown readability.
- Frontend changes must run lint, unit tests, and build.
- Backend changes must run Maven tests and package.
- Agent/RAG changes must run Python unit tests and relevant eval smoke tests.
- Cross-service changes must include E2E or an explicit manual verification note.
- RAG quality claims require recorded eval artifacts, not subjective inspection.

## Dynamic Tool-Calling Agent Loop Acceptance

本节定义后续实现 `docs/dynamic-agent-loop.md` 时必须满足的验收标准。

### Contract Acceptance

- `AgentState`、`ToolSpec`、`ToolCall`、`ToolResult`、`AgentEvent` 和 `BoundedAgentResult` 必须是 typed Pydantic contracts。
- Agent state 必须可 JSON 序列化，并包含 `run_id`、`ticker`、`task_type`、`step_index`、`tool_call_count`、`evidence_memory`、`degraded_reasons` 和 `final_report`。
- Final report 必须输出 typed `taskSections`，并保持 Java `AnalysisReport` envelope 兼容。
- Event trace 不得包含 raw chain-of-thought，只允许 decision summary、phase、tool name、status、latency 和 evidence count。

### Policy Acceptance

- 三个 MVP task 必须共用同一个 Agent Runtime。
- 每个 task 必须有独立 `TaskPolicy`，包含 allowed tools、required outputs、step budget、tool budget 和 degraded policy。
- 未在 allowed tools 中的 tool call 必须被拒绝，并记录 policy violation event。
- 超过 step/tool/retry budget 时必须 finalize degraded report，不能继续循环。

### Tool Registry Acceptance

- Tool registry 必须校验 tool name、input schema、output schema 和 task policy。
- 工具业务逻辑必须在 domain service 中，tool adapter 只做参数转换、权限检查、事件记录和错误归一化。
- 工具失败必须转换为 structured degraded event，不能把裸异常作为产品 response。
- MVP tools 至少覆盖：
  - `get_company_facts`
  - `search_filing_sections`
  - `search_metric_evidence`
  - `get_business_signals`
  - `verify_citations`
  - `finalize_report`

### LLM Gateway Acceptance

- Agent Runtime 不得直接引用 SiliconFlow、OpenAI、Gemini 或任何 provider-specific SDK。
- Provider-specific 逻辑必须位于 LLM Gateway adapter。
- SiliconFlow、OpenAI、Gemini 至少共享同一个 `complete_json` 调用边界。
- 用户提供的 provider key 只能在请求链路中使用，不得写入 artifact、event trace、log 或 final report。

### E2E Acceptance

- Deterministic runner 必须能不调用 live LLM，完成三个 task 的 bounded loop。
- Cross-service path 必须能从 Spring Boot 调用 Python Research Service，并返回可被前端渲染的 typed `taskSections`。
- Frontend 必须能展示 task-specific report view 和 non-CoT agent progress events。
- Provider live E2E 必须覆盖至少一个 provider，再扩展到 SiliconFlow、OpenAI、Gemini。

### Required Verification Commands

实现 Agent loop contract 或 tool registry 时至少运行：

```bash
cd src/research-service
uv run ruff check .
uv run ruff format --check .
uv run mypy app tests
uv run pytest tests/agents tests/contracts
```

涉及 Java bridge 时增加：

```bash
cd backend
mvn -q -Dtest=ResearchServiceAgentClientTest,ResearchAgentReportMapperTest,FinancialAnalysisServiceTest test
```

涉及前端 agent progress 或 task section 渲染时增加：

```bash
cd frontend
npm run lint
npm test -- --run src/app/page.test.tsx
npm run build
```

涉及跨服务行为时增加：

```bash
./scripts/e2e-local.sh services
```

涉及真实 provider 到浏览器的 Agent E2E 时增加：

```bash
./scripts/e2e-local.sh live-agent
```

`live-agent` 会启动 Python Research Service 和 Spring Boot，并只运行 Playwright 中的 live Agent path。该模式要求运行时环境中存在 `SILICONFLOW_API_KEY`，并默认使用 `LIVE_AGENT_RESEARCH_SERVICE_TIMEOUT=PT75S`，避免真实 planner/provider 调用被普通本地短超时提前失败。Provider key 只能来自运行时环境或浏览器 localStorage，不能写入仓库、测试快照、日志 artifact 或文档。
