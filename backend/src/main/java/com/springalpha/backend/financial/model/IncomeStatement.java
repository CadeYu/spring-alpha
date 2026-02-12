package com.springalpha.backend.financial.model;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * Income Statement (Profit & Loss Statement) data structure.
 * Represents a single period's income statement.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class IncomeStatement {

    private String period;
    private String reportedCurrency; // e.g. USD, JPY, CNY

    // Revenue
    private BigDecimal revenue;
    private BigDecimal costOfRevenue;

    // Gross Profit
    private BigDecimal grossProfit;

    // Operating Expenses
    private BigDecimal researchAndDevelopment;
    private BigDecimal sellingGeneralAndAdministrative;
    private BigDecimal totalOperatingExpenses;

    // Operating Income
    private BigDecimal operatingIncome;

    // Non-Operating Items
    private BigDecimal interestExpense;
    private BigDecimal otherIncomeExpense;

    // Pre-tax Income
    private BigDecimal incomeBeforeTax;

    // Tax
    private BigDecimal incomeTaxExpense;

    // Net Income
    private BigDecimal netIncome;

    // Per Share Data
    private BigDecimal earningsPerShareBasic;
    private BigDecimal earningsPerShareDiluted;
    private BigDecimal weightedAverageShares;

    /**
     * Calculate gross margin
     */
    public BigDecimal getGrossMargin() {
        if (revenue == null || revenue.compareTo(BigDecimal.ZERO) == 0) {
            return BigDecimal.ZERO;
        }
        return grossProfit.divide(revenue, 4, BigDecimal.ROUND_HALF_UP);
    }

    /**
     * Calculate operating margin
     */
    public BigDecimal getOperatingMargin() {
        if (revenue == null || revenue.compareTo(BigDecimal.ZERO) == 0) {
            return BigDecimal.ZERO;
        }
        return operatingIncome.divide(revenue, 4, BigDecimal.ROUND_HALF_UP);
    }

    /**
     * Calculate net margin
     */
    public BigDecimal getNetMargin() {
        if (revenue == null || revenue.compareTo(BigDecimal.ZERO) == 0) {
            return BigDecimal.ZERO;
        }
        return netIncome.divide(revenue, 4, BigDecimal.ROUND_HALF_UP);
    }
}
