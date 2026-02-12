'use client';

import { useState, useRef, useEffect } from 'react';
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Search, Loader2, TrendingUp, AlertCircle, TrendingDown, Bot, Quote } from 'lucide-react';
import { MetricCard } from '@/components/MetricCard';
import { HealthScore } from '@/components/HealthScore';
import { RiskAlerts } from '@/components/RiskAlerts';
import { ExecutiveSummary } from '@/components/analysis/ExecutiveSummary';
import { KeyMetrics } from '@/components/analysis/KeyMetrics';
import { BusinessDrivers } from '@/components/analysis/BusinessDrivers';
import { RiskFactors } from '@/components/analysis/RiskFactors';
import { BullBearCase } from '@/components/analysis/BullBearCase';
import { RevenueChart } from '@/components/analysis/RevenueChart';
import { MarginAnalysisChart } from '@/components/analysis/MarginAnalysisChart';
import { AnalysisReport } from '@/types/AnalysisReport';
import { DuPontChart } from '@/components/financial/dupont-chart';
import { InsightCards } from '@/components/financial/insight-cards';
import { WaterfallChart } from '@/components/financial/waterfall-chart';

// Available AI models for analysis
const AI_MODELS = [
  { id: 'groq', name: 'Groq Llama 3.3', icon: '⚡', description: 'Fast & Free', descZh: '快速免费' },
  { id: 'openai', name: 'OpenAI GPT-4', icon: '🧠', description: 'Most Capable', descZh: '最强能力' },
  { id: 'gemini', name: 'Google Gemini', icon: '💎', description: 'Balanced', descZh: '均衡全面' },
  { id: 'enhanced-mock', name: 'Mock (Testing)', icon: '🔧', description: 'No API', descZh: '无需API' },
];

