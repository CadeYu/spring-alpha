package com.springalpha.backend.financial.contract;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonAlias;

import java.util.List;

/**
 * Analysis Report - The standardized output structure for all AI strategies.
 * This ensures consistent, structured reporting across different models.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class AnalysisReport {

    /**
     * High-level executive summary (2-3 sentences)
     */
    private String executiveSummary;

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
        private String excerpt; // Short text snippet
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
        private String modelName; // e.g., "gpt-4", "gemini-1.5-flash"
        private String generatedAt; // ISO timestamp
        private String language; // "en", "zh"
    }
}
