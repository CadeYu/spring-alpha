'use client';

import { useState, useRef, useEffect } from 'react';
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Search, Loader2, TrendingUp, AlertCircle, TrendingDown } from 'lucide-react';
import { MetricCard } from '@/components/MetricCard';
import { HealthScore } from '@/components/HealthScore';
import { RiskAlerts } from '@/components/RiskAlerts';

interface MetricInsight {
  metricName: string;
  value: string;
  interpretation: string;
  sentiment: 'positive' | 'negative' | 'neutral';
}

interface BusinessDriver {
  title: string;
  description: string;
  impact: 'high' | 'medium' | 'low';
}

interface RiskFactor {
  category: string;
  description: string;
  severity: 'high' | 'medium' | 'low';
}

interface AnalysisReport {
  executiveSummary: string;
  keyMetrics: MetricInsight[];
  businessDrivers: BusinessDriver[];
  riskFactors: RiskFactor[];
  bullCase: string;
  bearCase: string;
  metadata: {
    modelName: string;
    generatedAt: string;
    language: string;
  };
}

export default function Home() {
  const [ticker, setTicker] = useState('AAPL');
  const [lang, setLang] = useState('en');
  const [report, setReport] = useState<AnalysisReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleSearch = async () => {
    if (!ticker) return;

    setIsLoading(true);
    setReport(null);
    setError(null);

    try {
      console.log(`Fetching analysis for ${ticker} in ${lang}...`);
      const response = await fetch(`/api/java/sec/analyze/${ticker}?lang=${lang}`);
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
            AI Earnings Analyst <span className="text-xs bg-slate-800 px-2 py-1 rounded text-slate-400">v2.0</span>
          </h1>
        </div>

        {/* Search Bar */}
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-4 flex gap-2">
            <Input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
              placeholder="Enter Ticker (e.g., AAPL, MSFT, TSLA)"
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
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Search className="w-4 h-4 mr-2" /> Analyze</>}
            </Button>
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
          <>
            {/* Executive Summary */}
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader className="border-b border-slate-800">
                <CardTitle className="text-emerald-400">📊 Executive Summary</CardTitle>
              </CardHeader>
              <CardContent className="p-6">
                <p className="text-slate-300 text-lg leading-relaxed">{report.executiveSummary}</p>
                <p className="text-slate-500 text-xs mt-4">
                  Generated by {report.metadata.modelName} at {new Date(report.metadata.generatedAt).toLocaleString()}
                </p>
              </CardContent>
            </Card>

            {/* Key Metrics */}
            {report.keyMetrics && report.keyMetrics.length > 0 && (
              <div>
                <h2 className="text-xl font-semibold text-emerald-300 mb-4">💰 Key Financial Metrics</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {report.keyMetrics.map((metric, idx) => (
                    <Card key={idx} className="bg-slate-900 border-slate-800">
                      <CardContent className="p-4">
                        <div className="flex items-start justify-between">
                          <div className="flex-1">
                            <h3 className="text-sm font-medium text-slate-400">{metric.metricName}</h3>
                            <p className="text-2xl font-bold text-emerald-400 mt-1">{metric.value}</p>
                          </div>
                          <div className={`p-2 rounded ${metric.sentiment === 'positive' ? 'bg-green-900/30 text-green-400' :
                              metric.sentiment === 'negative' ? 'bg-red-900/30 text-red-400' :
                                'bg-slate-800 text-slate-400'
                            }`}>
                            {metric.sentiment === 'positive' ? '📈' : metric.sentiment === 'negative' ? '📉' : '➡️'}
                          </div>
                        </div>
                        <p className="text-sm text-slate-400 mt-3">{metric.interpretation}</p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              </div>
            )}

            {/* Business Drivers & Risks */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Business Drivers */}
              {report.businessDrivers && report.businessDrivers.length > 0 && (
                <Card className="bg-slate-900 border-slate-800">
                  <CardHeader className="border-b border-slate-800">
                    <CardTitle className="text-emerald-400">🚀 Business Drivers</CardTitle>
                  </CardHeader>
                  <CardContent className="p-6 space-y-4">
                    {report.businessDrivers.map((driver, idx) => (
                      <div key={idx} className="border-l-4 border-emerald-500 pl-4">
                        <h4 className="font-semibold text-white">{driver.title}</h4>
                        <p className="text-sm text-slate-400 mt-1">{driver.description}</p>
                        <span className={`text-xs mt-2 inline-block px-2 py-1 rounded ${driver.impact === 'high' ? 'bg-emerald-900/30 text-emerald-400' :
                            driver.impact === 'medium' ? 'bg-yellow-900/30 text-yellow-400' :
                              'bg-slate-800 text-slate-400'
                          }`}>
                          Impact: {driver.impact}
                        </span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}

              {/* Risk Factors */}
              {report.riskFactors && report.riskFactors.length > 0 && (
                <Card className="bg-slate-900 border-slate-800">
                  <CardHeader className="border-b border-slate-800">
                    <CardTitle className="text-red-400">⚠️ Risk Factors</CardTitle>
                  </CardHeader>
                  <CardContent className="p-6 space-y-4">
                    {report.riskFactors.map((risk, idx) => (
                      <div key={idx} className="border-l-4 border-red-500 pl-4">
                        <h4 className="font-semibold text-white">{risk.category}</h4>
                        <p className="text-sm text-slate-400 mt-1">{risk.description}</p>
                        <span className={`text-xs mt-2 inline-block px-2 py-1 rounded ${risk.severity === 'high' ? 'bg-red-900/30 text-red-400' :
                            risk.severity === 'medium' ? 'bg-yellow-900/30 text-yellow-400' :
                              'bg-slate-800 text-slate-400'
                          }`}>
                          Severity: {risk.severity}
                        </span>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              )}
            </div>

            {/* Bull/Bear Cases */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <Card className="bg-green-900/10 border-green-800">
                <CardHeader className="border-b border-green-800">
                  <CardTitle className="text-green-400">🐂 Bull Case</CardTitle>
                </CardHeader>
                <CardContent className="p-6">
                  <p className="text-slate-300">{report.bullCase}</p>
                </CardContent>
              </Card>

              <Card className="bg-red-900/10 border-red-800">
                <CardHeader className="border-b border-red-800">
                  <CardTitle className="text-red-400">🐻 Bear Case</CardTitle>
                </CardHeader>
                <CardContent className="p-6">
                  <p className="text-slate-300">{report.bearCase}</p>
                </CardContent>
              </Card>
            </div>
          </>
        )}

        {/* Empty State */}
        {!report && !isLoading && !error && (
          <Card className="bg-slate-900 border-slate-800 min-h-[400px] flex items-center justify-center">
            <CardContent className="text-center">
              <TrendingUp className="w-16 h-16 text-slate-700 mx-auto mb-4" />
              <p className="text-slate-500 text-lg">Enter a ticker symbol and click Analyze to get started</p>
            </CardContent>
          </Card>
        )}

      </div>
    </div>
  );
}
