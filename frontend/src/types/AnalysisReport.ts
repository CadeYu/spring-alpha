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
    agentEvents?: AgentEventMetadata[];
}

export interface AgentEventMetadata {
    phase: string;
    status: string;
    summary: string;
    toolName?: string | null;
    eventKind?: 'reasoning' | 'tool' | string | null;
    agentName?: string | null;
    modelName?: string | null;
    toolInput?: Record<string, unknown> | null;
    usage?: Record<string, unknown> | null;
    latencyMs?: number;
    degradedReason?: string | null;
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

export type TaskSectionSchemaVersion = 'task_sections.v1';

export type ResearchTaskType =
    | 'latest_earnings_readout'
    | 'business_driver_deep_dive'
    | 'cash_flow_capital_allocation';

export type TaskCitationStatus = 'supported' | 'partial' | 'missing' | 'unverified';

export interface TaskSectionCoverage {
    status: 'complete' | 'partial' | 'degraded';
    missingSections: string[];
    evidenceCount: number;
}

export interface EvidenceRef {
    section: string;
    excerpt: string;
    filingDate?: string;
    accessionNumber?: string;
    sourceId?: string;
}

export interface EvidenceBoundPoint {
    title: string;
    summary: string;
    evidenceRefs: EvidenceRef[];
    citationStatus: TaskCitationStatus;
}

export interface EvidenceBoundMetric {
    name: string;
    value: string;
    period?: string;
    interpretation: string;
    evidenceRefs: EvidenceRef[];
    citationStatus: TaskCitationStatus;
}

export interface CompanyProfileSection {
    summary: string;
    evidenceRefs: EvidenceRef[];
    citationStatus: TaskCitationStatus;
}

export interface BaseTaskSections {
    schemaVersion: TaskSectionSchemaVersion;
    taskType: ResearchTaskType;
    coverage: TaskSectionCoverage;
}

export interface LatestEarningsSections extends BaseTaskSections {
    taskType: 'latest_earnings_readout';
    companyProfile?: CompanyProfileSection | null;
    toplineVerdict: {
        headline: string;
        summary: string;
        verdict: 'positive' | 'mixed' | 'negative';
    };
    keyTakeaways: EvidenceBoundPoint[];
    financialDashboard: {
        metrics: EvidenceBoundMetric[];
        chartFocus: string[];
    };
    driverSnapshot: EvidenceBoundPoint[];
    riskSnapshot: EvidenceBoundPoint[];
}

export interface BusinessDriverSections extends BaseTaskSections {
    taskType: 'business_driver_deep_dive';
    driverThesis: {
        headline: string;
        durability: 'durable' | 'mixed' | 'temporary' | 'unclear';
        summary: string;
    };
    driverMap: {
        product: EvidenceBoundPoint[];
        segment: EvidenceBoundPoint[];
        geography: EvidenceBoundPoint[];
        demand: EvidenceBoundPoint[];
        pricing: EvidenceBoundPoint[];
        customer: EvidenceBoundPoint[];
        strategy: EvidenceBoundPoint[];
    };
    positiveSignals: EvidenceBoundPoint[];
    negativeSignals: EvidenceBoundPoint[];
    watchlist: string[];
}

export interface CashFlowCapitalAllocationSections extends BaseTaskSections {
    taskType: 'cash_flow_capital_allocation';
    cashQualityVerdict: {
        headline: string;
        earningsBackedByCash: 'yes' | 'mixed' | 'no' | 'unclear';
        summary: string;
    };
    cashMetrics: EvidenceBoundMetric[];
    capitalAllocation: {
        capex: EvidenceBoundPoint[];
        buybacks: EvidenceBoundPoint[];
        dividends: EvidenceBoundPoint[];
        debt: EvidenceBoundPoint[];
        liquidity: EvidenceBoundPoint[];
    };
    allocationDiscipline: EvidenceBoundPoint[];
    redFlags: EvidenceBoundPoint[];
}

export type TaskSpecificSections =
    | TaskSpecificSectionsEnvelope
    | LatestEarningsSections
    | BusinessDriverSections
    | CashFlowCapitalAllocationSections;

export interface TaskSpecificSectionsEnvelope extends BaseTaskSections {
    latestEarnings?: LatestEarningsSections | null;
    businessDriver?: BusinessDriverSections | null;
    cashFlowCapitalAllocation?: CashFlowCapitalAllocationSections | null;
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
    taskSections?: TaskSpecificSections;

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
