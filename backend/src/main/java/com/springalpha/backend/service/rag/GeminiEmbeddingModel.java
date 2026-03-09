package com.springalpha.backend.service.rag;

import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.document.Document;
import org.springframework.ai.embedding.Embedding;
import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.embedding.EmbeddingRequest;
import org.springframework.ai.embedding.EmbeddingResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Remote Gemini embedding provider used by PGVector RAG.
 * This stays internal only; Gemini is no longer exposed as a user-facing chat model.
 */
@Slf4j
@Service
@Primary
@ConditionalOnProperty(name = "app.embedding-provider", havingValue = "gemini")
public class GeminiEmbeddingModel implements EmbeddingModel {

    private static final String GEMINI_EMBEDDING_MODEL = "gemini-embedding-001";
    private static final int EMBEDDING_DIMENSIONS = 768;
    private static final int MAX_TEXT_LENGTH = 8_000;

    private final WebClient webClient;
    private final String apiKey;

    public GeminiEmbeddingModel(@Value("${GEMINI_API_KEY:}") String apiKey) {
        this.apiKey = apiKey;
        this.webClient = WebClient.builder()
                .baseUrl("https://generativelanguage.googleapis.com/v1beta")
                .defaultHeader("Content-Type", "application/json")
                .build();
        log.info("✅ GeminiEmbeddingModel initialized (model: {}, dimensions: {})",
                GEMINI_EMBEDDING_MODEL, EMBEDDING_DIMENSIONS);
    }

    @Override
    public EmbeddingResponse call(EmbeddingRequest request) {
        List<String> texts = request.getInstructions();
        List<Embedding> embeddings = new ArrayList<>(texts.size());

        for (int i = 0; i < texts.size(); i++) {
            if (i > 0) {
                sleepSilently(600);
            }
            embeddings.add(new Embedding(embedWithRetry(texts.get(i), 3), i));
        }

        return new EmbeddingResponse(embeddings);
    }

    @Override
    public float[] embed(String text) {
        if (apiKey == null || apiKey.isBlank()) {
            throw new IllegalStateException("GEMINI_API_KEY is required for Gemini embeddings");
        }

        String truncatedText = truncateText(text);
        Map<String, Object> requestBody = Map.of(
                "model", "models/" + GEMINI_EMBEDDING_MODEL,
                "content", Map.of("parts", List.of(Map.of("text", truncatedText))),
                "outputDimensionality", EMBEDDING_DIMENSIONS);

        EmbeddingApiResponse response = webClient.post()
                .uri("/models/{model}:embedContent?key={apiKey}", GEMINI_EMBEDDING_MODEL, apiKey)
                .bodyValue(requestBody)
                .retrieve()
                .bodyToMono(EmbeddingApiResponse.class)
                .timeout(java.time.Duration.ofSeconds(30))
                .block(java.time.Duration.ofSeconds(35));

        if (response != null && response.embedding != null && response.embedding.values != null) {
            return response.embedding.values;
        }
        throw new IllegalStateException("Empty embedding response from Gemini");
    }

    @Override
    public float[] embed(Document document) {
        return embed(document.getFormattedContent());
    }

    @Override
    public int dimensions() {
        return EMBEDDING_DIMENSIONS;
    }

    private float[] embedWithRetry(String text, int maxRetries) {
        RuntimeException lastError = null;
        for (int attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                return embed(text);
            } catch (RuntimeException ex) {
                lastError = ex;
                String message = ex.getMessage() == null ? "" : ex.getMessage();
                if (!message.contains("429") && !message.contains("Too Many Requests")) {
                    throw ex;
                }
                log.warn("Gemini embedding rate limited, retry {}/{}", attempt, maxRetries);
                sleepSilently((long) Math.pow(2, attempt - 1) * 1000);
            }
        }
        throw lastError == null ? new IllegalStateException("Failed to generate Gemini embedding") : lastError;
    }

    private static String truncateText(String text) {
        if (text == null) {
            return "";
        }
        return text.length() > MAX_TEXT_LENGTH ? text.substring(0, MAX_TEXT_LENGTH) : text;
    }

    private static void sleepSilently(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
        }
    }

    private static final class EmbeddingApiResponse {
        public EmbeddingValues embedding;
    }

    private static final class EmbeddingValues {
        public float[] values;
    }
}
