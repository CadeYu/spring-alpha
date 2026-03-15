package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.model.FinancialFacts;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class DashboardModeClassifierTest {

    @Test
    void classifiesReitsBeforeFinancialSectorKeywords() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("O")
                .companyName("Realty Income Corporation")
                .build();

        MarketSupplementalData supplementalData = new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "Realty Income Corporation",
                "Real Estate",
                "REIT - Retail",
                "EQUITY",
                null,
                null,
                null,
                null,
                java.util.List.of(),
                null,
                null);

        DashboardModeClassifier.DashboardMode mode = DashboardModeClassifier.classify(facts, supplementalData);

        assertEquals(DashboardModeClassifier.MODE_UNSUPPORTED_REIT, mode.mode());
    }

    @Test
    void classifiesBanksAsFinancialSector() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .build();

        MarketSupplementalData supplementalData = new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "JPMorgan Chase & Co.",
                "Financial Services",
                "Banks - Diversified",
                "EQUITY",
                null,
                null,
                null,
                null,
                java.util.List.of(),
                null,
                null);

        DashboardModeClassifier.DashboardMode mode = DashboardModeClassifier.classify(facts, supplementalData);

        assertEquals(DashboardModeClassifier.MODE_FINANCIAL, mode.mode());
    }

    @Test
    void keepsPaymentNetworksInStandardMode() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("V")
                .companyName("Visa Inc.")
                .build();

        MarketSupplementalData supplementalData = new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "Visa Inc.",
                "Financial Services",
                "Credit Services",
                "EQUITY",
                null,
                null,
                null,
                null,
                java.util.List.of(),
                null,
                null);

        DashboardModeClassifier.DashboardMode mode = DashboardModeClassifier.classify(facts, supplementalData);

        assertEquals(DashboardModeClassifier.MODE_STANDARD, mode.mode());
        assertNull(mode.message());
    }

    @Test
    void keepsFinancialInfrastructureEquitiesInStandardMode() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("SPGI")
                .companyName("S&P Global Inc.")
                .build();

        MarketSupplementalData supplementalData = new MarketSupplementalData(
                "yfinance",
                true,
                true,
                true,
                "S&P Global Inc.",
                "Financial Services",
                "Financial Data & Stock Exchanges",
                "EQUITY",
                null,
                null,
                null,
                null,
                java.util.List.of(),
                null,
                null);

        DashboardModeClassifier.DashboardMode mode = DashboardModeClassifier.classify(facts, supplementalData);

        assertEquals(DashboardModeClassifier.MODE_STANDARD, mode.mode());
        assertNull(mode.message());
    }
}
