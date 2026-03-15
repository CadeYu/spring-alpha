package com.springalpha.backend.financial.service;

import java.math.BigDecimal;
import java.util.List;

public record MarketSupplementalData(
        String provider,
        boolean profileAvailable,
        boolean quoteAvailable,
        boolean valuationAvailable,
        String companyName,
        String sector,
        String industry,
        String securityType,
        BigDecimal latestPrice,
        BigDecimal marketCap,
        BigDecimal priceToEarningsRatio,
        BigDecimal priceToBookRatio,
        List<QuarterlyFinancialSnapshot> quarterlyFinancials,
        String message,
        String businessSummary) {

    public record QuarterlyFinancialSnapshot(
            String periodEnd,
            BigDecimal revenue,
            BigDecimal grossProfit,
            BigDecimal operatingIncome,
            BigDecimal netIncome,
            BigDecimal operatingCashFlow,
            BigDecimal freeCashFlow) {
    }
}
