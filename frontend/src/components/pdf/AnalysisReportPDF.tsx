'use client';

import {
    Document,
    Page,
    Text,
    View,
    Image,
    StyleSheet,
    Font,
} from '@react-pdf/renderer';
import type { AnalysisReport } from '@/types/AnalysisReport';

// ─── Register Chinese font (Noto Sans SC from Google Fonts) ───────────────
Font.register({
    family: 'NotoSansSC',
    fonts: [
        {
            src: 'https://fonts.gstatic.com/s/notosanssc/v37/k3kCo84MPvpLmixcA63oeAL7Iqp5IZJF9bmaG9_FnYxNbPzS5HE.ttf',
            fontWeight: 400,
        },
        {
            src: 'https://fonts.gstatic.com/s/notosanssc/v37/k3kCo84MPvpLmixcA63oeAL7Iqp5IZJF9bmaG9_EnYxNbPzS5HE.ttf',
            fontWeight: 700,
        },
    ],
});

// ─── Color Palette (Professional Financial Report) ────────────────────────
const colors = {
    primary: '#0F4C5C',      // Deep teal (header/brand)
    accent: '#10B981',       // Emerald green (highlights)
    danger: '#EF4444',       // Red (bearish/risk)
    warning: '#F59E0B',      // Amber (caution)
    dark: '#1E293B',         // Slate 800
    text: '#334155',         // Slate 700 (body text)
    textLight: '#64748B',    // Slate 500 (secondary text)
    bg: '#FFFFFF',           // White background
    bgLight: '#F8FAFC',      // Slate 50 (alternating rows)
    border: '#E2E8F0',       // Slate 200
    positive: '#059669',     // Emerald 600
    negative: '#DC2626',     // Red 600
    neutral: '#6B7280',      // Gray 500
};

// ─── Font helpers ─────────────────────────────────────────────────────────
function fontRegular(isZh: boolean) { return isZh ? 'NotoSansSC' : 'Helvetica'; }
function fontBold(isZh: boolean) { return isZh ? 'NotoSansSC' : 'Helvetica-Bold'; }

