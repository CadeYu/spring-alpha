package com.springalpha.backend.service.profile;

import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.contract.CompanyProfile;
import com.springalpha.backend.financial.model.FinancialFacts;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class CompanyProfileExtractorTest {

    private final CompanyProfileExtractor extractor = new CompanyProfileExtractor();

    @Test
    void extractBuildsStructuredProfileFromBusinessSummarySignalsAndEvidence() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("CRDO")
                .companyName("Credo Technology Group")
                .period("FY2026 Q3")
                .filingDate("2026-03-01")
                .marketBusinessSummary("Credo develops high-speed connectivity solutions including SerDes, active electrical cables (AEC), and optical DSP chips for cloud and hyperscale data center customers.")
                .build();

        BusinessSignals signals = BusinessSignals.builder()
                .productServiceUpdates(List.of(BusinessSignals.SignalItem.builder()
                        .title("AEC demand ramp")
                        .summary("AEC and optical DSP products continued to ramp with hyperscaler programs.")
                        .build()))
                .segmentPerformance(List.of(BusinessSignals.SignalItem.builder()
                        .title("Connectivity portfolio growth")
                        .summary("SerDes and retimer demand remained strong in AI data-center interconnect deployments.")
                        .build()))
                .build();

        CompanyProfile profile = extractor.extract(
                "CRDO",
                "quarterly",
                facts,
                signals,
                Map.of("MD&A", "Customers continued deploying SerDes and retimer connectivity solutions in AI data-center interconnect workloads."));

        assertNotNull(profile);
        assertFalse(profile.isEmpty());
        assertTrue(profile.getProductLines().contains("SerDes"));
        assertTrue(profile.getProductLines().contains("AEC"));
        assertTrue(profile.getProductLines().contains("Optical DSP"));
        assertTrue(profile.getCustomerTypes().contains("Cloud and data-center customers")
                || profile.getCustomerTypes().contains("Hyperscalers"));
        assertTrue(profile.getBusinessModelSummary().toLowerCase().contains("connectivity"));
    }

    @Test
    void extractFallsBackToGenericFinancialKpisWhenCompanySpecificOnesAreAbsent() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("AAPL")
                .companyName("Apple Inc.")
                .period("Q1 2026")
                .filingDate("2026-01-31")
                .revenue(java.math.BigDecimal.TEN)
                .grossMargin(java.math.BigDecimal.ONE)
                .netMargin(java.math.BigDecimal.ONE)
                .freeCashFlow(java.math.BigDecimal.ONE)
                .build();

        CompanyProfile profile = extractor.extract("AAPL", "quarterly", facts, BusinessSignals.builder().build(), Map.of());

        assertNotNull(profile);
        assertTrue(profile.getKeyKpis().contains("Revenue"));
        assertTrue(profile.getKeyKpis().contains("Gross Margin"));
        assertTrue(profile.getKeyKpis().contains("Net Margin"));
        assertTrue(profile.getKeyKpis().contains("Free Cash Flow"));
    }

    @Test
    void extractDoesNotMisclassifyGenericConnectivityAsAiDatacenterInterconnect() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("TSLA")
                .companyName("Tesla, Inc.")
                .period("Q3 2026")
                .filingDate("2026-03-01")
                .marketBusinessSummary("Tesla designs and manufactures electric vehicles, battery energy storage systems, and related software and services for consumers.")
                .build();

        CompanyProfile profile = extractor.extract(
                "TSLA",
                "quarterly",
                facts,
                BusinessSignals.builder().build(),
                Map.of("MD&A", "The company continues improving vehicle software, service, and charging connectivity for customers."));

        assertNotNull(profile);
        assertTrue(profile.getProductLines() == null || !profile.getProductLines().contains("AI data-center connectivity"));
        assertTrue(profile.getBusinessModelSummary().toLowerCase().contains("electric vehicles"));
    }

    @Test
    void extractCapturesPrimaryConsumerHardwareLinesBeforeAncillaryServiceTerms() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("AAPL")
                .companyName("Apple Inc.")
                .period("Q1 2026")
                .filingDate("2026-01-31")
                .marketBusinessSummary(
                        "Apple designs, manufactures, and markets smartphones, personal computers, tablets, wearables and accessories, and sells related services. The company also offers subscriptions, advertising, and credit card services to consumers and enterprise customers.")
                .build();

        CompanyProfile profile = extractor.extract("AAPL", "quarterly", facts, BusinessSignals.builder().build(), Map.of());

        assertNotNull(profile);
        assertTrue(profile.getProductLines().contains("Smartphones"));
        assertTrue(profile.getProductLines().contains("Personal computers"));
        assertTrue(profile.getProductLines().contains("Tablets"));
        assertTrue(profile.getBusinessModelSummary().toLowerCase().contains("smartphones"));
    }
}
