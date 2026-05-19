package com.springalpha.backend.service;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.ResearchTaskType;
import com.springalpha.backend.service.provider.ProviderCredentialValidator;
import com.springalpha.backend.service.research.ResearchAgentClient;
import com.springalpha.backend.service.research.ResearchAgentReportMapper;
import com.springalpha.backend.service.research.ResearchAgentRequest;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.UUID;

@Slf4j
@Service
public class FinancialAnalysisService {
    private static final int DEFAULT_AGENT_FILING_MAX_CHARS = 120_000;
    private static final String FILING_TRUNCATION_MARKER = "... [Truncated for live analysis]";

    private final SecService secService;
    private final ProviderCredentialValidator providerCredentialValidator;
    private final ResearchAgentClient researchAgentClient;
    private final ResearchAgentReportMapper researchAgentReportMapper;
    private final int agentFilingMaxChars;

    @Autowired
    public FinancialAnalysisService(
            SecService secService,
            ProviderCredentialValidator providerCredentialValidator,
            ResearchAgentClient researchAgentClient,
            ResearchAgentReportMapper researchAgentReportMapper,
            @Value("${app.research-service.agent-filing-max-chars:" + DEFAULT_AGENT_FILING_MAX_CHARS + "}") int agentFilingMaxChars) {
        this.secService = secService;
        this.providerCredentialValidator = providerCredentialValidator;
        this.researchAgentClient = researchAgentClient;
        this.researchAgentReportMapper = researchAgentReportMapper;
        this.agentFilingMaxChars = Math.max(1, agentFilingMaxChars);
    }

    public FinancialAnalysisService(
            SecService secService,
            ProviderCredentialValidator providerCredentialValidator,
            ResearchAgentClient researchAgentClient,
            ResearchAgentReportMapper researchAgentReportMapper) {
        this(
                secService,
                providerCredentialValidator,
                researchAgentClient,
                researchAgentReportMapper,
                DEFAULT_AGENT_FILING_MAX_CHARS);
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
        return analyzeStock(ticker, lang, model, null, providerApiKey, taskType);
    }

    public Flux<AnalysisReport> analyzeStock(
            String ticker,
            String lang,
            String model,
            String llmModel,
            String providerApiKey,
            ResearchTaskType taskType) {
        String provider = resolveProvider(model);
        String selectedLlmModel = normalizeLlmModel(llmModel);
        String language = lang != null && !lang.isBlank() ? lang : "en";
        String normalizedTicker = ticker.toUpperCase(Locale.ROOT);
        ResearchTaskType effectiveTaskType = taskType != null ? taskType : ResearchTaskType.LATEST_EARNINGS_READOUT;

        return providerCredentialValidator.validate(provider, providerApiKey)
                .thenMany(Mono.fromCallable(() -> agentFacts(normalizedTicker))
                        .subscribeOn(Schedulers.boundedElastic())
                        .flatMapMany(facts -> secService.getLatestFilingContent(normalizedTicker)
                        .subscribeOn(Schedulers.boundedElastic())
                        .flatMapMany(filingText -> runResearchAgent(normalizedTicker, language, provider,
                                selectedLlmModel,
                                providerCredentialValidator.resolveApiKey(provider, providerApiKey),
                                effectiveTaskType, filingText, facts))));
    }

