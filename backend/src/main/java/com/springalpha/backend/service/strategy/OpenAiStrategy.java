package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;
import java.time.Duration;

/**
 * OpenAI 策略实现 (OpenAiStrategy)
 * <p>
 * **定位**: 对接 OpenAI GPT-4 API 的实现类。
 * **特点**:
 * 1. 使用官方 `gpt-4o-mini` 模型 (性价比高)。
 * 2. 通过 WebClient 调用 REST API (而非 Spring AI 自动配置，为了更细粒度的控制)。
 * 3. 强制 JSON 模式 (`Return ONLY valid JSON...`)。
 */
@Slf4j
@Service
@ConditionalOnProperty(name = "app.openai.enabled", havingValue = "true", matchIfMissing = false)
public class OpenAiStrategy extends BaseAiStrategy implements CredentialValidatingStrategy {

    private final WebClient.Builder webClientBuilder;
    private final String configuredApiKey;
    private final String baseUrl;
    private final String model;

    public OpenAiStrategy(
            PromptTemplateService promptService,
            AnalysisReportValidator validator,
            ObjectMapper objectMapper,
            @Value("${app.openai.api-key:}") String apiKey,
            @Value("${app.openai.model:gpt-4o-mini}") String model,
            @Value("${app.openai.base-url:https://api.openai.com/v1}") String baseUrl) {
        super(promptService, validator, objectMapper);
        this.configuredApiKey = apiKey;
        this.model = model;
        this.baseUrl = baseUrl;
        this.webClientBuilder = WebClient.builder()
                .baseUrl(baseUrl)
                .defaultHeader("Content-Type", "application/json");
        log.info("🤖 OpenAI Strategy initialized with model: {} (URL: {})", model, baseUrl);
    }

    @Override
    public String getName() {
        return "openai";
    }

    /**
     * 调用 OpenAI Chat Completions API
     * <p>
     * 使用 Server-Sent Events (SSE) 流式获取响应。
     * 手动解析 `data: {...}` 格式的数据块。
     */
    @Override
    protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang, String apiKeyOverride) {
        log.info("🧠 OpenAI Strategy - calling {}", model);

        String effectiveApiKey = resolveApiKey(apiKeyOverride);

        Map<String, Object> requestBody = Map.of(
                "model", model,
                "messages", List.of(
                        Map.of("role", "system", "content", systemPrompt),
                        Map.of("role", "user", "content", userPrompt +
                                "\n\nIMPORTANT: Return ONLY valid JSON matching the schema, with no markdown formatting.")),
                "temperature", 0.7,
                "max_tokens", 2000,
                "stream", true);

        WebClient webClient = webClientBuilder.clone()
                .baseUrl(baseUrl)
                .defaultHeader("Authorization", "Bearer " + effectiveApiKey)
                .build();

        return webClient.post()
                .uri("/chat/completions")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(requestBody)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .retrieve()
                .bodyToFlux(String.class)
                .doOnSubscribe(s -> log.info("📡 Streaming from OpenAI API..."))
                .filter(line -> line.startsWith("data:") && !line.contains("[DONE]"))
                .map(line -> {
                    try {
                        String json = line.substring(5).trim();
                        if (json.isEmpty() || json.equals("[DONE]"))
                            return "";

                        @SuppressWarnings("unchecked")
                        Map<String, Object> response = objectMapper.readValue(json, Map.class);
                        @SuppressWarnings("unchecked")
                        List<Map<String, Object>> choices = (List<Map<String, Object>>) response.get("choices");
                        if (choices != null && !choices.isEmpty()) {
                            @SuppressWarnings("unchecked")
                            Map<String, Object> delta = (Map<String, Object>) choices.get(0).get("delta");
                            if (delta != null && delta.containsKey("content")) {
                                return (String) delta.get("content");
                            }
                        }
                        return "";
                    } catch (Exception e) {
                        log.debug("Parse error for chunk: {}", e.getMessage());
                        return "";
                    }
                })
                .filter(s -> !s.isEmpty())
                .doOnComplete(() -> log.info("✅ OpenAI API stream completed"))
                .onErrorResume(e -> {
                    log.error("❌ OpenAI API call failed: {}", e.getMessage());
                    return Flux.error(mapOpenAiException(e));
                });
    }

    @Override
    public Mono<Void> validateCredentials(String apiKeyOverride) {
        String effectiveApiKey = resolveApiKey(apiKeyOverride);
        WebClient webClient = webClientBuilder.clone()
                .baseUrl(baseUrl)
                .defaultHeader("Authorization", "Bearer " + effectiveApiKey)
                .build();

        return webClient.get()
                .uri("/models")
                .retrieve()
                .bodyToMono(String.class)
                .timeout(Duration.ofSeconds(10))
                .then()
                .onErrorResume(e -> Mono.error(mapOpenAiException(e)));
    }

    private String resolveApiKey(String apiKeyOverride) {
        String effectiveApiKey = apiKeyOverride != null && !apiKeyOverride.isBlank()
                ? apiKeyOverride.trim()
                : configuredApiKey;
        if (effectiveApiKey == null || effectiveApiKey.isBlank()) {
            throw new ProviderAuthenticationException(
                    "OpenAI API key is required for BYOK mode",
                    "openai",
                    "OPENAI_API_KEY_MISSING",
                    HttpStatus.BAD_REQUEST);
        }
        return effectiveApiKey;
    }

    private RuntimeException mapOpenAiException(Throwable error) {
        if (error instanceof ProviderAuthenticationException providerAuthenticationException) {
            return providerAuthenticationException;
        }
        if (error instanceof WebClientResponseException responseException) {
            if (responseException.getStatusCode() == HttpStatus.UNAUTHORIZED
                    || responseException.getStatusCode() == HttpStatus.FORBIDDEN) {
                return new ProviderAuthenticationException(
                        "OpenAI API key is invalid or unauthorized for this project",
                        "openai",
                        "OPENAI_API_KEY_INVALID",
                        HttpStatus.UNAUTHORIZED);
            }
        }
        return new RuntimeException("OpenAI API error: " + error.getMessage(), error);
    }
}
