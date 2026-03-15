package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.contract.CompanyProfile;
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
                    "whatChanged": "Demand improved",
                    "drivers": "Pricing and mix",
                    "strategicBets": "AI infrastructure",
                    "watchItems": "Monitor sustainability"
                  },
                  "keyMetrics": []
                }
                """;

        AnalysisReport report = strategy.exposeParseJsonResponse(response);
        strategy.exposeNormalizeCoreThesis(report);

        assertNotNull(report.getCoreThesis());
        assertNotNull(report.getCoreThesis().getWhatChanged());
        assertTrue(report.getCoreThesis().getWhatChanged().isEmpty());
        assertNotNull(report.getCoreThesis().getDrivers());
        assertTrue(report.getCoreThesis().getDrivers().isEmpty());
        assertNotNull(report.getCoreThesis().getStrategicBets());
        assertTrue(report.getCoreThesis().getStrategicBets().isEmpty());
        assertNotNull(report.getCoreThesis().getWatchItems());
        assertTrue(report.getCoreThesis().getWatchItems().isEmpty());
        assertEquals("Higher-quality growth supported the quarter.", report.getExecutiveSummary());
    }

    @Test
    void parseJsonResponseUnwrapsAnalysisReportRoot() throws JsonProcessingException {
        String response = """
                {
                  "analysisReport": {
                    "executiveSummary": "Wrapped response from the model.",
                    "keyMetrics": []
                  }
                }
                """;

        AnalysisReport report = strategy.exposeParseJsonResponse(response);

        assertEquals("Wrapped response from the model.", report.getExecutiveSummary());
    }

    @Test
    void parseJsonResponseAcceptsMarkdownFencedJson() throws JsonProcessingException {
        String response = """
                ```json
                {
                  "executiveSummary": "Fenced JSON response.",
                  "keyMetrics": []
                }
                ```
                """;

        AnalysisReport report = strategy.exposeParseJsonResponse(response);

        assertEquals("Fenced JSON response.", report.getExecutiveSummary());
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
    void promptServiceRequiresVerbatimCitationExcerpts() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("AAPL")
                .period("FY 2025")
                .financialFacts(FinancialFacts.builder().build())
                .textEvidence(Map.of("MD&A", "Americas net sales increased during 2025 compared to 2024 primarily due to higher net sales of iPhone and Services."))
                .evidenceAvailable(true)
                .build();

        PromptTemplateService promptService = new PromptTemplateService(objectMapper);

        assertTrue(promptService.buildSummaryPrompt(contract, "zh")
                .contains("MUST be copied verbatim from TEXTUAL EVIDENCE"));
        assertTrue(promptService.buildInsightsPrompt(contract, "zh")
                .contains("MUST be copied verbatim from TEXTUAL EVIDENCE"));
        assertTrue(promptService.buildFactorsPrompt(contract, "zh")
                .contains("MUST be copied verbatim from TEXTUAL EVIDENCE"));
        assertTrue(promptService.buildDriversPrompt(contract, "zh")
                .contains("MUST be copied verbatim from TEXTUAL EVIDENCE"));
    }

    @Test
    void summaryPromptIncludesBusinessSignalsAndBusinessFirstGuidance() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("MSFT")
                .period("Q2 2026")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .companyProfile(CompanyProfile.builder()
                        .businessModelSummary("Provides SerDes, AEC, and optical DSP connectivity solutions for cloud and hyperscale customers.")
                        .productLines(List.of("SerDes", "AEC", "Optical DSP"))
                        .customerTypes(List.of("Cloud and data-center customers"))
                        .keyKpis(List.of("Revenue", "Gross Margin"))
                        .build())
                .businessSignals(BusinessSignals.builder()
                        .segmentPerformance(List.of(BusinessSignals.SignalItem.builder()
                                .title("Azure / cloud momentum")
                                .summary("Azure revenue grew as AI demand remained strong.")
                                .evidenceSection("MD&A")
                                .build()))
                        .build())
                .textEvidence(Map.of("MD&A", "Azure revenue grew as AI demand remained strong."))
                .evidenceAvailable(true)
                .build();

        String prompt = new PromptTemplateService(objectMapper).buildSummaryPrompt(contract, "en");

        assertTrue(prompt.contains("BUSINESS SIGNALS:"));
        assertTrue(prompt.contains("COMPANY PROFILE:"));
        assertTrue(prompt.contains("SerDes"));
        assertTrue(prompt.contains("Azure / cloud momentum"));
        assertTrue(prompt.contains("Do NOT turn the summary into a simple restatement of revenue, margin, and net income."));
        assertTrue(prompt.contains("Avoid vague wording such as \"strong demand\""));
    }

    @Test
    void driversAndFactorsPromptsIncludeCompanyProfileContext() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("HOOD")
                .period("Q4 2025")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .companyProfile(CompanyProfile.builder()
                        .businessModelSummary("Provides brokerage, Gold subscription, and derivatives products for retail users.")
                        .productLines(List.of("Gold subscription", "Event contracts", "Index options"))
                        .customerTypes(List.of("Consumers / retail users"))
                        .keyKpis(List.of("Gold Subscribers", "Net Deposits", "Platform Assets"))
                        .build())
                .textEvidence(Map.of("MD&A", "Gold subscribers grew and new products expanded engagement."))
                .evidenceAvailable(true)
                .build();

        PromptTemplateService promptService = new PromptTemplateService(objectMapper);
        String driversPrompt = promptService.buildDriversPrompt(contract, "zh");
        String factorsPrompt = promptService.buildFactorsPrompt(contract, "zh");

        assertTrue(driversPrompt.contains("COMPANY PROFILE:"));
        assertTrue(driversPrompt.contains("Gold subscription"));
        assertTrue(factorsPrompt.contains("COMPANY PROFILE:"));
        assertTrue(factorsPrompt.contains("Platform Assets"));
    }

    @Test
    void buildInsightsPromptCapsEvidenceToReduceQuarterlyPromptTruncation() {
        String longEvidence = "Demand remained strong across products. ".repeat(500);
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("AAPL")
                .period("Q1 2025")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .textEvidence(Map.of(
                        "MD&A", longEvidence,
                        "Risk Factors", longEvidence))
                .evidenceAvailable(true)
                .build();

        String prompt = new PromptTemplateService(objectMapper).buildInsightsPrompt(contract, "zh");

        assertTrue(prompt.contains("[truncated for prompt budget]"));
        assertTrue(prompt.length() < 9000, "Insights prompt should be materially smaller than the full evidence blob");
    }

    @Test
    void groqSpecificPromptsUseSmallerEvidenceBudgetsThanDefaultPrompts() {
        String longEvidence = "Demand remained strong across products. ".repeat(700);
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("MSFT")
                .period("Q2 2026")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .textEvidence(Map.of(
                        "MD&A", longEvidence,
                        "Risk Factors", longEvidence,
                        "Business", longEvidence))
                .evidenceAvailable(true)
                .build();

        PromptTemplateService promptService = new PromptTemplateService(objectMapper);

        String defaultSummary = promptService.buildSummaryPrompt(contract, "en");
        String groqSummary = promptService.buildGroqSummaryPrompt(contract, "en");
        String defaultInsights = promptService.buildInsightsPrompt(contract, "en");
        String groqInsights = promptService.buildGroqInsightsPrompt(contract, "en");

        assertTrue(groqSummary.length() < defaultSummary.length(),
                "Groq summary prompt should be smaller than the default summary prompt");
        assertTrue(groqInsights.length() < defaultInsights.length(),
                "Groq insights prompt should be smaller than the default insights prompt");
        assertTrue(groqInsights.contains("[truncated for prompt budget]"));
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
        assertNotNull(summaryReport.getExecutiveSummary());
        assertTrue(summaryReport.getExecutiveSummary().contains("营收"));
    }

    @Test
    void parseAndValidateAttachesBusinessSignalsFromContract() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("MSFT")
                .companyName("Microsoft Corporation")
                .period("Q2 2026")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .companyProfile(CompanyProfile.builder()
                        .businessModelSummary("Provides cloud software and enterprise infrastructure services.")
                        .productLines(List.of("Azure"))
                        .customerTypes(List.of("Enterprise customers"))
                        .build())
                .businessSignals(BusinessSignals.builder()
                        .segmentPerformance(List.of(BusinessSignals.SignalItem.builder()
                                .title("Azure / cloud momentum")
                                .summary("Azure revenue grew as AI demand remained strong.")
                                .build()))
                        .build())
                .textEvidence(Map.of("MD&A", "Azure revenue grew as AI demand remained strong."))
                .evidenceAvailable(true)
                .build();

        AnalysisReport report = strategy.exposeParseAndValidate("""
                {
                  "coreThesis": {
                    "headline": "Cloud demand stayed resilient",
                    "summary": "Enterprise AI workloads continued to support demand."
                  },
                  "keyMetrics": []
                }
                """, contract, "en", "SummaryAgent").block();

        assertNotNull(report);
        assertNotNull(report.getBusinessSignals());
        assertFalse(report.getBusinessSignals().getSegmentPerformance().isEmpty());
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
        assertEquals("LIMITED", summaryReport.getSourceContext().getStatus());
        assertTrue(summaryReport.getSourceContext().getMessage().contains("display-ready high-confidence verbatim quote"));
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
    void parseAndValidateBuildsInsightsFallbackWhenQuarterlyAgentJsonIsMalformed() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("AAPL")
                .companyName("Apple Inc.")
                .period("Q1 2025")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .textEvidence(Map.of("MD&A", "Revenue growth remained strong during the reported quarter."))
                .evidenceAvailable(true)
                .build();

        String malformedInsights = """
                {
                  "dupontAnalysis": {
                    "netProfitMargin": "0.2928",
                    "assetTurnover": "0.3780",
                    "equityMultiplier": "4.2876",
                    "returnOnEquity": "0.4773",
                    "interpretation": "bad json"
                  },
                  "insightEngine": {
                    "accountingChanges": [],
                    "rootCauseAnalysis": [
                      {
                        "metric": "Gross Margin",
                        "reason": "missing comma here"
                        "evidence": "broken"
                      }
                    ]
                  }
                }
                """;

        AnalysisReport report = strategy.exposeParseAndValidate(malformedInsights, contract, "zh", "InsightsAgent")
                .block();

        assertNotNull(report);
        assertNotNull(report.getDupontAnalysis());
        assertNotNull(report.getInsightEngine());
        assertNotNull(report.getInsightEngine().getRootCauseAnalysis());
        assertFalse(report.getInsightEngine().getRootCauseAnalysis().isEmpty());
        assertNotEquals("N/A", report.getDupontAnalysis().getNetProfitMargin());
        assertTrue(report.getInsightEngine().getRootCauseAnalysis().stream()
                .anyMatch(item -> item.getMetric() != null && !item.getMetric().isBlank()));
    }

    @Test
    void buildFallbackReportProvidesFactorAndDriverContent() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("AAPL")
                .companyName("Apple Inc.")
                .period("Q1 2026")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .companyProfile(CompanyProfile.builder()
                        .businessModelSummary("Provides iPhone, Mac, and Services to consumer and enterprise customers.")
                        .productLines(List.of("iPhone", "Services"))
                        .customerTypes(List.of("Consumers"))
                        .keyKpis(List.of("Revenue", "Gross Margin"))
                        .build())
                .build();

        AnalysisReport factorsReport = strategy.exposeBuildFallbackReportForAgent("FactorsAgent", contract, "en");
        AnalysisReport driversReport = strategy.exposeBuildFallbackReportForAgent("DriversAgent", contract, "en");

        assertNotNull(factorsReport.getFactorAnalysis());
        assertNotNull(factorsReport.getFactorAnalysis().getRevenueBridge());
        assertFalse(factorsReport.getFactorAnalysis().getRevenueBridge().isEmpty());
        assertNotNull(factorsReport.getTopicTrends());
        assertFalse(factorsReport.getTopicTrends().isEmpty());
        assertNotNull(driversReport.getBusinessDrivers());
        assertFalse(driversReport.getBusinessDrivers().isEmpty());
        assertNotNull(driversReport.getRiskFactors());
        assertNotNull(driversReport.getBullCase());
        assertNotNull(driversReport.getBearCase());
    }

    @Test
    void driversFallbackUsesCompanyProfileToAvoidGenericStrategicLanguage() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("CRDO")
                .companyName("Credo Technology Group")
                .period("FY2026 Q3")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .companyProfile(CompanyProfile.builder()
                        .businessModelSummary("Provides SerDes, AEC, and optical DSP connectivity solutions for cloud and data-center customers.")
                        .productLines(List.of("SerDes", "AEC", "Optical DSP"))
                        .customerTypes(List.of("Cloud and data-center customers"))
                        .keyKpis(List.of("Revenue", "Gross Margin"))
                        .build())
                .build();

        AnalysisReport report = strategy.exposeBuildFallbackReportForAgent("DriversAgent", contract, "zh");

        assertNotNull(report.getBusinessDrivers());
        assertTrue(report.getBusinessDrivers().stream()
                .anyMatch(item -> item.getDescription().contains("SerDes")
                        || item.getDescription().contains("AEC")
                        || item.getDescription().contains("Optical DSP")));
    }

    @Test
    void summaryFallbackDoesNotRepeatCompanyNameAsBusinessIdentityOrDuplicateRevenueAnchor() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("TSLA")
                .companyName("Tesla, Inc.")
                .period("Q3 2026")
                .reportType("quarterly")
                .financialFacts(FinancialFacts.builder()
                        .ticker("TSLA")
                        .companyName("Tesla, Inc.")
                        .period("Q3 2026")
                        .currency("USD")
                        .revenue(new BigDecimal("28095000000"))
                        .revenueYoY(new BigDecimal("0.1157"))
                        .netIncome(new BigDecimal("1200000000"))
                        .netMargin(new BigDecimal("0.0427"))
                        .build())
                .companyProfile(CompanyProfile.builder()
                        .businessModelSummary("Tesla, Inc.")
                        .build())
                .evidenceAvailable(false)
                .build();

        AnalysisReport report = strategy.exposeParseAndValidate("""
                {
                  "coreThesis": {
                    "headline": "特斯拉第三季度财报显示利润和利润率显著下降",
                    "summary": "核心业务主线仍在延续，本季营收为280.95亿美元，同比增长11.57%。"
                  },
                  "keyMetrics": []
                }
                """, contract, "zh", "SummaryAgent").block();

        assertNotNull(report);
        assertNotNull(report.getCoreThesis());
        assertNotNull(report.getCoreThesis().getSummary());
        assertFalse(report.getCoreThesis().getSummary().contains("是一家Tesla"));
        assertEquals(1, report.getCoreThesis().getSummary().split("本季营收为", -1).length - 1);
    }

    @Test
    void driversFallbackMapsBusinessRiskSignalsIntoDisplayableRiskFactors() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .period("FY2025 Q3")
                .currency("USD")
                .revenue(new BigDecimal("46430000000"))
                .netIncome(new BigDecimal("14393000000"))
                .netMargin(new BigDecimal("0.31"))
                .operatingCashFlow(new BigDecimal("-45214000000"))
                .build();

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .period("FY2025 Q3")
                .reportType("quarterly")
                .financialFacts(facts)
                .businessSignals(BusinessSignals.builder()
                        .riskSignals(List.of(
                                BusinessSignals.SignalItem.builder()
                                        .title("Regulatory overhang")
                                        .summary("Regulatory scrutiny and litigation exposure could pressure capital returns and profitability.")
                                        .evidenceSection("Risk Factors")
                                        .build(),
                                BusinessSignals.SignalItem.builder()
                                        .title("Funding and liquidity")
                                        .summary("Funding markets and deposit trends may remain volatile during periods of macro stress.")
                                        .evidenceSection("Risk Factors")
                                        .build()))
                        .build())
                .build();

        AnalysisReport report = strategy.exposeBuildFallbackReportForAgent("DriversAgent", contract, "zh");

        assertNotNull(report);
        assertNotNull(report.getRiskFactors());
        assertEquals(2, report.getRiskFactors().size());
        assertEquals("监管与合规", report.getRiskFactors().get(0).getCategory());
        assertTrue(report.getRiskFactors().get(0).getDescription().startsWith("SEC 风险披露提到："));
        assertEquals("高", normalizeSeverityForAssertion(report.getRiskFactors().get(0).getSeverity(), true));
        assertEquals("流动性与市场敏感性", report.getRiskFactors().get(1).getCategory());
    }

    @Test
    void zhFallbackRiskFactorsTranslateKnownEnglishFallbackNarrative() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .period("FY2025 Q3")
                .netMargin(new BigDecimal("0.31"))
                .build();

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("JPM")
                .companyName("JPMorgan Chase & Co.")
                .period("FY2025 Q3")
                .reportType("quarterly")
                .financialFacts(facts)
                .businessSignals(BusinessSignals.builder()
                        .riskSignals(List.of(
                                BusinessSignals.SignalItem.builder()
                                        .title("投入兑现仍需验证")
                                        .summary("When narrative evidence is sparse, the next question is whether management can keep funding its priorities without letting margins or demand momentum slip.")
                                        .evidenceSection("Risk Factors")
                                        .build()))
                        .build())
                .build();

        AnalysisReport report = strategy.exposeBuildFallbackReportForAgent("DriversAgent", contract, "zh");

        assertNotNull(report.getRiskFactors());
        assertEquals(1, report.getRiskFactors().size());
        assertFalse(report.getRiskFactors().get(0).getDescription().contains("When narrative evidence is sparse"));
        assertTrue(report.getRiskFactors().get(0).getDescription().contains("持续投入核心优先事项"));
    }

    @Test
    void zhFallbackRiskFactorsDoNotExposeRawEnglishRiskTitles() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("TSLA")
                .companyName("Tesla, Inc.")
                .period("Q3 2026")
                .reportType("quarterly")
                .financialFacts(FinancialFacts.builder()
                        .ticker("TSLA")
                        .companyName("Tesla, Inc.")
                        .period("Q3 2026")
                        .build())
                .businessSignals(BusinessSignals.builder()
                        .riskSignals(List.of(
                                BusinessSignals.SignalItem.builder()
                                        .title("Service mix shift")
                                        .summary("Revenue Recognition Revenue by source The following table disaggregates our revenue by major source.")
                                        .evidenceSection("Risk Factors")
                                        .build()))
                        .build())
                .build();

        AnalysisReport report = strategy.exposeBuildFallbackReportForAgent("DriversAgent", contract, "zh");

        assertNotNull(report.getRiskFactors());
        assertEquals(1, report.getRiskFactors().size());
        assertEquals("产品结构与收入质量", report.getRiskFactors().get(0).getCategory());
        assertFalse(report.getRiskFactors().get(0).getDescription().contains("Revenue Recognition"));
        assertTrue(report.getRiskFactors().get(0).getDescription().contains("收入结构"));
    }

    @Test
    void zhFallbackRiskFactorsSummarizeLongEnglishOperationalSnippet() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("TSLA")
                .companyName("Tesla, Inc.")
                .period("Q3 2026")
                .reportType("quarterly")
                .financialFacts(FinancialFacts.builder()
                        .ticker("TSLA")
                        .companyName("Tesla, Inc.")
                        .period("Q3 2026")
                        .build())
                .businessSignals(BusinessSignals.builder()
                        .riskSignals(List.of(
                                BusinessSignals.SignalItem.builder()
                                        .title("Risk and competition signals")
                                        .summary("government incentives and tariffs may impact the transaction price or our ability to execute these existing contracts.")
                                        .evidenceSection("Risk Factors")
                                        .build()))
                        .build())
                .build();

        AnalysisReport report = strategy.exposeBuildFallbackReportForAgent("DriversAgent", contract, "zh");

        assertNotNull(report.getRiskFactors());
        assertEquals(1, report.getRiskFactors().size());
        assertEquals("政策与外部环境", report.getRiskFactors().get(0).getCategory());
        assertFalse(report.getRiskFactors().get(0).getDescription().contains("government incentives"));
        assertTrue(report.getRiskFactors().get(0).getDescription().contains("关税"));
    }

    @Test
    void parseAndValidatePreservesGroundedStateWithExplanationWhenAllCitationsAreDropped() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("MSFT")
                .companyName("Microsoft Corporation")
                .period("Q2 2026")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .textEvidence(Map.of("MD&A", "Revenue increased due to cloud demand and higher enterprise usage."))
                .evidenceAvailable(true)
                .build();

        String response = """
                {
                  "coreThesis": {
                    "verdict": "positive",
                    "headline": "Microsoft delivered resilient quarterly growth",
                    "summary": "Revenue growth remained healthy."
                  },
                  "citations": [
                    {
                      "section": "MD&A",
                      "excerpt": "Total revenue | | 81,273 | | 69,632 |"
                    }
                  ]
                }
                """;

        AnalysisReport report = strategy.exposeParseAndValidate(response, contract, "en", "SummaryAgent").block();

        assertNotNull(report);
        assertNull(report.getCitations());
        assertNotNull(report.getSourceContext());
        assertEquals("LIMITED", report.getSourceContext().getStatus());
        assertTrue(report.getSourceContext().getMessage().contains("display-ready high-confidence verbatim quote"));
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

    @Test
    void normalizeCoreThesisBackfillsLegacyFieldsFromFourQuestionStructure() {
        AnalysisReport report = AnalysisReport.builder()
                .coreThesis(AnalysisReport.CoreThesis.builder()
                        .headline("Advertising efficiency kept improving")
                        .summary("Recommendation quality and new monetization surfaces kept expanding.")
                        .whatChanged(List.of("Recommendation quality kept lifting engagement."))
                        .drivers(List.of(AnalysisReport.SupportingEvidence.builder()
                                .label("Ad pricing")
                                .detail("Pricing and conversion remained healthy across ad surfaces.")
                                .build()))
                        .strategicBets(List.of(AnalysisReport.SupportingEvidence.builder()
                                .label("AI infrastructure")
                                .detail("Management is still scaling compute to support future monetization.")
                                .build()))
                        .build())
                .build();

        strategy.exposeNormalizeCoreThesis(report);

        assertEquals(List.of("Recommendation quality kept lifting engagement."),
                report.getCoreThesis().getKeyPoints());
        assertNotNull(report.getCoreThesis().getSupportingEvidence());
        assertEquals(2, report.getCoreThesis().getSupportingEvidence().size());
        assertEquals("Ad pricing", report.getCoreThesis().getSupportingEvidence().get(0).getLabel());
        assertEquals("AI infrastructure", report.getCoreThesis().getSupportingEvidence().get(1).getLabel());
    }

    @Test
    void parseAndValidateRebuildsMetricHeavySummaryIntoBusinessFirstStructure() {
        AnalysisContract contract = AnalysisContract.builder()
                .ticker("META")
                .companyName("Meta Platforms, Inc.")
                .period("Q4 2025")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .businessSignals(BusinessSignals.builder()
                        .segmentPerformance(List.of(BusinessSignals.SignalItem.builder()
                                .title("Advertising engine")
                                .summary("Ad pricing and impressions improved across Family of Apps and Reels surfaces.")
                                .build()))
                        .productServiceUpdates(List.of(BusinessSignals.SignalItem.builder()
                                .title("Recommendation efficiency")
                                .summary("AI recommendation systems kept improving engagement and conversion quality.")
                                .build()))
                        .strategicMoves(List.of(BusinessSignals.SignalItem.builder()
                                .title("Meta AI commercialization")
                                .summary("Management is expanding Meta AI and business messaging monetization.")
                                .build()))
                        .riskSignals(List.of(BusinessSignals.SignalItem.builder()
                                .title("Infrastructure buildout")
                                .summary("Investors still need to watch whether AI investment scales faster than monetization.")
                                .build()))
                        .build())
                .textEvidence(Map.of("MD&A", "Ad pricing and impressions improved across Family of Apps and Reels surfaces."))
                .evidenceAvailable(true)
                .build();

        AnalysisReport report = strategy.exposeParseAndValidate("""
                {
                  "coreThesis": {
                    "verdict": "positive",
                    "headline": "Revenue increased 10% and net income improved",
                    "summary": "Revenue grew 10%, gross margin improved, and net income increased again.",
                    "whatChanged": [
                      "Revenue rose 10% year over year."
                    ],
                    "watchItems": [
                      "Watch revenue, gross margin, and net income next quarter."
                    ]
                  },
                  "keyMetrics": []
                }
                """, contract, "en", "SummaryAgent").block();

        assertNotNull(report);
        assertNotNull(report.getCoreThesis());
        assertTrue(report.getCoreThesis().getHeadline().toLowerCase().contains("advertising")
                || report.getCoreThesis().getHeadline().toLowerCase().contains("ai"));
        assertNotNull(report.getCoreThesis().getWhatChanged());
        assertFalse(report.getCoreThesis().getWhatChanged().isEmpty());
        assertTrue(report.getCoreThesis().getWhatChanged().stream()
                .anyMatch(item -> item.toLowerCase().contains("advertising")
                        || item.toLowerCase().contains("recommendation")
                        || item.toLowerCase().contains("engagement")));
        assertNotNull(report.getCoreThesis().getStrategicBets());
        assertFalse(report.getCoreThesis().getStrategicBets().isEmpty());
        assertNotNull(report.getCoreThesis().getWatchItems());
        assertTrue(report.getCoreThesis().getWatchItems().stream()
                .noneMatch(item -> item.toLowerCase().contains("gross margin")
                        || item.toLowerCase().contains("net income")));
    }

    @Test
    void parseAndValidateAddsExactNumbersToGenericBusinessStatements() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("META")
                .companyName("Meta Platforms, Inc.")
                .period("Q4 2025")
                .filingDate("2026-02-04")
                .currency("USD")
                .revenue(new BigDecimal("59894000000"))
                .revenueYoY(new BigDecimal("0.1688"))
                .grossMargin(new BigDecimal("0.8179"))
                .operatingIncome(new BigDecimal("24745000000"))
                .operatingMargin(new BigDecimal("0.4131"))
                .netIncome(new BigDecimal("22768000000"))
                .netMargin(new BigDecimal("0.3801"))
                .freeCashFlow(new BigDecimal("15230000000"))
                .freeCashFlowYoY(new BigDecimal("0.3278"))
                .operatingCashFlow(new BigDecimal("26480000000"))
                .build();

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("META")
                .companyName("Meta Platforms, Inc.")
                .period("Q4 2025")
                .reportType("quarterly")
                .financialFacts(facts)
                .businessSignals(BusinessSignals.builder()
                        .segmentPerformance(List.of(BusinessSignals.SignalItem.builder()
                                .title("Advertising engine")
                                .summary("广告收入达到1961.75亿美元，同比增长22.08%，Family of Apps 继续贡献主要增量。")
                                .build()))
                        .strategicMoves(List.of(BusinessSignals.SignalItem.builder()
                                .title("Infrastructure buildout")
                                .summary("基础设施投资继续提升，以支持AI模型训练与推理。")
                                .build()))
                        .build())
                .textEvidence(Map.of("MD&A", "广告收入达到1961.75亿美元，同比增长22.08%，Family of Apps 继续贡献主要增量。"))
                .evidenceAvailable(true)
                .build();

        AnalysisReport report = strategy.exposeParseAndValidate("""
                {
                  "coreThesis": {
                    "verdict": "positive",
                    "headline": "Meta在Q4 2025实现显著收入增长，展现出强劲的盈利能力",
                    "summary": "本期最值得关注的不是单一财务指标，而是核心业务执行继续主导业务表现。背后的关键驱动在于核心业务执行，而公司同时仍在围绕算力与基础设施投入推进投入与商业化，这会决定下一阶段增长质量和市场叙事能否延续。",
                    "whatChanged": [
                      "广告业务需求强劲，推动收入增长。",
                      "有效的成本控制使得运营利润和净利润显著提升。",
                      "尽管毛利率略有下降，但整体盈利能力依然强劲。",
                      "现金流管理策略为未来投资提供了良好基础。"
                    ],
                    "drivers": [
                      {
                        "label": "广告需求",
                        "detail": "Meta的广告业务继续表现强劲，推动了收入的显著增长。"
                      }
                    ],
                    "watchItems": [
                      "监测未来几个季度的现金流表现，以评估其财务健康状况。"
                    ]
                  },
                  "keyMetrics": []
                }
                """, contract, "zh", "SummaryAgent").block();

        assertNotNull(report);
        assertNotNull(report.getCoreThesis());
        assertTrue(report.getCoreThesis().getSummary().contains("598.94亿美元")
                || report.getCoreThesis().getSummary().contains("1961.75亿美元"));
        assertTrue(report.getCoreThesis().getSummary().contains("16.88%")
                || report.getCoreThesis().getSummary().contains("22.08%"));
        assertTrue(report.getCoreThesis().getWhatChanged().get(0).contains("1961.75亿美元"));
        assertTrue(report.getCoreThesis().getWhatChanged().get(0).contains("22.08%"));
        assertTrue(report.getCoreThesis().getWhatChanged().get(1).contains("247.45亿美元"));
        assertTrue(report.getCoreThesis().getWhatChanged().get(1).contains("227.68亿美元"));
        assertTrue(report.getCoreThesis().getWhatChanged().get(2).contains("81.79%"));
        assertTrue(report.getCoreThesis().getWhatChanged().get(3).contains("32.78%"));
        assertTrue(report.getCoreThesis().getDrivers().get(0).getDetail().contains("1961.75亿美元"));
        assertTrue(report.getCoreThesis().getWatchItems().get(0).contains("32.78%"));
    }

    @Test
    void parseAndValidateFallbackSummaryNamesCompanyBusinessInsteadOfGenericCoreBusinessLine() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("CRDO")
                .companyName("Credo Technology")
                .period("FY2026 Q3")
                .currency("USD")
                .marketSector("Technology")
                .marketIndustry("Semiconductors")
                .revenue(new BigDecimal("407000000"))
                .revenueYoY(new BigDecimal("2.0149"))
                .freeCashFlow(new BigDecimal("140000000"))
                .freeCashFlowYoY(new BigDecimal("365.7598"))
                .build();

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("CRDO")
                .companyName("Credo Technology")
                .period("FY2026 Q3")
                .reportType("quarterly")
                .financialFacts(facts)
                .businessSignals(BusinessSignals.builder()
                        .segmentPerformance(List.of(BusinessSignals.SignalItem.builder()
                                .title("AI connectivity demand")
                                .summary("Demand remained strong for high-speed connectivity products in AI and data-center deployments.")
                                .build()))
                        .strategicMoves(List.of(BusinessSignals.SignalItem.builder()
                                .title("Infrastructure ramp")
                                .summary("Management is still investing in capacity and customer programs for next-stage scale.")
                                .build()))
                        .build())
                .textEvidence(Map.of("MD&A", "Demand remained strong for high-speed connectivity products in AI and data-center deployments."))
                .evidenceAvailable(true)
                .build();

        AnalysisReport report = strategy.exposeParseAndValidate("""
                {
                  "coreThesis": {
                    "verdict": "positive",
                    "headline": "核心业务主线仍在延续",
                    "summary": "核心业务主线仍在延续，公司仍在加大投入。"
                  },
                  "keyMetrics": []
                }
                """, contract, "zh", "SummaryAgent").block();

        assertNotNull(report);
        assertNotNull(report.getCoreThesis());
        assertTrue(report.getCoreThesis().getSummary().contains("Credo Technology是一家面向数据中心与连接场景的半导体公司"));
        assertFalse(report.getCoreThesis().getSummary().contains("推荐效率"));
        assertFalse(report.getCoreThesis().getHeadline().equals("核心业务主线仍在延续"));
    }

    @Test
    void parseAndValidateUsesPrimaryLocalizedProductsInsteadOfAncillaryServiceKeywords() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("AAPL")
                .companyName("Apple Inc.")
                .period("Q1 2026")
                .currency("USD")
                .revenue(new BigDecimal("143756000000"))
                .revenueYoY(new BigDecimal("0.1565"))
                .operatingIncome(new BigDecimal("50852000000"))
                .netIncome(new BigDecimal("42097000000"))
                .build();

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("AAPL")
                .companyName("Apple Inc.")
                .period("Q1 2026")
                .reportType("quarterly")
                .financialFacts(facts)
                .companyProfile(CompanyProfile.builder()
                        .productLines(List.of("Advertising", "Credit card", "Subscriptions", "Smartphones", "Personal computers", "Tablets"))
                        .customerTypes(List.of("Enterprise customers"))
                        .businessModelSummary("Apple designs, manufactures, and markets smartphones, personal computers, tablets, wearables and accessories, and sells related services.")
                        .build())
                .evidenceAvailable(false)
                .build();

        AnalysisReport report = strategy.exposeParseAndValidate("""
                {
                  "coreThesis": {
                    "headline": "苹果公司在2026财年第一季度实现强劲增长，推动盈利能力提升",
                    "summary": "核心业务主线仍在延续，公司仍在加大投入。"
                  },
                  "keyMetrics": []
                }
                """, contract, "zh", "SummaryAgent").block();

        assertNotNull(report);
        assertNotNull(report.getCoreThesis());
        assertTrue(report.getCoreThesis().getSummary().contains("智能手机")
                || report.getCoreThesis().getSummary().contains("消费科技公司"));
        assertFalse(report.getCoreThesis().getSummary().contains("Advertising"));
        assertFalse(report.getCoreThesis().getSummary().contains("Credit card"));
    }

    @Test
    void parseAndValidateExtremeYoyNarrativeMentionsLowBaseInsteadOfBarePercentage() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("CRDO")
                .companyName("Credo Technology")
                .period("FY2026 Q3")
                .currency("USD")
                .marketIndustry("Semiconductors")
                .revenue(new BigDecimal("407000000"))
                .revenueYoY(new BigDecimal("2.0149"))
                .freeCashFlow(new BigDecimal("140000000"))
                .freeCashFlowYoY(new BigDecimal("365.7598"))
                .build();

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("CRDO")
                .companyName("Credo Technology")
                .period("FY2026 Q3")
                .reportType("quarterly")
                .financialFacts(facts)
                .build();

        AnalysisReport report = strategy.exposeParseAndValidate("""
                {
                  "coreThesis": {
                    "verdict": "positive",
                    "headline": "业务继续推进",
                    "summary": "本期最值得关注的不是单一财务指标，而是核心业务执行继续主导业务表现。"
                  },
                  "keyMetrics": []
                }
                """, contract, "zh", "SummaryAgent").block();

        assertNotNull(report);
        assertNotNull(report.getCoreThesis());
        assertTrue(report.getCoreThesis().getSummary().contains("去年同期基数较低"));
        assertTrue(report.getCoreThesis().getSummary().contains("+36575.98%"));
    }

    @Test
    void fallbackSignalSectionsUseConcreteProductTitlesInsteadOfGenericGrowthTemplate() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("CRDO")
                .companyName("Credo Technology")
                .period("FY2026 Q3")
                .currency("USD")
                .marketIndustry("Semiconductors")
                .revenue(new BigDecimal("407000000"))
                .revenueYoY(new BigDecimal("2.0149"))
                .freeCashFlow(new BigDecimal("140000000"))
                .freeCashFlowYoY(new BigDecimal("365.7598"))
                .build();

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("CRDO")
                .companyName("Credo Technology")
                .period("FY2026 Q3")
                .reportType("quarterly")
                .financialFacts(facts)
                .businessSignals(BusinessSignals.builder()
                        .productServiceUpdates(List.of(BusinessSignals.SignalItem.builder()
                                .title("AEC connectivity products")
                                .summary("Customers continued adopting AEC connectivity products in AI data-center deployments.")
                                .build()))
                        .strategicMoves(List.of(BusinessSignals.SignalItem.builder()
                                .title("Optical DSP products")
                                .summary("Management continues allocating resources to Optical DSP products and customer ramp.")
                                .build()))
                        .build())
                .build();

        AnalysisReport report = strategy.exposeParseAndValidate("""
                {
                  "coreThesis": {
                    "verdict": "positive",
                    "headline": "业务继续推进",
                    "summary": "核心业务主线仍在延续。",
                    "drivers": [
                      {
                        "label": "市场需求与定价能力",
                        "detail": "公司在相关市场的需求稳定。"
                      }
                    ],
                    "strategicBets": [
                      {
                        "label": "新产品开发与市场扩展",
                        "detail": "公司正在积极开发新产品。"
                      }
                    ],
                    "watchItems": [
                      "关注公司在新产品推出后的市场反应。"
                    ]
                  },
                  "keyMetrics": []
                }
                """, contract, "zh", "SummaryAgent").block();

        assertNotNull(report);
        assertNotNull(report.getCoreThesis());
        assertTrue(report.getCoreThesis().getDrivers().get(0).getLabel().contains("AEC"));
        assertTrue(report.getCoreThesis().getDrivers().get(0).getDetail().contains("AEC"));
        assertTrue(report.getCoreThesis().getStrategicBets().get(0).getLabel().contains("Optical DSP"));
        assertTrue(report.getCoreThesis().getWatchItems().get(0).contains("AEC")
                || report.getCoreThesis().getWatchItems().get(0).contains("Optical DSP"));
    }

    @Test
    void parseAndValidateUsesAvailableMetricsAndTreatsFlatGrowthAsNeutral() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("ORCL")
                .companyName("Oracle Corporation")
                .period("FY2026 Q3")
                .filingDate("2026-03-10")
                .currency("USD")
                .revenue(new BigDecimal("14130000000"))
                .revenueYoY(BigDecimal.ZERO)
                .operatingMargin(new BigDecimal("0.3086"))
                .netIncome(new BigDecimal("2936000000"))
                .netMargin(new BigDecimal("0.2078"))
                .freeCashFlow(new BigDecimal("5200000000"))
                .build();

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("ORCL")
                .companyName("Oracle Corporation")
                .period("FY2026 Q3")
                .reportType("quarterly")
                .financialFacts(facts)
                .textEvidence(Map.of("MD&A", "Oracle continued to emphasize cloud applications and infrastructure demand."))
                .evidenceAvailable(true)
                .build();

        AnalysisReport report = strategy.exposeParseAndValidate("""
                {
                  "coreThesis": {
                    "headline": "Cloud demand remained stable",
                    "summary": "Cloud applications and infrastructure remained the focus."
                  },
                  "keyMetrics": []
                }
                """, contract, "zh", "SummaryAgent").block();

        assertNotNull(report);
        assertNotNull(report.getKeyMetrics());
        assertEquals(List.of("营收", "营业利润率", "净利润", "营收同比增长"),
                report.getKeyMetrics().stream().map(AnalysisReport.MetricInsight::getMetricName).toList());
        AnalysisReport.MetricInsight growthMetric = report.getKeyMetrics().get(3);
        assertEquals("neutral", growthMetric.getSentiment());
        assertTrue(growthMetric.getInterpretation().contains("基本持平"));
        assertFalse(report.getKeyMetrics().stream().anyMatch(metric -> "毛利率".equals(metric.getMetricName())));
    }

    @Test
    void fallbackDriverAndRiskContentSkipsNAFieldsAndFlatGrowthWarnings() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("ORCL")
                .companyName("Oracle Corporation")
                .period("FY2026 Q3")
                .filingDate("2026-03-10")
                .currency("USD")
                .revenue(new BigDecimal("14130000000"))
                .revenueYoY(BigDecimal.ZERO)
                .operatingMargin(new BigDecimal("0.3084"))
                .operatingMarginChange(BigDecimal.ZERO)
                .netIncome(new BigDecimal("2936000000"))
                .netMargin(new BigDecimal("0.2078"))
                .build();

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("ORCL")
                .companyName("Oracle Corporation")
                .period("FY2026 Q3")
                .reportType("quarterly")
                .financialFacts(facts)
                .build();

        AnalysisReport report = strategy.exposeBuildFallbackReportForAgent("DriversAgent", contract, "zh");

        assertNotNull(report);
        assertNotNull(report.getBusinessDrivers());
        assertEquals(2, report.getBusinessDrivers().size());
        assertTrue(report.getBusinessDrivers().stream()
                .noneMatch(driver -> driver.getDescription() != null && driver.getDescription().contains("N/A")));
        assertTrue(report.getBusinessDrivers().stream()
                .anyMatch(driver -> "运营效率与利润兑现".equals(driver.getTitle())));

        assertNotNull(report.getRiskFactors());
        assertTrue(report.getRiskFactors().isEmpty(), "Flat revenue and missing valuation data should not create fallback risks");

        assertNotNull(report.getBullCase());
        assertFalse(report.getBullCase().contains("N/A"));
        assertTrue(report.getBullCase().contains("营业利润率"));

        assertNotNull(report.getBearCase());
        assertFalse(report.getBearCase().contains("N/A"));
        assertTrue(report.getBearCase().contains("收入迟迟不能重新加速"));
    }

    @Test
    void parseAndValidateNormalizesFiscalQuarterMentionsInChineseCoreThesis() {
        FinancialFacts facts = FinancialFacts.builder()
                .ticker("ORCL")
                .companyName("Oracle Corporation")
                .period("FY2026 Q3")
                .filingDate("2026-03-10")
                .currency("USD")
                .revenue(new BigDecimal("14130000000"))
                .revenueYoY(BigDecimal.ZERO)
                .operatingMargin(new BigDecimal("0.3086"))
                .netIncome(new BigDecimal("2936000000"))
                .netMargin(new BigDecimal("0.2078"))
                .build();

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("ORCL")
                .companyName("Oracle Corporation")
                .period("FY2026 Q3")
                .reportType("quarterly")
                .financialFacts(facts)
                .textEvidence(Map.of("MD&A", "Oracle Cloud Infrastructure revenue continued to expand."))
                .evidenceAvailable(true)
                .build();

        AnalysisReport report = strategy.exposeParseAndValidate("""
                {
                  "coreThesis": {
                    "headline": "ORACLE在Q3 2026维持稳定表现，云需求持续推动业务",
                    "summary": "在2026年第三季度，ORACLE的收入保持稳定，云需求继续支撑业务表现。",
                    "whatChanged": [
                      "Q3 2026收入基本持平。"
                    ]
                  },
                  "keyMetrics": []
                }
                """, contract, "zh", "SummaryAgent").block();

        assertNotNull(report);
        assertNotNull(report.getCoreThesis());
        assertEquals("FY2026 Q3", report.getPeriod());
        assertTrue(report.getCoreThesis().getHeadline().contains("2026财年Q3"));
        assertTrue(report.getCoreThesis().getSummary().contains("2026财年第三季度"));
        assertTrue(report.getCoreThesis().getWhatChanged().get(0).contains("2026财年Q3"));
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
                .operatingCashFlow(new BigDecimal("400000000"))
                .operatingCashFlowYoY(new BigDecimal("0.12"))
                .totalAssets(new BigDecimal("2500000000"))
                .totalEquity(new BigDecimal("1000000000"))
                .returnOnEquity(new BigDecimal("0.15"))
                .returnOnAssets(new BigDecimal("0.08"))
                .build();
    }

    private String normalizeSeverityForAssertion(String severity, boolean isZh) {
        if (!isZh) {
            return severity;
        }
        return switch (severity) {
            case "high" -> "高";
            case "medium" -> "中";
            case "low" -> "低";
            default -> severity;
        };
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

        reactor.core.publisher.Mono<AnalysisReport> exposeParseAndValidate(String json, AnalysisContract contract,
                String lang, String agentName) {
            return parseAndValidate(json, contract, lang, agentName);
        }

        AnalysisReport exposeBuildFallbackReportForAgent(String agentName, AnalysisContract contract, String lang) {
            return buildFallbackReportForAgent(agentName, contract, lang);
        }
    }
}
