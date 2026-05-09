package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.model.FinancialFacts;

import java.util.Optional;

/**
 * Contract for normalized financial facts used by dashboards and agent tools.
 * 
 * Production data flows through SEC company facts first, then enriches market
 * metadata and selected quote fields from Yahoo Finance. Test fixtures should be
 * profile-gated so they never participate in the production Spring context.
 */
public interface FinancialDataService {

    /**
     * Get financial facts for a given ticker.
     * 
     * @param ticker Stock ticker symbol (e.g., "AAPL")
     * @return FinancialFacts or null if not available
     */
    FinancialFacts getFinancialFacts(String ticker);

    default FinancialFacts getFinancialFacts(String ticker, String reportType) {
        return getFinancialFacts(ticker);
    }

    /**
     * Check if a ticker is supported by this implementation.
     * 
     * @param ticker Stock ticker symbol
     * @return true if data is available
     */
    boolean isSupported(String ticker);

    /**
     * Get historical margin data for trends chart.
     */
    java.util.List<com.springalpha.backend.financial.model.HistoricalDataPoint> getHistoricalData(String ticker);

    default java.util.List<com.springalpha.backend.financial.model.HistoricalDataPoint> getHistoricalData(
            String ticker,
            String reportType) {
        return getHistoricalData(ticker);
    }

    default Optional<String> resolveSecSearchIdentifier(String ticker) {
        return Optional.empty();
    }

    String[] getSupportedTickers();
}
