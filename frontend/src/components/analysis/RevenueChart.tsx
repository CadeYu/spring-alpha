'use client';

import { Bar, BarChart, ResponsiveContainer, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface RevenueChartProps {
    ticker?: string;
}

// Mock historical data for demonstration
const MOCK_HISTORY: Record<string, any[]> = {
    'AAPL': [
        { period: 'Q1 24', revenue: 119.58, income: 33.92 },
        { period: 'Q2 24', revenue: 90.75, income: 23.64 },
        { period: 'Q3 24', revenue: 85.78, income: 21.45 },
        { period: 'Q4 24', revenue: 94.93, income: 22.96 },
    ],
    'MSFT': [
        { period: 'Q3 24', revenue: 61.86, income: 21.94 },
        { period: 'Q4 24', revenue: 64.73, income: 22.04 },
        { period: 'Q1 25', revenue: 65.59, income: 24.67 },
        { period: 'Q2 25', revenue: 62.02, income: 21.87 },
    ],
    'TSLA': [
        { period: 'Q4 23', revenue: 25.17, income: 7.93 },
        { period: 'Q1 24', revenue: 21.30, income: 1.13 },
        { period: 'Q2 24', revenue: 25.50, income: 1.48 },
        { period: 'Q3 24', revenue: 25.18, income: 2.17 },
    ]
};

export function RevenueChart({ ticker = 'AAPL' }: RevenueChartProps) {
    const data = MOCK_HISTORY[ticker] || MOCK_HISTORY['AAPL'];

    return (
        <Card className="bg-slate-900 border-slate-800">
            <CardHeader className="border-b border-slate-800">
                <CardTitle className="text-emerald-400">📊 Revenue Trend (Last 4 Quarters)</CardTitle>
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
                            tickFormatter={(value) => `$${value}B`}
                        />
                        <Tooltip
                            contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', color: '#f8fafc' }}
                            itemStyle={{ color: '#f8fafc' }}
                            formatter={(value: any) => [`$${value}B`, '']}
                        />
                        <Bar dataKey="revenue" name="Revenue" fill="#10b981" radius={[4, 4, 0, 0]} barSize={40} />
                        <Bar dataKey="income" name="Net Income" fill="#3b82f6" radius={[4, 4, 0, 0]} barSize={40} />
                    </BarChart>
                </ResponsiveContainer>
                <p className="text-slate-500 text-xs mt-4 text-center">
                    *Historical data is simulated for demonstration purposes
                </p>
            </CardContent>
        </Card>
    );
}
