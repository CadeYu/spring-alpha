export interface MetricInsight {
    metricName: string;
    value: string;
    interpretation: string;
    sentiment: 'positive' | 'negative' | 'neutral';
}

export interface BusinessDriver {
    title: string;
    description: string;
    impact: 'high' | 'medium' | 'low';
}

export interface RiskFactor {
    category: string;
    description: string;
    severity: 'high' | 'medium' | 'low';
}

export interface Citation {
    section: string;
    excerpt: string;
    excerptZh?: string;
    verificationStatus?: 'VERIFIED' | 'UNVERIFIED' | 'NOT_FOUND';
}

export interface AnalysisMetadata {
    modelName: string;
    generatedAt: string;
    language: string;
}

export interface SourceContext {
    status?: 'GROUNDED' | 'LIMITED' | 'DEGRADED' | 'UNAVAILABLE';
    message?: string;
}

export type ReportType = 'quarterly';

export interface SupportingEvidence {
    label: string;
    detail: string;
}

export interface BusinessSignalItem {
    title?: string;
    summary?: string;
    evidenceSection?: string;
    evidenceSnippet?: string;
}

export interface BusinessEvidenceRef {
    topic?: string;
    section?: string;
    excerpt?: string;
}

export interface BusinessSignals {
    ticker?: string;
    reportType?: ReportType;
    period?: string;
    filingDate?: string;
    segmentPerformance?: BusinessSignalItem[];
    productServiceUpdates?: BusinessSignalItem[];
    managementFocus?: BusinessSignalItem[];
    strategicMoves?: BusinessSignalItem[];
    capexSignals?: BusinessSignalItem[];
    riskSignals?: BusinessSignalItem[];
    evidenceRefs?: BusinessEvidenceRef[];
}

export interface CoreThesis {
    verdict?: 'positive' | 'mixed' | 'negative';
    headline?: string;
    summary?: string;
    whatChanged?: string[];
    drivers?: SupportingEvidence[];
    strategicBets?: SupportingEvidence[];
    keyPoints?: string[];
    supportingEvidence?: SupportingEvidence[];
    watchItems?: string[];
}

export interface AnalysisReport {
    executiveSummary?: string;
    coreThesis?: CoreThesis;
    businessSignals?: BusinessSignals;
    reportType?: ReportType;
    companyName?: string;
    period?: string;
    filingDate?: string;
    keyMetrics: MetricInsight[];
    businessDrivers: BusinessDriver[];
    riskFactors: RiskFactor[];
    bullCase: string;
    bearCase: string;
    citations: Citation[];
    metadata: AnalysisMetadata;
    sourceContext?: SourceContext;
    currency?: string; // Added currency field

    // Advanced Insights
    dupontAnalysis?: DuPontAnalysis;
    insightEngine?: InsightEngine;
    factorAnalysis?: FactorAnalysis;
    topicTrends?: TopicTrend[];
}

// --- Advanced Insights Types ---

export interface DuPontAnalysis {
    netProfitMargin: string;
    assetTurnover: string;
    equityMultiplier: string;
    returnOnEquity: string;
    interpretation: string;
}

export interface InsightEngine {
    accountingChanges: AccountingChange[];
    rootCauseAnalysis: RootCauseEntry[];
}

export interface AccountingChange {
    policyName: string;
    changeDescription: string;
    riskAssessment: 'high' | 'medium' | 'low';
}

export interface RootCauseEntry {
    metric: string;
    reason: string;
    evidence: string;
}

export interface FactorAnalysis {
    revenueBridge: FactorBridgeItem[];
    marginBridge: FactorBridgeItem[];
}

export interface FactorBridgeItem {
    name: string;
    impact: string; // "+5%", "+", "-2%", "-"
    description: string;
}

export interface TopicTrend {
    topic: string;
    frequency: number; // 1-100
    sentiment: 'positive' | 'negative' | 'neutral';
}
