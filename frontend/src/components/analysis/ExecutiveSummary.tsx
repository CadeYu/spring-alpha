import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { ReactNode } from "react";
import {
    AnalysisReport,
    BusinessSignalItem,
    BusinessSignals,
    CoreThesis,
    SupportingEvidence,
} from "@/types/AnalysisReport";
import { Rocket, Sparkles, TrendingUp, TriangleAlert, type LucideIcon } from "lucide-react";

interface ExecutiveSummaryProps {
    thesis?: CoreThesis;
    businessSignals?: BusinessSignals;
    summary?: string;
    metadata?: AnalysisReport['metadata'];
    lang?: string;
}

type SignalGroupKey =
    | 'segmentPerformance'
    | 'productServiceUpdates'
    | 'managementFocus'
    | 'strategicMoves'
    | 'capexSignals'
    | 'riskSignals';

const verdictMap = {
    positive: {
        labelEn: "Positive",
        labelZh: "积极",
        className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
    },
    mixed: {
        labelEn: "Mixed",
        labelZh: "中性偏谨慎",
        className: "border-amber-500/30 bg-amber-500/10 text-amber-300",
    },
    negative: {
        labelEn: "Negative",
        labelZh: "偏空",
        className: "border-red-500/30 bg-red-500/10 text-red-300",
    },
} as const;

function splitFallbackSummary(summary?: string): string[] {
    if (!summary) return [];
    return summary
        .split(/(?<=[。！？.!?])\s*/)
        .map((sentence) => sentence.trim())
        .filter(Boolean);
}

function formatSignalText(item?: BusinessSignalItem, withTitle = true): string | null {
    if (!item) return null;

    const title = item.title?.trim();
    const detail = item.summary?.trim() || item.evidenceSnippet?.trim();

    if (title && detail) {
        if (!withTitle || detail.toLowerCase().startsWith(title.toLowerCase())) {
            return detail;
        }
        return `${title}: ${detail}`;
    }

    return title || detail || null;
}

function extractSignalBullets(
    businessSignals: BusinessSignals | undefined,
    groups: SignalGroupKey[],
    limit: number,
): string[] {
    if (!businessSignals) return [];

    const seen = new Set<string>();
    const bullets: string[] = [];

    for (const groupName of groups) {
        const group = businessSignals[groupName] ?? [];
        for (const item of group) {
            const text = formatSignalText(item);
            if (!text || seen.has(text)) {
                continue;
            }
            seen.add(text);
            bullets.push(text);
            if (bullets.length >= limit) {
                return bullets;
            }
        }
    }

    return bullets;
}

function extractSignalEvidence(
    businessSignals: BusinessSignals | undefined,
    groups: SignalGroupKey[],
    limit: number,
    fallbackLabel: string,
): SupportingEvidence[] {
    if (!businessSignals) return [];

    const seen = new Set<string>();
    const evidence: SupportingEvidence[] = [];

    for (const groupName of groups) {
        const group = businessSignals[groupName] ?? [];
        for (const item of group) {
            const label = item.title?.trim() || fallbackLabel;
            const detail = item.summary?.trim() || item.evidenceSnippet?.trim();
            const key = `${label}::${detail}`;
            if (!detail || seen.has(key)) {
                continue;
            }
            seen.add(key);
            evidence.push({ label, detail });
            if (evidence.length >= limit) {
                return evidence;
            }
        }
    }

    return evidence;
}

function cleanEvidence(items?: SupportingEvidence[]): SupportingEvidence[] {
    return items?.filter((item) => item?.detail?.trim()) ?? [];
}

function QuestionCard({
    title,
    icon: Icon,
    toneClassName,
    children,
}: {
    title: string;
    icon: LucideIcon;
    toneClassName: string;
    children: ReactNode;
}) {
    return (
        <section className="rounded-2xl border border-slate-800 bg-slate-950/45 p-4">
            <div className={`mb-4 flex items-center gap-2 ${toneClassName}`}>
                <Icon className="h-4 w-4" />
                <h3 className="text-sm font-semibold uppercase tracking-[0.25em]">
                    {title}
                </h3>
            </div>
            {children}
        </section>
    );
}