    private Flux<AnalysisReport> runResearchAgent(
            String ticker,
            String language,
            String provider,
            String llmModel,
            String providerApiKey,
            ResearchTaskType taskType,
            String filingText,
            Map<String, Object> facts) {
        String runId = "run_" + UUID.randomUUID();
        long startedAtNanos = System.nanoTime();
        ResearchAgentRequest request = new ResearchAgentRequest(
                runId,
                ticker,
                taskType,
                language,
                2,
                provider,
                llmModel,
                providerApiKey,
                facts,
                List.of(new ResearchAgentRequest.FilingDocument(
                        ticker,
                        "10-Q",
                        null,
                        null,
                        capFilingText(filingText))));

        log.info("research_agent_start runId={} ticker={} taskType={} provider={} llmModel={}",
                runId, ticker, taskType, provider, llmModel);

        return researchAgentClient.run(request)
                .switchIfEmpty(Mono.error(new IllegalStateException(
                        "Python Research Service is required for analysis but returned no report")))
                .doOnNext(result -> log.info(
                        "research_agent_result runId={} status={} degradedReasons={} latencyMs={}",
                        runId,
                        result.status(),
                        safeLogMessage(String.join("; ",
                                result.degradedReasons() == null ? List.of() : result.degradedReasons())),
                        elapsedMillis(startedAtNanos)))
                .map(result -> researchAgentReportMapper.toAnalysisReport(result, request.language()))
                .doOnNext(report -> log.info("research_agent_complete runId={} sourceStatus={} latencyMs={}",
                        runId,
                        report.getSourceContext() == null ? "UNKNOWN" : report.getSourceContext().getStatus(),
                        elapsedMillis(startedAtNanos)))
                .doOnError(error -> log.warn("research_agent_failed runId={} status=ERROR latencyMs={} errorCode={} message={}",
                        runId, elapsedMillis(startedAtNanos), error.getClass().getSimpleName(),
                        safeLogMessage(error.getMessage())))
                .flux();
    }

    private Map<String, Object> agentFacts(String ticker) {
        if (secService.getFinancialDataService() == null) {
            return Map.of();
        }
        try {
            var financialFacts = secService.getFinancialDataService().getFinancialFacts(ticker, "quarterly");
            if (financialFacts == null) {
                return Map.of();
            }
            Map<String, Object> facts = new LinkedHashMap<>();
            putIfPresent(facts, "company_name", financialFacts.getCompanyName());
            putIfPresent(facts, "companyName", financialFacts.getCompanyName());
            putIfPresent(facts, "period", financialFacts.getPeriod());
            putIfPresent(facts, "filing_date", financialFacts.getFilingDate());
            putIfPresent(facts, "filingDate", financialFacts.getFilingDate());
            putIfPresent(facts, "currency", financialFacts.getCurrency());
            putIfPresent(facts, "market_sector", financialFacts.getMarketSector());
            putIfPresent(facts, "marketSector", financialFacts.getMarketSector());
            putIfPresent(facts, "market_industry", financialFacts.getMarketIndustry());
            putIfPresent(facts, "marketIndustry", financialFacts.getMarketIndustry());
            putIfPresent(facts, "market_security_type", financialFacts.getMarketSecurityType());
            putIfPresent(facts, "marketSecurityType", financialFacts.getMarketSecurityType());
            putIfPresent(facts, "business_summary", financialFacts.getMarketBusinessSummary());
            putIfPresent(facts, "businessSummary", financialFacts.getMarketBusinessSummary());
            putIfPresent(facts, "market_business_summary", financialFacts.getMarketBusinessSummary());
            putIfPresent(facts, "marketBusinessSummary", financialFacts.getMarketBusinessSummary());
            return facts;
        } catch (RuntimeException error) {
            log.warn("agent_facts_unavailable ticker={} errorCode={}", ticker, error.getClass().getSimpleName());
            return Map.of();
        }
    }

    private void putIfPresent(Map<String, Object> facts, String key, String value) {
        if (value != null && !value.isBlank()) {
            facts.put(key, value);
        }
    }

    private long elapsedMillis(long startedAtNanos) {
        return (System.nanoTime() - startedAtNanos) / 1_000_000;
    }

    private String safeLogMessage(String message) {
        if (message == null || message.isBlank()) {
            return "";
        }
        String normalized = message.replaceAll("\\s+", " ").trim();
        return normalized.length() > 240 ? normalized.substring(0, 240) : normalized;
    }

    private String resolveProvider(String model) {
        return model != null && !model.isBlank()
                ? model.trim().toLowerCase(Locale.ROOT)
                : providerCredentialValidator.defaultProvider();
    }

    private String normalizeLlmModel(String llmModel) {
        return llmModel != null && !llmModel.isBlank() ? llmModel.trim() : null;
    }

    private String capFilingText(String filingText) {
        if (filingText.length() <= agentFilingMaxChars) {
            return filingText;
        }
        int contentLimit = Math.max(1, agentFilingMaxChars - FILING_TRUNCATION_MARKER.length());
        return filingText.substring(0, contentLimit).stripTrailing() + FILING_TRUNCATION_MARKER;
    }
}
