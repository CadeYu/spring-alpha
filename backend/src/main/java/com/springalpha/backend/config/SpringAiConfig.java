package com.springalpha.backend.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Spring AI 配置类
 * 
 * 配置 ChatModel Bean，供 SpringAiStrategy 使用
 */
@Configuration
public class SpringAiConfig {

    @Value("${spring.ai.openai.base-url:https://api.groq.com/openai}")
    private String baseUrl;

    @Value("${spring.ai.openai.api-key:}")
    private String apiKey;

    @Value("${spring.ai.openai.model:llama-3.3-70b-versatile}")
    private String modelName;

    @Bean
    public ChatModel chatModel() {
        // 使用 OpenAI API 兼容接口 (实际指向 Groq)
        OpenAiApi openAiApi = new OpenAiApi(baseUrl, apiKey);

        OpenAiChatOptions options = OpenAiChatOptions.builder()
                .withModel(modelName)
                .withTemperature(0.7)
                .withMaxTokens(2000)
                .build();

        return new OpenAiChatModel(openAiApi, options);
    }

    @Bean
    public ObjectMapper objectMapper() {
        return new ObjectMapper();
    }
}
