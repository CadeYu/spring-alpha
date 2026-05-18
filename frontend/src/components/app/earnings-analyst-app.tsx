"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineStyle,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type Time,
} from "lightweight-charts";
import {
  Loader2,
  TrendingUp,
  Bot,
  BriefcaseBusiness,
  ChartColumnIncreasing,
  WalletCards,
  AlertTriangle,
  MessageSquareText,
  Wrench,
} from "lucide-react";
import {
  AnalysisReport,
  AnalysisMetadata,
  BusinessDriverSections,
  CashFlowCapitalAllocationSections,
  EvidenceBoundPoint,
  EvidenceBoundMetric,
  LatestEarningsSections,
  CompanyProfileSection,
} from "@/types/AnalysisReport";
import { RagEvalDashboard } from "@/components/app/rag-eval-dashboard";
import { PdfDownloadButton } from "@/components/pdf/PdfDownloadButton";
import { formatPeriodForDisplay } from "@/lib/reportPresentation";
import { type ResearchTaskId } from "@/lib/researchTasks";
import { cn } from "@/lib/utils";
import { useSession } from "next-auth/react";
import { AuthBanner } from "@/components/app/auth-banner";
import { TickerSearchInput } from "@/components/app/ticker-search-input";
import { TrialGate, type TrialGateStatus } from "@/components/app/trial-gate";

const BYOK_PROVIDERS = [
  {
    id: "siliconflow",
    name: "SiliconFlow",
    modelName: "Kimi K2.6",
    description: "Use your own SiliconFlow key",
    descZh: "使用你自己的 SiliconFlow Key",
    keyLabel: "SiliconFlow API Key",
    keyPlaceholder: "Enter your SiliconFlow key",
    storageKey: "spring-alpha-siliconflow-key",
    badge: "SF",
  },
  {
    id: "openai",
    name: "OpenAI",
    modelName: "GPT",
    description: "Use your own OpenAI key",
    descZh: "使用你自己的 OpenAI Key",
    keyLabel: "OpenAI API Key",
    keyPlaceholder: "Enter your OpenAI key",
    storageKey: "spring-alpha-openai-key",
    badge: "OA",
  },
  {
    id: "gemini",
    name: "Gemini",
    modelName: "Gemini Pro",
    description: "Use your own Gemini key",
    descZh: "使用你自己的 Gemini Key",
    keyLabel: "Gemini API Key",
    keyPlaceholder: "Enter your Gemini key",
    storageKey: "spring-alpha-gemini-key",
    badge: "GM",
  },
] as const;

type ByokProviderId = (typeof BYOK_PROVIDERS)[number]["id"];

type AnalysisErrorState = {
  message: string;
  code?: string;
  source?: string;
  degraded?: boolean;
};

type AnalysisRunPhase = "submitted" | "streaming" | "received" | "failed";

type AnalysisRunState = {
  ticker: string;
  taskTitle: string;
  providerName: string;
  phase: AnalysisRunPhase;
  startedAt: number;
};

type AgentPipelineRun = {
  taskId: ResearchTaskId;
  taskTitle: string;
  phase: AnalysisRunPhase | "pending";
  startedAt?: number;
  completedAt?: number;
};

type ReportsByTask = Partial<Record<ResearchTaskId, AnalysisReport>>;

const ANONYMOUS_TRIAL_STORAGE_KEY = "spring-alpha-anonymous-trial-used";

type TickerSuggestion = {
  ticker: string;
  companyName: string;
};

function normalizeTicker(rawTicker: string | undefined | null) {
  return rawTicker?.toUpperCase().trim() ?? "";
}

type MarketCandle = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
};

type MarketChartHover = {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume?: number;
  changePercent: number;
};

type MarketChartInterval = "1d" | "1wk" | "1mo" | "1y";

const MARKET_CHART_INTERVALS = [
  { id: "1d", label: "1D", labelZh: "日" },
  { id: "1wk", label: "1W", labelZh: "周" },
  { id: "1mo", label: "1M", labelZh: "月" },
  { id: "1y", label: "1Y", labelZh: "年" },
] satisfies Array<{
  id: MarketChartInterval;
  label: string;
  labelZh: string;
}>;

function mergeReportChunks(
  previous: AnalysisReport | undefined,
  reportData: Partial<AnalysisReport>,
): AnalysisReport {
  if (!previous) return reportData as AnalysisReport;

  const filtered = Object.fromEntries(
    Object.entries(reportData).filter(
      ([, value]) => value !== null && value !== undefined,
    ),
  ) as Partial<AnalysisReport>;
  return {
    ...previous,
    ...filtered,
  };
}

const RESEARCH_TASKS = [
  {
    id: "latest_earnings_readout",
    title: "Latest Earnings Readout",
    titleZh: "最新财报速读",
    description: "Full dashboard",
    descriptionZh: "完整 Dashboard",
    Icon: ChartColumnIncreasing,
  },
  {
    id: "business_driver_deep_dive",
    title: "Business Driver Deep Dive",
    titleZh: "业务驱动深挖",
    description: "Products, segments, demand",
    descriptionZh: "产品、分部、需求",
    Icon: BriefcaseBusiness,
  },
  {
    id: "cash_flow_capital_allocation",
    title: "Cash Flow & Capital Allocation",
    titleZh: "现金流与资本配置",
    description: "OCF, FCF, capex, buybacks",
    descriptionZh: "经营现金流、资本开支、回购",
    Icon: WalletCards,
  },
] satisfies Array<{
  id: ResearchTaskId;
  title: string;
  titleZh: string;
  description: string;
  descriptionZh: string;
  Icon: typeof ChartColumnIncreasing;
}>;

