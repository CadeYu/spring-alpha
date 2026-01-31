package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.model.FinancialFacts;

/**
 * Financial Data Service Interface - Defines the contract for obtaining
 * financial data.
 * 
 * This abstraction ensures that:
 * 1. Data consumers don't care about the source (Mock, XBRL, API, etc.)
 * 2. We can swap implementations without breaking downstream code
 * 3. The output format (FinancialFacts) is guaranteed to be consistent
 * 
 * Implementations:
 * - MockFinancialDataService: Hardcoded data for testing
 * - XbrlFinancialDataService: Parse SEC XBRL filings (future)
 * - CachedFinancialDataService: Redis-backed cache (future)
 */
public interface FinancialDataService {

    /**
     * Get financial facts for a given ticker.
     * 
     * @param ticker Stock ticker symbol (e.g., "AAPL")
     * @return FinancialFacts or null if not available
     */
    FinancialFacts getFinancialFacts(String ticker);

    /**
     * Check if a ticker is supported by this implementation.
     * 
     * @param ticker Stock ticker symbol
     * @return true if data is available
     */
    boolean isSupported(String ticker);

    /**
     * Get list of all supported tickers.
     * Useful for testing and validation.
     * 
     * @return Array of supported ticker symbols
     */
    /**
     * Get historical margin data for trends chart.
     */
    java.util.List<com.springalpha.backend.financial.model.HistoricalDataPoint> getHistoricalData(String ticker);

    String[] getSupportedTickers();
}
