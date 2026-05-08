# Spring Alpha Decisions

## 目标

本文档记录 Spring Alpha v2 的关键架构与产品决策。它用于解释为什么当前方向这样设计，避免后续 session 重复讨论已经确定的边界。

## 决策记录

### 1. 保留 Spring Boot 和 Next.js 作为产品运行栈

结论：不做全量 Python 重写。

原因：

- 当前 Java 后端已经承担 SSE、历史记录、金融数据聚合和旧分析链路。
- 当前 Next.js 前端已经承担 Dashboard、PDF、图表和用户工作台。
- 全量重写会放大迁移风险，且不会直接提升 RAG 质量。

### 2. 新增 Python Research Service

结论：Agent 与专业 RAG 放到 Python sidecar。

原因：

- LangGraph、LlamaIndex、Ragas、DeepEval 等生态在 Python 中更成熟。
- Python sidecar 可以承载实验型工程路线。
- Java 主链路可以保留稳定 fallback。

### 3. LlamaIndex 作为 RAG 主框架

结论：LlamaIndex 负责 SEC filing ingestion、parsing、nodes、metadata、retrieval、rerank、source packaging 和 eval 对接。

原因：

- 新版目标是 Evidence RAG，不只是向量检索。
- RAG 数据生命周期需要专门框架承载。
- 后续报告需要可复现的实验数据。

### 4. LangGraph 作为 Agent 编排框架

结论：Agent loop 使用确定性状态机加 bounded Evidence ReAct repair loop。

原因：

- 第一版不做开放 autonomous agent。
- LangGraph 适合状态、checkpoint、stream events 和失败分支。
- 可审计性比自由工具调用更重要。

### 5. 不暴露原始 Chain-of-Thought

结论：前端只展示 event summary、tool events、retrieval records、validation results 和 degraded reasons。

原因：

- 用户需要审计轨迹，不需要模型私有 scratchpad。
- 产品应展示可验证证据，而不是不可验证推理文本。

### 6. MVP 只保留 3 个任务卡

结论：MVP task cards 为 Latest Earnings Readout、Business Driver Deep Dive、Cash Flow and Capital Allocation。

原因：

- 第一版要小而稳。
- 这三个任务覆盖默认报告、业务驱动和现金流质量。
- Margin 与 Risk 暂时并入默认 readout，不作为独立入口。

### 7. RAG 升级按实验阶段推进

结论：RAG 不一次性加入所有高级能力，而是按 stage 做评测。

阶段：

- Stage 0: Baseline and eval dataset.
- Stage 1: Professional parsing and chunking.
- Stage 2: Hybrid search and RRF.
- Stage 3: Query rewrite and reranker.
- Stage 4: Evidence-aware generation and citation verification.
- Stage 5: Financial domain alignment.
- Stage 6: Eval dashboard and regression tests.

### 8. 指标必须来自真实实验

结论：不提前承诺固定提升比例。

原因：

- 报告需要真实 eval artifact。
- 每个阶段都应记录质量、延迟和成本。
- 主观感觉不能替代 regression data。

## 待决策事项

- Python Research Service 的运行代码何时从 contract-only 目录扩展为可启动服务。
- Agent/RAG contract 是否同步生成 Java DTO。
- MVP 是否需要最小 RAG Eval Dashboard，还是先输出 Markdown / JSON artifact。
- CI 是否在第一阶段运行 Python eval smoke tests。
