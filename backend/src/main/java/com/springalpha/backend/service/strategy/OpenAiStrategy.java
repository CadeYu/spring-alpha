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

import java.util.List;
import java.util.Map;

@Component
public class OpenAiStrategy implements AiAnalysisStrategy {

    private static final Logger log = LoggerFactory.getLogger(OpenAiStrategy.class);
    private final WebClient webClient;
    private final ObjectMapper objectMapper;

    // 支持配置 Base URL (可以是 api.openai.com, 也可以是 api.deepseek.com)
    @Value("${spring.ai.openai.base-url:https://api.openai.com}")
    private String baseUrl;

    @Value("${spring.ai.openai.api-key:}")
    private String apiKey;

    @Value("${spring.ai.openai.model:gpt-3.5-turbo}")
    private String modelName;

    public OpenAiStrategy(WebClient.Builder webClientBuilder, ObjectMapper objectMapper) {
        this.webClient = webClientBuilder.build();
        this.objectMapper = objectMapper;
    }

    @Override
    public Flux<String> analyze(String ticker, String textContent) {
        log.info("🤖 使用策略: OpenAI Compatible (Model: {}, URL: {})", modelName, baseUrl);

        if (apiKey == null || apiKey.isBlank()) {
            return Flux.error(new RuntimeException("OpenAI API Key is missing"));
        }

        // 动态构建 Prompt，强制中文输出
        String userPrompt = String.format("""
            请分析这篇关于 %s 的 SEC 10-K 财报。
            
            你的任务：
            1. 使用**中文**回答。
            2. 使用 Markdown 格式。
            3. 重点分析：关键财务指标（营收、净利、毛利）、主要风险、未来展望。
            4. 风格：专业、客观，多用数据说话，适当使用 Emojis 增强可读性。
            
            财报内容如下：
            %s
            """, ticker, textContent);

        Map<String, Object> requestBody = Map.of(
            "model", modelName,
            "messages", List.of(
                Map.of("role", "system", "content", "你是一位精通美股的资深金融分析师。"),
                Map.of("role", "user", "content", userPrompt)
            ),
            "stream", true
        );

        return webClient.post()
                .uri(baseUrl + "/v1/chat/completions")
                .header("Authorization", "Bearer " + apiKey)
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(requestBody)
                .retrieve()
                .bodyToFlux(String.class)
                .map(this::parseResponse)
                .filter(text -> !text.isEmpty());
    }

    @Override
    public String getName() {
        return "openai";
    }

    private String parseResponse(String jsonChunk) {
        // OpenAI 的 SSE 格式是 "data: {...}"
        try {
            String cleanJson = jsonChunk.replace("data: ", "").trim();
            if ("[DONE]".equals(cleanJson)) return "";
            
            JsonNode root = objectMapper.readTree(cleanJson);
            JsonNode choices = root.path("choices");
            if (choices.isArray() && !choices.isEmpty()) {
                String content = choices.get(0).path("delta").path("content").asText("");
                // 关键修复：将内容再次序列化为 JSON 字符串，保留 \n 等特殊字符
                // 例如: "Hello\nWorld" -> "{\"text\": \"Hello\\nWorld\"}"
                if (!content.isEmpty()) {
                    return objectMapper.writeValueAsString(Map.of("text", content));
                }
            }
        } catch (Exception e) {
            // ignore
        }
        return "";
    }
}
