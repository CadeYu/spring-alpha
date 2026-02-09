'use client';

import { useState, useRef, useEffect } from 'react';
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Search, Loader2, TrendingUp, AlertCircle, TrendingDown, Bot } from 'lucide-react';
import { MetricCard } from '@/components/MetricCard';
import { HealthScore } from '@/components/HealthScore';
import { RiskAlerts } from '@/components/RiskAlerts';
import { ExecutiveSummary } from '@/components/analysis/ExecutiveSummary';
import { KeyMetrics } from '@/components/analysis/KeyMetrics';
import { BusinessDrivers } from '@/components/analysis/BusinessDrivers';
import { RiskFactors } from '@/components/analysis/RiskFactors';
import { BullBearCase } from '@/components/analysis/BullBearCase';
import { AnalysisReport } from '@/types/AnalysisReport';

// Available AI models for analysis
const AI_MODELS = [
  { id: 'groq', name: 'Groq Llama 3.3', icon: '⚡', description: 'Fast & Free' },
  { id: 'openai', name: 'OpenAI GPT-4', icon: '🧠', description: 'Most Capable' },
  { id: 'gemini', name: 'Google Gemini', icon: '💎', description: 'Balanced' },
  { id: 'enhanced-mock', name: 'Mock (Testing)', icon: '🔧', description: 'No API' },
];

export default function Home() {
  const [ticker, setTicker] = useState('AAPL');
  const [lang, setLang] = useState('en');
  const [model, setModel] = useState('groq');
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
            AI Earnings Analyst <span className="text-xs bg-slate-800 px-2 py-1 rounded text-slate-400">v2.0</span>
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
            </div>

            {/* Row 2: Model Selector */}
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-slate-500" />
              <span className="text-xs text-slate-500">AI Model:</span>
              <div className="flex gap-2 flex-1">
                {AI_MODELS.map((m) => (
                  <button
                    key={m.id}
                    onClick={() => setModel(m.id)}
                    className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${model === m.id
                        ? 'bg-emerald-600 text-white'
                        : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
                      }`}
                    title={m.description}
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
            />

            <KeyMetrics metrics={report.keyMetrics} ticker={ticker} />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <BusinessDrivers drivers={report.businessDrivers} />
              <RiskFactors risks={report.riskFactors} />
            </div>

            <BullBearCase
              bullCase={report.bullCase}
              bearCase={report.bearCase}
            />
          </div>
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
