package com.springalpha.backend.service.prompt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.AnalysisContract;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

/**
 * Service for loading and rendering prompt templates.
 * Handles template variable substitution and multi-language support.
 */
@Slf4j
@Service
public class PromptTemplateService {

    private final ObjectMapper objectMapper;
    private final Map<String, String> templateCache = new HashMap<>();

    public PromptTemplateService(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    /**
     * Get the system prompt that defines the AI's role
     * 
     * @param lang Language code ("en" or "zh")
     */
    public String getSystemPrompt(String lang) {
        String templatePath = "zh".equalsIgnoreCase(lang)
                ? "prompts/system/financial_analyst_system_zh.txt"
                : "prompts/system/financial_analyst_system.txt";

        return loadTemplate(templatePath);
    }

    /**
     * Build the user prompt by filling in template variables
     */
    public String buildUserPrompt(AnalysisContract contract, String lang) {
        // Select template based on language
        String templatePath = "zh".equalsIgnoreCase(lang)
                ? "prompts/user/analysis_request_zh.txt"
                : "prompts/user/analysis_request_en.txt";

        String template = loadTemplate(templatePath);

        // Prepare template variables
        Map<String, String> variables = new HashMap<>();
        variables.put("ticker", contract.getTicker());
        variables.put("period", contract.getPeriod());
        variables.put("financialFacts", formatFinancialFacts(contract));
        variables.put("textEvidence", formatTextEvidence(contract));
        variables.put("analysisTasks", formatAnalysisTasks(contract));

        // Render template
        return renderTemplate(template, variables);
    }

    /**
     * Load template from classpath (with caching)
     */
    private String loadTemplate(String path) {
        return templateCache.computeIfAbsent(path, p -> {
            try {
                ClassPathResource resource = new ClassPathResource(p);
                return new String(resource.getInputStream().readAllBytes(), StandardCharsets.UTF_8);
            } catch (IOException e) {
                log.error("Failed to load template: {}", p, e);
                throw new RuntimeException("Template not found: " + p, e);
            }
        });
    }

    /**
     * Replace {{variable}} placeholders in template
     */
    private String renderTemplate(String template, Map<String, String> variables) {
        String result = template;
        for (Map.Entry<String, String> entry : variables.entrySet()) {
            String placeholder = "{{" + entry.getKey() + "}}";
            result = result.replace(placeholder, entry.getValue());
        }
        return result;
    }

    /**
     * Format financial facts as JSON string
     */
    private String formatFinancialFacts(AnalysisContract contract) {
        try {
            return objectMapper.writerWithDefaultPrettyPrinter()
                    .writeValueAsString(contract.getFinancialFacts());
        } catch (Exception e) {
            log.error("Failed to serialize financial facts", e);
            return "{}";
        }
    }

    /**
     * Format text evidence as readable string
     */
    private String formatTextEvidence(AnalysisContract contract) {
        if (contract.getTextEvidence() == null || contract.getTextEvidence().isEmpty()) {
            return "No textual evidence available.";
        }

        StringBuilder sb = new StringBuilder();
        contract.getTextEvidence().forEach((key, value) -> {
            sb.append("## ").append(key).append("\n");
            sb.append(value).append("\n\n");
        });
        return sb.toString();
    }

    /**
     * Format analysis tasks as bullet list
     */
    private String formatAnalysisTasks(AnalysisContract contract) {
        if (contract.getAnalysisTasks() == null || contract.getAnalysisTasks().isEmpty()) {
            return "- Analyze key financial metrics and their business implications\n" +
                    "- Identify major business drivers and risks\n" +
                    "- Provide balanced bull/bear perspectives";
        }

        StringBuilder sb = new StringBuilder();
        for (String task : contract.getAnalysisTasks()) {
            sb.append("- ").append(task).append("\n");
        }
        return sb.toString();
    }
}
