import Image from "next/image";
import Link from "next/link";
import {
  ArrowUpRight,
  BadgeCheck,
  BrainCircuit,
  FileSearch,
  Github,
  Radar,
  Sparkles,
  SquareChartGantt,
} from "lucide-react";

const featureCards = [
  {
    title: "财报读得更快",
    body: "把 SEC filing、结构化财务指标和前端 dashboard 串成一条链，不用在 10-Q、10-K 和图表之间来回跳。",
    icon: FileSearch,
  },
  {
    title: "先看结论，再钻细节",
    body: "核心分析、驱动因素、风险项、Bull / Bear case 和关键图表同屏展开，适合快速形成研究框架。",
    icon: SquareChartGantt,
  },
  {
    title: "不是纯聊天，是可落地研究流",
    body: "支持 citation / verification、行业模式切换、指标健康雷达和 PDF 导出，更像一个分析工作台。",
    icon: BrainCircuit,
  },
];

const proofPoints = [
  "季度与年度财报分析",
  "SEC / Yahoo 双源补充",
  "关键财务指标与趋势图",
  "多模型接入与 BYOK",
  "风险因子与驱动拆解",
  "PDF 报告导出",
];

const workflow = [
  {
    step: "01",
    title: "输入 ticker",
    body: "从 AAPL、NVDA 到银行、支付、半导体，我们先抓财报与行情补充数据。",
  },
  {
    step: "02",
    title: "生成结构化看板",
    body: "把营收、利润、现金流、趋势图和健康评分整理成一套可读 dashboard。",
  },
  {
    step: "03",
    title: "给出研究视角",
    body: "把业务主线、增长驱动、风险暴露和多空逻辑压缩成更像分析师的表达。",
  },
];

const heroStats = [
  { label: "数据链路", value: "SEC + Yahoo + AI" },
  { label: "输出形态", value: "Dashboard / PDF / Citations" },
  { label: "适用场景", value: "研究、演示、内容生产" },
];

const heroFlowNodes = [
  { title: "SEC Filing", detail: "10-Q / 10-K parsing" },
  { title: "Structured Facts", detail: "Revenue / Margin / FCF" },
  { title: "AI Thesis", detail: "Drivers / Risks / Scenarios" },
];

