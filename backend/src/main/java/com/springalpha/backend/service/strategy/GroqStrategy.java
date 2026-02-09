package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import lombok.extern.slf4j.Slf4j;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.model.ChatResponse;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

/**
 * Groq Strategy - Uses Groq's ultra-fast LLM API (Llama 3.3 70B)
 * Groq is OpenAI-compatible and completely FREE with high speed (200+ tokens/s)
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

    @Override
    protected Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang) {
        log.info("⚡ Groq Strategy - calling Llama 3.3 70B");
        log.debug("System Prompt ({} chars), User Prompt ({} chars)", systemPrompt.length(), userPrompt.length());

        try {
            // Build full prompt with explicit JSON instruction
            String fullPrompt = systemPrompt + "\n\n" + userPrompt +
                    "\n\nIMPORTANT: Return ONLY valid JSON matching the schema, with no markdown formatting.";

            org.springframework.ai.chat.messages.UserMessage userMessage = new org.springframework.ai.chat.messages.UserMessage(
                    fullPrompt);

            Prompt prompt = new Prompt(java.util.List.of(userMessage));

            // Call Groq API (streaming) with SAFE null handling
            return chatModel.stream(prompt)
                    .doOnSubscribe(s -> log.info("📡 Streaming from Groq API..."))
                    .handle((chatResponse, sink) -> {
                        // Safe handling of all potential nulls
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
                            sink.next(content);
                            log.debug("📨 Chunk: {} chars", content.length());
                        }
                    })
                    .cast(String.class)
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
