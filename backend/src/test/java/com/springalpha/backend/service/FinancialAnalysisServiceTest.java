package com.springalpha.backend.service;

import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.contract.CompanyProfile;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import com.springalpha.backend.financial.service.FinancialDataService;
import com.springalpha.backend.financial.service.UnsupportedTickerCategoryException;
import com.springalpha.backend.service.profile.CompanyProfileSnapshotService;
import com.springalpha.backend.service.rag.VectorRagService;
import com.springalpha.backend.service.signals.BusinessSignalSnapshotService;
import com.springalpha.backend.service.strategy.AiAnalysisStrategy;
import com.springalpha.backend.service.strategy.CredentialValidatingStrategy;
import com.springalpha.backend.service.strategy.ProviderAuthenticationException;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyBoolean;
import static org.mockito.ArgumentMatchers.anyMap;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

class FinancialAnalysisServiceTest {

    @Test
    void analyzeStockDegradesOnFirstRunAndStartsBackgroundVectorIngestion() throws InterruptedException {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService(sampleFacts());
        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(false);
        BusinessSignalSnapshotService snapshotService = snapshotService();
        CompanyProfileSnapshotService profileSnapshotService = profileSnapshotService();
        CapturingStrategy strategy = new CapturingStrategy("chatanywhere");

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                snapshotService,
                profileSnapshotService,
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
        assertTrue(contract.getEvidenceStatusMessage().contains("语义 grounding 尚未就绪"));
        assertEquals("Tesla, Inc.", contract.getCompanyName());
        assertEquals("quarterly", contract.getReportType());
        assertTrue(contract.getTextEvidence().get("MD&A").startsWith("Management Discussion and Analysis"));
        assertNotNull(contract.getBusinessSignals());
        assertNotNull(contract.getCompanyProfile());
        verify(snapshotService).getOrExtract(eq("TSLA"), eq("quarterly"), any(), anyMap(), eq(false));
        verify(profileSnapshotService).getOrExtract(eq("TSLA"), eq("quarterly"), any(), any(), anyMap());

        waitForBackgroundIngestion(vectorRagService);
        assertEquals(1, vectorRagService.storeCalls);
        assertEquals("TSLA", vectorRagService.lastStoredTicker);
    }

