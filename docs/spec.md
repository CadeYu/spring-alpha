# Spring Alpha 新版本规格草案

## 1. 产品目标

Spring Alpha 新版本的目标是从“财报分析 Dashboard”升级为“可审计的 AI 金融研究工作台”。

核心定位不是开放式聊天机器人，而是一个由任务卡驱动的研究系统。用户选择公司和研究任务后，系统自动完成财务事实拉取、SEC 原文检索、证据组织、Agent 编排、结构化 Dashboard 输出、引用校验与评测记录。

新版重点有三件事：

- 将现有财报分析能力升级为受控 Agent 工作流。
- 将当前 RAG 从基础 SEC 原文检索升级为可评估、可追踪、可解释、可回归测试的金融专业 RAG。
- 为后续《Spring Alpha RAG Professionalization Report》沉淀真实实验数据。

第一版保持小而稳：不做自由输入，不做开放 Agent，不做全量 Python 重写，只做任务卡式金融研究体验。

## 2. 用户画像

### 个人投资者

具备基础财务与投资知识，希望快速理解一家公司的最新财报、业务驱动因素、现金流质量和资本配置情况。不希望阅读完整 10-K / 10-Q，但需要看到关键结论背后的证据来源。

### 独立研究者或金融内容创作者

需要快速生成可复核的研究材料，关注引用质量、证据链、财务指标口径一致性，以及能否导出报告或截图用于二次整理。

### 开发者与技术面试受众

关注 Spring Boot、Next.js、Agent、RAG、PGVector、评测体系如何组成一个真实全栈 AI 产品。这个用户画像也是项目展示价值的重要部分。

### AI/RAG 工程实践者

关注 RAG 从 baseline 到专业化系统的演进过程，包括 chunking、hybrid search、reranker、citation verification、eval dashboard 和回归测试。

## 3. 10 个核心功能

### 1. 任务卡式研究入口

用户不输入自由 prompt，只选择 ticker 和预设任务卡。第一版任务集控制在 3 个：

- Latest Earnings Readout
- Business Driver Deep Dive
- Cash Flow & Capital Allocation

### 2. Latest Earnings Readout Dashboard

替代当前 Analyze 默认路径，输出完整财报解读 Dashboard，包括核心观点、关键指标、收入与利润趋势、业务摘要、风险摘要和 source context。

### 3. Business Driver Deep Dive

聚焦产品、分部、需求、价格、客户、竞争、战略动作等业务驱动因素。该任务最能体现 Agent 与专业 RAG 的价值。

### 4. Cash Flow & Capital Allocation

聚焦 operating cash flow、free cash flow、capex、buyback、dividend、debt、liquidity 等研究主题，用于判断利润质量和资本配置纪律。

### 5. 受控 Agent 执行流

使用 bounded ReAct 思路，但不暴露原始 chain-of-thought。系统对外展示可审计执行轨迹，包括任务阶段、工具调用摘要、检索状态、fallback 原因、校验结果和耗时。

### 6. LlamaIndex 专业 RAG 管线

以 LlamaIndex 负责 SEC filing ingestion、section-aware parsing、node/chunk、metadata、index、retrieval、rerank、source node packaging 和 RAG eval 对接。

### 7. Evidence-aware Generation

报告生成必须绑定 evidence。每个关键 claim 尽量关联 SEC 原文片段、section、filing date、accession number、citation status 和 source context。

### 8. RAG 实验与评测体系

按阶段记录 baseline 与升级效果，指标包括 retrieval recall@5、context precision、faithfulness、citation coverage、fallback rate、latency 和 cost。

### 9. RAG Eval Dashboard

前端新增评测视图，用于展示不同阶段、不同 ticker、不同任务类型下的 RAG 表现对比。第一版可以先展示静态或批处理结果，不要求实时实验平台。

### 10. 报告导出与研究归档

保留并增强当前 PDF / Dashboard 输出能力。每次研究生成一个可归档的 run，包括最终 report、agent events、retrieval records、citation validation 和 eval artifacts。

## 4. 明确 Out of Scope

第一版不做以下内容：

- 不做自由文本 prompt 输入。
- 不做开放式 autonomous agent。
- 不做多 Agent swarm 或 CrewAI 风格角色协作。
- 不做全量 Python 重写。
- 不把 Margin & Profitability Review、Risk Factor Review 做成第一版独立任务卡。
- 不做交易建议、买卖信号、自动下单或投资顾问式结论。
- 不引入 Elasticsearch / OpenSearch 作为第一阶段必需依赖。
- 不承诺 RAG 指标必然提升某个固定百分比。
- 不做多租户权限系统、团队协作、计费系统。
- 不做 Bloomberg / AlphaSense / FactSet 的完整替代品。
- 不暴露原始 chain-of-thought。

## 5. 技术栈建议

### 产品运行栈

