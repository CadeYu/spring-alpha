package com.springalpha.backend.financial.calculator;

import com.springalpha.backend.financial.model.*;
import org.springframework.stereotype.Component;

import java.math.BigDecimal;
import java.math.RoundingMode;

/**
 * Financial Calculator - Computes all financial metrics and ratios.
 * This is the core engine that transforms raw financial statements into
 * FinancialFacts.
 */
@Component
public class FinancialCalculator {

    private static final int PRECISION = 4;
    private static final RoundingMode ROUNDING = RoundingMode.HALF_UP;

    /**
     * Build complete FinancialFacts from financial statements.
     * 
     * @param ticker           Stock ticker symbol
     * @param companyName      Company name
     * @param period           Reporting period
     * @param currentIncome    Current period income statement
     * @param currentBalance   Current period balance sheet
     * @param currentCashFlow  Current period cash flow statement
     * @param previousIncome   Previous period income statement (for YoY/QoQ)
     * @param previousCashFlow Previous period cash flow (for YoY)
     * @return Complete FinancialFacts with all computed metrics
     */
    public FinancialFacts buildFinancialFacts(
            String ticker,
            String companyName,
            String period,
            IncomeStatement currentIncome,
            BalanceSheet currentBalance,
            CashFlowStatement currentCashFlow,
            IncomeStatement previousIncome,
            CashFlowStatement previousCashFlow) {

        FinancialFacts.FinancialFactsBuilder builder = FinancialFacts.builder()
                .ticker(ticker)
                .companyName(companyName)
                .period(period);

        // Revenue metrics
        if (currentIncome != null) {
            builder.revenue(currentIncome.getRevenue());

            if (previousIncome != null && previousIncome.getRevenue() != null) {
                builder.revenueYoY(calculateGrowthRate(
                        previousIncome.getRevenue(),
                        currentIncome.getRevenue()));
            }

            // Profitability metrics
            builder.grossProfit(currentIncome.getGrossProfit())
                    .grossMargin(currentIncome.getGrossMargin());

            if (previousIncome != null) {
                BigDecimal prevGrossMargin = previousIncome.getGrossMargin();
                BigDecimal currentGrossMargin = currentIncome.getGrossMargin();
                if (prevGrossMargin != null && currentGrossMargin != null) {
                    builder.grossMarginChange(currentGrossMargin.subtract(prevGrossMargin));
                }
            }

            builder.operatingIncome(currentIncome.getOperatingIncome())
                    .operatingMargin(currentIncome.getOperatingMargin());

            if (previousIncome != null) {
                BigDecimal prevOpMargin = previousIncome.getOperatingMargin();
                BigDecimal currentOpMargin = currentIncome.getOperatingMargin();
                if (prevOpMargin != null && currentOpMargin != null) {
                    builder.operatingMarginChange(currentOpMargin.subtract(prevOpMargin));
                }
            }

            builder.netIncome(currentIncome.getNetIncome())
                    .netMargin(currentIncome.getNetMargin());

            if (previousIncome != null) {
                BigDecimal prevNetMargin = previousIncome.getNetMargin();
                BigDecimal currentNetMargin = currentIncome.getNetMargin();
                if (prevNetMargin != null && currentNetMargin != null) {
                    builder.netMarginChange(currentNetMargin.subtract(prevNetMargin));
                }
            }
        }

        // Balance sheet metrics
        if (currentBalance != null) {
            builder.totalAssets(currentBalance.getTotalAssets())
                    .totalLiabilities(currentBalance.getTotalLiabilities())
                    .totalEquity(currentBalance.getTotalEquity())
                    .debtToEquityRatio(currentBalance.getDebtToEquityRatio());

            // Calculate ROE and ROA if we have net income
            if (currentIncome != null && currentIncome.getNetIncome() != null) {
                if (currentBalance.getTotalEquity() != null &&
                        currentBalance.getTotalEquity().compareTo(BigDecimal.ZERO) > 0) {
                    BigDecimal roe = currentIncome.getNetIncome()
                            .divide(currentBalance.getTotalEquity(), PRECISION, ROUNDING);
                    builder.returnOnEquity(roe);
                }

                if (currentBalance.getTotalAssets() != null &&
                        currentBalance.getTotalAssets().compareTo(BigDecimal.ZERO) > 0) {
                    BigDecimal roa = currentIncome.getNetIncome()
                            .divide(currentBalance.getTotalAssets(), PRECISION, ROUNDING);
                    builder.returnOnAssets(roa);
                }
            }
        }

        // Cash flow metrics
        if (currentCashFlow != null) {
            builder.operatingCashFlow(currentCashFlow.getOperatingCashFlow())
                    .freeCashFlow(currentCashFlow.getFreeCashFlow());

            if (previousCashFlow != null && previousCashFlow.getOperatingCashFlow() != null) {
                builder.operatingCashFlowYoY(calculateGrowthRate(
                        previousCashFlow.getOperatingCashFlow(),
                        currentCashFlow.getOperatingCashFlow()));

                if (previousCashFlow.getFreeCashFlow() != null) {
                    builder.freeCashFlowYoY(calculateGrowthRate(
                            previousCashFlow.getFreeCashFlow(),
                            currentCashFlow.getFreeCashFlow()));
                }
            }
        }

        return builder.build();
    }

    /**
     * Calculate growth rate between two periods.
     * Formula: (current - previous) / previous
     */
    private BigDecimal calculateGrowthRate(BigDecimal previous, BigDecimal current) {
        if (previous == null || current == null || previous.compareTo(BigDecimal.ZERO) == 0) {
            return BigDecimal.ZERO;
        }
        return current.subtract(previous)
                .divide(previous.abs(), PRECISION, ROUNDING);
    }
}