    @Test
    void analyzeStockUsesGroundedVectorSearchWhenCachedDocumentsExist() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService(sampleFacts());
        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(true);
        BusinessSignalSnapshotService snapshotService = snapshotService();
        CompanyProfileSnapshotService profileSnapshotService = profileSnapshotService();
        vectorRagService.mdnaResult = "MD&A excerpt";
        vectorRagService.riskResult = "Risk excerpt";
        CapturingStrategy strategy = new CapturingStrategy("chatanywhere");

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                snapshotService,
                profileSnapshotService,
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
        assertEquals("quarterly", contract.getReportType());
        assertEquals("MD&A excerpt", contract.getTextEvidence().get("MD&A"));
        assertEquals("Risk excerpt", contract.getTextEvidence().get("Risk Factors"));
        assertNotNull(contract.getBusinessSignals());
        assertNotNull(contract.getCompanyProfile());
        assertEquals(0, vectorRagService.storeCalls);
    }

    @Test
    void analyzeStockResetsTickerVectorsAndDegradesOnDimensionMismatch() throws InterruptedException {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService(sampleFacts());
        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(false);
        BusinessSignalSnapshotService snapshotService = snapshotService();
        CompanyProfileSnapshotService profileSnapshotService = profileSnapshotService();
        vectorRagService.throwDimensionMismatchOnHasDocuments = true;
        CapturingStrategy strategy = new CapturingStrategy("chatanywhere");

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                snapshotService,
                profileSnapshotService,
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
        assertTrue(contract.getEvidenceStatusMessage().contains("embedding 维度变化"));
        assertEquals("quarterly", contract.getReportType());
        verify(snapshotService).getOrExtract(eq("TSLA"), eq("quarterly"), any(), anyMap(), eq(false));
        verify(profileSnapshotService).getOrExtract(eq("TSLA"), eq("quarterly"), any(), any(), anyMap());

        waitForBackgroundIngestion(vectorRagService);
        assertEquals(1, vectorRagService.deleteCalls);
        assertEquals(1, vectorRagService.storeCalls);
    }

    @Test
    void analyzeStockSkipsBackgroundVectorIngestionWhenSameFilingIsAlreadyQueued() throws InterruptedException {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService(sampleFacts());
        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(false);
        vectorRagService.allowBackgroundIngestion = false;
        BusinessSignalSnapshotService snapshotService = snapshotService();
        CompanyProfileSnapshotService profileSnapshotService = profileSnapshotService();
        CapturingStrategy strategy = new CapturingStrategy("chatanywhere");

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                snapshotService,
                profileSnapshotService,
                List.of(strategy));

        List<AnalysisReport> reports = service.analyzeStock("TSLA", "zh", "chatanywhere", null)
                .collectList()
                .block();

        assertNotNull(reports);
        Thread.sleep(200);
        assertEquals(0, vectorRagService.storeCalls);
    }

    @Test
    void analyzeStockUsesQuarterlyReportTypeThroughoutTheMainPath() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService(sampleFacts());
        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(true);
        BusinessSignalSnapshotService snapshotService = snapshotService();
        CompanyProfileSnapshotService profileSnapshotService = profileSnapshotService();
        vectorRagService.mdnaResult = "MD&A excerpt";
        vectorRagService.riskResult = "Risk excerpt";
        CapturingStrategy strategy = new CapturingStrategy("chatanywhere");

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                snapshotService,
                profileSnapshotService,
                List.of(strategy));

        List<AnalysisReport> reports = service.analyzeStock("TSLA", "en", "chatanywhere", null)
                .collectList()
                .block();

        assertNotNull(reports);
        assertEquals("quarterly", financialDataService.lastReportType);
        assertEquals("quarterly", strategy.lastContract().getReportType());
        verify(snapshotService).getOrExtract(eq("TSLA"), eq("quarterly"), any(), anyMap(), eq(true));
        verify(profileSnapshotService).getOrExtract(eq("TSLA"), eq("quarterly"), any(), any(), anyMap());
    }

    @Test
    void analyzeStockRejectsUnsupportedReitTickersBeforeSecAnalysisStarts() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService(
                FinancialFacts.builder()
                        .ticker("AMT")
                        .companyName("American Tower Corporation")
                        .period("FY2025 Q4")
                        .filingDate("2026-02-24")
                        .dashboardMode("unsupported_reit")
                        .build());
        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(true);
        BusinessSignalSnapshotService snapshotService = snapshotService();
        CompanyProfileSnapshotService profileSnapshotService = profileSnapshotService();
        CapturingStrategy strategy = new CapturingStrategy("chatanywhere");

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                snapshotService,
                profileSnapshotService,
                List.of(strategy));

        UnsupportedTickerCategoryException thrown = assertThrows(
                UnsupportedTickerCategoryException.class,
                () -> service.analyzeStock("AMT", "zh", "chatanywhere", null)
                        .collectList()
                        .block());

        assertEquals("AMT", thrown.getTicker());
        assertEquals("unsupported_reit", thrown.getCategory());
        assertNull(strategy.lastContract());
        verify(snapshotService, never()).getOrExtract(anyString(), anyString(), any(), anyMap(), anyBoolean());
        verify(profileSnapshotService, never()).getOrExtract(anyString(), anyString(), any(), any(), anyMap());
    }

    @Test
    void analyzeStockOffloadsFinancialFactsFetchFromNonBlockingSubscriberThread() throws InterruptedException {
        AtomicBoolean calledOnNonBlockingThread = new AtomicBoolean(true);
        FinancialDataService financialDataService = new FinancialDataService() {
            @Override
            public FinancialFacts getFinancialFacts(String ticker) {
                return sampleFacts();
            }

            @Override
            public FinancialFacts getFinancialFacts(String ticker, String reportType) {
                calledOnNonBlockingThread.set(Schedulers.isInNonBlockingThread());
                return sampleFacts();
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
            public List<HistoricalDataPoint> getHistoricalData(String ticker, String reportType) {
                return List.of();
            }

            @Override
            public String[] getSupportedTickers() {
                return new String[] { "TSLA" };
            }
        };

        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(true);
        BusinessSignalSnapshotService snapshotService = snapshotService();
        CompanyProfileSnapshotService profileSnapshotService = profileSnapshotService();
        vectorRagService.mdnaResult = "MD&A excerpt";
        vectorRagService.riskResult = "Risk excerpt";
        CapturingStrategy strategy = new CapturingStrategy("chatanywhere");

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                snapshotService,
                profileSnapshotService,
                List.of(strategy));

        CountDownLatch completed = new CountDownLatch(1);
        AtomicReference<Throwable> errorRef = new AtomicReference<>();

        Schedulers.parallel().schedule(() -> service.analyzeStock("TSLA", "en", "chatanywhere", null)
                .doFinally(signal -> completed.countDown())
                .subscribe(report -> {
                }, errorRef::set));

        assertTrue(completed.await(3, TimeUnit.SECONDS), "analysis should complete");
        assertNull(errorRef.get(), "analysis should not fail when subscribed from a non-blocking scheduler");
        assertFalse(calledOnNonBlockingThread.get(),
                "financial facts fetch must not execute on Reactor non-blocking threads");
    }

    @Test
    void analyzeStockPropagatesCredentialValidationErrorsBeforeStreamingStarts() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService(sampleFacts());
        FakeSecService secService = new FakeSecService(financialDataService, sampleFiling());
        FakeVectorRagService vectorRagService = new FakeVectorRagService(true);
        BusinessSignalSnapshotService snapshotService = snapshotService();
        CompanyProfileSnapshotService profileSnapshotService = profileSnapshotService();
        InvalidCredentialStrategy strategy = new InvalidCredentialStrategy();

        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                vectorRagService,
                financialDataService,
                snapshotService,
                profileSnapshotService,
                List.of(strategy));

        ProviderAuthenticationException thrown = assertThrows(
                ProviderAuthenticationException.class,
                () -> service.analyzeStock("TSLA", "zh", "openai", "sk-invalid")
                        .collectList()
                        .block());

        assertEquals("OPENAI_API_KEY_INVALID", thrown.getCode());
        assertEquals(0, financialDataService.factsCalls);
        assertFalse(strategy.analyzeCalled);
        verify(snapshotService, never()).getOrExtract(anyString(), anyString(), any(), anyMap(), anyBoolean());
        verify(profileSnapshotService, never()).getOrExtract(anyString(), anyString(), any(), any(), anyMap());
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
                .period("Q4 2025")
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

    private BusinessSignalSnapshotService snapshotService() {
        BusinessSignalSnapshotService snapshotService = mock(BusinessSignalSnapshotService.class);
        when(snapshotService.getOrExtract(anyString(), anyString(), any(), anyMap(), anyBoolean()))
                .thenReturn(sampleBusinessSignals());
        return snapshotService;
    }

    private BusinessSignals sampleBusinessSignals() {
        return BusinessSignals.builder()
                .ticker("TSLA")
                .reportType("quarterly")
                .period("Q4 2025")
                .filingDate("2026-01-29")
                .segmentPerformance(List.of(BusinessSignals.SignalItem.builder()
                        .title("Automotive demand")
                        .summary("Vehicle demand remained under pressure due to pricing and volume.")
                        .evidenceSection("MD&A")
                        .evidenceSnippet("Revenue growth was pressured by pricing and volume.")
                        .build()))
                .evidenceRefs(List.of(BusinessSignals.EvidenceRef.builder()
                        .topic("Automotive demand")
                        .section("MD&A")
                        .excerpt("Revenue growth was pressured by pricing and volume.")
                        .build()))
                .build();
    }

    private CompanyProfileSnapshotService profileSnapshotService() {
        CompanyProfileSnapshotService service = mock(CompanyProfileSnapshotService.class);
        when(service.getOrExtract(anyString(), anyString(), any(), any(), anyMap()))
                .thenReturn(CompanyProfile.builder()
                        .ticker("TSLA")
                        .reportType("quarterly")
                        .businessModelSummary("Electric vehicle and energy platform")
                        .productLines(List.of("Vehicles", "Energy storage"))
                        .customerTypes(List.of("Consumers"))
                        .keyKpis(List.of("Revenue", "Gross Margin"))
                        .build());
        return service;
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
                    .reportType(contract.getReportType())
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
        private String lastReportType = "quarterly";
        private int factsCalls;

        private FakeFinancialDataService(FinancialFacts facts) {
            this.facts = facts;
        }

        @Override
        public FinancialFacts getFinancialFacts(String ticker) {
            this.factsCalls++;
            this.lastReportType = "quarterly";
            return facts;
        }

        @Override
        public FinancialFacts getFinancialFacts(String ticker, String reportType) {
            this.factsCalls++;
            this.lastReportType = reportType;
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

        @Override
        public Mono<String> getLatestFilingContent(String ticker) {
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
        private boolean allowBackgroundIngestion = true;

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
        public boolean shouldStartBackgroundIngestion(String ticker, String content) {
            return allowBackgroundIngestion;
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

    private static final class InvalidCredentialStrategy
            implements AiAnalysisStrategy, CredentialValidatingStrategy {

        private boolean analyzeCalled;

        @Override
        public String getName() {
            return "openai";
        }

        @Override
        public Flux<AnalysisReport> analyze(AnalysisContract contract, String lang, String apiKeyOverride) {
            analyzeCalled = true;
            return Flux.error(new AssertionError("analyze should not run when credential validation fails"));
        }

        @Override
        public Mono<Void> validateCredentials(String apiKeyOverride) {
            return Mono.error(new ProviderAuthenticationException(
                    "OpenAI API key is invalid or unauthorized for this project",
                    "openai",
                    "OPENAI_API_KEY_INVALID",
                    HttpStatus.UNAUTHORIZED));
        }
    }
}
