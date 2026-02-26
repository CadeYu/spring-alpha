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
                .flatMapMany(facts ->
                // Step 2: 获取 SEC 10-K 文本内容 (Async)
                // 来源：SEC EDGAR (HTML -> Markdown)
                secService.getLatest10KContent(ticker)
                        .flatMapMany(content ->
                        // 将阻塞的 Vector RAG 操作放入 boundedElastic 线程池，避免阻塞 Netty IO 线程
                        Mono.fromCallable(() -> {
                            log.info("📄 Retrieved SEC filing, length: {}. Running Vector RAG...",
                                    content.length());

                            // Step 3: 向量化存储 (Vector Storage)
                            // 如果这是第一次查该股票，将其切片 (Chunking) 并存入 PGVector 数据库。
                            if (!vectorRagService.hasDocuments(ticker)) {
                                log.info("📥 First time processing {}, storing in vector DB...", ticker);
                                vectorRagService.storeDocument(ticker, content);
                            } else {
                                log.info("✅ {} already in vector DB, skipping storage", ticker);
                            }

                            // Step 4: 语义检索 (Semantic Search / RAG)
                            // 这里体现了 "Agent" 的隐式意图 (Implicit Intent)。
                            // 用户没问 "为什么营收增长"，但系统自动生成了这些 Query 去向量库里找答案。

                            // Query 1: 关注管理层讨论 (MD&A)、营收驱动因素、业务表现
                            String mdnaQuery = "Management Discussion Analysis revenue drivers business performance growth";
                            // Query 2: 关注风险因素、不确定性、监管挑战
                            String riskQuery = "Risk Factors uncertainties challenges regulatory competition";

                            // 检索 Top-K 最相关的文本片段 (Markdown 格式)
                            String mdna = vectorRagService.retrieveRelevantContext(ticker, mdnaQuery);
                            String risks = vectorRagService.retrieveRelevantContext(ticker, riskQuery);

                            Map<String, String> textEvidence = new HashMap<>();
                            textEvidence.put("MD&A", mdna);
                            textEvidence.put("Risk Factors", risks);
                            return textEvidence;
                        })
                                .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic())
                                .flatMapMany(textEvidence -> {

                                    // Step 5: 构建分析契约 (Analysis Contract)
                                    // 这里定义了 AI 的"任务清单"。不管用户说什么，我们都强制 AI 完成这三项核心分析。
                                    List<String> analysisTasks = Arrays.asList(
                                            "Explain the primary drivers of revenue growth", // 解释营收增长的主因
                                            "Analyze the sustainability of margin changes", // 分析利润率变化的持续性
                                            "Summarize the most material risk factors"); // 总结最核心的风险

                                    AnalysisContract contract = AnalysisContract.builder()
                                            .ticker(ticker)
                                            .companyName(facts.getCompanyName())
                                            .period(facts.getPeriod())
                                            .financialFacts(facts) // 注入 JSON 数据 (骨架)
                                            .textEvidence(textEvidence) // 注入 RAG 文本 (血肉)
                                            .analysisTasks(analysisTasks)
                                            .language(lang != null ? lang : "en")
                                            .build();

                                    // Step 6: 选择策略 (Strategy Selection)
                                    // 决定用哪个模型 (Groq, OpenAI, Gemini...)
                                    AiAnalysisStrategy strategy = selectStrategy(model);

                                    log.info("🚀 Executing analysis with strategy: {}", strategy.getName());

                                    // Step 7: 执行分析 (Execution)
                                    // 发送最终 Prompt 给 LLM，并流式返回结果
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
