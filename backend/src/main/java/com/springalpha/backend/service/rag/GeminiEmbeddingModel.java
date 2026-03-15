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
import java.util.concurrent.atomic.AtomicLong;

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
    private static final long MIN_REQUEST_INTERVAL_MS = 1_500;
    private static final long RATE_LIMIT_COOLDOWN_MS = 60_000;
    private static final Object REQUEST_MONITOR = new Object();
    private static final AtomicLong NEXT_REQUEST_AT_MS = new AtomicLong(0);
    private static final AtomicLong COOLDOWN_UNTIL_MS = new AtomicLong(0);

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
        long cooldownUntil = COOLDOWN_UNTIL_MS.get();
        if (cooldownUntil > System.currentTimeMillis()) {
            throw new GeminiEmbeddingRateLimitException(
                    "Gemini embedding is cooling down after a 429 response; skipping background vector ingestion for now.");
        }

        RuntimeException lastError = null;
        for (int attempt = 1; attempt <= maxRetries; attempt++) {
            try {
                awaitGlobalPermit();
                return embed(text);
            } catch (RuntimeException ex) {
                lastError = ex;
                String message = ex.getMessage() == null ? "" : ex.getMessage();
                if (!message.contains("429") && !message.contains("Too Many Requests")) {
                    throw ex;
                }
                long until = System.currentTimeMillis() + RATE_LIMIT_COOLDOWN_MS;
                COOLDOWN_UNTIL_MS.accumulateAndGet(until, Math::max);
                log.warn("Gemini embedding rate limited (429); entering a {} ms cooldown and skipping the current ingestion batch",
                        RATE_LIMIT_COOLDOWN_MS);
                throw new GeminiEmbeddingRateLimitException(
                        "Gemini embedding hit a 429 rate limit and the current background ingestion was skipped.", ex);
            }
        }
        throw lastError == null ? new IllegalStateException("Failed to generate Gemini embedding") : lastError;
    }

    private static void awaitGlobalPermit() {
        synchronized (REQUEST_MONITOR) {
            long now = System.currentTimeMillis();
            long cooldownUntil = COOLDOWN_UNTIL_MS.get();
            if (cooldownUntil > now) {
                throw new GeminiEmbeddingRateLimitException(
                        "Gemini embedding is cooling down after a 429 response; skipping background vector ingestion for now.");
            }

            long nextRequestAt = NEXT_REQUEST_AT_MS.get();
            long waitMillis = Math.max(0, nextRequestAt - now);
            if (waitMillis > 0) {
                sleepSilently(waitMillis);
                now = System.currentTimeMillis();
            }
            NEXT_REQUEST_AT_MS.set(now + MIN_REQUEST_INTERVAL_MS);
        }
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
