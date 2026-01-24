# 🚧 Spring Alpha 开发进度

## Phase 1: 基础设施搭建 (Infrastructure)
- [x] **后端初始化**: Spring Boot 3.2.5 + Java 21 环境搭建完成。
- [x] **依赖管理**: 解决 Maven Milestone 仓库与 Spring AI 0.8.1 版本兼容性问题。
- [x] **冒烟测试**: `/api/health` 接口验证服务状态正常 (Port 8081)。

## Phase 2: 核心数据管道 (SEC Data Pipeline)
- [x] **URL 发现**: `SecService.findLatest10KUrl(ticker)` - 根据股票代码找到 10-K 索引页。
- [x] **内容抓取**: `SecService.fetch10KContent(url)` - 解析索引页找到主文件 HTML。
- [x] **数据清洗**: `SecService.cleanHtml(html)` - 使用 Jsoup 剔除 HTML 标签，保留 MD&A 章节。
- [ ] **API 暴露**: `SecController` - 暴露 `/api/sec/10k/{ticker}` 端点供前端调用。

## Phase 3: AI 分析集成 (AI Integration)
- [x] **策略模式**: 实现 `AiAnalysisStrategy` 接口，支持多 AI 提供商。
- [x] **手动实现**: 使用 WebClient 手动调用 Groq/Gemini API (展示底层原理)。
- [x] **Spring AI 集成**: 基于 Spring AI ChatClient，支持 Function Calling。
- [x] **流式输出**: 实现 `Flux<String>` 接口，支持 Server-Sent Events (SSE)。

## Phase 4: 前端开发 (Next.js)
- [ ] **项目初始化**: Next.js + Shadcn UI。
- [ ] **交互开发**: 股票搜索框 + SSE 接收组件。
- [ ] **图表渲染**: 解析 JSON 并使用 Recharts 画图。
