package com.springalpha.backend.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Spring AI 配置类
 * <p>
 * 1. **自动配置**: Spring AI 1.0.0-M6+ 使用 `spring-ai-openai-spring-boot-starter`
 * 即使我们手动使用 WebClient 调用 OpenAI/Groq (为了流式控制)，
 * 这个配置类仍然保留，用于其他 Spring AI 组件 (如 VectorStore) 的自动装配。
 * <p>
 * 2. **ObjectMapper**: 全局 JSON 序列化工具。
 */
@Configuration
public class SpringAiConfig {

    @Bean
    public ObjectMapper objectMapper() {
        return new ObjectMapper();
    }
}
