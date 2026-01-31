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
}
