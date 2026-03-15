package com.springalpha.backend.financial.service;

import java.math.BigDecimal;

public record FmpSupplementalData(
        boolean profileAvailable,
        boolean quoteAvailable,
        boolean valuationAvailable,
        String companyName,
        BigDecimal latestPrice,
        BigDecimal marketCap,
        BigDecimal priceToEarningsRatio,
        BigDecimal priceToBookRatio,
        String message) {
}
