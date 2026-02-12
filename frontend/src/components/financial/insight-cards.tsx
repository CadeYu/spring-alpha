import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { InsightEngine } from '@/types/AnalysisReport';
import { AlertTriangle, Lightbulb } from 'lucide-react';

interface InsightCardsProps {
    data: InsightEngine;
    lang?: string;
}

export function InsightCards({ data, lang = 'en' }: InsightCardsProps) {
    if (!data) return null;

    const { accountingChanges, rootCauseAnalysis } = data;
    const isZh = lang === 'zh';

    return (
        <div className="space-y-6">
            {/* Accounting Changes Alert */}
            {accountingChanges && accountingChanges.length > 0 && (
                <div className="space-y-3">
                    <h3 className="text-lg font-semibold flex items-center gap-2 text-slate-200">
                        <AlertTriangle className="h-5 w-5 text-amber-500" />
                        {isZh ? '会计政策变更' : 'Accounting Policy Changes'}
                    </h3>
                    {accountingChanges.map((change, idx) => (
                        <div key={idx} className="bg-amber-950/20 border border-amber-900/50 rounded-lg p-4 backdrop-blur-sm">
                            <div className="flex items-center gap-2 mb-2">
                                <span className="font-medium text-amber-200">{change.policyName}</span>
                                <Badge variant="outline" className={`ml-2 border-amber-500/50 text-amber-500 bg-amber-500/10`}>
                                    {change.riskAssessment.toUpperCase()} {isZh ? '风险' : 'RISK'}
                                </Badge>
                            </div>
                            <p className="text-sm text-slate-400 leading-relaxed">
                                {change.changeDescription}
                            </p>
                        </div>
                    ))}
                </div>
            )}

            {/* Root Cause Analysis Grid */}
            <div>
                <h3 className="text-lg font-semibold flex items-center gap-2 mb-4 text-emerald-400">
                    <Lightbulb className="h-5 w-5 text-yellow-500" />
                    {isZh ? '根因分析 (驱动因素)' : 'Root Cause Analysis (Drivers)'}
                </h3>
                <div className="flex flex-col gap-4">
                    {rootCauseAnalysis.map((item, idx) => (
                        <div
                            key={idx}
                            className="bg-slate-900/50 backdrop-blur-sm border border-slate-800 rounded-lg p-5 hover:border-emerald-500/30 transition-all duration-300 hover:shadow-lg hover:shadow-emerald-500/5 group"
                        >
                            <div className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-3 group-hover:text-emerald-500/80 transition-colors">
                                {item.metric}
                            </div>
                            <div className="text-base font-medium text-slate-200 mb-4 leading-snug">
                                {item.reason}
                            </div>
                            <div className="text-xs text-slate-500 italic px-3 py-2 bg-slate-950/50 rounded border-l-2 border-emerald-500/20">
                                "{item.evidence}"
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
