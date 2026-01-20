package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Flux;
import reactor.util.retry.Retry;

import java.time.Duration;
import java.util.List;
import java.util.Map;

@Component
public class GeminiStrategy implements AiAnalysisStrategy {

    private static final Logger log = LoggerFactory.getLogger(GeminiStrategy.class);
    private final WebClient webClient;
    private final ObjectMapper objectMapper;

    @Value("${spring.ai.vertex.ai.gemini.api-key}")
    private String apiKey;

    private static final String API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-lite:streamGenerateContent";

    private static final String SYSTEM_PROMPT = """
            你是一位资深的华尔街分析师。
            你的任务是阅读这份 SEC 10-K 财报，并用**中文**生成一份结构化分析报告。
            
            请包含：
            1. 📊 关键财务指标 (营收、净利润、毛利率及同比变化)
            2. ⚠️ 核心风险因素 (Top 3)
            3. 🔮 未来展望 (管理层语气与指引)
            
            格式要求：Markdown，专业，简洁。
            """;

    public GeminiStrategy(WebClient.Builder webClientBuilder, ObjectMapper objectMapper) {
        this.webClient = webClientBuilder.build();
        this.objectMapper = objectMapper;
    }

    @Override
    public Flux<String> analyze(String ticker, String textContent) {
        log.info("🤖 使用策略: Gemini Strategy");
        
        Map<String, Object> requestBody = Map.of(
            "contents", List.of(
                Map.of("parts", List.of(
                    Map.of("text", SYSTEM_PROMPT + "\n\n请分析股票代码 " + ticker + " 的财报内容：\n" + textContent)
                ))
            )
        );

        return webClient.post()
                .uri(uriBuilder -> uriBuilder
                        .scheme("https")
                        .host("generativelanguage.googleapis.com")
                        .path("/v1beta/models/gemini-2.0-flash-lite:streamGenerateContent")
                        .queryParam("key", apiKey)
                        .build())
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(requestBody)
                .retrieve()
                .bodyToFlux(String.class)
                .retryWhen(Retry.backoff(2, Duration.ofSeconds(1))
                        .filter(throwable -> throwable instanceof org.springframework.web.reactive.function.client.WebClientResponseException.TooManyRequests))
                .map(this::parseResponse)
                .filter(text -> !text.isEmpty());
    }

    @Override
    public String getName() {
        return "gemini";
    }

    private String parseResponse(String jsonChunk) {
        try {
            JsonNode root = objectMapper.readTree(jsonChunk);
            JsonNode candidates = root.path("candidates");
            if (candidates.isArray() && !candidates.isEmpty()) {
                JsonNode parts = candidates.get(0).path("content").path("parts");
                if (parts.isArray() && !parts.isEmpty()) {
                    String content = parts.get(0).path("text").asText("");
                    if (!content.isEmpty()) {
                        return objectMapper.writeValueAsString(Map.of("text", content));
                    }
                }
            }
        } catch (Exception e) {
            // ignore
        }
        return "";
    }
}