// ─── Styles (base — font overrides applied inline via isZh) ──────────────
const s = StyleSheet.create({
    page: {
        padding: 40,
        fontSize: 10,
        color: colors.text,
        backgroundColor: colors.bg,
    },
    // ── Header ──
    header: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'flex-end',
        borderBottomWidth: 3,
        borderBottomColor: colors.primary,
        paddingBottom: 10,
        marginBottom: 20,
    },
    brandText: {
        fontSize: 22,
        color: colors.primary,
        letterSpacing: 1,
    },
    tickerBadge: {
        fontSize: 14,
        color: colors.accent,
        backgroundColor: '#ECFDF5',
        padding: '4 10',
        borderRadius: 4,
    },
    metaRow: {
        flexDirection: 'row',
        gap: 16,
        marginBottom: 4,
    },
    metaText: {
        fontSize: 8,
        color: colors.textLight,
        textTransform: 'uppercase' as const,
        letterSpacing: 0.5,
    },
    reportMetaLine: {
        fontSize: 9,
        color: colors.text,
        marginTop: 4,
    },

    // ── Section ──
    section: {
        marginBottom: 16,
    },
    sectionTitle: {
        fontSize: 13,
        color: colors.primary,
        borderBottomWidth: 1,
        borderBottomColor: colors.border,
        paddingBottom: 4,
        marginBottom: 8,
        letterSpacing: 0.8,
    },
    bodyText: {
        fontSize: 10,
        lineHeight: 1.6,
        color: colors.text,
    },

    // ── Metrics Table ──
    table: {
        width: '100%',
        marginBottom: 8,
    },
    tableHeaderRow: {
        flexDirection: 'row',
        backgroundColor: colors.primary,
        padding: '6 8',
        borderRadius: 2,
    },
    tableHeaderCell: {
        fontSize: 8,
        color: '#FFFFFF',
        letterSpacing: 0.5,
    },
    tableRow: {
        flexDirection: 'row',
        padding: '5 8',
        borderBottomWidth: 0.5,
        borderBottomColor: colors.border,
    },
    tableRowAlt: {
        flexDirection: 'row',
        padding: '5 8',
        borderBottomWidth: 0.5,
        borderBottomColor: colors.border,
        backgroundColor: colors.bgLight,
    },
    colMetric: { width: '25%' },
    colValue: { width: '20%' },
    colInterpretation: { width: '55%' },

    // ── Cards (Drivers / Risks) ──
    twoCol: {
        flexDirection: 'row',
        gap: 16,
    },
    col: {
        flex: 1,
    },
    card: {
        backgroundColor: colors.bgLight,
        borderRadius: 4,
        padding: 8,
        marginBottom: 6,
        borderLeftWidth: 3,
        borderLeftColor: colors.accent,
    },
    cardDanger: {
        backgroundColor: '#FEF2F2',
        borderRadius: 4,
        padding: 8,
        marginBottom: 6,
        borderLeftWidth: 3,
        borderLeftColor: colors.danger,
    },
    cardTitle: {
        fontSize: 9,
        color: colors.dark,
        marginBottom: 2,
    },
    cardBody: {
        fontSize: 8.5,
        color: colors.text,
        lineHeight: 1.5,
    },
    badge: {
        fontSize: 7,
        paddingVertical: 1,
        paddingHorizontal: 4,
        borderRadius: 2,
        alignSelf: 'flex-start',
        marginBottom: 3,
    },
    badgeHigh: {
        backgroundColor: '#FEE2E2',
        color: colors.danger,
    },
    badgeMedium: {
        backgroundColor: '#FEF3C7',
        color: '#B45309',
    },
    badgeLow: {
        backgroundColor: '#ECFDF5',
        color: colors.positive,
    },

    // ── Bull / Bear ──
    bullBearRow: {
        flexDirection: 'row',
        gap: 16,
        marginBottom: 8,
    },
    bullBox: {
        flex: 1,
        backgroundColor: '#ECFDF5',
        borderRadius: 4,
        padding: 10,
        borderLeftWidth: 3,
        borderLeftColor: colors.positive,
    },
    bearBox: {
        flex: 1,
        backgroundColor: '#FEF2F2',
        borderRadius: 4,
        padding: 10,
        borderLeftWidth: 3,
        borderLeftColor: colors.negative,
    },
    bullBearTitle: {
        fontSize: 10,
        marginBottom: 4,
    },

    // ── DuPont ──
    dupontRow: {
        flexDirection: 'row',
        gap: 8,
        marginBottom: 8,
    },
    dupontCard: {
        flex: 1,
        backgroundColor: colors.bgLight,
        borderRadius: 4,
        padding: 8,
        alignItems: 'center',
        borderWidth: 1,
        borderColor: colors.border,
    },
    dupontLabel: {
        fontSize: 7,
        color: colors.textLight,
        textTransform: 'uppercase' as const,
        letterSpacing: 0.5,
        marginBottom: 2,
    },
    dupontValue: {
        fontSize: 14,
        fontFamily: 'Helvetica-Bold',
        color: colors.primary,
    },
    dupontFormula: {
        fontSize: 8,
        color: colors.textLight,
        textAlign: 'center',
        marginBottom: 4,
    },

    // ── Citations ──
    citationBox: {
        backgroundColor: colors.bgLight,
        borderRadius: 3,
        padding: 8,
        marginBottom: 5,
        borderLeftWidth: 2,
        borderLeftColor: colors.border,
    },
    citationExcerpt: {
        fontSize: 8.5,
        color: colors.text,
        lineHeight: 1.5,
        marginBottom: 3,
    },
    citationMeta: {
        flexDirection: 'row',
        justifyContent: 'space-between',
        alignItems: 'center',
    },
    citationSection: {
        fontSize: 7,
        color: colors.textLight,
        textTransform: 'uppercase' as const,
        letterSpacing: 0.5,
    },
    verifiedBadge: {
        fontSize: 7,
        paddingVertical: 1,
        paddingHorizontal: 4,
        borderRadius: 2,
    },

    // ── Footer ──
    footer: {
        position: 'absolute',
        bottom: 20,
        left: 40,
        right: 40,
        borderTopWidth: 0.5,
        borderTopColor: colors.border,
        paddingTop: 6,
        flexDirection: 'row',
        justifyContent: 'space-between',
    },
    footerText: {
        fontSize: 7,
        color: colors.textLight,
    },
    pageNumber: {
        fontSize: 7,
        color: colors.textLight,
    },
});

