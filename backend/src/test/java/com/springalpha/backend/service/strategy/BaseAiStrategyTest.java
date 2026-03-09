package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class BaseAiStrategyTest {

    private final ObjectMapper objectMapper = new ObjectMapper();
    private final TestStrategy strategy = new TestStrategy(
            new PromptTemplateService(objectMapper),
            new AnalysisReportValidator(),
            objectMapper);

    @Test
    void normalizeCoreThesisBuildsStructuredSummaryFromLegacyField() {
        AnalysisReport report = AnalysisReport.builder()
                .executiveSummary("Revenue improved meaningfully. Margin discipline remained solid.")
                .build();

        strategy.exposeNormalizeCoreThesis(report);

        assertNotNull(report.getCoreThesis());
        assertEquals("Revenue improved meaningfully.", report.getCoreThesis().getHeadline());
        assertEquals("Revenue improved meaningfully. Margin discipline remained solid.",
                report.getCoreThesis().getSummary());
        assertEquals("Revenue improved meaningfully. Margin discipline remained solid.", report.getExecutiveSummary());
    }

    @Test
    void parseJsonResponseLenientlyHandlesStructuredThesisArrayMismatch() throws JsonProcessingException {
        String response = """
                {
                  "coreThesis": {
                    "headline": "Margins improved with better mix",
                    "summary": "Higher-quality growth supported the quarter.",
                    "watchItems": "Monitor sustainability"
                  },
                  "keyMetrics": []
                }
                """;

        AnalysisReport report = strategy.exposeParseJsonResponse(response);
        strategy.exposeNormalizeCoreThesis(report);

        assertNotNull(report.getCoreThesis());
        assertNotNull(report.getCoreThesis().getWatchItems());
        assertTrue(report.getCoreThesis().getWatchItems().isEmpty());
        assertEquals("Higher-quality growth supported the quarter.", report.getExecutiveSummary());
    }

    @Test
    void validatorAcceptsStructuredCoreThesisWithoutLegacySummary() {
        AnalysisReport report = AnalysisReport.builder()
                .coreThesis(AnalysisReport.CoreThesis.builder()
                        .headline("Growth quality improved")
                        .summary("Growth quality improved as profitability expanded.")
                        .build())
                .keyMetrics(java.util.List.of(
                        AnalysisReport.MetricInsight.builder()
                                .metricName("Revenue")
                                .value("$1.00B")
                                .interpretation("Revenue remains stable.")
                                .sentiment("positive")
                                .build()))
                .build();

        FinancialFacts facts = FinancialFacts.builder()
                .revenue(new BigDecimal("1000000000"))
                .netIncome(new BigDecimal("250000000"))
                .revenueYoY(new BigDecimal("0.10"))
                .grossMargin(new BigDecimal("0.50"))
                .operatingMargin(new BigDecimal("0.20"))
                .netMargin(new BigDecimal("0.25"))
                .freeCashFlow(new BigDecimal("300000000"))
                .returnOnEquity(new BigDecimal("0.15"))
                .returnOnAssets(new BigDecimal("0.08"))
                .build();

        AnalysisReportValidator.ValidationResult result = new AnalysisReportValidator().validate(report, facts);
        assertTrue(result.isValid(), "Structured thesis should satisfy summary validation");
    }

    @Test
    void validatorDropsPlaceholderCitations() {
        AnalysisReport report = AnalysisReport.builder()
                .citations(List.of(
                        AnalysisReport.Citation.builder()
                                .section("source identifier")
                                .excerpt("No textual evidence available.")
                                .build(),
                        AnalysisReport.Citation.builder()
                                .section("MD&A")
                                .excerpt("Revenue increased due to higher deliveries.")
                                .build()))
                .build();

        AnalysisReportValidator validator = new AnalysisReportValidator();
        validator.validateCitations(report, "Revenue increased due to higher deliveries.");

        assertNotNull(report.getCitations());
        assertEquals(1, report.getCitations().size());
        assertEquals("VERIFIED", report.getCitations().get(0).getVerificationStatus());
    }

    @Test
    void promptServiceDoesNotInjectPlaceholderWhenEvidenceMissing() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("TSLA")
                .period("FY 2025")
                .financialFacts(FinancialFacts.builder().build())
                .textEvidence(Map.of())
                .evidenceAvailable(false)
                .evidenceStatusMessage("SEC retrieval failed.")
                .build();

        String prompt = new PromptTemplateService(objectMapper).buildSummaryPrompt(contract, "zh");
        assertFalse(prompt.contains("No textual evidence available."));
        assertTrue(prompt.contains("UNAVAILABLE"));
    }

    @Test
    void normalizeSentimentsMapsChineseValuesToCanonicalEnglish() {
        AnalysisReport report = AnalysisReport.builder()
                .keyMetrics(List.of(
                        AnalysisReport.MetricInsight.builder().metricName("营收").sentiment("负面").build(),
                        AnalysisReport.MetricInsight.builder().metricName("毛利率").sentiment("中性").build(),
                        AnalysisReport.MetricInsight.builder().metricName("净利润").sentiment("正面").build()))
                .build();

        strategy.exposeNormalizeSentiments(report);

        assertEquals("negative", report.getKeyMetrics().get(0).getSentiment());
        assertEquals("neutral", report.getKeyMetrics().get(1).getSentiment());
        assertEquals("positive", report.getKeyMetrics().get(2).getSentiment());
    }

    @Test
    void analyzeSetsDegradedSourceContextAndSuppressesCitationsWhenEvidenceUnavailable() {
        TestStrategy strategy = new TestStrategy(
                new PromptTemplateService(objectMapper),
                new AnalysisReportValidator(),
                objectMapper,
                """
                        {
                          "executiveSummary": "Revenue softened, but liquidity remained solid.",
                          "citations": [
                            {
                              "section": "MD&A",
                              "excerpt": "Revenue increased due to higher deliveries."
                            }
                          ]
                        }
                        """);

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("TSLA")
                .companyName("Tesla, Inc.")
                .period("FY 2025")
                .financialFacts(sampleFacts())
                .textEvidence(Map.of())
                .evidenceAvailable(false)
                .evidenceStatusMessage("SEC filing was available, but semantic grounding was not ready yet.")
                .build();

        List<AnalysisReport> reports = strategy.analyze(contract, "zh", null).collectList().block();

        assertNotNull(reports);
        AnalysisReport summaryReport = reports.get(0);
        assertNotNull(summaryReport.getSourceContext());
        assertEquals("DEGRADED", summaryReport.getSourceContext().getStatus());
        assertEquals("SEC filing was available, but semantic grounding was not ready yet.",
                summaryReport.getSourceContext().getMessage());
        assertNull(summaryReport.getCitations());
        assertEquals("Revenue softened, but liquidity remained solid.", summaryReport.getExecutiveSummary());
    }

    @Test
    void analyzePreservesExistingGroundedSourceContextFromModelOutput() {
        TestStrategy strategy = new TestStrategy(
                new PromptTemplateService(objectMapper),
                new AnalysisReportValidator(),
                objectMapper,
                """
                        {
                          "executiveSummary": "Growth quality improved with better margins.",
                          "sourceContext": {
                            "status": "GROUNDED",
                            "message": "Model already linked analysis to SEC excerpts."
                          }
                        }
                        """);

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("AAPL")
                .companyName("Apple Inc.")
                .period("FY 2025")
                .financialFacts(sampleFacts())
                .textEvidence(Map.of("MD&A", "Revenue increased due to higher deliveries."))
                .evidenceAvailable(false)
                .evidenceStatusMessage("Should not override existing source context")
                .build();

        AnalysisReport summaryReport = strategy.analyze(contract, "en", null).blockFirst();

        assertNotNull(summaryReport);
        assertNotNull(summaryReport.getSourceContext());
        assertEquals("GROUNDED", summaryReport.getSourceContext().getStatus());
        assertEquals("Model already linked analysis to SEC excerpts.", summaryReport.getSourceContext().getMessage());
    }

    @Test
    void normalizeCoreThesisBackfillsLegacySummaryFromHeadlineWhenSummaryMissing() {
        AnalysisReport report = AnalysisReport.builder()
                .coreThesis(AnalysisReport.CoreThesis.builder()
                        .headline("Margins stabilized after a difficult quarter")
                        .build())
                .build();

        strategy.exposeNormalizeCoreThesis(report);

        assertNotNull(report.getCoreThesis());
        assertEquals("Margins stabilized after a difficult quarter", report.getCoreThesis().getSummary());
        assertEquals("Margins stabilized after a difficult quarter", report.getExecutiveSummary());
    }

    @Test
    void normalizeCoreThesisCleansVerdictAndSupportingEvidence() {
        AnalysisReport report = AnalysisReport.builder()
                .coreThesis(AnalysisReport.CoreThesis.builder()
                        .verdict("bullish")
                        .headline("  Growth reaccelerated.  ")
                        .summary("  Higher-quality growth supported the quarter.  ")
                        .keyPoints(List.of("  Mix improved  ", " "))
                        .watchItems(new ArrayList<>(java.util.Arrays.asList("  Watch margins  ", null)))
                        .supportingEvidence(List.of(
                                AnalysisReport.SupportingEvidence.builder()
                                        .label(" ")
                                        .detail("  Deliveries improved  ")
                                        .build(),
                                AnalysisReport.SupportingEvidence.builder()
                                        .label(null)
                                        .detail(null)
                                        .build()))
                        .build())
                .build();

        strategy.exposeNormalizeCoreThesis(report);

        assertEquals("positive", report.getCoreThesis().getVerdict());
        assertEquals(List.of("Mix improved"), report.getCoreThesis().getKeyPoints());
        assertEquals(List.of("Watch margins"), report.getCoreThesis().getWatchItems());
        assertEquals(1, report.getCoreThesis().getSupportingEvidence().size());
        assertEquals("Evidence", report.getCoreThesis().getSupportingEvidence().get(0).getLabel());
        assertEquals("Deliveries improved", report.getCoreThesis().getSupportingEvidence().get(0).getDetail());
    }

    private FinancialFacts sampleFacts() {
        return FinancialFacts.builder()
                .ticker("TSLA")
                .companyName("Tesla, Inc.")
                .period("FY 2025")
                .filingDate("2026-01-29")
                .currency("USD")
                .revenue(new BigDecimal("1000000000"))
                .netIncome(new BigDecimal("250000000"))
                .revenueYoY(new BigDecimal("0.10"))
                .grossMargin(new BigDecimal("0.50"))
                .grossMarginChange(new BigDecimal("0.02"))
                .operatingMargin(new BigDecimal("0.20"))
                .netMargin(new BigDecimal("0.25"))
                .netMarginChange(new BigDecimal("0.01"))
                .freeCashFlow(new BigDecimal("300000000"))
                .returnOnEquity(new BigDecimal("0.15"))
                .returnOnAssets(new BigDecimal("0.08"))
                .build();
    }

    private static class TestStrategy extends BaseAiStrategy {

        private final String responseBody;

        protected TestStrategy(PromptTemplateService promptService, AnalysisReportValidator validator,
                ObjectMapper objectMapper) {
            this(promptService, validator, objectMapper, "{}");
        }

        protected TestStrategy(PromptTemplateService promptService, AnalysisReportValidator validator,
                ObjectMapper objectMapper, String responseBody) {
            super(promptService, validator, objectMapper);
            this.responseBody = responseBody;
        }

        @Override
        public String getName() {
            return "test";
        }

        @Override
        protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang, String apiKeyOverride) {
            return Flux.just(responseBody);
        }

        AnalysisReport exposeParseJsonResponse(String json) throws JsonProcessingException {
            return parseJsonResponse(json);
        }

        void exposeNormalizeCoreThesis(AnalysisReport report) {
            normalizeCoreThesis(report);
        }

        void exposeNormalizeSentiments(AnalysisReport report) {
            normalizeSentiments(report);
        }
    }
}
