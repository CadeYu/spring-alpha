'use client';

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip } from 'recharts';
import { Shield } from 'lucide-react';

interface FinancialFacts {
    grossMargin?: number;
    netMargin?: number;
    operatingMargin?: number;
    revenueYoY?: number;
    operatingCashFlowYoY?: number;
    freeCashFlowYoY?: number;
    debtToEquityRatio?: number;
    returnOnEquity?: number;
    returnOnAssets?: number;
    priceToEarningsRatio?: number;
    priceToBookRatio?: number;
}

interface RadarDataPoint {
    dimension: string;
    score: number;
    fullMark: 100;
}

interface FinancialHealthRadarProps {
    ticker: string;
    lang?: string;
    apiBase: string;
}

/** Clamp a value between 0 and 100 */
function clamp(v: number): number {
    return Math.max(0, Math.min(100, Math.round(v)));
}

/** Scale a percentage value (e.g., 0.22 = 22%) to a 0-100 score */
function scaleGrowth(val: number | undefined, min = -0.2, max = 0.3): number {
    if (val === undefined || val === null) return 50;
    // Convert if value looks like it's already a percentage (>1 or <-1)
    const v = Math.abs(val) > 5 ? val / 100 : val;
    return clamp(((v - min) / (max - min)) * 100);
}

/** Score profitability: weighted average of margins (0-100) */
function scoreProfitability(facts: FinancialFacts): number {
    const gm = facts.grossMargin ?? 0;
    const om = facts.operatingMargin ?? 0;
    const nm = facts.netMargin ?? 0;
    // Convert from decimal (0.82) to percentage if needed
    const gross = Math.abs(gm) <= 1 ? gm * 100 : gm;
    const oper = Math.abs(om) <= 1 ? om * 100 : om;
    const net = Math.abs(nm) <= 1 ? nm * 100 : nm;
    return clamp(gross * 0.3 + oper * 0.35 + net * 0.35);
}

/** Score growth: revenue YoY + operating CF YoY */
function scoreGrowth(facts: FinancialFacts): number {
    const rev = scaleGrowth(facts.revenueYoY);
    const ocf = scaleGrowth(facts.operatingCashFlowYoY);
    return clamp(rev * 0.6 + ocf * 0.4);
}

/** Score cash flow health */
function scoreCashFlow(facts: FinancialFacts): number {
    const ocf = scaleGrowth(facts.operatingCashFlowYoY, -0.3, 0.3);
    const fcf = scaleGrowth(facts.freeCashFlowYoY, -0.3, 0.3);
    return clamp(ocf * 0.5 + fcf * 0.5);
}

/** Score leverage: lower D/E is better */
function scoreLeverage(facts: FinancialFacts): number {
    const de = facts.debtToEquityRatio ?? 0.5;
    const v = Math.abs(de) > 5 ? de / 100 : de;
    // D/E 0 → 100, D/E ≥ 2 → 0
    return clamp((1 - v / 2) * 100);
}

/** Score efficiency: ROE + ROA */
function scoreEfficiency(facts: FinancialFacts): number {
    const roe = facts.returnOnEquity ?? 0;
    const roa = facts.returnOnAssets ?? 0;
    const roeVal = Math.abs(roe) <= 1 ? roe * 100 : roe;
    const roaVal = Math.abs(roa) <= 1 ? roa * 100 : roa;
    // ROE 0% → 0, 30%+ → 100; ROA 0% → 0, 15%+ → 100
    const roeScore = clamp((roeVal / 30) * 100);
    const roaScore = clamp((roaVal / 15) * 100);
    return clamp(roeScore * 0.6 + roaScore * 0.4);
}

/** Score valuation: lower P/E and P/B is better (value investing perspective) */
function scoreValuation(facts: FinancialFacts): number {
    const pe = facts.priceToEarningsRatio ?? 25;
    const pb = facts.priceToBookRatio ?? 5;
    // P/E: 5 → 100, 50+ → 0
    const peScore = clamp(((50 - pe) / 45) * 100);
    // P/B: 1 → 100, 15+ → 0
    const pbScore = clamp(((15 - pb) / 14) * 100);
    return clamp(peScore * 0.6 + pbScore * 0.4);
}

const LABELS: Record<string, { en: string; zh: string }> = {
    profitability: { en: 'Profitability', zh: '盈利性' },
    growth: { en: 'Growth', zh: '成长性' },
    cashFlow: { en: 'Cash Flow', zh: '现金流' },
    leverage: { en: 'Leverage', zh: '杠杆安全' },
    efficiency: { en: 'Efficiency', zh: '运营效率' },
    valuation: { en: 'Valuation', zh: '估值水平' },
};

// Custom tooltip
function CustomTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: RadarDataPoint }> }) {
    if (!active || !payload?.length) return null;
    const data = payload[0].payload;
    return (
        <div className="bg-slate-900/95 backdrop-blur-sm border border-slate-700 rounded-lg px-3 py-2 shadow-xl">
            <p className="text-emerald-400 font-medium text-sm">{data.dimension}</p>
            <p className="text-white text-lg font-bold">{data.score}<span className="text-slate-400 text-xs ml-1">/ 100</span></p>
        </div>
    );
}