export default function EarningsAnalystApp({
  initialTicker = "",
}: {
  initialTicker?: string;
}) {
  const normalizedInitialTicker = normalizeTicker(initialTicker);
  const [ticker, setTicker] = useState(normalizedInitialTicker);
  const [activeTicker, setActiveTicker] = useState(normalizedInitialTicker); // only set on submit
  const [lang, setLang] = useState("en");
  const [model, setModel] = useState<ByokProviderId>("siliconflow");
  const [providerApiKey, setProviderApiKey] = useState("");
  const [providerKeySaved, setProviderKeySaved] = useState(false);
  const [trialStatus, setTrialStatus] = useState<TrialGateStatus>(() => {
    if (typeof window === "undefined") {
      return "anonymous_ready";
    }

    return window.localStorage.getItem(ANONYMOUS_TRIAL_STORAGE_KEY) === "true"
      ? "trial_exhausted"
      : "anonymous_ready";
  });
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [reportsByTask, setReportsByTask] = useState<ReportsByTask>({});
  const [activeReportTaskId, setActiveReportTaskId] =
    useState<ResearchTaskId | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<AnalysisErrorState | null>(null);
  const [runState, setRunState] = useState<AnalysisRunState | null>(null);
  const [pipelineRuns, setPipelineRuns] = useState<AgentPipelineRun[]>([]);
  const [tickerSuggestionsOpen, setTickerSuggestionsOpen] = useState(false);
  const [tickerSuggestions, setTickerSuggestions] = useState<TickerSuggestion[]>([]);
  const [runNow, setRunNow] = useState(0);
  const tickerInputRef = useRef<HTMLInputElement>(null);
  const analysisAbortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const anonymousTrialConsumedRef = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const { status: sessionStatus } = useSession();
  const isZh = lang === "zh";
  const isAuthenticated = sessionStatus === "authenticated";
  const selectedProvider =
    BYOK_PROVIDERS.find((provider) => provider.id === model) ??
    BYOK_PROVIDERS[0];
  const trialGateStatus: TrialGateStatus =
    !isAuthenticated && trialStatus === "trial_exhausted"
      ? "trial_exhausted"
      : "anonymous_ready";
  const reportTitleTicker = activeTicker;
  const orderedReports = RESEARCH_TASKS.flatMap((task) => {
    const taskReport = reportsByTask[task.id];
    return taskReport ? [{ task, report: taskReport }] : [];
  });
  const primaryReport = orderedReports[0]?.report ?? null;
  const reportCompanyName = primaryReport?.companyName?.trim();
  const reportPeriod = primaryReport?.period?.trim();
  const reportFilingDate = primaryReport?.filingDate?.trim();
  const displayPeriod = formatPeriodForDisplay(reportPeriod, lang);
  const activeReportEntry =
    activeReportTaskId === null
      ? null
      : orderedReports.find(({ task }) => task.id === activeReportTaskId) ?? null;
  const timelineMetadata = buildTimelineMetadata(orderedReports, activeReportEntry);
  const timelineTaskTitle = activeReportEntry?.task
    ? isZh
      ? activeReportEntry.task.titleZh
      : activeReportEntry.task.title
    : orderedReports.length > 0
      ? isZh
        ? "全部 Agent"
        : "All agents"
      : undefined;
  useEffect(() => {
    const savedKey = window.localStorage.getItem(selectedProvider.storageKey);
    if (savedKey) {
      setProviderApiKey("");
      setProviderKeySaved(true);
    } else {
      setProviderApiKey("");
      setProviderKeySaved(false);
    }
  }, [selectedProvider.storageKey]);

  useEffect(() => {
    const query = ticker.trim();
    if (query.length < 2) {
      setTickerSuggestions([]);
      return;
    }

    const controller = new AbortController();
    const timeoutId = window.setTimeout(async () => {
      try {
        const response = await fetch(
          `/api/tickers/search?q=${encodeURIComponent(query)}&limit=8`,
          { signal: controller.signal },
        );
        if (!response.ok) {
          setTickerSuggestions([]);
          return;
        }
        const payload = (await response.json()) as {
          suggestions?: TickerSuggestion[];
        };
        setTickerSuggestions(payload.suggestions ?? []);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setTickerSuggestions([]);
      }
    }, 180);

    return () => {
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, [ticker]);

  const analysisApiBase = process.env.NEXT_PUBLIC_BACKEND_URL
    ? `${process.env.NEXT_PUBLIC_BACKEND_URL}/api`
    : "/api";

  const selectTickerSuggestion = (suggestion: TickerSuggestion) => {
    setTicker(suggestion.ticker);
    setTickerSuggestionsOpen(false);
    tickerInputRef.current?.focus();
  };

  const handleSearch = async (rawTicker?: string) => {
    const submittedTicker = normalizeTicker(
      rawTicker ?? tickerInputRef.current?.value ?? ticker,
    );
    if (!submittedTicker || isLoading) return;
    const runtimeProviderKey =
      providerApiKey.trim() ||
      window.localStorage.getItem(selectedProvider.storageKey)?.trim() ||
      "";
    const anonymousTrialAvailable =
      runtimeProviderKey.length === 0 && trialStatus !== "trial_exhausted";
    if (!runtimeProviderKey && isAuthenticated) {
      setError({
        message: isZh
          ? `请先保存你自己的 ${selectedProvider.name} API Key。`
          : `${selectedProvider.name} requires your own saved API key after sign in.`,
        code: "PROVIDER_KEY_REQUIRED",
        source: "auth",
      });
      return;
    }
    if (!runtimeProviderKey && !anonymousTrialAvailable) {
      setTrialStatus("trial_exhausted");
      setError({
        message: isZh
          ? "匿名试用已经用完，请使用 Google 登录并保存你自己的 API Key。"
          : "Your anonymous trial is over. Sign in with Google and save your own API key to continue.",
        code: "TRIAL_EXHAUSTED",
        source: "trial",
      });
      return;
    }

    anonymousTrialConsumedRef.current = false;

    const requestId = Date.now();
    requestIdRef.current = requestId;
    analysisAbortRef.current?.abort();
    const controller = new AbortController();
    analysisAbortRef.current = controller;

    setIsLoading(true);
    setReportsByTask({});
    setActiveReportTaskId(null);
    setError(null);
    setTicker(submittedTicker);
    setActiveTicker(submittedTicker);
    const startedAt = Date.now();
    const initialPipelineRuns = RESEARCH_TASKS.map((task) => ({
      taskId: task.id,
      taskTitle: isZh ? task.titleZh : task.title,
      phase: "pending" as const,
    }));
    setPipelineRuns(initialPipelineRuns);
    setRunState({
      ticker: submittedTicker,
      taskTitle: isZh ? "全部研究 Agent" : "All research agents",
      providerName: selectedProvider.name,
      phase: "submitted",
      startedAt,
    });
    setRunNow(startedAt);

    try {
      for (const task of RESEARCH_TASKS) {
        if (requestIdRef.current !== requestId || controller.signal.aborted) {
          return;
        }

        const taskStartedAt = Date.now();
        setPipelineRuns((current) =>
          current.map((run) =>
            run.taskId === task.id
              ? { ...run, phase: "submitted", startedAt: taskStartedAt }
              : run,
          ),
        );
        setRunState((current) =>
          current && current.ticker === submittedTicker
            ? {
                ...current,
                taskTitle: isZh ? task.titleZh : task.title,
                phase: "submitted",
              }
            : current,
        );

        const taskResult = await runResearchTask({
          taskId: task.id,
          requestId,
          submittedTicker,
          runtimeProviderKey,
          anonymousTrialMode: anonymousTrialAvailable,
          controller,
        });

        setPipelineRuns((current) =>
          current.map((run) =>
            run.taskId === task.id
              ? {
                  ...run,
                  phase: taskResult.phase,
                  completedAt: Date.now(),
                }
              : run,
          ),
        );
        if (taskResult.phase === "failed") {
          setRunState((current) =>
            current && current.ticker === submittedTicker
              ? { ...current, phase: "failed" }
              : current,
          );
          setError(
            taskResult.error ?? {
              message: "Research agent failed before producing a final report.",
              source: "python-research-service",
              code: "RESEARCH_AGENT_DEGRADED",
              degraded: true,
            },
          );
          break;
        }
      }
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      console.error("Fetch Error:", error);
      setRunState((current) =>
        current && current.ticker === submittedTicker
          ? { ...current, phase: "failed" }
          : current,
      );
      setError(normalizeAnalysisError(error));
    } finally {
      if (requestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  };

  const runResearchTask = async ({
    taskId,
    requestId,
    submittedTicker,
    runtimeProviderKey,
    anonymousTrialMode,
    controller,
  }: {
    taskId: ResearchTaskId;
    requestId: number;
    submittedTicker: string;
    runtimeProviderKey: string;
    anonymousTrialMode: boolean;
    controller: AbortController;
  }): Promise<{ phase: "received" | "failed"; error?: AnalysisErrorState }> => {
    console.log(
      `Fetching ${taskId} analysis for ${submittedTicker} using ${model} in ${lang}...`,
    );
    const analysisParams = new URLSearchParams({
      lang,
      model,
      taskType: taskId,
    });
    const requestHeaders: Record<string, string> = {};
    if (runtimeProviderKey) {
      requestHeaders["X-Provider-API-Key"] = runtimeProviderKey;
    }

    const response = await fetch(
      `${analysisApiBase}/sec/analyze/${submittedTicker}?${analysisParams.toString()}`,
      {
        headers: requestHeaders,
        signal: controller.signal,
      },
    );
    console.log("Response status:", response.status);

    if (!response.ok || !response.body) {
      const errorText = await response.text();
      throw analysisErrorFromResponseText(errorText, response.statusText);
    }

    setRunState((current) =>
      current && current.ticker === submittedTicker
        ? { ...current, phase: "streaming" }
        : current,
    );
    setPipelineRuns((current) =>
      current.map((run) =>
        run.taskId === taskId ? { ...run, phase: "streaming" } : run,
      ),
    );

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk;

      const lines = buffer.split("\n");

      for (let i = 0; i < lines.length - 1; i++) {
        const line = lines[i].trim();
        if (line.startsWith("data:")) {
          const jsonStr = line.substring(5).trim();
          try {
            const reportData = JSON.parse(jsonStr) as Partial<AnalysisReport>;
            if (requestIdRef.current !== requestId) {
              continue;
            }
            if (
              anonymousTrialMode &&
              !anonymousTrialConsumedRef.current &&
              taskId === "latest_earnings_readout"
            ) {
              anonymousTrialConsumedRef.current = true;
              window.localStorage.setItem(ANONYMOUS_TRIAL_STORAGE_KEY, "true");
              setTrialStatus("trial_exhausted");
            }
            setRunState((current) =>
              current && current.ticker === submittedTicker
                ? { ...current, phase: "received" }
                : current,
            );
            setReportsByTask((current) => ({
              ...current,
              [taskId]: mergeReportChunks(current[taskId], reportData),
            }));
            console.log("Received progressive report chunk");
          } catch (e) {
            console.warn("JSON parse error:", e);
          }
        }
      }

      buffer = lines[lines.length - 1];
    }
    return { phase: "received" };
  };

  useEffect(() => {
    return () => {
      analysisAbortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    if (!isLoading || !runState) {
      return;
    }
    const timer = window.setInterval(() => {
      setRunNow(Date.now());
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isLoading, runState]);

  const saveProviderKey = () => {
    const trimmedKey = providerApiKey.trim();
    if (!trimmedKey) {
      setProviderKeySaved(false);
      setError({
        message: isZh
          ? `请输入有效的 ${selectedProvider.name} API Key。`
          : `Please enter a valid ${selectedProvider.name} API key.`,
      });
      return;
    }
    window.localStorage.setItem(selectedProvider.storageKey, trimmedKey);
    setProviderApiKey("");
    setProviderKeySaved(true);
    setError(null);
  };

  const clearProviderKey = () => {
    window.localStorage.removeItem(selectedProvider.storageKey);
    setProviderApiKey("");
    setProviderKeySaved(false);
    setError({
      message: isZh
        ? `已清除 ${selectedProvider.name} Key，请重新输入。`
        : `${selectedProvider.name} key cleared. Enter a new key to continue.`,
    });
  };

  useEffect(() => {
    if (scrollRef.current) {
      const scrollElement = scrollRef.current.querySelector(
        "[data-radix-scroll-area-viewport]",
      );
      if (scrollElement) {
        scrollElement.scrollTop = scrollElement.scrollHeight;
      }
    }
  }, [reportsByTask]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-8 font-mono">
      <div className="max-w-6xl mx-auto space-y-6">
        {/* Header */}
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold flex items-center gap-2 text-emerald-400">
            <TrendingUp className="w-8 h-8" />
            {isZh ? "AI 财报分析师" : "AI Earnings Analyst"}{" "}
            <span className="text-xs bg-slate-800 px-2 py-1 rounded text-slate-400">
              v2.0
            </span>
          </h1>
        </div>

        {/* Search Bar */}
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-4 space-y-3">
            <AuthBanner />
            {/* Row 1: Ticker, Language, Button */}
            <div className="flex gap-2">
              <div className="relative flex-1">
                <TickerSearchInput
                  value={ticker}
                  onValueChange={(nextTicker) => {
                    setTicker(nextTicker.toUpperCase());
                    setTickerSuggestionsOpen(true);
                  }}
                  onSubmit={(submittedTicker) => void handleSearch(submittedTicker)}
                  placeholder={
                    isZh
                      ? "输入股票代码 (如 AAPL, MSFT)"
                      : "Enter Ticker (e.g., AAPL, MSFT, TSLA)"
                  }
                  buttonLabel={isZh ? "开始分析" : "Analyze ticker"}
                  isSubmitting={isLoading}
                  inputRef={tickerInputRef}
                  inputProps={{
                    role: "combobox",
                    autoComplete: "off",
                    "aria-expanded":
                      tickerSuggestionsOpen && tickerSuggestions.length > 0,
                    "aria-controls": "ticker-suggestion-list",
                    onFocus: () => setTickerSuggestionsOpen(true),
                    onBlur: () => {
                      window.setTimeout(() => setTickerSuggestionsOpen(false), 120);
                    },
                  }}
                />
                {tickerSuggestionsOpen && tickerSuggestions.length > 0 && (
                  <div
                    id="ticker-suggestion-list"
                    role="listbox"
                    className="absolute left-0 right-0 top-[calc(100%+8px)] z-30 overflow-hidden rounded-lg border border-emerald-500/30 bg-slate-900 shadow-2xl shadow-slate-950/60"
                  >
                    {tickerSuggestions.map((suggestion) => (
                      <button
                        key={suggestion.ticker}
                        type="button"
                        role="option"
                        aria-label={`${suggestion.ticker} ${suggestion.companyName}`}
                        aria-selected={ticker === suggestion.ticker}
                        onMouseDown={(event) => event.preventDefault()}
                        onClick={() => selectTickerSuggestion(suggestion)}
                        className="flex w-full flex-col items-start gap-1 border-b border-slate-800 px-4 py-3 text-left last:border-b-0 hover:bg-emerald-950/30 focus:bg-emerald-950/30 focus:outline-none"
                      >
                        <span className="text-sm font-bold tracking-widest text-emerald-300">
                          {suggestion.ticker}
                        </span>
                        <span className="text-sm text-slate-400">
                          {suggestion.companyName}
                        </span>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              <select
                value={lang}
                onChange={(e) => setLang(e.target.value)}
                className="bg-slate-950 border border-slate-700 text-emerald-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-600 font-mono text-sm"
              >
                <option value="en">🇺🇸 EN</option>
                <option value="zh">🇨🇳 CN</option>
              </select>
            </div>

            {/* Row 3: BYOK Provider Selector */}
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-slate-500" />
              <span className="text-xs text-slate-500">
                {isZh ? "BYOK Provider:" : "BYOK Provider:"}
              </span>
              <div className="flex gap-2 flex-1">
                {BYOK_PROVIDERS.map((provider) => (
                  <button
                    key={provider.id}
                    onClick={() => setModel(provider.id)}
                    className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      model === provider.id
                        ? "bg-emerald-600 text-white"
                        : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                    }`}
                    title={isZh ? provider.descZh : provider.description}
                  >
                    <span className="inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full bg-slate-950 px-1 text-[10px] font-semibold text-emerald-300 ring-1 ring-emerald-500/30">
                      {provider.badge}
                    </span>
                    <span>{provider.name}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="rounded-md border border-emerald-500/20 bg-emerald-950/10 p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-emerald-300">
                    {selectedProvider.keyLabel}
                  </p>
                  <p className="text-xs text-slate-400">
                    {isZh
                      ? `仅保存在当前浏览器本地，请求 ${selectedProvider.name} 时透传到后端。`
                      : `Stored only in this browser and forwarded to the backend for ${selectedProvider.name} requests.`}
                  </p>
                </div>
                <span
                  className={`text-xs font-medium ${providerKeySaved ? "text-emerald-400" : "text-amber-400"}`}
                >
                  {providerKeySaved
                    ? isZh
                      ? "已保存"
                      : "Saved"
                    : isZh
                      ? "未保存"
                      : "Not saved"}
                </span>
              </div>
              <div className="flex gap-2">
                <Input
                  type="password"
                  value={providerApiKey}
                  onChange={(e) => {
                    setProviderApiKey(e.target.value);
                    setProviderKeySaved(false);
                  }}
                  placeholder={selectedProvider.keyPlaceholder}
                  className="bg-slate-950 border-slate-700 text-slate-200"
                />
                <Button
                  type="button"
                  onClick={saveProviderKey}
                  className="bg-emerald-600 hover:bg-emerald-700 text-white"
                >
                  {isZh ? "保存" : "Save"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={clearProviderKey}
                  className="border-slate-700 bg-slate-950 text-slate-300 hover:bg-slate-900"
                >
                  {isZh ? "清除" : "Clear"}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>

        <TrialGate status={trialGateStatus} />

        {/* Error Display */}
        {error && <AnalysisErrorPanel error={error} isZh={isZh} />}

        {isLoading && runState && (
          <AnalysisRunStatusPanel
            runState={runState}
            pipelineRuns={pipelineRuns}
            isZh={isZh}
            now={runNow}
          />
        )}

        <section
          id="pdf-report-root"
          className="grid gap-4 lg:grid-cols-[300px,minmax(0,1fr)]"
        >
          <AgentPipelinePanel
            runs={pipelineRuns}
            reportsByTask={reportsByTask}
            activeTaskId={activeReportTaskId}
            onSelectTask={setActiveReportTaskId}
            isZh={isZh}
            timelineMetadata={timelineMetadata}
            timelineTaskTitle={timelineTaskTitle}
          />

          <div className="min-w-0 space-y-6">
            {!activeReportEntry && (
              <MarketCandlestickPanel ticker={reportTitleTicker} lang={lang} />
            )}

            {activeReportEntry && (
              <div className="space-y-6">
            <div className="flex items-center justify-between">
              <div id="pdf-report-header" className="space-y-1">
                <h2 className="text-lg font-bold text-emerald-400 flex items-center gap-2">
                  📊{" "}
                  {isZh
                    ? `${reportTitleTicker} 分析报告`
                    : `${reportTitleTicker} Analysis Report`}
                </h2>
                {(reportCompanyName || reportPeriod) && (
                  <p className="text-sm text-slate-400">
                    {reportCompanyName || reportTitleTicker}
                    {displayPeriod ? ` · ${displayPeriod}` : ""}
                    {reportFilingDate ? ` · ${reportFilingDate}` : ""}
                  </p>
                )}
                <p className="text-xs uppercase tracking-widest text-slate-500">
                  {isZh ? "三段 Agent 研究流水线" : "Three-agent research pipeline"}
                </p>
              </div>
              {primaryReport && (
                <div data-pdf-exclude="true">
                  <PdfDownloadButton
                    report={activeReportEntry.report}
                    ticker={reportTitleTicker}
                    lang={lang}
                  />
                </div>
              )}
            </div>

              <AgentReportPanel
                key={activeReportEntry.task.id}
                task={activeReportEntry.task}
                report={activeReportEntry.report}
                lang={lang}
              />
              </div>
            )}
          </div>
        </section>

        <section
          aria-labelledby="experiment-lab-title"
          className="space-y-3 border-t border-slate-800 pt-6"
        >
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-widest text-slate-500">
                {isZh ? "开发者诊断" : "Developer diagnostics"}
              </p>
              <h2
                id="experiment-lab-title"
                className="text-lg font-semibold text-slate-200"
              >
                {isZh ? "质量门禁与 RAG 评估" : "Quality gates and RAG evals"}
              </h2>
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={() => setDiagnosticsOpen((open) => !open)}
              className="border-slate-700 bg-slate-950 text-slate-300 hover:bg-slate-900"
            >
              {diagnosticsOpen
                ? isZh
                  ? "隐藏诊断"
                  : "Hide diagnostics"
                : isZh
                  ? "开发者诊断"
                  : "Developer diagnostics"}
            </Button>
          </div>
          {diagnosticsOpen && (
            <p className="text-xs uppercase tracking-widest text-slate-500">
              {isZh ? "内部验证信息" : "Internal validation artifacts"}
            </p>
          )}
          {diagnosticsOpen && (
            <RagEvalDashboard reports={orderedReports.map(({ report }) => report)} />
          )}
        </section>
      </div>
    </div>
  );
}

interface LatestEarningsReportSectionsProps {
  report: AnalysisReport;
  lang: string;
}

function AnalysisRunStatusPanel({
  runState,
  pipelineRuns,
  isZh,
  now,
}: {
  runState: AnalysisRunState;
  pipelineRuns: AgentPipelineRun[];
  isZh: boolean;
  now: number;
}) {
  const elapsedSeconds = Math.max(
    0,
    Math.round((now - runState.startedAt) / 1000),
  );
  const phaseCopy = analysisRunPhaseCopy(runState.phase, isZh);

  return (
    <Card
      role="status"
      aria-live="polite"
      className="border-emerald-500/30 bg-slate-900/80"
    >
      <CardContent className="space-y-4 p-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-emerald-400/30 bg-emerald-400/10 text-emerald-300">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1 space-y-3">
            <div className="space-y-1">
              <p className="text-sm font-semibold text-emerald-200">
                {isZh ? "真实 Agent 运行中" : "Live agent run in progress"}
              </p>
              <p className="text-sm leading-relaxed text-slate-300">
                {phaseCopy.detail}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
              <RunStatusMetric label="Ticker" value={runState.ticker} />
              <RunStatusMetric
                label={isZh ? "任务" : "Task"}
                value={runState.taskTitle}
              />
              <RunStatusMetric label="Provider" value={runState.providerName} />
              <RunStatusMetric
                label={isZh ? "耗时" : "Elapsed"}
                value={`${elapsedSeconds}s`}
              />
            </div>

            <div className="flex flex-wrap gap-2 text-xs">
              <span className="rounded border border-emerald-400/30 bg-emerald-400/10 px-2 py-1 font-medium text-emerald-200">
                {phaseCopy.label}
              </span>
              <span className="rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-slate-400">
                {isZh
                  ? "正在使用真实后端、SEC filing、Research Service 与 BYOK provider"
                  : "Using the real backend, SEC filing, Research Service, and BYOK provider"}
              </span>
            </div>
            {pipelineRuns.length > 0 && (
              <div className="grid gap-2 md:grid-cols-3">
                {pipelineRuns.map((run) => (
                  <div
                    key={run.taskId}
                    className="rounded border border-slate-800 bg-slate-950/60 px-3 py-2"
                  >
                    <p className="truncate text-xs font-medium text-slate-300">
                      {run.taskTitle}
                    </p>
                    <p className="mt-1 text-[10px] uppercase tracking-widest text-slate-500">
                      {agentPipelinePhaseLabel(run.phase, isZh)}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function RunStatusMetric({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/70 px-3 py-2">
      <p className="text-[10px] uppercase tracking-widest text-slate-500">
        {label}
      </p>
      <p className="truncate text-sm font-semibold text-slate-200" title={value}>
        {value}
      </p>
    </div>
  );
}

function buildTimelineMetadata(
  orderedReports: Array<{
    task: (typeof RESEARCH_TASKS)[number];
    report: AnalysisReport;
  }>,
  activeReportEntry:
    | {
        task: (typeof RESEARCH_TASKS)[number];
        report: AnalysisReport;
      }
    | null,
): AnalysisMetadata | undefined {
  if (activeReportEntry) return activeReportEntry.report.metadata;

  const agentEvents = orderedReports.flatMap(
    ({ report }) => report.metadata?.agentEvents ?? [],
  );
  if (agentEvents.length === 0) return undefined;

  const firstMetadata = orderedReports.find(
    ({ report }) => report.metadata,
  )?.report.metadata;
  return {
    modelName: firstMetadata?.modelName ?? "multiple agents",
    generatedAt: firstMetadata?.generatedAt ?? "",
    language: firstMetadata?.language ?? "en",
    agentEvents,
  };
}

function AgentPipelinePanel({
  runs,
  reportsByTask,
  activeTaskId,
  onSelectTask,
  isZh,
  timelineMetadata,
  timelineTaskTitle,
}: {
  runs: AgentPipelineRun[];
  reportsByTask: ReportsByTask;
  activeTaskId: ResearchTaskId | null;
  onSelectTask: (taskId: ResearchTaskId | null) => void;
  isZh: boolean;
  timelineMetadata?: AnalysisMetadata;
  timelineTaskTitle?: string;
}) {
  const activeRuns: AgentPipelineRun[] =
    runs.length > 0
      ? runs
      : RESEARCH_TASKS.map((task) => ({
          taskId: task.id,
          taskTitle: isZh ? task.titleZh : task.title,
          phase: reportsByTask[task.id] ? "received" : "pending",
        }));

  return (
    <aside className="space-y-3">
      <section
        aria-label={isZh ? "Agent 流水线" : "Agent pipeline"}
        className="rounded-md border border-slate-800 bg-slate-950/60 p-3"
      >
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <p className="text-xs uppercase tracking-widest text-slate-500">
              {isZh ? "Agent 流水线" : "Agent Pipeline"}
            </p>
            <p className="text-sm text-slate-300">
              {isZh
                ? "一次提交，三个研究 Agent 按顺序生成报告。"
                : "One submission runs all three research agents in order."}
            </p>
          </div>
        </div>
        <button
          type="button"
          role="tab"
          aria-selected={activeTaskId === null}
          onClick={() => onSelectTask(null)}
          className={cn(
            "mb-2 flex w-full items-center justify-between rounded-md border px-3 py-3 text-left transition-colors",
            activeTaskId === null
              ? "border-emerald-500/50 bg-emerald-950/30 text-emerald-200"
              : "border-slate-800 bg-slate-900/70 text-slate-300 hover:border-slate-700",
          )}
        >
          <span className="flex min-w-0 items-center gap-3">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-700 bg-slate-950">
              <TrendingUp className="h-4 w-4" />
            </span>
            <span className="min-w-0">
              <span className="block text-sm font-semibold">
                {isZh ? "行情图" : "Market Chart"}
              </span>
              <span className="block text-xs text-slate-500">
                {isZh ? "默认视图" : "Default view"}
              </span>
            </span>
          </span>
        </button>
        <div
          className="grid gap-2"
          role="tablist"
          aria-label={isZh ? "Agent 报告" : "Agent reports"}
        >
          {activeRuns.map((run, index) => {
            const task = RESEARCH_TASKS.find((item) => item.id === run.taskId);
            const Icon = task?.Icon ?? Bot;
            const phase =
              run.phase === "failed"
                ? "failed"
                : reportsByTask[run.taskId]
                  ? "received"
                  : run.phase;
            const selected = activeTaskId === run.taskId;
            return (
              <button
                type="button"
                role="tab"
                aria-selected={selected}
                key={run.taskId}
                onClick={() => onSelectTask(run.taskId)}
                className={cn(
                  "min-h-[86px] rounded-md border p-3 text-left transition-colors",
                  selected
                    ? "border-emerald-500/60 bg-emerald-950/30"
                    : phase === "received"
                      ? "border-emerald-500/40 bg-emerald-950/20"
                      : phase === "streaming" || phase === "submitted"
                        ? "border-amber-400/40 bg-amber-950/10"
                        : phase === "failed"
                          ? "border-red-500/40 bg-red-950/10"
                          : "border-slate-800 bg-slate-900/70",
                )}
              >
                <div className="flex items-start gap-3">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-slate-700 bg-slate-950 text-slate-300">
                    <Icon className="h-4 w-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] uppercase tracking-widest text-slate-500">
                      {isZh ? `第 ${index + 1} 步` : `Step ${index + 1}`}
                    </p>
                    <p className="mt-1 text-sm font-semibold leading-tight text-slate-100">
                      {run.taskTitle}
                    </p>
                    <p
                      className={cn(
                        "mt-2 text-xs font-medium",
                        phase === "received"
                          ? "text-emerald-300"
                          : phase === "streaming" || phase === "submitted"
                            ? "text-amber-300"
                            : phase === "failed"
                              ? "text-red-300"
                              : "text-slate-500",
                      )}
                    >
                      {agentPipelinePhaseLabel(phase, isZh)}
                    </p>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </section>
      <AgentMessagesTimeline
        metadata={timelineMetadata}
        taskTitle={timelineTaskTitle}
        isZh={isZh}
      />
    </aside>
  );
}

function agentPipelinePhaseLabel(
  phase: AgentPipelineRun["phase"],
  isZh: boolean,
) {
  if (phase === "received") return isZh ? "已完成" : "completed";
  if (phase === "streaming") return isZh ? "生成中" : "generating";
  if (phase === "submitted") return isZh ? "已提交" : "submitted";
  if (phase === "failed") return isZh ? "失败" : "failed";
  return isZh ? "等待中" : "pending";
}

function AgentMessagesTimeline({
  metadata,
  taskTitle,
  isZh,
}: {
  metadata?: AnalysisMetadata;
  taskTitle?: string;
  isZh: boolean;
}) {
  const events = metadata?.agentEvents?.filter((event) => event.summary) ?? [];

  return (
    <section
      aria-label={isZh ? "Agent 消息和工具" : "Messages and tools"}
      className="rounded-md border border-emerald-500/20 bg-[#111716] p-4 shadow-xl shadow-slate-950/30"
    >
      <div className="flex items-center gap-2 border-b border-emerald-500/25 pb-4">
        <MessageSquareText className="h-4 w-4 text-emerald-300" />
        <div>
          <p className="text-lg font-bold text-emerald-300">
            {isZh ? "Messages & Tools" : "Messages & Tools"}
          </p>
          {taskTitle && (
            <p className="mt-1 text-xs uppercase tracking-widest text-slate-500">
              {taskTitle}
            </p>
          )}
        </div>
      </div>

      {events.length === 0 ? (
        <div className="py-6 text-sm leading-6 text-slate-500">
          {isZh
            ? "运行完成后，这里会展示 reasoning 与 tool 调用时间线。"
            : "Reasoning and tool-call timeline appears here after an agent finishes."}
        </div>
      ) : (
        <div className="max-h-[640px] overflow-y-auto pr-1">
          {events.map((event, index) => {
            const kind = event.eventKind ?? (event.toolName ? "tool" : "reasoning");
            const isTool = kind === "tool" || Boolean(event.toolName);
            const elapsedMs = cumulativeEventLatency(events, index);
            const agentName =
              event.agentName || agentNameFromTaskTitle(taskTitle, isZh);
            const detail = isTool
              ? toolEventDetail(event)
              : reasoningEventDetail(event);
            return (
              <article
                key={`${event.phase}-${event.toolName ?? kind}-${index}`}
                className="border-b border-emerald-500/15 py-4 last:border-b-0"
              >
                <div className="mb-3 flex items-center justify-between gap-3">
                  <span className="font-mono text-xl font-bold text-emerald-300 tabular-nums">
                    {formatTimelineTime(elapsedMs)}
                  </span>
                  <span
                    className={cn(
                      "inline-flex min-h-8 items-center gap-1 rounded-md px-3 text-sm font-semibold",
                      isTool
                        ? "bg-yellow-400/15 text-yellow-300"
                        : event.status === "degraded" || event.degradedReason
                          ? "bg-red-500/15 text-red-300"
                          : "bg-emerald-400/15 text-emerald-300",
                    )}
                  >
                    {isTool ? (
                      <Wrench className="h-3.5 w-3.5" />
                    ) : (
                      <Bot className="h-3.5 w-3.5" />
                    )}
                    {isTool ? "Tool" : "Reasoning"}
                  </span>
                </div>
                <p className="text-sm font-semibold text-slate-400">
                  {agentName}
                </p>
                <p className="mt-2 break-words font-mono text-sm leading-6 text-slate-100">
                  {detail}
                </p>
                {event.degradedReason && (
                  <p className="mt-2 rounded border border-red-500/30 bg-red-950/20 px-2 py-1 text-xs leading-5 text-red-200">
                    {event.degradedReason}
                  </p>
                )}
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}

function cumulativeEventLatency(
  events: NonNullable<AnalysisMetadata["agentEvents"]>,
  index: number,
) {
  return events
    .slice(0, index + 1)
    .reduce((total, event) => total + Math.max(0, event.latencyMs ?? 0), 0);
}

function formatTimelineTime(milliseconds: number) {
  const seconds = Math.max(0, Math.round(milliseconds / 1000));
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainingSeconds).padStart(2, "0")}`;
}

function reasoningEventDetail(event: NonNullable<AnalysisMetadata["agentEvents"]>[number]) {
  const model = event.modelName || "provider model";
  const usage = event.usage ?? {};
  const inputTokens = numberFromUnknown(
    usage.prompt_tokens ?? usage.input_tokens ?? usage.total_prompt_tokens,
  );
  const outputTokens = numberFromUnknown(
    usage.completion_tokens ?? usage.output_tokens ?? usage.total_completion_tokens,
  );
  if (inputTokens !== null || outputTokens !== null) {
    return `${model}: ${inputTokens ?? "?"} in, ${outputTokens ?? "?"} out`;
  }
  return `${model}: ${event.summary}`;
}

function toolEventDetail(event: NonNullable<AnalysisMetadata["agentEvents"]>[number]) {
  const toolName = event.toolName || event.phase || "tool";
  const input = event.toolInput && Object.keys(event.toolInput).length > 0
    ? `: ${JSON.stringify(event.toolInput)}`
    : event.summary
      ? `: ${event.summary}`
      : "";
  return `${toolName}${input}`;
}

function numberFromUnknown(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function agentNameFromTaskTitle(taskTitle: string | undefined, isZh: boolean) {
  if (!taskTitle) return isZh ? "研究 Agent" : "Research Agent";
  if (/cash/i.test(taskTitle) || taskTitle.includes("现金")) {
    return isZh ? "现金流分析师" : "Cash Flow Analyst";
  }
  if (/business/i.test(taskTitle) || taskTitle.includes("业务")) {
    return isZh ? "业务分析师" : "Business Analyst";
  }
  return isZh ? "财报分析师" : "Earnings Analyst";
}

function MarketCandlestickPanel({
  ticker,
  lang,
}: {
  ticker: string;
  lang: string;
}) {
  const isZh = lang === "zh";
  const normalizedTicker = ticker.trim().toUpperCase();
  const [candles, setCandles] = useState<MarketCandle[]>([]);
  const [loading, setLoading] = useState(false);
  const [hoveredCandle, setHoveredCandle] = useState<MarketChartHover | null>(
    null,
  );
  const [interval, setInterval] = useState<MarketChartInterval>("1d");

  useEffect(() => {
    const normalizedTicker = ticker.trim().toUpperCase();
    if (!normalizedTicker) {
      return;
    }

    const controller = new AbortController();
    void Promise.resolve().then(async () => {
      setLoading(true);
      const request = fetch(
        `/api/market/chart/${encodeURIComponent(normalizedTicker)}?interval=${interval}`,
        {
          signal: controller.signal,
        },
      );
      if (!request || typeof request.then !== "function") {
        setCandles([]);
        setLoading(false);
        return;
      }

      try {
        const response = await request;
        if (!response.ok) {
          setCandles([]);
          return;
        }
        const payload = (await response.json()) as { candles?: MarketCandle[] };
        setCandles(payload.candles ?? []);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setCandles([]);
      } finally {
        setLoading(false);
      }
    });

    return () => controller.abort();
  }, [ticker, interval]);

  useEffect(() => {
    setHoveredCandle(null);
  }, [ticker, interval]);

  const lastCandle = candles[candles.length - 1] ?? null;
  const previousClose = candles[candles.length - 2]?.close ?? lastCandle?.open;
  const lastChangePercent =
    lastCandle && previousClose
      ? ((lastCandle.close - previousClose) / previousClose) * 100
      : 0;
  const activeStats =
    hoveredCandle ??
    (lastCandle
      ? {
          date: lastCandle.date,
          open: lastCandle.open,
          high: lastCandle.high,
          low: lastCandle.low,
          close: lastCandle.close,
          volume: lastCandle.volume,
          changePercent: lastChangePercent,
        }
      : null);
  const positiveMove = (activeStats?.changePercent ?? 0) >= 0;

  return (
    <Card className="min-h-[620px] overflow-hidden border-slate-800 bg-[#0b1118] shadow-2xl shadow-slate-950/40">
      <CardHeader className="border-b border-slate-800 bg-[#0d141c] px-4 py-3">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="min-w-0">
            <CardTitle className="flex items-center gap-2 text-emerald-400">
              <TrendingUp className="h-5 w-5" />
              {normalizedTicker
                ? isZh
                  ? `${normalizedTicker} K 线图`
                  : `${normalizedTicker} Market Chart`
                : isZh
                  ? "输入股票代码后查看 K 线图"
                  : "Enter a ticker to load the market chart"}
            </CardTitle>
            <p className="mt-1 text-xs text-slate-500">
              {isZh
                ? "滚轮缩放，拖拽平移，移动鼠标查看十字光标 OHLC。"
                : "Scroll to zoom, drag to pan, and move the cursor for crosshair OHLC."}
            </p>
          </div>
          {activeStats && (
            <div className="grid min-w-0 grid-cols-3 gap-2 text-xs md:grid-cols-6">
              <MarketStat label="O" value={formatPrice(activeStats.open)} />
              <MarketStat label="H" value={formatPrice(activeStats.high)} />
              <MarketStat label="L" value={formatPrice(activeStats.low)} />
              <MarketStat label="C" value={formatPrice(activeStats.close)} />
              <MarketStat
                label={isZh ? "涨跌" : "CHG"}
                value={`${positiveMove ? "+" : ""}${activeStats.changePercent.toFixed(2)}%`}
                tone={positiveMove ? "up" : "down"}
              />
              <MarketStat
                label="VOL"
                value={formatCompactNumber(activeStats.volume ?? 0)}
              />
            </div>
          )}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] uppercase tracking-widest text-slate-500">
          <div
            role="tablist"
            aria-label={isZh ? "K 线周期" : "Candlestick interval"}
            className="flex overflow-hidden rounded-md border border-slate-700 bg-slate-950"
          >
            {MARKET_CHART_INTERVALS.map((option) => {
              const selected = interval === option.id;
              return (
                <button
                  key={option.id}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  onClick={() => setInterval(option.id)}
                  className={cn(
                    "min-h-9 px-3 py-1 text-[11px] font-semibold uppercase tracking-widest transition-colors",
                    selected
                      ? "bg-emerald-500/15 text-emerald-300"
                      : "text-slate-500 hover:bg-slate-900 hover:text-slate-300",
                  )}
                >
                  {isZh ? option.labelZh : option.label}
                </button>
              );
            })}
          </div>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1">
            {isZh ? "全历史" : "ALL"}
          </span>
          <span className="rounded border border-emerald-500/30 bg-emerald-500/10 px-2 py-1 text-emerald-300">
            {isZh ? "十字光标" : "Crosshair"}
          </span>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1">
            {isZh ? "滚轮缩放" : "Scroll to zoom"}
          </span>
          <span className="rounded border border-slate-700 bg-slate-950 px-2 py-1">
            {isZh ? "拖拽平移" : "Drag to pan"}
          </span>
        </div>
      </CardHeader>
      <CardContent className="h-[520px] min-h-[520px] min-w-0 bg-[#070b11] p-0">
        {loading ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            {isZh ? "加载行情中..." : "Loading market chart..."}
          </div>
        ) : candles.length === 0 ? (
          <div className="flex h-full items-center justify-center text-sm text-slate-500">
            {normalizedTicker
              ? isZh
                ? "暂无可展示的行情 K 线。"
                : "No market candles available."
              : isZh
                ? "先输入股票代码，再查看行情与财报。"
                : "Enter a ticker above to load the market chart and reports."}
          </div>
        ) : (
          <TradingCandlestickChart
            candles={candles}
            interval={interval}
            onHoverCandle={setHoveredCandle}
          />
        )}
      </CardContent>
    </Card>
  );
}

function TradingCandlestickChart({
  candles,
  interval,
  onHoverCandle,
}: {
  candles: MarketCandle[];
  interval: MarketChartInterval;
  onHoverCandle: (candle: MarketChartHover | null) => void;
}) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const candlesByTime = useMemo(
    () => new Map(candles.map((candle) => [candle.date, candle])),
    [candles],
  );
  const defaultVisibleRange = useMemo(
    () => defaultVisibleLogicalRange(candles.length, interval),
    [candles.length, interval],
  );
  const defaultVisibleFrom =
    candles[Math.max(0, Math.floor(defaultVisibleRange.from))]?.date ?? "";
  const defaultVisibleTo =
    candles[Math.min(candles.length - 1, Math.floor(defaultVisibleRange.to))]
      ?.date ?? "";

  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      autoSize: true,
      height: 520,
      layout: {
        background: { type: ColorType.Solid, color: "#070b11" },
        textColor: "#8b98a5",
        fontFamily:
          "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: "rgba(51, 65, 85, 0.35)" },
        horzLines: { color: "rgba(51, 65, 85, 0.35)" },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "rgba(148, 163, 184, 0.55)",
          labelBackgroundColor: "#111827",
          style: LineStyle.Dashed,
          visible: true,
          labelVisible: true,
        },
        horzLine: {
          color: "rgba(148, 163, 184, 0.55)",
          labelBackgroundColor: "#111827",
          style: LineStyle.Dashed,
          visible: true,
          labelVisible: true,
        },
      },
      rightPriceScale: {
        borderColor: "#1e293b",
        scaleMargins: {
          top: 0.08,
          bottom: 0.22,
        },
      },
      timeScale: {
        borderColor: "#1e293b",
        barSpacing: 9,
        minBarSpacing: 3,
        rightOffset: 8,
        rightBarStaysOnScroll: true,
        timeVisible: false,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: false,
      },
      handleScale: {
        mouseWheel: true,
        pinch: true,
        axisPressedMouseMove: {
          time: true,
          price: true,
        },
        axisDoubleClickReset: true,
      },
      localization: {
        priceFormatter: (price: number) => formatPrice(price),
      },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#00c076",
      downColor: "#f84960",
      borderUpColor: "#00c076",
      borderDownColor: "#f84960",
      wickUpColor: "#00c076",
      wickDownColor: "#f84960",
      priceLineColor: "#38bdf8",
      priceLineWidth: 1,
    });
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "",
      base: 0,
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.78,
        bottom: 0,
      },
    });

    chart.subscribeCrosshairMove((param) => {
      const timeKey = String(param.time ?? "");
      const candle = candlesByTime.get(timeKey);
      if (!candle) {
        onHoverCandle(null);
        return;
      }
      const previousIndex = candles.findIndex((item) => item.date === timeKey) - 1;
      const previousClose = candles[previousIndex]?.close ?? candle.open;
      onHoverCandle({
        date: candle.date,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close,
        volume: candle.volume,
        changePercent:
          previousClose === 0
            ? 0
            : ((candle.close - previousClose) / previousClose) * 100,
      });
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    return () => {
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [candles, candlesByTime, onHoverCandle]);

  useEffect(() => {
    if (!candleSeriesRef.current || !volumeSeriesRef.current || !chartRef.current) {
      return;
    }

    const candleData: CandlestickData<Time>[] = candles.map((candle) => ({
      time: candle.date,
      open: candle.open,
      high: candle.high,
      low: candle.low,
      close: candle.close,
    }));
    const volumeData: HistogramData<Time>[] = candles.map((candle) => ({
      time: candle.date,
      value: candle.volume ?? 0,
      color:
        candle.close >= candle.open
          ? "rgba(0, 192, 118, 0.35)"
          : "rgba(248, 73, 96, 0.35)",
    }));

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);
    chartRef.current.timeScale().setVisibleLogicalRange(defaultVisibleRange);
  }, [candles, defaultVisibleRange, interval]);

  return (
    <div
      ref={chartContainerRef}
      data-testid="market-candlestick-chart"
      data-candle-count={candles.length}
      data-visible-from={defaultVisibleFrom}
      data-visible-to={defaultVisibleTo}
      data-interval={interval}
      className="h-full w-full cursor-crosshair touch-pan-x select-none"
      aria-label="Interactive candlestick chart with mouse wheel zoom and drag pan"
    />
  );
}

function defaultVisibleLogicalRange(
  candleCount: number,
  interval: MarketChartInterval,
) {
  const visibleBars = defaultVisibleBarsForInterval(interval);
  const lastIndex = Math.max(candleCount - 1, 0);
  const from = Math.max(0, lastIndex - visibleBars + 1);
  return {
    from,
    to: lastIndex + 6,
  };
}

function defaultVisibleBarsForInterval(interval: MarketChartInterval) {
  if (interval === "1d") return 120;
  if (interval === "1wk") return 104;
  if (interval === "1mo") return 120;
  return 60;
}

function MarketStat({
  label,
  value,
  tone = "neutral",
}: {
  label: string;
  value: string;
  tone?: "neutral" | "up" | "down";
}) {
  return (
    <div className="min-w-0 rounded border border-slate-800 bg-slate-950/70 px-2 py-1">
      <p className="text-[10px] uppercase tracking-widest text-slate-500">
        {label}
      </p>
      <p
        className={cn(
          "truncate text-sm font-semibold tabular-nums",
          tone === "up"
            ? "text-emerald-300"
            : tone === "down"
              ? "text-rose-300"
              : "text-slate-200",
        )}
      >
        {value}
      </p>
    </div>
  );
}

function formatPrice(value: number) {
  return `$${value.toLocaleString("en-US", {
    maximumFractionDigits: value >= 100 ? 2 : 4,
    minimumFractionDigits: 2,
  })}`;
}

function formatCompactNumber(value: number) {
  const absolute = Math.abs(value);
  if (absolute >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (absolute >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (absolute >= 1_000) return `${(value / 1_000).toFixed(2)}K`;
  return value.toLocaleString("en-US");
}

function AgentReportPanel({
  task,
  report,
  lang,
}: {
  task: (typeof RESEARCH_TASKS)[number];
  report: AnalysisReport;
  lang: string;
}) {
  const isZh = lang === "zh";
  const Icon = task.Icon;

  return (
    <section className="space-y-4">
      <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-md border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
          <Icon className="h-4 w-4" />
        </span>
        <div>
          <p className="text-xs uppercase tracking-widest text-slate-500">
            {isZh ? "Agent 报告" : "Agent Report"}
          </p>
          <h3 className="text-lg font-semibold text-emerald-300">
            {isZh ? task.titleZh : task.title}
          </h3>
        </div>
      </div>

      {task.id === "business_driver_deep_dive" ? (
        <BusinessDriverReportSections report={report} lang={lang} />
      ) : task.id === "cash_flow_capital_allocation" ? (
        <CashFlowReportSections report={report} lang={lang} />
      ) : (
        <LatestEarningsReportSections report={report} lang={lang} />
      )}

    </section>
  );
}

function analysisRunPhaseCopy(phase: AnalysisRunPhase, isZh: boolean) {
  if (phase === "submitted") {
    return {
      label: isZh ? "后端与 Agent 运行中" : "Backend and agent running",
      detail: isZh
        ? "前端已提交分析请求；后端正在拉取 filing、调用 Research Service，并等待 provider 返回报告。"
        : "The frontend submitted the request; the backend is fetching the filing, calling Research Service, and waiting for the provider-backed report.",
    };
  }
  if (phase === "streaming") {
    return {
      label: isZh ? "等待 Agent 输出" : "Waiting for agent output",
      detail: isZh
        ? "后端已接受请求，Research Service 正在检索证据、合成报告并返回 typed sections。"
        : "The backend accepted the request; Research Service is retrieving evidence, synthesizing the report, and returning typed sections.",
    };
  }
  if (phase === "received") {
    return {
      label: isZh ? "收到报告片段" : "Report chunk received",
      detail: isZh
        ? "已收到至少一个报告片段，前端正在渲染任务专属组件。"
        : "At least one report chunk arrived; the frontend is rendering the task-specific components.",
    };
  }
  return {
    label: isZh ? "运行失败" : "Run failed",
    detail: isZh
      ? "本次运行失败，错误原因会显示在上方错误卡片。"
      : "This run failed; the error card above shows the failure reason.",
  };
}

function LatestEarningsReportSections({
  report,
  lang,
}: LatestEarningsReportSectionsProps) {
  const typedSections =
    report.taskSections?.taskType === "latest_earnings_readout"
      ? resolveLatestEarningsSections(report.taskSections)
      : null;

  if (typedSections) {
    return <TypedLatestEarningsSections sections={typedSections} lang={lang} />;
  }

  return <MissingTaskSectionsCard lang={lang} taskTitle="Latest Earnings Readout" />;
}

function TypedLatestEarningsSections({
  sections,
  lang,
}: {
  sections: LatestEarningsSections;
  lang: string;
}) {
  const isZh = lang === "zh";
  const toplineVerdict = sections.toplineVerdict ?? {
    headline: isZh ? "财报观点待补充" : "Latest earnings thesis pending",
    verdict: "mixed" as const,
    summary: isZh
      ? "当前 typed contract 没有提供完整财报观点。"
      : "The typed contract did not provide a complete earnings thesis.",
  };

  return (
    <>
      <div
        id="pdf-section-summary-latest-earnings-readout"
        data-pdf-section="summary"
        className="space-y-6"
      >
        <ResearchViewCard
          lang={lang}
          title={isZh ? "财报速读视图" : "Earnings Readout View"}
          description={
            isZh
              ? "回答这次财报到底好不好、哪些指标最重要、发生了什么变化以及下一步该盯什么。"
              : "Answers whether the quarter was good, which KPIs matter, what changed, and what to watch next."
          }
          labels={[
            isZh ? "财报判断" : "Earnings Verdict",
            isZh ? "关键指标条" : "KPI Strip",
            isZh ? "发生了什么变化" : "What Changed",
            isZh ? "下一步观察" : "Watch Next",
          ]}
        />
        {sections.companyProfile && (
          <CompanyProfileCard profile={sections.companyProfile} lang={lang} />
        )}
        <AnalystVerdictCard
          eyebrow={isZh ? "财报判断" : "Earnings Verdict"}
          headline={toplineVerdict.headline}
          status={toplineVerdict.verdict}
          summary={toplineVerdict.summary}
        />
      </div>

      <MetricStripCard
        title={isZh ? "关键指标条" : "KPI Strip"}
        metrics={sections.financialDashboard?.metrics ?? []}
        emptyText={isZh ? "没有指标证据。" : "No KPI evidence provided."}
      />

      <PointListCard
        title={isZh ? "发生了什么变化" : "What Changed"}
        points={[
          ...(sections.keyTakeaways ?? []),
          ...(sections.driverSnapshot ?? []),
        ].slice(0, 5)}
        emptyText={isZh ? "没有变化要点。" : "No change points provided."}
      />
      <PointListCard
        title={isZh ? "下一步观察" : "Watch Next"}
        points={sections.riskSnapshot ?? []}
        emptyText={isZh ? "没有观察项。" : "No watch items provided."}
      />
    </>
  );
}

function CompanyProfileCard({
  profile,
  lang,
}: {
  profile: CompanyProfileSection;
  lang: string;
}) {
  return (
    <Card
      aria-labelledby="company-profile-title"
      className="bg-slate-900 border-slate-800"
    >
      <CardHeader className="border-b border-slate-800">
        <CardTitle id="company-profile-title" className="text-emerald-400">
          {lang === "zh" ? "公司画像" : "Company Profile"}
        </CardTitle>
      </CardHeader>
      <CardContent className="p-6">
        <p className="max-w-5xl text-sm leading-7 text-slate-300">
          {profile.summary}
        </p>
      </CardContent>
    </Card>
  );
}

function BusinessDriverReportSections({
  report,
  lang,
}: {
  report: AnalysisReport;
  lang: string;
}) {
  const typedSections =
    report.taskSections?.taskType === "business_driver_deep_dive"
      ? resolveBusinessDriverSections(report.taskSections)
      : null;

  if (typedSections) {
    return <TypedBusinessDriverSections sections={typedSections} lang={lang} />;
  }

  return <MissingTaskSectionsCard lang={lang} taskTitle="Business Driver Deep Dive" />;
}

function CashFlowReportSections({
  report,
  lang,
}: {
  report: AnalysisReport;
  lang: string;
}) {
  const typedSections =
    report.taskSections?.taskType === "cash_flow_capital_allocation"
      ? resolveCashFlowSections(report.taskSections)
      : null;

  if (typedSections) {
    return <TypedCashFlowSections sections={typedSections} lang={lang} />;
  }

  return (
    <MissingTaskSectionsCard
      lang={lang}
      taskTitle="Cash Flow & Capital Allocation"
    />
  );
}

function TypedBusinessDriverSections({
  sections,
  lang,
}: {
  sections: BusinessDriverSections;
  lang: string;
}) {
  const isZh = lang === "zh";
  const driverMap = sections.driverMap ?? emptyDriverMap();
  const driverThesis = sections.driverThesis ?? {
    headline: isZh ? "业务驱动待补充" : "Business driver thesis pending",
    durability: "unclear" as const,
    summary: isZh
      ? "当前 typed contract 没有提供完整驱动论点。"
      : "The typed contract did not provide a complete driver thesis.",
  };
  const driverGroups = [
    { label: isZh ? "产品" : "Product", items: driverMap.product },
    { label: isZh ? "分部" : "Segment", items: driverMap.segment },
    { label: isZh ? "地区" : "Geography", items: driverMap.geography },
    { label: isZh ? "需求" : "Demand", items: driverMap.demand },
    { label: isZh ? "定价" : "Pricing", items: driverMap.pricing },
    { label: isZh ? "客户" : "Customer", items: driverMap.customer },
    { label: isZh ? "战略" : "Strategy", items: driverMap.strategy },
  ];

  return (
    <>
      <div
        id="pdf-section-summary-business-driver-deep-dive"
        data-pdf-section="summary"
        className="space-y-6"
      >
        <ResearchViewCard
          lang={lang}
          title={isZh ? "业务驱动研究视图" : "Business Driver Research View"}
          description={
            isZh
              ? "回答增长由什么驱动、强度如何、能否持续，以及哪些信号支持或反驳。"
              : "Answers what drives the business, how strong it is, whether it is durable, and which signals support or challenge it."
          }
          labels={[
            isZh ? "论点" : "Thesis",
            isZh ? "驱动地图" : "Driver Map",
            isZh ? "影响表" : "Impact Table",
            isZh ? "信号" : "Signals",
          ]}
        />
        <AnalystVerdictCard
          eyebrow={isZh ? "论点" : "Thesis"}
          headline={driverThesis.headline}
          status={driverThesis.durability}
          summary={driverThesis.summary}
        />
      </div>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="border-b border-slate-800">
          <CardTitle className="text-emerald-400">
            {isZh ? "驱动因素地图" : "Driver Map"}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 p-6 md:grid-cols-2">
          {driverGroups.map((group) => (
            <div
              key={group.label}
              className="rounded-md border border-slate-800 bg-slate-950/60 p-4"
            >
              <p className="text-sm font-semibold text-slate-200">
                {group.label}
              </p>
              <div className="mt-3 space-y-3">
                {group.items.length > 0 ? (
                  group.items.map((item, index) => (
                    <EvidencePointBlock
                      key={`${item.title}-${index}`}
                      point={item}
                    />
                  ))
                ) : (
                  <p className="text-sm text-slate-500">
                    {isZh ? "没有该维度证据。" : "No evidence for this lens."}
                  </p>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <ImpactTableCard groups={driverGroups} lang={lang} />

      <PointListCard
        title={isZh ? "信号" : "Signals"}
        points={[
          ...(sections.positiveSignals ?? []),
          ...(sections.negativeSignals ?? []),
        ]}
        emptyText={isZh ? "没有信号。" : "No signals provided."}
      />
      <WatchlistCard items={sections.watchlist ?? []} lang={lang} />
    </>
  );
}

function TypedCashFlowSections({
  sections,
  lang,
}: {
  sections: CashFlowCapitalAllocationSections;
  lang: string;
}) {
  const isZh = lang === "zh";
  const capitalAllocation = sections.capitalAllocation ?? {
    capex: [],
    buybacks: [],
    dividends: [],
    debt: [],
    liquidity: [],
  };
  const cashQualityVerdict = sections.cashQualityVerdict ?? {
    headline: isZh ? "现金质量待补充" : "Cash quality verdict pending",
    earningsBackedByCash: "unclear" as const,
    summary: isZh
      ? "当前 typed contract 没有提供完整现金质量判断。"
      : "The typed contract did not provide a complete cash quality verdict.",
  };
  const allocationGroups = [
    { label: "Capex", items: capitalAllocation.capex },
    { label: "Buybacks", items: capitalAllocation.buybacks },
    { label: "Dividends", items: capitalAllocation.dividends },
    { label: "Debt", items: capitalAllocation.debt },
    { label: "Liquidity", items: capitalAllocation.liquidity },
  ];

  return (
    <>
      <div
        id="pdf-section-summary-cash-flow-capital-allocation"
        data-pdf-section="summary"
        className="space-y-6"
      >
        <ResearchViewCard
          lang={lang}
          title={isZh ? "资本配置视图" : "Capital Allocation View"}
          description={
            isZh
              ? "回答利润是否由现金支撑、现金流如何转化，以及管理层如何配置资本。"
              : "Answers whether earnings are backed by cash, how cash converts, and how management allocates capital."
          }
          labels={[
            isZh ? "现金质量" : "Cash Quality",
            isZh ? "现金流桥" : "Cash Flow Bridge",
            isZh ? "资本配置评分卡" : "Capital Allocation Scorecard",
          ]}
        />
        <AnalystVerdictCard
          eyebrow={isZh ? "现金质量" : "Cash Quality"}
          headline={cashQualityVerdict.headline}
          status={cashQualityVerdict.earningsBackedByCash}
          summary={cashQualityVerdict.summary}
        />
      </div>

      <MetricStripCard
        title={isZh ? "现金流桥" : "Cash Flow Bridge"}
        metrics={sections.cashMetrics ?? []}
        emptyText={isZh ? "没有现金流指标。" : "No cash flow metrics provided."}
      />

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="border-b border-slate-800">
          <CardTitle className="text-emerald-400">
            {isZh ? "资本配置评分卡" : "Capital Allocation Scorecard"}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 p-6 md:grid-cols-2">
          {allocationGroups.map((group) => (
            <div
              key={group.label}
              className="rounded-md border border-slate-800 bg-slate-950/60 p-4"
            >
              <p className="text-sm font-semibold text-slate-200">
                {group.label}
              </p>
              <div className="mt-3 space-y-3">
                {group.items.length > 0 ? (
                  group.items.map((item, index) => (
                    <EvidencePointBlock
                      key={`${item.title}-${index}`}
                      point={item}
                    />
                  ))
                ) : (
                  <p className="text-sm text-slate-500">
                    {isZh ? "没有该维度证据。" : "No evidence for this lens."}
                  </p>
                )}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      <PointListCard
        title={isZh ? "配置纪律" : "Allocation Discipline"}
        points={sections.allocationDiscipline ?? []}
        emptyText={
          isZh
            ? "没有配置纪律信号。"
            : "No allocation discipline points provided."
        }
      />
      <PointListCard
        title={isZh ? "风险信号" : "Red Flags"}
        points={sections.redFlags ?? []}
        emptyText={isZh ? "没有风险信号。" : "No red flags provided."}
      />
    </>
  );
}

function resolveBusinessDriverSections(
  taskSections: NonNullable<AnalysisReport["taskSections"]>,
): BusinessDriverSections | null {
  const envelope = taskSections as {
    businessDriver?: BusinessDriverSections | null;
  };
  if (envelope.businessDriver) {
    return withTaskSectionEnvelopeFields(
      envelope.businessDriver,
      taskSections,
      "business_driver_deep_dive",
    );
  }
  if ("driverThesis" in taskSections || "driverMap" in taskSections) {
    return taskSections as BusinessDriverSections;
  }
  return null;
}

function resolveLatestEarningsSections(
  taskSections: NonNullable<AnalysisReport["taskSections"]>,
): LatestEarningsSections | null {
  const envelope = taskSections as {
    latestEarnings?: LatestEarningsSections | null;
  };
  if (envelope.latestEarnings) {
    return withTaskSectionEnvelopeFields(
      envelope.latestEarnings,
      taskSections,
      "latest_earnings_readout",
    );
  }
  if (
    "toplineVerdict" in taskSections ||
    "financialDashboard" in taskSections
  ) {
    return taskSections as LatestEarningsSections;
  }
  return null;
}

function resolveCashFlowSections(
  taskSections: NonNullable<AnalysisReport["taskSections"]>,
): CashFlowCapitalAllocationSections | null {
  const envelope = taskSections as {
    cashFlowCapitalAllocation?: CashFlowCapitalAllocationSections | null;
  };
  if (envelope.cashFlowCapitalAllocation) {
    return withTaskSectionEnvelopeFields(
      envelope.cashFlowCapitalAllocation,
      taskSections,
      "cash_flow_capital_allocation",
    );
  }
  if (
    "cashQualityVerdict" in taskSections ||
    "capitalAllocation" in taskSections
  ) {
    return taskSections as CashFlowCapitalAllocationSections;
  }
  return null;
}

function withTaskSectionEnvelopeFields<
  TSection extends
    | LatestEarningsSections
    | BusinessDriverSections
    | CashFlowCapitalAllocationSections,
>(
  section: TSection,
  envelope: NonNullable<AnalysisReport["taskSections"]>,
  taskType: TSection["taskType"],
): TSection {
  return {
    ...section,
    schemaVersion: section.schemaVersion ?? envelope.schemaVersion,
    taskType: section.taskType ?? taskType,
    coverage: section.coverage ?? envelope.coverage,
  };
}

function emptyDriverMap(): BusinessDriverSections["driverMap"] {
  return {
    product: [],
    segment: [],
    geography: [],
    demand: [],
    pricing: [],
    customer: [],
    strategy: [],
  };
}

function ResearchViewCard({
  lang,
  title,
  description,
  labels,
}: {
  lang: string;
  title: string;
  description: string;
  labels: string[];
}) {
  const isZh = lang === "zh";

  return (
    <Card className="mb-6 border-emerald-500/20 bg-slate-900/80">
      <CardContent className="p-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-widest text-slate-500">
              {isZh ? "当前研究视图" : "Research View"}
            </p>
            <h3 className="text-lg font-semibold text-emerald-300">{title}</h3>
            <p className="max-w-3xl text-sm leading-6 text-slate-400">
              {description}
            </p>
          </div>
          <div className="grid min-w-[260px] gap-2 text-sm text-slate-300">
            {labels.map((label) => (
              <div
                key={label}
                className="rounded-md border border-slate-800 bg-slate-950/70 px-3 py-2"
              >
                {label}
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function AnalystVerdictCard({
  eyebrow,
  headline,
  status,
  summary,
}: {
  eyebrow: string;
  headline: string;
  status: string;
  summary: string;
}) {
  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="border-b border-slate-800">
        <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
          <CardTitle className="text-emerald-400">{eyebrow}</CardTitle>
          <Badge className="w-fit border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
            {status}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="p-6">
        <p className="text-xl font-semibold leading-8 text-slate-100">
          {headline}
        </p>
        <p className="mt-3 text-sm leading-6 text-slate-400">{summary}</p>
      </CardContent>
    </Card>
  );
}

function MetricStripCard({
  title,
  metrics,
  emptyText,
}: {
  title: string;
  metrics: EvidenceBoundMetric[];
  emptyText: string;
}) {
  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="border-b border-slate-800">
        <CardTitle className="text-emerald-400">{title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-3 p-6 md:grid-cols-3">
        {metrics.length > 0 ? (
          metrics.map((metric) => (
            <EvidenceMetricBlock key={metric.name} metric={metric} />
          ))
        ) : (
          <p className="text-sm text-slate-500">{emptyText}</p>
        )}
      </CardContent>
    </Card>
  );
}

function EvidencePointBlock({ point }: { point: EvidenceBoundPoint }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-md border border-slate-800 bg-slate-950/60 p-3">
      <p className="min-w-0 [overflow-wrap:anywhere] font-semibold text-slate-200">
        {point.title}
      </p>
      <p className="mt-2 min-w-0 [overflow-wrap:anywhere] text-sm leading-6 text-slate-400">
        {point.summary}
      </p>
    </div>
  );
}

function ImpactTableCard({
  groups,
  lang,
}: {
  groups: { label: string; items: EvidenceBoundPoint[] }[];
  lang: string;
}) {
  const isZh = lang === "zh";
  const rows = groups.flatMap((group) =>
    group.items.map((item) => ({
      category: group.label,
      title: item.title,
      summary: item.summary,
    })),
  );

  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="border-b border-slate-800">
        <CardTitle className="text-emerald-400">
          {isZh ? "影响表" : "Impact Table"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-6">
        {rows.length > 0 ? (
          rows.slice(0, 8).map((row, index) => (
            <div
              key={`${row.category}-${row.title}-${index}`}
              className="grid min-w-0 gap-3 overflow-hidden rounded-md border border-slate-800 bg-slate-950/60 p-4 md:grid-cols-[140px,minmax(0,1fr)]"
            >
              <p className="min-w-0 [overflow-wrap:anywhere] text-sm font-semibold text-slate-200">
                {row.category}
              </p>
              <div className="min-w-0">
                <p className="min-w-0 [overflow-wrap:anywhere] text-sm font-semibold text-slate-100">
                  {row.title}
                </p>
                <p className="mt-1 min-w-0 [overflow-wrap:anywhere] text-sm leading-6 text-slate-400">
                  {row.summary}
                </p>
              </div>
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-500">
            {isZh ? "没有可评分的驱动项。" : "No driver impact items provided."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function EvidenceMetricBlock({ metric }: { metric: EvidenceBoundMetric }) {
  return (
    <div className="min-w-0 overflow-hidden rounded-md border border-slate-800 bg-slate-950/60 p-4">
      <p className="min-w-0 [overflow-wrap:anywhere] text-sm text-slate-400">
        {metric.name}
      </p>
      <p className="mt-1 min-w-0 [overflow-wrap:anywhere] text-xl font-semibold text-emerald-300">
        {formatMetricDisplayValue(metric.value)}
      </p>
      <p className="mt-3 min-w-0 [overflow-wrap:anywhere] text-sm leading-6 text-slate-400">
        {metric.interpretation}
      </p>
    </div>
  );
}

function formatMetricDisplayValue(value: unknown) {
  const rawValue = value === null || value === undefined ? "" : String(value);
  const trimmedValue = rawValue.trim();
  if (!trimmedValue) return rawValue;

  if (
    /[%]|(?:\b|[0-9])(k|m|b|t|million|billion|trillion)\b/i.test(trimmedValue)
  ) {
    return rawValue;
  }

  const numericMatch = trimmedValue.match(
    /^([$€£¥])?\s*(-?\d[\d,]*(?:\.\d+)?)\s*(USD|EUR|GBP|JPY|CNY)?$/i,
  );
  if (!numericMatch) return rawValue;

  const [, leadingCurrency, rawNumber, trailingCurrency] = numericMatch;
  const numericValue = Number(rawNumber.replace(/,/g, ""));
  if (!Number.isFinite(numericValue)) return rawValue;

  const absoluteValue = Math.abs(numericValue);
  const compactUnit =
    absoluteValue >= 1_000_000_000_000
      ? { divisor: 1_000_000_000_000, suffix: "T" }
      : absoluteValue >= 1_000_000_000
        ? { divisor: 1_000_000_000, suffix: "B" }
        : absoluteValue >= 1_000_000
          ? { divisor: 1_000_000, suffix: "M" }
          : absoluteValue >= 10_000
            ? { divisor: 1_000, suffix: "K" }
            : null;

  if (!compactUnit) return rawValue;

  const currencySymbol = leadingCurrency || currencyCodeToSymbol(trailingCurrency) || "$";
  const compactNumber = (numericValue / compactUnit.divisor)
    .toFixed(1)
    .replace(/\.0$/, "");

  return `${currencySymbol}${compactNumber}${compactUnit.suffix}`;
}

function currencyCodeToSymbol(currencyCode: string | undefined) {
  switch (currencyCode?.toUpperCase()) {
    case "USD":
      return "$";
    case "EUR":
      return "€";
    case "GBP":
      return "£";
    case "JPY":
    case "CNY":
      return "¥";
    default:
      return "";
  }
}

function PointListCard({
  title,
  points,
  emptyText,
}: {
  title: string;
  points: EvidenceBoundPoint[];
  emptyText: string;
}) {
  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="border-b border-slate-800">
        <CardTitle className="text-emerald-400">{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-6">
        {points.length > 0 ? (
          points.map((point, index) => (
            <EvidencePointBlock key={`${point.title}-${index}`} point={point} />
          ))
        ) : (
          <p className="text-sm text-slate-500">{emptyText}</p>
        )}
      </CardContent>
    </Card>
  );
}

function WatchlistCard({ items, lang }: { items: string[]; lang: string }) {
  const isZh = lang === "zh";

  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="border-b border-slate-800">
        <CardTitle className="text-emerald-400">
          {isZh ? "跟踪清单" : "Watchlist"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2 p-6">
        {items.length > 0 ? (
          items.map((item) => (
            <div
              key={item}
              className="rounded-md border border-slate-800 bg-slate-950/60 px-3 py-2 text-sm text-slate-300"
            >
              {item}
            </div>
          ))
        ) : (
          <p className="text-sm text-slate-500">
            {isZh ? "没有跟踪项。" : "No watch items provided."}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function MissingTaskSectionsCard({
  lang,
  taskTitle,
}: {
  lang: string;
  taskTitle: string;
}) {
  const isZh = lang === "zh";

  return (
    <Card className="border-amber-500/30 bg-slate-900">
      <CardHeader className="border-b border-slate-800">
        <CardTitle className="flex items-center gap-2 text-amber-300">
          <AlertTriangle className="h-5 w-5" />
          {isZh ? "缺少 typed taskSections" : "Missing typed taskSections"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-6">
        <p className="text-sm leading-6 text-slate-300">
          {isZh
            ? `当前 ${taskTitle} 报告没有返回任务专属 typed contract。前端已移除旧 dashboard 兜底，避免展示过期的 legacy 字段。`
            : `The ${taskTitle} report did not include its task-specific typed contract. The legacy dashboard fallback has been removed so stale legacy fields are not presented as a valid report.`}
        </p>
        <p className="text-xs uppercase tracking-widest text-slate-500">
          {isZh
            ? "请检查 Python Research Service final_report.task_sections。"
            : "Check Python Research Service final_report.task_sections."}
        </p>
      </CardContent>
    </Card>
  );
}

function analysisErrorFromResponseText(
  errorText: string,
  statusText: string,
): AnalysisErrorState {
  if (!errorText) {
    return { message: `Network response error: ${statusText}` };
  }
  const normalizedErrorText = stripSseDataPrefix(errorText);
  try {
    const parsed = JSON.parse(
      normalizedErrorText,
    ) as Partial<AnalysisErrorState> & {
      error?: string;
    };
    return {
      message: userFacingErrorMessage(
        parsed.error ||
          parsed.message ||
          `Network response error: ${statusText}`,
        parsed.code,
      ),
      code: parsed.code,
      source: parsed.source,
      degraded: parsed.degraded,
    };
  } catch {
    return { message: userFacingErrorMessage(normalizedErrorText) };
  }
}

function stripSseDataPrefix(errorText: string): string {
  const trimmed = errorText.trim();
  return trimmed.startsWith("data:") ? trimmed.slice(5).trim() : trimmed;
}

function userFacingErrorMessage(message: string, code?: string): string {
  const lowerMessage = message.toLowerCase();
  const isResearchServiceTimeout =
    code === "RESEARCH_SERVICE_UNAVAILABLE" &&
    (message.includes("Did not observe any item or terminal signal") ||
      message.includes("flatMap") ||
      lowerMessage.includes("timeout") ||
      lowerMessage.includes("timed out"));

  if (isResearchServiceTimeout) {
    return "The research agent took too long to finish. Please retry or choose a narrower task while we optimize live report generation.";
  }
  return message;
}

function normalizeAnalysisError(error: unknown): AnalysisErrorState {
  if (isAnalysisErrorState(error)) {
    return error;
  }
  return {
    message: error instanceof Error ? error.message : String(error),
  };
}

function isAnalysisErrorState(error: unknown): error is AnalysisErrorState {
  return (
    typeof error === "object" &&
    error !== null &&
    "message" in error &&
    typeof (error as AnalysisErrorState).message === "string"
  );
}

function AnalysisErrorPanel({
  error,
  isZh,
}: {
  error: AnalysisErrorState;
  isZh: boolean;
}) {
  const isResearchServiceUnavailable =
    error.code === "RESEARCH_SERVICE_UNAVAILABLE" ||
    error.source === "python-research-service";

  if (isResearchServiceUnavailable) {
    return (
      <Card
        role="alert"
        className="border-amber-500/40 bg-amber-950/20 text-amber-100"
      >
        <CardContent className="space-y-3 p-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-amber-400/30 bg-amber-400/10 text-amber-300">
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            </span>
            <div className="min-w-0 space-y-2">
              <div className="space-y-1">
                <p className="text-sm font-semibold text-amber-200">
                  {isZh
                    ? "Python Research Service 不可用"
                    : "Python Research Service unavailable"}
                </p>
                <p className="text-sm leading-relaxed text-amber-100/90">
                  {error.message}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs">
                <span className="rounded border border-amber-400/30 bg-amber-400/10 px-2 py-1 font-medium text-amber-200">
                  {isZh ? "Agent 降级" : "Agent degraded"}
                </span>
                {error.source && (
                  <span className="rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-slate-300">
                    source: {error.source}
                  </span>
                )}
                {error.code && (
                  <span className="rounded border border-slate-700 bg-slate-950/60 px-2 py-1 text-slate-300">
                    code: {error.code}
                  </span>
                )}
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card role="alert" className="border-red-700 bg-red-900/20">
      <CardContent className="p-4">
        <p className="text-sm leading-relaxed text-red-300">
          {isZh ? "错误：" : "Error: "}
          {error.message}
        </p>
      </CardContent>
    </Card>
  );
}
