package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

import java.util.List;
import java.util.Map;

/**
 * ChatAnywhere Strategy - 免费 GPT-4o-mini API
 * <p>
 * 使用 ChatAnywhere 提供的免费 OpenAI 兼容 API
 * (https://github.com/chatanywhere/GPT_API_free)。
 * <p>
 * **为什么用 java.net.http.HttpClient 而不是 WebClient?**
 * ChatAnywhere 前端使用 Cloudflare CDN，会根据 TLS 指纹拦截 Reactor Netty 请求 (403)。
 * Java 标准 HttpClient 的 TLS 指纹被 Cloudflare 信任，所以用它来替代。
 * <p>
 * **免费额度**: gpt-4o-mini 200 次/天，完全够用（50 次股票分析 × 4 agents）。
 * **协议**: 100% OpenAI 兼容，仅需改 base URL。
 */
@Slf4j
@Service
@ConditionalOnProperty(name = "app.chatanywhere.enabled", havingValue = "true", matchIfMissing = false)
public class ChatAnywhereStrategy extends BaseAiStrategy {

    private final HttpClient httpClient;
    private final String apiKey;
    private final String model;
    private final String baseUrl;

    public ChatAnywhereStrategy(
            PromptTemplateService promptService,
            AnalysisReportValidator validator,
            ObjectMapper objectMapper,
            @Value("${app.chatanywhere.api-key:}") String apiKey,
            @Value("${app.chatanywhere.model:gpt-4o-mini}") String model,
            @Value("${app.chatanywhere.base-url:https://api.chatanywhere.org/v1}") String baseUrl) {
        super(promptService, validator, objectMapper);
        this.apiKey = apiKey;
        this.model = model;
        this.baseUrl = baseUrl;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(30))
                .build();
        log.info("🆓 ChatAnywhere Strategy initialized with model: {} (URL: {})", model, baseUrl);
    }

    @Override
    public String getName() {
        return "chatanywhere";
    }

    public String getDisplayName() {
        return "GPT-4o mini";
    }

    /**
     * 调用 ChatAnywhere (OpenAI 兼容) Chat Completions API
     * <p>
     * 使用 Java 标准 HttpClient 进行 SSE 流式请求，
     * 逐行读取 "data: {...}" 事件，提取 delta.content。
     */
    @Override
    protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang, String apiKeyOverride) {
        log.info("🆓 ChatAnywhere Strategy - calling {}", model);

        String jsonInstruction = "zh".equalsIgnoreCase(lang)
                ? "\n\n重要：请仅返回符合架构的有效 JSON，不要使用 markdown 格式。**所有分析内容必须使用中文输出，引用原文(excerpt)除外。**"
                : "\n\nIMPORTANT: Return ONLY valid JSON matching the schema, with no markdown formatting.";

        // ChatAnywhere free tier limits input to 4096 tokens (~12000 chars).
        // The prompt structure is: [header + financialFacts + textEvidence] + [TASK +
        // JSON schema].
        // The JSON schema is at the END, so blind truncation would cut it off.
        // Smart truncation: keep the schema (tail) intact, truncate only the data
        // section.
        final int MAX_USER_PROMPT_CHARS = 12000;
        String truncatedPrompt = userPrompt;
        if (userPrompt.length() > MAX_USER_PROMPT_CHARS) {
            // Find the TASK section boundary - this is where the schema starts
            int taskIdx = userPrompt.indexOf("\nTASK:");
            if (taskIdx == -1)
                taskIdx = userPrompt.indexOf("\nOUTPUT REQUIREMENTS:");

            if (taskIdx > 0) {
                // Split: data part (before TASK:) and schema part (TASK: onwards)
                String dataPart = userPrompt.substring(0, taskIdx);
                String schemaPart = userPrompt.substring(taskIdx);

                // Budget for data = total budget - schema size - safety margin
                int databudget = MAX_USER_PROMPT_CHARS - schemaPart.length() - 200;
                if (databudget < 2000)
                    databudget = 2000; // minimum data context

                if (dataPart.length() > databudget) {
                    dataPart = dataPart.substring(0, databudget)
                            + "\n\n[... data truncated to fit token limit ...]";
                }

                truncatedPrompt = dataPart + schemaPart
                        + "\n\nCRITICAL: Return ONLY the flat JSON object, NO wrapper. "
                        + "For array fields, use [] with objects, never plain strings.";
            } else {
                // Fallback: no TASK section found, use simple truncation
                truncatedPrompt = userPrompt.substring(0, MAX_USER_PROMPT_CHARS)
                        + "\n\n[... content truncated ...]";
            }
            log.warn("⚠️ User prompt truncated from {} to {} chars for ChatAnywhere free tier",
                    userPrompt.length(), truncatedPrompt.length());
        }

        // Also truncate system prompt if needed
        final int MAX_SYSTEM_PROMPT_CHARS = 2000;
        String truncatedSystem = systemPrompt.length() > MAX_SYSTEM_PROMPT_CHARS
                ? systemPrompt.substring(0, MAX_SYSTEM_PROMPT_CHARS)
                : systemPrompt;

        try {
            // Build request body as JSON string
            Map<String, Object> requestBody = Map.of(
                    "model", model,
                    "messages", List.of(
                            Map.of("role", "system", "content", truncatedSystem),
                            Map.of("role", "user", "content", truncatedPrompt + jsonInstruction)),
                    "temperature", 0.1,
                    "max_tokens", 2000,
                    "stream", true);

            String bodyJson = objectMapper.writeValueAsString(requestBody);

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(baseUrl + "/chat/completions"))
                    .header("Authorization", "Bearer " + apiKey)
                    .header("Content-Type", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(bodyJson))
                    .timeout(Duration.ofSeconds(120))
                    .build();

            // Use Flux.create + blocking I/O on boundedElastic scheduler
            // This is the standard pattern for wrapping blocking APIs in Reactor
            return Flux.<String>create(sink -> {
                try {
                    log.info("📡 Streaming from ChatAnywhere API...");
                    HttpResponse<java.io.InputStream> response = httpClient.send(
                            request, HttpResponse.BodyHandlers.ofInputStream());

                    if (response.statusCode() != 200) {
                        String errorBody = new String(response.body().readAllBytes());
                        log.error("❌ ChatAnywhere API returned {}: {}", response.statusCode(), errorBody);
                        sink.error(new RuntimeException(
                                "ChatAnywhere API error " + response.statusCode() + ": " + errorBody));
                        return;
                    }

                    try (BufferedReader reader = new BufferedReader(
                            new InputStreamReader(response.body()))) {
                        String line;
                        while ((line = reader.readLine()) != null) {
                            if (line.isBlank() || line.equals("data: [DONE]")) {
                                continue;
                            }
                            if (line.startsWith("data: ")) {
                                String json = line.substring(6).trim();
                                try {
                                    @SuppressWarnings("unchecked")
                                    Map<String, Object> chunk = objectMapper.readValue(json, Map.class);
                                    @SuppressWarnings("unchecked")
                                    List<Map<String, Object>> choices = (List<Map<String, Object>>) chunk
                                            .get("choices");
                                    if (choices != null && !choices.isEmpty()) {
                                        @SuppressWarnings("unchecked")
                                        Map<String, Object> delta = (Map<String, Object>) choices.get(0).get("delta");
                                        if (delta != null && delta.containsKey("content")) {
                                            String content = (String) delta.get("content");
                                            if (content != null && !content.isEmpty()) {
                                                sink.next(content);
                                            }
                                        }
                                    }
                                } catch (Exception e) {
                                    log.trace("Skipping non-parseable SSE line: {}", e.getMessage());
                                }
                            }
                        }
                    }
                    log.info("✅ ChatAnywhere API stream completed");
                    sink.complete();
                } catch (Exception e) {
                    log.error("❌ ChatAnywhere API call failed: {}", e.getMessage());
                    sink.error(new RuntimeException("ChatAnywhere API error: " + e.getMessage()));
                }
            }).subscribeOn(Schedulers.boundedElastic());

        } catch (Exception e) {
            log.error("Failed to create ChatAnywhere request", e);
            return Flux.error(e);
        }
    }
}
