# Dynamic Tool-Calling Agent Loop

## 目标

本文档定义 Spring Alpha Python Research Service 的 dynamic tool-calling agent loop 设计。

当前系统已经具备三任务入口、typed `taskSections`、Python Research Service API boundary 和 cross-service contract E2E。Spring Boot 只作为产品 API 和 Python Agent client；分析、RAG 和报告生成统一在 Research Service 内完成。下一步不是把某一个模型写死进 Agent，而是把 Research Service 升级为：

```text
task-specific policy
  -> bounded dynamic tool-calling loop
  -> evidence memory
  -> citation verification
  -> typed taskSections
```

模型提供商必须是可替换的。SiliconFlow、OpenAI、Gemini 都只是 provider adapter，不是 Agent runtime 的依赖。

## 非目标

- 不做开放式 autonomous agent。
- 不做多 Agent swarm。
- 不暴露 raw chain-of-thought。
- 不让模型自由调用任意工具。
- 不把 provider-specific 逻辑写进 Agent loop。
- 不把未经验证的自由文本直接透传到前端。
- 不在第一版做无限循环、长期记忆或后台任务调度。

## 总体架构

```text
Spring Boot
  -> Python Research Service
      -> Agent Runtime
          -> Task Policy
          -> Planner
          -> Tool Router
          -> Tool Registry
          -> Evidence Memory
          -> Gap Checker
          -> Report Finalizer
      -> LLM Gateway
          -> SiliconFlow Adapter
          -> OpenAI Adapter
          -> Gemini Adapter
      -> RAG Tools
          -> LlamaIndex retrieval
          -> SEC section search
          -> metric evidence search
          -> evidence-bound business signal extraction
          -> citation verification
      -> Report Synthesis
          -> latest earnings typed synthesis
          -> business driver typed synthesis
          -> cash flow typed synthesis
```

Agent Runtime 不知道具体模型。它只依赖统一的 LLM Gateway：

```python
class LlmClient(Protocol):
    async def complete_json(self, request: LlmRequest) -> LlmResponse:
        ...
```

Provider adapter 负责：

- provider 鉴权；
- endpoint 和 model 选择；
- token / timeout / retry 参数；
- JSON 输出清洗；
- provider error 归一化；
- cost / latency metadata。

Agent Runtime 负责：

- 按任务选择 policy；
- 执行 bounded loop；
- 调用 typed tools；
- 记录 trace；
- 检查 evidence gaps；
- 使用 evidence memory 生成 typed final report。

当前生产主路径中，最终报告 synthesis 已覆盖三个 MVP task：

| Task | 取证路径 | LLM synthesis 输出 |
| --- | --- | --- |
| `latest_earnings_readout` | SEC companyfacts、RAG filing sections、metric evidence | `LatestEarningsSections` |
| `business_driver_deep_dive` | RAG filing sections、evidence-bound business signals | `BusinessDriverSections` |
| `cash_flow_capital_allocation` | SEC companyfacts、RAG filing sections、metric evidence | `CashFlowCapitalAllocationSections` |

LLM synthesis 只能引用 `EvidenceMemory.source_refs` 中已有的 `source_id`。任何未知
source id 都必须触发 synthesis fallback 或 degraded reason，不能被透传到产品报告。

## Loop 范式

第一版采用 bounded ReAct，不采用开放式自由探索。

```text
Start
  -> Resolve Task Policy
  -> Initialize Agent State
  -> Seed Required Context
  -> Plan Next Step
  -> Validate Tool Call
  -> Execute Tool
  -> Observe Tool Result
  -> Update Evidence Memory
  -> Check Coverage
      -> if more evidence needed and budget remains: Plan Next Step
      -> if enough evidence: Finalize Report
      -> if budget exhausted: Finalize Degraded Report
  -> Verify Citations
  -> Return BoundedAgentResult
```

每个 run 有固定预算：

```text
max_steps: 5
max_tool_calls: task-specific
max_repair_loops: 2
per_tool_timeout: task-specific
run_timeout: request timeout budget
```

LLM 可以输出下一步 tool call 或 finalization intent，但不能绕过 policy。

## Agent State

Agent state 必须是显式、可序列化、可回放的对象。

```python
class AgentState(BaseModel):
    run_id: str
    ticker: str
    task_type: ResearchTaskType
    language: str
    provider: LlmProvider
    model: str | None
    task_policy: TaskPolicy
    step_index: int
    tool_call_count: int
    evidence_memory: EvidenceMemory
    retrieval_records: list[RetrievalRecord]
    tool_events: list[AgentEvent]
    draft_sections: dict[str, Any] | None
    coverage: CoverageState
    degraded_reasons: list[str]
    final_report: EvidenceAwareReport | None
```

状态更新规则：

- 节点只能写自己负责的字段。
- tool result 必须先进入 evidence memory，再进入 report finalizer。
- final report 必须从 state 中可追溯生成。
- 失败不抛给前端为裸异常，而是转换成 degraded event 和 degraded reason。

## Trace 与用户可见边界

