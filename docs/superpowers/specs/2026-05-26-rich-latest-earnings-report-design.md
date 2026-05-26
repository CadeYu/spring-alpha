# Rich Latest Earnings Report Design

**Goal:** 把 `latest_earnings_readout` 从短摘要卡升级成更像投资研究 memo 的财报报告，让单个 ticker 的 earnings 内容有足够的信息密度、证据链和可读结构。

**Architecture:** 保持现有 Spring Boot -> Python Research Service -> Next.js report UI 链路不变；第一版只扩展 latest earnings typed section contract、synthesis prompt、normalization/backfill 和前端展示层，不新增独立 agent，不引入新的外部服务。

**Tech Stack:** Python Research Service, Pydantic typed contracts, Spring Boot report mapper, Next.js/React UI, existing lexical/RAG evidence retrieval.

---

## 1. 背景

当前 `latest_earnings_readout` 能跑通真实 agent、SEC filing、RAG evidence 和 BYOK provider，但内容形态偏像证据摘要：

- `topline_verdict` 通常只有 headline 和一段短 summary。
- `financial_dashboard.metrics` 主要覆盖 revenue、gross margin、operating income。
- `key_takeaways`、`driver_snapshot`、`risk_snapshot` 没有明确的最小内容量要求。
- 前端只展示 `Earnings Verdict`、`KPI Strip`、`What Changed`、`Watch Next`，如果模型只返回 1 条 point，UI 就会显得很薄。

对比 TradingAgents 这类 multi-agent report，它们的丰富感来自多视角结构：不同 analyst 角色、bull/bear debate、risk review、final decision trail。Spring Alpha 不需要照搬交易决策系统，但需要把 earnings 报告从“几张卡片”升级为“有结构的研究 memo”。

## 2. 产品目标

第一版目标是显著提高 latest earnings 的报告厚度，同时不牺牲当前速度优化成果。

目标：

- 一个 successful latest earnings report 不应该只有一句核心 item。
- 报告要回答：这季度好不好、为什么、数字质量如何、哪些因素驱动、哪些因素拖累、下一季度该看什么。
- 每个主要观点都必须尽量绑定 evidence；没有证据时必须显式保守，而不是编造。
- 中文报告要像中文投资研究 memo，不要只把英文 key 翻译成中文。
- UI 保持工作台风格，不做营销页式长文章。

非目标：

- 不做完整 TradingAgents 交易系统。
- 不新增 bull/bear/risk 多个独立 provider 调用。
- 不改变 `business_driver_deep_dive` 和 `cash_flow_capital_allocation` 的核心 schema。
- 不引入新的 paid data provider。
- 不为了变长而允许无证据泛泛而谈。

## 3. 推荐方案

### 3.1 方案 A: 扩展 latest earnings typed schema

在现有 latest earnings task 内新增更细的 typed sections。保持一个 agent final synthesis 调用，但要求它输出更完整的 memo 结构。

优点：

- 改动最集中。
- 对速度影响最小。
- 能复用现有 RAG、metric evidence、citation sanitizer 和前端 task 分页。
- 回滚简单。

缺点：

- 丰富度仍然受单次 synthesis prompt 和 evidence pack 限制。
- 不会获得真正多 agent debate 的推理深度。

### 3.2 方案 B: 新增轻量 bull/bear reviewer pass

在 latest earnings synthesis 后追加一次低 token reviewer 调用，专门生成 bull case、bear case 和 watch next。

优点：

- 内容层次更接近 TradingAgents。
- 能减少单个 prompt 同时做所有事情的压力。

缺点：

- 增加一次 provider latency 和失败点。
- 当前目标是 60s 内体验，短期风险更高。

### 3.3 方案 C: 完整多 agent earnings desk

拆成 KPI analyst、quality analyst、driver analyst、risk analyst，再由 manager 汇总。

优点：

- 最像机构研究流程。
- 长期可扩展性最好。

缺点：

- 明显增加成本和运行时间。
- 需要更复杂的状态管理、失败降级和 UI 时间线。
- 超出本次“让 earnings report 变厚”的最小目标。

