package com.springalpha.backend.controller;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import com.springalpha.backend.financial.service.FinancialDataService;
import com.springalpha.backend.service.FinancialAnalysisService;
import com.springalpha.backend.service.SecService;
import com.springalpha.backend.service.profile.CompanyProfileSnapshotService;
import com.springalpha.backend.service.signals.BusinessSignalSnapshotService;
import com.springalpha.backend.service.strategy.AiAnalysisStrategy;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;

class SecControllerTest {

    @Test
    void analyzeEndpointStreamsReportsWithRequestedModelAndLanguage() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService);

        WebTestClient client = WebTestClient.bindToController(controller).build();

        List<AnalysisReport> reports = client.get()
                .uri("/api/sec/analyze/TSLA?lang=zh&model=openai")
                .header("X-OpenAI-API-Key", "sk-test")
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
        assertEquals("openai", analysisService.lastModel);
        assertEquals("quarterly", analysisService.lastReportType);
        assertEquals("sk-test", analysisService.lastOpenAiApiKey);
    }

    @Test
    void get10kContentTruncatesLargeResponses() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        secService.content = "A".repeat(10050);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService);

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
    void modelsEndpointReturnsConfiguredModels() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService);

        WebTestClient client = WebTestClient.bindToController(controller).build();

        client.get()
                .uri("/api/sec/models")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.models[0]").isEqualTo("chatanywhere")
                .jsonPath("$.models[1]").isEqualTo("openai")
                .jsonPath("$.default").isEqualTo("chatanywhere")
                .jsonPath("$.count").isEqualTo(2);
    }

    @Test
    void historyEndpointReturnsHistoricalPointsFromFinancialDataService() {
        FakeFinancialDataService financialDataService = new FakeFinancialDataService();
        FakeSecService secService = new FakeSecService(financialDataService);
        FakeFinancialAnalysisService analysisService = new FakeFinancialAnalysisService(secService, financialDataService);
        SecController controller = new SecController(secService, analysisService);

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

        private FakeFinancialAnalysisService(SecService secService, FinancialDataService financialDataService) {
            super(secService, new com.springalpha.backend.service.rag.VectorRagService(null), financialDataService,
                    mock(BusinessSignalSnapshotService.class),
                    mock(CompanyProfileSnapshotService.class),
                    List.<AiAnalysisStrategy>of());
        }

        @Override
        public Flux<AnalysisReport> analyzeStock(String ticker, String lang, String model, String openAiApiKey) {
            this.lastLang = lang;
            this.lastModel = model;
            this.lastReportType = "quarterly";
            this.lastOpenAiApiKey = openAiApiKey;
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
            return List.of("chatanywhere", "openai");
        }

        @Override
        public String getDefaultModel() {
            return "chatanywhere";
        }
    }

    private static final class FakeSecService extends SecService {

        private String content = "Management Discussion and Analysis";

        private FakeSecService(FinancialDataService financialDataService) {
            super(financialDataService);
        }

        @Override
        public Mono<String> getLatest10KContent(String ticker) {
            return Mono.just(content);
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
