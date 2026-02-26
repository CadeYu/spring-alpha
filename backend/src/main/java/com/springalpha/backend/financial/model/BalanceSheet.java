package com.springalpha.backend.financial.model;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

/**
 * 资产负债表 (Balance Sheet) - FMP API 映射类
 * <p>
 * 对应 FMP API 的 `/balance-sheet-statement` 端点。
 * 包含：Total Assets, Total Liabilities, Total Equity, Cash, Debt 等。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
public class BalanceSheet {

    private String period;
    private String asOfDate;

    // Assets
    private BigDecimal cashAndCashEquivalents;
    private BigDecimal shortTermInvestments;
    private BigDecimal accountsReceivable;
    private BigDecimal inventory;
    private BigDecimal totalCurrentAssets;

    private BigDecimal propertyPlantEquipment;
    private BigDecimal intangibleAssets;
    private BigDecimal goodwill;
    private BigDecimal totalNonCurrentAssets;

    private BigDecimal totalAssets;

    // Liabilities
    private BigDecimal accountsPayable;
    private BigDecimal shortTermDebt;
    private BigDecimal totalCurrentLiabilities;

    private BigDecimal longTermDebt;
    private BigDecimal totalNonCurrentLiabilities;

    private BigDecimal totalLiabilities;

    // Equity
    private BigDecimal commonStock;
    private BigDecimal retainedEarnings;
    private BigDecimal totalEquity;

    /**
     * Calculate debt-to-equity ratio
     */
    public BigDecimal getDebtToEquityRatio() {
        if (totalEquity == null || totalEquity.compareTo(BigDecimal.ZERO) == 0) {
            return BigDecimal.ZERO;
        }
        BigDecimal totalDebt = (shortTermDebt != null ? shortTermDebt : BigDecimal.ZERO)
                .add(longTermDebt != null ? longTermDebt : BigDecimal.ZERO);
        return totalDebt.divide(totalEquity, 4, BigDecimal.ROUND_HALF_UP);
    }

    /**
     * Calculate current ratio (liquidity measure)
     */
    public BigDecimal getCurrentRatio() {
        if (totalCurrentLiabilities == null || totalCurrentLiabilities.compareTo(BigDecimal.ZERO) == 0) {
            return BigDecimal.ZERO;
        }
        return totalCurrentAssets.divide(totalCurrentLiabilities, 4, BigDecimal.ROUND_HALF_UP);
    }
}
