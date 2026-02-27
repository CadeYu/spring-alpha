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
     * 核心业务方法：执行股票财务分析
     * <p>
     * 这是一个典型的 **Agentic Workflow (代理工作流)**，虽然用户只输入了一个 Ticker，
     * 但后端充当了“分析师代理”，自动完成了以下复杂步骤：
     * 1. **获取硬数据 (Quantitative)**: 从 FMP API 获取精确的财务指标 (Revenue, Profit 等)。
     * 2. **获取软证据 (Qualitative)**: 从 SEC 10-K 文件中 RAG 检索相关的文本段落 (MD&A, Risk
     * Factors)。
     * 3. **构建混合上下文 (Hybrid Context)**: 将 "JSON 数据" + "Markdown 文本" 拼装成巨大的 Prompt。
     * 4. **AI 推理 (Reasoning)**: 调用大模型 (Groq/Llama3) 生成最终的分析报告。
     *
     * @param ticker 股票代码 (e.g., AAPL)
     * @param lang   分析语言 (en/zh)
     * @param model  指定模型 (可选)
     */
    public Flux<AnalysisReport> analyzeStock(String ticker, String lang, String model) {
        return Mono.fromCallable(() -> {
            log.info("📊 Starting financial analysis for: {} (lang: {}, model: {})",
                    ticker, lang, model.isEmpty() ? activeProvider : model);

            // Step 1: 获取财务“硬”数据 (Financial Facts)
            // 来源：FMP API (JSON)
            // 作用：提供精确的数值骨架，防止 AI 在数字上产生幻觉。
            FinancialFacts facts = financialDataService.getFinancialFacts(ticker);
            if (facts == null) {
                log.error("❌ Failed to retrieve financial facts for {}", ticker);
                throw new RuntimeException("Unable to retrieve financial data for: " + ticker
                        + ". This could be due to network issues or invalid ticker.");
            }

            log.info("✅ Retrieved financial facts for {}: Revenue YoY = {}",
                    ticker, facts.getRevenueYoY());

            return facts;
        })
                .flatMapMany(facts -> {
                    // Step 2: 获取 SEC 10-K + RAG 文本 (可降级)
                    // 如果 SEC/Gemini Embedding 失败，不阻塞分析，降级为仅 FMP 数据模式
                    Mono<Map<String, String>> textEvidenceMono = secService.getLatest10KContent(ticker)
                            .flatMap(content -> Mono.fromCallable(() -> {
                                log.info("📄 Retrieved SEC filing, length: {}. Running Vector RAG...",
                                        content.length());

                                // Step 3: 向量化存储 (Vector Storage)
                                if (!vectorRagService.hasDocuments(ticker)) {
                                    log.info("📥 First time processing {}, storing in vector DB...", ticker);
                                    vectorRagService.storeDocument(ticker, content);
                                } else {
                                    log.info("✅ {} already in vector DB, skipping storage", ticker);
                                }

                                // Step 4: 语义检索 (Semantic Search / RAG)
                                String mdnaQuery = "Management Discussion Analysis revenue drivers business performance growth";
                                String riskQuery = "Risk Factors uncertainties challenges regulatory competition";

                                String mdna = vectorRagService.retrieveRelevantContext(ticker, mdnaQuery);
                                String risks = vectorRagService.retrieveRelevantContext(ticker, riskQuery);

                                Map<String, String> textEvidence = new HashMap<>();
                                textEvidence.put("MD&A", mdna);
                                textEvidence.put("Risk Factors", risks);
                                return textEvidence;
                            }).subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic()))
                            // 整个 SEC+RAG 链路 90 秒超时
                            .timeout(java.time.Duration.ofSeconds(90))
                            // 降级：SEC 或 RAG 失败时，使用空 textEvidence 继续分析
                            .onErrorResume(e -> {
                                log.warn("⚠️ SEC/RAG pipeline failed, degrading to FMP-only mode: {}", e.getMessage());
                                return Mono.just(new HashMap<>());
                            });

                    return textEvidenceMono.flatMapMany(textEvidence -> {
                        // Step 5: 构建分析契约 (Analysis Contract)
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

                        // Step 6: 选择策略 (Strategy Selection)
                        AiAnalysisStrategy strategy = selectStrategy(model);

                        log.info("🚀 Executing analysis with strategy: {} (RAG: {})",
                                strategy.getName(), textEvidence.isEmpty() ? "DISABLED" : "ENABLED");

                        // Step 7: 执行分析 (Execution)
                        return strategy.analyze(contract, lang)
                                .onErrorResume(e -> {
                                    log.error("❌ Strategy [{}] failed: {}. Falling back to enhanced-mock",
                                            strategy.getName(), e.getMessage());
                                    AiAnalysisStrategy fallback = strategies.get("enhanced-mock");
                                    return fallback != null
                                            ? fallback.analyze(contract, lang)
                                            : Flux.error(e);
                                });
                    });
                });
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
