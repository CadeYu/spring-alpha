package com.springalpha.backend.service.rag;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.Embedding;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.embedding.EmbeddingRequest;
import org.springframework.ai.embedding.EmbeddingResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

import org.springframework.context.annotation.Primary;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Gemini Embedding Model - 使用 Google Gemini API 生成文本嵌入
 * 
 * 免费层限制: 1,500 requests/day, 1M tokens/minute
 * 模型: text-embedding-004, 输出维度: 768
 */
@Slf4j
@Component
@Primary // 标记为主要 EmbeddingModel，让 PGVector 使用这个而不是 OpenAI
public class GeminiEmbeddingModel implements EmbeddingModel {

    private static final String GEMINI_EMBEDDING_MODEL = "text-embedding-004";
    private static final int EMBEDDING_DIMENSIONS = 768;
    private static final int MAX_TEXT_LENGTH = 8000; // Approximate token limit

    private final WebClient webClient;
    private final String apiKey;

    public GeminiEmbeddingModel(
            @Value("${GEMINI_API_KEY:}") String apiKey) {
        this.apiKey = apiKey;
        this.webClient = WebClient.builder()
                .baseUrl("https://generativelanguage.googleapis.com/v1beta")
                .build();
        log.info("✅ GeminiEmbeddingModel initialized (model: {}, dimensions: {})",
                GEMINI_EMBEDDING_MODEL, EMBEDDING_DIMENSIONS);
    }

    @Override
    public EmbeddingResponse call(EmbeddingRequest request) {
        List<Embedding> embeddings = new ArrayList<>();
        List<String> texts = request.getInstructions();

        for (int i = 0; i < texts.size(); i++) {
            float[] vector = embed(texts.get(i));
            embeddings.add(new Embedding(vector, i));
        }

        return new EmbeddingResponse(embeddings);
    }

    @Override
    public float[] embed(String text) {
        String truncatedText = truncateText(text);

        Map<String, Object> requestBody = Map.of(
                "model", "models/" + GEMINI_EMBEDDING_MODEL,
                "content", Map.of("parts", List.of(Map.of("text", truncatedText))));

        try {
            EmbeddingApiResponse response = webClient.post()
                    .uri("/models/{model}:embedContent?key={apiKey}",
                            GEMINI_EMBEDDING_MODEL, apiKey)
                    .bodyValue(requestBody)
                    .retrieve()
                    .bodyToMono(EmbeddingApiResponse.class)
                    .block();

            if (response != null && response.embedding != null) {
                return response.embedding.values;
            }

            log.warn("Empty embedding response, returning zero vector");
            return new float[EMBEDDING_DIMENSIONS];

        } catch (Exception e) {
            log.error("Failed to get embedding from Gemini API: {}", e.getMessage());
            return new float[EMBEDDING_DIMENSIONS];
        }
    }

    @Override
    public float[] embed(Document document) {
        return embed(document.getFormattedContent());
    }

    @Override
    public int dimensions() {
        return EMBEDDING_DIMENSIONS;
    }

    private String truncateText(String text) {
        if (text == null)
            return "";
        return text.length() > MAX_TEXT_LENGTH
                ? text.substring(0, MAX_TEXT_LENGTH)
                : text;
    }

    // Response DTOs
    private static class EmbeddingApiResponse {
        public EmbeddingValues embedding;
    }

    private static class EmbeddingValues {
        public float[] values;
    }
}
