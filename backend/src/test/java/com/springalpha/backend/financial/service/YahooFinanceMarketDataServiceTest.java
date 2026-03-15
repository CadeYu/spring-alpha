package com.springalpha.backend.financial.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class YahooFinanceMarketDataServiceTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void returnsSupplementalDataFromHelperOutput() {
        YahooFinanceMarketDataService.ProcessRunner runner = (command, timeout) -> new YahooFinanceMarketDataService.ProcessResult(
                0,
                """
                        {
                          "profileAvailable": true,
                          "quoteAvailable": true,
                          "valuationAvailable": true,
                          "companyName": "Oracle Corporation",
                          "sector": "Technology",
                          "industry": "Software - Infrastructure",
                          "securityType": "EQUITY",
                          "latestPrice": 30.0,
                          "marketCap": 144000000000,
                          "priceToEarningsRatio": 20.5,
                          "priceToBookRatio": 5.2,
                          "quarterlyFinancials": [
                            {
                              "periodEnd": "2025-02-28",
                              "revenue": 14130000000,
                              "grossProfit": 9935000000,
                              "operatingIncome": 4449000000,
                              "netIncome": 2936000000,
                              "operatingCashFlow": 5933000000,
                              "freeCashFlow": 71000000
                            }
                          ],
                          "message": null,
                          "businessSummary": "Oracle provides enterprise infrastructure software and cloud services."
                        }
                        """,
                "");

        YahooFinanceMarketDataService service = new YahooFinanceMarketDataService(
                objectMapper,
                "python3",
                Duration.ofHours(1),
                Duration.ofSeconds(5),
                runner);

        MarketSupplementalData data = service.getSupplementalData("orcl", "quarterly");

        assertEquals("yfinance", data.provider());
        assertTrue(data.profileAvailable());
        assertTrue(data.quoteAvailable());
        assertEquals("Oracle Corporation", data.companyName());
        assertEquals("Technology", data.sector());
        assertEquals("Software - Infrastructure", data.industry());
        assertEquals("EQUITY", data.securityType());
        assertEquals(new BigDecimal("30.0"), data.latestPrice());
        assertEquals(new BigDecimal("144000000000"), data.marketCap());
        assertTrue(data.valuationAvailable());
        assertEquals(new BigDecimal("20.5"), data.priceToEarningsRatio());
        assertEquals(new BigDecimal("5.2"), data.priceToBookRatio());
        assertEquals("Oracle provides enterprise infrastructure software and cloud services.", data.businessSummary());
        assertEquals(1, data.quarterlyFinancials().size());
        assertEquals(new BigDecimal("14130000000"), data.quarterlyFinancials().get(0).revenue());
    }

    @Test
    void degradesGracefullyWhenHelperFails() {
        YahooFinanceMarketDataService.ProcessRunner runner = (command, timeout) -> new YahooFinanceMarketDataService.ProcessResult(
                3,
                "",
                "Python package 'yfinance' is not installed.");

        YahooFinanceMarketDataService service = new YahooFinanceMarketDataService(
                objectMapper,
                "python3",
                Duration.ofHours(1),
                Duration.ofSeconds(5),
                runner);

        MarketSupplementalData data = service.getSupplementalData("ORCL", "quarterly");

        assertFalse(data.profileAvailable());
        assertFalse(data.quoteAvailable());
        assertFalse(data.valuationAvailable());
        assertTrue(data.message().contains("yfinance"));
    }

    @Test
    void retriesWithDashAliasWhenDotTickerReturnsEmptyPayload() {
        YahooFinanceMarketDataService.ProcessRunner runner = (command, timeout) -> {
            String ticker = command.get(command.size() - 1);
            if ("BRK.B".equals(ticker)) {
                return new YahooFinanceMarketDataService.ProcessResult(
                        0,
                        """
                                {
                                  "profileAvailable": false,
                                  "quoteAvailable": false,
                                  "valuationAvailable": false,
                                  "companyName": null,
                                  "sector": null,
                                  "industry": null,
                                  "securityType": null,
                                  "latestPrice": null,
                                  "marketCap": null,
                                  "priceToEarningsRatio": null,
                                  "priceToBookRatio": null,
                                  "quarterlyFinancials": [],
                                  "message": "No data",
                                  "businessSummary": null
                                }
                                """,
                        "");
            }

            return new YahooFinanceMarketDataService.ProcessResult(
                    0,
                    """
                            {
                              "profileAvailable": true,
                              "quoteAvailable": true,
                              "valuationAvailable": true,
                              "companyName": "Berkshire Hathaway Inc.",
                              "sector": "Financial Services",
                              "industry": "Insurance - Diversified",
                              "securityType": "EQUITY",
                              "latestPrice": 512.4,
                              "marketCap": 1100000000000,
                              "priceToEarningsRatio": 14.4,
                              "priceToBookRatio": 1.6,
                              "quarterlyFinancials": [],
                              "message": null,
                              "businessSummary": null
                            }
                            """,
                    "");
        };

        YahooFinanceMarketDataService service = new YahooFinanceMarketDataService(
                objectMapper,
                "python3",
                Duration.ofHours(1),
                Duration.ofSeconds(5),
                runner);

        MarketSupplementalData data = service.getSupplementalData("BRK.B", "quarterly");

        assertTrue(data.profileAvailable());
        assertEquals("Berkshire Hathaway Inc.", data.companyName());
        assertEquals("Financial Services", data.sector());
        assertEquals(new BigDecimal("14.4"), data.priceToEarningsRatio());
    }

    @Test
    void doesNotCacheUnavailableResultsAcrossCalls() {
        AtomicBoolean returnSuccess = new AtomicBoolean(false);
        YahooFinanceMarketDataService.ProcessRunner runner = (command, timeout) -> {
            if (!returnSuccess.get()) {
                return new YahooFinanceMarketDataService.ProcessResult(
                        3,
                        "",
                        "temporary helper failure");
            }

            return new YahooFinanceMarketDataService.ProcessResult(
                    0,
                    """
                            {
                              "profileAvailable": true,
                              "quoteAvailable": true,
                              "valuationAvailable": true,
                              "companyName": "JPMorgan Chase & Co.",
                              "sector": "Financial Services",
                              "industry": "Banks - Diversified",
                              "securityType": "EQUITY",
                              "latestPrice": 282.89,
                              "marketCap": 762963558400,
                              "priceToEarningsRatio": 14.13,
                              "priceToBookRatio": 2.22,
                              "quarterlyFinancials": [],
                              "message": null,
                              "businessSummary": null
                            }
                            """,
                    "");
        };

        YahooFinanceMarketDataService service = new YahooFinanceMarketDataService(
                objectMapper,
                "python3",
                Duration.ofHours(1),
                Duration.ofSeconds(5),
                runner);

        MarketSupplementalData first = service.getSupplementalData("JPM", "quarterly");
        assertFalse(first.profileAvailable());

        returnSuccess.set(true);
        MarketSupplementalData second = service.getSupplementalData("JPM", "quarterly");

        assertTrue(second.profileAvailable());
        assertEquals("Financial Services", second.sector());
        assertEquals("Banks - Diversified", second.industry());
    }
}
