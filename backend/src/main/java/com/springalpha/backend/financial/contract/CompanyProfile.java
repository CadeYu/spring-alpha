package com.springalpha.backend.financial.contract;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Collections;
import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
@JsonInclude(JsonInclude.Include.NON_NULL)
public class CompanyProfile {

    public enum SourceQuality {
        LOW,
        MEDIUM,
        HIGH
    }

    public enum AnalysisMode {
        OPERATING,
        FINANCIAL,
        INSURANCE,
        ASSET_MANAGER,
        REIT,
        EXCHANGE_MARKET_INFRA,
        PAYMENT_FINTECH,
        CRYPTO_EXCHANGE,
        CRYPTO_TREASURY,
        HOLDING,
        BIOTECH_PRE_REVENUE,
        COMMODITY_ENERGY,
        INDUSTRIAL,
        SEMICONDUCTOR,
        TELECOM_NETWORKING,
        CONSUMER_PLATFORM,
        UNKNOWN
    }

    private String ticker;
    private String reportType;
    private String period;
    private String filingDate;

    private List<String> whatItSells;
    private List<String> customerTypes;
    private List<String> productLines;
    private List<String> keyKpis;
    private String businessModelSummary;
    private SourceQuality sourceQuality;
    private AnalysisMode analysisMode;
    private SourceQuality analysisModeConfidence;
    private List<String> businessTags;
    private List<SourceRef> sourceRefs;

    @JsonIgnore
    public boolean isEmpty() {
        return safe(whatItSells).isEmpty()
                && safe(customerTypes).isEmpty()
                && safe(productLines).isEmpty()
                && safe(keyKpis).isEmpty()
                && (businessModelSummary == null || businessModelSummary.isBlank())
                && analysisMode == null
                && safe(businessTags).isEmpty()
                && safe(sourceRefs).isEmpty();
    }

    @JsonIgnore
    public boolean hasHighConfidenceBusinessDescription() {
        return SourceQuality.HIGH.equals(sourceQuality);
    }

    @JsonIgnore
    public boolean hasHighConfidenceAnalysisMode() {
        return analysisMode != null
                && analysisMode != AnalysisMode.UNKNOWN
                && SourceQuality.HIGH.equals(analysisModeConfidence);
    }

    private <T> List<T> safe(List<T> items) {
        return items == null ? Collections.emptyList() : items;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class SourceRef {
        private String field;
        private String source;
        private String excerpt;
    }
}
