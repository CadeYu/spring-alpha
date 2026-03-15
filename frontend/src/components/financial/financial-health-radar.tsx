'use client';

import React, { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, ResponsiveContainer, Tooltip } from 'recharts';
import { Shield } from 'lucide-react';
import type { FinancialFactsSnapshot } from '@/types/FinancialFacts';
import { DashboardModeNotice } from './dashboard-mode-notice';
import { FinancialSectorSnapshot } from './financial-sector-snapshot';

interface RadarDataPoint {
    key: string;
    dimension: string;
    score: number;
    fullMark: 100;
}

interface FinancialHealthRadarProps {
    ticker: string;
    lang?: string;
    apiBase: string;
}

const CORE_KEYS = ['profitability', 'growth', 'cashFlow', 'leverage', 'efficiency'] as const;

/** Clamp a value between 0 and 100 */
function clamp(v: number): number {
    return Math.max(0, Math.min(100, Math.round(v)));
}

function normalizePercent(val: number | null | undefined): number | null {
    if (val === undefined || val === null || Number.isNaN(val)) {
        return null;
    }
    return Math.abs(val) <= 5 ? val * 100 : val;
}

function normalizeRatio(val: number | null | undefined): number | null {
    if (val === undefined || val === null || Number.isNaN(val)) {
        return null;
    }
    return Math.abs(val) > 5 ? val / 100 : val;
}

function scoreByBands(value: number, bands: Array<[number, number]>): number {
    if (bands.length === 0) return 50;
    if (value <= bands[0][0]) return bands[0][1];

    for (let idx = 1; idx < bands.length; idx += 1) {
        const [upperValue, upperScore] = bands[idx];
        const [lowerValue, lowerScore] = bands[idx - 1];
        if (value <= upperValue) {
            const ratio = (value - lowerValue) / (upperValue - lowerValue);
            return clamp(lowerScore + (upperScore - lowerScore) * ratio);
        }
    }

    return bands[bands.length - 1][1];
}

function weightedAverage(parts: Array<{ score: number | null; weight: number }>): number | null {
    const available = parts.filter((part) => part.score !== null);
    if (available.length === 0) {
        return null;
    }

    const totalWeight = available.reduce((sum, part) => sum + part.weight, 0);
    const weightedScore = available.reduce((sum, part) => sum + (part.score ?? 0) * part.weight, 0);
    return clamp(weightedScore / totalWeight);
}

/** Score profitability with diminishing returns for already-excellent margins. */
export function scoreProfitability(facts: FinancialFactsSnapshot): number | null {
    const gross = normalizePercent(facts.grossMargin);
    const oper = normalizePercent(facts.operatingMargin);
    const net = normalizePercent(facts.netMargin);

    const grossScore = gross === null ? null : scoreByBands(gross, [
        [10, 20],
        [20, 45],
        [35, 70],
        [45, 88],
        [55, 100],
    ]);
    const operScore = oper === null ? null : scoreByBands(oper, [
        [5, 20],
        [10, 40],
        [20, 68],
        [28, 88],
        [35, 100],
    ]);
    const netScore = net === null ? null : scoreByBands(net, [
        [2, 15],
        [8, 35],
        [15, 60],
        [22, 82],
        [28, 100],
    ]);

    return weightedAverage([
        { score: grossScore, weight: 0.25 },
        { score: operScore, weight: 0.35 },
        { score: netScore, weight: 0.4 },
    ]);
}

/** Score growth fairly for mature companies: modest positive growth is still healthy. */
export function scoreGrowth(facts: FinancialFactsSnapshot): number | null {
    const revenueGrowth = normalizePercent(facts.revenueYoY);
    const operatingCashFlowGrowth = normalizePercent(facts.operatingCashFlowYoY);

    const revenueScore = revenueGrowth === null ? null : scoreByBands(revenueGrowth, [
        [-15, 15],
        [-5, 35],
        [0, 50],
        [5, 68],
        [10, 82],
        [20, 100],
    ]);
    const ocfScore = operatingCashFlowGrowth === null ? null : scoreByBands(operatingCashFlowGrowth, [
        [-20, 22],
        [-5, 45],
        [0, 58],
        [5, 72],
        [12, 86],
        [25, 100],
    ]);

    return weightedAverage([
        { score: revenueScore, weight: 0.6 },
        { score: ocfScore, weight: 0.4 },
    ]);
}

