# 📈 Spring Alpha (Financial AI Agent)

> **Build Your Own Bloomberg Terminal with Java & AI.**
>
> 一个基于 **Spring AI** 与 **Groq (OpenAI 兼容)** 的美股财报智能分析 Agent。专为开发者设计的“白盒”金融分析工具，支持 BYOK (Bring Your Own Key) 模式。

![License](https://img.shields.io/badge/license-MIT-blue.svg) ![Spring Boot](https://img.shields.io/badge/Spring%20Boot-3.3-green) ![Next.js](https://img.shields.io/badge/Next.js-14-black) ![Build Status](https://img.shields.io/badge/build-passing-brightgreen)

## 📖 简介 (Introduction)

**Spring Alpha** 解决了散户投资者面临的核心痛点：**SEC 财报 (10-K/10-Q) 晦涩难懂且篇幅冗长**。

不同于传统的“聊天机器人”，Spring Alpha 是一个**全栈 AI 应用**。它利用 Java 高并发特性抓取 SEC 原始数据，通过 ETL 管道清洗噪声，并利用 LLM 进行深度推理，最后通过 **Generative UI** 技术在前端动态渲染可视化图表。

**核心价值**：让每位开发者都能拥有一个免费、私有、且强大的 AI 金融分析师。

## ✨ 核心特性 (Key Features)

### 1. 🚀 企业级 Java AI 架构 (Enterprise-Grade)
- 基于 **Spring AI** 框架构建，实现了模型无关性 (Model Agnostic)，未来可无缝切换至 GPT-4 或 Claude 3。
- 使用 **Spring WebFlux** 实现全链路异步非阻塞 IO，轻松应对高并发财报分析请求。

### 2. ⚡️ 实时流式响应 (Real-time Streaming)
- 利用 **Server-Sent Events (SSE)** 技术推送分析结果。
- 当前前端按 JSON event 渲染，后续可升级为逐段生成式 UI。

### 3. 📊 生成式 UI (Generative UI)
- AI 不仅仅会说话，还会画图。
- 基于结构化 JSON 驱动前端渲染 **Interactive Charts (Recharts)**（部分图表仍为 mock 数据，便于联调）。
- 自动生成“红绿灯”风险评估卡片，直观展示财报雷点。

### 4. 🧹 智能 ETL 管道 (Smart ETL Pipeline)
- 内置针对 SEC EDGAR 系统的专用爬虫。
- 使用 **Jsoup** 进行语义级 HTML 清洗，自动剔除免责声明等噪音，并可定位核心章节，为 RAG 提供更高质量的证据文本。

### 5. 🔐 BYOK 模式 (隐私优先)
- **Bring Your Own Key**：所有 API Key 仅在内存中流转，不落库。
- 你的数据，你的模型，你的隐私。

## 🛠️ 技术栈 (Tech Stack)

| 模块 | 技术选型 | 理由 |
| :--- | :--- | :--- |
| **Backend** | **Java 21**, Spring Boot 3.3 | 企业级标准，虚拟线程支持 |
| **AI Framework** | **Spring AI** + 手动 WebClient | 双重实现：展示框架能力 + 底层原理 |
| **Reactive** | Spring WebFlux (Reactor) | 高吞吐量流式处理 |
| **Crawler** | Jsoup | 高效 HTML 解析与清洗 |
| **Frontend** | **Next.js 14**, TypeScript | SSR 与 Server Actions 最佳实践 |
| **UI Library** | **Shadcn/ui**, Tailwind CSS | 极简、现代、专业的金融终端风格 |
| **Model** | **Groq (LLaMA 3.3 70B)**（Gemini 规划中） | 长文本分析性价比之王 |

## 🏗️ 架构亮点

本项目实现了**策略模式 + Spring AI 集成**，展示技术深度与框架能力的结合：

| 实现方案 | 技术栈 | 适用场景 | 特点 |
| :--- | :--- | :--- | :--- |
| **策略模式** | 自定义 Strategy + Spring AI ChatModel | 生产环境主力 | 可切换模型、统一输出 |
| **Spring AI** | Spring AI ChatModel | 演示与扩展 | 统一抽象、快速开发 |

### Spring AI Function Calling 示例

```java
// AI 可以自动调用工具函数获取实时数据
@Description("Get current stock price")
public Function<Request, Response> getStockPrice() {
    return request -> {
        // 调用真实 API 获取股价
        return new Response(ticker, price);
    };
}
```

## 🗺️ Roadmap (开发路线图)

### Phase 1: MVP ✅
- [x] 项目初始化 (Spring Boot + Next.js Monorepo)
- [x] 接入 Spring AI（Groq / OpenAI 兼容）
- [x] 实现 SEC 10-K HTML 基础抓取与清洗
- [x] 实现 `/api/sec/analyze` SSE 与前端对接

### Phase 2: Core Analysis ✅
- [x] **Generative UI**：后端返回 JSON，前端渲染图表
- [x] 增加杜邦分析法 Prompt 模板

### Phase 3: Deep Analysis ✅
- [x] **Multi-Model Support**：策略模式支持 Groq / OpenAI / Gemini / Mock 四种模型切换
- [x] **FMP 数据接入**：真实财务数据 (Revenue, Profit, Balance Sheet, Cash Flow)
- [x] **Vector RAG**：PGVector + Gemini Embedding 语义检索，替代关键词匹配
- [x] **Anti-Hallucination**：模糊匹配引用校验 + 双语引用系统
- [x] **Advanced Insights**：杜邦分析、智能洞察引擎、瀑布图、词云

### Phase 4: Production Ready 🚧
- [ ] **Docker Deploy**: Docker Compose 一键部署（backend + frontend）
- [ ] **PDF Export**: 生成专业级金融分析报告 PDF（高盛研报风格）
- [ ] **Earnings Call**: 接入 FMP Transcript API，LLM 情感分析财报电话会议


## 🚀 快速开始 (Quick Start)

### 前置要求
- Java 21+
- Node.js 18+
- Groq API Key（或其它 OpenAI 兼容服务）

### 后端启动
```bash
cd backend
# 配置 application.yml 中的 GROQ_API_KEY
./mvnw spring-boot:run
```

### 前端启动
```bash
cd frontend
npm install
npm run dev
```
