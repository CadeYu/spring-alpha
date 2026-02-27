"use client"

import { useMemo } from "react"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export interface HistoricalDataPoint {
    period: string
    grossMargin: number | string
    operatingMargin: number | string
    netMargin: number | string
    revenue?: number
    netIncome?: number
}

interface MarginAnalysisProps {
    ticker: string;
    lang?: string;
    data?: any[];
    loading?: boolean;
}

export function MarginAnalysisChart({ ticker, lang = 'en', data: rawData = [], loading = false }: MarginAnalysisProps) {
    // useMemo: 数据转换同步完成，避免 useEffect 的额外渲染周期导致图表闪烁/消失
    const data = useMemo(() => {
        if (rawData.length === 0) return [];
        return rawData.map((item: any) => ({
            period: item.period,
            grossMargin: (Number(item.grossMargin) * 100).toFixed(1),
            operatingMargin: (Number(item.operatingMargin) * 100).toFixed(1),
            netMargin: (Number(item.netMargin) * 100).toFixed(1)
        }));
    }, [rawData]);

    const isZh = lang === 'zh';

    if (loading || data.length === 0) {
        return null
    }

    return (
        <Card className="border-slate-800 bg-slate-900">
            <CardHeader className="border-b border-slate-800">
                <CardTitle className="text-emerald-400">{isZh ? '利润率趋势分析 (近5年)' : 'Margin Trend Analysis (Last 5 Years)'}</CardTitle>
                <CardDescription className="text-slate-400">
                    {isZh ? '追踪盈利效率随时间的变化' : 'Tracking the profitability efficiency over time.'}
                </CardDescription>
            </CardHeader>
            <CardContent className="h-[400px] p-6">
                <div className="h-full w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={data}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#334155" vertical={false} />
                            <XAxis
                                dataKey="period"
                                stroke="#94a3b8"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                dy={10}
                            />
                            <YAxis
                                stroke="#94a3b8"
                                fontSize={12}
                                tickLine={false}
                                axisLine={false}
                                tickFormatter={(value) => `${value}%`}
                                dx={-10}
                            />
                            <Tooltip
                                contentStyle={{ backgroundColor: '#0f172a', borderColor: '#1e293b', color: '#f8fafc' }}
                                itemStyle={{ color: '#f8fafc' }}
                                formatter={(value: any) => [`${value}%`, '']}
                            />
                            <Legend wrapperStyle={{ paddingTop: '20px' }} />
                            <Line
                                type="monotone"
                                dataKey="netMargin"
                                name={isZh ? "净利率" : "Net Margin"}
                                stroke="#8b5cf6" // Purple
                                strokeWidth={2}
                                dot={{ r: 4, strokeWidth: 0, fill: "#8b5cf6" }}
                                activeDot={{ r: 6, strokeWidth: 0 }}
                            />
                            <Line
                                type="monotone"
                                dataKey="grossMargin"
                                name={isZh ? "毛利率" : "Gross Margin"}
                                stroke="#34d399" // emerald-400
                                strokeWidth={2}
                                dot={{ r: 4, strokeWidth: 0, fill: "#34d399" }}
                                activeDot={{ r: 6, strokeWidth: 0 }}
                            />
                            <Line
                                type="monotone"
                                dataKey="operatingMargin"
                                name={isZh ? "营业利润率" : "Operating Margin"}
                                stroke="#2dd4bf" // teal-400
                                strokeWidth={2}
                                dot={{ r: 4, strokeWidth: 0, fill: "#2dd4bf" }}
                                activeDot={{ r: 6, strokeWidth: 0 }}
                            />
                        </LineChart>
                    </ResponsiveContainer>
                </div>
            </CardContent>
        </Card>
    )
}


