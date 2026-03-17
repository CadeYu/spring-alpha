"use client";

import Image from "next/image";
import { useState, useRef, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Search, Loader2, TrendingUp, Bot } from "lucide-react";
import { ExecutiveSummary } from "@/components/analysis/ExecutiveSummary";
import { KeyMetrics } from "@/components/analysis/KeyMetrics";
import { BusinessDrivers } from "@/components/analysis/BusinessDrivers";
import { RiskFactors } from "@/components/analysis/RiskFactors";
import { BullBearCase } from "@/components/analysis/BullBearCase";
import { AnalysisReport } from "@/types/AnalysisReport";
import { DuPontChart } from "@/components/financial/dupont-chart";
import { InsightCards } from "@/components/financial/insight-cards";
import { FinancialHealthRadar } from "@/components/financial/financial-health-radar";
import { TopicWordCloud } from "@/components/analysis/TopicWordCloud";
import { PdfDownloadButton } from "@/components/pdf/PdfDownloadButton";
import {
  formatPeriodForDisplay,
  getSourceMessage,
  getSourceStatusLabel,
  mergeSourceContexts,
} from "@/lib/reportPresentation";
import type { HistoricalDataPoint } from "@/components/analysis/MarginAnalysisChart";

// Available AI models for analysis
const AI_MODELS = [
  {
    id: "chatanywhere",
    name: "GPT-4o Mini",
    iconSrc: "/brands/openai.png",
    iconAlt: "OpenAI",
    description: "Free 200/day",
    descZh: "免费200次/天",
  },
  {
    id: "groq",
    name: "Meta Llama 3.3",
    iconSrc: "/brands/meta.jpeg",
    iconAlt: "Meta",
    description: "Fast & Free",
    descZh: "快速免费",
  },
  {
    id: "openai",
    name: "OpenAI (BYOK)",
    iconSrc: "/brands/openai.png",
    iconAlt: "OpenAI",
    description: "Use your own API key",
    descZh: "使用你自己的 API Key",
  },
];

const OPENAI_KEY_STORAGE = "spring-alpha-openai-key";

