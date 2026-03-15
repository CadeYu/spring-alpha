package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;

import java.math.BigDecimal;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.*;

class GroqStrategyTest {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Test
    void analyzeUsesReducedGroqExecutionPlanAndFallbackSections() {
        TestGroqStrategy strategy = new TestGroqStrategy(
                new PromptTemplateService(objectMapper),
                new AnalysisReportValidator(),
                objectMapper);

        AnalysisContract contract = AnalysisContract.builder()
                .ticker("MSFT")
                .companyName("Microsoft Corporation")
                .period("Q2 2026")
                .reportType("quarterly")
                .financialFacts(sampleFacts())
                .textEvidence(java.util.Map.of())
                .evidenceAvailable(false)
                .evidenceStatusMessage("SEC filing was available, but semantic grounding was not ready yet.")
                .build();

        List<AnalysisReport> reports = strategy.analyze(contract, "en", null).collectList().block();

        assertNotNull(reports);
        assertEquals(4, reports.size(), "Groq should still emit four partial reports for the UI");
        assertEquals(2, strategy.apiCallCount.get(), "Groq should only spend two model calls per analysis");

        AnalysisReport summary = reports.get(0);
        AnalysisReport factors = reports.get(1);
        AnalysisReport drivers = reports.get(2);
        AnalysisReport insights = reports.get(3);

        assertNotNull(summary.getCoreThesis());
        assertNotNull(factors.getFactorAnalysis());
        assertFalse(factors.getFactorAnalysis().getRevenueBridge().isEmpty());
        assertNotNull(drivers.getBusinessDrivers());
        assertFalse(drivers.getBusinessDrivers().isEmpty());
        assertNotNull(drivers.getRiskFactors());
        assertFalse(drivers.getRiskFactors().isEmpty());
        assertNotNull(drivers.getBullCase());
        assertNotNull(drivers.getBearCase());
        assertNotNull(insights.getDupontAnalysis());
    }

    private FinancialFacts sampleFacts() {
        return FinancialFacts.builder()
                .ticker("MSFT")
                .companyName("Microsoft Corporation")
                .period("Q2 2026")
                .filingDate("2026-01-31")
                .currency("USD")
                .revenue(new BigDecimal("81273000000"))
                .revenueYoY(new BigDecimal("0.0463"))
                .grossProfit(new BigDecimal("55295000000"))
                .grossMargin(new BigDecimal("0.6804"))
                .grossMarginChange(new BigDecimal("0.0060"))
                .operatingIncome(new BigDecimal("37060000000"))
                .operatingMargin(new BigDecimal("0.4560"))
                .operatingMarginChange(new BigDecimal("0.0040"))
                .netIncome(new BigDecimal("38458000000"))
                .netMargin(new BigDecimal("0.4732"))
                .netMarginChange(new BigDecimal("0.0020"))
                .operatingCashFlow(new BigDecimal("42000000000"))
                .operatingCashFlowYoY(new BigDecimal("0.0820"))
                .freeCashFlow(new BigDecimal("31000000000"))
                .freeCashFlowYoY(new BigDecimal("0.0550"))
                .totalAssets(new BigDecimal("664000000000"))
                .totalEquity(new BigDecimal("390000000000"))
                .returnOnEquity(new BigDecimal("0.0984"))
                .returnOnAssets(new BigDecimal("0.0579"))
                .priceToEarningsRatio(new BigDecimal("36.30"))
                .priceToBookRatio(new BigDecimal("10.76"))
                .build();
    }

    private static final class TestGroqStrategy extends GroqStrategy {
        private final AtomicInteger apiCallCount = new AtomicInteger();

        private TestGroqStrategy(PromptTemplateService promptService, AnalysisReportValidator validator,
                ObjectMapper objectMapper) {
            super(promptService, validator, objectMapper, "test-key");
        }

        @Override
        protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang, String apiKeyOverride) {
            int callIndex = apiCallCount.incrementAndGet();
            return Flux.just(callIndex == 1 ? summaryResponse() : insightsResponse());
        }

        private String summaryResponse() {
            return """
                    {
                      "coreThesis": {
                        "verdict": "positive",
                        "headline": "Microsoft delivered resilient quarterly growth",
                        "summary": "Revenue growth and margins remained solid in the latest quarter."
                      },
                      "keyMetrics": []
                    }
                    """;
        }

        private String insightsResponse() {
            return """
                    {
                      "dupontAnalysis": {
                        "netProfitMargin": "0.4732",
                        "assetTurnover": "0.1224",
                        "equityMultiplier": "1.7026",
                        "returnOnEquity": "0.0984",
                        "interpretation": "Profitability remains the main ROE driver."
                      },
                      "insightEngine": {
                        "accountingChanges": [],
                        "rootCauseAnalysis": [
                          {
                            "metric": "Revenue",
                            "reason": "Demand remained healthy.",
                            "evidence": "Revenue grew year over year."
                          }
                        ]
                      }
                    }
                    """;
        }
    }
}
