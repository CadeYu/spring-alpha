"use client"

import React, { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts';
import { FactorBridgeItem } from '@/types/AnalysisReport';

interface WaterfallChartProps {
    title: string;
    data: FactorBridgeItem[];
    lang?: string;
}

// ... ChartData interface ...

export function WaterfallChart({ title, data, lang = 'en' }: WaterfallChartProps) {
    const chartData = useMemo(() => processWaterfallData(data, lang), [data, lang]);
    const isZh = lang === 'zh';

    if (!data || data.length === 0) return null;

    return (
        <Card className="col-span-1 min-h-[400px] bg-slate-900/50 backdrop-blur-sm border-slate-800 hover:border-emerald-500/30 transition-all duration-300">
            <CardHeader>
                <CardTitle className="text-emerald-400 font-medium tracking-wide flex items-center gap-2">
                    <span className="w-1 h-6 bg-emerald-500 rounded-full inline-block mr-1"></span>
                    {title}
                </CardTitle>
            </CardHeader>
            <CardContent className="h-[320px] w-full pt-4">
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 20, right: 30, left: 10, bottom: 5 }}>
                        <XAxis
                            dataKey="name"
                            axisLine={false}
                            tickLine={false}
                            tick={{ fill: '#64748b', fontSize: 11, fontWeight: 500 }}
                            interval={0}
                        />
                        <YAxis hide />
                        <Tooltip content={<CustomTooltip lang={lang} />} cursor={{ fill: 'rgba(16, 185, 129, 0.05)' }} />
                        <ReferenceLine y={0} stroke="#334155" strokeDasharray="3 3" />
                        <Bar dataKey="value" stackId="a" fill="transparent" /> {/* Invisible spacer */}
                        <Bar dataKey="barHeight" stackId="a" radius={[4, 4, 4, 4]}>
                            {chartData.map((entry, index) => (
                                <Cell key={`cell-${index}`} fill={entry.color} strokeWidth={0} />
                            ))}
                        </Bar>
                    </BarChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    );
}

// Logic to process the waterfall data
function processWaterfallData(items: FactorBridgeItem[], lang: string): any[] {
    let currentTotal = 0;
    const processed = [];
    const isZh = lang === 'zh';

    // Start with a base of 0 or previous total (simplified for this bridge)
    // We treat "impact" as delta.

    for (const item of items) {
        let numericValue = 0;
        let isQualitative = false;
        let color = "#64748b"; // slate-500 (neutral)

        // 1. Try to parse number (e.g., "+5%", "-2.3%")
        const sanitized = item.impact.replace('%', '');
        const parsed = parseFloat(sanitized);

        if (!isNaN(parsed)) {
            numericValue = parsed;
        } else {
            // 2. Handle Qualitative: + or -
            isQualitative = true;
            if (item.impact.includes('+')) numericValue = 2; // Arbitrary visual height for qualitative pos
            else if (item.impact.includes('-')) numericValue = -2; // Arbitrary visual height for qualitative neg
            else numericValue = 0.5; // Neutral/Flat
        }

        // Determine Color
        if (numericValue > 0) color = "#10b981"; // emerald-500
        else if (numericValue < 0) color = "#ef4444"; // red-500

        // Calculate Waterfall positions
        const prevTotal = currentTotal;
        currentTotal += numericValue;

        // For Recharts stacked bar trick:
        // We need "value" (floating bottom) and "barHeight" (actual bar length)
        // If val is positive: starts at prevTotal, height is val
        // If val is negative: starts at prevTotal + val (which is currentTotal), height is abs(val)

        let bottom = 0;
        let height = 0;

        if (numericValue >= 0) {
            bottom = prevTotal;
            height = numericValue;
        } else {
            bottom = currentTotal;
            height = Math.abs(numericValue);
        }

        processed.push({
            name: item.name,
            value: bottom, // The invisible stack
            barHeight: height, // The colored bar
            color: color,
            originalImpact: item.impact,
            description: item.description,
            isQualitative
        });
    }

    // Optional: Add a "Total" bar at the end? 
    // For bridge analysis usually we show the Cumulative result.
    // Let's add a "Net Impact" column
    processed.push({
        name: isZh ? "净影响" : "Net Impact",
        value: 0,
        barHeight: currentTotal,
        color: currentTotal >= 0 ? "#3b82f6" : "#f59e0b", // Blue or Amber
        originalImpact: currentTotal.toFixed(1) + (processed.some(p => p.isQualitative) ? (isZh ? " (估)" : " (Est)") : "%"),
        description: isZh ? "所有因素的累积效应" : "Cumulative effect of all factors",
        isQualitative: false
    });

    return processed;
}

const CustomTooltip = ({ active, payload, label, lang = 'en' }: any) => {
    if (active && payload && payload.length) {
        const data = payload[1].payload; // Access the main data payload (second item in stack)
        const isZh = lang === 'zh';
        return (
            <div className="bg-slate-900/95 border border-slate-700 p-3 rounded-lg shadow-xl text-slate-200 backdrop-blur-md">
                <p className="font-semibold mb-1 text-slate-100">{label}</p>
                <div className="flex items-center gap-2 mb-2">
                    <span className={`text-lg font-bold ${data.barHeight >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {data.originalImpact}
                    </span>
                    <span className="text-xs text-slate-500 uppercase tracking-wider font-medium">{isZh ? '影响' : 'Impact'}</span>
                </div>
                <p className="text-xs text-slate-400 w-56 leading-relaxed">
                    {data.description}
                </p>
            </div>
        );
    };
    return null;
};
