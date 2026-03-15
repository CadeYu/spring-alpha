package com.springalpha.backend.service.signals;

import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.model.FinancialFacts;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class BusinessSignalExtractorTest {

    private final BusinessSignalExtractor extractor = new BusinessSignalExtractor();

    @Test
    void extractsBusinessSignalsFromOperatingAndRiskEvidence() {
        BusinessSignals signals = extractor.extract(
                "MSFT",
                "quarterly",
                sampleFacts(),
                Map.of(
                        "MD&A",
                        """
                                Azure revenue grew as enterprise demand for cloud and AI services remained strong, and Copilot adoption expanded across commercial customers.
                                Management continues to prioritize efficiency while investing in data center capacity to support AI workloads and platform commercialization.
                                """,
                        "Risk Factors",
                        """
                                We face intense competition in cloud infrastructure and productivity software, and regulatory scrutiny could pressure monetization and margins.
                                """));

        assertNotNull(signals);
        assertEquals("quarterly", signals.getReportType());
        assertFalse(signals.getSegmentPerformance().isEmpty());
        assertFalse(signals.getProductServiceUpdates().isEmpty());
        assertFalse(signals.getManagementFocus().isEmpty());
        assertFalse(signals.getStrategicMoves().isEmpty());
        assertFalse(signals.getRiskSignals().isEmpty());
        assertTrue(signals.getSegmentPerformance().stream()
                .anyMatch(item -> item.getSummary() != null && item.getSummary().contains("Azure revenue grew")));
        assertTrue(signals.getProductServiceUpdates().stream()
                .anyMatch(item -> item.getSummary() != null && item.getSummary().contains("Copilot adoption")));
        assertTrue(signals.getRiskSignals().stream()
                .anyMatch(item -> item.getSummary() != null && item.getSummary().contains("competition")));
        assertFalse(signals.getEvidenceRefs().isEmpty());
    }

    @Test
    void capturesAdPricingRecommendationAndInfrastructureThemes() {
        BusinessSignals signals = extractor.extract(
                "META",
                "quarterly",
                sampleFacts(),
                Map.of(
                        "MD&A",
                        """
                                Ad impressions and ad pricing improved across Family of Apps, while AI recommendation systems continued lifting engagement and Reels monetization.
                                Management continues investing in data center capacity and GPU infrastructure to support Meta AI and business messaging commercialization.
                                """));

        assertNotNull(signals);
        assertTrue(signals.getSegmentPerformance().stream()
                .anyMatch(item -> item.getSummary() != null
                        && (item.getSummary().contains("Ad impressions")
                                || item.getSummary().contains("ad pricing")
                                || item.getSummary().contains("Family of Apps"))));
        assertTrue(signals.getProductServiceUpdates().stream()
                .anyMatch(item -> item.getTitle() != null
                        && (item.getTitle().contains("Recommendation")
                                || item.getTitle().contains("Reels")
                                || item.getTitle().contains("Meta AI"))));
        assertTrue(signals.getCapexSignals().stream()
                .anyMatch(item -> item.getSummary() != null
                        && (item.getSummary().contains("data center capacity")
                                || item.getSummary().contains("GPU infrastructure"))));
    }

    @Test
    void fallsBackGracefullyWhenNarrativeEvidenceIsSparse() {
        BusinessSignals signals = extractor.extract("TSLA", "annual", sampleFacts(), Map.of());

        assertNotNull(signals);
        assertEquals("quarterly", signals.getReportType());
        assertTrue(signals.getSegmentPerformance() == null || signals.getSegmentPerformance().isEmpty());
        assertTrue(signals.getProductServiceUpdates() == null || signals.getProductServiceUpdates().isEmpty());
        assertFalse(signals.getManagementFocus().isEmpty());
        assertFalse(signals.getRiskSignals().isEmpty());
        assertTrue(signals.getManagementFocus().stream()
                .anyMatch(item -> item.getEvidenceSection() != null && item.getEvidenceSection().equals("Financial Facts")));
        assertTrue(signals.getManagementFocus().stream()
                .noneMatch(item -> item.getSummary() != null && item.getSummary().contains("Revenue growth of")));
        assertTrue(signals.getRiskSignals().stream()
                .noneMatch(item -> item.getSummary() != null && item.getSummary().contains("margin durability remains the key risk")));
    }

    @Test
    void ignoresInlineXbrlArtifactsWhenExtractingRiskSignals() {
        BusinessSignals signals = extractor.extract(
                "JPM",
                "quarterly",
                sampleFacts(),
                Map.of(
                        "Risk Factors",
                        """
                                srt:WeightedAverageMember jpm:MeasurementInputCorrelationofInterestRatestoForeignExchangeRates us-gaap:FairValueInputsLevel3Member us-gaap:ValuationTechniqueOptionPricingModelMember
                                Regulatory scrutiny and litigation exposure could pressure capital returns and profitability during periods of market stress.
                                """
                ));

        assertNotNull(signals);
        assertFalse(signals.getRiskSignals().isEmpty());
        assertTrue(signals.getRiskSignals().stream()
                .anyMatch(item -> item.getSummary() != null && item.getSummary().contains("Regulatory scrutiny")));
        assertTrue(signals.getRiskSignals().stream()
                .noneMatch(item -> item.getSummary() != null
                        && (item.getSummary().contains("us-gaap:")
                                || item.getSummary().contains("ValuationTechnique")
                                || item.getSummary().contains("WeightedAverageMember"))));
    }

    @Test
    void ignoresConcatenatedIxbrlArtifactsWithoutWhitespaceBoundaries() {
        BusinessSignals signals = extractor.extract(
                "JPM",
                "quarterly",
                sampleFacts(),
                Map.of(
                        "Risk Factors",
                        """
                                ricingModelMembersrt:WeightedAverageMemberjpm:MeasurementInputCorrelationofInterestRatestoForeignExchangeRatesMember2025-09-300000019617us-gaap:FairValueInputsLevel3Memberus-gaap:ValuationTechniqueOptionPricingModelMember
                                Regulatory scrutiny and litigation exposure could pressure capital returns and profitability during periods of market stress.
                                """
                ));

        assertNotNull(signals);
        assertFalse(signals.getRiskSignals().isEmpty());
        assertTrue(signals.getRiskSignals().stream()
                .anyMatch(item -> item.getSummary() != null && item.getSummary().contains("Regulatory scrutiny")));
        assertTrue(signals.getRiskSignals().stream()
                .noneMatch(item -> item.getSummary() != null
                        && (item.getSummary().contains("us-gaap:")
                                || item.getSummary().contains("MeasurementInput")
                                || item.getSummary().contains("ricingModelMembersrt"))));
    }

    private FinancialFacts sampleFacts() {
        return FinancialFacts.builder()
                .ticker("MSFT")
                .companyName("Microsoft Corporation")
                .period("Q2 2026")
                .filingDate("2026-01-31")
                .revenueYoY(new BigDecimal("0.08"))
                .operatingCashFlowYoY(new BigDecimal("0.12"))
                .netMargin(new BigDecimal("0.28"))
                .build();
    }
}
