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

## Phase 5: Anti-Hallucination (Citation Verification)
- [x] **校验逻辑**: 实现模糊匹配 (Fuzzy Matching) 验证引用。
- [x] **后端集成**: 每次生成报告自动校验，返回 `verificationStatus`。
- [x] **Prompt 优化**: 强化 Prompt 避免产生空引用 (2026-02-09)。

## Phase 6: 深度洞察 (Advanced Insights)
- [x] **杜邦分析法 (DuPont Analysis)**: ROE 拆解 (净利率 x 周转率 x 杠杆率)。
- [x] **智能洞察引擎 (Insight Engine)**: 
    - 自动识别会计策略变更 (营收确认、资产减值)。
    - 关键指标根因归因 (Root Cause Analysis)。
- [x] **动态因子分析 (Waterfall Charts)**: 
    - 收入/利润率驱动因素分解。
    - **Prompt 优化**: 允许使用 "+/-" 定性描述替代缺失数值 (2026-02-09)。
- [x] **NLP 主题趋势 (Topic Trends)**: 提取 MD&A 高频热词 (如 "AI", "Supply Chain") 并可视化的词云 (Word Cloud) (2026-02-14)。
- [ ] **NLP 主题趋势 (Topic Trends)**: 提取 MD&A 高频热词 (如 "AI", "Supply Chain") 并追踪趋势（暂缓）。

## Phase 7: Production Ready
- [x] **PDF 下载**: 使用 @react-pdf/renderer 生成专业级金融分析报告 PDF（高盛研报风格）(2026-02-26)。
- [x] **Key Metrics 固定**: 4 个固定指标使用 FMP 硬数据，不依赖 AI 生成 (2026-02-26)。
- [x] **Bug 修复 & 稳定性**: Groq 60s 超时保护、Validator 误报修复、日志降噪、Next.js 代理超时 120s (2026-02-27)。
- [x] **图表数据可靠性**: History 请求重试 + 触发时序修正 (2026-02-27)。
- [x] **鲁棒性改进**: SEC+RAG 优雅降级（失败时切换 FMP-only 模式）、Gemini Embedding 30s 超时保护、SEC 搜索重试 + 20s 超时 (2026-02-27)。
- [x] **Margin 折线图修复**: `useEffect`+`useState` → `useMemo` + 修复 `historyLoading` 成功路径未重置 bug (2026-02-27)。
- [ ] **Docker 部署**: Docker Compose 一键部署脚本（backend + frontend + env 编排）。

## 代码清理记录
- [x] **删除死代码**: 移除未使用的 `RagService.java`（关键词匹配降级方案），项目实际使用 `VectorRagService` + PGVector 向量语义检索 (2026-02-26)。