Agent trace 是内部可观测性材料，不是普通用户界面本身。Agent Runtime
必须生成结构化 events，用于 eval、release gate、内部 debug 和线上支持；产品前端默认只展示压缩后的 trust summary。

分层规则：

```text
Internal trace
  -> eval assertions
  -> release readiness artifacts
  -> internal debug panel
  -> support diagnostics

User-facing trust summary
  -> source status
  -> evidence count
  -> citation coverage
  -> degraded or unavailable reason
```

普通用户默认只看到：

- source status，例如 `grounded`、`partial`、`unavailable`。
- evidence summary，例如使用了多少 filing sections、是否有 citation coverage。
- source context，例如 filing type、filing date、section 和 short snippet。
- human-readable warning，例如 Research Service unavailable、partial evidence、citation missing。

普通用户默认不看到：

- raw `AgentEvent` JSON。
- `planner_context` 原始字段。
- tool budget、step budget、fallback counter 等调试字段。
- provider private prompts、hidden scratchpad 或 raw chain-of-thought。
- provider key、长 filing 原文、完整 prompt payload 或未脱敏异常。

高级/内部 debug panel 可以展开 Agent trace，但必须满足：

- 只展示 structured decision summary，不展示 raw chain-of-thought。
- 可以展示 phase、tool name、status、latency、degraded reason、coverage summary。
- 可以展示 `planner_context` 的只读摘要，用于解释 planner 为什么 finalize、coverage stop 或 fallback。
- 不能展示 provider key、request secret、完整 filing text、完整 prompt 或 provider 原始错误体。

Release dashboard 只展示 gate-level 聚合指标，例如 provider decision count、fallback count、stop reason、tool names 和 compose status。它不展示逐步 raw event。

日志只保留运行诊断必需字段，例如 run id、provider、model、latency、status、error code 和 degraded reason。日志不得成为 Agent trace 的唯一来源，也不得写入 secrets、长文本 evidence 或 provider prompt。

## Planner 输出

Planner 输出不是自然语言答案，而是严格 JSON。

```json
{
  "decision": "call_tool",
  "summary": "Need segment and demand evidence before drafting driver thesis.",
  "tool_name": "search_filing_sections",
  "tool_input": {
    "ticker": "AAPL",
    "task_type": "business_driver_deep_dive",
    "sections": ["MD&A", "Business"],
    "query": "product segment demand pricing drivers"
  }
}
```

或：

```json
{
  "decision": "finalize",
  "summary": "Evidence coverage is sufficient for a degraded-safe final report."
}
```

`summary` 是可展示的 decision summary，不是 raw chain-of-thought。

## Tool Registry

第一版使用自研 typed registry，不直接把 LangChain / LangGraph tool abstraction 作为业务边界。

```python
class ToolSpec(BaseModel):
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: ToolHandler
    timeout_seconds: int
    requires_evidence: bool
```

Tool Registry 负责：

- 根据 tool name 找 handler；
- 校验输入 schema；
- 校验 task policy 是否允许该 tool；
- 标准化 tool result；
- 记录 latency、status、source refs 和 error code；
- 禁止未知工具执行。

业务逻辑必须在 domain service 中，tool adapter 只做边界适配。

## MVP Tools

第一版工具控制在 6 个。

| Tool | 作用 | 主要输入 | 主要输出 |
| --- | --- | --- | --- |
| `get_company_facts` | 获取 SEC companyfacts 财务事实 | `ticker`, `period`, `metrics` | SEC-backed typed facts |
| `search_filing_sections` | 检索 SEC filing section evidence | `ticker`, `sections`, `query` | source refs |
| `search_metric_evidence` | 查找指标相关证据和 period alignment | `ticker`, `metrics`, `period` | evidence-bound metric records |
| `get_business_signals` | 从已有 source refs 抽取业务信号、产品、客户、分部线索 | `signal_types` | source-bound business signals |
| `verify_citations` | 验证 claim 与 source refs 的绑定质量 | `claims`, `source_refs` | citation validation |
| `finalize_report` | 生成 typed `taskSections` 和 final report | `state`, `coverage` | `EvidenceAwareReport` |

后续 RAG 专业化优先升级这些工具，而不是重写 Agent loop。

`get_business_signals` 不允许无证据生成业务信号；当 evidence memory 中没有 source refs
时，必须返回 empty/degraded reason。每条 signal 必须携带 source id、section、snippet
和 citation status。

## Task Policy

三个 MVP task 共用一个 Agent Runtime，但使用不同 policy。

### Latest Earnings Readout

```text
allowed_tools:
  - get_company_facts
  - search_filing_sections
  - search_metric_evidence
  - verify_citations
  - finalize_report

required_outputs:
  - toplineVerdict
  - keyTakeaways
  - financialDashboard
  - driverSnapshot
  - riskSnapshot
```

重点：

- 数字一致性；
- period alignment；
- source coverage；
- dashboard 完整性。

### Business Driver Deep Dive

```text
allowed_tools:
  - search_filing_sections
  - search_metric_evidence
  - get_business_signals
  - verify_citations
  - finalize_report

required_outputs:
  - driverThesis
  - driverMap
  - positiveSignals
  - negativeSignals
  - watchlist
```

重点：

