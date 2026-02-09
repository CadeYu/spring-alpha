package com.springalpha.backend.service;

import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.service.FinancialDataService;
import com.springalpha.backend.service.strategy.AiAnalysisStrategy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.*;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class FinancialAnalysisService {

    private static final Logger log = LoggerFactory.getLogger(FinancialAnalysisService.class);
    private final SecService secService;
    private final com.springalpha.backend.service.rag.VectorRagService vectorRagService;
    private final FinancialDataService financialDataService;
    private final Map<String, AiAnalysisStrategy> strategies;

    @Value("${app.ai-provider:enhanced-mock}")
    private String activeProvider;

    public FinancialAnalysisService(
            SecService secService,
            com.springalpha.backend.service.rag.VectorRagService vectorRagService,
            FinancialDataService financialDataService,
            List<AiAnalysisStrategy> strategyList) {
        this.secService = secService;
        this.vectorRagService = vectorRagService;
        this.financialDataService = financialDataService;
        this.strategies = strategyList.stream()
                .collect(Collectors.toMap(AiAnalysisStrategy::getName, Function.identity()));

        log.info("🎯 Loaded AI strategies: {}", this.strategies.keySet());
    }

    /**
     * Get list of available AI models
     */
    public List<String> getAvailableModels() {
        return new ArrayList<>(strategies.keySet());
    }

    /**
     * Get the default model name from configuration
     */
    public String getDefaultModel() {
        return activeProvider;
    }

    /**
     * Analyze stock using the new Analysis Contract system with model selection.
     * 
     * @param ticker Stock ticker
     * @param lang   Language for analysis
     * @param model  Model to use (empty string means use default)
     */
    public Flux<AnalysisReport> analyzeStock(String ticker, String lang, String model) {
        return Mono.fromCallable(() -> {
            log.info("📊 Starting financial analysis for: {} (lang: {}, model: {})",
                    ticker, lang, model.isEmpty() ? activeProvider : model);

            // Step 1: Get financial facts
            FinancialFacts facts = financialDataService.getFinancialFacts(ticker);
            if (facts == null) {
                throw new IllegalArgumentException("Ticker not supported: " + ticker);
            }

            log.info("✅ Retrieved financial facts for {}: Revenue YoY = {}",
                    ticker, facts.getRevenueYoY());

            return facts;
        })
                .flatMapMany(facts ->
                // Step 2: Get SEC text content (async)
                secService.getLatest10KContent(ticker)
                        .flatMapMany(content ->
                        // Offload blocking Vector RAG operations to boundedElastic scheduler
                        Mono.fromCallable(() -> {
                            log.info("📄 Retrieved SEC filing, length: {}. Running Vector RAG...",
                                    content.length());

                            // Step 3: Store document in Vector DB if not already present
                            if (!vectorRagService.hasDocuments(ticker)) {
                                log.info("📥 First time processing {}, storing in vector DB...", ticker);
                                vectorRagService.storeDocument(ticker, content);
                            } else {
                                log.info("✅ {} already in vector DB, skipping storage", ticker);
                            }

                            // Step 4: Retrieve text evidence using Vector RAG (semantic search)
                            String mdnaQuery = "Management Discussion Analysis revenue drivers business performance growth";
                            String riskQuery = "Risk Factors uncertainties challenges regulatory competition";

                            String mdna = vectorRagService.retrieveRelevantContext(ticker, mdnaQuery);
                            String risks = vectorRagService.retrieveRelevantContext(ticker, riskQuery);

                            Map<String, String> textEvidence = new HashMap<>();
                            textEvidence.put("MD&A", mdna);
                            textEvidence.put("Risk Factors", risks);
                            return textEvidence;
                        })
                                .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic())
                                .flatMapMany(textEvidence -> {

                                    // Step 5: Build Analysis Contract
                                    List<String> analysisTasks = Arrays.asList(
                                            "Explain the primary drivers of revenue growth",
                                            "Analyze the sustainability of margin changes",
                                            "Summarize the most material risk factors");

                                    AnalysisContract contract = AnalysisContract.builder()
                                            .ticker(ticker)
                                            .companyName(facts.getCompanyName())
                                            .period(facts.getPeriod())
                                            .financialFacts(facts)
                                            .textEvidence(textEvidence)
                                            .analysisTasks(analysisTasks)
                                            .language(lang != null ? lang : "en")
                                            .build();

                                    // Step 6: Select strategy (use model param if provided)
                                    AiAnalysisStrategy strategy = selectStrategy(model);

                                    log.info("🚀 Executing analysis with strategy: {}", strategy.getName());

                                    // Step 7: Execute analysis
                                    return strategy.analyze(contract, lang)
                                            .onErrorResume(e -> {
                                                log.error("❌ Strategy [{}] failed: {}. Falling back to enhanced-mock",
                                                        strategy.getName(), e.getMessage());
                                                AiAnalysisStrategy fallback = strategies.get("enhanced-mock");
                                                return fallback != null
                                                        ? fallback.analyze(contract, lang)
                                                        : Flux.error(e);
                                            });
                                })));
    }

    /**
     * Select strategy based on model parameter or default config
     */
    private AiAnalysisStrategy selectStrategy(String model) {
        // Use provided model if not empty, otherwise use default
        String targetModel = (model != null && !model.isEmpty()) ? model : activeProvider;

        AiAnalysisStrategy strategy = strategies.get(targetModel);

        if (strategy == null) {
            log.warn("⚠️ Strategy [{}] not found, available: {}. Using enhanced-mock",
                    targetModel, strategies.keySet());
            strategy = strategies.get("enhanced-mock");
        }

        if (strategy == null) {
            throw new IllegalStateException("No strategies available!");
        }

        return strategy;
    }
}
