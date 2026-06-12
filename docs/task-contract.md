# Task-Specific Report Contract

## 目标

本文档定义 Spring Alpha 中期报告 contract 设计。

当前短期方案已经让前端按任务类型渲染不同页面，但数据仍来自同一个通用 `AnalysisReport`。这会导致 Market Narrative & Sentiment 和 Cash Flow 页面只能通过关键词筛选、字段复用和前端推断来组织内容。

中期目标是把三个 MVP 任务升级为明确的 task-specific report contract：

- Latest Earnings Readout：回答最新财报发生了什么。
- Market Narrative & Sentiment：回答市场新闻、StockTwits 和 Reddit 正在如何讨论这只股票。
- Cash Flow & Capital Allocation：回答利润是否有现金支持，以及资本配置是否健康。

## 设计原则

- 保持现有 `AnalysisReport` 向后兼容。
- 新增 task-specific payload，不一次性删除旧字段。
- 前端优先渲染 typed task sections；缺失时回退到当前短期布局。
- Python research-service 是分析与报告生成的唯一生产产出方；Java 只负责 typed client 和兼容 envelope 映射。
- 每个关键 point 或 metric 都应能绑定 evidence。
- 不暴露 raw chain-of-thought。
- 不把 open-ended agent 输出直接透传到 UI。

## Contract 外壳

现有 `AnalysisReport` 保持为公共 envelope，中期新增可选字段：

```ts
export interface AnalysisReport {
  executiveSummary?: string;
  coreThesis?: CoreThesis;
  businessSignals?: BusinessSignals;
  keyMetrics: MetricInsight[];
  businessDrivers: BusinessDriver[];
  riskFactors: RiskFactor[];
  bullCase: string;
  bearCase: string;
  citations: Citation[];
  metadata: AnalysisMetadata;
  sourceContext?: SourceContext;
  currency?: string;
  companyName?: string;
  reportType?: ReportType;
  period?: string;
  filingDate?: string;
  taskSections?: TaskSpecificSections;
}
```

`taskSections` 是新增字段。旧字段仍用于：

- PDF 兼容；
- 渐进式 SSE 合并；
- task sections 缺失时的前端 fallback；
- 旧测试与已有展示逻辑。

## 公共类型

```ts
export type TaskSectionSchemaVersion = "task_sections.v1";

export type ResearchTaskType =
  | "latest_earnings_readout"
  | "business_driver_deep_dive"
  | "cash_flow_capital_allocation";

export type CitationStatus =
  | "supported"
  | "partial"
  | "missing"
  | "unverified";

export interface TaskSectionCoverage {
  status: "complete" | "partial" | "degraded";
  missingSections: string[];
  evidenceCount: number;
}

export interface BaseTaskSections {
  schemaVersion: TaskSectionSchemaVersion;
  taskType: ResearchTaskType;
  coverage: TaskSectionCoverage;
}

export interface EvidenceRef {
  section: string;
  excerpt: string;
  filingDate?: string;
  accessionNumber?: string;
  sourceId?: string;
}

export interface EvidenceBoundPoint {
  title: string;
  summary: string;
  evidenceRefs: EvidenceRef[];
  citationStatus: CitationStatus;
}

export interface EvidenceBoundMetric {
  name: string;
  value: string;
  period?: string;
  interpretation: string;
  evidenceRefs: EvidenceRef[];
  citationStatus: CitationStatus;
}
```

## Task Sections

### Latest Earnings Readout

这个任务是完整 dashboard。它回答：

- 本季度最重要的变化是什么？
- 关键财务指标是否变好？
- 业务驱动和风险有哪些？
- 哪些结论有 SEC evidence 支撑？

```ts
export interface LatestEarningsSections extends BaseTaskSections {
  taskType: "latest_earnings_readout";
  toplineVerdict: {
    headline: string;
    summary: string;
    verdict: "positive" | "mixed" | "negative";
  };
  keyTakeaways: EvidenceBoundPoint[];
  financialDashboard: {
    metrics: EvidenceBoundMetric[];
    chartFocus: string[];
  };
  driverSnapshot: EvidenceBoundPoint[];
  riskSnapshot: EvidenceBoundPoint[];
}
```

前端主视图：

```text
Latest Earnings Readout
  -> Topline Verdict
  -> Key Takeaways
  -> Financial Dashboard
  -> Driver Snapshot
  -> Risk Snapshot
  -> Evidence Trail
```

### Market Narrative & Sentiment

这个任务不是财务 dashboard，也不是 SEC/RAG 业务驱动分析。它回答：

