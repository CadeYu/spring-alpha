package com.springalpha.backend.service;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.ResearchTaskType;
import com.springalpha.backend.service.provider.ProviderAuthenticationException;
import com.springalpha.backend.service.provider.ProviderCredentialValidator;
import com.springalpha.backend.service.research.ResearchAgentClient;
import com.springalpha.backend.service.research.ResearchAgentRequest;
import com.springalpha.backend.service.research.ResearchAgentResult;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class FinancialAnalysisServiceTest {

    @Test
    void analyzeStockUsesPythonResearchAgentAsTheOnlyAnalysisPath() {
        FakeProviderCredentialValidator credentialValidator = new FakeProviderCredentialValidator();
        FakeResearchAgentClient researchAgentClient = FakeResearchAgentClient.success();
        FakeSecService secService = new FakeSecService();
        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                credentialValidator,
                researchAgentClient,
                new com.springalpha.backend.service.research.ResearchAgentReportMapper());

        List<AnalysisReport> reports = service.analyzeStock(
                "tsla",
                "en",
                "siliconflow",
                "secret",
                ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE)
                .collectList()
                .block();

        assertNotNull(reports);
        assertEquals(1, reports.size());
        assertEquals("Python agent summary", reports.getFirst().getExecutiveSummary());
        assertEquals("siliconflow", credentialValidator.lastProvider);
        assertEquals("secret", credentialValidator.lastApiKey);
        assertEquals("TSLA", researchAgentClient.lastRequest.ticker());
        assertEquals(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, researchAgentClient.lastRequest.taskType());
        assertEquals("en", researchAgentClient.lastRequest.language());
        assertEquals("siliconflow", researchAgentClient.lastRequest.llmProvider());
        assertEquals("secret", researchAgentClient.lastRequest.llmApiKey());
        assertNotNull(researchAgentClient.lastRequest.filings());
        assertEquals(1, researchAgentClient.lastRequest.filings().size());
        assertEquals("TSLA", researchAgentClient.lastRequest.filings().getFirst().ticker());
        assertEquals("10-Q", researchAgentClient.lastRequest.filings().getFirst().filingType());
        assertTrue(researchAgentClient.lastRequest.filings().getFirst().text().contains("Revenue grew"));
        assertEquals("TSLA", secService.lastTicker);
    }

    @Test
    void analyzeStockUsesDefaultProviderWhenModelIsBlank() {
        FakeProviderCredentialValidator credentialValidator = new FakeProviderCredentialValidator();
        FakeResearchAgentClient researchAgentClient = FakeResearchAgentClient.success();
        FinancialAnalysisService service = new FinancialAnalysisService(
                new FakeSecService(),
                credentialValidator,
                researchAgentClient,
                new com.springalpha.backend.service.research.ResearchAgentReportMapper());

        service.analyzeStock("AAPL", "en", "", "secret")
                .collectList()
                .block();

        assertEquals("siliconflow", credentialValidator.lastProvider);
        assertEquals("siliconflow", researchAgentClient.lastRequest.llmProvider());
    }

    @Test
    void analyzeStockPropagatesCredentialValidationErrorsBeforeCallingResearchAgent() {
        FakeProviderCredentialValidator credentialValidator = new FakeProviderCredentialValidator();
        credentialValidator.error = new ProviderAuthenticationException(
                "SiliconFlow API key is invalid or unauthorized for this project",
                "siliconflow",
                "SILICONFLOW_API_KEY_INVALID",
                HttpStatus.UNAUTHORIZED);
        FakeResearchAgentClient researchAgentClient = FakeResearchAgentClient.success();
        FinancialAnalysisService service = new FinancialAnalysisService(
                new FakeSecService(),
                credentialValidator,
                researchAgentClient,
                new com.springalpha.backend.service.research.ResearchAgentReportMapper());

        ProviderAuthenticationException thrown = assertThrows(
                ProviderAuthenticationException.class,
                () -> service.analyzeStock("TSLA", "zh", "siliconflow", "sk-invalid")
                        .collectList()
                        .block());

        assertEquals("SILICONFLOW_API_KEY_INVALID", thrown.getCode());
        assertEquals(0, researchAgentClient.calls);
    }

    @Test
    void analyzeStockPropagatesResearchAgentFailureWithoutLegacyFallback() {
        FakeProviderCredentialValidator credentialValidator = new FakeProviderCredentialValidator();
        FakeResearchAgentClient researchAgentClient = FakeResearchAgentClient.failure();
        FinancialAnalysisService service = new FinancialAnalysisService(
                new FakeSecService(),
                credentialValidator,
                researchAgentClient,
                new com.springalpha.backend.service.research.ResearchAgentReportMapper());

        RuntimeException error = assertThrows(RuntimeException.class,
                () -> service.analyzeStock(
                        "TSLA",
                        "en",
                        "siliconflow",
                        "secret",
                        ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION)
                        .collectList()
                        .block());

        assertEquals("research service unavailable", error.getMessage());
        assertEquals(1, researchAgentClient.calls);
    }

    @Test
    void analyzeStockRunsSecFilingFetchOffReactiveEventLoop() {
        FakeProviderCredentialValidator credentialValidator = new FakeProviderCredentialValidator();
        FakeResearchAgentClient researchAgentClient = FakeResearchAgentClient.success();
        FakeSecService secService = new FakeSecService();
        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                credentialValidator,
                researchAgentClient,
                new com.springalpha.backend.service.research.ResearchAgentReportMapper());

        List<AnalysisReport> reports = Mono.defer(() -> service.analyzeStock(
                "AAPL",
                "en",
                "siliconflow",
                "secret",
                ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE).collectList())
                .subscribeOn(Schedulers.newSingle("reactor-http-nio-test"))
                .block();

        assertNotNull(reports);
        assertFalse(secService.lastThreadName.startsWith("reactor-http-nio-test"));
        assertTrue(secService.lastThreadName.contains("boundedElastic"));
    }

    @Test
    void analyzeStockFailsWhenResearchAgentReturnsNoReport() {
        FakeProviderCredentialValidator credentialValidator = new FakeProviderCredentialValidator();
        FakeResearchAgentClient researchAgentClient = FakeResearchAgentClient.empty();
        FinancialAnalysisService service = new FinancialAnalysisService(
                new FakeSecService(),
                credentialValidator,
                researchAgentClient,
                new com.springalpha.backend.service.research.ResearchAgentReportMapper());

        IllegalStateException error = assertThrows(IllegalStateException.class,
                () -> service.analyzeStock("TSLA", "en", "siliconflow", "secret")
                        .collectList()
                        .block());

        assertEquals("Python Research Service is required for analysis but returned no report", error.getMessage());
    }

    @Test
    void modelsComeFromProviderValidator() {
        FakeProviderCredentialValidator credentialValidator = new FakeProviderCredentialValidator();
        FinancialAnalysisService service = new FinancialAnalysisService(
                new FakeSecService(),
                credentialValidator,
                FakeResearchAgentClient.success(),
                new com.springalpha.backend.service.research.ResearchAgentReportMapper());

        assertEquals(List.of("gemini", "openai", "siliconflow"), service.getAvailableModels());
        assertEquals("siliconflow", service.getDefaultModel());
    }

    private static final class FakeProviderCredentialValidator implements ProviderCredentialValidator {

        private RuntimeException error;
        private String lastProvider;
        private String lastApiKey;

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
            this.lastProvider = provider;
            this.lastApiKey = apiKey;
            return error == null ? Mono.empty() : Mono.error(error);
        }
    }

    private static final class FakeResearchAgentClient implements ResearchAgentClient {

        private final ResearchAgentResult result;
        private final RuntimeException error;
        private final boolean empty;
        private int calls;
        private ResearchAgentRequest lastRequest;

        private FakeResearchAgentClient(ResearchAgentResult result, RuntimeException error, boolean empty) {
            this.result = result;
            this.error = error;
            this.empty = empty;
        }

        private static FakeResearchAgentClient success() {
            Map<String, Object> sections = new LinkedHashMap<>();
            sections.put("summary", "Python agent summary");
            Map<String, Object> finalReport = new LinkedHashMap<>();
            finalReport.put("ticker", "TSLA");
            finalReport.put("sections", sections);
            return new FakeResearchAgentClient(
                    new ResearchAgentResult(
                            "run_test",
                            ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
                            "ok",
                            List.of(),
                            List.of(),
                            finalReport),
                    null,
                    false);
        }

        private static FakeResearchAgentClient failure() {
            return new FakeResearchAgentClient(null, new RuntimeException("research service unavailable"), false);
        }

        private static FakeResearchAgentClient empty() {
            return new FakeResearchAgentClient(null, null, true);
        }

        @Override
        public Mono<ResearchAgentResult> run(ResearchAgentRequest request) {
            this.calls++;
            this.lastRequest = request;
            if (error != null) {
                return Mono.error(error);
            }
            if (empty) {
                return Mono.empty();
            }
            return Mono.just(result);
        }
    }

    private static final class FakeSecService extends SecService {

        private String lastTicker;
        private String lastThreadName;

        private FakeSecService() {
            super(null);
        }

        @Override
        public Mono<String> getLatestFilingContent(String ticker) {
            this.lastTicker = ticker;
            return Mono.fromCallable(() -> {
                this.lastThreadName = Thread.currentThread().getName();
                return """
                    Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
                    Revenue grew because services demand improved and gross margin expanded.
                    Earnings dashboard metrics include revenue, gross margin, and operating income.
                    """;
            });
        }
    }
}