export function ExecutiveSummary({ thesis, businessSignals, summary, metadata, lang = 'en' }: ExecutiveSummaryProps) {
    const isZh = lang === 'zh';
    const verdict = thesis?.verdict && thesis.verdict in verdictMap
        ? verdictMap[thesis.verdict as keyof typeof verdictMap]
        : verdictMap.mixed;

    const whatChanged = thesis?.whatChanged?.filter(Boolean) ?? [];
    const legacyKeyPoints = thesis?.keyPoints?.filter(Boolean) ?? [];
    const drivers = cleanEvidence(thesis?.drivers);
    const strategicBets = cleanEvidence(thesis?.strategicBets);
    const watchItems = thesis?.watchItems?.filter(Boolean) ?? [];
    const legacyEvidence = cleanEvidence(thesis?.supportingEvidence);

    const displayedWhatChanged = whatChanged.length > 0
        ? whatChanged
        : (legacyKeyPoints.length > 0
            ? legacyKeyPoints
            : extractSignalBullets(businessSignals, ['segmentPerformance', 'productServiceUpdates'], 4));

    const displayedDrivers = drivers.length > 0
        ? drivers
        : (legacyEvidence.length > 0
            ? legacyEvidence.slice(0, 3)
            : extractSignalEvidence(
                businessSignals,
                ['managementFocus', 'segmentPerformance', 'productServiceUpdates'],
                3,
                isZh ? '核心驱动因素' : 'Core Driver',
            ));

    const displayedStrategicBets = strategicBets.length > 0
        ? strategicBets
        : (() => {
            const signalFallback = extractSignalEvidence(
                businessSignals,
                ['strategicMoves', 'capexSignals', 'productServiceUpdates'],
                3,
                isZh ? '战略押注' : 'Strategic Bet',
            );
            if (signalFallback.length > 0) {
                return signalFallback;
            }
            if (legacyEvidence.length > displayedDrivers.length) {
                return legacyEvidence.slice(displayedDrivers.length, displayedDrivers.length + 2);
            }
            return [];
        })();

    const displayedWatchItems = watchItems.length > 0
        ? watchItems
        : (() => {
            const signalFallback = extractSignalBullets(
                businessSignals,
                ['riskSignals', 'capexSignals', 'strategicMoves'],
                3,
            );
            if (signalFallback.length > 0) {
                return signalFallback;
            }
            return splitFallbackSummary(thesis?.summary || summary).slice(0, 2);
        })();

    return (
        <Card className="overflow-hidden border-slate-800 bg-slate-900/70 backdrop-blur-sm">
            <div className="grid grid-cols-1 lg:grid-cols-[300px,1fr]">
                <div className="border-b border-slate-800 bg-[radial-gradient(circle_at_top,_rgba(16,185,129,0.18),_transparent_55%),linear-gradient(180deg,_rgba(15,23,42,0.98),_rgba(2,6,23,0.98))] p-6 lg:border-b-0 lg:border-r">
                    <div className="flex h-full flex-col justify-between gap-6">
                        <div className="space-y-4">
                            <div className="flex items-center gap-2 text-emerald-300">
                                <Sparkles className="h-5 w-5" />
                                <span className="text-sm font-semibold uppercase tracking-[0.25em]">
                                    {isZh ? '核心分析' : 'Core Thesis'}
                                </span>
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <Badge variant="outline" className={verdict.className}>
                                    {isZh ? verdict.labelZh : verdict.labelEn}
                                </Badge>
                                <Badge variant="outline" className="border-slate-700 bg-slate-950/70 text-slate-300">
                                    {isZh ? '研究视角' : 'Research Note'}
                                </Badge>
                            </div>
                        </div>

                        <div className="space-y-4">
                            <h2 className="text-3xl font-bold leading-tight text-white">
                                {thesis?.headline || (isZh ? '等待模型形成核心判断…' : 'Waiting for the model to form a clear thesis...')}
                            </h2>
                            <p className="text-sm leading-7 text-slate-300">
                                {thesis?.summary || summary || (isZh ? '正在生成结构化分析内容。' : 'Structured analysis is being generated.')}
                            </p>
                        </div>

                        {metadata && (
                            <p className="text-xs text-slate-500">
                                {isZh
                                    ? `由 ${metadata.modelName} 生成于 ${new Date(metadata.generatedAt).toLocaleString('zh-CN')} (${metadata.language === 'zh' ? '中文' : metadata.language})`
                                    : `Generated by ${metadata.modelName} at ${new Date(metadata.generatedAt).toLocaleString()} (${metadata.language})`}
                            </p>
                        )}
                    </div>
                </div>

                <CardContent className="p-6">
                    <div className="grid gap-4 xl:grid-cols-2">
                        {displayedWhatChanged.length > 0 && (
                            <QuestionCard
                                title={isZh ? '本季发生了什么' : 'What Changed'}
                                icon={TrendingUp}
                                toneClassName="text-emerald-300"
                            >
                                <div className="space-y-3">
                                    {displayedWhatChanged.map((point, index) => (
                                        <div key={`${point}-${index}`} className="rounded-xl border border-slate-800 bg-slate-950/55 p-4">
                                            <p className="text-sm leading-7 text-slate-200">{point}</p>
                                        </div>
                                    ))}
                                </div>
                            </QuestionCard>
                        )}

                        {displayedDrivers.length > 0 && (
                            <QuestionCard
                                title={isZh ? '核心驱动因素' : 'What Drove It'}
                                icon={Sparkles}
                                toneClassName="text-cyan-300"
                            >
                                <div className="space-y-3">
                                    {displayedDrivers.map((item, index) => (
                                        <div key={`${item.label}-${index}`} className="rounded-xl border border-slate-800 bg-slate-950/55 p-4">
                                            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-300/80">
                                                {item.label}
                                            </p>
                                            <p className="text-sm leading-7 text-slate-300">{item.detail}</p>
                                        </div>
                                    ))}
                                </div>
                            </QuestionCard>
                        )}

                        {displayedStrategicBets.length > 0 && (
                            <QuestionCard
                                title={isZh ? '公司在押注什么' : 'What Is The Bet'}
                                icon={Rocket}
                                toneClassName="text-fuchsia-300"
                            >
                                <div className="space-y-3">
                                    {displayedStrategicBets.map((item, index) => (
                                        <div key={`${item.label}-${index}`} className="rounded-xl border border-slate-800 bg-slate-950/55 p-4">
                                            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-fuchsia-300/80">
                                                {item.label}
                                            </p>
                                            <p className="text-sm leading-7 text-slate-300">{item.detail}</p>
                                        </div>
                                    ))}
                                </div>
                            </QuestionCard>
                        )}

                        {displayedWatchItems.length > 0 && (
                            <QuestionCard
                                title={isZh ? '后续跟踪什么' : 'What To Watch'}
                                icon={TriangleAlert}
                                toneClassName="text-amber-300"
                            >
                                <div className="space-y-3">
                                    {displayedWatchItems.map((item, index) => (
                                        <div key={`${item}-${index}`} className="rounded-xl border border-amber-500/15 bg-amber-500/5 px-4 py-3">
                                            <p className="text-sm leading-7 text-slate-300">{item}</p>
                                        </div>
                                    ))}
                                </div>
                            </QuestionCard>
                        )}
                    </div>
                </CardContent>
            </div>
        </Card>
    );
}