| 层 | 技术 | 职责 |
| --- | --- | --- |
| Frontend | Next.js, React, Tailwind, Recharts | 任务卡、Dashboard、Evidence Trail、Eval Dashboard |
| Backend | Spring Boot, WebFlux, JPA | 主 API、SSE relay、history、旧分析链路回退 |
| Database | PostgreSQL, PGVector | 财务数据、向量数据、run records、eval records |

### Research Runtime

| 层 | 技术 | 职责 |
| --- | --- | --- |
| Python API | FastAPI, Uvicorn, Pydantic v2 | Agent/RAG sidecar，对 Java 暴露 typed API |
| Agent Runtime | LangGraph | bounded ReAct、状态机、checkpoint、stream events |
| RAG Framework | LlamaIndex | parsing、nodes、retrieval、rerank、query engine、source packaging |
| HTTP Client | httpx | 调用 Java、SEC、外部数据源 |
| Persistence | SQLAlchemy 2, Alembic | Python 侧实验表、run 表、event 表 |

### RAG Lab

| 层 | 技术 | 职责 |
| --- | --- | --- |
| Evaluation | LlamaIndex eval, Ragas | retrieval / generation 指标与报告数据 |
| Regression | pytest, pytest-asyncio, optional DeepEval | 回归测试与 CI gate |
| Observability | structlog, OpenTelemetry, optional Langfuse | event trace、latency、cost、tool calls |
| Package Management | uv | Python sidecar 与 eval harness 可复现 |

### 技术边界

LlamaIndex 是 RAG 主框架。LangGraph 是 Agent 编排框架。Spring Boot 是产品主后端。Next.js 是产品前端。Postgres / PGVector 是第一版统一持久化和向量存储。

LangChain 不作为主应用层依赖。若 LangGraph 或 Ragas 内部需要 LangChain 生态适配，可以作为局部依赖存在，但不让它接管 RAG 或模型调用边界。

## 6. 风险点

### 架构复杂度上升

新增 Python sidecar 后，系统从双服务变成多服务。需要清晰定义 Java 与 Python 之间的 API contract、timeout、fallback、部署方式和日志关联。

### RAG 指标设计难度高

金融 RAG 的“正确”不只是语义相关，还包括 fiscal period、section、metric、company event、filing type 的对齐。评测集如果设计粗糙，指标会误导优化方向。

### Citation Verification 容易过度承诺

引用命中不等于 claim 被完全支持。第一版应把 citation status 分为 supported、partial、missing、unverified，而不是简单 true / false。

### Latency 与 Cost 增加

Hybrid search、query rewrite、reranker、claim verification 都会增加耗时和成本。每个阶段必须记录 latency 和 cost，避免只追求质量指标。

### 数据源口径冲突

SEC company facts、Yahoo enrichment、SEC filing narrative 可能存在时间口径和字段定义差异。系统需要保留 source priority 和 confidence 标识。

### LlamaIndex 与现有 Spring AI RAG 并存

迁移期间会存在两套 RAG 路径。必须明确 baseline、experimental、fallback 的边界，避免同一个请求混用不同检索结果而无法评估。

### Agent 可解释性边界

用户需要看到执行轨迹，但不能暴露原始 chain-of-thought。需要展示 decision summary、tool events、retrieval records 和 validation results。

### 报告数据不可伪造

最终报告必须使用真实实验结果。文档中只能设计指标与实验方法，不能提前写固定提升比例。

## 7. 最小可用版本的验收标准

### 产品验收

- 用户可以在前端选择 ticker 和 3 个任务卡之一。
- 用户不需要输入自由文本任务。
- Latest Earnings Readout 可以替代当前 Analyze 默认体验。
- Business Driver Deep Dive 和 Cash Flow & Capital Allocation 能输出结构化 Dashboard。
- 前端能展示 report、source context、citation status 和 agent progress。

### Agent 验收

- Python sidecar 可以接收 Java 后端传入的 typed task request。
- LangGraph 能执行固定状态流，并输出结构化 agent events。
- Java 后端可以通过 SSE 将 agent progress 和最终 report 传给前端。
- Agent 失败时可以回退旧分析链路或返回明确 degraded 状态。

### RAG 验收

- Stage 0 baseline 评测集已建立，至少覆盖 3 个任务类型和一组代表性 ticker。
- Stage 1 LlamaIndex ingestion 可以解析 SEC filing，并生成带 metadata 的 nodes。
- 新旧 RAG 路径可以在相同 eval dataset 上对比。
- 每次检索记录 query、retrieved nodes、source metadata、latency 和 fallback 状态。

### Eval 验收

- 至少能生成一份 baseline eval artifact。
- 指标至少包含 retrieval recall@5、context precision、faithfulness、citation coverage、latency。
- Eval 结果可被前端或 Markdown 报告读取展示。
- CI 或本地命令可以运行最小回归测试，防止 RAG 输出质量明显退化。

### 工程验收

- 旧 Java 分析链路保持可用。
- 新 Agent/RAG 路径通过 feature flag 开启。
- 数据库 migration 可回滚或可安全重复执行。
- README 与 docs 能说明新版架构、启动方式、RAG 实验阶段和当前限制。