// ─── Helper: Sentiment color ─────────────────────────────────────────────
function sentimentColor(sentiment: string): string {
    switch (sentiment) {
        case 'positive': return colors.positive;
        case 'negative': return colors.negative;
        default: return colors.neutral;
    }
}

function severityBadgeStyle(level: string) {
    switch (level) {
        case 'high': return { ...s.badge, ...s.badgeHigh };
        case 'medium': return { ...s.badge, ...s.badgeMedium };
        default: return { ...s.badge, ...s.badgeLow };
    }
}

function verificationStyle(status?: string) {
    switch (status) {
        case 'VERIFIED':
            return { ...s.verifiedBadge, backgroundColor: '#ECFDF5', color: colors.positive };
        case 'UNVERIFIED':
            return { ...s.verifiedBadge, backgroundColor: '#FEF3C7', color: '#B45309' };
        case 'NOT_FOUND':
            return { ...s.verifiedBadge, backgroundColor: '#FEE2E2', color: colors.danger };
        default:
            return { ...s.verifiedBadge, backgroundColor: '#F1F5F9', color: colors.textLight };
    }
}

function verificationLabel(status?: string, isZh?: boolean) {
    switch (status) {
        case 'VERIFIED': return isZh ? '已验证' : 'Verified';
        case 'UNVERIFIED': return isZh ? '未验证' : 'Unverified';
        case 'NOT_FOUND': return isZh ? '未找到' : 'Not Found';
        default: return isZh ? '未知' : 'N/A';
    }
}

// ─── PDF Document ─────────────────────────────────────────────────────────
interface AnalysisReportPDFProps {
    report: AnalysisReport;
    ticker: string;
    lang: string;
    chartImages?: Record<string, string>;  // id -> base64 data URL
}

// ─── Helper: translate citation section names for PDF ─────────────────────
function translateSection(section: string): string {
    return (section || '')
        .replace(/MD&A/gi, 'SEC财报中的管理层讨论与分析')
        .replace(/Risk Factors/gi, '风险因素')
        .replace(/Financial Statements/gi, '财务报表')
        .replace(/Notes/gi, '附注');
}

// ─── Helper: translate severity/impact badges ─────────────────────────────
function badgeLabel(level: string, isZh: boolean): string {
    if (!isZh) return level.toUpperCase();
    switch (level) {
        case 'high': return '高';
        case 'medium': return '中';
        case 'low': return '低';
        default: return level;
    }
}

