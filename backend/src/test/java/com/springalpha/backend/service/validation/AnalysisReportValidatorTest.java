package com.springalpha.backend.service.validation;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.model.FinancialFacts;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class AnalysisReportValidatorTest {

    private final AnalysisReportValidator validator = new AnalysisReportValidator();

    @Test
    void validateRejectsMissingSummaryAndInvalidSentiment() {
        AnalysisReport report = AnalysisReport.builder()
                .keyMetrics(List.of(
                        AnalysisReport.MetricInsight.builder()
                                .metricName("Revenue")
                                .value("$1.2B")
                                .interpretation("Revenue was stable.")
                                .sentiment("mixed")
                                .build()))
                .build();

        AnalysisReportValidator.ValidationResult result = validator.validate(report, baselineFacts());

        assertFalse(result.isValid());
        assertTrue(result.getErrors().contains("coreThesis or executiveSummary is required"));
        assertTrue(result.getErrors().stream().anyMatch(error -> error.contains("Invalid sentiment")));
    }

    @Test
    void validateWarnsWhenMetricValueCannotBeTracedToFacts() {
        AnalysisReport report = AnalysisReport.builder()
                .executiveSummary("Revenue remained resilient.")
                .keyMetrics(List.of(
                        AnalysisReport.MetricInsight.builder()
                                .metricName("Revenue")
                                .value("$9.9B")
                                .interpretation("Revenue remained resilient.")
                                .sentiment("positive")
                                .build()))
                .build();

        AnalysisReportValidator.ValidationResult result = validator.validate(report, baselineFacts());

        assertTrue(result.isValid());
        assertTrue(result.getWarnings().stream()
                .anyMatch(warning -> warning.contains("possible hallucination")));
    }

    @Test
    void validateCitationsMarksMissingSourceAsUnverified() {
        AnalysisReport report = AnalysisReport.builder()
                .citations(List.of(
                        AnalysisReport.Citation.builder()
                                .section("MD&A")
                                .excerpt("Revenue grew because deliveries accelerated.")
                                .build()))
                .build();

        validator.validateCitations(report, "");

        assertEquals(1, report.getCitations().size());
        assertEquals("UNVERIFIED", report.getCitations().get(0).getVerificationStatus());
    }

    @Test
    void validateCitationsDropsEntriesThatAreNotVerbatimInSource() {
        AnalysisReport report = AnalysisReport.builder()
                .citations(List.of(
                        AnalysisReport.Citation.builder()
                                .section("MD&A")
                                .excerpt("Total net sales increased during 2025 compared to 2024 primarily due to higher net sales of Services, iPhone and Mac.")
                                .build(),
                        AnalysisReport.Citation.builder()
                                .section("MD&A")
                                .excerpt("Americas net sales increased during 2025 compared to 2024 primarily due to higher net sales of iPhone and Services.")
                                .build()))
                .build();

        validator.validateCitations(report,
                "Americas net sales increased during 2025 compared to 2024 primarily due to higher net sales of iPhone and Services.");

        assertEquals(1, report.getCitations().size());
        assertEquals("VERIFIED", report.getCitations().get(0).getVerificationStatus());
        assertEquals("Americas net sales increased during 2025 compared to 2024 primarily due to higher net sales of iPhone and Services.",
                report.getCitations().get(0).getExcerpt());
    }

    @Test
    void validateCitationsDeduplicatesVerifiedEntries() {
        AnalysisReport report = AnalysisReport.builder()
                .citations(List.of(
                        AnalysisReport.Citation.builder()
                                .section("MD&A")
                                .excerpt("Revenue increased due to stronger deliveries.")
                                .build(),
                        AnalysisReport.Citation.builder()
                                .section("Management Discussion")
                                .excerpt("Revenue increased due to stronger deliveries.")
                                .build()))
                .build();

        validator.validateCitations(report, "Revenue increased due to stronger deliveries.");

        assertEquals(1, report.getCitations().size());
        assertEquals("VERIFIED", report.getCitations().get(0).getVerificationStatus());
    }

    @Test
    void validateCitationsRemovesEntriesWithEmptyExcerpt() {
        AnalysisReport report = AnalysisReport.builder()
                .citations(List.of(
                        AnalysisReport.Citation.builder()
                                .section("MD&A")
                                .excerpt("   ")
                                .build(),
                        AnalysisReport.Citation.builder()
                                .section("MD&A")
                                .excerpt("Revenue increased due to stronger deliveries.")
                                .build()))
                .build();

        validator.validateCitations(report, "Revenue increased due to stronger deliveries.");

        assertEquals(1, report.getCitations().size());
        assertEquals("Revenue increased due to stronger deliveries.", report.getCitations().get(0).getExcerpt());
    }

    @Test
    void validateCitationsDropsLowSignalTableRows() {
        AnalysisReport report = AnalysisReport.builder()
                .citations(List.of(
                        AnalysisReport.Citation.builder()
                                .section("MD&A")
                                .excerpt("Total revenue / / 81,273 / / 69,632 /")
                                .build(),
                        AnalysisReport.Citation.builder()
                                .section("MD&A")
                                .excerpt("Revenue increased due to stronger deliveries.")
                                .build()))
                .build();

        validator.validateCitations(report,
                "Revenue increased due to stronger deliveries. Total revenue revenue table values are shown elsewhere.");

        assertEquals(1, report.getCitations().size());
        assertEquals("Revenue increased due to stronger deliveries.", report.getCitations().get(0).getExcerpt());
    }

    private FinancialFacts baselineFacts() {
        return FinancialFacts.builder()
                .revenue(new BigDecimal("1200000000"))
                .netIncome(new BigDecimal("250000000"))
                .revenueYoY(new BigDecimal("0.10"))
                .grossMargin(new BigDecimal("0.45"))
                .operatingMargin(new BigDecimal("0.18"))
                .netMargin(new BigDecimal("0.21"))
                .freeCashFlow(new BigDecimal("300000000"))
                .returnOnEquity(new BigDecimal("0.15"))
                .returnOnAssets(new BigDecimal("0.08"))
                .build();
    }
}
