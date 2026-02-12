package com.springalpha.backend.config;

import org.springframework.ai.embedding.EmbeddingModel;
import org.springframework.ai.transformers.TransformersEmbeddingModel;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Configuration for Local Embeddings (ONNX)
 * Uses HuggingFace models locally via DJL/ONNX Runtime.
 * No API Key required. Free and private.
 */
@Configuration
public class LocalEmbeddingConfig {

    @Bean
    @ConditionalOnProperty(name = "app.embedding-provider", havingValue = "local", matchIfMissing = true)
    public EmbeddingModel localEmbeddingModel() {
        return new TransformersEmbeddingModel();
    }
}