export function FinancialHealthRadar({ ticker, lang = 'en', apiBase }: FinancialHealthRadarProps) {
    const isZh = lang === 'zh';
    const [facts, setFacts] = useState<FinancialFacts | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!ticker || ticker.length < 1) return;
        let cancelled = false;

        async function loadFacts() {
            setLoading(true);

            try {
                const response = await fetch(`${apiBase}/financial/${ticker}`);
                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}`);
                }

                const data = await response.json() as FinancialFacts;
                if (!cancelled && data) {
                    setFacts(data);
                }
            } catch {
                // Preserve existing facts on error.
            } finally {
                if (!cancelled) {
                    setLoading(false);
                }
            }
        }

        void loadFacts();

        return () => {
            cancelled = true;
        };
    }, [ticker, apiBase]);

    // Compute radar data from facts
    const radarData: RadarDataPoint[] = facts ? [
        { dimension: LABELS.profitability[isZh ? 'zh' : 'en'], score: scoreProfitability(facts), fullMark: 100 },
        { dimension: LABELS.growth[isZh ? 'zh' : 'en'], score: scoreGrowth(facts), fullMark: 100 },
        { dimension: LABELS.cashFlow[isZh ? 'zh' : 'en'], score: scoreCashFlow(facts), fullMark: 100 },
        { dimension: LABELS.leverage[isZh ? 'zh' : 'en'], score: scoreLeverage(facts), fullMark: 100 },
        { dimension: LABELS.efficiency[isZh ? 'zh' : 'en'], score: scoreEfficiency(facts), fullMark: 100 },
        { dimension: LABELS.valuation[isZh ? 'zh' : 'en'], score: scoreValuation(facts), fullMark: 100 },
    ] : [];

    const overallScore = radarData.length > 0
        ? Math.round(radarData.reduce((sum, d) => sum + d.score, 0) / radarData.length)
        : 0;

    const scoreColor = overallScore >= 70 ? 'text-emerald-400' : overallScore >= 40 ? 'text-amber-400' : 'text-red-400';
    const scoreGlow = overallScore >= 70 ? 'shadow-emerald-500/20' : overallScore >= 40 ? 'shadow-amber-500/20' : 'shadow-red-500/20';

    if (loading || !facts) {
        return (
            <Card className="bg-slate-900/50 backdrop-blur-sm border-slate-800 border-dashed">
                <CardHeader>
                    <CardTitle className="text-emerald-400/50 flex items-center gap-2">
                        <Shield className="w-5 h-5" />
                        {isZh ? '📊 财务健康雷达图' : '📊 Financial Health Radar'}
                    </CardTitle>
                </CardHeader>
                <CardContent className="py-12 flex items-center justify-center text-slate-500 text-sm">
                    {loading
                        ? (isZh ? '加载中...' : 'Loading...')
                        : (isZh ? '数据生成中或未提供...' : 'Generating data or not available...')}
                </CardContent>
            </Card>
        );
    }

    return (
        <Card className="bg-slate-900/50 backdrop-blur-sm border-slate-800 hover:border-emerald-500/30 transition-all duration-300">
            <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-emerald-400 flex items-center gap-2">
                    <Shield className="w-5 h-5" />
                    {isZh ? '📊 财务健康雷达图' : '📊 Financial Health Radar'}
                </CardTitle>
                <div className={`text-center px-4 py-2 rounded-xl bg-slate-800/80 shadow-lg ${scoreGlow}`}>
                    <div className="text-xs text-slate-400 uppercase tracking-wider">
                        {isZh ? '综合评分' : 'Overall'}
                    </div>
                    <div className={`text-2xl font-bold ${scoreColor}`}>
                        {overallScore}
                        <span className="text-xs text-slate-500 ml-1">/ 100</span>
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                <div className="flex flex-col lg:flex-row items-center gap-6">
                    {/* Radar Chart */}
                    <div className="w-full lg:w-2/3 h-[320px]">
                        <ResponsiveContainer width="100%" height="100%">
                            <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="75%">
                                <PolarGrid stroke="#334155" strokeDasharray="3 3" />
                                <PolarAngleAxis
                                    dataKey="dimension"
                                    tick={{ fill: '#94a3b8', fontSize: 13, fontWeight: 500 }}
                                />
                                <PolarRadiusAxis
                                    angle={90}
                                    domain={[0, 100]}
                                    tick={{ fill: '#475569', fontSize: 10 }}
                                    tickCount={5}
                                />
                                <Tooltip content={<CustomTooltip />} />
                                <Radar
                                    name={isZh ? '财务健康' : 'Financial Health'}
                                    dataKey="score"
                                    stroke="#34d399"
                                    fill="#34d399"
                                    fillOpacity={0.15}
                                    strokeWidth={2}
                                    dot={{ r: 4, fill: '#34d399', strokeWidth: 0 }}
                                    animationDuration={800}
                                    animationEasing="ease-out"
                                />
                            </RadarChart>
                        </ResponsiveContainer>
                    </div>

                    {/* Score Breakdown */}
                    <div className="w-full lg:w-1/3 space-y-3">
                        {radarData.map((d) => (
                            <div key={d.dimension} className="flex items-center gap-3">
                                <div className="flex-1">
                                    <div className="flex justify-between text-sm mb-1">
                                        <span className="text-slate-300">{d.dimension}</span>
                                        <span className={
                                            d.score >= 70 ? 'text-emerald-400 font-semibold'
                                                : d.score >= 40 ? 'text-amber-400 font-semibold'
                                                    : 'text-red-400 font-semibold'
                                        }>
                                            {d.score}
                                        </span>
                                    </div>
                                    <div className="w-full bg-slate-800 rounded-full h-2">
                                        <div
                                            className={`h-2 rounded-full transition-all duration-700 ${d.score >= 70 ? 'bg-emerald-500'
                                                : d.score >= 40 ? 'bg-amber-500'
                                                    : 'bg-red-500'
                                                }`}
                                            style={{ width: `${d.score}%` }}
                                        />
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