### 推荐

第一版采用方案 A。先把 latest earnings schema 和 UI 做厚，验证 10-15 个线上 ticker 的输出质量和速度。如果报告厚度仍不足，再考虑方案 B，而不是直接上完整多 agent 架构。

## 4. 新报告信息架构

新的 latest earnings 页面应按研究 memo 顺序组织。

```text
Earnings Memo
  1. Executive Verdict
  2. KPI Scorecard
  3. What Changed
  4. Quality Of Quarter
  5. Drivers And Draggers
  6. Bull / Bear Read
  7. Watch Next
  8. Evidence And Citation Health
```

### 4.1 Executive Verdict

用途：给用户一个清晰总判断，但不止一句。

要求：

- `headline`: 一句话结论。
- `summary`: 3-5 句，必须覆盖结果方向、核心数字、主要驱动、主要疑点。
- `verdict`: `positive | mixed | negative`。
- `confidence`: `high | medium | low`，由证据覆盖度决定。

### 4.2 KPI Scorecard

用途：让用户快速看到季度数字，而不是在段落里找数字。

建议指标优先级：

- `revenue`
- `revenue_growth`
- `gross_margin`
- `operating_income`
- `operating_margin`
- `net_income`
- `eps`
- `operating_cash_flow`
- `free_cash_flow`
- `capex`

第一版不强求所有指标都存在，但 successful report 至少应有 3 个 numeric metrics；如果只有 1-2 个，要在 coverage 里说明。

### 4.3 What Changed

用途：解释这季度相对上季度或去年同期发生了什么变化。

要求：

- 至少 3 条 point。
- 每条 point 应包含 `title`、`summary`、`source_ids`、`citation_status`。
- summary 不少于 2 句，避免一句话 item。

### 4.4 Quality Of Quarter

用途：把“增长是否健康”讲清楚。

建议拆成：

- `growth_quality`
- `margin_quality`
- `cash_quality`
- `one_time_items`

每个 lens 是 evidence-bound point，缺证据时允许为空，但不能编造。

### 4.5 Drivers And Draggers

用途：把正向驱动和拖累因素分开，不再混成一组短句。

字段：

- `drivers`: 2-4 条正向驱动。
- `draggers`: 1-4 条负向或压力因素。

示例 lens：

- demand
- pricing
- product mix
- segment mix
- cost structure
- operating leverage
- macro / FX / regulation

### 4.6 Bull / Bear Read

用途：用轻量 debate 增强报告厚度，但不新增 agent。

字段：

- `bull_case`: 2-3 条。
- `bear_case`: 2-3 条。
- `balanced_read`: 2-4 句，解释为什么最终 verdict 是 positive/mixed/negative。

约束：

- bull/bear 都必须来自 evidence 或 metric evidence。
- 不能写估值建议、目标价或交易指令。

### 4.7 Watch Next

用途：让报告有行动性。

要求：

- 3-5 条。
- 每条必须说明下季度要观察的 metric 或 filing clue。
- 不能只写泛泛的“关注需求变化”。

## 5. Contract 设计

第一版建议把 schema version 从 `task_sections.v1` 保持不变，避免 Java/TypeScript 大规模 discriminated union 迁移；字段使用 additive extension。前端兼容旧字段，后端 mapper 逐步补齐。

建议新增 Python contract 字段：

```text
LatestEarningsSections
  company_profile
  topline_verdict
  financial_dashboard
  key_takeaways
  driver_snapshot
  risk_snapshot
  quality_of_quarter
  drivers_and_draggers
  bull_bear_read
  watch_next
```

建议新增 typed models：

```text
QualityOfQuarter
  growth_quality: EvidenceBoundPoint | null
  margin_quality: EvidenceBoundPoint | null
  cash_quality: EvidenceBoundPoint | null
  one_time_items: EvidenceBoundPoint | null

DriversAndDraggers
  drivers: list[EvidenceBoundPoint]
  draggers: list[EvidenceBoundPoint]

BullBearRead
  bull_case: list[EvidenceBoundPoint]
  bear_case: list[EvidenceBoundPoint]
  balanced_read: EvidenceBoundPoint | null

WatchNextItem
  title: str
  metric: str | null
  why_it_matters: str
  evidence_refs: list[EvidenceRef]
  citation_status: CitationStatus
```

