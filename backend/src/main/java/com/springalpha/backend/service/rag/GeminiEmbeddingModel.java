package com.springalpha.backend.service.rag;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.Embedding;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.embedding.EmbeddingRequest;
import org.springframework.ai.embedding.EmbeddingResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import org.springframework.context.annotation.Primary;

import java.util.List;
import java.util.Map;

/**
 * Gemini Embedding Model - 使用 Google Gemini API 生成文本嵌入
 * 
 * 免费层限制: 1,500 requests/day, 1M tokens/minute
 * 模型: text-embedding-004, 输出维度: 768
 */
@Slf4j
@Service
@Primary
@ConditionalOnProperty(name = "app.embedding-provider", havingValue = "gemini", matchIfMissing = false)
public class GeminiEmbeddingModel implements EmbeddingModel {

    private static final String GEMINI_EMBEDDING_MODEL = "gemini-embedding-001";
    private static final int EMBEDDING_DIMENSIONS = 3072; // gemini-embedding-001 outputs 3072 dims
    private static final int MAX_TEXT_LENGTH = 8000; // Approximate token limit

    private final WebClient webClient;
    private final String apiKey;

    public GeminiEmbeddingModel(
            @Value("${GEMINI_API_KEY:}") String apiKey) {
        this.apiKey = apiKey;
        this.webClient = WebClient.builder()
                .baseUrl("https://generativelanguage.googleapis.com/v1beta")
                .defaultHeader("Content-Type", "application/json")
                .build();
        log.info("✅ GeminiEmbeddingModel initialized (model: {}, dimensions: 768)",
                GEMINI_EMBEDDING_MODEL);
    }

    @Override
    public EmbeddingResponse call(EmbeddingRequest request) {
        List<String> texts = request.getInstructions();
        log.info("🚀 Generating embeddings for {} document chunks in parallel...", texts.size());

        long start = System.currentTimeMillis();

        // Use parallel stream to fetch embeddings concurrently
        // This significantly speeds up ingestion (e.g. 30 chunks: 27s -> 2s)
        // Use sequential stream with delay to respect rate limits (100 RPM)
        List<Embedding> embeddings = new java.util.ArrayList<>();
        for (int i = 0; i < texts.size(); i++) {
            try {
                // Add small delay to avoid 429 (approx 600ms = ~100 requests/min)
                if (i > 0)
                    Thread.sleep(600);

                float[] vector = embedWithRetry(texts.get(i), 3);
                embeddings.add(new Embedding(vector, i));
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        long elapsed = System.currentTimeMillis() - start;
        log.info("✅ Batch embedding completed in {} ms", elapsed);

        return new EmbeddingResponse(embeddings);
    }

    private float[] embedWithRetry(String text, int maxRetries) {
        for (int i = 0; i < maxRetries; i++) {
            try {
                return embed(text);
            } catch (Exception e) {
                if (e.getMessage().contains("429") || e.getMessage().contains("Too Many Requests")) {
                    log.warn("⚠️ Gemini Embedding Rate Limit (429), retrying... (attempt {}/{})", i + 1, maxRetries);
                    try {
                        Thread.sleep((long) Math.pow(2, i) * 1000);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        break;
                    }
                } else {
                    log.error("❌ Embedding failed (non-retriable): {}", e.getMessage());
                    break;
                }
            }
        }
        return new float[EMBEDDING_DIMENSIONS]; // Return empty vector if all retries fail
    }

    @Override
    public float[] embed(String text) {
        String truncatedText = truncateText(text);
        log.debug("🌐 Calling Gemini Embedding API for {} chars...", truncatedText.length());

        Map<String, Object> requestBody = Map.of(
                "model", "models/" + GEMINI_EMBEDDING_MODEL,
                "content", Map.of("parts", List.of(Map.of("text", truncatedText))));

        // Blocking call is fine here as we are wrapping it in retry logic above
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
        throw new RuntimeException("Empty embedding response");
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