/** Score cash flow health */
export function scoreCashFlow(facts: FinancialFactsSnapshot): number | null {
    const operatingCashFlowGrowth = normalizePercent(facts.operatingCashFlowYoY);
    const freeCashFlowGrowth = normalizePercent(facts.freeCashFlowYoY);

    const ocfScore = operatingCashFlowGrowth === null ? null : scoreByBands(operatingCashFlowGrowth, [
        [-20, 20],
        [-5, 42],
        [0, 55],
        [5, 68],
        [15, 86],
        [30, 100],
    ]);
    const fcfScore = freeCashFlowGrowth === null ? null : scoreByBands(freeCashFlowGrowth, [
        [-25, 18],
        [-5, 40],
        [0, 54],
        [8, 70],
        [20, 88],
        [40, 100],
    ]);

    return weightedAverage([
        { score: ocfScore, weight: 0.5 },
        { score: fcfScore, weight: 0.5 },
    ]);
}

/** Score capital structure: mature companies are not punished too harshly for buyback-driven leverage. */
export function scoreLeverage(facts: FinancialFactsSnapshot): number | null {
    const debtToEquity = normalizeRatio(facts.debtToEquityRatio);
    if (debtToEquity === null || debtToEquity < 0) {
        return null;
    }

    return scoreByBands(debtToEquity, [
        [0.2, 95],
        [0.6, 85],
        [1.0, 72],
        [1.5, 60],
        [2.5, 42],
        [4.0, 20],
    ]);
}

/** Score efficiency: ROE + ROA */
export function scoreEfficiency(facts: FinancialFactsSnapshot): number | null {
    const roe = normalizePercent(facts.returnOnEquity);
    const roa = normalizePercent(facts.returnOnAssets);

    const roeScore = roe === null ? null : scoreByBands(roe, [
        [5, 20],
        [10, 38],
        [20, 65],
        [30, 82],
        [45, 100],
    ]);
    const roaScore = roa === null ? null : scoreByBands(roa, [
        [2, 18],
        [5, 42],
        [10, 70],
        [15, 90],
        [20, 100],
    ]);

    return weightedAverage([
        { score: roeScore, weight: 0.55 },
        { score: roaScore, weight: 0.45 },
    ]);
}

/** Market pricing is informative, but should not dominate financial-health scoring. */
export function scoreMarketPricing(facts: FinancialFactsSnapshot): number | null {
    const pe = facts.priceToEarningsRatio != null && facts.priceToEarningsRatio > 0
        ? facts.priceToEarningsRatio
        : null;
    const pb = facts.priceToBookRatio != null && facts.priceToBookRatio > 0
        ? facts.priceToBookRatio
        : null;

    if (pe == null && pb == null) {
        return null;
    }

    let weightedScore = 0;
    let totalWeight = 0;

    if (pe != null) {
        const peScore = scoreByBands(pe, [
            [12, 90],
            [20, 82],
            [30, 72],
            [45, 58],
            [70, 40],
            [100, 25],
        ]);
        weightedScore += peScore * 0.55;
        totalWeight += 0.55;
    }

    if (pb != null) {
        const pbScore = scoreByBands(pb, [
            [2, 88],
            [5, 78],
            [10, 64],
            [20, 45],
            [35, 25],
        ]);
        weightedScore += pbScore * 0.45;
        totalWeight += 0.45;
    }

    return totalWeight > 0 ? clamp(weightedScore / totalWeight) : null;
}

export function hasMarketPricingData(facts: FinancialFactsSnapshot): boolean {
    return (facts.priceToEarningsRatio ?? 0) > 0 || (facts.priceToBookRatio ?? 0) > 0;
}

const LABELS: Record<string, { en: string; zh: string }> = {
    profitability: { en: 'Profit Quality', zh: '盈利质量' },
    growth: { en: 'Growth Quality', zh: '增长质量' },
    cashFlow: { en: 'Cash Conversion', zh: '现金转化' },
    leverage: { en: 'Balance Sheet', zh: '资产负债表' },
    efficiency: { en: 'Capital Efficiency', zh: '资本效率' },
    pricing: { en: 'Market Pricing', zh: '市场定价' },
};

export function buildRadarData(facts: FinancialFactsSnapshot, lang: string): RadarDataPoint[] {
    const isZh = lang === 'zh';
    const candidateScores = [
        { key: 'profitability', score: scoreProfitability(facts) },
        { key: 'growth', score: scoreGrowth(facts) },
        { key: 'cashFlow', score: scoreCashFlow(facts) },
        { key: 'leverage', score: scoreLeverage(facts) },
        { key: 'efficiency', score: scoreEfficiency(facts) },
    ];

    const radarData = candidateScores
        .filter((item) => item.score !== null)
        .map((item) => ({
            key: item.key,
            dimension: LABELS[item.key][isZh ? 'zh' : 'en'],
            score: item.score as number,
            fullMark: 100 as const,
        }));

    const pricingScore = scoreMarketPricing(facts);
    if (pricingScore !== null) {
        radarData.push({
            key: 'pricing',
            dimension: LABELS.pricing[isZh ? 'zh' : 'en'],
            score: pricingScore,
            fullMark: 100,
        });
    }

    return radarData;
}

