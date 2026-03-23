package com.springalpha.backend.service;

import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.contract.CompanyProfile;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.service.FinancialDataService;
import com.springalpha.backend.financial.service.UnsupportedTickerCategoryException;
import com.springalpha.backend.service.profile.CompanyProfileSnapshotService;
import com.springalpha.backend.service.signals.BusinessSignalSnapshotService;
import com.springalpha.backend.service.strategy.AiAnalysisStrategy;
import com.springalpha.backend.service.strategy.CredentialValidatingStrategy;
import com.springalpha.backend.service.strategy.ProviderAuthenticationException;
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
    private static final String REPORT_TYPE_QUARTERLY = "quarterly";
    private final SecService secService;
    private final com.springalpha.backend.service.rag.VectorRagService vectorRagService;
    private final FinancialDataService financialDataService;
    private final BusinessSignalSnapshotService businessSignalSnapshotService;
    private final CompanyProfileSnapshotService companyProfileSnapshotService;
    private final Map<String, AiAnalysisStrategy> strategies;
    private static final String DIMENSION_MISMATCH_MARKER = "different vector dimensions";

    @Value("${app.ai-provider:enhanced-mock}")
    private String activeProvider;

    public FinancialAnalysisService(
            SecService secService,
            com.springalpha.backend.service.rag.VectorRagService vectorRagService,
            FinancialDataService financialDataService,
            BusinessSignalSnapshotService businessSignalSnapshotService,
            CompanyProfileSnapshotService companyProfileSnapshotService,
            List<AiAnalysisStrategy> strategyList) {
        this.secService = secService;
        this.vectorRagService = vectorRagService;
        this.financialDataService = financialDataService;
        this.businessSignalSnapshotService = businessSignalSnapshotService;
        this.companyProfileSnapshotService = companyProfileSnapshotService;
        this.strategies = strategyList.stream()
                .collect(Collectors.toMap(AiAnalysisStrategy::getName, Function.identity()));

        log.info("🎯 Loaded AI strategies: {}", this.strategies.keySet());
    }

    /**
     * Get list of available AI models
     */
    public List<String> getAvailableModels() {
        return strategies.keySet().stream()
                .filter(name -> !"enhanced-mock".equals(name))
                .sorted()
                .toList();
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
     * 2. **获取软证据 (Qualitative)**: 从最新季度 SEC filing 中 RAG 检索相关的文本段落 (MD&A, Risk
     * Factors)。
     * 3. **构建混合上下文 (Hybrid Context)**: 将 "JSON 数据" + "Markdown 文本" 拼装成巨大的 Prompt。
     * 4. **AI 推理 (Reasoning)**: 调用大模型 (Groq/Llama3) 生成最终的分析报告。
     *
     * @param ticker 股票代码 (e.g., AAPL)
     * @param lang   分析语言 (en/zh)
     * @param model  指定模型 (可选)
     */
    public Flux<AnalysisReport> analyzeStock(String ticker, String lang, String model, String openAiApiKey) {
        AiAnalysisStrategy strategy = selectStrategy(model);
        Mono<Void> credentialCheck = Mono.empty();
        if (strategy instanceof CredentialValidatingStrategy validatingStrategy) {
            credentialCheck = validatingStrategy.validateCredentials(
                    "openai".equals(strategy.getName()) ? openAiApiKey : null);
        }

        Mono<FinancialFacts> factsMono = Mono.fromCallable(() -> {
            log.info("📊 Starting quarterly financial analysis for: {} (lang: {}, model: {})",
                    ticker, lang, model.isEmpty() ? activeProvider : model);

            // Step 1: 获取财务“硬”数据 (Financial Facts)
            // 来源：季度财务数据服务
            // 作用：提供精确的数值骨架，防止 AI 在数字上产生幻觉。
            FinancialFacts facts = financialDataService.getFinancialFacts(ticker, REPORT_TYPE_QUARTERLY);
            if (facts == null) {
                log.error("❌ Failed to retrieve financial facts for {}", ticker);
                throw new RuntimeException("Unable to retrieve financial data for: " + ticker
                        + ". This ticker may be unsupported, temporarily unavailable from SEC, or blocked by the configured market-data providers.");
            }
            if ("unsupported_reit".equalsIgnoreCase(facts.getDashboardMode())) {
                String categoryMessage = "zh".equalsIgnoreCase(lang)
                        ? String.format("%s 被识别为 REIT / Trust 类型，目前不在普通经营性公司财报分析范围内。", ticker.toUpperCase())
                        : String.format("%s is categorized as a REIT / trust-like issuer and is currently outside the standard operating-company analysis flow.",
                                ticker.toUpperCase());
                throw new UnsupportedTickerCategoryException(
                        ticker.toUpperCase(),
                        facts.getDashboardMode(),
                        categoryMessage);
            }

            log.info("✅ Retrieved financial facts for {}: Revenue YoY = {}",
                    ticker, facts.getRevenueYoY());

            return facts;
        })
                .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic())
                .hide();

        return credentialCheck.thenMany(factsMono.flatMapMany(facts -> {
                    boolean isZh = "zh".equalsIgnoreCase(lang);
                    // Step 2: 获取最新季度 SEC filing + RAG 文本 (可降级)
                    // 如果 SEC/向量检索链路失败，不阻塞分析，降级为仅 facts 驱动的分析模式
                    Mono<SourceEvidenceBundle> textEvidenceMono = secService.getLatestFilingContent(
                            ticker)
                            .flatMap(content -> Mono.fromCallable(() -> {
                                log.info("📄 Retrieved SEC filing, length: {}.", content.length());

                                Map<String, String> textEvidence = new HashMap<>();
                                String degradedMessage = null;
                                boolean hasCachedDocuments = false;

                                // 快速路径：如果向量数据库里已有该 Ticker 的文档（非首次查询），直接语义检索
                                try {
                                    hasCachedDocuments = vectorRagService.hasDocuments(ticker);
                                } catch (Exception e) {
                                    if (isVectorDimensionMismatch(e)) {
                                        log.warn("⚠️ Vector dimension mismatch detected during cache check for {}, resetting cached vectors",
                                                ticker);
                                        vectorRagService.deleteDocuments(ticker);
                                        degradedMessage = vectorDimensionResetMessage(isZh);
                                    } else {
                                        log.warn("⚠️ Vector cache check failed for {}: {}", ticker, e.getMessage());
                                        degradedMessage = semanticRetrievalFailedMessage(isZh);
                                    }
                                }

                                if (hasCachedDocuments) {
                                    log.info("✅ {} already in vector DB, using semantic search", ticker);
                                    try {
                                        String mdnaQuery = "Management Discussion Analysis revenue drivers business performance growth";
                                        String riskQuery = "Risk Factors uncertainties challenges regulatory competition";
                                        String mdna = vectorRagService.retrieveRelevantContext(ticker, mdnaQuery);
                                        String risks = vectorRagService.retrieveRelevantContext(ticker, riskQuery);
                                        textEvidence.put("MD&A", mdna);
                                        textEvidence.put("Risk Factors", risks);
                                        log.info("✅ Vector RAG completed successfully for {}", ticker);
                                        return new SourceEvidenceBundle(textEvidence, true, null);
                                    } catch (Exception e) {
                                        if (isVectorDimensionMismatch(e)) {
                                            log.warn("⚠️ Vector dimension mismatch for {}, resetting cached vectors", ticker);
                                            vectorRagService.deleteDocuments(ticker);
                                            degradedMessage = vectorDimensionResetMessage(isZh);
                                        } else {
                                            degradedMessage = semanticRetrievalFailedMessage(isZh);
                                        }
                                        log.warn("⚠️ Vector retrieval failed, using raw text: {}", e.getMessage());
                                    }
                                }

                                // 慢速路径 / 降级路径：首次查询或检索失败时
                                // 直接截取原始 filing 文本作为上下文（不等待 Embedding）
                                int maxLen = Math.min(content.length(), 12000);
                                String rawContext = content.substring(0, maxLen);
                                textEvidence.put("MD&A", rawContext);
                                textEvidence.put("Risk Factors", "");
                                log.info("📝 Using raw text ({} chars) for {} — vectors will be cached in background",
                                        maxLen, ticker);

                                // 🔥 Fire-and-Forget：在后台异步存储向量，下次查询就能用语义检索了
                                final String contentCopy = content;
                                if (vectorRagService.shouldStartBackgroundIngestion(ticker, contentCopy)) {
                                    reactor.core.publisher.Mono.fromRunnable(() -> {
                                        try {
                                            log.info("🔄 [Background] Starting vector ingestion for {}", ticker);
                                            vectorRagService.storeDocument(ticker, contentCopy);
                                            log.info("✅ [Background] Vector ingestion completed for {}", ticker);
                                        } catch (Exception e) {
                                            log.warn("⚠️ [Background] Vector ingestion failed for {}: {}", ticker,
                                                    e.getMessage());
                                        }
                                            }).subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic())
                                            .subscribe(); // Fire-and-forget!
                                }

                                return new SourceEvidenceBundle(textEvidence, false,
                                        degradedMessage != null ? degradedMessage
                                                : semanticGroundingUnavailableMessage(isZh));
                            }).subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic()))
                            // 整个 SEC+RAG 链路 30 秒超时（大幅缩短，因为不再等待 Embedding）
                            .timeout(java.time.Duration.ofSeconds(30))
                            // 降级：SEC 失败时，使用空 textEvidence 继续分析
                            .onErrorResume(e -> {
                                log.warn("⚠️ SEC/RAG pipeline failed, degrading to facts-only mode: {}", e.getMessage());
                                return Mono.just(new SourceEvidenceBundle(
                                        new HashMap<>(),
                                        false,
                                        secRetrievalFailedMessage(isZh)));
                            });

                    Flux<AnalysisReport> analysisFlux = textEvidenceMono.flatMapMany(sourceEvidence -> {
                        BusinessSignals businessSignals = businessSignalSnapshotService.getOrExtract(
                                ticker,
                                REPORT_TYPE_QUARTERLY,
                                facts,
                                sourceEvidence.textEvidence(),
                                sourceEvidence.evidenceAvailable());
                        CompanyProfile companyProfile = companyProfileSnapshotService.getOrExtract(
                                ticker,
                                REPORT_TYPE_QUARTERLY,
                                facts,
                                businessSignals,
                                sourceEvidence.textEvidence());

                        // Step 5: 构建分析契约 (Analysis Contract)
                        List<String> analysisTasks = Arrays.asList(
                                "Explain the primary drivers of revenue growth",
                                "Analyze the sustainability of margin changes",
                                "Summarize the most material risk factors");

                        AnalysisContract contract = AnalysisContract.builder()
                                .ticker(ticker)
                                .companyName(facts.getCompanyName())
                                .period(facts.getPeriod())
                                .reportType(REPORT_TYPE_QUARTERLY)
                                .financialFacts(facts)
                                .textEvidence(sourceEvidence.textEvidence())
                                .businessSignals(businessSignals)
                                .companyProfile(companyProfile)
                                .analysisTasks(analysisTasks)
                                .language(lang != null ? lang : "en")
                                .evidenceAvailable(sourceEvidence.evidenceAvailable())
                                .evidenceStatusMessage(sourceEvidence.statusMessage())
                                .build();

                        log.info("🚀 Executing analysis with strategy: {} (RAG: {})",
                                strategy.getName(), sourceEvidence.evidenceAvailable() ? "ENABLED" : "DEGRADED");

                        // Step 7: 执行分析 (Execution)
                        return strategy.analyze(contract, lang,
                                "openai".equals(strategy.getName()) ? openAiApiKey : null)
                                .onErrorResume(e -> {
                                    if (containsProviderAuthenticationException(e)) {
                                        return Flux.error(e);
                                    }
                                    log.error("❌ Strategy [{}] failed: {}. Falling back to enhanced-mock",
                                            strategy.getName(), e.getMessage());
                                    AiAnalysisStrategy fallback = strategies.get("enhanced-mock");
                                    return fallback != null
                                            ? fallback.analyze(contract, lang, null)
                                            : Flux.error(e);
                                });
                    });

                    // 发送一个初始的骨架报告，防止 Next.js/Nginx 等代理层因为 30 秒都没有收到数据而发生 Read Timeout 504 错误
                    AnalysisReport initialSkeleton = AnalysisReport.builder()
                            .currency(facts.getCurrency())
                            .companyName(facts.getCompanyName())
                            .reportType(REPORT_TYPE_QUARTERLY)
                            .period(facts.getPeriod())
                            .filingDate(facts.getFilingDate())
                            .sourceContext(AnalysisReport.SourceContext.builder()
                                    .status("UNAVAILABLE")
                                    .message(isZh ? "分析正在准备来源证据。" : "Analysis is preparing source evidence.")
                                    .build())
                            .build();

                    return Flux.concat(Mono.just(initialSkeleton), analysisFlux);
                }));
    }

    private boolean isVectorDimensionMismatch(Throwable error) {
        if (error == null || error.getMessage() == null) {
            return false;
        }
        return error.getMessage().contains(DIMENSION_MISMATCH_MARKER);
    }

    private boolean containsProviderAuthenticationException(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof ProviderAuthenticationException) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private String vectorDimensionResetMessage(boolean isZh) {
        return isZh
                ? "检测到 embedding 维度变化，SEC 向量缓存已重建。本次改用降级模式运行，暂不展示可验证引用。"
                : "Cached SEC vectors were rebuilt after an embedding dimension change. This run used fallback raw filing text, so source verification is temporarily unavailable.";
    }

    private String semanticRetrievalFailedMessage(boolean isZh) {
        return isZh
                ? "本次 SEC 语义检索失败，因此暂不展示可验证引用。"
                : "Semantic SEC retrieval failed for this run, so citations are unavailable.";
    }

    private String semanticGroundingUnavailableMessage(boolean isZh) {
        return isZh
                ? "SEC 文件已获取，但语义 grounding 尚未就绪。本次以降级模式运行，因此不展示可验证引用。"
                : "SEC filing was available, but semantic grounding was not ready yet. This run is operating without verifiable citations.";
    }

    private String secRetrievalFailedMessage(boolean isZh) {
        return isZh
                ? "本次未能获取 SEC 文件，因此报告仅基于财务数据生成，无法提供可验证引用。"
                : "SEC filing retrieval failed for this run, so the report uses financial data only and cannot provide verifiable source citations.";
    }

    private record SourceEvidenceBundle(Map<String, String> textEvidence, boolean evidenceAvailable,
            String statusMessage) {
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
