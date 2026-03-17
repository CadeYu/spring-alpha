<div align="center">

# 📈 Spring Alpha (Financial AI Agent)

**Build Your Own Bloomberg Terminal with Java & AI.**

一个基于 **Spring AI** 与 **Next.js** 构建的企业级美股智能分析 Agent。
专为开发者设计的“白盒”金融分析工具，支持 BYOK (Bring Your Own Key) 模式。

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.3-6DB33F?logo=spring&logoColor=white)](https://spring.io/projects/spring-boot)
[![Next.js](https://img.shields.io/badge/Next.js-14-000000?logo=next.js&logoColor=white)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://reactjs.org/)
[![Docker](https://img.shields.io/badge/Docker-Supported-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)

[**English**](./README_EN.md) | [**中文**](./README.md)

🌟 **[Live Demo 立即体验](https://spring-alpha-two.vercel.app/)** 🌟 <br>
*(基于 LLaMA 3.3 70B 模型驱动)*

</div>

---

## 🎯 为什么需要 Spring Alpha？

散户投资者面临的核心痛点是：**SEC 财报 (10-K/10-Q) 晦涩难懂且篇幅冗长**，而市面上的金融终端（如 Bloomberg）昂贵且封闭。

不同于传统的“聊天机器人”，Spring Alpha 是一套**完整的全栈 AI 金融应用**。它不仅是你的个人金融分析师，更是一个展示 **Java 在 AI 时代依然能打**的绝佳开源范例。

**核心价值**：让每位开发者都能零成本部署一个私有、免费、且强大的 AI 财富研究助手。

## ✨ 核心特性 (Features)

### 🚀 企业级 AI 架构 (Production-Ready)
*   **双通道模型支持**：默认提供免费模型（Groq / ChatAnywhere），同时支持用户自带 **OpenAI API Key** 切换到官方 OpenAI 模型。
*   **WebFlux 异步流**：全链路非阻塞 IO 处理高并发请求，结合 **SSE (Server-Sent Events)** 实现打字机级别的流式渲染体验。

### 📊 生成式金融 UI (Generative UI)
*   **AI 不止会说话，还会画图**：抛弃枯燥的纯文本 Markdown 报告，自动将大模型的数据输出渲染为 **交互式分析图表**。
*   **核心分析首屏**：首屏以结构化 **Core Thesis** 呈现 verdict、headline、论据支撑与后续跟踪点，而不是单段式摘要。
*   **深度商业洞察**：内置杜邦分析法 (DuPont Analysis)、利润与营收驱动瀑布图 (Waterfall Chart) 以及财报高频词云 (Topic Word Cloud)。
*   **PDF 一键导出**：集成 `@react-pdf/renderer`，支持秒级生成「高盛研报级」精美 PDF 报告。

### 🧠 智能 RAG 与防幻觉 (Anti-Hallucination)
*   **混合数据引擎**：以 **SEC company facts** 作为财报口径事实源，以 **Yahoo enrichment** 补充行业标签、估值与季度快照，再用 **SEC filing 原文** 提供 narrative evidence。
*   **向量检索**：集成 **PGVector** 与 Embedding 流水线，优先检索 *MD&A*（管理层讨论）和 *Risk Factors*（风险因素）；首次未命中时自动降级到 raw filing，再后台补向量。
*   **引用校验与降级模式**：前端明确标识 citation 状态与 source context，避免把未经验证的 LLM 输出伪装成“确定事实”。

### 🐳 一键极速部署 (One-Click Deploy)
*   提供开箱即用的 `docker-compose.yml`，一键拉起后端 Spring Boot、前端 Next.js 及 PGVector 向量数据库。

---

## 🏗️ 系统架构图 (Architecture)

```mermaid
graph TD
    User([👨‍💻 User]) -->|Visit / or /app| NextJS[⚛️ Next.js Frontend]
    NextJS -->|SSE Proxy / REST Proxy| ApiRoutes[🔀 Next Route Handlers]
    ApiRoutes -->|Analyze / History| SpringBoot[🍃 Spring Boot Backend]

    subgraph Financial Facts Layer
        SpringBoot --> Hybrid[🧩 HybridFinancialDataService]
        Hybrid --> SecFacts[🏛️ SEC Company Facts]
        Hybrid --> Yahoo[🐍 Yahoo Python Enrichment]
    end

    subgraph Filing & RAG Layer
        SpringBoot --> SecFiling[📄 SEC Filing HTML]
        SecFiling --> Cleaner[🧹 Jsoup Cleaner]
        Cleaner --> Vector[🧠 PGVector / Embedding]
    end

    subgraph AI Orchestration Layer
        SpringBoot --> Orchestrator[🎯 FinancialAnalysisService]
        Orchestrator --> Strategy[⚙️ AI Strategy + Validation]
        Strategy --> Providers[🤖 OpenAI / ChatAnywhere / Groq]
    end

    Providers --> SpringBoot
    SpringBoot -->|SSE AnalysisReport| NextJS
```

---

## 🔄 请求流与代码入口 (Request Flow)

当用户在前端输入一个 ticker 并点击 `Analyze` 时，核心代码流程如下：

1. **前端工作台入口**
   * `/app` 页面渲染 `frontend/src/components/app/earnings-analyst-app.tsx`
   * `handleSearch()` 同时发起分析 SSE 和历史图表请求

2. **Next.js 代理层**
   * `frontend/src/app/api/sec/analyze/[ticker]/route.ts` 负责把浏览器请求桥接到后端 SSE
   * 这样前端不需要直连后端地址，也能保留 `text/event-stream` 流式能力

3. **Spring Boot 控制层**
   * `backend/src/main/java/com/springalpha/backend/controller/SecController.java`
   * `/api/sec/analyze/{ticker}` 返回 `Flux<AnalysisReport>`，把分析结果持续流给前端

4. **编排与数据融合**
   * `backend/src/main/java/com/springalpha/backend/service/FinancialAnalysisService.java`
   * 先拉季度财务事实，再抓最新 SEC filing，再命中 RAG 或降级原文，最后组装 `AnalysisContract`

5. **混合财务数据服务**
   * `backend/src/main/java/com/springalpha/backend/financial/service/HybridFinancialDataService.java`
   * 以 SEC facts 作为主事实源，再用 Yahoo enrichment 补 `profile / quote / valuation / quarterly snapshots`

6. **RAG 与引用**
   * `backend/src/main/java/com/springalpha/backend/service/rag/VectorRagService.java`
   * 有向量就做语义检索，没有向量就先降级分析并后台补 embedding

7. **策略模式驱动 LLM**
   * `backend/src/main/java/com/springalpha/backend/service/strategy/BaseAiStrategy.java`
   * 顺序执行 `SummaryAgent / InsightsAgent / FactorsAgent / DriversAgent`
   * 输出不是 markdown dump，而是面向 dashboard 的结构化 `AnalysisReport`

8. **前端渐进式展示**
   * SSE 到达后，摘要、指标、驱动因素、风险、图表逐步点亮
   * 历史数据走独立接口，不阻塞 AI 首屏



## 🧩 模块分层 (Module Map)

### 前端

*   `frontend/src/app/page.tsx`：品牌 landing page
*   `frontend/src/app/app/page.tsx`：真实分析工作台入口
*   `frontend/src/components/app/earnings-analyst-app.tsx`：搜索、模型切换、SSE 消费、整体 dashboard 编排
*   `frontend/src/components/analysis/*`：摘要、关键指标、驱动因素、风险等研究模块
*   `frontend/src/components/financial/*`：杜邦、雷达图、洞察卡片等金融可视化模块

### 后端

*   `controller`：HTTP / SSE 入口
*   `financial/service`：SEC facts、Yahoo enrichment、混合事实服务
*   `service`：编排层
*   `service/rag`：embedding、向量检索、citation context
*   `service/strategy`：多 provider LLM 策略与模板方法
*   `service/signals`、`service/profile`：商业信号和公司画像快照
*   `service/validation`：结构化输出与 citation 校验

---


## 🛠️ 技术栈 (Tech Stack)

| 模块 | 技术选型 | 备注 |
| :--- | :--- | :--- |
| **Backend** | **Java 21**, Spring Boot 3.3, WebFlux | 使用虚拟线程与响应式编程 |
| **AI Framework** | **Spring AI** | Java 生态最主流 AI 抽象框架 |
| **Vector DB** | **PostgreSQL** + PGVector | 高性能向量近似搜索 |
| **Frontend** | **Next.js 14**, React 19, TypeScript | Server Actions 与 App Router |
| **UI Components**| **Tailwind CSS**, Shadcn UI, Recharts | 极简专业的金融终端视觉设计 |

---

## 🚀 快速开始 (Quick Start)

### 选项 A：Docker Compose 一键启动（🔥 推荐）

这是最快体验 Spring Alpha 的方式。

1. **克隆代码**
    ```bash
    git clone https://github.com/your-username/spring-alpha.git
    cd spring-alpha
    ```

2. **配置环境变量**
    复制配置文件并填入您的 API Keys：
    ```bash
    cp .env.example .env
    ```
    请在 `.env` 文件中填写：
    *   `GROQ_API_KEY`: 去 [Groq Cloud](https://console.groq.com) 免费申请。

3. **一键启动**
    ```bash
    docker-compose up -d --build
    ```
    浏览器访问 `http://localhost:3000` 即可开始分析！

### 选项 B：本地源码开发

#### 前置要求
*   Java 21+
*   Node.js 18+
*   Maven

#### 启动后端
```bash
cd backend
cp .env.example .env # 填入环境变量
./mvnw spring-boot:run
```

#### 启动前端
```bash
cd frontend
npm install
npm run dev
```

启动后：

*   `http://localhost:3000/` 是产品 landing page
*   `http://localhost:3000/app` 是真实财报分析工作台

---

## 🗺️ 项目状态与 Roadmap

我们已经完成了所有的核心商业分析功能闭环。

- [x] **MVP 阶段**：跑通 Spring WebFlux + SSE + Next.js 全栈渲染链路。
- [x] **Generative UI**：基于结构化 JSON 控制前端图表（杜邦分析、瀑布桥、词云）。
- [x] **Vector RAG 注入**：PGVector 语义检索防幻觉。
- [x] **生产级部署**：Docker Compose 一键编排 & 研报 PDF 导出。
- [x] **多策略切换**：支持免费模型（Groq / ChatAnywhere）与用户自带 OpenAI Key 两种使用方式。
- [x] **Core Thesis 升级**：首屏分析升级为结构化 thesis 层，突出研究结论、证据与跟踪点。
- [wt] **Earnings Call 接入**（计划中）：分析高管 Q&A 会议音频情感分析。
- [wt] **竞争对手分析**（计划中）：横向对比多只同赛道股票指标。

### 当前边界

本次升级主要增强 **首屏输出契约与展示层**，让摘要更像研究笔记，而不是泛化 recap。
如果后续仍希望显著提升洞见质量，下一阶段应补充更丰富的上游研究输入，例如 guidance、segment KPI、资本配置信号以及管理层 commentary 结构化抽取。

## ✅ 测试与发布流程

当前仓库已经接入分层测试，覆盖：

- 后端 deterministic tests
- 前端 unit / component tests
- 前端 E2E smoke
- PDF 渲染与下载路径

### 本地一键执行

```bash
./run_checks.sh
```

### 分步执行

```bash
cd backend
mvn -Dtest=SecControllerTest,SecServiceTest,FinancialAnalysisServiceTest,BaseAiStrategyTest,AnalysisReportValidatorTest,FmpFinancialDataServiceTest test

cd ../frontend
npm run lint
npx tsc --noEmit
npm test
npm run test:e2e
```

### 测试进度与发布签收

- 详细测试计划与当前通过数见 [testing.md](./testing.md)
- 发布前真实环境 smoke 手册见 [docs/release-smoke.md](./docs/release-smoke.md)
- 发布签收模板见 [docs/release-signoff-template.md](./docs/release-signoff-template.md)
- GitHub Actions CI 已配置在 `.github/workflows/ci.yml`
- 发布前仍建议按 `testing.md` 中的真实 provider checklist 做一次手工签收

### 向量库注意事项

如果你切换过 embedding 提供商、模型，或者调整过 embedding 维度，已有的 `vector_store` 可能与当前向量维度不兼容。
一旦日志出现类似 `different vector dimensions 3072 and 768`，需要清理并重建受影响 ticker 的向量数据，否则 RAG 会自动降级且不会提供可验证引用。

---

## 🤝 贡献代码

欢迎提交 Pull Requests 做任何改进！这是一个展现 Java Web 结合现代 AI 的绝佳练兵场。
1. Fork 本仓库
2. 创建您的 Feature Branch (`git checkout -b feature/AmazingFeature`)
3. 提交您的修改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送分支 (`git push origin feature/AmazingFeature`)
5. 开启一个 Pull Request

---

## 📄 开源协议 (License)

本项目基于 [MIT License](LICENSE) 协议开源，完全免费。
*Bring Your Own Key, Own Your Data.*

<div align="center">
  如果这个项目对您有帮助，请给个 ⭐️ Star 鼓励一下作者！
</div>
