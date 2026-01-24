'use client';

import { useState, useRef, useEffect } from 'react';
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import ReactMarkdown from 'react-markdown';
import { Search, Loader2, TrendingUp } from 'lucide-react';
import { MetricCard } from '@/components/MetricCard';
import { HealthScore } from '@/components/HealthScore';
import { RiskAlerts } from '@/components/RiskAlerts';

export default function Home() {
  const [ticker, setTicker] = useState('AAPL');
  const [lang, setLang] = useState('en'); // 默认英文
  const [analysis, setAnalysis] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleSearch = async () => {
    if (!ticker) return;

    setIsLoading(true);
    setAnalysis('');

    try {
      console.log(`Starting fetch for ${ticker} in ${lang}...`);
      // 传递 lang 参数给后端
      const response = await fetch(`/api/java/sec/analyze/${ticker}?lang=${lang}`);
      console.log("Response status:", response.status);

      if (!response.ok || !response.body) {
        throw new Error(`Network response error: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        console.log("Raw Chunk:", JSON.stringify(chunk)); // 打印原始数据，方便调试

        const lines = chunk.split('\n');
        let buffer = '';

        for (const line of lines) {
          if (line.startsWith('data:')) {
            const jsonStr = line.substring(5).trim();
            if (!jsonStr) continue;

            try {
              const data = JSON.parse(jsonStr);
              if (data.text) {
                buffer += data.text;
              }
            } catch (e) {
              console.warn("JSON parse error:", e);
            }
          }
        }

        if (buffer) {
          setAnalysis(prev => prev + buffer);
        }
      }
    } catch (error) {
      console.error("Fetch Error:", error);
      // 显示具体的错误信息到界面上
      setAnalysis(prev => prev + `\n\n❌ Connection Failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setIsLoading(false);
    }
  };

  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      const scrollElement = scrollRef.current.querySelector('[data-radix-scroll-area-viewport]');
      if (scrollElement) {
        scrollElement.scrollTop = scrollElement.scrollHeight;
      }
    }
  }, [analysis]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200 p-8 font-mono">
      <div className="max-w-4xl mx-auto space-y-6">

        {/* Header */}
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold flex items-center gap-2 text-emerald-400">
            <TrendingUp className="w-8 h-8" />
            Spring Alpha <span className="text-xs bg-slate-800 px-2 py-1 rounded text-slate-400">PROTOTYPE</span>
          </h1>
        </div>

        {/* Search Bar */}
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-4 flex gap-2">
            <Input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder="Enter Ticker (e.g., AAPL, TSLA, NVDA)"
              className="bg-slate-950 border-slate-700 text-lg font-bold tracking-widest text-emerald-300 flex-1"
            />

            {/* Language Selector */}
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

        {/* 数据可视化区域 - 只在有分析结果时显示 */}
        {analysis && (
          <>
            {/* 关键指标卡片 */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <MetricCard
                title="营收"
                value="$895"
                unit="亿"
                change={6.2}
                icon="revenue"
              />
              <MetricCard
                title="净利润"
                value="$234"
                unit="亿"
                change={8.1}
                icon="profit"
              />
              <MetricCard
                title="毛利率"
                value="44.1"
                unit="%"
                change={1.2}
                icon="growth"
              />
              <MetricCard
                title="同比增长"
                value="8.5"
                unit="%"
                change={2.3}
                icon="growth"
              />
            </div>

            {/* 健康度 + 风险提示 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* 健康度评分 */}
              <HealthScore score={85} />

              {/* 风险提示 */}
              <div className="bg-slate-900/50 backdrop-blur-sm border border-slate-800 rounded-lg p-6">
                <RiskAlerts
                  risks={[
                    {
                      level: 'medium',
                      message: '应收账款周转天数增长 22 天，需关注回款情况',
                    },
                    {
                      level: 'low',
                      message: '研发支出占比 9.2%，高于行业平均 6.5%',
                    },
                  ]}
                />
              </div>
            </div>
          </>
        )}

        {/* Analysis Result */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* Main Text Report */}
          <Card className="md:col-span-3 bg-slate-900 border-slate-800 min-h-[500px]">
            <CardHeader className="border-b border-slate-800 pb-3">
              <CardTitle className="text-emerald-400 flex items-center gap-2">
                📄 AI Analyst Report
                {isLoading && <span className="text-xs text-slate-500 animate-pulse">Typing...</span>}
              </CardTitle>
            </CardHeader>
            <ScrollArea className="h-[600px] p-6" ref={scrollRef}>
              {/* 强制文字颜色为浅灰/白色，覆盖默认样式 */}
              <div className="text-slate-300 space-y-4 leading-relaxed">
                {analysis ? (
                  <ReactMarkdown
                    components={{
                      // 自定义 Markdown 组件样式
                      h1: ({ node, ...props }) => <h1 className="text-2xl font-bold text-emerald-400 mt-6 mb-4" {...props} />,
                      h2: ({ node, ...props }) => <h2 className="text-xl font-semibold text-emerald-300 mt-5 mb-3 border-b border-slate-700 pb-2" {...props} />,
                      h3: ({ node, ...props }) => <h3 className="text-lg font-medium text-emerald-200 mt-4 mb-2" {...props} />,
                      p: ({ node, ...props }) => <p className="mb-4 text-slate-300" {...props} />,
                      ul: ({ node, ...props }) => <ul className="list-disc list-inside mb-4 space-y-1" {...props} />,
                      ol: ({ node, ...props }) => <ol className="list-decimal list-inside mb-4 space-y-1" {...props} />,
                      li: ({ node, ...props }) => <li className="ml-2" {...props} />,
                      strong: ({ node, ...props }) => <strong className="text-white font-bold" {...props} />,
                      blockquote: ({ node, ...props }) => <blockquote className="border-l-4 border-emerald-500 pl-4 italic text-slate-400 my-4" {...props} />,
                    }}
                  >
                    {analysis}
                  </ReactMarkdown>
                ) : (
                  <div className="text-slate-600 text-center mt-20">
                    Waiting for data stream...
                  </div>
                )}
              </div>
            </ScrollArea>
          </Card>
        </div>

      </div>
    </div>
  );
}