export default function EarningsAnalystApp() {
  const [ticker, setTicker] = useState("AAPL");
  const [activeTicker, setActiveTicker] = useState(""); // only set on submit
  const [lang, setLang] = useState("en");
  const [model, setModel] = useState("chatanywhere");
  const [openAiApiKey, setOpenAiApiKey] = useState("");
  const [openAiKeySaved, setOpenAiKeySaved] = useState(false);
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
  const isOpenAiMode = model === "openai";
  const reportTitleTicker = activeTicker || ticker;
  const reportCompanyName = report?.companyName?.trim();
  const reportPeriod = report?.period?.trim();
  const reportFilingDate = report?.filingDate?.trim();
  const displayPeriod = formatPeriodForDisplay(reportPeriod, lang);

  useEffect(() => {
    const savedKey = window.localStorage.getItem(OPENAI_KEY_STORAGE);
    if (savedKey) {
      setOpenAiApiKey(savedKey);
      setOpenAiKeySaved(true);
    }
  }, []);

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
    if (isOpenAiMode && !openAiApiKey.trim()) {
      setError(
        isZh
          ? "请选择 OpenAI 模式后先输入并保存你的 API Key。"
          : "OpenAI BYOK mode requires you to enter and save your API key first.",
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

    // Fetch history data in parallel with analysis (doesn't depend on AI)
    fetchHistory(submittedTicker, requestId);

    try {
      console.log(
        `Fetching analysis for ${submittedTicker} using ${model} in ${lang}...`,
      );
      const response = await fetch(
        `${analysisApiBase}/sec/analyze/${submittedTicker}?lang=${lang}&model=${model}`,
        {
          headers: isOpenAiMode
            ? { "X-OpenAI-API-Key": openAiApiKey.trim() }
            : undefined,
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

  const saveOpenAiKey = () => {
    const trimmedKey = openAiApiKey.trim();
    if (!trimmedKey) {
      setOpenAiKeySaved(false);
      setError(
        isZh
          ? "请输入有效的 OpenAI API Key。"
          : "Please enter a valid OpenAI API key.",
      );
      return;
    }
    window.localStorage.setItem(OPENAI_KEY_STORAGE, trimmedKey);
    setOpenAiApiKey(trimmedKey);
    setOpenAiKeySaved(true);
    setError(null);
  };

  const clearOpenAiKey = () => {
    window.localStorage.removeItem(OPENAI_KEY_STORAGE);
    setOpenAiApiKey("");
    setOpenAiKeySaved(false);
    if (isOpenAiMode) {
      setError(
        isZh
          ? "已清除 OpenAI Key，请重新输入。"
          : "OpenAI key cleared. Enter a new key to continue.",
      );
    }
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

            {/* Row 2: Model Selector */}
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-slate-500" />
              <span className="text-xs text-slate-500">
                {isZh ? "AI 模型:" : "AI Model:"}
              </span>
              <div className="flex gap-2 flex-1">
                {AI_MODELS.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => setModel(m.id)}
                    className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                      model === m.id
                        ? "bg-emerald-600 text-white"
                        : "bg-slate-800 text-slate-400 hover:bg-slate-700"
                    }`}
                    title={isZh ? m.descZh : m.description}
                  >
                    <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center overflow-hidden rounded-full bg-white/95 ring-1 ring-black/10">
                      <Image
                        src={m.iconSrc}
                        alt={m.iconAlt}
                        width={16}
                        height={16}
                        className="h-4 w-4 object-cover"
                      />
                    </span>
                    <span>{m.name}</span>
                  </button>
                ))}
              </div>
            </div>

            {isOpenAiMode && (
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-950/10 p-4 space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-emerald-300">
                      {isZh ? "OpenAI API Key" : "OpenAI API Key"}
                    </p>
                    <p className="text-xs text-slate-400">
                      {isZh
                        ? "仅保存在当前浏览器本地，并在请求 OpenAI 模式时透传到后端。"
                        : "Stored only in this browser and forwarded to the backend only for OpenAI mode."}
                    </p>
                  </div>
                  <span
                    className={`text-xs font-medium ${openAiKeySaved ? "text-emerald-400" : "text-amber-400"}`}
                  >
                    {openAiKeySaved
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
                    value={openAiApiKey}
                    onChange={(e) => {
                      setOpenAiApiKey(e.target.value);
                      setOpenAiKeySaved(false);
                    }}
                    placeholder={
                      isZh
                        ? "输入 sk-... 开头的 OpenAI Key"
                        : "Enter your OpenAI key (sk-...)"
                    }
                    className="bg-slate-950 border-slate-700 text-slate-200"
                  />
                  <Button
                    type="button"
                    onClick={saveOpenAiKey}
                    className="bg-emerald-600 hover:bg-emerald-700 text-white"
                  >
                    {isZh ? "保存" : "Save"}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={clearOpenAiKey}
                    className="border-slate-700 bg-slate-950 text-slate-300 hover:bg-slate-900"
                  >
                    {isZh ? "清除" : "Clear"}
                  </Button>
                </div>
              </div>
            )}
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
              </div>
              <div data-pdf-exclude="true">
                <PdfDownloadButton
                  report={report}
                  ticker={reportTitleTicker}
                  lang={lang}
                />
              </div>
            </div>

            <div id="pdf-section-summary">
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
                currency={report.currency}
                historyData={historyData}
                historyLoading={historyLoading}
                apiBase={apiBase}
              />
            </div>

            {/* Advanced Insights Section */}
            <div id="pdf-section-advanced" className="space-y-6">
              <h2 className="text-xl font-bold flex items-center gap-2 text-emerald-400 border-b border-slate-800 pb-2">
                <TrendingUp className="w-6 h-6" />
                {isZh ? "深度洞察" : "Advanced Insights"}
              </h2>

              {/* DuPont Analysis */}
              <div id="chart-dupont">
                <DuPontChart data={report.dupontAnalysis!} lang={lang} />
              </div>

              {/* Topic Trends (Word Cloud) */}
              <div id="chart-topics">
                <TopicWordCloud trends={report.topicTrends || []} lang={lang} />
              </div>

              {/* Insight Engine (Root Cause & Accounting Changes) */}
              <div id="chart-insights">
                <InsightCards data={report.insightEngine!} lang={lang} />
              </div>

              {/* Financial Health Radar (replaces Factor Analysis Waterfalls) */}
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
              <BusinessDrivers
                drivers={report.businessDrivers || []}
                lang={lang}
              />
              <RiskFactors risks={report.riskFactors || []} lang={lang} />
            </div>

            <div id="pdf-section-bull-bear">
              <BullBearCase
                bullCase={report.bullCase}
                bearCase={report.bearCase}
                lang={lang}
              />
            </div>

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
      </div>
    </div>
  );
}
