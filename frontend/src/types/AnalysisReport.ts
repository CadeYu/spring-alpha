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

export interface AnalysisReport {
    executiveSummary: string;
    keyMetrics: MetricInsight[];
    businessDrivers: BusinessDriver[];
    riskFactors: RiskFactor[];
    bullCase: string;
    bearCase: string;
    citations: Citation[];
    metadata: AnalysisMetadata;
    currency?: string; // Added currency field

    // Advanced Insights
    dupontAnalysis?: DuPontAnalysis;
    insightEngine?: InsightEngine;
    factorAnalysis?: FactorAnalysis;
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
