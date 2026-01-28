package com.springalpha.backend.financial.model;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.Map;

/**
 * Financial Facts - The single source of truth for all financial metrics.
 * This class contains only computed facts, never AI-generated interpretations.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class FinancialFacts {

    // Basic Information
    private String ticker;
    private String companyName;
    private String period; // e.g., "Q3 2024", "FY 2023"
    private String filingDate;

    // Revenue Metrics
    private BigDecimal revenue;
    private BigDecimal revenueYoY; // Year-over-Year growth
    private BigDecimal revenueQoQ; // Quarter-over-Quarter growth

    // Profitability Metrics
    private BigDecimal grossProfit;
    private BigDecimal grossMargin;
    private BigDecimal grossMarginChange;

    private BigDecimal operatingIncome;
    private BigDecimal operatingMargin;
    private BigDecimal operatingMarginChange;

    private BigDecimal netIncome;
    private BigDecimal netMargin;
    private BigDecimal netMarginChange;

    // Cash Flow Metrics
    private BigDecimal operatingCashFlow;
    private BigDecimal operatingCashFlowYoY;
    private BigDecimal freeCashFlow;
    private BigDecimal freeCashFlowYoY;

    // Balance Sheet Metrics
    private BigDecimal totalAssets;
    private BigDecimal totalLiabilities;
    private BigDecimal totalEquity;
    private BigDecimal debtToEquityRatio;

    // Efficiency Metrics
    private BigDecimal returnOnEquity; // ROE
    private BigDecimal returnOnAssets; // ROA

    // Additional computed metrics can be stored here as a flexible map
    private Map<String, BigDecimal> additionalMetrics;

    /**
     * Check if this is a quarterly or annual report
     */
    public boolean isQuarterly() {
        return period != null && period.toUpperCase().startsWith("Q");
    }

    /**
     * Check if this is an annual report
     */
    public boolean isAnnual() {
        return period != null && (period.toUpperCase().startsWith("FY")
                || period.toUpperCase().startsWith("YEAR"));
    }
}
