# Spring Alpha 软件设计文档（SDD）

适用于 Spring Alpha 当前实现与演进。

## 1. 背景与目标
Spring Alpha 是一个面向开发者的财报智能分析系统，目标是把结构化财务数据（FMP）与 SEC 披露文本结合，生成可解释、可追溯、具备专业框架的研究型输出。

**核心目标：**
1. **结构化生成 (Generative UI)**：输出结构化洞察（而不是自由流文本），驱动前端复杂的图表渲染。
2. **严防幻觉 (Anti-Hallucination)**：每个结论必须有真实的数据/文本证据，事实不依赖大语言模型猜测。
3. **架构现代化**：全异步流式输出，低资源消耗，高并发。

## 2. 系统边界
**输入**：
- 结构化财务数据（FMP API 提供精确数值）
- SEC 官方披露文本内容（10-K / 10-Q）

**输出**：
- 结构化分析报告（JSON via SSE）
- 高颜值分析研报 UI 面板 + **PDF 文件下载**

## 3. 架构概览

**后端 (Backend)**：
- **Spring Boot 3.3 + WebFlux**：提供底层的异步事件流 (SSE) 接口。
- **架构分层**：Controller → Service → Strategy → Data Service。
- **动态策略模式 (Strategy Pattern)**：AI 引擎接口化，支持多 Provider (Groq, OpenAI, Gemini) 动态切换。

**前端 (Frontend)**：
- **Next.js 14 + Shadcn UI**：现代响应式 UI 框架。
- 代理拦截后端 SSE 流，动态渲染为杜邦分析表、瀑布流等组件。

## 4. 核心执行引擎 (Agentic Workflow)

核心入口位于 `FinancialAnalysisService.java`，整个流程如同一个自动化的金融分析师处理研报：

1. **获取硬数据**：调用 FMP 获取精确数字（不通过大语言模型）。
2. **文本抽取与 RAG**：
   - Jsoup 清洗 SEC 原文 HTML。
   - PGVector + Embedding：语义化检索切片（例如只拿 MD&A 章节）。
3. **契约拼装**：组合为 `AnalysisContract`（合同对象）。
4. **模型分析**：依据 Controller 传入的 `model` 决定走哪个 Strategy 执行。
5. **流式聚合与校验**：在 `BaseAiStrategy` 中将打字机数据流聚合为 JSON 对象，调用 `AnalysisReportValidator` 进行字段覆盖和来源自检。

## 5. API 梳理

1. `GET /api/sec/analyze/{ticker}?lang=en|zh`（核心 SSE 接口，最长 120s 超时监控）
2. `GET /api/sec/history/{ticker}` （拉取 FMP 历史数据用于渲染折线图趋势）
3. `GET /api/sec/models`（查询引擎支持的 LLM 模型）

## 6. 前端 UI 设计精要

前端通过 `AnalysisReport` 泛型接收分析结果。不仅有文本段落，在第二期架构演进中，扩展了强大的深度洞察模块：
- **DuPont Analysis (杜邦分析)**：直观展现 ROE 拆解因子。
- **Waterfall Bridge (因素瀑布桥)**：展示 Revenue 和 Margin 是被哪些业务板块正向/负向影响的。
- **Topic Trends**：词云聚合。
- **Source Verification UI (信源验证组件)**：界面红绿灯标识每一段引文是否真实存在于原始文档中。
- **PDF Export**：集成 `@react-pdf/renderer` 将上述组件渲染至物理 PDF。

## 7. 已清查的技术债与里程碑

历史的设计方案中存在的重大卡点已得到解决：
- **[已修复]** `SSE 目前不是“分段生成”`：通过前端巧妙地监听 `data: {...}` 的增量流，虽然不能完全打字机图形，但是能做到秒级首段渲染，极大提升了加载体验。
- **[已修复]** `Docker 部署`：实现了从 DB (Postgres/PGVector) 到 Backend，再到 Frontend 全链路的 `docker-compose.yml` 容器编排。
- **[已修复]** `PDF 导出`：独立组件按钮完成生成与下载。

## 8. 未来演进建议

1. **Streaming JSON Parser 升级**：当前需等整段 JSON closed 后才能渲染，未来可接入基于 AST 的流式 JSON 解析库（如 Oboe.js 或针对 Next.js 的专门流处理），实现逐个字段生成的丝滑体验。
2. **Earnings Call 会议分析**：接入 FMP 音频 API 及文本转写，实现高管情绪追踪。
3. **企业微信/Telegram 机器人扩展**：将 `/api/sec/analyze` 的结果精简格式化推送至 IM 工具，做成个人理财订阅号。