export default function Home() {
  const [ticker, setTicker] = useState('AAPL');
  const [lang, setLang] = useState('en');
  const [model, setModel] = useState('groq');
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [historyData, setHistoryData] = useState<any[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const isZh = lang === 'zh';

  // Fetch History Data
  useEffect(() => {
    if (!ticker) return;

    const fetchHistory = async () => {
      setHistoryLoading(true);
      try {
        const res = await fetch(`/api/java/sec/history/${ticker}`);
        if (res.ok) {
          const data = await res.json();
          setHistoryData(data);
        } else {
          setHistoryData([]);
        }
      } catch (e) {
        console.error("Failed to fetch history:", e);
        setHistoryData([]);
      } finally {
        setHistoryLoading(false);
      }
    };

    fetchHistory();
  }, [ticker]);

  const handleSearch = async () => {
    if (!ticker) return;

    setIsLoading(true);
    setReport(null);
    setError(null);

    try {
      console.log(`Fetching analysis for ${ticker} using ${model} in ${lang}...`);
      const response = await fetch(`/api/java/sec/analyze/${ticker}?lang=${lang}&model=${model}`);
      console.log("Response status:", response.status);

      if (!response.ok || !response.body) {
        throw new Error(`Network response error: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;

        // Parse SSE format: data:{...}
        const lines = buffer.split('\n');

        for (let i = 0; i < lines.length - 1; i++) {
          const line = lines[i].trim();
          if (line.startsWith('data:')) {
            const jsonStr = line.substring(5).trim();
            try {
              const reportData = JSON.parse(jsonStr);
              setReport(reportData);
              console.log("Received report:", reportData);
            } catch (e) {
              console.warn("JSON parse error:", e);
            }
          }
        }

        // Keep last incomplete line in buffer
        buffer = lines[lines.length - 1];
      }
    } catch (error) {
      console.error("Fetch Error:", error);
      setError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsLoading(false);
    }
  };

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      const scrollElement = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
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
            {isZh ? 'AI 财报分析师' : 'AI Earnings Analyst'} <span className="text-xs bg-slate-800 px-2 py-1 rounded text-slate-400">v2.0</span>
          </h1>
        </div>

        {/* Search Bar */}
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-4 space-y-3">
            {/* Row 1: Ticker, Language, Button */}
            <div className="flex gap-2">
              <Input
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder={isZh ? "输入股票代码 (如 AAPL, MSFT)" : "Enter Ticker (e.g., AAPL, MSFT, TSLA)"}
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
                onClick={handleSearch}
                disabled={isLoading}
                className="bg-emerald-600 hover:bg-emerald-700 text-white min-w-[120px]"
              >
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Search className="w-4 h-4 mr-2" /> {isZh ? '开始分析' : 'Analyze'}</>}
              </Button>
            </div>

            {/* Row 2: Model Selector */}
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-slate-500" />
              <span className="text-xs text-slate-500">{isZh ? 'AI 模型:' : 'AI Model:'}</span>
              <div className="flex gap-2 flex-1">
                {AI_MODELS.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => setModel(m.id)}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${model === m.id
                      ? 'bg-emerald-600 text-white'
                      : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                      }`}
                    title={isZh ? m.descZh : m.description}
                  >
                    {m.icon} {m.name}
                  </button>
                ))}
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
          <div className="space-y-6">
            <ExecutiveSummary
              summary={report.executiveSummary}
              metadata={report.metadata}
              lang={lang}
            />

            <KeyMetrics
              metrics={report.keyMetrics}
              ticker={ticker}
              lang={lang}
              currency={report.currency}
              historyData={historyData}
              historyLoading={historyLoading}
            />

            {/* Advanced Insights Section */}
            {(report.dupontAnalysis || report.insightEngine || report.factorAnalysis) && (
              <div className="space-y-6">
                <h2 className="text-xl font-bold flex items-center gap-2 text-emerald-400 border-b border-slate-800 pb-2">
                  <TrendingUp className="w-6 h-6" />
                  {isZh ? '深度洞察' : 'Advanced Insights'}
                </h2>

                {/* DuPont Analysis */}
                {report.dupontAnalysis && (
                  <DuPontChart data={report.dupontAnalysis} lang={lang} />
                )}

                {/* Insight Engine (Root Cause & Accounting Changes) */}
                {report.insightEngine && (
                  <InsightCards data={report.insightEngine} lang={lang} />
                )}

                {/* Factor Analysis (Waterfalls) */}
                {report.factorAnalysis && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                    <WaterfallChart
                      title={isZh ? "营收桥 (增长驱动)" : "Revenue Bridge (Drivers of Growth)"}
                      data={report.factorAnalysis.revenueBridge}
                      lang={lang}
                    />
                    <WaterfallChart
                      title={isZh ? "利润率桥 (盈利驱动)" : "Margin Bridge (Drivers of Profitability)"}
                      data={report.factorAnalysis.marginBridge}
                      lang={lang}
                    />
                  </div>
                )}
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <BusinessDrivers drivers={report.businessDrivers} lang={lang} />
              <RiskFactors risks={report.riskFactors} lang={lang} />
            </div>

            <BullBearCase
              bullCase={report.bullCase}
              bearCase={report.bearCase}
              lang={lang}
            />

            {/* Citations with Verification Status */}
            {report.citations && report.citations.length > 0 && (
              <Card className="bg-slate-900/50 backdrop-blur-sm border-slate-800 hover:border-emerald-500/30 transition-all duration-300">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-emerald-400 font-medium tracking-wide">
                    <span className="w-1 h-6 bg-emerald-500 rounded-full inline-block mr-1"></span>
                    {isZh ? '来源引用与验证' : 'Source Citations & Verification'}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {report.citations.map((citation, idx) => (
                    <div key={idx} className="bg-slate-950/50 rounded-lg border border-slate-800 p-4 transition-all duration-300 hover:border-slate-700 hover:bg-slate-900/80 group">
                      <div className="flex gap-4 items-start">
                        <div className="mt-0.5 shrink-0 bg-slate-900 p-1.5 rounded-full border border-slate-800 shadow-sm">
                          {citation.verificationStatus === 'VERIFIED' ? (
                            <span title={isZh ? "已验证" : "Verified in source text"} className="text-emerald-500 text-lg drop-shadow-[0_0_5px_rgba(16,185,129,0.5)]">✅</span>
                          ) : citation.verificationStatus === 'UNVERIFIED' ? (
                            <span title={isZh ? "未验证" : "Unverified / Low confidence"} className="text-yellow-500 text-lg">⚠️</span>
                          ) : citation.verificationStatus === 'NOT_FOUND' ? (
                            <span title={isZh ? "未找到 (可能包含幻觉)" : "Not found in source text (Possible Hallucination)"} className="text-red-500 text-lg">❌</span>
                          ) : (
                            <span title={isZh ? "无验证数据" : "No verification data"} className="text-slate-500 text-lg">❓</span>
                          )}
                        </div>
                        <div className="flex-1 space-y-3">
                          <div className="relative">
                            <span className="absolute -left-2 -top-2 text-3xl text-slate-800 font-serif select-none">“</span>
                            <p className="text-sm text-slate-300 leading-relaxed italic relative z-10 pl-2">
                              {(isZh && citation.excerptZh) ? citation.excerptZh : citation.excerpt}
                            </p>
                            <span className="absolute -bottom-4 right-0 text-3xl text-slate-800 font-serif select-none rotate-180">“</span>
                          </div>

                          <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800/50 mt-2">
                            <span className="text-[10px] font-bold text-emerald-500/70 uppercase tracking-wider bg-emerald-950/20 px-2 py-0.5 rounded border border-emerald-900/30">
                              {isZh ? '来源' : 'SOURCE'}
                            </span>
                            <p className="text-xs font-medium text-slate-500 uppercase tracking-widest">
                              {citation.section}
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
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
              <p className="text-slate-500 text-lg">{isZh ? '输入股票代码并点击“开始分析”' : 'Enter a ticker symbol and click Analyze to get started'}</p>
            </CardContent>
          </Card>
        )}

      </div>
    </div>
  );
}
