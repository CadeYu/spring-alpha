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
 * OpenAI Strategy - Uses OpenAI's GPT-4 API directly
 * Requires OPENAI_API_KEY environment variable
 */
@Slf4j
@Service
@ConditionalOnProperty(name = "app.openai.enabled", havingValue = "true", matchIfMissing = false)
public class OpenAiStrategy extends BaseAiStrategy {

    private final WebClient webClient;
    private final String model;

    public OpenAiStrategy(
            PromptTemplateService promptService,
            AnalysisReportValidator validator,
            ObjectMapper objectMapper,
            @Value("${app.openai.api-key:}") String apiKey,
            @Value("${app.openai.model:gpt-4o-mini}") String model) {
        super(promptService, validator, objectMapper);
        this.model = model;
        this.webClient = WebClient.builder()
                .baseUrl("https://api.openai.com/v1")
                .defaultHeader("Authorization", "Bearer " + apiKey)
                .defaultHeader("Content-Type", "application/json")
                .build();
        log.info("🤖 OpenAI Strategy initialized with model: {}", model);
    }

    @Override
    public String getName() {
        return "openai";
    }

    @Override
    protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang) {
        log.info("🧠 OpenAI Strategy - calling {}", model);

        Map<String, Object> requestBody = Map.of(
                "model", model,
                "messages", List.of(
                        Map.of("role", "system", "content", systemPrompt),
                        Map.of("role", "user", "content", userPrompt +
                                "\n\nIMPORTANT: Return ONLY valid JSON matching the schema, with no markdown formatting.")),
                "temperature", 0.7,
                "max_tokens", 2000,
                "stream", true);

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
                    return Flux.error(new RuntimeException("OpenAI API error: " + e.getMessage()));
                });
    }
}
