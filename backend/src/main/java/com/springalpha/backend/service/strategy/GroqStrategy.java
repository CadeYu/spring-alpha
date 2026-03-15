package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import io.netty.handler.ssl.SslContext;
import io.netty.handler.ssl.SslContextBuilder;
import io.netty.handler.ssl.util.InsecureTrustManagerFactory;
import reactor.netty.http.client.HttpClient;
import reactor.util.retry.Retry;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicLong;

/**
 * Groq Strategy - 对接 Groq 高速推理 API (Llama 3.3 70B)
 * <p>
 * **为什么选择 Groq?**
 * Groq 使用 LPU (Language Processing Unit) 芯片，推理速度极快 (>300 tokens/s)。
 * 这对于需要实时生成长篇财报分析的应用来说至关重要，用户等待时间从 30秒 缩短到 3-5秒。
 * <p>
 * **主要职责**:
 * 1. **Prompt Assembly**: 将 System Prompt, User Prompt 和 JSON 指令拼装。
 * 2. **Streaming**: 流式返回结果，让前端实现打字机效果。
 * 3. **Resilience**: 处理 429 限流错误 (自动重试)。
 */
@Slf4j
@Service
public class GroqStrategy extends BaseAiStrategy {

    private static final long MIN_REQUEST_INTERVAL_MS = 6000L;

    private final WebClient webClient;
    private final AtomicLong nextAvailableRequestAtMs = new AtomicLong(0);

    public GroqStrategy(
            PromptTemplateService promptService,
            AnalysisReportValidator validator,
            ObjectMapper objectMapper,
            @Value("${spring.ai.openai.api-key:}") String apiKey) {
        super(promptService, validator, objectMapper);

        try {
            SslContext sslContext = SslContextBuilder.forClient()
                    .trustManager(InsecureTrustManagerFactory.INSTANCE)
                    .build();
            HttpClient httpClient = HttpClient.create().secure(t -> t.sslContext(sslContext));

            this.webClient = WebClient.builder()
                    .clientConnector(new ReactorClientHttpConnector(httpClient))
                    .baseUrl("https://api.groq.com/openai/v1")
                    .defaultHeader("Authorization", "Bearer " + apiKey)
                    .defaultHeader("Content-Type", MediaType.APPLICATION_JSON_VALUE)
                    .build();
        } catch (Exception e) {
            throw new RuntimeException("Failed to initialize Groq WebClient", e);
        }
    }

    @Override
    public String getName() {
        return "groq";
    }

    public String getDisplayName() {
        return "Llama 3.3 70B";
    }

    @Override
    public Flux<AnalysisReport> analyze(AnalysisContract contract, String lang, String apiKeyOverride) {
        log.info("🤖 Starting reduced-call Groq analysis for {} using a 2-agent execution plan",
                contract.getTicker());

        String systemPrompt = promptService.getSystemPrompt(lang);

        Mono<AnalysisReport> summaryAgent = executeAgent(
                systemPrompt,
                promptService.buildGroqSummaryPrompt(contract, lang),
                contract, lang, apiKeyOverride, "SummaryAgent");

        Mono<AnalysisReport> insightsAgent = executeAgent(
                systemPrompt,
                promptService.buildGroqInsightsPrompt(contract, lang),
                contract, lang, apiKeyOverride, "InsightsAgent");

        return Flux.concat(
                summaryAgent,
                emitFallbackAgentReport("FactorsAgent", contract, lang),
                emitFallbackAgentReport("DriversAgent", contract, lang),
                insightsAgent);
    }