兼容策略：

- `key_takeaways` 和 `driver_snapshot` 保留，避免旧 UI 和测试失效。
- `watch_next` 新增后，旧 `risk_snapshot` 仍作为 fallback。
- `quality_of_quarter` 缺失时，前端不显示该 section。
- Java `AnalysisReport` 和 TypeScript `AnalysisReport` 都按 optional additive fields 映射。

## 6. Prompt 设计

需要调整 latest earnings final synthesis prompt，而不是只在 UI 里拼接。

当前 prompt 中的 `Return compact JSON` 会压缩输出。第一版改为：

- `Return evidence-dense JSON only`
- 要求每个 narrative point summary 为 2-4 句。
- 要求 successful report 至少输出：
  - 3-6 KPI metrics
  - 3-5 what changed points
  - 2-4 drivers
  - 1-3 draggers
  - 2 bull case points
  - 2 bear case points
  - 3 watch next items
- 如果 evidence 不足，可以降级数量，但必须在 coverage/missing sections 里反映。
- 中文 prompt 要明确要求中文 memo 风格，保留 `revenue`、`gross margin`、`operating cash flow` 等专有名词也可以，但句子必须自然。

同时保留硬约束：

- 只返回 JSON。
- 不允许编造 `source_ids`。
- 所有 `source_ids` 必须来自 allowed list。
- 不允许输出目标价、买卖建议或未经证据支持的预测。

## 7. Evidence 和 RAG 设计

报告变厚不能靠 hallucination，必须提高 evidence pack 的覆盖。

### 7.1 Metric evidence

latest earnings evidence query 应继续优先拉：

- revenue
- gross margin
- operating income
- net income
- eps
- operating cash flow
- capex
- free cash flow

### 7.2 Filing sections

RAG lexical retrieval 应优先保留：

- MD&A
- Results of Operations
- Segment Information
- Liquidity and Capital Resources
- Cash Flows
- Risk Factors
- Outlook / Guidance when present

### 7.3 Evidence budget

不建议无限扩大 context。第一版目标是更好地组织已有证据：

- source refs 从当前上限 8 提升到 10-12，只对 latest earnings 生效。
- final evidence context 仍保持压缩，避免重新把速度拉回 100s+。
- 对每个 section 至少给模型 1-2 条相关 evidence anchor。

## 8. UI 设计

前端仍采用工作台式密集布局，不做长营销文章。

建议 UI 顺序：

```text
+------------------------------------------------+
| Earnings Memo                                  |
| Executive Verdict + confidence                 |
+------------------------------------------------+
| KPI Scorecard                                  |
| revenue | gross margin | op income | cash flow |
+------------------------------------------------+
| What Changed                                   |
| 3-5 evidence-bound points                      |
+------------------------------------------------+
| Quality Of Quarter                             |
| growth | margin | cash | one-time items        |
+------------------------------------------------+
| Drivers And Draggers                           |
| drivers left, draggers right                   |
+------------------------------------------------+
| Bull / Bear Read                               |
| bull case | bear case | balanced read          |
+------------------------------------------------+
| Watch Next                                     |
| metric-linked watch items                      |
+------------------------------------------------+
```

UI 规则：

- 不要把所有内容塞进嵌套 card。
- 每个 section 是一个 top-level card 或 unframed band。
- point summary 使用 2-4 句时，卡片宽度要允许换行，不要截断。
- 中文 label 应自然：`财报判断`、`关键指标`、`本季变化`、`季度质量`、`驱动与拖累`、`多空视角`、`下一季观察`。
- 保留 evidence/citation UI，不把证据隐藏掉。

## 9. 质量门槛

新增输出质量 gate，避免“schema 扩了但还是一句话”。

建议规则：