- Yahoo Finance news 当前如何描述这只股票？
- StockTwits 散户情绪是 Bullish、Bearish、Mixed，还是样本太薄？
- Reddit 讨论是否补充或反驳新闻/StockTwits 叙事？
- 这些来源之间有什么分歧、噪音或样本限制？

```ts
export interface MarketSentimentSections extends BaseTaskSections {
  taskType: "business_driver_deep_dive";
  sentimentHeader?: {
    overallBand: "Bullish" | "Mildly Bullish" | "Neutral" | "Mixed" | "Mildly Bearish" | "Bearish";
    overallScore: number;
    confidence: "low" | "medium" | "high";
    summary: string;
  } | null;
  narrativeSnapshot?: EvidenceBoundPoint | null;
  bullBearNarrative?: {
    bullCase: string;
    bearCase: string;
    balancedRead: string;
  } | null;
  sourceDivergence?: {
    summary: string;
    newsDirection: string;
    stocktwitsDirection: string;
    redditDirection: string;
  } | null;
  noiseWarnings?: string[] | null;
  driverThesis?: DriverThesis | null;
  driverMap?: DriverMap | null;
}

export type BusinessDriverSections = MarketSentimentSections;
```

前端主视图：

```text
Market Narrative & Sentiment
  -> Sentiment Header
  -> Narrative Snapshot
  -> Bull/Bear Narrative
  -> Source Divergence
  -> Noise Warnings
  -> Source Citations
```

默认不调用 SEC/RAG business-driver 工具，不把 revenue、segment 或 margin 伪装成市场情绪证据。旧缓存中的 `driverThesis` / `driverMap` 仅作为兼容渲染分支保留。

### Cash Flow & Capital Allocation

这个任务不是业务驱动分析。它回答：

- 利润是否被经营现金流支持？
- 自由现金流质量如何？
- Capex、buyback、dividend、debt、liquidity 的资本配置纪律如何？
- 是否存在现金流、债务或回购风险？

```ts
export interface CashFlowCapitalAllocationSections extends BaseTaskSections {
  taskType: "cash_flow_capital_allocation";
  cashQualityVerdict: {
    headline: string;
    earningsBackedByCash: "yes" | "mixed" | "no" | "unclear";
    summary: string;
  };
  cashMetrics: EvidenceBoundMetric[];
  capitalAllocation: {
    capex: EvidenceBoundPoint[];
    buybacks: EvidenceBoundPoint[];
    dividends: EvidenceBoundPoint[];
    debt: EvidenceBoundPoint[];
    liquidity: EvidenceBoundPoint[];
  };
  allocationDiscipline: EvidenceBoundPoint[];
  redFlags: EvidenceBoundPoint[];
}
```

前端主视图：

```text
Cash Flow & Capital Allocation
  -> Cash Quality Verdict
  -> Cash Metrics
  -> Capital Allocation
  -> Allocation Discipline
  -> Red Flags
  -> Evidence Trail
```

默认不展示完整 Business Drivers、Advanced Insights 和通用财务 dashboard。必要收入或利润数字只能作为 cash quality context 出现。

## Union 类型

```ts
export type TaskSpecificSections =
  | LatestEarningsSections
  | BusinessDriverSections
  | CashFlowCapitalAllocationSections;
```

前端 renderer 应按 `taskSections.taskType` 做 exhaustive rendering。如果 `taskSections` 缺失，使用当前短期布局作为 fallback。

## Java Contract 映射

Java 侧建议在 `AnalysisReport` 中新增：

```java
private TaskSpecificSections taskSections;
```

中期可以先用普通 POJO 表达 union：

```text
AnalysisReport
  -> TaskSpecificSections
       schemaVersion
       taskType
       coverage
       latestEarnings
       businessDriver
       cashFlowCapitalAllocation
```

这样比 Java sealed polymorphic JSON 更容易渐进落地。长期可以迁移到 Jackson polymorphic type 或独立 response envelope。

## Python Contract 映射

Python research-service 当前有 `EvidenceAwareReport.sections: dict[str, Any]`。中期应升级为 typed sections：

```py
class EvidenceAwareReport(BaseModel):
    run_id: str
    ticker: str
    task_type: ResearchTaskType
    task_sections: TaskSpecificSections
    claims: list[EvidenceBoundClaim]
    retrieval_records: list[dict[str, Any]] = Field(default_factory=list)
```

`sections: dict[str, Any]` 可以短期保留为 deprecated 字段，但不应继续作为主 contract。

## 生成与验证规则

### 通用规则

- `schemaVersion` 必须等于 `task_sections.v1`。
- `taskType` 必须等于用户请求的任务类型。
- `coverage.evidenceCount` 应等于 task sections 内 evidence refs 的数量。
- 每个 task 至少应有一个 `EvidenceBoundPoint` 或 `EvidenceBoundMetric`。
- 如果 evidence 不足，必须将 `coverage.status` 标为 `partial` 或 `degraded`。
- 不允许 task sections 引用前端组件名。

