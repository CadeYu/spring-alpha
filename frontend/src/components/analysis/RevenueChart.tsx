'use client';

import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import type { HistoricalDataPoint } from "./MarginAnalysisChart";

interface RevenueChartProps {
    ticker?: string;
    lang?: string;
    currency?: string;
    data?: HistoricalDataPoint[];
    loading?: boolean;
}

export function RevenueChart({ lang = 'en', currency = 'USD', data = [] }: RevenueChartProps) {
    const isZh = lang === 'zh';

    // Determine symbol
    let symbol = '$';
    if (currency === 'JPY') symbol = '¥';
    else if (currency === 'EUR') symbol = '€';
    else if (currency === 'CNY') symbol = '¥';
    else if (currency === 'GBP') symbol = '£';
    else if (currency !== 'USD' && currency.length === 3) symbol = currency + ' ';

    // Internal fetch removed in favor of parent hoisting to avoid race conditions

    return (
        <Card className="bg-slate-900 border-slate-800">
            <CardHeader className="border-b border-slate-800">
                <CardTitle className="text-emerald-400">📊 {isZh ? '营收趋势 (近5年)' : 'Revenue Trend (Last 5 Years)'}</CardTitle>
                <CardDescription className="text-slate-400">
                    {isZh ? '年度营收与净利润表现' : 'Annual revenue and net income performance.'}
                </CardDescription>
            </CardHeader>
            <CardContent className="h-[400px] p-6">
                <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={data}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                        <XAxis
                            dataKey="period"
                            stroke="#94a3b8"
                            fontSize={12}
                            tickLine={false}
                            axisLine={false}
                        />
                        <YAxis
                            stroke="#94a3b8"
                            fontSize={12}
                            tickLine={false}
                            axisLine={false}
                            tickFormatter={(value) => `${symbol}${(value / 1000000000).toFixed(0)}B`}
                        />
                        <Tooltip
                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', color: '#f8fafc' }}
                            itemStyle={{ color: '#f8fafc' }}
                            formatter={(value: number | string | undefined) => {
                                const numericValue = Number(value);
                                return [`${symbol}${(numericValue / 1000000000).toFixed(2)}B`, ''];
                            }}
                        />
                        <Bar dataKey="revenue" name={isZh ? "营收" : "Revenue"} fill="#10b981" radius={[4, 4, 0, 0]} barSize={40} />
                        <Bar dataKey="netIncome" name={isZh ? "净利润" : "Net Income"} fill="#3b82f6" radius={[4, 4, 0, 0]} barSize={40} />
                    </BarChart>
                </ResponsiveContainer>
            </CardContent>
        </Card>
    );
}
