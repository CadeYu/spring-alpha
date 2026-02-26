import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TopicTrend } from "@/types/AnalysisReport";
import { motion } from "framer-motion";
import { Cloud } from "lucide-react";

interface TopicWordCloudProps {
    trends?: TopicTrend[];
    lang?: string;
}

export function TopicWordCloud({ trends, lang = 'en' }: TopicWordCloudProps) {
    if (!trends || trends.length === 0) return null;

    const title = lang === 'zh' ? "NLP 主题趋势" : "NLP Topic Trends";
    const subtitle = lang === 'zh' ? "MD&A 关键词热度与情感分析" : "Key Themes & Sentiment in MD&A";

    // Helper to determine font size class based on frequency (1-100)
    const getSizeClass = (freq: number) => {
        if (freq > 80) return "text-4xl font-bold";
        if (freq > 60) return "text-3xl font-semibold";
        if (freq > 40) return "text-2xl font-medium";
        if (freq > 20) return "text-xl";
        return "text-base";
    };

    // Helper to determine color based on sentiment
    const getColorClass = (sentiment: string) => {
        switch (sentiment?.toLowerCase()) {
            case 'positive': return "text-green-600 dark:text-green-400";
            case 'negative': return "text-red-500 dark:text-red-400";
            case 'neutral':
            default: return "text-gray-500 dark:text-gray-400";
        }
    };

    return (
        <Card className="bg-slate-900/50 backdrop-blur-sm border-slate-800 hover:border-emerald-500/30 transition-all duration-300">
            <CardHeader className="flex flex-row items-center space-y-0 pb-2">
                <div className="flex flex-col">
                    <CardTitle className="text-xl font-bold flex items-center gap-2 text-emerald-400">
                        <Cloud className="h-5 w-5 text-emerald-500" />
                        {title}
                    </CardTitle>
                    <p className="text-sm text-slate-400 mt-1">
                        {subtitle}
                    </p>
                </div>
            </CardHeader>
            <CardContent>
                <div className="flex flex-wrap gap-4 items-center justify-center min-h-[150px] p-6 bg-slate-950/30 rounded-xl border border-slate-800/50">
                    {trends.map((trend, index) => (
                        <motion.span
                            key={index}
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            transition={{ duration: 0.5, delay: index * 0.05 }}
                            className={`${getSizeClass(trend.frequency)} ${getColorClass(trend.sentiment)} cursor-pointer hover:scale-110 transition-transform duration-200 select-none drop-shadow-lg`}
                            title={`${trend.topic}: ${trend.sentiment} (Freq: ${trend.frequency})`}
                        >
                            {trend.topic}
                        </motion.span>
                    ))}
                </div>
                <div className="mt-4 flex justify-center gap-6 text-xs text-slate-500 font-medium uppercase tracking-wider">
                    <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]"></span>
                        {lang === 'zh' ? "正面" : "Positive"}
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.6)]"></span>
                        {lang === 'zh' ? "负面" : "Negative"}
                    </div>
                    <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-gray-500"></span>
                        {lang === 'zh' ? "中性" : "Neutral"}
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
