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
        String quoteType,
        String typeDisplay,
        String country,
        String exchange,
        String fullExchangeName,
        String currency,
        BigDecimal latestPrice,
        BigDecimal marketCap,
        BigDecimal priceToEarningsRatio,
        BigDecimal priceToBookRatio,
        List<QuarterlyFinancialSnapshot> quarterlyFinancials,
        String message,
        String businessSummary) {

    public MarketSupplementalData(
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
        this(
                provider,
                profileAvailable,
                quoteAvailable,
                valuationAvailable,
                companyName,
                sector,
                industry,
                securityType,
                null,
                null,
                null,
                null,
                null,
                null,
                latestPrice,
                marketCap,
                priceToEarningsRatio,
                priceToBookRatio,
                quarterlyFinancials,
                message,
                businessSummary);
    }

    public record QuarterlyFinancialSnapshot(
            String periodEnd,
            BigDecimal revenue,
            BigDecimal grossProfit,
            BigDecimal operatingIncome,
            BigDecimal netIncome,
            BigDecimal operatingCashFlow,
            BigDecimal capitalExpenditures,
            BigDecimal freeCashFlow,
            BigDecimal cashAndShortTermInvestments,
            BigDecimal currentAssets,
            BigDecimal currentLiabilities,
            BigDecimal totalDebt) {
    }
}
