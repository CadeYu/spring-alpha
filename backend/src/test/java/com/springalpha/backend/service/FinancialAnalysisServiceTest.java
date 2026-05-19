package com.springalpha.backend.service;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.ResearchTaskType;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.service.provider.ProviderAuthenticationException;
import com.springalpha.backend.service.provider.ProviderCredentialValidator;
import com.springalpha.backend.service.research.ResearchAgentClient;
import com.springalpha.backend.service.research.ResearchAgentRequest;
import com.springalpha.backend.service.research.ResearchAgentResult;
import com.springalpha.backend.service.research.ResearchServiceUnavailableException;
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
        assertEquals(
                "Tesla designs electric vehicles and energy systems.",
                researchAgentClient.lastRequest.facts().get("business_summary"));
        assertEquals(
                "Tesla designs electric vehicles and energy systems.",
                researchAgentClient.lastRequest.facts().get("marketBusinessSummary"));
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
    void analyzeStockForwardsSelectedLlmModelToResearchAgent() {
        FakeProviderCredentialValidator credentialValidator = new FakeProviderCredentialValidator();
        FakeResearchAgentClient researchAgentClient = FakeResearchAgentClient.success();
        FinancialAnalysisService service = new FinancialAnalysisService(
                new FakeSecService(),
                credentialValidator,
                researchAgentClient,
                new com.springalpha.backend.service.research.ResearchAgentReportMapper());

        service.analyzeStock(
                "AAPL",
                "en",
                "siliconflow",
                "deepseek-ai/deepseek-v4-flash",
                "secret",
                ResearchTaskType.LATEST_EARNINGS_READOUT)
                .collectList()
                .block();

        assertEquals("siliconflow", credentialValidator.lastProvider);
        assertEquals("deepseek-ai/deepseek-v4-flash", researchAgentClient.lastRequest.llmModel());
    }

    @Test
    void analyzeStockForwardsConfiguredProviderKeyWhenRequestKeyIsBlank() {
        FakeProviderCredentialValidator credentialValidator = new FakeProviderCredentialValidator();
        credentialValidator.configuredApiKey = "configured-provider-key";
        FakeResearchAgentClient researchAgentClient = FakeResearchAgentClient.success();
        FinancialAnalysisService service = new FinancialAnalysisService(
                new FakeSecService(),
                credentialValidator,
                researchAgentClient,
                new com.springalpha.backend.service.research.ResearchAgentReportMapper());

        service.analyzeStock("AAPL", "en", "siliconflow", "")
                .collectList()
                .block();

        assertEquals("", credentialValidator.lastApiKey);
        assertEquals("configured-provider-key", researchAgentClient.lastRequest.llmApiKey());
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

        ResearchServiceUnavailableException error = assertThrows(ResearchServiceUnavailableException.class,
                () -> service.analyzeStock(
                        "TSLA",
                        "en",
                        "siliconflow",
                        "secret",
                        ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION)
                        .collectList()
                        .block());

        assertEquals("Python Research Service is unavailable: service unavailable", error.getMessage());
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
    void analyzeStockCapsFilingTextSentToResearchAgent() {
        FakeProviderCredentialValidator credentialValidator = new FakeProviderCredentialValidator();
        FakeResearchAgentClient researchAgentClient = FakeResearchAgentClient.success();
        FakeSecService secService = new FakeSecService("Revenue grew. ".repeat(20_000));
        FinancialAnalysisService service = new FinancialAnalysisService(
                secService,
                credentialValidator,
                researchAgentClient,
                new com.springalpha.backend.service.research.ResearchAgentReportMapper(),
                10_000);

        service.analyzeStock(
                "AAPL",
                "en",
                "siliconflow",
                "secret",
                ResearchTaskType.LATEST_EARNINGS_READOUT)
                .collectList()
                .block();

        String text = researchAgentClient.lastRequest.filings().getFirst().text();
        assertTrue(text.length() < 10_200);
        assertTrue(text.endsWith("... [Truncated for live analysis]"));
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
        private String configuredApiKey = "";

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

        @Override
        public String resolveApiKey(String provider, String apiKey) {
            if (apiKey != null && !apiKey.isBlank()) {
                return apiKey.trim();
            }
            return configuredApiKey;
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
                            List.of(),
                            finalReport),
                    null,
                    false);
        }

        private static FakeResearchAgentClient failure() {
            return new FakeResearchAgentClient(null, new ResearchServiceUnavailableException(
                    "Python Research Service is unavailable: service unavailable"), false);
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

        private final String filingContent;
        private String lastTicker;
        private String lastThreadName;

        private FakeSecService() {
            this("""
                Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
                Revenue grew because services demand improved and gross margin expanded.
                Earnings dashboard metrics include revenue, gross margin, and operating income.
                """);
        }

        private FakeSecService(String filingContent) {
            super(null);
            this.filingContent = filingContent;
        }

        @Override
        public Mono<String> getLatestFilingContent(String ticker) {
            this.lastTicker = ticker;
            return Mono.fromCallable(() -> {
                this.lastThreadName = Thread.currentThread().getName();
                return filingContent;
            });
        }

        @Override
        public com.springalpha.backend.financial.service.FinancialDataService getFinancialDataService() {
            return new com.springalpha.backend.financial.service.FinancialDataService() {
                @Override
                public FinancialFacts getFinancialFacts(String ticker) {
                    return getFinancialFacts(ticker, "quarterly");
                }

                @Override
                public FinancialFacts getFinancialFacts(String ticker, String reportType) {
                    return FinancialFacts.builder()
                            .ticker(ticker)
                            .companyName("Tesla, Inc.")
                            .period("2026Q2")
                            .filingDate("2026-05-01")
                            .currency("USD")
                            .marketSector("Consumer Cyclical")
                            .marketIndustry("Auto Manufacturers")
                            .marketBusinessSummary("Tesla designs electric vehicles and energy systems.")
                            .build();
                }

                @Override
                public boolean isSupported(String ticker) {
                    return true;
                }

                @Override
                public java.util.List<com.springalpha.backend.financial.model.HistoricalDataPoint> getHistoricalData(
                        String ticker) {
                    return java.util.List.of();
                }

                @Override
                public String[] getSupportedTickers() {
                    return new String[] { "TSLA" };
                }
            };
        }
    }
}
