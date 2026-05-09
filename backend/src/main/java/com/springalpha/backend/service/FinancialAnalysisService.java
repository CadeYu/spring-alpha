package com.springalpha.backend.service;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.ResearchTaskType;
import com.springalpha.backend.service.provider.ProviderCredentialValidator;
import com.springalpha.backend.service.research.ResearchAgentClient;
import com.springalpha.backend.service.research.ResearchAgentReportMapper;
import com.springalpha.backend.service.research.ResearchAgentRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.List;
import java.util.Locale;
import java.util.UUID;

@Slf4j
@Service
public class FinancialAnalysisService {

    private final SecService secService;
    private final ProviderCredentialValidator providerCredentialValidator;
    private final ResearchAgentClient researchAgentClient;
    private final ResearchAgentReportMapper researchAgentReportMapper;

    @Autowired
    public FinancialAnalysisService(
            SecService secService,
            ProviderCredentialValidator providerCredentialValidator,
            ResearchAgentClient researchAgentClient,
            ResearchAgentReportMapper researchAgentReportMapper) {
        this.secService = secService;
        this.providerCredentialValidator = providerCredentialValidator;
        this.researchAgentClient = researchAgentClient;
        this.researchAgentReportMapper = researchAgentReportMapper;
    }

    public List<String> getAvailableModels() {
        return providerCredentialValidator.availableProviders();
    }

    public String getDefaultModel() {
        return providerCredentialValidator.defaultProvider();
    }

    public Flux<AnalysisReport> analyzeStock(String ticker, String lang, String model, String providerApiKey) {
        return analyzeStock(ticker, lang, model, providerApiKey, ResearchTaskType.LATEST_EARNINGS_READOUT);
    }

    public Flux<AnalysisReport> analyzeStock(
            String ticker,
            String lang,
            String model,
            String providerApiKey,
            ResearchTaskType taskType) {
        String provider = resolveProvider(model);
        String language = lang != null && !lang.isBlank() ? lang : "en";
        String normalizedTicker = ticker.toUpperCase(Locale.ROOT);
        ResearchTaskType effectiveTaskType = taskType != null ? taskType : ResearchTaskType.LATEST_EARNINGS_READOUT;

        return providerCredentialValidator.validate(provider, providerApiKey)
                .thenMany(Flux.defer(() -> secService.getLatestFilingContent(normalizedTicker)
                        .subscribeOn(Schedulers.boundedElastic())
                        .flatMapMany(filingText -> runResearchAgent(normalizedTicker, language, provider, providerApiKey,
                                effectiveTaskType, filingText))));
    }

    private Flux<AnalysisReport> runResearchAgent(
            String ticker,
            String language,
            String provider,
            String providerApiKey,
            ResearchTaskType taskType,
            String filingText) {
        String runId = "run_" + UUID.randomUUID();
        long startedAtNanos = System.nanoTime();
        ResearchAgentRequest request = new ResearchAgentRequest(
                runId,
                ticker,
                taskType,
                language,
                2,
                provider,
                null,
                providerApiKey,
                List.of(new ResearchAgentRequest.FilingDocument(
                        ticker,
                        "10-Q",
                        null,
                        null,
                        filingText)));

        log.info("research_agent_start runId={} ticker={} taskType={} provider={}",
                runId, ticker, taskType, provider);

        return researchAgentClient.run(request)
                .switchIfEmpty(Mono.error(new IllegalStateException(
                        "Python Research Service is required for analysis but returned no report")))
                .map(result -> researchAgentReportMapper.toAnalysisReport(result, request.language()))
                .doOnNext(report -> log.info("research_agent_complete runId={} status=OK latencyMs={}",
                        runId, elapsedMillis(startedAtNanos)))
                .doOnError(error -> log.warn("research_agent_failed runId={} status=ERROR latencyMs={} errorCode={}",
                        runId, elapsedMillis(startedAtNanos), error.getClass().getSimpleName()))
                .flux();
    }

    private long elapsedMillis(long startedAtNanos) {
        return (System.nanoTime() - startedAtNanos) / 1_000_000;
    }

    private String resolveProvider(String model) {
        return model != null && !model.isBlank()
                ? model.trim().toLowerCase(Locale.ROOT)
                : providerCredentialValidator.defaultProvider();
    }
}
