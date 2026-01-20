'use client';

import { useState, useRef, useEffect } from 'react';
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";
import ReactMarkdown from 'react-markdown';
import { Search, Loader2, TrendingUp } from 'lucide-react';

export default function Home() {
  const [ticker, setTicker] = useState('AAPL');
  const [analysis, setAnalysis] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const handleSearch = async () => {
    if (!ticker) return;
    
    setIsLoading(true);
    setAnalysis(''); // 清空旧数据

    try {
      console.log("Starting fetch...");
      // 使用 Next.js 代理转发，解决 CORS 和 Mixed Content 问题
      const response = await fetch(`/api/java/sec/analyze/${ticker}`);
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
              className="bg-slate-950 border-slate-700 text-lg font-bold tracking-widest text-emerald-300"
            />
            <Button 
              onClick={handleSearch} 
              disabled={isLoading}
              className="bg-emerald-600 hover:bg-emerald-700 text-white min-w-[120px]"
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <><Search className="w-4 h-4 mr-2" /> Analyze</>}
            </Button>
          </CardContent>
        </Card>

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
                      h1: ({node, ...props}) => <h1 className="text-2xl font-bold text-emerald-400 mt-6 mb-4" {...props} />,
                      h2: ({node, ...props}) => <h2 className="text-xl font-semibold text-emerald-300 mt-5 mb-3 border-b border-slate-700 pb-2" {...props} />,
                      h3: ({node, ...props}) => <h3 className="text-lg font-medium text-emerald-200 mt-4 mb-2" {...props} />,
                      p: ({node, ...props}) => <p className="mb-4 text-slate-300" {...props} />,
                      ul: ({node, ...props}) => <ul className="list-disc list-inside mb-4 space-y-1" {...props} />,
                      ol: ({node, ...props}) => <ol className="list-decimal list-inside mb-4 space-y-1" {...props} />,
                      li: ({node, ...props}) => <li className="ml-2" {...props} />,
                      strong: ({node, ...props}) => <strong className="text-white font-bold" {...props} />,
                      blockquote: ({node, ...props}) => <blockquote className="border-l-4 border-emerald-500 pl-4 italic text-slate-400 my-4" {...props} />,
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
