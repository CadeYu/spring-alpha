"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowUpRight,
  Bot,
  ChartCandlestick,
  Github,
  Languages,
  MessageSquareText,
  TerminalSquare,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { TickerSearchInput } from "@/components/app/ticker-search-input";
import {
  tickerSearchButtonLabel,
  tickerSearchPlaceholder,
} from "@/lib/tickerSearchCopy";

type Locale = "zh" | "en";

const LANDING_LOCALE_STORAGE = "spring-alpha-landing-locale";

const copy = {
  zh: {
    brandTagline: "AI 财报研究工作台",
    nav: {
      app: "应用",
      agents: "Agent",
      github: "GitHub",
    },
    actions: {
      launch: "进入应用",
      github: "查看 GitHub",
      start: "开始研究",
      issue: "提交 Issue",
    },
    localeLabel: "语言",
    hero: {
      pill: "Spring Alpha 工作台",
      title: "更快读懂每一次财报",
      body:
        "Spring Alpha 是一个 ticker-first 的 AI 财报研究工作台。输入股票代码，依次运行三个分析 Agent，在同一块界面里查看 SEC 文件、行情图、工具时间线和实时 RAG telemetry。",
      imageAlt: "Spring Alpha live workbench preview",
      command: "用三个 Agent 分析 AAPL 财报",
    },
    strips: [
      "SEC 文件",
      "Yahoo 行情数据",
      "LangGraph Agent",
      "EvidencePack telemetry",
    ],
    terminal: {
      title: "一个 ticker，三个 Agent，一块研究界面。",
      lines: [
        "ticker=AAPL provider=siliconflow",
        "agent.latest_earnings: 收集事实并生成财报解读",
        "agent.business_driver: 检查分部和需求变化",
        "agent.cash_flow: 评估 FCF 和资本配置",
        "ui.timeline: 展示 messages, tools 和 telemetry",
      ],
    },
    sections: [
      {
        label: "01 / Agents",
        title: "三个报告按顺序运行",
        body:
          "Latest Earnings Readout、Business Driver Deep Dive、Cash Flow & Capital Allocation 是三条独立分析链路。用户可以切换报告，同时保留完整运行上下文。",
      },
      {
        label: "02 / Workspace",
        title: "K 线图是默认界面",
        body:
          "没有选择报告时，应用默认展示 all-time market chart。报告、Agent 状态和 Messages & Tools 围绕它展开，而不是把工作流降级成聊天框。",
      },
      {
        label: "03 / RAG",
        title: "展示 telemetry，不展示假分数",
        body:
          "RAG 面板只展示当前 run 能证明的指标：evidence retrieved、evidence used、metric facts、sections covered、latency、empty retrieval 和 evidence pack size。",
      },
    ],
    highlights: {
      label: "Project Highlights",
      title: "不只是好看的 demo，而是一条真实研究链路。",
      cards: [
        {
          title: "Ticker-first 入口",
          body:
            "用户不需要先选复杂任务。输入 ticker 后，系统补全公司名、展示行情，并按顺序运行三条研究 Agent。",
        },
        {
          title: "TradingAgents 风格执行",
          body:
            "Agent 使用 LangGraph / LangChain tool-calling 思路组织，把 company facts、SEC evidence、metric facts 和 synthesis 分开处理。",
        },
        {
          title: "真实 telemetry",
          body:
            "侧边栏展示当前 run 的 messages、tools、latency、evidence pack size 和 retrieval signals，而不是离线 benchmark 假分数。",
        },
        {
          title: "BYOK provider",
          body:
            "用户可以带自己的 SiliconFlow、OpenAI 或 Gemini key。前端保存本地 key，后端只在请求时接收并转发。",
        },
      ],
    },
    architecture: {
      label: "Architecture",
      title: "Spring Boot, Python agents, Next.js 和 PGVector 组合成一条可审计链路。",
      rows: [
        {
          name: "Frontend",
          value: "Next.js workbench, ticker autocomplete, market chart, agent report tabs, timeline sidebar",
        },
        {
          name: "Backend",
          value: "Spring Boot API, SEC fetch, SSE bridge, provider error mapping, Java service boundary",
        },
        {
          name: "Research Service",
          value: "Python, LangGraph, LangChain tools, LlamaIndex cleaning/chunking, EvidencePack assembly",
        },
        {
          name: "Storage",
          value: "PGVector for filing chunks and retrieval metadata; SEC companyfacts for structured metrics",
        },
      ],
    },
    difference: {
      label: "What makes it different",
      title: "我们把 RAG 收缩成工具，把 Agent 输出做成产品界面。",
      points: [
        "Company profile 不从 filing snippet 硬凑，而优先来自 company facts 和业务描述。",
        "LLM 失败时展示透明错误、可重试入口和已收集证据，不再用 deterministic report 假装成功。",
        "RAG 面板只展示当前 run 可证明的实时指标，不展示无法实时计算的 recall / precision。",
        "默认显示 all-time K 线图，用户点击不同 Agent report 后再切换报告内容。",
      ],
    },
    footer: {
      title: "把 SEC 文件放进更清晰的研究循环。",
      body:
        "打开应用，输入 ticker，让 Agent 先搭出第一版研究框架；你可以同时检查行情图和工具时间线。",
    },
  },
  en: {
    brandTagline: "AI earnings research workspace",
    nav: {
      app: "App",
      agents: "Agents",
      github: "GitHub",
    },
    actions: {
      launch: "Launch App",
      github: "View on GitHub",
      start: "Start Research",
      issue: "Open Issue",
    },
    localeLabel: "Language",
    hero: {
      pill: "Spring Alpha Workspace",
      title: "Research faster at Any earnings call",
      body:
        "Spring Alpha is a ticker-first AI research workbench. Enter a stock symbol, run three analyst agents, and review SEC filings, market charts, tool timelines, and live RAG telemetry in one focused workspace.",
      imageAlt: "Spring Alpha live workbench preview",
      command: "Analyze NVDA earnings with three agents",
    },
    strips: [
      "SEC filings",
      "Yahoo market data",
      "LangGraph agents",
      "EvidencePack telemetry",
    ],
    terminal: {
      title: "One ticker. Three agents. One research surface.",
      lines: [
        "ticker=NVDA provider=siliconflow",
        "agent.latest_earnings: collect facts, synthesize report",
        "agent.business_driver: inspect segment and demand changes",
        "agent.cash_flow: evaluate FCF and capital allocation",
        "ui.timeline: stream messages, tools, and telemetry",
      ],
    },
    sections: [
      {
        label: "01 / Agents",
        title: "Three reports run in order",
        body:
          "Latest Earnings Readout, Business Driver Deep Dive, and Cash Flow & Capital Allocation are designed as separate analyst lanes, so the user can switch reports without losing the full run context.",
      },
      {
        label: "02 / Workspace",
        title: "The chart is the default surface",
        body:
          "Before a report is selected, the app opens with an all-time market chart. Reports, agent status, and Messages & Tools stay around it instead of replacing the workflow with a chat box.",
      },
      {
        label: "03 / RAG",
        title: "Telemetry, not fake scores",
        body:
          "The RAG panel only shows current-run signals: evidence retrieved, evidence used, metric facts, sections covered, latency, empty retrieval, and evidence pack size.",
      },
    ],
    highlights: {
      label: "Project Highlights",
      title: "Not a pretty demo, but a real research pipeline.",
      cards: [
        {
          title: "Ticker-first entry",
          body:
            "The user starts with a ticker. The workspace resolves the company, opens the chart, and runs three research agents in order.",
        },
        {
          title: "TradingAgents-style execution",
          body:
            "Agents follow a LangGraph / LangChain tool-calling shape, separating company facts, SEC evidence, metric facts, and synthesis.",
        },
        {
          title: "Live telemetry",
          body:
            "The sidebar shows current-run messages, tools, latency, evidence pack size, and retrieval signals instead of offline benchmark scores.",
        },
        {
          title: "BYOK providers",
          body:
            "Users can bring SiliconFlow, OpenAI, or Gemini keys. Keys stay local in the browser and are forwarded only for the active request.",
        },
      ],
    },
    architecture: {
      label: "Architecture",
      title: "Spring Boot, Python agents, Next.js, and PGVector form an auditable research loop.",
      rows: [
        {
          name: "Frontend",
          value: "Next.js workbench, ticker autocomplete, market chart, agent report tabs, timeline sidebar",
        },
        {
          name: "Backend",
          value: "Spring Boot API, SEC fetch, SSE bridge, provider error mapping, Java service boundary",
        },
        {
          name: "Research Service",
          value: "Python, LangGraph, LangChain tools, LlamaIndex cleaning/chunking, EvidencePack assembly",
        },
        {
          name: "Storage",
          value: "PGVector for filing chunks and retrieval metadata; SEC companyfacts for structured metrics",
        },
      ],
    },
    difference: {
      label: "What makes it different",
      title: "RAG is a tool. Agent output is a product surface.",
      points: [
        "Company profile comes from company facts and business descriptions, not filing snippets forced into a bio.",
        "LLM failures show transparent errors, retry affordances, and collected evidence instead of deterministic fake reports.",
        "The RAG panel only exposes current-run telemetry, not recall / precision metrics that cannot be computed live.",
        "The default surface is the all-time market chart; reports appear when users choose an agent lane.",
      ],
    },
    footer: {
      title: "Bring SEC filings into a sharper research loop.",
      body:
        "Open the app, type a ticker, and let the agents build the first pass while you inspect the chart and timeline.",
    },
  },
} satisfies Record<Locale, {
  brandTagline: string;
  nav: Record<"app" | "agents" | "github", string>;
  actions: Record<"launch" | "github" | "start" | "issue", string>;
  localeLabel: string;
  hero: {
    pill: string;
    title: string;
    body: string;
    imageAlt: string;
    command: string;
  };
  strips: string[];
  terminal: {
    title: string;
    lines: string[];
  };
  sections: Array<{
    label: string;
    title: string;
    body: string;
  }>;
  highlights: {
    label: string;
    title: string;
    cards: Array<{
      title: string;
      body: string;
    }>;
  };
  architecture: {
    label: string;
    title: string;
    rows: Array<{
      name: string;
      value: string;
    }>;
  };
  difference: {
    label: string;
    title: string;
    points: string[];
  };
  footer: {
    title: string;
    body: string;
  };
}>;

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
  const [locale, setLocale] = useState<Locale>("zh");
  const [isLocaleReady, setIsLocaleReady] = useState(false);
  const [ticker, setTicker] = useState("");
  const tickerInputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setLocale(getInitialLocale());
      setIsLocaleReady(true);
    }, 0);

    return () => window.clearTimeout(handle);
  }, []);

  useEffect(() => {
    if (isLocaleReady) {
      window.localStorage.setItem(LANDING_LOCALE_STORAGE, locale);
    }
  }, [isLocaleReady, locale]);

  const t = copy[locale];

  const updateLocale = (nextLocale: Locale) => {
    setLocale(nextLocale);
    window.localStorage.setItem(LANDING_LOCALE_STORAGE, nextLocale);
  };

  const handleTickerSubmit = (submittedTicker: string) => {
    const normalizedTicker = submittedTicker.trim().toUpperCase();
    if (!normalizedTicker) {
      return;
    }

    router.push(`/app?ticker=${encodeURIComponent(normalizedTicker)}`);
  };

  return (
    <main className="min-h-screen overflow-hidden bg-[#111111] font-['Noto_Sans_Mono',var(--font-geist-mono),ui-monospace,monospace] text-[#ebebeb]">
      <div className="pointer-events-none fixed inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.06)_1px,transparent_1.4px)] bg-[length:18px_18px] opacity-55" />
        <div className="absolute inset-0 bg-[linear-gradient(180deg,rgba(17,17,17,0.08),#111111_78%)]" />
        <div className="absolute -left-28 top-8 h-[44rem] w-[26rem] rotate-[-22deg] rounded-[3rem] border border-white/10 bg-[linear-gradient(135deg,rgba(255,255,255,0.11),rgba(255,255,255,0.02))] opacity-45 shadow-[0_0_90px_rgba(0,0,0,0.65)]" />
        <div className="absolute -right-20 top-0 h-[34rem] w-[19rem] rotate-[18deg] rounded-[2.5rem] border border-white/10 bg-[linear-gradient(160deg,rgba(20,184,166,0.2),rgba(212,184,126,0.05),rgba(255,255,255,0.02))] opacity-45 blur-[1px]" />
        <div className="absolute inset-x-0 bottom-0 h-80 bg-[linear-gradient(180deg,transparent,#111111)]" />
      </div>

      <div className="relative mx-auto flex min-h-screen w-full max-w-[1240px] flex-col px-5 pb-16 pt-5 sm:px-7 lg:px-8">
        <header className="flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-3" aria-label="Spring Alpha home">
            <span className="grid h-9 w-9 place-items-center rounded-lg border border-emerald-300/20 bg-[#062b2c] text-emerald-300 shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_10px_28px_rgba(16,185,129,0.16)]">
              <ChartCandlestick className="h-5 w-5" />
            </span>
            <span className="text-base font-semibold tracking-[-0.02em] text-white">
              Spring Alpha
            </span>
          </Link>

          <nav className="hidden items-center gap-8 text-sm font-semibold text-white/72 md:flex">
            <Link href="/app" className="transition hover:text-white">
              <ChartCandlestick className="mr-2 inline h-4 w-4 text-white/40" />
              {t.nav.app}
            </Link>
            <a href="#agents" className="transition hover:text-white">
              <Bot className="mr-2 inline h-4 w-4 text-white/40" />
              {t.nav.agents}
            </a>
            <a
              href="https://github.com/CadeYu/spring-alpha"
              target="_blank"
              rel="noreferrer"
              className="transition hover:text-white"
            >
              <Github className="mr-2 inline h-4 w-4 text-white/40" />
              {t.nav.github}
            </a>
          </nav>

          <div className="flex items-center gap-3">
            <div className="hidden items-center rounded-full border border-white/10 bg-black/35 p-1 sm:flex">
              <Languages className="ml-2 h-3.5 w-3.5 text-white/45" />
              {(["zh", "en"] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => updateLocale(option)}
                  aria-pressed={locale === option}
                  aria-label={`${t.localeLabel}: ${option.toUpperCase()}`}
                  className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                    locale === option
                      ? "bg-white/12 text-white"
                      : "text-white/50 hover:text-white"
                  }`}
                >
                  {option.toUpperCase()}
                </button>
              ))}
            </div>
            <Link
              href="/app"
              className="inline-flex min-h-11 items-center justify-center rounded-lg bg-[#0fc6a5] px-5 text-sm font-bold text-[#031f1c] shadow-[0_14px_35px_rgba(15,198,165,0.2)] transition hover:-translate-y-0.5 hover:bg-[#35d8bd]"
            >
              {t.actions.launch}
            </Link>
          </div>
        </header>

        <section className="flex flex-1 flex-col items-center pt-20 text-center sm:pt-24 lg:pt-28">
          <Link
            href="/app"
            className="mb-12 inline-flex items-center gap-3 rounded-full border border-white/10 bg-black/45 px-4 py-2 text-sm font-semibold text-white/70 shadow-[inset_0_1px_0_rgba(255,255,255,0.08),0_12px_34px_rgba(0,0,0,0.35)] backdrop-blur"
          >
            <span>{t.hero.pill}</span>
            <span className="h-4 w-px bg-white/12" />
            <span className="grid h-7 w-7 place-items-center rounded-full bg-white/8 text-white">
              <ArrowUpRight className="h-4 w-4" />
            </span>
          </Link>

          <h1 className="max-w-5xl text-balance text-[3.05rem] font-semibold leading-[1.04] tracking-[-0.045em] text-[#d8d8d8] sm:text-[4.15rem] lg:text-[5.25rem]">
            {t.hero.title}
          </h1>

          <p className="mt-7 max-w-4xl text-balance text-base font-medium leading-8 text-white/48 sm:text-lg lg:text-xl">
            {t.hero.body}
          </p>

          <div className="mt-9 w-full max-w-3xl">
            <TickerSearchInput
              value={ticker}
              onValueChange={setTicker}
              onSubmit={handleTickerSubmit}
              placeholder={tickerSearchPlaceholder[locale]}
              buttonLabel={tickerSearchButtonLabel[locale]}
              inputRef={tickerInputRef}
              wrapperClassName="h-16"
              inputClassName="text-lg sm:text-xl"
              buttonClassName="bg-[#0fc6a5] text-[#031f1c] hover:bg-[#35d8bd]"
              inputProps={{
                role: "combobox",
                autoComplete: "off",
                "aria-label": locale === "zh" ? "输入股票代码" : "Enter ticker",
              }}
            />
            <p className="mt-3 text-sm text-white/48">
              {locale === "zh"
                ? "匿名用户可免费分析 1 次，之后需要 Google 登录并使用自己的 key。"
                : "Anonymous users get one free real analysis, then must sign in with Google and bring their own key."}
            </p>
          </div>

          <div className="mt-9 flex flex-col items-center justify-center gap-4 sm:flex-row">
            <a
              href="https://github.com/CadeYu/spring-alpha"
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border border-white/10 bg-black/35 px-6 text-sm font-bold text-white/78 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)] transition hover:-translate-y-0.5 hover:border-white/20 hover:text-white"
            >
              <Github className="h-4 w-4" />
              {t.actions.github}
            </a>
          </div>

          <div className="mt-12 flex max-w-4xl flex-wrap items-center justify-center gap-3">
            {t.strips.map((item) => (
              <span
                key={item}
                className="rounded-full border border-white/10 bg-white/[0.035] px-4 py-2 text-xs font-semibold text-white/50"
              >
                {item}
              </span>
            ))}
          </div>
        </section>

        <section className="relative mt-12 border-t border-white/10 pt-4 sm:mt-16">
          <div className="absolute inset-x-[-3rem] top-0 h-px bg-[linear-gradient(90deg,transparent,rgba(20,184,166,0.68),rgba(212,184,126,0.35),transparent)]" />
          <div className="mx-auto max-w-[1124px] overflow-hidden rounded-t-[1.55rem] border border-white/12 bg-[#0b0b0b] shadow-[0_30px_100px_rgba(0,0,0,0.72)]">
            <div className="flex items-center gap-2 border-b border-white/10 bg-[#161b1f] px-5 py-3">
              <span className="h-3 w-3 rounded-full bg-white/18" />
              <span className="h-3 w-3 rounded-full bg-[#d4b87e]/45" />
              <span className="h-3 w-3 rounded-full bg-[#2dd4bf]/65" />
              <div className="ml-4 min-w-0 flex-1 rounded-md bg-white/[0.06] px-3 py-1.5 text-left text-xs font-semibold text-white/45">
                {t.hero.command}
              </div>
            </div>
            <div className="relative aspect-[16/9] min-h-[320px] bg-[#070b12] sm:min-h-[520px]">
              <Image
                src="/showcase/live-workbench.png"
                alt={t.hero.imageAlt}
                fill
                priority
                sizes="(min-width: 1280px) 1124px, 92vw"
                className="object-cover object-top"
              />
              <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-[linear-gradient(180deg,transparent,rgba(17,17,17,0.86))]" />
            </div>
          </div>
        </section>

        <section id="agents" className="grid gap-6 border-y border-white/10 py-16 lg:grid-cols-[0.9fr_1.1fr]">
          <div className="max-w-lg">
            <p className="text-sm font-bold uppercase tracking-[0.22em] text-[#2dd4bf]">
              Agent Runtime
            </p>
            <h2 className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">
              {t.terminal.title}
            </h2>
          </div>

          <div className="rounded-2xl border border-white/10 bg-black/42 p-4 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.07)]">
            <div className="mb-4 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.18em] text-white/38">
              <TerminalSquare className="h-4 w-4" />
              Messages & Tools
            </div>
            <div className="space-y-3">
              {t.terminal.lines.map((line, index) => (
                <div key={line} className="grid grid-cols-[3.75rem_1fr] gap-4 text-sm">
                  <span className="text-white/34">00:0{index + 1}</span>
                  <span className="text-white/68">{line}</span>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="grid gap-4 py-16 lg:grid-cols-3">
          {t.sections.map((section) => (
            <article
              key={section.label}
              className="rounded-2xl border border-white/10 bg-white/[0.035] p-6 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
            >
              <p className="text-xs font-bold uppercase tracking-[0.22em] text-white/34">
                {section.label}
              </p>
              <h2 className="mt-5 text-2xl font-semibold tracking-[-0.035em] text-white">
                {section.title}
              </h2>
              <p className="mt-4 text-sm leading-7 text-white/50">{section.body}</p>
            </article>
          ))}
        </section>

        <section className="grid gap-8 border-t border-white/10 py-16 lg:grid-cols-[0.82fr_1.18fr]">
          <div className="max-w-xl">
            <p className="text-sm font-bold uppercase tracking-[0.22em] text-[#2dd4bf]">
              {t.highlights.label}
            </p>
            <h2 className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">
              {t.highlights.title}
            </h2>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {t.highlights.cards.map((card) => (
              <article
                key={card.title}
                className="rounded-2xl border border-white/10 bg-white/[0.035] p-5 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
              >
                <h3 className="text-lg font-semibold tracking-[-0.03em] text-white">
                  {card.title}
                </h3>
                <p className="mt-3 text-sm leading-7 text-white/50">{card.body}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="grid gap-8 rounded-3xl border border-white/10 bg-black/35 p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)] sm:p-8 lg:grid-cols-[0.88fr_1.12fr]">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.22em] text-[#d4b87e]">
              {t.architecture.label}
            </p>
            <h2 className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">
              {t.architecture.title}
            </h2>
          </div>

          <div className="divide-y divide-white/10 rounded-2xl border border-white/10 bg-[#0b1114]">
            {t.architecture.rows.map((row) => (
              <div key={row.name} className="grid gap-2 p-5 sm:grid-cols-[10rem_1fr]">
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-white/38">
                  {row.name}
                </p>
                <p className="text-sm leading-7 text-white/62">{row.value}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-8 py-16 lg:grid-cols-[0.92fr_1.08fr]">
          <div>
            <p className="text-sm font-bold uppercase tracking-[0.22em] text-[#2dd4bf]">
              {t.difference.label}
            </p>
            <h2 className="mt-4 max-w-xl text-3xl font-semibold tracking-[-0.04em] text-white sm:text-4xl">
              {t.difference.title}
            </h2>
          </div>

          <div className="grid gap-3">
            {t.difference.points.map((point, index) => (
              <div
                key={point}
                className="grid gap-4 rounded-2xl border border-white/10 bg-white/[0.035] p-5 text-left sm:grid-cols-[3.2rem_1fr]"
              >
                <span className="text-sm font-bold text-white/34">
                  0{index + 1}
                </span>
                <p className="text-sm leading-7 text-white/58">{point}</p>
              </div>
            ))}
          </div>
        </section>

        <footer className="grid gap-8 rounded-3xl border border-white/10 bg-[#f7f1e8] p-6 text-black shadow-[0_28px_80px_rgba(0,0,0,0.45)] sm:p-8 lg:grid-cols-[1fr_auto] lg:items-center">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full bg-black px-3 py-1.5 text-xs font-bold text-white">
              <ChartCandlestick className="h-3.5 w-3.5" />
              Ticker-first
            </div>
            <h2 className="max-w-3xl text-3xl font-semibold tracking-[-0.04em] sm:text-4xl">
              {t.footer.title}
            </h2>
            <p className="mt-4 max-w-2xl text-sm font-semibold leading-7 text-black/52">
              {t.footer.body}
            </p>
          </div>
          <div className="flex flex-col gap-3 sm:flex-row lg:flex-col">
            <Link
              href="/app"
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg bg-black px-6 text-sm font-bold text-white transition hover:-translate-y-0.5 hover:bg-black/82"
            >
              {t.actions.launch}
              <ArrowUpRight className="h-4 w-4" />
            </Link>
            <a
              href="https://github.com/CadeYu/spring-alpha/issues"
              target="_blank"
              rel="noreferrer"
              className="inline-flex min-h-12 items-center justify-center gap-2 rounded-lg border border-black/10 bg-white/60 px-6 text-sm font-bold text-black transition hover:-translate-y-0.5 hover:bg-white"
            >
              <MessageSquareText className="h-4 w-4" />
              {t.actions.issue}
            </a>
          </div>
        </footer>
      </div>
    </main>
  );
}
