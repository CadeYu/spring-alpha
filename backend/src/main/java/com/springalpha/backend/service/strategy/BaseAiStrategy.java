package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import lombok.extern.slf4j.Slf4j;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * Base class for all AI analysis strategies.
 * Provides common functionality for prompt building, JSON parsing, and
 * validation.
 */
@Slf4j
public abstract class BaseAiStrategy implements AiAnalysisStrategy {

    protected final PromptTemplateService promptService;
    protected final AnalysisReportValidator validator;
    protected final ObjectMapper objectMapper;

    protected BaseAiStrategy(
            PromptTemplateService promptService,
            AnalysisReportValidator validator,
            ObjectMapper objectMapper) {
        this.promptService = promptService;
        this.validator = validator;
        this.objectMapper = objectMapper;
    }

    /**
     * Template method that orchestrates the analysis flow.
     * Subclasses only need to implement callLlmApi().
     */
    @Override
    public Flux<AnalysisReport> analyze(AnalysisContract contract, String lang) {
        log.info("🤖 Analyzing {} with strategy: {}", contract.getTicker(), getName());

        // 1. Build prompts (both system and user in same language)
        String systemPrompt = promptService.getSystemPrompt(lang);
        String userPrompt = promptService.buildUserPrompt(contract, lang);

        // 2. Call LLM API (implemented by subclass)
        return callLlmApi(systemPrompt, userPrompt, lang)
                // 3. Accumulate streaming response
                .reduce("", String::concat)
                // 4. Parse and validate
                .flatMap(jsonResponse -> parseAndValidate(jsonResponse, contract, lang))
                .flux();
    }

    /**
     * Abstract method for subclasses to implement their specific LLM API calls.
     * Should return a stream of JSON chunks that will be concatenated.
     */
    protected abstract Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang);

    /**
     * Parse JSON response to AnalysisReport and validate against facts
     */
    private Mono<AnalysisReport> parseAndValidate(String jsonResponse, AnalysisContract contract, String lang) {
        try {
            // Parse JSON
            AnalysisReport report = parseJsonResponse(jsonResponse);

            // Add metadata
            enrichMetadata(report, lang);

            // Validate against financial facts
            AnalysisReportValidator.ValidationResult validationResult = validator.validate(report,
                    contract.getFinancialFacts());

            if (!validationResult.isValid()) {
                log.error("❌ Validation failed for {}: {}", getName(), validationResult.getErrors());
                // In production, you might want to retry or fallback
                // For now, we'll still return the report but log the errors
            }

            if (!validationResult.getWarnings().isEmpty()) {
                log.warn("⚠️ Validation warnings for {}: {}", getName(), validationResult.getWarnings());
            }

            return Mono.just(report);

        } catch (Exception e) {
            log.error("Failed to parse LLM response from {}", getName(), e);
            return Mono.error(new RuntimeException("Failed to parse LLM response: " + e.getMessage(), e));
        }
    }

    /**
     * Parse JSON string to AnalysisReport object
     */
    protected AnalysisReport parseJsonResponse(String jsonResponse) throws JsonProcessingException {
        // Try to extract JSON from markdown code blocks if present
        String cleanJson = extractJsonFromMarkdown(jsonResponse);

        return objectMapper.readValue(cleanJson, AnalysisReport.class);
    }

    /**
     * Extract JSON from markdown code blocks (```json ... ```)
     */
    private String extractJsonFromMarkdown(String response) {
        // Check if response is wrapped in markdown code block
        if (response.contains("```json")) {
            int start = response.indexOf("```json") + 7;
            int end = response.lastIndexOf("```");
            if (end > start) {
                return response.substring(start, end).trim();
            }
        } else if (response.contains("```")) {
            int start = response.indexOf("```") + 3;
            int end = response.lastIndexOf("```");
            if (end > start) {
                return response.substring(start, end).trim();
            }
        }

        return response.trim();
    }

    /**
     * Add metadata to the report
     */
    private void enrichMetadata(AnalysisReport report, String lang) {
        if (report.getMetadata() == null) {
            report.setMetadata(AnalysisReport.AnalysisMetadata.builder()
                    .modelName(getName())
                    .generatedAt(LocalDateTime.now().format(DateTimeFormatter.ISO_DATE_TIME))
                    .language(lang)
                    .build());
        } else {
            report.getMetadata().setModelName(getName());
            report.getMetadata().setGeneratedAt(LocalDateTime.now().format(DateTimeFormatter.ISO_DATE_TIME));
            report.getMetadata().setLanguage(lang);
        }
    }
}
