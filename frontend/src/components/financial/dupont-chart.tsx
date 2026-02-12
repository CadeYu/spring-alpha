import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DuPontAnalysis } from '@/types/AnalysisReport';
import { Activity, CircleDollarSign, Scale } from 'lucide-react';

interface DuPontChartProps {
    data: DuPontAnalysis;
    lang?: string;
}

export function DuPontChart({ data, lang = 'en' }: DuPontChartProps) {
    if (!data) return null;

    const isZh = lang === 'zh';

    return (
        <Card className="col-span-1 md:col-span-3 bg-slate-900/50 backdrop-blur-sm border-slate-800 hover:border-emerald-500/30 transition-all duration-300">
            <CardHeader>
                <CardTitle className="text-emerald-400 flex items-center gap-2">
                    <Activity className="w-5 h-5" />
                    {isZh ? '杜邦分析 (ROE 拆解)' : 'DuPont Analysis (ROE Decomposition)'}
                </CardTitle>
            </CardHeader>
            <CardContent>
                <div className="flex flex-col md:flex-row items-center justify-between gap-4 py-6">

                    {/* Return On Equity (Result) */}
                    <div className="flex-1 w-full relative group">
                        <div className="absolute inset-0 bg-emerald-500/10 blur-xl rounded-xl group-hover:bg-emerald-500/20 transition-all duration-500" />
                        <Card className="relative border-emerald-500/50 bg-slate-950/80 backdrop-blur-md shadow-lg shadow-emerald-500/10">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium text-emerald-400 uppercase tracking-wider">
                                    {isZh ? '净资产收益率 (ROE)' : 'Return on Equity'}
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="text-3xl font-bold text-white tabular-nums">{data.returnOnEquity}</div>
                                <p className="text-xs text-slate-500 mt-1">ROE</p>
                            </CardContent>
                        </Card>
                    </div>

                    <div className="text-2xl text-slate-700 font-light">=</div>

                    {/* Net Profit Margin */}
                    <div className="flex-1 w-full relative group">
                        <Card className="bg-slate-950/50 border-slate-800 hover:border-slate-700 transition-all duration-300">
                            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                                <CardTitle className="text-sm font-medium text-slate-400">
                                    {isZh ? '销售净利率' : 'Net Margin'}
                                </CardTitle>
                                <CircleDollarSign className="h-4 w-4 text-emerald-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-slate-200 tabular-nums">{data.netProfitMargin}</div>
                                <p className="text-xs text-slate-500 mt-1">{isZh ? '盈利能力' : 'Profitability'}</p>
                            </CardContent>
                        </Card>
                    </div>

                    <div className="text-xl text-slate-700 font-light">×</div>

                    {/* Asset Turnover */}
                    <div className="flex-1 w-full relative group">
                        <Card className="bg-slate-950/50 border-slate-800 hover:border-slate-700 transition-all duration-300">
                            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                                <CardTitle className="text-sm font-medium text-slate-400">
                                    {isZh ? '资产周转率' : 'Asset Turnover'}
                                </CardTitle>
                                <Activity className="h-4 w-4 text-blue-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-slate-200 tabular-nums">{data.assetTurnover}</div>
                                <p className="text-xs text-slate-500 mt-1">{isZh ? '营运效率' : 'Efficiency'}</p>
                            </CardContent>
                        </Card>
                    </div>

                    <div className="text-xl text-slate-700 font-light">×</div>

                    {/* Equity Multiplier */}
                    <div className="flex-1 w-full relative group">
                        <Card className="bg-slate-950/50 border-slate-800 hover:border-slate-700 transition-all duration-300">
                            <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0">
                                <CardTitle className="text-sm font-medium text-slate-400">
                                    {isZh ? '权益乘数' : 'Equity Multiplier'}
                                </CardTitle>
                                <Scale className="h-4 w-4 text-purple-500" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-slate-200 tabular-nums">{data.equityMultiplier}</div>
                                <p className="text-xs text-slate-500 mt-1">{isZh ? '杠杆水平' : 'Leverage'}</p>
                            </CardContent>
                        </Card>
                    </div>
                </div>

                <div className="mt-2 p-4 bg-slate-950/30 rounded-lg text-sm text-slate-400 border border-slate-800/50 flex gap-3 items-start">
                    <span className="text-lg">💡</span>
                    <span className="italic leading-relaxed">{data.interpretation}</span>
                </div>
            </CardContent>
        </Card>
    );
}
