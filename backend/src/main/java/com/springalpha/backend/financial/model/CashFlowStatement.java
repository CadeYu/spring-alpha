package com.springalpha.backend.financial.model;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * Cash Flow Statement data structure.
 * Represents cash movements from operating, investing, and financing
 * activities.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CashFlowStatement {

    private String period;

    // Operating Activities
    private BigDecimal netIncome;
    private BigDecimal depreciationAndAmortization;
    private BigDecimal stockBasedCompensation;
    private BigDecimal changeInWorkingCapital;
    private BigDecimal operatingCashFlow;

    // Investing Activities
    private BigDecimal capitalExpenditures;
    private BigDecimal acquisitions;
    private BigDecimal investmentPurchases;
    private BigDecimal investingCashFlow;

    // Financing Activities
    private BigDecimal debtIssuance;
    private BigDecimal debtRepayment;
    private BigDecimal dividendsPaid;
    private BigDecimal stockRepurchases;
    private BigDecimal financingCashFlow;

    // Net Change
    private BigDecimal netChangeInCash;

    /**
     * Calculate free cash flow (Operating Cash Flow - CapEx)
     */
    public BigDecimal getFreeCashFlow() {
        BigDecimal opCash = operatingCashFlow != null ? operatingCashFlow : BigDecimal.ZERO;
        BigDecimal capex = capitalExpenditures != null ? capitalExpenditures : BigDecimal.ZERO;
        return opCash.subtract(capex.abs()); // CapEx is usually negative, so we use abs
    }

    /**
     * Calculate cash conversion ratio (Operating CF / Net Income)
     */
    public BigDecimal getCashConversionRatio() {
        if (netIncome == null || netIncome.compareTo(BigDecimal.ZERO) == 0) {
            return BigDecimal.ZERO;
        }
        return operatingCashFlow.divide(netIncome, 4, BigDecimal.ROUND_HALF_UP);
    }
}
