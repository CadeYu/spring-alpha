package com.springalpha.backend.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Spring AI 配置类
 * 
 * Spring AI 1.0.0-M7 使用自动配置，ChatModel 由 starter 自动创建
 * 配置在 application.yml 中的 spring.ai.openai.* 属性
 */
@Configuration
public class SpringAiConfig {

    @Bean
    public ObjectMapper objectMapper() {
        return new ObjectMapper();
    }
}
