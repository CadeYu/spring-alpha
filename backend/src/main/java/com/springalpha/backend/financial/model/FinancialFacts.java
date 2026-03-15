package com.springalpha.backend.financial.model;

import com.fasterxml.jackson.annotation.JsonIgnore;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.util.Map;

/**
 * 财务事实数据 (Ground Truth)
 * <p>
 * 这是 RAG 流程中的 **核心数据结构**。
 * 它存储从 FMP (Financial Modeling Prep) API 获取的、经过验证的 **真实** 财务数据。
 * <p>
 * **为什么需要它？**
 * 防止 LLM 发挥想象力去"编造"数字。我们在 Prompt 中会强制 LLM 使用这里的数字
 * 进行计算和分析，而不是自己去算。
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

    // Valuation Metrics (from FMP /ratios)
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
