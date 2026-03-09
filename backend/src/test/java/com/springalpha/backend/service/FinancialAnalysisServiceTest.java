package com.springalpha.backend.service;

import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import com.springalpha.backend.financial.service.FinancialDataService;
import com.springalpha.backend.service.rag.VectorRagService;
import com.springalpha.backend.service.strategy.AiAnalysisStrategy;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class FinancialAnalysisServiceTest {

    @Test
    void analyzeStockDegradesOnFirstRunAndStartsBackgroundVectorIngestion() throws InterruptedException {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService(sampleFacts());
        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(false);
        CapturingStrategy strategy = new CapturingStrategy("chatanywhere");

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                List.of(strategy));

        List<AnalysisReport> reports = service.analyzeStock("TSLA", "zh", "chatanywhere", null)
                .collectList()
                .block();

        assertNotNull(reports);
        assertTrue(reports.stream().anyMatch(report -> report.getSourceContext() != null
                && "UNAVAILABLE".equals(report.getSourceContext().getStatus())));
        assertTrue(reports.stream().anyMatch(report -> report.getSourceContext() != null
                && "DEGRADED".equals(report.getSourceContext().getStatus())));

        AnalysisContract contract = strategy.lastContract();
        assertNotNull(contract);
        assertFalse(contract.isEvidenceAvailable());
        assertTrue(contract.getEvidenceStatusMessage().contains("semantic grounding was not ready yet"));
        assertEquals("Tesla, Inc.", contract.getCompanyName());
        assertTrue(contract.getTextEvidence().get("MD&A").startsWith("Management Discussion and Analysis"));

        waitForBackgroundIngestion(vectorRagService);
        assertEquals(1, vectorRagService.storeCalls);
        assertEquals("TSLA", vectorRagService.lastStoredTicker);
    }

    @Test
    void analyzeStockUsesGroundedVectorSearchWhenCachedDocumentsExist() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService(sampleFacts());
        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(true);
        vectorRagService.mdnaResult = "MD&A excerpt";
        vectorRagService.riskResult = "Risk excerpt";
        CapturingStrategy strategy = new CapturingStrategy("chatanywhere");

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                List.of(strategy));

        List<AnalysisReport> reports = service.analyzeStock("TSLA", "en", "chatanywhere", null)
                .collectList()
                .block();

        assertNotNull(reports);
        assertTrue(reports.stream().anyMatch(report -> report.getSourceContext() != null
                && "GROUNDED".equals(report.getSourceContext().getStatus())));

        AnalysisContract contract = strategy.lastContract();
        assertNotNull(contract);
        assertTrue(contract.isEvidenceAvailable());
        assertEquals("MD&A excerpt", contract.getTextEvidence().get("MD&A"));
        assertEquals("Risk excerpt", contract.getTextEvidence().get("Risk Factors"));
        assertEquals(0, vectorRagService.storeCalls);
    }

    @Test
    void analyzeStockResetsTickerVectorsAndDegradesOnDimensionMismatch() throws InterruptedException {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService(sampleFacts());
        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(false);
        vectorRagService.throwDimensionMismatchOnHasDocuments = true;
        CapturingStrategy strategy = new CapturingStrategy("chatanywhere");

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                List.of(strategy));

        List<AnalysisReport> reports = service.analyzeStock("TSLA", "zh", "chatanywhere", null)
                .collectList()
                .block();

        assertNotNull(reports);
        assertTrue(reports.stream().anyMatch(report -> report.getSourceContext() != null
                && "DEGRADED".equals(report.getSourceContext().getStatus())));

        AnalysisContract contract = strategy.lastContract();
        assertNotNull(contract);
        assertFalse(contract.isEvidenceAvailable());
        assertTrue(contract.getEvidenceStatusMessage().contains("embedding dimension change"));

        waitForBackgroundIngestion(vectorRagService);
        assertEquals(1, vectorRagService.deleteCalls);
        assertEquals(1, vectorRagService.storeCalls);
    }

    private void waitForBackgroundIngestion(FakeVectorRagService vectorRagService) throws InterruptedException {
        long deadline = System.nanoTime() + Duration.ofSeconds(2).toNanos();
        while (vectorRagService.storeCalls == 0 && System.nanoTime() < deadline) {
            Thread.sleep(25);
        }
    }

    private FinancialFacts sampleFacts() {
        return FinancialFacts.builder()
                .ticker("TSLA")
                .companyName("Tesla, Inc.")
                .period("FY 2025")
                .filingDate("2026-01-29")
                .currency("USD")
                .revenue(new BigDecimal("94827000000"))
                .revenueYoY(new BigDecimal("-0.0293"))
                .netIncome(new BigDecimal("3794000000"))
                .grossMargin(new BigDecimal("0.1803"))
                .operatingMargin(new BigDecimal("0.0459"))
                .netMargin(new BigDecimal("0.0400"))
                .freeCashFlow(new BigDecimal("6220000000"))
                .returnOnEquity(new BigDecimal("0.0462"))
                .returnOnAssets(new BigDecimal("0.0275"))
                .build();
    }

    private String sampleFiling() {
        return "Management Discussion and Analysis Revenue growth was pressured by pricing and volume. "
                + "Risk Factors include competition and execution risk.";
    }

    private static final class CapturingStrategy implements AiAnalysisStrategy {

        private final String name;
        private AnalysisContract lastContract;

        private CapturingStrategy(String name) {
            this.name = name;
        }

        @Override
        public String getName() {
            return name;
        }

        @Override
        public Flux<AnalysisReport> analyze(AnalysisContract contract, String lang, String apiKeyOverride) {
            this.lastContract = contract;
            AnalysisReport.SourceContext sourceContext = AnalysisReport.SourceContext.builder()
                    .status(contract.isEvidenceAvailable() ? "GROUNDED" : "DEGRADED")
                    .message(contract.getEvidenceStatusMessage())
                    .build();

            return Flux.just(AnalysisReport.builder()
                    .executiveSummary("stub report")
                    .companyName(contract.getCompanyName())
                    .period(contract.getPeriod())
                    .sourceContext(sourceContext)
                    .build());
        }

        private AnalysisContract lastContract() {
            return lastContract;
        }
    }

    private static final class FakeFinancialDataService implements FinancialDataService {

        private final FinancialFacts facts;

        private FakeFinancialDataService(FinancialFacts facts) {
            this.facts = facts;
        }

        @Override
        public FinancialFacts getFinancialFacts(String ticker) {
            return facts;
        }

        @Override
        public boolean isSupported(String ticker) {
            return true;
        }

        @Override
        public List<HistoricalDataPoint> getHistoricalData(String ticker) {
            return List.of();
        }

        @Override
        public String[] getSupportedTickers() {
            return new String[] { "TSLA" };
        }
    }

    private static final class FakeSecService extends SecService {

        private final String filingContent;

        private FakeSecService(FinancialDataService financialDataService, String filingContent) {
            super(financialDataService);
            this.filingContent = filingContent;
        }

        @Override
        public Mono<String> getLatest10KContent(String ticker) {
            return Mono.just(filingContent);
        }
    }

    private static final class FakeVectorRagService extends VectorRagService {

        private final boolean hasDocuments;
        private boolean throwDimensionMismatchOnHasDocuments;
        private String mdnaResult = "";
        private String riskResult = "";
        private int storeCalls;
        private int deleteCalls;
        private String lastStoredTicker;

        private FakeVectorRagService(boolean hasDocuments) {
            super(null);
            this.hasDocuments = hasDocuments;
        }

        @Override
        public boolean hasDocuments(String ticker) {
            if (throwDimensionMismatchOnHasDocuments) {
                throw new RuntimeException("ERROR: different vector dimensions 3072 and 768");
            }
            return hasDocuments;
        }

        @Override
        public String retrieveRelevantContext(String ticker, String query) {
            if (query.contains("Management Discussion Analysis")) {
                return mdnaResult;
            }
            return riskResult;
        }

        @Override
        public void storeDocument(String ticker, String content) {
            this.storeCalls++;
            this.lastStoredTicker = ticker;
        }

        @Override
        public void deleteDocuments(String ticker) {
            this.deleteCalls++;
        }
    }
}
