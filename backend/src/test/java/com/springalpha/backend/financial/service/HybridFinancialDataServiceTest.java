package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.List;
import java.util.Optional;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class HybridFinancialDataServiceTest {

    @Test
    void usesSecCoreFactsAndTreatsMarketEnrichmentAsOptional() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        FinancialFacts secFacts = FinancialFacts.builder()
                .ticker("ORCL")
                .companyName("Oracle Corporation")
                .period("FY2026 Q3")
                .filingDate("2026-03-10")
                .revenue(new BigDecimal("14500000000"))
                .earningsPerShare(new BigDecimal("1.50"))
                .totalEquity(new BigDecimal("18000000000"))
                .build();

        when(secService.getFinancialFacts("ORCL", "quarterly")).thenReturn(secFacts);
        when(enrichmentService.getSupplementalData("ORCL", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "Oracle Corporation",
                "Technology",
                "Software - Infrastructure",
                "EQUITY",
                new BigDecimal("30.00"),
                new BigDecimal("144000000000"),
                new BigDecimal("18.4000"),
                new BigDecimal("7.1000"),
                java.util.List.of(new MarketSupplementalData.QuarterlyFinancialSnapshot(
                        "2025-02-28",
                        new BigDecimal("14500000000"),
                        new BigDecimal("10150000000"),
                        new BigDecimal("4500000000"),
                        new BigDecimal("3100000000"),
                        new BigDecimal("5600000000"),
                        new BigDecimal("80000000"))),
                "Supplemental FMP data unavailable for: valuation",
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("ORCL", "quarterly");

        assertNotNull(facts);
        assertEquals("Oracle Corporation", facts.getCompanyName());
        assertEquals(new BigDecimal("10150000000"), facts.getGrossProfit());
        assertEquals(new BigDecimal("0.7000"), facts.getGrossMargin());
        assertEquals(new BigDecimal("5600000000"), facts.getOperatingCashFlow());
        assertEquals(new BigDecimal("80000000"), facts.getFreeCashFlow());
        assertEquals(new BigDecimal("18.4000"), facts.getPriceToEarningsRatio());
        assertEquals(new BigDecimal("7.1000"), facts.getPriceToBookRatio());
        assertEquals("Technology", facts.getMarketSector());
        assertEquals("Software - Infrastructure", facts.getMarketIndustry());
        assertEquals("EQUITY", facts.getMarketSecurityType());
        assertEquals("standard", facts.getDashboardMode());
        verify(secService).getFinancialFacts("ORCL", "quarterly");
        verify(enrichmentService).getSupplementalData("ORCL", "quarterly");
    }

    @Test
    void supplementsMissingHistoryMarginsFromYahooQuarterlyStatements() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        when(secService.getHistoricalData("ORCL", "quarterly")).thenReturn(List.of(
                HistoricalDataPoint.builder()
                        .period("FY2026 Q3")
                        .revenue(new BigDecimal("14130000000"))
                        .netIncome(new BigDecimal("2936000000"))
                        .grossMargin(null)
                        .operatingMargin(null)
                        .netMargin(null)
                        .build()));

        when(enrichmentService.getSupplementalData("ORCL", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                false,
                "Oracle Corporation",
                "Technology",
                "Software - Infrastructure",
                "EQUITY",
                new BigDecimal("30.00"),
                new BigDecimal("144000000000"),
                null,
                null,
                List.of(new MarketSupplementalData.QuarterlyFinancialSnapshot(
                        "2025-02-28",
                        new BigDecimal("14130000000"),
                        new BigDecimal("9935000000"),
                        new BigDecimal("4449000000"),
                        new BigDecimal("2936000000"),
                        new BigDecimal("5933000000"),
                        new BigDecimal("71000000"))),
                null,
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        List<HistoricalDataPoint> history = service.getHistoricalData("ORCL", "quarterly");

        assertNotNull(history);
        assertEquals(1, history.size());
        assertEquals(new BigDecimal("0.7031"), history.get(0).getGrossMargin());
        assertEquals(new BigDecimal("0.3149"), history.get(0).getOperatingMargin());
        assertEquals(new BigDecimal("0.2078"), history.get(0).getNetMargin());
        verify(secService).getHistoricalData("ORCL", "quarterly");
        verify(enrichmentService).getSupplementalData("ORCL", "quarterly");
    }

    @Test
    void marksBanksAsFinancialSectorMode() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        FinancialFacts secFacts = FinancialFacts.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .period("FY2025 Q4")
                .filingDate("2026-01-14")
                .revenue(new BigDecimal("44000000000"))
                .build();

        when(secService.getFinancialFacts("JPM", "quarterly")).thenReturn(secFacts);
        when(enrichmentService.getSupplementalData("JPM", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "JPMorgan Chase & Co.",
                "Financial Services",
                "Banks - Diversified",
                "EQUITY",
                new BigDecimal("240.00"),
                new BigDecimal("680000000000"),
                new BigDecimal("14.0000"),
                new BigDecimal("2.1000"),
                List.of(),
                null,
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("JPM", "quarterly");

        assertNotNull(facts);
        assertEquals("financial_sector", facts.getDashboardMode());
        assertNotNull(facts.getDashboardMessage());
    }

    @Test
    void keepsPaymentNetworksInStandardMode() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        FinancialFacts secFacts = FinancialFacts.builder()
                .ticker("V")
                .companyName("Visa Inc.")
                .period("FY2025 Q4")
                .filingDate("2026-01-28")
                .revenue(new BigDecimal("9500000000"))
                .build();

        when(secService.getFinancialFacts("V", "quarterly")).thenReturn(secFacts);
        when(enrichmentService.getSupplementalData("V", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "Visa Inc.",
                "Financial Services",
                "Credit Services",
                "EQUITY",
                new BigDecimal("320.00"),
                new BigDecimal("620000000000"),
                new BigDecimal("31.0000"),
                new BigDecimal("18.5000"),
                List.of(),
                null,
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("V", "quarterly");

        assertNotNull(facts);
        assertEquals("standard", facts.getDashboardMode());
        assertNull(facts.getDashboardMessage());
    }

    @Test
    void backfillsBankRevenueAndCashFlowFromYahooWhenSecRevenueIsMissing() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        FinancialFacts secFacts = FinancialFacts.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .period("FY2025 Q4")
                .filingDate("2026-01-14")
                .revenue(null)
                .netIncome(new BigDecimal("13025000000"))
                .build();

        when(secService.getFinancialFacts("JPM", "quarterly")).thenReturn(secFacts);
        when(enrichmentService.getSupplementalData("JPM", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "JPMorgan Chase & Co.",
                "Financial Services",
                "Banks - Diversified",
                "EQUITY",
                new BigDecimal("282.89"),
                new BigDecimal("762963558400"),
                new BigDecimal("14.1233"),
                new BigDecimal("2.2277"),
                List.of(
                        new MarketSupplementalData.QuarterlyFinancialSnapshot(
                                "2025-12-31",
                                new BigDecimal("45796000000"),
                                null,
                                null,
                                new BigDecimal("13025000000"),
                                new BigDecimal("119724000000"),
                                new BigDecimal("119724000000")),
                        new MarketSupplementalData.QuarterlyFinancialSnapshot(
                                "2024-12-31",
                                new BigDecimal("42791000000"),
                                null,
                                null,
                                new BigDecimal("14005000000"),
                                new BigDecimal("147758000000"),
                                new BigDecimal("147758000000"))),
                null,
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("JPM", "quarterly");

        assertNotNull(facts);
        assertEquals(new BigDecimal("45796000000"), facts.getRevenue());
        assertEquals(new BigDecimal("119724000000"), facts.getOperatingCashFlow());
        assertEquals(new BigDecimal("119724000000"), facts.getFreeCashFlow());
        assertEquals(new BigDecimal("0.0702"), facts.getRevenueYoY());
        assertEquals(new BigDecimal("-0.1897"), facts.getOperatingCashFlowYoY());
        assertEquals(new BigDecimal("-0.1897"), facts.getFreeCashFlowYoY());
        assertEquals("financial_sector", facts.getDashboardMode());
    }

    @Test
    void backfillsHistoryRevenueFromYahooWhenSecHistoryHasOnlyNetIncome() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        when(secService.getHistoricalData("JPM", "quarterly")).thenReturn(List.of(
                HistoricalDataPoint.builder()
                        .period("FY2025 Q1")
                        .revenue(null)
                        .netIncome(new BigDecimal("14643000000"))
                        .grossMargin(null)
                        .operatingMargin(null)
                        .netMargin(null)
                        .build(),
                HistoricalDataPoint.builder()
                        .period("FY2025 Q2")
                        .revenue(null)
                        .netIncome(new BigDecimal("14987000000"))
                        .grossMargin(null)
                        .operatingMargin(null)
                        .netMargin(null)
                        .build(),
                HistoricalDataPoint.builder()
                        .period("FY2025 Q3")
                        .revenue(null)
                        .netIncome(new BigDecimal("14393000000"))
                        .grossMargin(null)
                        .operatingMargin(null)
                        .netMargin(null)
                        .build()));

        when(enrichmentService.getSupplementalData("JPM", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "JPMorgan Chase & Co.",
                "Financial Services",
                "Banks - Diversified",
                "EQUITY",
                new BigDecimal("282.89"),
                new BigDecimal("762963558400"),
                new BigDecimal("14.1233"),
                new BigDecimal("2.2277"),
                List.of(
                        new MarketSupplementalData.QuarterlyFinancialSnapshot(
                                "2025-09-30",
                                new BigDecimal("46430000000"),
                                null,
                                null,
                                new BigDecimal("14393000000"),
                                new BigDecimal("-45214000000"),
                                new BigDecimal("-45214000000")),
                        new MarketSupplementalData.QuarterlyFinancialSnapshot(
                                "2025-06-30",
                                new BigDecimal("44882000000"),
                                null,
                                null,
                                new BigDecimal("14987000000"),
                                new BigDecimal("29547000000"),
                                new BigDecimal("29547000000")),
                        new MarketSupplementalData.QuarterlyFinancialSnapshot(
                                "2025-03-31",
                                new BigDecimal("45327000000"),
                                null,
                                null,
                                new BigDecimal("14643000000"),
                                new BigDecimal("-251839000000"),
                                new BigDecimal("-251839000000"))),
                null,
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        List<HistoricalDataPoint> history = service.getHistoricalData("JPM", "quarterly");

        assertNotNull(history);
        assertEquals(3, history.size());
        assertEquals(new BigDecimal("45327000000"), history.get(0).getRevenue());
        assertEquals(new BigDecimal("44882000000"), history.get(1).getRevenue());
        assertEquals(new BigDecimal("46430000000"), history.get(2).getRevenue());
        assertEquals(new BigDecimal("0.3231"), history.get(0).getNetMargin());
        assertEquals(new BigDecimal("0.3339"), history.get(1).getNetMargin());
        assertEquals(new BigDecimal("0.3100"), history.get(2).getNetMargin());
    }

    @Test
    void doesNotForceStandardModeWhenEnrichmentReturnsNoClassificationInputs() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        FinancialFacts secFacts = FinancialFacts.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .period("FY2025 Q4")
                .filingDate("2026-01-14")
                .revenue(new BigDecimal("44000000000"))
                .build();

        when(secService.getFinancialFacts("JPM", "quarterly")).thenReturn(secFacts);
        when(enrichmentService.getSupplementalData("JPM", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                false,
                false,
                false,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                List.of(),
                "Yahoo Finance enrichment unavailable: interrupted",
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("JPM", "quarterly");

        assertNotNull(facts);
        assertNull(facts.getDashboardMode());
        assertNull(facts.getMarketSector());
        assertNull(facts.getMarketIndustry());
    }

    @Test
    void marksReitsAsUnsupportedDashboardMode() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        FinancialFacts secFacts = FinancialFacts.builder()
                .ticker("PLD")
                .companyName("Prologis, Inc.")
                .period("FY2025 Q4")
                .filingDate("2026-01-28")
                .revenue(new BigDecimal("2100000000"))
                .build();

        when(secService.getFinancialFacts("PLD", "quarterly")).thenReturn(secFacts);
        when(enrichmentService.getSupplementalData("PLD", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "Prologis, Inc.",
                "Real Estate",
                "REIT - Industrial",
                "EQUITY",
                new BigDecimal("112.00"),
                new BigDecimal("103000000000"),
                new BigDecimal("28.0000"),
                new BigDecimal("1.9000"),
                List.of(),
                null,
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("PLD", "quarterly");

        assertNotNull(facts);
        assertEquals("unsupported_reit", facts.getDashboardMode());
        assertNotNull(facts.getDashboardMessage());
    }

    @Test
    void returnsMarketOnlyFallbackFactsWhenSecLookupFailsForUnsupportedReit() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        when(secService.getFinancialFacts("BXP", "quarterly")).thenReturn(null);
        when(enrichmentService.getSupplementalData("BXP", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "BXP, Inc.",
                "Real Estate",
                "REIT - Office",
                "EQUITY",
                new BigDecimal("68.00"),
                new BigDecimal("10500000000"),
                new BigDecimal("17.4000"),
                new BigDecimal("1.0000"),
                List.of(),
                null,
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("BXP", "quarterly");

        assertNotNull(facts);
        assertEquals("BXP", facts.getTicker());
        assertEquals("BXP, Inc.", facts.getCompanyName());
        assertEquals("Real Estate", facts.getMarketSector());
        assertEquals("REIT - Office", facts.getMarketIndustry());
        assertEquals("unsupported_reit", facts.getDashboardMode());
        assertNotNull(facts.getDashboardMessage());
        assertNull(facts.getRevenue());
    }

    @Test
    void keepsReturningNullWhenSecLookupFailsForSupportedNonReitTicker() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        when(secService.getFinancialFacts("XYZ", "quarterly")).thenReturn(null);
        when(enrichmentService.getSupplementalData("XYZ", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "XYZ Corp.",
                "Technology",
                "Software - Application",
                "EQUITY",
                new BigDecimal("15.00"),
                new BigDecimal("5000000000"),
                new BigDecimal("20.0000"),
                new BigDecimal("4.0000"),
                List.of(),
                null,
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("XYZ", "quarterly");

        assertNull(facts);
    }

    @Test
    void backfillsDashboardMetadataForCachedFactsFromOlderSchema() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);
        com.springalpha.backend.financial.cache.MarketDataCacheService cacheService =
                mock(com.springalpha.backend.financial.cache.MarketDataCacheService.class);

        FinancialFacts cachedFacts = FinancialFacts.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .period("FY2025 Q4")
                .filingDate("2026-01-14")
                .revenue(new BigDecimal("44000000000"))
                .build();

        when(cacheService.getFinancialFacts("hybrid-v5-sec-report-date", "JPM", "quarterly", false))
                .thenReturn(Optional.of(cachedFacts));
        when(enrichmentService.getSupplementalData("JPM", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "JPMorgan Chase & Co.",
                "Financial Services",
                "Banks - Diversified",
                "EQUITY",
                new BigDecimal("240.00"),
                new BigDecimal("680000000000"),
                new BigDecimal("14.0000"),
                new BigDecimal("2.1000"),
                List.of(),
                null,
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                cacheService,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("JPM", "quarterly");

        assertNotNull(facts);
        assertEquals("financial_sector", facts.getDashboardMode());
        assertEquals("Financial Services", facts.getMarketSector());
        verify(enrichmentService).getSupplementalData("JPM", "quarterly");
        verify(cacheService).putFinancialFacts(anyString(), anyString(), anyString(), any(FinancialFacts.class), any());
    }

    @Test
    void backfillsCachedFactsWhenRevenueWasMissingInOlderBankPayloads() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);
        com.springalpha.backend.financial.cache.MarketDataCacheService cacheService =
                mock(com.springalpha.backend.financial.cache.MarketDataCacheService.class);

        FinancialFacts cachedFacts = FinancialFacts.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .period("FY2025 Q3")
                .filingDate("2025-11-04")
                .marketSector("Financial Services")
                .marketIndustry("Banks - Diversified")
                .marketSecurityType("EQUITY")
                .dashboardMode("financial_sector")
                .dashboardMessage("Financial sector mode is active.")
                .revenue(null)
                .netIncome(new BigDecimal("14393000000"))
                .build();

        when(cacheService.getFinancialFacts("hybrid-v5-sec-report-date", "JPM", "quarterly", false))
                .thenReturn(Optional.of(cachedFacts));
        when(enrichmentService.getSupplementalData("JPM", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "JPMorgan Chase & Co.",
                "Financial Services",
                "Banks - Diversified",
                "EQUITY",
                new BigDecimal("282.89"),
                new BigDecimal("762963558400"),
                new BigDecimal("14.1233"),
                new BigDecimal("2.2277"),
                List.of(
                        new MarketSupplementalData.QuarterlyFinancialSnapshot(
                                "2025-09-30",
                                new BigDecimal("46430000000"),
                                null,
                                null,
                                new BigDecimal("14393000000"),
                                new BigDecimal("-45214000000"),
                                new BigDecimal("-45214000000")),
                        new MarketSupplementalData.QuarterlyFinancialSnapshot(
                                "2024-09-30",
                                new BigDecimal("43432000000"),
                                null,
                                null,
                                new BigDecimal("12900000000"),
                                new BigDecimal("-38000000000"),
                                new BigDecimal("-38000000000"))),
                null,
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                cacheService,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("JPM", "quarterly");

        assertNotNull(facts);
        assertEquals(new BigDecimal("46430000000"), facts.getRevenue());
        assertEquals(new BigDecimal("-45214000000"), facts.getOperatingCashFlow());
        verify(enrichmentService).getSupplementalData("JPM", "quarterly");
        verify(cacheService).putFinancialFacts(anyString(), anyString(), anyString(), any(FinancialFacts.class), any());
    }

    @Test
    void reclassifiesCachedFactsWhenDashboardModeRuleChanges() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);
        com.springalpha.backend.financial.cache.MarketDataCacheService cacheService =
                mock(com.springalpha.backend.financial.cache.MarketDataCacheService.class);

        FinancialFacts cachedFacts = FinancialFacts.builder()
                .ticker("V")
                .companyName("Visa Inc.")
                .period("FY2025 Q4")
                .filingDate("2026-01-28")
                .revenue(new BigDecimal("9500000000"))
                .marketSector("Financial Services")
                .marketIndustry("Credit Services")
                .marketSecurityType("EQUITY")
                .dashboardMode("financial_sector")
                .dashboardMessage("Financial sector mode is active for this ticker because generic operating-company margin and cash-conversion dashboards are not reliable for bank, broker, or insurer-style filings.")
                .build();

        when(cacheService.getFinancialFacts("hybrid-v5-sec-report-date", "V", "quarterly", false))
                .thenReturn(Optional.of(cachedFacts));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                cacheService,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("V", "quarterly");

        assertNotNull(facts);
        assertEquals("standard", facts.getDashboardMode());
        assertNull(facts.getDashboardMessage());
        verify(enrichmentService).getSupplementalData("V", "quarterly");
        verify(cacheService).putFinancialFacts(anyString(), anyString(), anyString(), any(FinancialFacts.class), any());
    }

    @Test
    void preservesExistingFinancialClassificationWhenBackfillTemporarilyFails() {
        SecCompanyFactsFinancialDataService secService = mock(SecCompanyFactsFinancialDataService.class);
        MarketEnrichmentService enrichmentService = mock(MarketEnrichmentService.class);

        FinancialFacts secFacts = FinancialFacts.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .period("FY2025 Q4")
                .filingDate("2026-01-14")
                .revenue(new BigDecimal("44000000000"))
                .marketSector("Financial Services")
                .marketIndustry("Banks - Diversified")
                .marketSecurityType("EQUITY")
                .dashboardMode("financial_sector")
                .dashboardMessage("Financial sector mode is active.")
                .build();

        when(secService.getFinancialFacts("JPM", "quarterly")).thenReturn(secFacts);
        when(enrichmentService.getSupplementalData("JPM", "quarterly")).thenReturn(new MarketSupplementalData(
                "yfinance",
                false,
                false,
                false,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                null,
                List.of(),
                "Yahoo Finance enrichment unavailable: interrupted",
                null));

        HybridFinancialDataService service = new HybridFinancialDataService(
                secService,
                enrichmentService,
                null,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("JPM", "quarterly");

        assertNotNull(facts);
        assertEquals("financial_sector", facts.getDashboardMode());
        assertEquals("Financial Services", facts.getMarketSector());
        assertEquals("Banks - Diversified", facts.getMarketIndustry());
        assertEquals("EQUITY", facts.getMarketSecurityType());
        assertTrue(facts.getDashboardMessage().contains("Financial sector mode"));
    }
}
