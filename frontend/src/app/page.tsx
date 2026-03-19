"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowUpRight,
  BadgeCheck,
  BrainCircuit,
  FileSearch,
  Github,
  Languages,
  Radar,
  Sparkles,
  SquareChartGantt,
} from "lucide-react";

type Locale = "zh" | "en";

const LANDING_LOCALE_STORAGE = "spring-alpha-landing-locale";

const featureIcons = [FileSearch, SquareChartGantt, BrainCircuit] as const;

const copy = {
  zh: {
    brandTagline: "AI 财报研究驾驶舱",
    nav: {
      features: "能力",
      showcase: "展示",
      workflow: "流程",
    },
    actions: {
      launch: "进入应用",
      preview: "看现有界面",
      github: "去 GitHub 点赞",
      contribute: "贡献代码 / 提 Issue",
    },
    localeLabel: "语言",
    hero: {
      badge: "面向美股财报研究的 AI 分析工作台",
      titlePrefix: "把",
      titleHighlight: "财报阅读",
      titleSuffix: "变成一块真正可用的研究界面",
      body:
        "Spring Alpha 把 SEC 原文、结构化财务指标、趋势图、风险因子和 AI 解读放在一个连续体验里。先看品牌页理解它能做什么，再一键进入真正的财报应用。",
      quickStats: [
        { label: "真实分析入口", value: "/app 工作区" },
        { label: "数据链路", value: "SEC + Yahoo + 财报检索增强" },
        { label: "当前策略", value: "向量检索 + 原始财报兜底" },
      ],
      flowTitle: "分析链路",
      flowBody: "从披露原文到结构化指标，再到更像研究结论的表达。",
      signalTitle: "信号快照",
      signalValue: "+15.65%",
      signalBody: "营收同比增长",
      groundedTitle: "可追溯模式",
      groundedValue: "引用 + 图表",
      groundedBody: "把数字、图表和论点放进同一条阅读链路。",
      whatYouGetLabel: "你会得到什么",
      whatYouGetTitle: "从原始披露，到能直接拿来判断的研究界面",
      whatYouGetBody:
        "它不是单独一个聊天框，也不是只有几张图的静态看板，而是把“看财报”和“形成观点”放在同一条阅读路径里。",
      productLabel: "真实产品界面",
      productTitle: "用 AAPL 实际页面展示产品完成度",
      productTag: "真实看板",
      productCards: [
        { label: "引擎", value: "SEC + Yahoo" },
        { label: "输出", value: "看板 + PDF" },
        { label: "研究模式", value: "多头 / 空头 / 风险" },
      ],
      productHighlights: [
        {
          title: "模型接入方式",
          body: "默认可直接使用免费托管模型，也支持切换到 OpenAI BYOK，自带 Key 后走官方接口。",
        },
        {
          title: "免费可用模型",
          body: "内置 ChatAnywhere 的 GPT-4o mini，以及 Groq 的 Llama 3.3，开箱即可体验。",
        },
        {
          title: "技术栈",
          body: "前端基于 Next.js，后端使用 Spring Boot，分析链路串联 SEC、Yahoo、RAG 和多策略模型层。",
        },
      ],
      imageAlt: "Spring Alpha AAPL 看板预览",
    },
    proofPoints: [
      "季度财报分析",
      "SEC / Yahoo 双源补充",
      "关键财务指标与趋势图",
      "多模型接入与 BYOK",
      "风险因子与驱动拆解",
      "PDF 报告导出",
    ],
    heroStats: [
      { label: "数据形态", value: "SEC + Yahoo + AI" },
      { label: "输出形态", value: "看板 / PDF / 引用" },
      { label: "适用场景", value: "研究、演示、内容生产" },
    ],
    flowNodes: [
      { title: "SEC 财报", detail: "10-Q / 10-K 解析" },
      { title: "结构化事实", detail: "营收 / 利润率 / 自由现金流" },
      { title: "AI 研究结论", detail: "驱动因素 / 风险 / 情景推演" },
    ],
    features: {
      cards: [
        {
          title: "财报读得更快",
          body:
            "把 SEC 财报、结构化财务指标和前端看板串成一条链，不用在 10-Q、10-K 和图表之间来回跳。",
        },
        {
          title: "先看结论，再钻细节",
          body:
            "核心分析、驱动因素、风险项、多空观点和关键图表同屏展开，适合快速形成研究框架。",
        },
        {
          title: "不是纯聊天，是可落地研究流",
          body:
            "支持引用校验、行业模式切换、指标健康雷达和 PDF 导出，更像一个分析工作台。",
        },
      ],
    },
    showcase: {
      label: "产品展示",
      title: "不是只会回答一句话，而是给你一整页研究上下文",
      body:
        "这个页面会把核心分析、关键指标、营收趋势、利润率趋势、杜邦拆解、健康雷达、风险因子和多空逻辑排在同一条阅读流里。你不需要边看财报边自己拼看板。",
      cards: [
        {
          label: "分析界面",
          title: "读财报最常用的模块一次展开",
          body:
            "执行摘要、驱动因素、风险项、引用和图表不是拆开的多个工具，而是一页内完成的分析旅程。",
        },
        {
          label: "研究纪律",
          title: "兼顾可视化和可追溯输出",
          body:
            "不是只有会说故事的 LLM，也不是只有冰冷数字。它尝试把原始披露、结构化指标和表达质量放进同一个产品里。",
        },
        {
          label: "为什么重要",
          title: "为个人研究、内容创作和演示展示做了一层更有完成度的包装",
          body:
            "你可以把它当成一个 AI 财报分析应用，也可以把它当成一套面向投资研究产品的交互原型。品牌页负责讲清楚产品定位，“进入应用”负责把人送进真正的工作区。",
        },
      ],
    },
    workflow: {
      label: "使用流程",
      title: "从一只股票，到一页像样的研究输出",
      steps: [
        {
          step: "01",
          title: "输入股票代码",
          body:
            "从 AAPL、NVDA 到银行、支付、半导体，我们先抓财报与行情补充数据。",
        },
        {
          step: "02",
          title: "生成结构化看板",
          body:
            "把营收、利润、现金流、趋势图和健康评分整理成一套可读看板。",
        },
        {
          step: "03",
          title: "给出研究视角",
          body:
            "把业务主线、增长驱动、风险暴露和多空逻辑压缩成更像分析师的表达。",
        },
      ],
    },
    footer: {
      label: "开源进展",
      title: "如果你喜欢这个方向，欢迎去 GitHub 点赞、提 Issue，或者直接贡献代码。",
      body:
        "Spring Alpha 现在不仅是一个可运行的财报分析应用，也是一套正在持续打磨的开源产品原型。你的点赞、反馈、PR 和想法，都会直接影响它下一步长成什么样。",
    },
  },
  en: {
    brandTagline: "AI earnings research cockpit",
    nav: {
      features: "Features",
      showcase: "Showcase",
      workflow: "Workflow",
    },
    actions: {
      launch: "Launch App",
      preview: "Preview UI",
      github: "Star on GitHub",
      contribute: "Contribute / Open Issue",
    },
    localeLabel: "Language",
    hero: {
      badge: "An AI workspace for U.S. earnings research",
      titlePrefix: "Turn",
      titleHighlight: "earnings reading",
      titleSuffix: "into a research interface you can actually use",
      body:
        "Spring Alpha puts SEC filings, structured financial facts, trend charts, risk factors, and AI reasoning into one continuous experience. The landing page explains the product, then `/app` takes you into the real workspace.",
      quickStats: [
        { label: "Real entry", value: "/app workspace" },
        { label: "Data path", value: "SEC + Yahoo + Filing RAG" },
        { label: "Current strategy", value: "Vector retrieval + raw filing fallback" },
      ],
      flowTitle: "Analysis flow",
      flowBody: "From raw disclosure to structured facts to analyst-style framing.",
      signalTitle: "Signal snapshot",
      signalValue: "+15.65%",
      signalBody: "Revenue YoY growth",
      groundedTitle: "Grounded mode",
      groundedValue: "Citations + charts",
      groundedBody: "Keep numbers, charts, and claims in the same reading path.",
      whatYouGetLabel: "What you get",
      whatYouGetTitle: "From raw disclosure to a research surface ready for judgment",
      whatYouGetBody:
        "This is not a lone chat box or a static dashboard with a few charts. It keeps reading the filing and forming a thesis in the same flow.",
      productLabel: "Live product frame",
      productTitle: "AAPL screen capture showing real product maturity",
      productTag: "Real dashboard",
      productCards: [
        { label: "Engine", value: "SEC + Yahoo" },
        { label: "Output", value: "Dashboard + PDF" },
        { label: "Research mode", value: "Bull / Bear / Risks" },
      ],
      productHighlights: [
        {
          title: "Model access",
          body: "Use the built-in free hosted models by default, or switch to OpenAI in BYOK mode with your own key.",
        },
        {
          title: "Free model options",
          body: "The app ships with ChatAnywhere GPT-4o mini and Groq Llama 3.3 so it works out of the box.",
        },
        {
          title: "Tech stack",
          body: "Next.js on the frontend, Spring Boot on the backend, with SEC, Yahoo, RAG, and strategy-based model routing underneath.",
        },
      ],
      imageAlt: "Spring Alpha AAPL dashboard preview",
    },
    proofPoints: [
      "Quarterly report analysis",
      "SEC + Yahoo dual-source enrichment",
      "Key metrics and trend charts",
      "Multi-model support with BYOK",
      "Risk factors and driver breakdowns",
      "PDF report export",
    ],
    heroStats: [
      { label: "Data stack", value: "SEC + Yahoo + AI" },
      { label: "Outputs", value: "Dashboard / PDF / Citations" },
      { label: "Use cases", value: "Research, demos, content creation" },
    ],
    flowNodes: [
      { title: "SEC Filing", detail: "10-Q / 10-K parsing" },
      { title: "Structured Facts", detail: "Revenue / Margin / FCF" },
      { title: "AI Thesis", detail: "Drivers / Risks / Scenarios" },
    ],
    features: {
      cards: [
        {
          title: "Read filings faster",
          body:
            "Connect SEC filings, structured financial metrics, and the dashboard in one path instead of bouncing between filings and charts.",
        },
        {
          title: "See the thesis before the details",
          body:
            "Core analysis, drivers, risks, bull and bear cases, and supporting visuals stay on one screen so you can form a view quickly.",
        },
        {
          title: "More than chat, closer to a workflow",
          body:
            "Citations, verification, mode switching, health radar, and PDF export make this feel like a research workstation instead of a chat demo.",
        },
      ],
    },
    showcase: {
      label: "Showcase",
      title: "Not a one-line answer, but a full page of research context",
      body:
        "The product lines up the executive summary, key metrics, revenue trends, margin trends, DuPont breakdown, health radar, risks, and bull/bear framing in one reading flow.",
      cards: [
        {
          label: "Analysis surface",
          title: "The modules you use most while reading filings open together",
          body:
            "Executive summary, drivers, risks, citations, and charts are not split into separate tools. They are part of one continuous analysis journey.",
        },
        {
          label: "Research discipline",
          title: "Visual storytelling with grounded output",
          body:
            "This is not only an eloquent LLM and not only a cold metrics page. It tries to keep disclosure, structured facts, and communication quality in the same product.",
        },
        {
          label: "Why this matters",
          title: "Packaged for personal research, content creation, and demos",
          body:
            "You can treat it as an AI earnings research app or as a stronger interaction prototype for an investing product. The landing page sets the frame and `Launch App` sends users into the real workspace.",
        },
      ],
    },
    workflow: {
      label: "Workflow",
      title: "From one ticker to a credible research output",
      steps: [
        {
          step: "01",
          title: "Enter a ticker",
          body:
            "From AAPL and NVDA to banks, payments, and semis, we first fetch filings and market context.",
        },
        {
          step: "02",
          title: "Generate a structured dashboard",
          body:
            "Revenue, profit, cash flow, trend charts, and health signals get organized into a readable research surface.",
        },
        {
          step: "03",
          title: "Frame the investment view",
          body:
            "Compress the business story, growth drivers, risk exposure, and bull/bear logic into analyst-style output.",
        },
      ],
    },
    footer: {
      label: "Open source momentum",
      title: "If you like this direction, star the repo, open an issue, or contribute.",
      body:
        "Spring Alpha is not only a runnable earnings analysis app. It is also an open-source product prototype that is still being shaped in public.",
    },
  },
} satisfies Record<Locale, unknown>;

