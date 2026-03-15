package com.springalpha.backend.service.rag;

public class GeminiEmbeddingRateLimitException extends RuntimeException {

    public GeminiEmbeddingRateLimitException(String message) {
        super(message);
    }

    public GeminiEmbeddingRateLimitException(String message, Throwable cause) {
        super(message, cause);
    }
}