- `topline_verdict.summary` 至少 120 个中文字符或 80 个英文词，除非 coverage degraded。
- `key_takeaways + driver_snapshot` 至少 3 条。
- `financial_dashboard.metrics` 至少 3 条 numeric metrics。
- `watch_next` 至少 3 条。
- 每个 visible point summary 至少 40 个中文字符或 25 个英文词。
- 如果未达标，report `coverage.status` 应为 `partial` 或 `degraded`，并把缺失项放入 `missing_sections`。

这些规则不应阻止返回报告；它们用于降级标记、测试和开发者诊断。

## 10. 测试策略

### 10.1 Python tests

更新或新增：

- latest earnings payload normalization test
- schema optional-field compatibility test
- quality gate test for too-short points
- source id sanitizer test for new sections
- fallback test when `watch_next` is missing but `risk_snapshot` exists

### 10.2 Java tests

更新 mapper tests：

- Spring Boot can deserialize new latest earnings fields.
- Old payloads without new fields still deserialize.
- API response camelCase mapping matches frontend contract.

### 10.3 Frontend tests

更新 page/component tests：

- renders `Quality Of Quarter`
- renders `Drivers And Draggers`
- renders `Bull / Bear Read`
- renders `Watch Next`
- old reports without new fields still render.
- long Chinese summaries wrap without horizontal overflow.

### 10.4 Live acceptance

线上真实 ticker 验收：

- Test set: AAPL, TSLA, AMD, JPM, V.
- 每个 ticker 跑 `latest_earnings_readout`。
- 记录总耗时、source status、metric count、point count、watch next count。
- 通过标准：
  - 4/5 ticker 在 60s 内。
  - 5/5 ticker 至少 3 个 KPI metrics 或明确 partial。
  - 5/5 ticker 不出现只有一句话的主要 section。
  - 中文模式下主要 section 文案自然，不是英文模板直译。

## 11. 风险

### 11.1 速度回退

扩 schema 会增加 output tokens。控制方式：

- 不新增 provider 调用。
- 限制每个 section 的最大 point 数。
- 保持 evidence context 压缩。
- 使用 quality gate 识别薄报告，而不是无限 retry。

### 11.2 Hallucination 增加

报告变长会增加编造风险。控制方式：

- 所有 point 都要求 citation status 和 source refs。
- sanitizer 继续剔除非法 source ids。
- missing evidence 必须降级，而不是补想象。

### 11.3 UI 变得臃肿

信息更多后可能难扫读。控制方式：

- 保持 section 顺序固定。
- KPI 数字优先视觉呈现。
- 每个 section 使用清晰标题和短摘要。
- 不做 nested cards。

### 11.4 Backward compatibility

老缓存或旧 payload 可能没有新字段。控制方式：

- 新字段全部 optional。
- 前端 fallback 到旧 `risk_snapshot` / `driver_snapshot`。
- Python normalization 对缺失字段给空数组或 null。

## 12. 分阶段实施

### Phase 1: Contract and prompt

- 扩 Python latest earnings models。
- 更新 synthesis prompt。
- 更新 normalization 和 source id sanitizer。
- 增加 Python tests。

### Phase 2: Java and frontend mapping

- 扩 Java `AnalysisReport` latest earnings typed sections。
- 扩 TypeScript `AnalysisReport` types。
- 前端渲染新增 sections。
- 增加 frontend tests。

### Phase 3: Live tuning

- 部署到 Vultr。
- 线上跑 5 个 ticker。
- 根据薄弱项调整 prompt 和 evidence budget。
- 记录速度和质量基线。

## 13. 验收标准

设计完成后的实现应满足：

- `latest_earnings_readout` 不再只靠一段 verdict 和 1 条 takeaway 撑页面。
- 报告包含 KPI、变化、质量、驱动、拖累、多空视角和下一季观察。
- 每个主要 section 都能绑定 evidence 或明确 partial/degraded。
- 旧 payload 不会把页面打崩。
- 线上 5 ticker latest earnings 测试有可复核 artifact。
- CI、Vultr deploy 和生产 smoke 都通过。

## 14. Commit Message

```text
docs: specify rich latest earnings report design
```
