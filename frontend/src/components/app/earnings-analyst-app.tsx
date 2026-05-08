"use client";

import { useState, useRef, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Search,
  Loader2,
  TrendingUp,
  Bot,
  BriefcaseBusiness,
  ChartColumnIncreasing,
  WalletCards,
} from "lucide-react";
import { ExecutiveSummary } from "@/components/analysis/ExecutiveSummary";
import { KeyMetrics } from "@/components/analysis/KeyMetrics";
import { BusinessDrivers } from "@/components/analysis/BusinessDrivers";
import { RiskFactors } from "@/components/analysis/RiskFactors";
import { BullBearCase } from "@/components/analysis/BullBearCase";
import {
  AnalysisReport,
  AnalysisMetadata,
  BusinessEvidenceRef,
  BusinessDriverSections,
  BusinessSignalItem,
  CashFlowCapitalAllocationSections,
  Citation,
  EvidenceBoundPoint,
  EvidenceBoundMetric,
  MetricInsight,
} from "@/types/AnalysisReport";
import { DuPontChart } from "@/components/financial/dupont-chart";
import { InsightCards } from "@/components/financial/insight-cards";
import { FinancialHealthRadar } from "@/components/financial/financial-health-radar";
import { TopicWordCloud } from "@/components/analysis/TopicWordCloud";
import { RagEvalDashboard } from "@/components/app/rag-eval-dashboard";
import { PdfDownloadButton } from "@/components/pdf/PdfDownloadButton";
import {
  formatPeriodForDisplay,
  getSourceMessage,
  getSourceStatusLabel,
  mergeSourceContexts,
} from "@/lib/reportPresentation";
import {
  DEFAULT_RESEARCH_TASK_ID,
  type ResearchTaskId,
} from "@/lib/researchTasks";
import { cn } from "@/lib/utils";
import type { HistoricalDataPoint } from "@/components/analysis/MarginAnalysisChart";

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

