# 🚧 Spring Alpha 开发进度

## Phase 1: 基础设施搭建 (Infrastructure)
- [x] **后端初始化**: Spring Boot 3.2.5 + Java 21 环境搭建完成。
- [x] **依赖管理**: 解决 Maven Milestone 仓库与 Spring AI 0.8.1 版本兼容性问题。
- [x] **冒烟测试**: `/api/health` 接口验证服务状态正常 (Port 8081)。

## Phase 2: 核心数据管道 (SEC Data Pipeline)
- [x] **URL 发现**: `SecService.findLatest10KIndexUrl(ticker)` - 根据股票代码找到 10-K 索引页。
- [x] **内容抓取**: 解析索引页找到主文件 HTML。
- [x] **数据清洗**: 使用 Jsoup 清洗 HTML，可定位 MD&A 章节并截断。
- [x] **API 暴露**: `SecController` - 暴露 `/api/sec/10k/{ticker}` 端点供前端调用。

## Phase 3: AI 分析集成 (AI Integration)
- [x] **策略模式**: 实现 `AiAnalysisStrategy` 接口，支持多 AI 提供商。
- [x] **Spring AI 集成**: 基于 Spring AI ChatModel，支持 Groq (OpenAI 兼容)。
- [x] **流式输出**: 通过 SSE 返回 JSON 报告（当前为单次 JSON 事件）。
- [x] **Gemini Strategy**: 完成 `GeminiStrategy.java` 实现，支持 Google Gemini API。
- [x] **OpenAI Strategy**: 完成 `OpenAiStrategy.java` 实现，支持 GPT-4。
- [x] **FMP 数据源**: 完成 `FmpFinancialDataService.java`，接入真实财务数据。

## Phase 4: 前端开发 (Next.js)
- [x] **项目初始化**: Next.js + Shadcn UI。
- [x] **交互开发**: 股票搜索框 + SSE 接收组件。
- [x] **图表渲染**: 解析 JSON 并使用 Recharts 画图。
- [x] **LLM 模型选择器**: 前端 UI 支持 Groq/OpenAI/Gemini/Mock 四种模型切换。
- [x] **语言切换**: 支持 EN/CN 双语分析报告。
- [x] **Null 值处理**: 修复 `formatFinancialValue` 空值导致的 TypeError (2026-02-09)。

## Phase 5: 待开发功能 (Roadmap)
- [ ] **向量 RAG 升级**: 从关键词匹配升级到 Spring AI + PGVector 向量检索。
- [ ] **引用校验 (Anti-Hallucination)**: 校验 LLM 输出的 citations 是否真实存在于 SEC 原文。
- [ ] **邮件发送报告**: 分析完成后，支持发送报告到用户邮箱存档。
- [ ] **导出 PDF**: 支持将分析报告导出为 PDF 文档。
- [ ] **杜邦分析法**: 增加 DuPont Analysis Prompt 模板。
- [ ] **财报电话会议分析**: 接入 FMP Earnings Call Transcript API，分析电话会议内容。
- [ ] **Docker 部署**: 提供 Docker Compose 一键部署脚本。