function getInitialLocale(): Locale {
  if (typeof window === "undefined") {
    return "zh";
  }

  const savedLocale = window.localStorage.getItem(LANDING_LOCALE_STORAGE);
  if (savedLocale === "zh" || savedLocale === "en") {
    return savedLocale;
  }

  return navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en";
}

export default function LandingPage() {
  const [locale, setLocale] = useState<Locale>(() => getInitialLocale());

  useEffect(() => {
    window.localStorage.setItem(LANDING_LOCALE_STORAGE, locale);
  }, [locale]);

  const t = copy[locale];

  return (
    <main className="min-h-screen overflow-hidden bg-[#07111f] text-white">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-[-10%] top-[-8rem] h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(circle,_rgba(30,199,164,0.28),_transparent_65%)] blur-3xl" />
        <div className="absolute right-[-8%] top-[10rem] h-[30rem] w-[30rem] rounded-full bg-[radial-gradient(circle,_rgba(71,132,255,0.20),_transparent_70%)] blur-3xl" />
        <div className="absolute inset-x-0 top-0 h-[32rem] bg-[linear-gradient(180deg,rgba(14,30,54,0.92),rgba(7,17,31,0.55),transparent)]" />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(140,169,212,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(140,169,212,0.08)_1px,transparent_1px)] bg-[size:72px_72px] [mask-image:radial-gradient(circle_at_center,black,transparent_85%)]" />
      </div>

      <div className="relative mx-auto flex w-full max-w-7xl flex-col px-6 pb-16 pt-6 sm:px-8 lg:px-10">
        <header className="sticky top-4 z-20 mb-8">
          <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 rounded-[1.75rem] border border-white/10 bg-slate-950/55 px-5 py-3 shadow-[0_10px_40px_rgba(0,0,0,0.25)] backdrop-blur-xl">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-300 ring-1 ring-emerald-300/20">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-semibold tracking-[0.24em] text-emerald-300 uppercase">
                  Spring Alpha
                </p>
                <p className="text-xs text-slate-400">{t.brandTagline}</p>
              </div>
            </div>

            <nav className="hidden items-center gap-6 text-sm text-slate-300 md:flex">
              <a href="#features" className="transition hover:text-white">
                {t.nav.features}
              </a>
              <a href="#showcase" className="transition hover:text-white">
                {t.nav.showcase}
              </a>
              <a href="#workflow" className="transition hover:text-white">
                {t.nav.workflow}
              </a>
            </nav>

            <div className="flex flex-wrap items-center justify-end gap-2">
              <div className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] p-1">
                <span className="px-2 text-xs text-slate-400">
                  <Languages className="h-3.5 w-3.5" />
                </span>
                {(["zh", "en"] as const).map((option) => (
                  <button
                    key={option}
                    type="button"
                    onClick={() => setLocale(option)}
                    aria-pressed={locale === option}
                    aria-label={`${t.localeLabel}: ${option.toUpperCase()}`}
                    className={`rounded-full px-3 py-1.5 text-xs font-medium transition ${
                      locale === option
                        ? "bg-emerald-300/20 text-emerald-100"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {option.toUpperCase()}
                  </button>
                ))}
              </div>
              <a
                href="https://github.com/CadeYu/spring-alpha"
                target="_blank"
                rel="noreferrer"
                aria-label="Open GitHub repository"
                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-white/12 bg-white/5 text-slate-300 transition hover:border-emerald-300/30 hover:bg-white/10 hover:text-white"
              >
                <Github className="h-4 w-4" />
              </a>
              <Link
                href="/app"
                className="inline-flex items-center gap-2 rounded-full border border-emerald-300/30 bg-emerald-400/15 px-4 py-2 text-sm font-medium text-emerald-200 transition hover:bg-emerald-400/25"
              >
                {t.actions.launch}
                <ArrowUpRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </header>

        <section className="relative grid items-start gap-8 pb-16 pt-2 lg:grid-cols-[minmax(0,1.02fr)_minmax(420px,0.98fr)] lg:gap-12">
          <div className="max-w-3xl pt-2">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-200">
              <BadgeCheck className="h-4 w-4" />
              {t.hero.badge}
            </div>

            <div className="mb-8 grid gap-3 sm:grid-cols-3">
              {t.hero.quickStats.map((item) => (
                <div
                  key={item.label}
                  className="rounded-[1.3rem] border border-white/8 bg-white/[0.04] px-4 py-4"
                >
                  <p className="text-[11px] uppercase tracking-[0.18em] text-slate-500">
                    {item.label}
                  </p>
                  <p className="mt-2 text-sm font-semibold text-white">{item.value}</p>
                </div>
              ))}
            </div>

            <h1 className="max-w-4xl text-5xl font-semibold leading-[0.94] tracking-[-0.05em] text-white sm:text-6xl lg:text-[4.5rem]">
              {t.hero.titlePrefix}{" "}
              <span className="bg-[linear-gradient(135deg,#d8fff5,#7cebd4_35%,#8eb9ff_70%,#ffffff)] bg-clip-text text-transparent">
                {t.hero.titleHighlight}
              </span>{" "}
              {t.hero.titleSuffix}
            </h1>

            <p className="mt-7 max-w-2xl text-lg leading-8 text-slate-300 sm:text-xl">
              {t.hero.body}
            </p>

            <div className="mt-9 flex flex-col gap-4 sm:flex-row">
              <Link
                href="/app"
                className="inline-flex items-center justify-center gap-2 rounded-full bg-[linear-gradient(135deg,#34d399,#58e7c8,#76a9ff)] px-6 py-3 text-sm font-semibold text-slate-950 shadow-[0_18px_45px_rgba(42,192,160,0.35)] transition hover:scale-[1.01]"
              >
                {t.actions.launch}
                <ArrowUpRight className="h-4 w-4" />
              </Link>
              <a
                href="#showcase"
                className="inline-flex items-center justify-center gap-2 rounded-full border border-white/12 bg-white/5 px-6 py-3 text-sm font-medium text-slate-200 transition hover:bg-white/10"
              >
                {t.actions.preview}
                <Radar className="h-4 w-4" />
              </a>
            </div>

            <div className="mt-8 rounded-[1.8rem] border border-white/8 bg-[linear-gradient(180deg,rgba(11,20,32,0.92),rgba(9,15,26,0.88))] p-5">
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-emerald-400/12 text-emerald-300 ring-1 ring-emerald-300/15">
                  <Sparkles className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-xs uppercase tracking-[0.22em] text-emerald-300/80">
                    {t.hero.flowTitle}
                  </p>
                  <p className="mt-1 text-base leading-7 text-slate-300">
                    {t.hero.flowBody}
                  </p>
                </div>
              </div>

              <div className="relative mt-6 hidden xl:block">
                <div className="grid gap-5 xl:grid-cols-3">
                  {t.flowNodes.map((node, index) => (
                    <div
                      key={node.title}
                      className="relative rounded-[1.45rem] border border-white/8 bg-white/[0.04] px-5 py-5"
                    >
                      <div className="mb-4 flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-full border border-emerald-300/20 bg-emerald-300/10 text-sm font-semibold text-emerald-200">
                          0{index + 1}
                        </div>
                        <p className="text-sm font-semibold tracking-[0.18em] text-emerald-200/90">
                          {node.title}
                        </p>
                      </div>
                      <p className="text-lg leading-9 text-slate-200">{node.detail}</p>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:hidden">
                <div className="rounded-[1.2rem] border border-emerald-300/15 bg-white/[0.04] px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">
                    {t.hero.signalTitle}
                  </p>
                  <p className="mt-3 text-3xl font-semibold text-emerald-300">
                    {t.hero.signalValue}
                  </p>
                  <p className="mt-1 text-sm text-slate-300">{t.hero.signalBody}</p>
                </div>
                <div className="rounded-[1.2rem] border border-sky-300/15 bg-white/[0.04] px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">
                    {t.hero.groundedTitle}
                  </p>
                  <p className="mt-3 text-base font-semibold text-white">
                    {t.hero.groundedValue}
                  </p>
                  <p className="mt-2 text-xs leading-6 text-slate-300">
                    {t.hero.groundedBody}
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-8 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-[1.6rem] border border-white/8 bg-[linear-gradient(180deg,rgba(14,24,39,0.96),rgba(10,16,28,0.92))] p-5">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  {t.hero.whatYouGetLabel}
                </p>
                <p className="mt-3 text-xl font-semibold text-white">
                  {t.hero.whatYouGetTitle}
                </p>
                <p className="mt-4 text-sm leading-7 text-slate-300">
                  {t.hero.whatYouGetBody}
                </p>
              </div>
              <div className="grid gap-3">
                {t.heroStats.map((item) => (
                  <div
                    key={item.label}
                    className="rounded-[1.3rem] border border-white/8 bg-white/[0.045] px-4 py-4"
                  >
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      {item.label}
                    </p>
                    <p className="mt-2 text-base font-semibold text-white">
                      {item.value}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          </div>

          <div className="relative lg:pt-16">
            <div className="absolute -inset-6 rounded-[2rem] bg-[radial-gradient(circle_at_top,rgba(52,211,153,0.20),transparent_55%),radial-gradient(circle_at_bottom_right,rgba(101,153,255,0.18),transparent_45%)] blur-2xl" />
            <div className="relative overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(18,31,49,0.96),rgba(10,18,30,0.92))] p-5 shadow-[0_24px_90px_rgba(0,0,0,0.42)]">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/8 pb-4">
                <div className="max-w-[24rem]">
                  <p className="text-xs uppercase tracking-[0.24em] text-emerald-300/80">
                    {t.hero.productLabel}
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-white">
                    {t.hero.productTitle}
                  </p>
                </div>
                <div className="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-xs text-emerald-100">
                  {t.hero.productTag}
                </div>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                {t.hero.productCards.map((item) => (
                  <div
                    key={item.label}
                    className="rounded-2xl border border-white/8 bg-[#09111c] p-4"
                  >
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                      {item.label}
                    </p>
                    <p className="mt-2 text-lg font-semibold text-white">{item.value}</p>
                  </div>
                ))}
              </div>

              <div className="mt-5 grid gap-4 xl:grid-cols-[0.46fr_0.54fr]">
                <div className="grid gap-3">
                  {t.hero.productHighlights.map((item) => (
                    <div
                      key={item.title}
                      className="rounded-[1.3rem] border border-white/8 bg-white/[0.04] p-4"
                    >
                      <div className="flex items-center gap-3">
                        <span className="h-2.5 w-2.5 rounded-full bg-emerald-300 shadow-[0_0_16px_rgba(110,231,183,0.8)]" />
                        <p className="text-sm font-semibold text-white">{item.title}</p>
                      </div>
                      <p className="mt-3 text-sm leading-7 text-slate-300">{item.body}</p>
                    </div>
                  ))}
                </div>

                <div className="overflow-hidden rounded-[1.4rem] border border-white/10 bg-[#040b14] p-3">
                  <div className="relative h-[34rem] overflow-hidden rounded-[1rem] border border-white/6 bg-[#06101b] sm:h-[42rem] xl:h-[50rem]">
                    <Image
                      src="/showcase/aapl-dashboard.png"
                      alt={t.hero.imageAlt}
                      fill
                      priority
                      sizes="(min-width: 1280px) 32vw, (min-width: 1024px) 40vw, 100vw"
                      className="object-cover object-[78%_top]"
                    />
                    <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-[linear-gradient(180deg,transparent,rgba(4,11,20,0.9))]" />
                  </div>
                </div>
              </div>

            </div>
          </div>
        </section>

        <section
          id="features"
          className="grid gap-5 border-y border-white/8 py-16 md:grid-cols-3"
        >
          {t.features.cards.map(({ title, body }, index) => {
            const Icon = featureIcons[index];
            return (
              <article
                key={title}
                className="rounded-[1.8rem] border border-white/8 bg-white/[0.045] p-6 backdrop-blur-sm"
              >
                <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-400/12 text-emerald-300 ring-1 ring-emerald-300/15">
                  <Icon className="h-5 w-5" />
                </div>
                <h2 className="mt-5 text-2xl font-semibold text-white">{title}</h2>
                <p className="mt-4 text-base leading-7 text-slate-300">{body}</p>
              </article>
            );
          })}
        </section>

        <section
          id="showcase"
          className="grid gap-8 py-16 lg:grid-cols-[0.9fr_1.1fr]"
        >
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-emerald-300/75">
              {t.showcase.label}
            </p>
            <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-white">
              {t.showcase.title}
            </h2>
            <p className="mt-6 max-w-xl text-lg leading-8 text-slate-300">
              {t.showcase.body}
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            {t.showcase.cards.map((card, index) => (
              <div
                key={card.title}
                className={`rounded-[1.6rem] border border-white/8 bg-[linear-gradient(180deg,rgba(13,22,34,0.98),rgba(10,16,26,0.92))] p-5 ${
                  index === 2 ? "md:col-span-2" : ""
                }`}
              >
                <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                  {card.label}
                </p>
                <p className="mt-3 text-xl font-semibold text-white">{card.title}</p>
                <p className="mt-4 text-sm leading-7 text-slate-300">{card.body}</p>
              </div>
            ))}
          </div>
        </section>

        <section
          id="workflow"
          className="rounded-[2rem] border border-white/8 bg-white/[0.035] p-6 sm:p-8"
        >
          <div className="max-w-2xl">
            <p className="text-sm uppercase tracking-[0.28em] text-emerald-300/75">
              {t.workflow.label}
            </p>
            <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-white">
              {t.workflow.title}
            </h2>
          </div>

          <div className="mt-10 grid gap-4 lg:grid-cols-3">
            {t.workflow.steps.map((item) => (
              <article
                key={item.step}
                className="rounded-[1.6rem] border border-white/8 bg-[#08111d] p-6"
              >
                <p className="text-xs font-semibold tracking-[0.28em] text-emerald-300">
                  {item.step}
                </p>
                <h3 className="mt-4 text-2xl font-semibold text-white">
                  {item.title}
                </h3>
                <p className="mt-4 text-sm leading-7 text-slate-300">
                  {item.body}
                </p>
              </article>
            ))}
          </div>
        </section>

        <section className="py-16">
          <div className="overflow-hidden rounded-[2.4rem] border border-emerald-300/15 bg-[linear-gradient(135deg,rgba(13,28,45,0.96),rgba(10,18,28,0.94))] px-6 py-10 sm:px-10">
            <div className="grid gap-8 lg:grid-cols-[1fr_auto] lg:items-center">
              <div>
                <p className="text-sm uppercase tracking-[0.28em] text-emerald-300/80">
                  {t.footer.label}
                </p>
                <h2 className="mt-4 max-w-3xl text-4xl font-semibold tracking-[-0.04em] text-white">
                  {t.footer.title}
                </h2>
                <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-300">
                  {t.footer.body}
                </p>
              </div>

              <div className="flex flex-col items-stretch gap-3 sm:flex-row lg:flex-col">
                <a
                  href="https://github.com/CadeYu/spring-alpha"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center gap-2 rounded-full bg-[linear-gradient(135deg,#34d399,#58e7c8,#76a9ff)] px-6 py-3 text-sm font-semibold text-slate-950 shadow-[0_18px_45px_rgba(42,192,160,0.35)] transition hover:scale-[1.01]"
                >
                  {t.actions.github}
                  <Github className="h-4 w-4" />
                </a>
                <a
                  href="https://github.com/CadeYu/spring-alpha/issues"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center gap-2 rounded-full border border-white/12 bg-white/5 px-6 py-3 text-sm font-medium text-slate-200 transition hover:bg-white/10"
                >
                  {t.actions.contribute}
                  <ArrowUpRight className="h-4 w-4" />
                </a>
                <Link
                  href="/app"
                  className="inline-flex items-center justify-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-6 py-3 text-sm font-medium text-emerald-100 transition hover:bg-emerald-400/16"
                >
                  {t.actions.launch}
                  <ArrowUpRight className="h-4 w-4" />
                </Link>
              </div>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