- 产品、分部、地区、需求、定价、客户和战略动作；
- 公司特有驱动，避免泛泛宏观描述；
- evidence-bound driver points；
- durability 判断。

### Cash Flow and Capital Allocation

```text
allowed_tools:
  - get_company_facts
  - search_filing_sections
  - search_metric_evidence
  - verify_citations
  - finalize_report

required_outputs:
  - cashQualityVerdict
  - cashMetrics
  - capitalAllocation
  - allocationDiscipline
  - redFlags
```

重点：

- OCF、FCF、capex、buybacks、dividends、debt、liquidity；
- earnings backed by cash；
- number consistency；
- capital allocation discipline。

## Evidence Memory

Evidence memory 是 Agent loop 的核心，不是 chat history。

```python
class EvidenceMemory(BaseModel):
    facts: dict[str, FinancialFact]
    source_refs: list[SourceRef]
    metric_evidence: list[EvidenceBoundMetric]
    business_signals: list[BusinessSignal]
    citation_results: list[CitationValidationResult]
```

规则：

- 每个 claim 必须能追溯到 source refs 或 facts。
- 没有 source refs 的 claim 必须标记为 `missing` 或 `unverified`。
- citation verifier 不能凭语义感觉通过，必须记录匹配依据。
- Evidence memory 可以被 eval runner 重放。

## Provider-Agnostic LLM Gateway

Python Research Service 接收 Java 转发的 provider 信息：

```json
{
  "provider": "siliconflow",
  "model": "Pro/moonshotai/Kimi-K2.6",
  "api_key": "user-provided",
  "base_url": "https://api.siliconflow.cn/v1"
}
```

也可以是：

```json
{
  "provider": "openai",
  "model": "gpt-5.2",
  "api_key": "user-provided",
  "base_url": "https://api.openai.com/v1"
}
```

或：

```json
{
  "provider": "gemini",
  "model": "gemini-2.5-pro",
  "api_key": "user-provided",
  "base_url": "https://generativelanguage.googleapis.com"
}
```

Agent loop 不分支判断 provider。Provider 差异只存在于 adapter。

## Event Trace

前端可以展示 event summary，但不能展示 raw chain-of-thought。

```json
{
  "event_type": "tool_call",
  "phase": "retrieve_evidence",
  "summary": "Searched MD&A and Business sections for product and demand drivers.",
  "tool_name": "search_filing_sections",
  "status": "ok",
  "latency_ms": 842,
  "evidence_count": 5
}
```

推荐事件：

- `run_started`
- `task_resolved`
- `plan_created`
- `tool_call`
- `tool_result`
- `coverage_checked`
- `citation_verified`
- `report_finalized`
- `run_degraded`
- `run_failed`

## Degraded Policy

失败必须结构化。

| 场景 | 行为 |
| --- | --- |
| Provider auth failed | 返回明确 auth error，不降级伪造报告 |
| Tool timeout | 记录 degraded reason，尝试一次可控 repair |
| Evidence insufficient | 输出 partial/degraded coverage |
| Citation mismatch | claim 标记 `partial` / `missing` |
| Unknown tool requested | 拒绝执行，记录 policy violation，重新规划一次 |
| Budget exhausted | finalize degraded report |
| Final schema invalid | 尝试一次 schema repair，失败后返回 degraded error |

## 与 LangGraph 的关系

推荐关系：

```text
Domain Agent Runtime
  -> owns state, policy, registry, contracts
LangGraph
  -> executes nodes, checkpoint, streaming, branch control
```

不要把业务规则藏进 LangGraph node callback 中。LangGraph 是 runtime adapter，不是 domain contract。

## 与 RAG 升级的关系

RAG 专业化阶段应优先升级工具：

- Stage 0：baseline eval 调用当前 tools；
- Stage 1：升级 `search_filing_sections` 的 parsing/chunking；
- Stage 2：升级 retrieval tool 为 hybrid search；
- Stage 3：在 retrieval tool 内加入 query rewrite 和 reranker；
- Stage 4：升级 `verify_citations`；
- Stage 5：升级 `search_metric_evidence` 的时间、指标、段落对齐；
- Stage 6：把 tool traces 和 eval artifacts 接入 dashboard。

Agent loop 保持稳定，RAG 能力通过 tool implementation 演进。

## 最小实现切片

推荐分 4 个 feature 落地：

1. Agent loop contract and state。
2. Tool registry and deterministic runner。
3. Task policy and coverage checker。
4. Provider-agnostic LLM gateway and live planner。

前 3 步不接 live LLM，只做 deterministic runner，保证 trace、tool policy、final report contract 稳定。

## 验收摘要

详细验收标准见 `VERIFY.md` 的 Dynamic Tool-Calling Agent Loop 章节。核心要求：

- 三个 task 都能通过同一个 bounded loop 执行。
- 每个 task 的 allowed tools 和 required outputs 被 policy enforce。
- 未知工具、超预算、schema invalid 都能被结构化处理。
- final report 必须包含 typed `taskSections`。
- trace 不包含 raw chain-of-thought。
- provider adapter 可替换，Agent Runtime 不引用具体 provider。
