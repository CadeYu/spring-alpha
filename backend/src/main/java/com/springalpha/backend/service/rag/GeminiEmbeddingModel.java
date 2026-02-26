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
 * <p>
 * **什么是 Embedding (嵌入)?**
 * 它是将 Human Text 转化为 Computer Vectors (一串数字) 的过程。
 * 只有变成了向量，我们才能计算两段话的 "相似度" (Cosine Similarity)。
 * 
 * **模型参数**:
 * - Model: text-embedding-004
 * - Dimensions: 768 (每个文本变成 768 个浮点数)
 * - Rate Limit: 免费层限制 1,500 requests/day, 1M tokens/minute
 */
@Slf4j
@Service
@Primary
@ConditionalOnProperty(name = "app.embedding-provider", havingValue = "gemini", matchIfMissing = false)
public class GeminiEmbeddingModel implements EmbeddingModel {

    private static final String GEMINI_EMBEDDING_MODEL = "gemini-embedding-001";
    private static final int EMBEDDING_DIMENSIONS = 3072; // gemini-embedding-001 outputs 3072 dims
    private static final int MAX_TEXT_LENGTH = 8000; // API 限制，太长的文本会被截断

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

    /**
     * 批量生成嵌入 (Batch Embed)
     * <p>
     * 一次性处理一堆 Chunks。为了提高速度，我们使用了并发处理，
     * 但同时必须小心不要触发 429 限流。
     */
    @Override
    public EmbeddingResponse call(EmbeddingRequest request) {
        List<String> texts = request.getInstructions();
        log.info("🚀 Generating embeddings for {} document chunks in parallel...", texts.size());

        long start = System.currentTimeMillis();

        List<Embedding> embeddings = new java.util.ArrayList<>();
        for (int i = 0; i < texts.size(); i++) {
            try {
                // 速率控制 (Rate Limiting):
                // 每次请求间隔 600ms，大约 100 RPM (Requests Per Minute)
                // 这比直接并发要慢，主要为了保平安 (Gemini 免费版很敏感)
                if (i > 0)
                    Thread.sleep(600);

                // 带重试机制的调用
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

    /**
     * 带重试机制的 Embedding 调用
     * 遇到 429 错误时，自动休眠并重试 (指数退避)
     */
    private float[] embedWithRetry(String text, int maxRetries) {
        for (int i = 0; i < maxRetries; i++) {
            try {
                return embed(text);
            } catch (Exception e) {
                if (e.getMessage().contains("429") || e.getMessage().contains("Too Many Requests")) {
                    log.warn("⚠️ Gemini Embedding Rate Limit (429), retrying... (attempt {}/{})", i + 1, maxRetries);
                    try {
                        // 2^i 秒后重试 (1s, 2s, 4s...)
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
        return new float[EMBEDDING_DIMENSIONS]; // 全部失败则返回空向量
    }

    /**
     * 单次调用 Gemini API
     */
    @Override
    public float[] embed(String text) {
        String truncatedText = truncateText(text); // 截断过长文本
        log.debug("🌐 Calling Gemini Embedding API for {} chars...", truncatedText.length());

        Map<String, Object> requestBody = Map.of(
                "model", "models/" + GEMINI_EMBEDDING_MODEL,
                "content", Map.of("parts", List.of(Map.of("text", truncatedText))));

        // 阻塞式调用 (Blocking Call)
        // 因为外层 loop 已经在控制并发了，这里 block 没问题
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