export default function EarningsAnalystApp() {
  const [ticker, setTicker] = useState("AAPL");
  const [activeTicker, setActiveTicker] = useState(""); // only set on submit
  const [lang, setLang] = useState("en");
  const [model, setModel] = useState<ByokProviderId>("siliconflow");
  const [selectedTask, setSelectedTask] = useState<ResearchTaskId>(
    DEFAULT_RESEARCH_TASK_ID,
  );
  const [activeTask, setActiveTask] = useState<ResearchTaskId>(
    DEFAULT_RESEARCH_TASK_ID,
  );
  const [providerApiKey, setProviderApiKey] = useState("");
  const [providerKeySaved, setProviderKeySaved] = useState(false);
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyData, setHistoryData] = useState<HistoricalDataPoint[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const tickerInputRef = useRef<HTMLInputElement>(null);
  const analysisAbortRef = useRef<AbortController | null>(null);
  const historyAbortRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isZh = lang === "zh";
  const selectedProvider =
    BYOK_PROVIDERS.find((provider) => provider.id === model) ??
    BYOK_PROVIDERS[0];
  const activeTaskConfig =
    RESEARCH_TASKS.find((task) => task.id === activeTask) ?? RESEARCH_TASKS[0];
  const reportTitleTicker = activeTicker || ticker;
  const reportCompanyName = report?.companyName?.trim();
  const reportPeriod = report?.period?.trim();
  const reportFilingDate = report?.filingDate?.trim();
  const displayPeriod = formatPeriodForDisplay(reportPeriod, lang);

  useEffect(() => {
    const savedKey = window.localStorage.getItem(selectedProvider.storageKey);
    if (savedKey) {
      setProviderApiKey(savedKey);
      setProviderKeySaved(true);
    } else {
      setProviderApiKey("");
      setProviderKeySaved(false);
    }
  }, [selectedProvider.storageKey]);

  // Backend URL: direct to backend in production, local rewrite proxy in dev.
  const apiBase = process.env.NEXT_PUBLIC_BACKEND_URL
    ? `${process.env.NEXT_PUBLIC_BACKEND_URL}/api`
    : "/api/java";
  const analysisApiBase = process.env.NEXT_PUBLIC_BACKEND_URL
    ? `${process.env.NEXT_PUBLIC_BACKEND_URL}/api`
    : "/api";

  const normalizeTicker = (rawTicker: string | undefined | null) =>
    rawTicker?.toUpperCase().trim() ?? "";

  // Fetch History Data with retry logic
  const fetchHistory = async (tickerToFetch: string, requestId: number) => {
    setHistoryLoading(true);
    const maxRetries = 2;
    historyAbortRef.current?.abort();
    const controller = new AbortController();
    historyAbortRef.current = controller;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const res = await fetch(`${apiBase}/sec/history/${tickerToFetch}`, {
          signal: controller.signal,
        });
        if (res.ok) {
          const data = (await res.json()) as HistoricalDataPoint[];
          if (requestIdRef.current === requestId) {
            setHistoryData(data);
          }
          setHistoryLoading(false);
          return; // Success — exit
        }
        console.warn(`History fetch attempt ${attempt} returned ${res.status}`);
      } catch (e) {
        if (controller.signal.aborted) {
          return;
        }
        console.warn(`History fetch attempt ${attempt} failed:`, e);
      }

      // Wait 1s before retrying
      if (attempt < maxRetries) {
        await new Promise((r) => setTimeout(r, 1000));
      }
    }

    // All retries failed
    console.error(
      `Failed to fetch history for ${tickerToFetch} after ${maxRetries} attempts`,
    );
    if (requestIdRef.current === requestId) {
      setHistoryData([]);
      setHistoryLoading(false);
    }
  };

  const handleSearch = async (rawTicker?: string) => {
    const submittedTicker = normalizeTicker(
      rawTicker ?? tickerInputRef.current?.value ?? ticker,
    );
    if (!submittedTicker || isLoading) return;
    if (!providerApiKey.trim()) {
      setError(
        isZh
          ? `请先输入并保存你的 ${selectedProvider.name} API Key。`
          : `${selectedProvider.name} BYOK mode requires you to enter and save your API key first.`,
      );
      return;
    }

    const requestId = Date.now();
    requestIdRef.current = requestId;
    analysisAbortRef.current?.abort();
    const controller = new AbortController();
    analysisAbortRef.current = controller;

    setIsLoading(true);
    setReport(null);
    setError(null);
    setHistoryData([]);
    setTicker(submittedTicker);
    setActiveTicker(submittedTicker);
    setActiveTask(selectedTask);

    // Fetch history data in parallel with analysis (doesn't depend on AI)
    fetchHistory(submittedTicker, requestId);

    try {
      console.log(
        `Fetching ${selectedTask} analysis for ${submittedTicker} using ${model} in ${lang}...`,
      );
      const analysisParams = new URLSearchParams({
        lang,
        model,
        taskType: selectedTask,
      });
      const response = await fetch(
        `${analysisApiBase}/sec/analyze/${submittedTicker}?${analysisParams.toString()}`,
        {
          headers: { "X-Provider-API-Key": providerApiKey.trim() },
          signal: controller.signal,
        },
      );
      console.log("Response status:", response.status);

      if (!response.ok || !response.body) {
        const errorText = await response.text();
        let message = `Network response error: ${response.statusText}`;
        if (errorText) {
          try {
            const parsed = JSON.parse(errorText) as { error?: string };
            if (parsed.error) {
              message = parsed.error;
            }
          } catch {
            message = errorText;
          }
        }
        throw new Error(message);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;

        // Parse SSE format: data:{...}
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
              setReport((prev) => {
                if (!prev) return reportData as AnalysisReport;

                // Filter out null/undefined values from the incoming chunk
                // to prevent overwriting already-received data from other agents
                const filtered = Object.fromEntries(
                  Object.entries(reportData).filter(
                    ([, value]) => value !== null && value !== undefined,
                  ),
                ) as Partial<AnalysisReport>;

                // Merge citations specifically since they are arrays from multiple agents
                const mergedCitations = [
                  ...(prev.citations || []),
                  ...(reportData.citations || []),
                ];
                const sourceContext = mergeSourceContexts(
                  prev.sourceContext,
                  reportData.sourceContext,
                );

                return {
                  ...prev,
                  ...filtered,
                  citations:
                    mergedCitations.length > 0
                      ? mergedCitations
                      : prev.citations,
                  sourceContext,
                };
              });
              console.log("Received progressive report chunk");
            } catch (e) {
              console.warn("JSON parse error:", e);
            }
          }
        }

        // Keep last incomplete line in buffer
        buffer = lines[lines.length - 1];
      }
    } catch (error) {
      if (controller.signal.aborted) {
        return;
      }
      console.error("Fetch Error:", error);
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      if (requestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  };

  useEffect(() => {
    return () => {
      analysisAbortRef.current?.abort();
      historyAbortRef.current?.abort();
    };
  }, []);

  const saveProviderKey = () => {
    const trimmedKey = providerApiKey.trim();
    if (!trimmedKey) {
      setProviderKeySaved(false);
      setError(
        isZh
          ? `请输入有效的 ${selectedProvider.name} API Key。`
          : `Please enter a valid ${selectedProvider.name} API key.`,
      );
      return;
    }
    window.localStorage.setItem(selectedProvider.storageKey, trimmedKey);
    setProviderApiKey(trimmedKey);
    setProviderKeySaved(true);
    setError(null);
  };

  const clearProviderKey = () => {
    window.localStorage.removeItem(selectedProvider.storageKey);
    setProviderApiKey("");
    setProviderKeySaved(false);
    setError(
      isZh
        ? `已清除 ${selectedProvider.name} Key，请重新输入。`
        : `${selectedProvider.name} key cleared. Enter a new key to continue.`,
    );
  };

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      const scrollElement = scrollRef.current.querySelector(
        "[data-radix-scroll-area-viewport]",
      );
      if (scrollElement) {
        scrollElement.scrollTop = scrollElement.scrollHeight;
      }
    }
  }, [report]);

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
            {/* Row 1: Ticker, Language, Button */}
            <div className="flex gap-2">
              <Input
                ref={tickerInputRef}
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                onKeyDown={(e) =>
                  e.key === "Enter" && void handleSearch(e.currentTarget.value)
                }
                placeholder={
                  isZh
                    ? "输入股票代码 (如 AAPL, MSFT)"
                    : "Enter Ticker (e.g., AAPL, MSFT, TSLA)"
                }
                className="bg-slate-950 border-slate-700 text-lg font-bold tracking-widest text-emerald-300 flex-1"
              />

              <select
                value={lang}
                onChange={(e) => setLang(e.target.value)}
                className="bg-slate-950 border border-slate-700 text-emerald-300 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-emerald-600 font-mono text-sm"
              >
                <option value="en">🇺🇸 EN</option>
                <option value="zh">🇨🇳 CN</option>
              </select>

              <Button
                onClick={() => void handleSearch(tickerInputRef.current?.value)}
                disabled={isLoading}
                className="bg-emerald-600 hover:bg-emerald-700 text-white min-w-[120px]"
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <>
                    <Search className="w-4 h-4 mr-2" />{" "}
                    {isZh ? "开始分析" : "Analyze"}
                  </>
                )}
              </Button>
            </div>

            {/* Row 2: Task Cards */}
            <div
              aria-label={isZh ? "研究任务" : "Research tasks"}
              role="radiogroup"
              className="grid grid-cols-1 gap-2 md:grid-cols-3"
            >
              {RESEARCH_TASKS.map((task) => {
                const isSelected = selectedTask === task.id;
                const Icon = task.Icon;

                return (
                  <button
                    key={task.id}
                    type="button"
                    role="radio"
                    aria-checked={isSelected}
                    onClick={() => setSelectedTask(task.id)}
                    disabled={isLoading}
                    className={cn(
                      "group flex min-h-[76px] items-start gap-3 rounded-md border px-3 py-3 text-left transition-all disabled:cursor-not-allowed disabled:opacity-60",
                      isSelected
                        ? "border-emerald-500 bg-emerald-950/30 text-emerald-100 shadow-[0_0_0_1px_rgba(16,185,129,0.25)]"
                        : "border-slate-800 bg-slate-950/60 text-slate-300 hover:border-slate-700 hover:bg-slate-900",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border",
                        isSelected
                          ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                          : "border-slate-800 bg-slate-900 text-slate-500 group-hover:text-slate-300",
                      )}
                    >
                      <Icon className="h-4 w-4" />
                    </span>
                    <span className="min-w-0 space-y-1">
                      <span className="block text-sm font-semibold leading-tight">
                        {isZh ? task.titleZh : task.title}
                      </span>
                      <span className="block text-xs leading-snug text-slate-500">
                        {isZh ? task.descriptionZh : task.description}
                      </span>
                    </span>
                  </button>
                );
              })}
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

        {/* Error Display */}
        {error && (
          <Card className="bg-red-900/20 border-red-700">
            <CardContent className="p-4">
              <p className="text-red-400">❌ Error: {error}</p>
            </CardContent>
          </Card>
        )}

        {/* Analysis Report */}
        {report && (
          <div id="pdf-report-root" className="space-y-6">
            {/* Report Toolbar */}
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
                  {isZh ? activeTaskConfig.titleZh : activeTaskConfig.title}
                </p>
              </div>
              <div data-pdf-exclude="true">
                <PdfDownloadButton
                  report={report}
                  ticker={reportTitleTicker}
                  lang={lang}
                />
              </div>
            </div>

            {activeTask === "business_driver_deep_dive" ? (
              <BusinessDriverReportSections report={report} lang={lang} />
            ) : activeTask === "cash_flow_capital_allocation" ? (
              <CashFlowReportSections report={report} lang={lang} />
            ) : (
              <LatestEarningsReportSections
                report={report}
                activeTicker={activeTicker}
                lang={lang}
                currency={report.currency}
                historyData={historyData}
                historyLoading={historyLoading}
                apiBase={apiBase}
              />
            )}

            <AgentProgress metadata={report.metadata} lang={lang} />

            {/* Citations with Verification Status */}
            {((report.citations && report.citations.length > 0) ||
              !!report.sourceContext?.message) && (
              <Card
                id="pdf-section-citations"
                className="bg-slate-900/50 backdrop-blur-sm border-slate-800 hover:border-emerald-500/30 transition-all duration-300"
              >
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-emerald-400 font-medium tracking-wide">
                    <span className="w-1 h-6 bg-emerald-500 rounded-full inline-block mr-1"></span>
                    {isZh
                      ? "来源引用与验证"
                      : "Source Citations & Verification"}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {report.citations && report.citations.length > 0 ? (
                    report.citations.map((citation, idx) => (
                      <div
                        key={idx}
                        className="bg-slate-950/50 rounded-lg border border-slate-800 p-4 transition-all duration-300 hover:border-slate-700 hover:bg-slate-900/80 group"
                      >
                        <div className="flex gap-4 items-start">
                          <div className="mt-0.5 shrink-0 bg-slate-900 p-1.5 rounded-full border border-slate-800 shadow-sm">
                            {citation.verificationStatus === "VERIFIED" ? (
                              <span
                                title={
                                  isZh ? "已验证" : "Verified in source text"
                                }
                                className="text-emerald-500 text-lg drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]"
                              >
                                ✅
                              </span>
                            ) : citation.verificationStatus === "UNVERIFIED" ? (
                              <span
                                title={
                                  isZh
                                    ? "未验证"
                                    : "Unverified / Low confidence"
                                }
                                className="text-yellow-500 text-lg"
                              >
                                ⚠️
                              </span>
                            ) : citation.verificationStatus === "NOT_FOUND" ? (
                              <span
                                title={
                                  isZh
                                    ? "未找到 (可能包含幻觉)"
                                    : "Not found in source text (Possible Hallucination)"
                                }
                                className="text-red-500 text-lg"
                              >
                                ❌
                              </span>
                            ) : (
                              <span
                                title={
                                  isZh ? "无验证数据" : "No verification data"
                                }
                                className="text-slate-500 text-lg"
                              >
                                ❓
                              </span>
                            )}
                          </div>
                          <div className="flex-1 space-y-3">
                            <div className="relative">
                              <span className="absolute -left-2 -top-2 text-3xl text-slate-800 font-serif select-none">
                                “
                              </span>
                              <p className="text-sm text-slate-300 leading-relaxed italic relative z-10 pl-2">
                                {isZh && citation.excerptZh
                                  ? citation.excerptZh
                                  : citation.excerpt}
                              </p>
                              <span className="absolute -bottom-4 right-0 text-3xl text-slate-800 font-serif select-none rotate-180">
                                “
                              </span>
                            </div>

                            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800/50 mt-2">
                              <span className="text-[10px] font-bold text-emerald-500/70 uppercase tracking-wider bg-emerald-950/20 px-2 py-0.5 rounded border border-emerald-900/30">
                                {isZh ? "来源" : "SOURCE"}
                              </span>
                              <p className="text-xs font-medium text-slate-500 uppercase tracking-widest">
                                {isZh
                                  ? (citation.section || "")
                                      .replace(
                                        /MD&A/gi,
                                        "SEC财报中的管理层讨论与分析",
                                      )
                                      .replace(/Risk Factors/gi, "风险因素")
                                      .replace(
                                        /Financial Statements/gi,
                                        "财务报表",
                                      )
                                      .replace(/Notes/gi, "附注")
                                  : citation.section}
                              </p>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="bg-slate-950/50 rounded-lg border border-slate-800 p-4">
                      <div className="flex gap-4 items-start">
                        <div className="mt-0.5 shrink-0 bg-slate-900 p-1.5 rounded-full border border-slate-800 shadow-sm">
                          <span
                            title={
                              isZh
                                ? "本次无可验证来源"
                                : "No verifiable source for this run"
                            }
                            className="text-yellow-500 text-lg"
                          >
                            ⚠️
                          </span>
                        </div>
                        <div className="space-y-2">
                          <p className="text-sm text-slate-200 leading-relaxed">
                            {getSourceMessage(report.sourceContext, lang)}
                          </p>
                          <p className="text-xs uppercase tracking-widest text-slate-500">
                            {isZh
                              ? `当前状态：${getSourceStatusLabel(report.sourceContext, lang)}`
                              : `Current status: ${getSourceStatusLabel(report.sourceContext, lang)}`}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        )}

        {/* Empty State */}
        {!report && !isLoading && !error && (
          <Card className="bg-slate-900 border-slate-800 min-h-[400px] flex items-center justify-center">
            <CardContent className="text-center">
              <TrendingUp className="w-16 h-16 text-slate-700 mx-auto mb-4" />
              <p className="text-slate-500 text-lg">
                {isZh
                  ? "输入股票代码并点击“开始分析”"
                  : "Enter a ticker symbol and click Analyze to get started"}
              </p>
            </CardContent>
          </Card>
        )}

        <section
          aria-labelledby="experiment-lab-title"
          className="space-y-3 border-t border-slate-800 pt-6"
        >
          <div>
            <p className="text-xs uppercase tracking-widest text-slate-500">
              Experiment Lab
            </p>
            <h2
              id="experiment-lab-title"
              className="text-lg font-semibold text-slate-200"
            >
              RAG eval artifacts
            </h2>
          </div>
          <RagEvalDashboard />
        </section>
      </div>
    </div>
  );
}

interface LatestEarningsReportSectionsProps {
  report: AnalysisReport;
  activeTicker: string;
  lang: string;
  currency?: string;
  historyData: HistoricalDataPoint[];
  historyLoading: boolean;
  apiBase: string;
}

function AgentProgress({
  metadata,
  lang,
}: {
  metadata?: AnalysisMetadata;
  lang: string;
}) {
  const isZh = lang === "zh";
  const events = metadata?.agentEvents?.filter((event) => event.summary) ?? [];
  if (events.length === 0) {
    return null;
  }

  return (
    <Card className="bg-slate-900/50 border-slate-800">
      <CardHeader>
        <CardTitle className="text-emerald-400">
          {isZh ? "Agent 执行轨迹" : "Agent Progress"}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {events.slice(0, 8).map((event, index) => (
          <div
            key={`${event.phase}-${event.toolName ?? "decision"}-${index}`}
            className="grid gap-2 rounded-md border border-slate-800 bg-slate-950/60 p-3 text-sm md:grid-cols-[160px,1fr]"
          >
            <div className="space-y-1">
              <p className="font-semibold text-slate-200">{event.phase}</p>
              {event.toolName && (
                <p className="text-xs text-emerald-300">{event.toolName}</p>
              )}
            </div>
            <p className="leading-6 text-slate-400">{event.summary}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function LatestEarningsReportSections({
  report,
  activeTicker,
  lang,
  currency,
  historyData,
  historyLoading,
  apiBase,
}: LatestEarningsReportSectionsProps) {
  const isZh = lang === "zh";

  return (
    <>
      <div id="pdf-section-summary">
        <ResearchViewCard
          lang={lang}
          title={isZh ? "财报 Dashboard 视图" : "Earnings Dashboard View"}
          description={
            isZh
              ? "这个视图保留完整 dashboard，用于快速读懂最新财报的核心表现。"
              : "This view keeps the full dashboard for a fast readout of the latest earnings release."
          }
          labels={[
            isZh ? "核心财务指标" : "Key Financial Metrics",
            isZh ? "利润率与趋势图" : "Margin and Trend Charts",
            isZh ? "证据引用" : "Evidence Trail",
          ]}
        />
        <ExecutiveSummary
          thesis={report.coreThesis}
          businessSignals={report.businessSignals}
          summary={report.executiveSummary}
          metadata={report.metadata}
          lang={lang}
        />
      </div>

      <div id="pdf-section-metrics">
        <KeyMetrics
          metrics={report.keyMetrics}
          ticker={activeTicker}
          lang={lang}
          currency={currency}
          historyData={historyData}
          historyLoading={historyLoading}
          apiBase={apiBase}
        />
      </div>

      <div id="pdf-section-advanced" className="space-y-6">
        <h2 className="text-xl font-bold flex items-center gap-2 text-emerald-400 border-b border-slate-800 pb-2">
          <TrendingUp className="w-6 h-6" />
          {isZh ? "深度洞察" : "Advanced Insights"}
        </h2>
        <div id="chart-dupont">
          <DuPontChart data={report.dupontAnalysis!} lang={lang} />
        </div>
        <div id="chart-topics">
          <TopicWordCloud trends={report.topicTrends || []} lang={lang} />
        </div>
        <div id="chart-insights">
          <InsightCards data={report.insightEngine!} lang={lang} />
        </div>
        <div id="chart-radar">
          <FinancialHealthRadar
            ticker={activeTicker}
            lang={lang}
            apiBase={apiBase}
          />
        </div>
      </div>

      <div
        id="pdf-section-drivers-risks"
        className="grid grid-cols-1 md:grid-cols-2 gap-6"
      >
        <BusinessDrivers drivers={report.businessDrivers || []} lang={lang} />
        <RiskFactors risks={report.riskFactors || []} lang={lang} />
      </div>

      <div id="pdf-section-bull-bear">
        <BullBearCase
          bullCase={report.bullCase}
          bearCase={report.bearCase}
          lang={lang}
        />
      </div>
    </>
  );
}

function BusinessDriverReportSections({
  report,
  lang,
}: {
  report: AnalysisReport;
  lang: string;
}) {
  const isZh = lang === "zh";
  const typedSections =
    report.taskSections?.taskType === "business_driver_deep_dive"
      ? resolveBusinessDriverSections(report.taskSections)
      : null;

  if (typedSections) {
    return (
      <TypedBusinessDriverSections sections={typedSections} lang={lang} />
    );
  }

  const driverGroups = buildBusinessDriverGroups(report, lang);
  const evidence = buildBusinessEvidence(report);

  return (
    <>
      <div id="pdf-section-summary" className="space-y-6">
        <ResearchViewCard
          lang={lang}
          title={
            isZh ? "业务驱动研究视图" : "Business Driver Research View"
          }
          description={
            isZh
              ? "这个视图优先解释产品、分部、需求、定价、客户和战略动作，而不是只重复财务指标。"
              : "This view prioritizes products, segments, demand, pricing, customers, and strategic actions instead of repeating financial metrics."
          }
          labels={[
            isZh ? "产品 / 分部信号" : "Product / Segment Signals",
            isZh ? "需求与定价信号" : "Demand & Pricing Signals",
            isZh ? "竞争与执行风险" : "Competitive / Execution Risks",
          ]}
        />
        <ExecutiveSummary
          thesis={report.coreThesis}
          businessSignals={report.businessSignals}
          summary={report.executiveSummary}
          metadata={report.metadata}
          lang={lang}
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
              key={group.title}
              className="rounded-md border border-slate-800 bg-slate-950/60 p-4"
            >
              <p className="text-sm font-semibold text-slate-200">
                {group.title}
              </p>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                {group.detail}
              </p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="border-b border-slate-800">
          <CardTitle className="text-emerald-400">
            {isZh ? "驱动证据" : "Driver Evidence"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-6">
          {evidence.length > 0 ? (
            evidence.map((item, index) => (
              <EvidenceRow
                key={`${item.label}-${index}`}
                label={item.label}
                detail={item.detail}
                meta={item.meta}
              />
            ))
          ) : (
            <p className="text-sm text-slate-500">
              {isZh
                ? "当前报告没有提供可拆分的驱动证据。"
                : "This report did not provide separable driver evidence."}
            </p>
          )}
        </CardContent>
      </Card>

      <BusinessDrivers drivers={report.businessDrivers || []} lang={lang} />
    </>
  );
}

function CashFlowReportSections({
  report,
  lang,
}: {
  report: AnalysisReport;
  lang: string;
}) {
  const isZh = lang === "zh";
  const typedSections =
    report.taskSections?.taskType === "cash_flow_capital_allocation"
      ? resolveCashFlowSections(report.taskSections)
      : null;

  if (typedSections) {
    return <TypedCashFlowSections sections={typedSections} lang={lang} />;
  }

  const cashMetrics = filterCashMetrics(report.keyMetrics || []);
  const allocationEvidence = buildCapitalAllocationEvidence(report);

  return (
    <>
      <div id="pdf-section-summary" className="space-y-6">
        <ResearchViewCard
          lang={lang}
          title={isZh ? "资本配置视图" : "Capital Allocation View"}
          description={
            isZh
              ? "这个视图优先解释经营现金流、自由现金流、资本开支、回购、债务和流动性。"
              : "This view prioritizes operating cash flow, free cash flow, capex, buybacks, debt, and liquidity."
          }
          labels={[
            isZh ? "现金转化质量" : "Cash Conversion Quality",
            isZh ? "资本开支 / 投资强度" : "Capex / Investment Intensity",
            isZh ? "回购 / 债务 / 流动性" : "Buybacks / Debt / Liquidity",
          ]}
        />
        <ExecutiveSummary
          thesis={report.coreThesis}
          businessSignals={report.businessSignals}
          summary={report.executiveSummary}
          metadata={report.metadata}
          lang={lang}
        />
      </div>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="border-b border-slate-800">
          <CardTitle className="text-emerald-400">
            {isZh ? "现金质量判断" : "Cash Quality Verdict"}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 p-6 md:grid-cols-3">
          {(cashMetrics.length > 0
            ? cashMetrics
            : [
                {
                  metricName: isZh ? "现金指标" : "Cash Metrics",
                  value: isZh ? "待补充" : "Pending",
                  interpretation: isZh
                    ? "当前后端 contract 尚未提供专属现金流字段。"
                    : "The current backend contract has not provided dedicated cash-flow fields yet.",
                  sentiment: "neutral" as const,
                },
              ]
          ).map((metric) => (
            <MetricFocusBlock key={metric.metricName} metric={metric} />
          ))}
        </CardContent>
      </Card>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="border-b border-slate-800">
          <CardTitle className="text-emerald-400">
            {isZh ? "资本配置视角" : "Capital Allocation Lens"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-6">
          {allocationEvidence.length > 0 ? (
            allocationEvidence.map((item, index) => (
              <EvidenceRow
                key={`${item.label}-${index}`}
                label={item.label}
                detail={item.detail}
                meta={item.meta}
              />
            ))
          ) : (
            <p className="text-sm text-slate-500">
              {isZh
                ? "当前报告没有提供回购、债务、资本开支或流动性相关证据。"
                : "This report did not provide buyback, debt, capex, or liquidity evidence."}
            </p>
          )}
        </CardContent>
      </Card>
    </>
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
      <div id="pdf-section-summary" className="space-y-6">
        <ResearchViewCard
          lang={lang}
          title={
            isZh ? "业务驱动研究视图" : "Business Driver Research View"
          }
          description={
            isZh
              ? "这个视图由 typed task sections 驱动，优先展示业务驱动、信号和跟踪项。"
              : "This view is powered by typed task sections and prioritizes drivers, signals, and watch items."
          }
          labels={[
            isZh ? "产品 / 分部信号" : "Product / Segment Signals",
            isZh ? "需求与定价信号" : "Demand & Pricing Signals",
            isZh ? "竞争与执行风险" : "Competitive / Execution Risks",
          ]}
        />
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="border-b border-slate-800">
            <CardTitle className="text-emerald-400">
              {isZh ? "驱动论点" : "Driver Thesis"}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <p className="text-lg font-semibold text-slate-100">
              {driverThesis.headline}
            </p>
            <p className="mt-2 text-sm uppercase tracking-widest text-slate-500">
              {driverThesis.durability}
            </p>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              {driverThesis.summary}
            </p>
          </CardContent>
        </Card>
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
                    <EvidencePointBlock key={`${item.title}-${index}`} point={item} />
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
        title={isZh ? "正向信号" : "Positive Signals"}
        points={sections.positiveSignals ?? []}
        emptyText={isZh ? "没有正向信号。" : "No positive signals provided."}
      />
      <PointListCard
        title={isZh ? "负向信号" : "Negative Signals"}
        points={sections.negativeSignals ?? []}
        emptyText={isZh ? "没有负向信号。" : "No negative signals provided."}
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
      <div id="pdf-section-summary" className="space-y-6">
        <ResearchViewCard
          lang={lang}
          title={isZh ? "资本配置视图" : "Capital Allocation View"}
          description={
            isZh
              ? "这个视图由 typed task sections 驱动，优先展示现金质量和资本配置。"
              : "This view is powered by typed task sections and prioritizes cash quality and capital allocation."
          }
          labels={[
            isZh ? "现金转化质量" : "Cash Conversion Quality",
            isZh ? "资本开支 / 投资强度" : "Capex / Investment Intensity",
            isZh ? "回购 / 债务 / 流动性" : "Buybacks / Debt / Liquidity",
          ]}
        />
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader className="border-b border-slate-800">
            <CardTitle className="text-emerald-400">
              {isZh ? "现金质量判断" : "Cash Quality Verdict"}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <p className="text-lg font-semibold text-slate-100">
              {cashQualityVerdict.headline}
            </p>
            <p className="mt-2 text-sm uppercase tracking-widest text-slate-500">
              {cashQualityVerdict.earningsBackedByCash}
            </p>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              {cashQualityVerdict.summary}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="border-b border-slate-800">
          <CardTitle className="text-emerald-400">
            {isZh ? "现金指标" : "Cash Metrics"}
          </CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 p-6 md:grid-cols-3">
          {(sections.cashMetrics ?? []).map((metric) => (
            <EvidenceMetricBlock key={metric.name} metric={metric} />
          ))}
        </CardContent>
      </Card>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader className="border-b border-slate-800">
          <CardTitle className="text-emerald-400">
            {isZh ? "资本配置视角" : "Capital Allocation Lens"}
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
                    <EvidencePointBlock key={`${item.title}-${index}`} point={item} />
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
        emptyText={isZh ? "没有配置纪律信号。" : "No allocation discipline points provided."}
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
    return envelope.businessDriver;
  }
  if ("driverThesis" in taskSections || "driverMap" in taskSections) {
    return taskSections as BusinessDriverSections;
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
    return envelope.cashFlowCapitalAllocation;
  }
  if ("cashQualityVerdict" in taskSections || "capitalAllocation" in taskSections) {
    return taskSections as CashFlowCapitalAllocationSections;
  }
  return null;
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

function MetricFocusBlock({ metric }: { metric: MetricInsight }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-4">
      <p className="text-sm text-slate-400">{metric.metricName}</p>
      <p className="mt-1 text-xl font-semibold text-emerald-300">
        {metric.value}
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-400">
        {metric.interpretation}
      </p>
    </div>
  );
}

function EvidencePointBlock({ point }: { point: EvidenceBoundPoint }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <p className="font-semibold text-slate-200">{point.title}</p>
        <p className="text-xs uppercase tracking-widest text-slate-500">
          {point.citationStatus}
        </p>
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-400">{point.summary}</p>
    </div>
  );
}

function EvidenceMetricBlock({ metric }: { metric: EvidenceBoundMetric }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-sm text-slate-400">{metric.name}</p>
        <p className="text-xs uppercase tracking-widest text-slate-500">
          {metric.citationStatus}
        </p>
      </div>
      <p className="mt-1 text-xl font-semibold text-emerald-300">
        {metric.value}
      </p>
      <p className="mt-3 text-sm leading-6 text-slate-400">
        {metric.interpretation}
      </p>
    </div>
  );
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

function EvidenceRow({
  label,
  detail,
  meta,
}: {
  label: string;
  detail: string;
  meta?: string;
}) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <p className="font-semibold text-slate-200">{label}</p>
        {meta && (
          <p className="text-xs uppercase tracking-widest text-slate-500">
            {meta}
          </p>
        )}
      </div>
      <p className="mt-2 text-sm leading-6 text-slate-400">{detail}</p>
    </div>
  );
}

function buildBusinessDriverGroups(report: AnalysisReport, lang: string) {
  const isZh = lang === "zh";
  const signals = report.businessSignals;
  const fallbackDrivers = report.businessDrivers || [];
  const fallbackDetail =
    fallbackDrivers
      .map((driver) => `${driver.title}: ${driver.description}`)
      .join(" ") ||
    report.coreThesis?.summary ||
    report.executiveSummary ||
    (isZh ? "当前报告没有提供该维度。" : "No signal provided for this lens.");

  return [
    {
      title: isZh ? "产品 / 服务" : "Product / Service",
      detail: summarizeSignalItems(signals?.productServiceUpdates, fallbackDetail),
    },
    {
      title: isZh ? "分部 / 地区" : "Segment / Geography",
      detail: summarizeSignalItems(signals?.segmentPerformance, fallbackDetail),
    },
    {
      title: isZh ? "管理层重点" : "Management Focus",
      detail: summarizeSignalItems(signals?.managementFocus, fallbackDetail),
    },
    {
      title: isZh ? "战略动作" : "Strategic Actions",
      detail: summarizeSignalItems(signals?.strategicMoves, fallbackDetail),
    },
  ];
}

function summarizeSignalItems(
  items: BusinessSignalItem[] | undefined,
  fallback: string,
) {
  const summary = items
    ?.map((item) => item.summary || item.evidenceSnippet || item.title)
    .filter(Boolean)
    .join(" ");

  return summary || fallback;
}

function buildBusinessEvidence(report: AnalysisReport) {
  const refs =
    report.businessSignals?.evidenceRefs?.map((ref) =>
      evidenceFromBusinessRef(ref),
    ) ?? [];
  const driverEvidence =
    report.businessDrivers?.map((driver) => ({
      label: driver.title,
      detail: driver.description,
      meta: `Impact: ${driver.impact}`,
    })) ?? [];

  return [...refs, ...driverEvidence].slice(0, 6);
}

function evidenceFromBusinessRef(ref: BusinessEvidenceRef) {
  return {
    label: ref.topic || "Evidence",
    detail: ref.excerpt || "No excerpt provided.",
    meta: ref.section,
  };
}

const CASH_KEYWORDS = [
  "cash",
  "free cash flow",
  "operating cash flow",
  "ocf",
  "fcf",
  "capex",
  "capital expenditure",
  "buyback",
  "repurchase",
  "dividend",
  "debt",
  "liquidity",
];

function filterCashMetrics(metrics: MetricInsight[]) {
  return metrics
    .filter((metric) =>
      CASH_KEYWORDS.some((keyword) =>
        `${metric.metricName} ${metric.interpretation}`
          .toLowerCase()
          .includes(keyword),
      ),
    )
    .slice(0, 6);
}

function buildCapitalAllocationEvidence(report: AnalysisReport) {
  const citationEvidence =
    report.citations
      ?.filter((citation) => citationMatchesKeywords(citation, CASH_KEYWORDS))
      .map((citation) => ({
        label: citation.section || "SEC Evidence",
        detail: "Source excerpt available in Evidence Trail.",
        meta: citation.verificationStatus,
      })) ?? [];
  const metricEvidence = filterCashMetrics(report.keyMetrics || []).map(
    (metric) => ({
      label: metric.metricName,
      detail: metric.interpretation,
      meta: metric.value,
    }),
  );

  return [...metricEvidence, ...citationEvidence].slice(0, 6);
}

function citationMatchesKeywords(citation: Citation, keywords: string[]) {
  const haystack = `${citation.section} ${citation.excerpt}`.toLowerCase();
  return keywords.some((keyword) => haystack.includes(keyword));
}
