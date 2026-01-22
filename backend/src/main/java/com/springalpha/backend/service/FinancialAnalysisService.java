package com.springalpha.backend.service;

import com.springalpha.backend.service.strategy.AiAnalysisStrategy;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

@Service
public class FinancialAnalysisService {

    private static final Logger log = LoggerFactory.getLogger(FinancialAnalysisService.class);
    private final SecService secService;
    private final RagService ragService;
    private final Map<String, AiAnalysisStrategy> strategies;

    // 默认使用 gemini，如果想用 mock 可以在 application.yml 配置 app.ai-provider=mock
    @Value("${app.ai-provider:gemini}")
    private String activeProvider;

    public FinancialAnalysisService(SecService secService, RagService ragService, List<AiAnalysisStrategy> strategyList) {
        this.secService = secService;
        this.ragService = ragService;
        this.strategies = strategyList.stream()
                .collect(Collectors.toMap(AiAnalysisStrategy::getName, Function.identity()));
        
        log.info("🎯 已加载 AI 策略: {}", this.strategies.keySet());
    }

    public Flux<String> analyzeStock(String ticker, String lang) {
        return secService.getLatest10KContent(ticker)
                .flatMapMany(content -> {
                    log.info("📄 获取到财报全文，长度: {}。开始 RAG 检索...", content.length());
                    
                    // 1. 使用 RAG 检索最相关的片段 (替代之前的 substring 截断)
                    // 检索词涵盖：财务数据、风险、未来展望
                    String query = "Key Financial Metrics, Revenue, Net Income, Risk Factors, Future Outlook, Guidance";
                    String context = ragService.retrieveRelevantContext(content, query);
                    
                    // 2. 选择策略 (默认 Gemini)
                    AiAnalysisStrategy tempStrategy = strategies.getOrDefault(activeProvider, strategies.get("mock"));
                    
                    // 3. 安全检查：如果策略没找到，强制用 Mock
                    if (tempStrategy == null) {
                        tempStrategy = strategies.get("mock");
                    }
                    
                    final AiAnalysisStrategy strategy = tempStrategy;

                    log.info("🚀 启动分析，使用策略: {}, 语言: {}", strategy.getName(), lang);

                    // 4. 执行分析 (带自动降级)
                    // 如果 Gemini 429/404，onErrorResume 会捕获并切换到 MockStrategy
                    return strategy.analyze(ticker, context, lang)
                            .onErrorResume(e -> {
                                log.error("❌ 策略 [{}] 执行失败: {}. 自动切换到 Mock 兜底。", strategy.getName(), e.getMessage());
                                return strategies.get("mock").analyze(ticker, context, lang);
                            });
                });
    }
}
