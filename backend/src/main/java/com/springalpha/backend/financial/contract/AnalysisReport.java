package com.springalpha.backend.financial.contract;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonAlias;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.List;
import java.util.Map;

/**
 * 分析报告 (The Output)
 * <p>
 * 这是系统最终生成的结构化报告。
 * 所有的 AI 策略 (OpenAI, Groq, ChatAnywhere) **必须** 返回这个结构的 JSON。
 * <p>
 * **核心部分**:
 * - `coreThesis`: 结构化核心分析 (研究观点、证据、跟踪点)。
 * - `executiveSummary`: 兼容旧版摘要字符串。
 * - `keyMetrics`: 关键指标分析 (含数值、解释、情感向)。
 * - `businessDrivers`: 业务驱动因素 (SWOT 分析)。
 * - `citations`: 引用来源 (RAG 溯源，增强可信度)。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
@JsonInclude(JsonInclude.Include.NON_NULL)
public class AnalysisReport {

    /**
     * Backward-compatible freeform executive summary.
     */
    private String executiveSummary;

    /**
     * Structured first-screen research thesis.
     */
    private CoreThesis coreThesis;

    /**
     * Structured business-first signals extracted from filing evidence.
     * This is used to render the first screen around operating narrative,
     * not around repeated metric recap.
     */
    private BusinessSignals businessSignals;

    /**
     * Key financial metric insights with interpretations
     */
    private List<MetricInsight> keyMetrics;

    /**
     * Business drivers analysis
     */
    private List<BusinessDriver> businessDrivers;

    /**
     * Risk factors and uncertainties
     */
    private List<RiskFactor> riskFactors;

    /**
     * Bull case scenario
     */
    private String bullCase;

    /**
     * Bear case scenario
     */
    private String bearCase;

    /**
     * Citations linking interpretations back to evidence
     */
    private List<Citation> citations;

    /**
     * Metadata about the analysis
     */
    private AnalysisMetadata metadata;

    /**
     * Source grounding status for citation UI and degraded-mode messaging.
     */
    private SourceContext sourceContext;

    /**
     * Currency of the financial figures (e.g., "USD", "JPY")
     */
    private String currency; // Added currency field

    /**
     * Company display name from financial facts.
     */
    private String companyName;

    /**
     * Filing/report type metadata. The current product flow is quarterly-only.
     */
    private String reportType;

    /**
     * Reporting period for the analyzed filing/facts.
     */
    private String period;

    /**
     * Filing/report date in ISO-like yyyy-MM-dd form when available.
     */
    private String filingDate;

    /**
     * Task-specific typed report sections. This is additive and nullable so the
     * legacy AnalysisReport fields remain backward-compatible during migration.
     */
    private TaskSpecificSections taskSections;

    /**
     * Live RAG telemetry derived from this run's retrieval records.
     */
    private RagTelemetry ragTelemetry;

    /**
     * Represents a single financial metric with interpretation
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class MetricInsight {
        @JsonAlias("name")
        private String metricName; // e.g., "Revenue YoY Growth"
        private String value; // e.g., "8.2%"
        private String interpretation; // LLM's explanation
        private String sentiment; // "positive", "negative", "neutral"
    }

    /**
     * Represents a business driver identified by the LLM
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class BusinessDriver {
        private String title;
        private String description;
        private String impact; // "high", "medium", "low"
    }

    /**
     * Represents a risk factor
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RiskFactor {
        private String category; // e.g., "Market Risk", "Operational Risk"
        private String description;
        private String severity; // "high", "medium", "low"
    }

    /**
     * Citation linking back to source evidence
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class Citation {
        private String section; // e.g., "MD&A", "Risk Factors"
        private String excerpt; // Short text snippet (keep in English for verification)
        @JsonAlias("excerpt_zh")
        private String excerptZh; // Localized snippet for display
        private String verificationStatus; // "VERIFIED", "UNVERIFIED", "NOT_FOUND"
    }

    /**
     * Metadata about the analysis
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class AnalysisMetadata {
        private String modelName; // e.g., "gpt-4o-mini", "llama-3.3-70b"
        private String generatedAt; // ISO timestamp
        private String language; // "en", "zh"
        private List<AgentEventMetadata> agentEvents;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class AgentEventMetadata {
        private String phase;
        private String status;
        private String summary;
        private String toolName;
        private String eventKind;
        private String agentName;
        private String modelName;
        private Map<String, Object> toolInput;
        private Map<String, Object> usage;
        private long latencyMs;
        private String degradedReason;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class SourceContext {
        private String status; // "GROUNDED", "LIMITED", "DEGRADED", "UNAVAILABLE"
        private String message;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RagTelemetry {
        private int evidenceRetrieved;
        private int evidenceUsed;
        private int metricFacts;
        private int sectionsCovered;
        private long retrievalLatencyMs;
        private boolean emptyRetrieval;
        private int evidencePackBytes;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class TaskSpecificSections {
        private String schemaVersion;
        private ResearchTaskType taskType;
        private TaskSectionCoverage coverage;
        private LatestEarningsSections latestEarnings;
        private BusinessDriverSections businessDriver;
        private CashFlowCapitalAllocationSections cashFlowCapitalAllocation;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class TaskSectionCoverage {
        private String status;
        private List<String> missingSections;
        private int evidenceCount;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class EvidenceRef {
        private String section;
        private String excerpt;
        private String filingDate;
        private String accessionNumber;
        private String sourceId;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class EvidenceBoundPoint {
        private String title;
        private String summary;
        private List<EvidenceRef> evidenceRefs;
        private String citationStatus;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class EvidenceBoundMetric {
        private String name;
        private String value;
        private String period;
        private String interpretation;
        private List<EvidenceRef> evidenceRefs;
        private String citationStatus;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class LatestEarningsSections {
        private CompanyProfileSection companyProfile;
        private ToplineVerdict toplineVerdict;
        private List<EvidenceBoundPoint> keyTakeaways;
        private LatestFinancialDashboard financialDashboard;
        private List<EvidenceBoundPoint> driverSnapshot;
        private List<EvidenceBoundPoint> riskSnapshot;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class CompanyProfileSection {
        private String summary;
        private List<EvidenceRef> evidenceRefs;
        private String citationStatus;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class ToplineVerdict {
        private String headline;
        private String summary;
        private String verdict;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class LatestFinancialDashboard {
        private List<EvidenceBoundMetric> metrics;
        private List<String> chartFocus;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class BusinessDriverSections {
        private DriverThesis driverThesis;
        private DriverMap driverMap;
        private List<EvidenceBoundPoint> positiveSignals;
        private List<EvidenceBoundPoint> negativeSignals;
        private List<String> watchlist;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class DriverThesis {
        private String headline;
        private String durability;
        private String summary;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class DriverMap {
        private List<EvidenceBoundPoint> product;
        private List<EvidenceBoundPoint> segment;
        private List<EvidenceBoundPoint> geography;
        private List<EvidenceBoundPoint> demand;
        private List<EvidenceBoundPoint> pricing;
        private List<EvidenceBoundPoint> customer;
        private List<EvidenceBoundPoint> strategy;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class CashFlowCapitalAllocationSections {
        private CashQualityVerdict cashQualityVerdict;
        private List<EvidenceBoundMetric> cashMetrics;
        private CapitalAllocation capitalAllocation;
        private List<EvidenceBoundPoint> allocationDiscipline;
        private List<EvidenceBoundPoint> redFlags;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class CashQualityVerdict {
        private String headline;
        private String earningsBackedByCash;
        private String summary;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class CapitalAllocation {
        private List<EvidenceBoundPoint> capex;
        private List<EvidenceBoundPoint> buybacks;
        private List<EvidenceBoundPoint> dividends;
        private List<EvidenceBoundPoint> debt;
        private List<EvidenceBoundPoint> liquidity;
    }

    /**
     * Structured thesis block for the first-screen insight card.
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class CoreThesis {
        private String verdict; // "positive", "mixed", "negative"
        private String headline;
        private String summary;
        private List<String> whatChanged;
        private List<SupportingEvidence> drivers;
        private List<SupportingEvidence> strategicBets;
        private List<String> keyPoints;
        private List<SupportingEvidence> supportingEvidence;
        private List<String> watchItems;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class SupportingEvidence {
        private String label;
        private String detail;
    }

    /**
     * DuPont Analysis decomposition
     */
    private DuPontAnalysis dupontAnalysis;

    /**
     * AI Insight Engine results
     */
    private InsightEngine insightEngine;

    /**
     * Dynamic Factor Analysis (Waterfall charts)
     */
    private FactorAnalysis factorAnalysis;

    /**
     * Represents DuPont Analysis components
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class DuPontAnalysis {
        private String netProfitMargin; // NI / Revenue
        private String assetTurnover; // Revenue / Assets
        private String equityMultiplier; // Assets / Equity
        private String returnOnEquity; // ROE
        private String interpretation; // Analysis of the driver
    }

    /**
     * Represents AI Insights (Root Cause & Accounting Policies)
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class InsightEngine {
        private List<AccountingChange> accountingChanges;
        private List<RootCause> rootCauseAnalysis;

        @Data
        @Builder
        @NoArgsConstructor
        @AllArgsConstructor
        @JsonIgnoreProperties(ignoreUnknown = true)
        public static class AccountingChange {
            private String policyName; // e.g., "Revenue Recognition"
            private String changeDescription;
            private String riskAssessment; // "high", "medium", "low"
        }

        @Data
        @Builder
        @NoArgsConstructor
        @AllArgsConstructor
        @JsonIgnoreProperties(ignoreUnknown = true)
        public static class RootCause {
            private String metric; // e.g., "Gross Margin Decline"
            private String reason; // "Raw material price hike"
            private String evidence; // Quote
        }
    }

    /**
     * 表示因子分析 (Factor Analysis) for Waterfall Charts
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class FactorAnalysis {
        private List<Factor> revenueBridge;
        private List<Factor> marginBridge;

        @Data
        @Builder
        @NoArgsConstructor
        @AllArgsConstructor
        @JsonIgnoreProperties(ignoreUnknown = true)
        public static class Factor {
            private String name; // e.g., "Price", "Volume", "Mix"
            private String impact; // "+5.2%", "-1.1%"
            private String description;
        }
    }

    /**
     * NLP 主题趋势 (Topic Trends)
     * <p>
     * 用于生成词云 (Word Cloud) 或趋势图。
     * LLM 会从 MD&A 中提取高频战略关键词。
     */
    private List<TopicTrend> topicTrends;

    /**
     * 主题趋势数据结构
     */
    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class TopicTrend {
        /**
         * 关键词 (e.g. "AI", "Supply Chain")
         */
        private String topic;

        /**
         * 提及频次 (估算值 或 相对权重 1-100)
         */
        private int frequency;

        /**
         * 情感倾向 (positive/negative/neutral)
         * 用于词云渲染颜色 (绿/红/灰)
         */
        private String sentiment;
    }
}
