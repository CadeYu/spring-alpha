package com.springalpha.backend.financial.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.Map;

/**
 * Normalized financial facts from SEC companyfacts with Yahoo market enrichment.
 *
 * This model is the Java boundary object for dashboards and Python Agent
 * requests. Numeric fundamentals should originate from SEC filings whenever
 * available; market profile, security classification, and valuation context may
 * come from Yahoo Finance enrichment.
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
    private String currency; // e.g. USD, JPY
    private String marketSector;
    private String marketIndustry;
    private String marketSecurityType;
    private String marketBusinessSummary;
    private String dashboardMode;
    private String dashboardMessage;

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
    private BigDecimal earningsPerShare; // Added EPS

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

    // Valuation Metrics (from market enrichment)
    private BigDecimal priceToEarningsRatio; // P/E
    private BigDecimal priceToBookRatio; // P/B

    // Additional computed metrics can be stored here as a flexible map
    private Map<String, BigDecimal> additionalMetrics;

    /**
     * Check if this looks like a quarterly report label.
     */
    @JsonIgnore
    public boolean isQuarterly() {
        return period != null && period.toUpperCase().contains("Q");
    }
}