    /**
     * 调用 LLM API 生成分析报告
     * 
     * @param systemPrompt 系统设定 (你是高盛分析师...)
     * @param userPrompt   用户输入 (包含 FMP 数据 + RAG 文本)
     * @param lang         输出语言
     */
    @Override
    protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang, String apiKeyOverride) {
        log.info("⚡ Groq Strategy - calling Llama 3.3 70B");
        log.debug("System Prompt ({} chars), User Prompt ({} chars)", systemPrompt.length(), userPrompt.length());

        try {
            // 构建完整的 Prompt，并强制追加 JSON 格式指令
            // 这一步非常关键：LLM 经常“忘事”，所以在最后再强调一遍 "只能返回 JSON"
            String jsonInstruction = "zh".equalsIgnoreCase(lang)
                    ? "\n\n重要：请仅返回符合架构的有效 JSON，不要使用 markdown 格式。**所有分析内容必须使用中文输出，引用原文(excerpt)除外。**"
                    : "\n\nIMPORTANT: Return ONLY valid JSON matching the schema, with no markdown formatting.";

            // 解析为 OpenAI 兼容的 JSON 格式
            var requestBody = Map.of(
                    "model", "llama-3.3-70b-versatile",
                    "messages", List.of(
                            Map.of("role", "system", "content", systemPrompt),
                            Map.of("role", "user", "content", userPrompt + jsonInstruction)),
                    "temperature", 0.1,
                    "stream", true);

            return Flux.defer(() -> acquireRequestSlot().thenMany(createGroqRequest(requestBody)))
                    .timeout(Duration.ofSeconds(60))
                    .retryWhen(Retry.backoff(3, Duration.ofSeconds(3))
                            .filter(throwable -> throwable instanceof org.springframework.web.reactive.function.client.WebClientResponseException.TooManyRequests)
                            .doBeforeRetry(
                                    retrySignal -> log.warn("⚠️ Groq Rate Limit (429) hit, retrying... (attempt {}/3)",
                                            retrySignal.totalRetries() + 1))
                            .onRetryExhaustedThrow((retryBackoffSpec, retrySignal) -> retrySignal.failure()))
                    .doOnComplete(() -> log.info("✅ Groq API stream completed"))
                    .onErrorResume(e -> {
                        log.error("❌ Groq API call failed: {}", e.getMessage(), e);
                        return Flux.error(new RuntimeException("Groq API error: " + e.getMessage()));
                    });

        } catch (Exception e) {
            log.error("Failed to create Groq prompt", e);
            return Flux.error(e);
        }
    }

    private Mono<Void> acquireRequestSlot() {
        return Mono.defer(() -> {
            long delayMs = reserveRequestSlot();
            if (delayMs <= 0) {
                return Mono.empty();
            }
            log.info("⏱️ Delaying Groq request by {} ms to stay within provider rate limits", delayMs);
            return Mono.delay(Duration.ofMillis(delayMs)).then();
        });
    }

    private long reserveRequestSlot() {
        while (true) {
            long now = System.currentTimeMillis();
            long current = nextAvailableRequestAtMs.get();
            long startAt = Math.max(now, current);
            long nextAllowed = startAt + MIN_REQUEST_INTERVAL_MS;
            if (nextAvailableRequestAtMs.compareAndSet(current, nextAllowed)) {
                return Math.max(0, startAt - now);
            }
        }
    }

    private Flux<String> createGroqRequest(Map<String, Object> requestBody) {
        return webClient.post()
                .uri("/chat/completions")
                .bodyValue(requestBody)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .retrieve()
                .bodyToFlux(String.class)
                .doOnSubscribe(s -> log.info("📡 Streaming from Groq API (WebClient)..."))
                .handle((String rawEvent, reactor.core.publisher.SynchronousSink<String> sink) -> {
                    try {
                        if (rawEvent == null || rawEvent.isBlank() || rawEvent.contains("[DONE]")) {
                            return;
                        }
                        Map<?, ?> chunk = objectMapper.readValue(rawEvent, Map.class);
                        List<?> choices = (List<?>) chunk.get("choices");
                        if (choices != null && !choices.isEmpty()) {
                            Map<?, ?> firstChoice = (Map<?, ?>) choices.get(0);
                            Map<?, ?> delta = (Map<?, ?>) firstChoice.get("delta");
                            if (delta != null && delta.containsKey("content")) {
                                String content = (String) delta.get("content");
                                if (content != null && !content.isEmpty()) {
                                    sink.next(content);
                                }
                            }
                        }
                    } catch (Exception e) {
                        log.trace("Skipping non-parseable SSE event: {}", e.getMessage());
                    }
                });
    }
}
