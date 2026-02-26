package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.model.ChatModel;

import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

/**
 * Groq Strategy - 对接 Groq 高速推理 API (Llama 3.3 70B)
 * <p>
 * **为什么选择 Groq?**
 * Groq 使用 LPU (Language Processing Unit) 芯片，推理速度极快 (>300 tokens/s)。
 * 这对于需要实时生成长篇财报分析的应用来说至关重要，用户等待时间从 30秒 缩短到 3-5秒。
 * <p>
 * **主要职责**:
 * 1. **Prompt Assembly**: 将 System Prompt, User Prompt 和 JSON 指令拼装。
 * 2. **Streaming**: 流式返回结果，让前端实现打字机效果。
 * 3. **Resilience**: 处理 429 限流错误 (自动重试)。
 */
@Slf4j
@Service
public class GroqStrategy extends BaseAiStrategy {

    private final ChatModel chatModel;

    public GroqStrategy(
            PromptTemplateService promptService,
            AnalysisReportValidator validator,
            ObjectMapper objectMapper,
            ChatModel chatModel) {
        super(promptService, validator, objectMapper);
        this.chatModel = chatModel;
    }

    @Override
    public String getName() {
        return "groq";
    }

    /**
     * 调用 LLM API 生成分析报告
     * 
     * @param systemPrompt 系统设定 (你是高盛分析师...)
     * @param userPrompt   用户输入 (包含 FMP 数据 + RAG 文本)
     * @param lang         输出语言
     */
    @Override
    protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang) {
        log.info("⚡ Groq Strategy - calling Llama 3.3 70B");
        log.debug("System Prompt ({} chars), User Prompt ({} chars)", systemPrompt.length(), userPrompt.length());

        try {
            // 构建完整的 Prompt，并强制追加 JSON 格式指令
            // 这一步非常关键：LLM 经常“忘事”，所以在最后再强调一遍 "只能返回 JSON"
            String jsonInstruction = "zh".equalsIgnoreCase(lang)
                    ? "\n\n重要：请仅返回符合架构的有效 JSON，不要使用 markdown 格式。**所有分析内容必须使用中文输出，引用原文(excerpt)除外。**"
                    : "\n\nIMPORTANT: Return ONLY valid JSON matching the schema, with no markdown formatting.";

            // 最终发送给模型的内容 = 角色设定 + 数据上下文 + 格式要求
            String fullPrompt = systemPrompt + "\n\n" + userPrompt + jsonInstruction;

            org.springframework.ai.chat.messages.UserMessage userMessage = new org.springframework.ai.chat.messages.UserMessage(
                    fullPrompt);

            Prompt prompt = new Prompt(java.util.List.of(userMessage));

            // 调用 Groq API (Stream 模式)
            // 使用 Flux流式返回，避免前端长时间白屏
            return chatModel.stream(prompt)
                    .doOnSubscribe(s -> log.info("📡 Streaming from Groq API..."))
                    .handle((chatResponse, sink) -> {
                        // 防御性编程：处理各种可能的 Null 指针 (API 返回空包时)
                        if (chatResponse == null)
                            return;
                        var result = chatResponse.getResult();
                        if (result == null)
                            return;
                        var output = result.getOutput();
                        if (output == null)
                            return;

                        var content = output.getText();
                        if (content != null && !content.isEmpty()) {
                            sink.next(content); // 将这一小块文本推送到流中
                            log.debug("📨 Chunk: {} chars", content.length());
                        }
                    })
                    .cast(String.class)
                    // 容错机制：Groq 免费版限制较严，容易报 429 Too Many Requests
                    // 这里实现了指数退避重试 (Exponential Backoff): 等 2s, 4s, 8s 再试
                    .retryWhen(reactor.util.retry.Retry.backoff(3, java.time.Duration.ofSeconds(2))
                            .filter(throwable -> throwable instanceof org.springframework.web.reactive.function.client.WebClientResponseException.TooManyRequests)
                            .doBeforeRetry(
                                    retrySignal -> log.warn("⚠️ Groq Rate Limit (429) hit, retrying... (attempt {}/3)",
                                            retrySignal.totalRetries() + 1))
                            .onRetryExhaustedThrow((retryBackoffSpec, retrySignal) -> retrySignal.failure()))
                    .doOnComplete(() -> log.info("✅ Groq API stream completed"))
                    .onErrorResume(e -> {
                        log.error("❌ Groq API call failed: {}", e.getMessage(), e);
                        return Flux.error(new RuntimeException("Groq API error: " + e.getMessage()));
                    });

        } catch (Exception e) {
            log.error("Failed to create Groq prompt", e);
            return Flux.error(e);
        }
    }
}