export function computeOverallScore(radarData: RadarDataPoint[]): number {
    const weights: Record<string, number> = {
        profitability: 0.24,
        growth: 0.18,
        cashFlow: 0.20,
        leverage: 0.14,
        efficiency: 0.24,
        pricing: 0,
    };

    const coreData = radarData.filter((item) => (weights[item.key] ?? 0) > 0);
    if (coreData.length === 0) {
        return 0;
    }

    const totalWeight = coreData.reduce((sum, item) => sum + (weights[item.key] ?? 0), 0);
    const weighted = coreData.reduce((sum, item) => sum + item.score * (weights[item.key] ?? 0), 0);
    return clamp(weighted / totalWeight);
}

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
    const [facts, setFacts] = useState<FinancialFactsSnapshot | null>(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (!ticker || ticker.length < 1) {
            setFacts(null);
            return;
        }
        let cancelled = false;
        setFacts(null);

        async function loadFacts() {
            setLoading(true);

            try {
                const response = await fetch(`${apiBase}/financial/${ticker}`);
                if (!response.ok) {
                    if (!cancelled) {
                        setFacts(null);
                    }
                    return;
                }

                const data = await response.json() as FinancialFactsSnapshot;
                if (!cancelled && data) {
                    setFacts(data);
                }
            } catch {
                if (!cancelled) {
                    setFacts(null);
                }
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
    const radarData: RadarDataPoint[] = facts ? buildRadarData(facts, lang) : [];
    const overallScore = radarData.length > 0 ? computeOverallScore(radarData) : 0;
    const marketPricingAvailable = facts ? hasMarketPricingData(facts) : false;
    const missingCoreDimensions = CORE_KEYS.length
        - radarData.filter((item) => CORE_KEYS.includes(item.key as (typeof CORE_KEYS)[number])).length;

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

    if (facts.dashboardMode === 'unsupported_reit') {
        return (
            <Card className="bg-slate-900/50 backdrop-blur-sm border-slate-800">
                <CardHeader>
                    <CardTitle className="text-emerald-400 flex items-center gap-2">
                        <Shield className="w-5 h-5" />
                        {isZh ? '📊 财务健康雷达图' : '📊 Financial Health Radar'}
                    </CardTitle>
                </CardHeader>
                <CardContent>
                    <DashboardModeNotice
                        mode="unsupported_reit"
                        lang={lang}
                        message={facts.dashboardMessage}
                    />
                </CardContent>
            </Card>
        );
    }

    if (facts.dashboardMode === 'financial_sector') {
        return <FinancialSectorSnapshot facts={facts} lang={lang} />;
    }

    if (radarData.length === 0) {
        return (
            <Card className="bg-slate-900/50 backdrop-blur-sm border-slate-800 border-dashed">
                <CardHeader>
                    <CardTitle className="text-emerald-400/50 flex items-center gap-2">
                        <Shield className="w-5 h-5" />
                        {isZh ? '📊 财务健康雷达图' : '📊 Financial Health Radar'}
                    </CardTitle>
                </CardHeader>
                <CardContent className="py-12 flex items-center justify-center text-slate-500 text-sm">
                    {isZh ? '当前缺少足够的可评分指标。' : 'Not enough reliable inputs are available to score this dashboard.'}
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
                        {isZh ? '基本面评分' : 'Fundamental'}
                    </div>
                    <div className={`text-2xl font-bold ${scoreColor}`}>
                        {overallScore}
                        <span className="text-xs text-slate-500 ml-1">/ 100</span>
                    </div>
                    <div className="text-[10px] text-slate-500 mt-1">
                        {isZh ? '不含市场定价' : 'ex-market pricing'}
                    </div>
                </div>
            </CardHeader>
            <CardContent>
                <div className="flex flex-col lg:flex-row items-center gap-6">
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

                        {missingCoreDimensions > 0 && (
                            <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/70 px-3 py-3 text-xs text-slate-400">
                                {isZh
                                    ? `已隐藏 ${missingCoreDimensions} 个缺失维度，避免用空值推导误导性评分。`
                                    : `${missingCoreDimensions} core dimensions were hidden because the required inputs were unavailable or structurally invalid.`}
                            </div>
                        )}

                        {!marketPricingAvailable && (
                            <div className="rounded-xl border border-dashed border-slate-700 bg-slate-900/70 px-3 py-3 text-xs text-slate-400">
                                {isZh
                                    ? '市场定价维度已隐藏：当前未获取到可用的补充市场估值数据，基本面评分仍基于 SEC 财务披露生成。'
                                    : 'Market pricing is hidden for this ticker because supplemental valuation data is unavailable. The fundamental score still reflects SEC-backed financials.'}
                            </div>
                        )}
                    </div>
                </div>
            </CardContent>
        </Card>
    );
}