### Latest 验证

- 必须有 `toplineVerdict`。
- 必须有至少 2 个 `keyTakeaways`。
- `financialDashboard.metrics` 不应为空。

### Market Narrative & Sentiment 验证

- 必须有 `sentimentHeader`。
- 必须有 `narrativeSnapshot`、`bullBearNarrative` 和 `sourceDivergence`。
- Yahoo Finance、StockTwits、Reddit 某个来源为空或不可用时，必须在 `noiseWarnings` 或 `sourceDivergence` 中说明。
- 不应编造 Reddit、X、StockTwits 或新闻内容。

### Cash Flow 验证

- 必须有 `cashQualityVerdict`。
- `cashMetrics` 至少包含 OCF、FCF、capex、buyback、debt 或 liquidity 中的一个主题。
- `capitalAllocation` 至少一个维度非空。
- 不应把普通 revenue growth 当成 cash quality。

## 前端迁移策略

第一阶段：

- 新增 TypeScript types。
- 新增 `TaskSectionsRenderer`。
- 如果 `report.taskSections` 存在，优先渲染 typed sections。
- 如果不存在，使用当前短期 renderer。

第二阶段：

- 删除前端关键词筛选 cash metrics 的主要路径。
- Market Narrative 页面优先消费 `sentimentHeader`、`narrativeSnapshot`、`bullBearNarrative`、`sourceDivergence`、`noiseWarnings`。
- 旧 Business Driver 页面只在旧缓存报告中消费 `driverMap`、`driverThesis`。
- Cash Flow 页面只消费 `cashQualityVerdict`、`cashMetrics`、`capitalAllocation`、`allocationDiscipline`、`redFlags`。

第三阶段：

- PDF export 使用 task sections 生成不同 report layout。
- E2E 断言 task sections 驱动的差异化内容。
- UI 展示 coverage 状态和 missing sections。

## 后端迁移策略

第一阶段：

- Java `AnalysisReport` 新增 nullable `taskSections`。
- Validator 增加 task-specific checks，但只 warning，不阻断。

第二阶段：

- Python Research Service 返回 task sections。
- Java `ResearchAgentReportMapper` 将 Python contract 映射到 `AnalysisReport.taskSections`。
- 对缺失字段执行 deterministic repair 或标记 degraded。

第三阶段：

- Validator 将核心 task-specific 缺失升级为 degraded 状态。

## E2E 验收标准

- Latest 页面使用 `taskSections.latestEarnings` 渲染完整 dashboard。
- Market Narrative 页面使用 `taskSections.businessDriver` 渲染 Sentiment Header、Narrative Snapshot、Bull/Bear Narrative、Source Divergence 和 Noise Warnings。
- Cash 页面使用 `taskSections.cashFlowCapitalAllocation` 渲染 Cash Quality、Cash Metrics、Capital Allocation 和 Red Flags。
- 三个页面在首屏、主体模块、证据组织上明显不同。
- 当 `taskSections` 缺失时，前端仍能显示 unavailable/degraded 状态或当前短期兼容页面。
- Python Research Service 不可用时，后端返回明确 503/degraded 错误，不生成 Java report。
- Python research-service 可独立通过 Pydantic validation。

## 后期演进

### Contract v2

长期可以引入独立 response envelope：

```ts
export interface ResearchReportResponse {
  runId: string;
  ticker: string;
  taskType: ResearchTaskType;
  report: TaskSpecificSections;
  legacyReport?: AnalysisReport;
  agentTrace?: AgentTrace;
  retrievalRecords?: RetrievalRecord[];
  evalSummary?: EvalSummary;
}
```

这会让产品 report、agent trace、retrieval records 和 eval artifacts 分层更清楚。

### Dynamic Tool-Calling Agent

后期 agent 不应自由输出任意 UI schema。推荐路线是：

```text
Task Profile
  -> allowed tools
  -> evidence plan
  -> tool results
  -> typed task sections
  -> claim validation
  -> final report
```

每个 task profile 拥有不同工具预算：

- Latest：financial facts、filing sections、risk snapshot、chart context。
- Business：segment/product/geography retrieval、business signals、risk notes。
- Cash：cash flow statement、liquidity/capital resources、debt notes、buyback/dividend notes。

### Evidence Product

后期前端应能展开每个 point：

```text
Claim
  -> supporting excerpts
  -> source section
  -> filing metadata
  -> retrieval query
  -> citation verification
  -> eval score
```

这会把 Spring Alpha 从“AI dashboard”推进到“可审计金融研究工作台”。