export default function LandingPage() {
  return (
    <main className="min-h-screen overflow-hidden bg-[#07111f] text-white">
      <div className="pointer-events-none absolute inset-0">
        <div className="absolute left-[-10%] top-[-8rem] h-[28rem] w-[28rem] rounded-full bg-[radial-gradient(circle,_rgba(30,199,164,0.28),_transparent_65%)] blur-3xl" />
        <div className="absolute right-[-8%] top-[10rem] h-[30rem] w-[30rem] rounded-full bg-[radial-gradient(circle,_rgba(71,132,255,0.20),_transparent_70%)] blur-3xl" />
        <div className="absolute inset-x-0 top-0 h-[32rem] bg-[linear-gradient(180deg,rgba(14,30,54,0.92),rgba(7,17,31,0.55),transparent)]" />
        <div className="absolute inset-0 bg-[linear-gradient(rgba(140,169,212,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(140,169,212,0.08)_1px,transparent_1px)] bg-[size:72px_72px] [mask-image:radial-gradient(circle_at_center,black,transparent_85%)]" />
      </div>

      <div className="relative mx-auto flex w-full max-w-7xl flex-col px-6 pb-16 pt-6 sm:px-8 lg:px-10">
        <header className="sticky top-4 z-20 mb-10">
          <div className="mx-auto flex max-w-6xl items-center justify-between rounded-full border border-white/10 bg-slate-950/55 px-5 py-3 shadow-[0_10px_40px_rgba(0,0,0,0.25)] backdrop-blur-xl">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-emerald-400/15 text-emerald-300 ring-1 ring-emerald-300/20">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm font-semibold tracking-[0.24em] text-emerald-300 uppercase">
                  Spring Alpha
                </p>
                <p className="text-xs text-slate-400">
                  AI earnings research cockpit
                </p>
              </div>
            </div>

            <nav className="hidden items-center gap-6 text-sm text-slate-300 md:flex">
              <a href="#features" className="transition hover:text-white">
                Features
              </a>
              <a href="#showcase" className="transition hover:text-white">
                Showcase
              </a>
              <a href="#workflow" className="transition hover:text-white">
                Workflow
              </a>
            </nav>

            <div className="flex items-center gap-2">
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
                Launch App
                <ArrowUpRight className="h-4 w-4" />
              </Link>
            </div>
          </div>
        </header>

        <section className="relative grid items-end gap-10 pb-16 pt-4 lg:grid-cols-[1.05fr_0.95fr]">
          <div className="max-w-3xl">
            <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-4 py-2 text-sm text-emerald-200">
              <BadgeCheck className="h-4 w-4" />
              面向美股财报研究的 AI 分析工作台
            </div>

            <h1 className="max-w-4xl text-5xl font-semibold leading-[0.94] tracking-[-0.05em] text-white sm:text-6xl lg:text-7xl">
              把
              <span className="bg-[linear-gradient(135deg,#d8fff5,#7cebd4_35%,#8eb9ff_70%,#ffffff)] bg-clip-text text-transparent">
                财报阅读
              </span>
              变成一块真正可用的研究界面
            </h1>

            <p className="mt-8 max-w-2xl text-lg leading-8 text-slate-300 sm:text-xl">
              Spring Alpha 把 SEC 原文、结构化财务指标、趋势图、风险因子和 AI
              解读放在一个连续体验里。先看品牌页理解它能做什么，再一键进入真正的财报
              app。
            </p>

            <div className="mt-10 flex flex-col gap-4 sm:flex-row">
              <Link
                href="/app"
                className="inline-flex items-center justify-center gap-2 rounded-full bg-[linear-gradient(135deg,#34d399,#58e7c8,#76a9ff)] px-6 py-3 text-sm font-semibold text-slate-950 shadow-[0_18px_45px_rgba(42,192,160,0.35)] transition hover:scale-[1.01]"
              >
                Launch App
                <ArrowUpRight className="h-4 w-4" />
              </Link>
              <a
                href="#showcase"
                className="inline-flex items-center justify-center gap-2 rounded-full border border-white/12 bg-white/5 px-6 py-3 text-sm font-medium text-slate-200 transition hover:bg-white/10"
              >
                看现有界面
                <Radar className="h-4 w-4" />
              </a>
            </div>

            <div className="mt-8 rounded-[1.8rem] border border-white/8 bg-[linear-gradient(180deg,rgba(11,20,32,0.92),rgba(9,15,26,0.88))] p-5">
              <div className="flex items-center gap-3">
                <div className="h-10 w-10 rounded-2xl bg-emerald-400/12 ring-1 ring-emerald-300/15" />
                <div>
                  <p className="text-xs uppercase tracking-[0.22em] text-emerald-300/80">
                    Analysis flow
                  </p>
                  <p className="mt-1 text-sm text-slate-300">
                    从披露原文到结构化指标，再到更像研究结论的表达。
                  </p>
                </div>
              </div>

              <div className="mt-5 hidden items-center gap-3 xl:flex">
                {heroFlowNodes.map((node, index) => (
                  <div key={node.title} className="flex items-center gap-3">
                    <div className="min-w-[170px] rounded-[1.2rem] border border-white/8 bg-white/[0.04] px-4 py-3">
                      <div className="mb-2 flex items-center gap-2">
                        <span className="h-2.5 w-2.5 rounded-full bg-emerald-300 shadow-[0_0_18px_rgba(110,231,183,0.8)]" />
                        <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-200/90">
                          {node.title}
                        </p>
                      </div>
                      <p className="text-xs leading-6 text-slate-300">{node.detail}</p>
                    </div>
                    {index < heroFlowNodes.length - 1 && (
                      <div className="h-px w-8 bg-[linear-gradient(90deg,rgba(74,222,128,0.8),rgba(125,211,252,0.35))]" />
                    )}
                  </div>
                ))}
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-2 xl:hidden">
                <div className="rounded-[1.2rem] border border-emerald-300/15 bg-white/[0.04] px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">
                    Signal snapshot
                  </p>
                  <p className="mt-3 text-3xl font-semibold text-emerald-300">+15.65%</p>
                  <p className="mt-1 text-sm text-slate-300">Revenue YoY growth</p>
                </div>
                <div className="rounded-[1.2rem] border border-sky-300/15 bg-white/[0.04] px-4 py-4">
                  <p className="text-[11px] uppercase tracking-[0.22em] text-slate-500">
                    Grounded mode
                  </p>
                  <p className="mt-3 text-base font-semibold text-white">
                    Citations + charts
                  </p>
                  <p className="mt-2 text-xs leading-6 text-slate-300">
                    把数字、图表和论点放进同一条阅读链路。
                  </p>
                </div>
              </div>
            </div>

            <div className="mt-12 grid gap-3 sm:grid-cols-2">
              {proofPoints.map((item) => (
                <div
                  key={item}
                  className="rounded-2xl border border-white/8 bg-white/4 px-4 py-4 text-sm text-slate-200 backdrop-blur-sm"
                >
                  <span className="mr-2 text-emerald-300">+</span>
                  {item}
                </div>
              ))}
            </div>

            <div className="mt-8 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
              <div className="rounded-[1.6rem] border border-white/8 bg-[linear-gradient(180deg,rgba(14,24,39,0.96),rgba(10,16,28,0.92))] p-5">
                <p className="text-xs uppercase tracking-[0.24em] text-slate-500">
                  What you get
                </p>
                <p className="mt-3 text-xl font-semibold text-white">
                  从原始披露，到能直接拿来判断的研究界面
                </p>
                <p className="mt-4 text-sm leading-7 text-slate-300">
                  它不是单独一个聊天框，也不是只有几张图的静态 dashboard，而是把“看财报”和“形成观点”放在同一条阅读路径里。
                </p>
              </div>
              <div className="grid gap-3">
                {heroStats.map((item) => (
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

          <div className="relative">
            <div className="absolute -inset-6 rounded-[2rem] bg-[radial-gradient(circle_at_top,rgba(52,211,153,0.20),transparent_55%),radial-gradient(circle_at_bottom_right,rgba(101,153,255,0.18),transparent_45%)] blur-2xl" />
            <div className="relative overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(18,31,49,0.96),rgba(10,18,30,0.92))] p-5 shadow-[0_24px_90px_rgba(0,0,0,0.42)]">
              <div className="flex items-center justify-between border-b border-white/8 pb-4">
                <div>
                  <p className="text-xs uppercase tracking-[0.24em] text-emerald-300/80">
                    Live product frame
                  </p>
                  <p className="mt-2 text-2xl font-semibold text-white">
                    用 AAPL 实际页面展示产品完成度
                  </p>
                </div>
                <div className="rounded-full border border-emerald-300/20 bg-emerald-300/10 px-3 py-1 text-xs text-emerald-100">
                  Real dashboard
                </div>
              </div>

              <div className="mt-5 grid gap-3 sm:grid-cols-3">
                <div className="rounded-2xl border border-white/8 bg-[#09111c] p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    Engine
                  </p>
                  <p className="mt-2 text-lg font-semibold text-white">
                    SEC + Yahoo
                  </p>
                </div>
                <div className="rounded-2xl border border-white/8 bg-[#09111c] p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    Output
                  </p>
                  <p className="mt-2 text-lg font-semibold text-white">
                    Dashboard + PDF
                  </p>
                </div>
                <div className="rounded-2xl border border-white/8 bg-[#09111c] p-4">
                  <p className="text-xs uppercase tracking-[0.2em] text-slate-500">
                    Research mode
                  </p>
                  <p className="mt-2 text-lg font-semibold text-white">
                    Bull / Bear / Risks
                  </p>
                </div>
              </div>

              <div className="mt-5 overflow-hidden rounded-[1.4rem] border border-white/10 bg-[#040b14] p-3">
                <Image
                  src="/showcase/aapl-dashboard.png"
                  alt="Spring Alpha AAPL dashboard preview"
                  width={576}
                  height={1536}
                  className="h-auto w-full rounded-[1rem]"
                  priority
                />
              </div>
            </div>
          </div>
        </section>

        <section
          id="features"
          className="grid gap-5 border-y border-white/8 py-16 md:grid-cols-3"
        >
          {featureCards.map(({ title, body, icon: Icon }) => (
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
          ))}
        </section>

        <section
          id="showcase"
          className="grid gap-8 py-16 lg:grid-cols-[0.9fr_1.1fr]"
        >
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-emerald-300/75">
              Showcase
            </p>
            <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-white">
              不是只会回答一句话，而是给你一整页研究上下文
            </h2>
            <p className="mt-6 max-w-xl text-lg leading-8 text-slate-300">
              这个页面会把核心分析、关键指标、营收趋势、利润率趋势、杜邦拆解、健康雷达、
              风险因子和多空逻辑排在同一条阅读流里。你不需要边看财报边自己拼 dashboard。
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-[1.6rem] border border-white/8 bg-[linear-gradient(180deg,rgba(13,22,34,0.98),rgba(10,16,26,0.92))] p-5">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                Analysis surface
              </p>
              <p className="mt-3 text-xl font-semibold text-white">
                读财报最常用的模块一次展开
              </p>
              <p className="mt-4 text-sm leading-7 text-slate-300">
                Executive summary、drivers、risk、citations 和图表不是拆开的多个工具，而是一页内完成的分析旅程。
              </p>
            </div>
            <div className="rounded-[1.6rem] border border-white/8 bg-[linear-gradient(180deg,rgba(9,18,33,0.98),rgba(9,15,25,0.92))] p-5">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                Research discipline
              </p>
              <p className="mt-3 text-xl font-semibold text-white">
                兼顾可视化和 grounded 输出
              </p>
              <p className="mt-4 text-sm leading-7 text-slate-300">
                不是只有会说故事的 LLM，也不是只有冰冷数字。它尝试把原始披露、结构化指标和表达质量放进同一个产品里。
              </p>
            </div>
            <div className="rounded-[1.6rem] border border-white/8 bg-[linear-gradient(180deg,rgba(13,22,34,0.98),rgba(10,16,26,0.92))] p-5 md:col-span-2">
              <p className="text-xs uppercase tracking-[0.22em] text-slate-500">
                Why this matters
              </p>
              <p className="mt-3 text-xl font-semibold text-white">
                为个人研究、内容创作和 demo 展示做了一层更有完成度的包装
              </p>
              <p className="mt-4 text-sm leading-7 text-slate-300">
                你可以把它当成一个 AI 财报分析 app，也可以把它当成一套面向投资研究产品的交互原型。新的 landing
                page 负责讲清楚产品定位，`Launch App` 负责把人送进真正的工作区。
              </p>
            </div>
          </div>
        </section>

        <section
          id="workflow"
          className="rounded-[2rem] border border-white/8 bg-white/[0.035] p-6 sm:p-8"
        >
          <div className="max-w-2xl">
            <p className="text-sm uppercase tracking-[0.28em] text-emerald-300/75">
              Workflow
            </p>
            <h2 className="mt-4 text-4xl font-semibold tracking-[-0.04em] text-white">
              从一只股票，到一页像样的研究输出
            </h2>
          </div>

          <div className="mt-10 grid gap-4 lg:grid-cols-3">
            {workflow.map((item) => (
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
                  Open source momentum
                </p>
                <h2 className="mt-4 max-w-3xl text-4xl font-semibold tracking-[-0.04em] text-white">
                  如果你喜欢这个方向，欢迎去 GitHub 点赞、提 issue，或者直接贡献代码。
                </h2>
                <p className="mt-5 max-w-2xl text-lg leading-8 text-slate-300">
                  Spring Alpha 现在不仅是一个可运行的财报分析 app，也是一套正在持续打磨的开源产品原型。你的 star、反馈、PR 和想法，都会直接影响它下一步长成什么样。
                </p>
              </div>

              <div className="flex flex-col items-stretch gap-3 sm:flex-row lg:flex-col">
                <a
                  href="https://github.com/CadeYu/spring-alpha"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center gap-2 rounded-full bg-[linear-gradient(135deg,#34d399,#58e7c8,#76a9ff)] px-6 py-3 text-sm font-semibold text-slate-950 shadow-[0_18px_45px_rgba(42,192,160,0.35)] transition hover:scale-[1.01]"
                >
                  Star on GitHub
                  <Github className="h-4 w-4" />
                </a>
                <a
                  href="https://github.com/CadeYu/spring-alpha/issues"
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center justify-center gap-2 rounded-full border border-white/12 bg-white/5 px-6 py-3 text-sm font-medium text-slate-200 transition hover:bg-white/10"
                >
                  Contribute / Open Issue
                  <ArrowUpRight className="h-4 w-4" />
                </a>
                <Link
                  href="/app"
                  className="inline-flex items-center justify-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-6 py-3 text-sm font-medium text-emerald-100 transition hover:bg-emerald-400/16"
                >
                  Launch App
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
