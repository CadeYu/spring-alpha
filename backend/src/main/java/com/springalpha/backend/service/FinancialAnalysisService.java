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
    private final RagService ragService;
    private final FinancialDataService financialDataService;
    private final Map<String, AiAnalysisStrategy> strategies;

    @Value("${app.ai-provider:enhanced-mock}")
    private String activeProvider;

    public FinancialAnalysisService(
            SecService secService,
            RagService ragService,
            FinancialDataService financialDataService,
            List<AiAnalysisStrategy> strategyList) {
        this.secService = secService;
        this.ragService = ragService;
        this.financialDataService = financialDataService;
        this.strategies = strategyList.stream()
                .collect(Collectors.toMap(AiAnalysisStrategy::getName, Function.identity()));

        log.info("🎯 Loaded AI strategies: {}", this.strategies.keySet());
    }

    /**
     * Analyze stock using the new Analysis Contract system.
     * This method bridges the old API (ticker + lang) with the new contract-based
     * approach.
     */
    public Flux<AnalysisReport> analyzeStock(String ticker, String lang) {
        return Mono.fromCallable(() -> {
            log.info("📊 Starting financial analysis for: {} (lang: {})", ticker, lang);

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
                        .flatMapMany(content -> {
                            log.info("📄 Retrieved SEC filing, length: {}. Running RAG extraction...",
                                    content.length());

                            // Step 3: Extract text evidence using RAG
                            String mdnaQuery = "Management Discussion and Analysis, Revenue drivers, Business performance";
                            String riskQuery = "Risk Factors, Uncertainties, Challenges";

                            String mdna = ragService.retrieveRelevantContext(content, mdnaQuery);
                            String risks = ragService.retrieveRelevantContext(content, riskQuery);

                            Map<String, String> textEvidence = new HashMap<>();
                            textEvidence.put("MD&A", mdna);
                            textEvidence.put("Risk Factors", risks);

                            // Step 4: Build Analysis Contract
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

                            // Step 5: Select strategy
                            AiAnalysisStrategy strategy = selectStrategy();

                            log.info("🚀 Executing analysis with strategy: {}", strategy.getName());

                            // Step 6: Execute analysis
                            return strategy.analyze(contract, lang)
                                    .onErrorResume(e -> {
                                        log.error("❌ Strategy [{}] failed: {}. Falling back to enhanced-mock",
                                                strategy.getName(), e.getMessage());
                                        AiAnalysisStrategy fallback = strategies.get("enhanced-mock");
                                        return fallback != null
                                                ? fallback.analyze(contract, lang)
                                                : Flux.error(e);
                                    });
                        }));
    }

    private AiAnalysisStrategy selectStrategy() {
        AiAnalysisStrategy strategy = strategies.get(activeProvider);

        if (strategy == null) {
            log.warn("⚠️ Strategy [{}] not found, using enhanced-mock", activeProvider);
            strategy = strategies.get("enhanced-mock");
        }

        if (strategy == null) {
            throw new IllegalStateException("No strategies available!");
        }

        return strategy;
    }
}
