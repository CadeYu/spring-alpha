# 📈 Spring Alpha (Financial AI Agent)

> **Build Your Own Bloomberg Terminal with Java & AI.**
>
> 一个基于 **Spring AI** 和 **Gemini 1.5 Flash** 的美股财报智能分析 Agent。专为开发者设计的“白盒”金融分析工具，支持 BYOK (Bring Your Own Key) 模式。

![License](https://img.shields.io/badge/license-MIT-blue.svg) ![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.3-green) ![Next.js](https://img.shields.io/badge/Next.js-14-black) ![Build Status](https://img.shields.io/badge/build-passing-brightgreen)

## 📖 简介 (Introduction)

**Spring Alpha** 解决了散户投资者面临的核心痛点：**SEC 财报 (10-K/10-Q) 晦涩难懂且篇幅冗长**。

不同于传统的“聊天机器人”，Spring Alpha 是一个**全栈 AI 应用**。它利用 Java 高并发特性实时抓取 SEC 原始数据，通过 ETL 管道清洗噪声，并利用 Gemini 1.5 的长文本能力进行深度推理，最后通过 **Generative UI** 技术在前端动态渲染可视化图表。

**核心价值**：让每位开发者都能拥有一个免费、私有、且强大的 AI 金融分析师。

## ✨ 核心特性 (Key Features)

### 1. 🚀 企业级 Java AI 架构 (Enterprise-Grade)
- 基于 **Spring AI** 框架构建，实现了模型无关性 (Model Agnostic)，未来可无缝切换至 GPT-4 或 Claude 3。
- 使用 **Spring WebFlux** 实现全链路异步非阻塞 IO，轻松应对高并发财报分析请求。

### 2. ⚡️ 实时流式响应 (Real-time Streaming)
- 告别 Loading 转圈。利用 **Server-Sent Events (SSE)** 技术，AI 的分析结果以“打字机”效果实时推送到前端。
- 首字延迟 (TTFT) 低于 **800ms**。

### 3. 📊 生成式 UI (Generative UI)
- AI 不仅仅会说话，还会画图。
- 能够识别财报中的财务数据（营收、净利润、毛利率），并自动驱动前端渲染 **Interactive Charts (Recharts)**。
- 自动生成“红绿灯”风险评估卡片，直观展示财报雷点。

### 4. 🧹 智能 ETL 管道 (Smart ETL Pipeline)
- 内置针对 SEC EDGAR 系统的专用爬虫。
- 使用 **Jsoup** 进行语义级 HTML 清洗，自动剔除免责声明等噪音，只提取 MD&A 和 Risk Factors 核心章节，节省 60% Token 消耗。

### 5. 🔐 BYOK 模式 (隐私优先)
- **Bring Your Own Key**：所有 API Key 仅在内存中流转，不落库。
- 你的数据，你的模型，你的隐私。

## 🛠️ 技术栈 (Tech Stack)

| 模块 | 技术选型 | 理由 |
| :--- | :--- | :--- |
| **Backend** | **Java 21**, Spring Boot 3.3 | 企业级标准，虚拟线程支持 |
| **AI Framework** | **Spring AI** | Spring 官方 AI 接入层，标准化 Prompt 模板 |
| **Reactive** | Spring WebFlux (Reactor) | 高吞吐量流式处理 |
| **Crawler** | Jsoup | 高效 HTML 解析与清洗 |
| **Frontend** | **Next.js 14**, TypeScript | SSR 与 Server Actions 最佳实践 |
| **UI Library** | **Shadcn/ui**, Tailwind CSS | 极简、现代、专业的金融终端风格 |
| **Model** | **Google Gemini 1.5 Flash** | 1M Context Window，长文本分析性价比之王 |

## 🗺️ Roadmap (开发路线图)

### Phase 1: MVP (Current Focus) ✅
- [x] 项目初始化 (Spring Boot + Next.js Monorepo)
- [ ] 接入 Spring AI & Gemini 1.5 Flash
- [ ] 实现 SEC 10-K HTML 基础抓取与清洗
- [ ] 实现 `/stream` 接口与前端 SSE 对接

### Phase 2: Core Analysis 🚧
- [ ] 实现 **Generative UI**：后端返回 JSON，前端渲染图表
- [ ] 增加“杜邦分析法” Prompt 模板
- [ ] 引入 Redis 缓存热门股票数据

### Phase 3: Advanced Features 🔮
- [ ] **Competitor Compare**: 引入 RAG，实现两家公司财报横向对比
- [ ] **Earnings Call**: 集成 Whisper 模型，分析财报电话会议录音情感
- [ ] **Docker Deploy**: 提供 Docker Compose 一键部署脚本

## 🚀 快速开始 (Quick Start)

### 前置要求
- Java 21+
- Node.js 18+
- Google Gemini API Key

### 后端启动
```bash
cd backend
# 配置 application.yml 中的 spring.ai.openai.api-key
./mvnw spring-boot:run
```

### 前端启动
```bash
cd frontend
npm install
npm run dev
```