export function AnalysisReportPDF({ report, ticker, lang, chartImages = {} }: AnalysisReportPDFProps) {
    const isZh = lang === 'zh';
    const fr = fontRegular(isZh);
    const fb = fontBold(isZh);
    const reportIdentity = [report.companyName, report.period, report.filingDate].filter(Boolean).join(' · ');
    const generatedAt = report.metadata?.generatedAt
        ? new Date(report.metadata.generatedAt).toLocaleString(isZh ? 'zh-CN' : 'en-US')
        : 'N/A';

    return (
        <Document
            title={isZh ? `${ticker} AI 金融分析报告` : `${ticker} Financial Analysis Report`}
            author="Spring Alpha"
            subject={isZh ? `${ticker} AI 财报分析` : `AI-Powered Financial Analysis for ${ticker}`}
        >
            <Page size="A4" style={{ ...s.page, fontFamily: fr }}>
                {/* ── Header ── */}
                <View style={s.header}>
                    <View>
                        <Text style={{ ...s.brandText, fontFamily: fb }}>SPRING ALPHA</Text>
                        <View style={s.metaRow}>
                            <Text style={s.metaText}>
                                {isZh ? 'AI 金融分析报告' : 'AI Financial Analysis Report'}
                            </Text>
                            <Text style={s.metaText}>|</Text>
                            <Text style={s.metaText}>{generatedAt}</Text>
                            <Text style={s.metaText}>|</Text>
                            <Text style={s.metaText}>
                                {isZh ? '模型' : 'Model'}: {report.metadata?.modelName || 'N/A'}
                            </Text>
                        </View>
                        {reportIdentity && (
                            <Text style={{ ...s.reportMetaLine, fontFamily: fb }}>
                                {reportIdentity}
                            </Text>
                        )}
                    </View>
                    <Text style={{ ...s.tickerBadge, fontFamily: fb }}>{ticker}</Text>
                </View>

                {/* ── Core Thesis ── */}
                <View style={s.section}>
                    <Text style={{ ...s.sectionTitle, fontFamily: fb }}>
                        {isZh ? '核心分析' : 'Core Thesis'}
                    </Text>
                    {report.coreThesis?.headline && (
                        <Text style={{ ...s.cardTitle, fontFamily: fb, fontSize: 12, marginBottom: 6 }}>
                            {report.coreThesis.headline}
                        </Text>
                    )}
                    <Text style={s.bodyText}>
                        {report.coreThesis?.summary || report.executiveSummary || 'N/A'}
                    </Text>
                    {report.coreThesis?.keyPoints && report.coreThesis.keyPoints.length > 0 && (
                        <View style={{ marginTop: 8 }}>
                            {report.coreThesis.keyPoints.slice(0, 4).map((point, i) => (
                                <Text key={i} style={{ ...s.bodyText, fontSize: 9, marginBottom: 4 }}>
                                    • {point}
                                </Text>
                            ))}
                        </View>
                    )}
                </View>

                {/* ── Key Metrics ── */}
                {report.keyMetrics && report.keyMetrics.length > 0 && (
                    <View style={s.section}>
                        <Text style={{ ...s.sectionTitle, fontFamily: fb }}>
                            {isZh ? '核心指标' : 'Key Metrics'}
                        </Text>
                        <View style={s.table}>
                            <View style={s.tableHeaderRow}>
                                <Text style={{ ...s.tableHeaderCell, ...s.colMetric, fontFamily: fb }}>
                                    {isZh ? '指标' : 'Metric'}
                                </Text>
                                <Text style={{ ...s.tableHeaderCell, ...s.colValue, fontFamily: fb }}>
                                    {isZh ? '数值' : 'Value'}
                                </Text>
                                <Text style={{ ...s.tableHeaderCell, ...s.colInterpretation, fontFamily: fb }}>
                                    {isZh ? '解读' : 'Interpretation'}
                                </Text>
                            </View>
                            {report.keyMetrics.map((metric, i) => (
                                <View key={i} style={i % 2 === 0 ? s.tableRow : s.tableRowAlt}>
                                    <Text style={{ ...s.colMetric, fontFamily: fb, fontSize: 9 }}>
                                        {metric.metricName}
                                    </Text>
                                    <Text style={{ ...s.colValue, color: sentimentColor(metric.sentiment), fontFamily: fb }}>
                                        {metric.value}
                                    </Text>
                                    <Text style={{ ...s.colInterpretation, fontSize: 8.5 }}>
                                        {metric.interpretation}
                                    </Text>
                                </View>
                            ))}
                        </View>
                    </View>
                )}

                {/* ── Business Drivers & Risk Factors (Two Columns) ── */}
                <View style={s.twoCol}>
                    {/* Business Drivers */}
                    {report.businessDrivers && report.businessDrivers.length > 0 && (
                        <View style={s.col}>
                            <Text style={{ ...s.sectionTitle, fontFamily: fb }}>
                                {isZh ? '业务驱动因素' : 'Business Drivers'}
                            </Text>
                            {report.businessDrivers.map((driver, i) => (
                                <View key={i} style={s.card} wrap={false}>
                                    <Text style={{ ...severityBadgeStyle(driver.impact), fontFamily: fb }}>
                                        {badgeLabel(driver.impact, isZh)}
                                    </Text>
                                    <Text style={{ ...s.cardTitle, fontFamily: fb }}>{driver.title}</Text>
                                    <Text style={{ ...s.cardBody, fontFamily: fr }}>{driver.description}</Text>
                                </View>
                            ))}
                        </View>
                    )}

                    {/* Risk Factors */}
                    {report.riskFactors && report.riskFactors.length > 0 && (
                        <View style={s.col}>
                            <Text style={{ ...s.sectionTitle, fontFamily: fb }}>
                                {isZh ? '风险因素' : 'Risk Factors'}
                            </Text>
                            {report.riskFactors.map((risk, i) => (
                                <View key={i} style={s.cardDanger} wrap={false}>
                                    <Text style={{ ...severityBadgeStyle(risk.severity), fontFamily: fb }}>
                                        {badgeLabel(risk.severity, isZh)}
                                    </Text>
                                    <Text style={{ ...s.cardTitle, fontFamily: fb }}>{risk.category}</Text>
                                    <Text style={{ ...s.cardBody, fontFamily: fr }}>{risk.description}</Text>
                                </View>
                            ))}
                        </View>
                    )}
                </View>

                {/* ── Bull / Bear Case ── */}
                {(report.bullCase || report.bearCase) && (
                    <View style={s.section}>
                        <Text style={{ ...s.sectionTitle, fontFamily: fb }}>
                            {isZh ? '多空分析' : 'Bull / Bear Case'}
                        </Text>
                        <View style={s.bullBearRow}>
                            <View style={s.bullBox}>
                                <Text style={{ ...s.bullBearTitle, color: colors.positive, fontFamily: fb }}>
                                    {isZh ? '看涨论据' : 'Bull Case'}
                                </Text>
                                <Text style={s.cardBody}>{report.bullCase}</Text>
                            </View>
                            <View style={s.bearBox}>
                                <Text style={{ ...s.bullBearTitle, color: colors.negative, fontFamily: fb }}>
                                    {isZh ? '看跌论据' : 'Bear Case'}
                                </Text>
                                <Text style={s.cardBody}>{report.bearCase}</Text>
                            </View>
                        </View>
                    </View>
                )}

                {/* ── DuPont Analysis ── */}
                {report.dupontAnalysis && (
                    <View style={s.section}>
                        <Text style={{ ...s.sectionTitle, fontFamily: fb }}>
                            {isZh ? '杜邦分析' : 'DuPont Analysis'}
                        </Text>
                        <Text style={s.dupontFormula}>
                            {isZh
                                ? 'ROE = 净利率 × 资产周转率 × 权益乘数'
                                : 'ROE = Net Profit Margin × Asset Turnover × Equity Multiplier'}
                        </Text>
                        <View style={s.dupontRow}>
                            <View style={s.dupontCard}>
                                <Text style={s.dupontLabel}>{isZh ? '净利率' : 'Net Margin'}</Text>
                                <Text style={s.dupontValue}>{report.dupontAnalysis.netProfitMargin}</Text>
                            </View>
                            <View style={s.dupontCard}>
                                <Text style={s.dupontLabel}>{isZh ? '周转率' : 'Turnover'}</Text>
                                <Text style={s.dupontValue}>{report.dupontAnalysis.assetTurnover}</Text>
                            </View>
                            <View style={s.dupontCard}>
                                <Text style={s.dupontLabel}>{isZh ? '杠杆率' : 'Leverage'}</Text>
                                <Text style={s.dupontValue}>{report.dupontAnalysis.equityMultiplier}</Text>
                            </View>
                            <View style={s.dupontCard}>
                                <Text style={s.dupontLabel}>ROE</Text>
                                <Text style={{ ...s.dupontValue, color: colors.accent }}>
                                    {report.dupontAnalysis.returnOnEquity}
                                </Text>
                            </View>
                        </View>
                        <Text style={s.bodyText}>{report.dupontAnalysis.interpretation}</Text>
                    </View>
                )}

                {/* ── Chart Screenshots (captured via html2canvas) ── */}
                {Object.keys(chartImages).length > 0 && (
                    <View style={s.section} break>
                        <Text style={{ ...s.sectionTitle, fontFamily: fb }}>
                            {isZh ? '数据可视化' : 'Data Visualizations'}
                        </Text>
                        {chartImages['chart-dupont'] && (
                            <View style={{ marginBottom: 16 }}>
                                <Text style={{ fontSize: 9, color: colors.textLight, marginBottom: 6, fontFamily: fb }}>
                                    {isZh ? '杜邦分析图表' : 'DuPont Analysis Chart'}
                                </Text>
                                {/* react-pdf Image is not a DOM img and does not support alt */}
                                {/* eslint-disable-next-line jsx-a11y/alt-text */}
                                <Image
                                    src={chartImages['chart-dupont']}
                                    style={{ width: '100%', borderRadius: 4 }}
                                />
                            </View>
                        )}
                        {chartImages['chart-radar'] && (
                            <View style={{ marginBottom: 16 }}>
                                <Text style={{ fontSize: 9, color: colors.textLight, marginBottom: 6, fontFamily: fb }}>
                                    {isZh ? '财务健康雷达图' : 'Financial Health Radar'}
                                </Text>
                                {/* react-pdf Image is not a DOM img and does not support alt */}
                                {/* eslint-disable-next-line jsx-a11y/alt-text */}
                                <Image
                                    src={chartImages['chart-radar']}
                                    style={{ width: '100%', borderRadius: 4 }}
                                />
                            </View>
                        )}
                    </View>
                )}

                {/* ── Citations ── */}
                {((report.citations && report.citations.length > 0) || report.sourceContext?.message) && (
                    <View style={s.section} break>
                        <Text style={{ ...s.sectionTitle, fontFamily: fb }}>
                            {isZh ? '来源引用与验证' : 'Source Citations & Verification'}
                        </Text>
                        {report.citations && report.citations.length > 0 ? (
                            report.citations.map((citation, i) => (
                                <View key={i} style={s.citationBox}>
                                    <Text style={{ ...s.citationExcerpt, ...(isZh ? { fontFamily: fr } : { fontStyle: 'italic' as const }) }}>
                                        &ldquo;{isZh ? (citation.excerptZh || citation.excerpt) : citation.excerpt}&rdquo;
                                    </Text>
                                    <View style={s.citationMeta}>
                                        <Text style={s.citationSection}>
                                            {isZh ? '来源' : 'Source'}: {isZh ? translateSection(citation.section) : citation.section}
                                        </Text>
                                        <Text style={verificationStyle(citation.verificationStatus)}>
                                            {verificationLabel(citation.verificationStatus, isZh)}
                                        </Text>
                                    </View>
                                </View>
                            ))
                        ) : (
                            <View style={s.citationBox}>
                                <Text style={{ ...s.citationExcerpt, fontFamily: fr }}>
                                    {report.sourceContext?.message}
                                </Text>
                                <View style={s.citationMeta}>
                                    <Text style={s.citationSection}>
                                        {isZh ? '状态' : 'Status'}: {report.sourceContext?.status || 'N/A'}
                                    </Text>
                                </View>
                            </View>
                        )}
                    </View>
                )}

                {/* ── Footer ── */}
                <View style={s.footer} fixed>
                    <Text style={s.footerText}>
                        {isZh
                            ? '免责声明：本报告由 AI 生成，仅供参考，不构成投资建议。'
                            : 'Disclaimer: This report is AI-generated for informational purposes only. Not investment advice.'}
                    </Text>
                    <Text style={s.pageNumber} render={({ pageNumber, totalPages }) => `${pageNumber} / ${totalPages}`} />
                </View>
            </Page>
        </Document>
    );
}
