"use client"

import { useEffect, useState } from "react"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export interface HistoricalDataPoint {
    period: string
    grossMargin: number
    operatingMargin: number
    netMargin: number
}

interface MarginAnalysisProps {
    ticker: string
}

export function MarginAnalysisChart({ ticker }: MarginAnalysisProps) {
    const [data, setData] = useState<HistoricalDataPoint[]>([])
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        async function fetchData() {
            if (!ticker) return

            try {
                // Using the new history endpoint
                const res = await fetch(`http://localhost:8081/api/sec/history/${ticker}`)
                if (res.ok) {
                    const json = await res.json()
                    // Convert decimal to percentage for better display (0.45 -> 45)
                    const formatted = json.map((item: any) => ({
                        period: item.period,
                        grossMargin: (item.grossMargin * 100).toFixed(1),
                        operatingMargin: (item.operatingMargin * 100).toFixed(1),
                        netMargin: (item.netMargin * 100).toFixed(1)
                    }))
                    setData(formatted)
                }
            } catch (error) {
                console.error("Failed to fetch margin history", error)
            } finally {
                setLoading(false)
            }
        }

        fetchData()
    }, [ticker])

    if (loading || data.length === 0) {
        return null // Don't render empty chart if no data (e.g. for non-AAPL mock)
    }

    return (
        <Card className="border-slate-800 bg-slate-900">
            <CardHeader className="border-b border-slate-800">
                <CardTitle className="text-emerald-400">Margin Trend Analysis (Last 5 Quarters)</CardTitle>
                <CardDescription className="text-slate-400">
                    Tracking the profitability efficiency over time.
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
                                name="Net Margin"
                                stroke="#8b5cf6" // Purple
                                strokeWidth={2}
                                dot={{ r: 4, strokeWidth: 0, fill: "#8b5cf6" }}
                                activeDot={{ r: 6, strokeWidth: 0 }}
                            />
                            <Line
                                type="monotone"
                                dataKey="grossMargin"
                                name="Gross Margin"
                                stroke="#34d399" // emerald-400
                                strokeWidth={2}
                                dot={{ r: 4, strokeWidth: 0, fill: "#34d399" }}
                                activeDot={{ r: 6, strokeWidth: 0 }}
                            />
                            <Line
                                type="monotone"
                                dataKey="operatingMargin"
                                name="Operating Margin"
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


