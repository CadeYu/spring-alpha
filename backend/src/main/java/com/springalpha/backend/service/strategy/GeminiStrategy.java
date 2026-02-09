package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;

/**
 * Gemini Strategy - Uses Google's Gemini API
 * Requires GEMINI_API_KEY environment variable
 */
@Slf4j
@Service
@ConditionalOnProperty(name = "app.gemini.enabled", havingValue = "true", matchIfMissing = false)
public class GeminiStrategy extends BaseAiStrategy {

    private final WebClient webClient;
    private final String model;
    private final String apiKey;

    public GeminiStrategy(
            PromptTemplateService promptService,
            AnalysisReportValidator validator,
            ObjectMapper objectMapper,
            @Value("${app.gemini.api-key:}") String apiKey,
            @Value("${app.gemini.model:gemini-1.5-flash}") String model) {
        super(promptService, validator, objectMapper);
        this.model = model;
        this.apiKey = apiKey;
        this.webClient = WebClient.builder()
                .baseUrl("https://generativelanguage.googleapis.com/v1beta")
                .defaultHeader("Content-Type", "application/json")
                .build();
        log.info("💎 Gemini Strategy initialized with model: {}", model);
    }

    @Override
    public String getName() {
        return "gemini";
    }

    @Override
    protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang) {
        log.info("💎 Gemini Strategy - calling {}", model);

        // Gemini uses a different request format
        Map<String, Object> requestBody = Map.of(
                "contents", List.of(
                        Map.of("parts", List.of(
                                Map.of("text", systemPrompt + "\n\n" + userPrompt +
                                        "\n\nIMPORTANT: Return ONLY valid JSON matching the schema, with no markdown formatting.")))),
                "generationConfig", Map.of(
                        "temperature", 0.7,
                        "maxOutputTokens", 2000));

        // Gemini uses streamGenerateContent for streaming
        return webClient.post()
                .uri("/models/{model}:streamGenerateContent?key={apiKey}&alt=sse", model, apiKey)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(requestBody)
                .accept(MediaType.TEXT_EVENT_STREAM)
                .retrieve()
                .bodyToFlux(String.class)
                .doOnSubscribe(s -> log.info("📡 Streaming from Gemini API..."))
                .filter(line -> line.startsWith("data:"))
                .map(line -> {
                    try {
                        String json = line.substring(5).trim();
                        if (json.isEmpty())
                            return "";

                        @SuppressWarnings("unchecked")
                        Map<String, Object> response = objectMapper.readValue(json, Map.class);
                        @SuppressWarnings("unchecked")
                        List<Map<String, Object>> candidates = (List<Map<String, Object>>) response.get("candidates");
                        if (candidates != null && !candidates.isEmpty()) {
                            @SuppressWarnings("unchecked")
                            Map<String, Object> content = (Map<String, Object>) candidates.get(0).get("content");
                            if (content != null) {
                                @SuppressWarnings("unchecked")
                                List<Map<String, Object>> parts = (List<Map<String, Object>>) content.get("parts");
                                if (parts != null && !parts.isEmpty()) {
                                    return (String) parts.get(0).get("text");
                                }
                            }
                        }
                        return "";
                    } catch (Exception e) {
                        log.debug("Parse error for chunk: {}", e.getMessage());
                        return "";
                    }
                })
                .filter(s -> s != null && !s.isEmpty())
                .doOnComplete(() -> log.info("✅ Gemini API stream completed"))
                .onErrorResume(e -> {
                    log.error("❌ Gemini API call failed: {}", e.getMessage());
                    return Flux.error(new RuntimeException("Gemini API error: " + e.getMessage()));
                });
    }
}
