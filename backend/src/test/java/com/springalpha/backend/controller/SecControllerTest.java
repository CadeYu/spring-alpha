package com.springalpha.backend.controller;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.ResearchTaskType;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import com.springalpha.backend.financial.service.FinancialDataService;
import com.springalpha.backend.service.FinancialAnalysisService;
import com.springalpha.backend.service.SecService;
import com.springalpha.backend.service.provider.ProviderCredentialValidator;
import com.springalpha.backend.service.research.ResearchServiceUnavailableException;
import com.springalpha.backend.trial.TrialDecision;
import com.springalpha.backend.trial.TrialLedgerService;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class SecControllerTest {

    @Test
    void analyzeEndpointStreamsReportsWithRequestedModelAndLanguage() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService, new FakeTrialLedgerService(true));

        WebTestClient client = WebTestClient.bindToController(controller).build();

        List<AnalysisReport> reports = client.get()
                .uri("/api/sec/analyze/TSLA?lang=zh&model=siliconflow")
                .header("X-Provider-API-Key", "sk-test")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .returnResult(AnalysisReport.class)
                .getResponseBody()
                .collectList()
                .block();

        assertTrue(reports != null && !reports.isEmpty());
        assertEquals("Tesla, Inc.", reports.get(0).getCompanyName());
        assertEquals("zh", analysisService.lastLang);
        assertEquals("siliconflow", analysisService.lastModel);
        assertEquals("quarterly", analysisService.lastReportType);
        assertEquals("sk-test", analysisService.lastOpenAiApiKey);
        assertEquals(ResearchTaskType.LATEST_EARNINGS_READOUT, analysisService.lastTaskType);
    }

    @Test
    void analyzeEndpointPassesLatestEarningsReadoutTaskTypeToService() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService, new FakeTrialLedgerService(true));

        WebTestClient client = WebTestClient.bindToController(controller).build();

        client.get()
                .uri("/api/sec/analyze/AAPL?taskType=latest_earnings_readout")
                .header("X-Provider-API-Key", "sk-test")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .returnResult(AnalysisReport.class)
                .getResponseBody()
                .collectList()
                .block();

        assertEquals(ResearchTaskType.LATEST_EARNINGS_READOUT, analysisService.lastTaskType);
        assertEquals(1, analysisService.callCount);
    }

    @Test
    void analyzeEndpointRejectsUnsupportedTaskTypeBeforeCallingService() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService, new FakeTrialLedgerService(true));

        WebTestClient client = WebTestClient.bindToController(controller).build();

        client.get()
                .uri("/api/sec/analyze/AAPL?taskType=freeform_prompt")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isBadRequest();

        assertEquals(0, analysisService.callCount);
    }

    @Test
    void analyzeEndpointRejectsTrialExhaustedAnonymousRequests() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        FakeTrialLedgerService trialLedgerService = new FakeTrialLedgerService(false);
        SecController controller = new SecController(secService, analysisService, trialLedgerService);

        WebTestClient client = WebTestClient.bindToController(controller)
                .controllerAdvice(new ApiExceptionHandler())
                .build();

        client.get()
                .uri("/api/sec/analyze/AAPL?taskType=latest_earnings_readout")
                .header("X-Visitor-Id", UUID.randomUUID().toString())
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isEqualTo(402)
                .expectBody(String.class)
                .value(body -> assertTrue(body.contains("TRIAL_EXHAUSTED")));

        assertEquals(0, analysisService.callCount);
    }

    @Test
    void analyzeEndpointReturnsKeyRequiredWhenAuthenticatedUserHasNoSavedKey() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        FakeTrialLedgerService trialLedgerService = new FakeTrialLedgerService(true);
        SecController controller = new SecController(secService, analysisService, trialLedgerService);

        WebTestClient client = WebTestClient.bindToController(controller)
                .controllerAdvice(new ApiExceptionHandler())
                .build();

        client.get()
                .uri("/api/sec/analyze/AAPL?taskType=latest_earnings_readout")
                .header("X-Auth-Mode", "authenticated")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody(String.class)
                .value(body -> assertTrue(body.contains("PROVIDER_KEY_REQUIRED")));

        assertEquals(0, analysisService.callCount);
    }

    @Test
    void analyzeEndpointReturnsServiceUnavailableWhenResearchServiceFails() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        analysisService.error = new ResearchServiceUnavailableException(
                "Python Research Service is unavailable: connection refused");
        SecController controller = new SecController(secService, analysisService, new FakeTrialLedgerService(true));

        WebTestClient client = WebTestClient.bindToController(controller)
                .controllerAdvice(new ApiExceptionHandler())
                .build();

        client.get()
                .uri("/api/sec/analyze/AAPL?taskType=latest_earnings_readout")
                .header("X-Provider-API-Key", "sk-test")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isEqualTo(503)
                .expectBody(String.class)
                .value(body -> {
                    assertTrue(body.contains("RESEARCH_SERVICE_UNAVAILABLE"));
                    assertTrue(body.contains("python-research-service"));
                    assertTrue(body.contains("degraded"));
                });
    }

    @Test
    void get10kContentTruncatesLargeResponses() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        secService.content = "A".repeat(10050);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService, new FakeTrialLedgerService(true));

        WebTestClient client = WebTestClient.bindToController(controller).build();

        String body = client.get()
                .uri("/api/sec/10k/TSLA")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .returnResult()
                .getResponseBody();

        assertTrue(body != null && body.endsWith("... (truncated)"));
    }

    @Test
    void get10kContentRunsBlockingFetchOffEventLoop() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        secService.assertOffEventLoop = true;
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService, new FakeTrialLedgerService(true));

        WebTestClient client = WebTestClient.bindToController(controller).build();

        String body = client.get()
                .uri("/api/sec/10k/TSLA")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class)
                .returnResult()
                .getResponseBody();

        assertEquals("Management Discussion and Analysis", body);
        assertTrue(secService.lastThreadName.contains("boundedElastic"));
    }

    @Test
    void modelsEndpointReturnsConfiguredModels() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService, new FakeTrialLedgerService(true));

        WebTestClient client = WebTestClient.bindToController(controller).build();

        client.get()
                .uri("/api/sec/models")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.models[0]").isEqualTo("gemini")
                .jsonPath("$.models[1]").isEqualTo("openai")
                .jsonPath("$.models[2]").isEqualTo("siliconflow")
                .jsonPath("$.default").isEqualTo("siliconflow")
                .jsonPath("$.count").isEqualTo(3);
    }

    @Test
    void historyEndpointReturnsHistoricalPointsFromFinancialDataService() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService, new FakeTrialLedgerService(true));

        WebTestClient client = WebTestClient.bindToController(controller).build();

        List<HistoricalDataPoint> history = client.get()
                .uri("/api/sec/history/TSLA")
                .exchange()
                .expectStatus().isOk()
                .returnResult(HistoricalDataPoint.class)
                .getResponseBody()
                .collectList()
                .block();

        assertEquals(1, history.size());
        assertEquals("Q4 2025", history.get(0).getPeriod());
    }

    private static final class FakeFinancialAnalysisService extends FinancialAnalysisService {

        private String lastLang;
        private String lastModel;
        private String lastReportType;
        private String lastOpenAiApiKey;
        private ResearchTaskType lastTaskType;
        private int callCount;
        private RuntimeException error;

        private FakeFinancialAnalysisService(SecService secService, FinancialDataService financialDataService) {
            super(secService,
                    new FakeProviderCredentialValidator(),
                    request -> Mono.empty(),
                    new com.springalpha.backend.service.research.ResearchAgentReportMapper());
        }

        @Override
        public Flux<AnalysisReport> analyzeStock(String ticker, String lang, String model, String openAiApiKey) {
            return analyzeStock(ticker, lang, model, openAiApiKey, ResearchTaskType.LATEST_EARNINGS_READOUT);
        }

        @Override
        public Flux<AnalysisReport> analyzeStock(String ticker, String lang, String model, String openAiApiKey,
                ResearchTaskType taskType) {
            this.callCount++;
            this.lastLang = lang;
            this.lastModel = model;
            this.lastReportType = "quarterly";
            this.lastOpenAiApiKey = openAiApiKey;
            this.lastTaskType = taskType;
            if (error != null) {
                return Flux.error(error);
            }
            return Flux.just(AnalysisReport.builder()
                    .executiveSummary("stub report")
                    .companyName("Tesla, Inc.")
                    .reportType("quarterly")
                    .period("Q4 2025")
                    .filingDate("2026-01-29")
                    .build());
        }

        @Override
        public List<String> getAvailableModels() {
            return List.of("gemini", "openai", "siliconflow");
        }

        @Override
        public String getDefaultModel() {
            return "siliconflow";
        }
    }

    private static final class FakeTrialLedgerService extends TrialLedgerService {

        private final boolean allow;

        private FakeTrialLedgerService(boolean allow) {
            super(new NoopAnonymousVisitorStore());
            this.allow = allow;
        }

        @Override
        public TrialDecision reserveAnonymousTrial(UUID visitorId, Optional<String> ipHash) {
            return allow
                    ? TrialDecision.allow()
                    : TrialDecision.deny("TRIAL_EXHAUSTED", "Trial exhausted");
        }
    }

    private static final class NoopAnonymousVisitorStore implements com.springalpha.backend.trial.AnonymousVisitorStore {

        @Override
        public Optional<com.springalpha.backend.trial.AnonymousVisitor> findById(UUID visitorId) {
            return Optional.empty();
        }

        @Override
        public com.springalpha.backend.trial.AnonymousVisitor save(
                com.springalpha.backend.trial.AnonymousVisitor visitor) {
            return visitor;
        }
    }

    private static final class FakeProviderCredentialValidator implements ProviderCredentialValidator {

        @Override
        public List<String> availableProviders() {
            return List.of("gemini", "openai", "siliconflow");
        }

        @Override
        public String defaultProvider() {
            return "siliconflow";
        }

        @Override
        public Mono<Void> validate(String provider, String apiKey) {
            return Mono.empty();
        }
    }

    private static final class FakeSecService extends SecService {

        private String content = "Management Discussion and Analysis";
        private boolean assertOffEventLoop;
        private String lastThreadName = "";

        private FakeSecService(FinancialDataService financialDataService) {
            super(financialDataService);
        }

        @Override
        public Mono<String> getLatest10KContent(String ticker) {
            return Mono.fromCallable(() -> {
                lastThreadName = Thread.currentThread().getName();
                if (assertOffEventLoop && lastThreadName.startsWith("reactor-http-nio")) {
                    throw new IllegalStateException("Debug filing fetch ran on event loop");
                }
                return content;
            });
        }
    }

    private static final class FakeFinancialDataService implements FinancialDataService {

        @Override
        public com.springalpha.backend.financial.model.FinancialFacts getFinancialFacts(String ticker) {
            return null;
        }

        @Override
        public boolean isSupported(String ticker) {
            return true;
        }

        @Override
        public List<HistoricalDataPoint> getHistoricalData(String ticker) {
            return List.of(HistoricalDataPoint.builder()
                    .period("Q4 2025")
                    .grossMargin(new BigDecimal("0.40"))
                    .operatingMargin(new BigDecimal("0.20"))
                    .netMargin(new BigDecimal("0.10"))
                    .revenue(new BigDecimal("100"))
                    .netIncome(new BigDecimal("10"))
                    .build());
        }

        @Override
        public String[] getSupportedTickers() {
            return new String[] { "TSLA" };
        }
    }
}
