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
 * Prompt 模板服务
 * <p>
 * 负责加载和渲染 Prompt 模板 (resources/prompts/*.txt)。
 * 核心功能是 **变量替换** (Variable Substitution) 和 **多语言支持**。
 * <p>
 * 所有的 Prompt 都是文本文件，与代码分离，方便非技术人员修改。
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
     * 获取 System Prompt (系统角色设定)
     * <p>
     * 使用统一模板，通过 {{language}} 变量控制输出语言。
     * 确保中英文分析内容结构完全一致。
     */
    public String getSystemPrompt(String lang) {
        String template = loadTemplate("prompts/system/financial_analyst_system.txt");
        String language = resolveLanguageName(lang);
        return template.replace("{{language}}", language);
    }

    /**
     * 构建 Task 1 Prompt: Executive Summary, Key Metrics, Bull/Bear Case
     */
    public String buildSummaryPrompt(AnalysisContract contract, String lang) {
        return buildPromptFromTemplate("prompts/user/task_summary.txt", contract, lang);
    }

    /**
     * 构建 Task 2 Prompt: DuPont Analysis, Insight Engine
     */
    public String buildInsightsPrompt(AnalysisContract contract, String lang) {
        return buildPromptFromTemplate("prompts/user/task_insights.txt", contract, lang);
    }

    /**
     * 构建 Task 3 Prompt: Factor Analysis (Bridges), Topic Trends
     */
    public String buildFactorsPrompt(AnalysisContract contract, String lang) {
        return buildPromptFromTemplate("prompts/user/task_factors.txt", contract, lang);
    }

    /**
     * 构建 Task 4 Prompt: Business Drivers, Risk Factors
     */
    public String buildDriversPrompt(AnalysisContract contract, String lang) {
        return buildPromptFromTemplate("prompts/user/task_drivers.txt", contract, lang);
    }

    /**
     * 内部通用模板填充逻辑
     */
    private String buildPromptFromTemplate(String templatePath, AnalysisContract contract, String lang) {
        String template = loadTemplate(templatePath);

        Map<String, String> variables = new HashMap<>();
        variables.put("ticker", contract.getTicker());
        variables.put("period", contract.getPeriod());
        variables.put("financialFacts", formatFinancialFacts(contract));
        variables.put("textEvidence", formatTextEvidence(contract));
        variables.put("evidenceAvailability", contract.isEvidenceAvailable() ? "AVAILABLE" : "UNAVAILABLE");
        variables.put("evidenceStatusMessage",
                contract.getEvidenceStatusMessage() == null ? "" : contract.getEvidenceStatusMessage());
        variables.put("language", resolveLanguageName(lang));

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
            return "";
        }

        StringBuilder sb = new StringBuilder();
        contract.getTextEvidence().forEach((key, value) -> {
            sb.append("## ").append(key).append("\n");
            sb.append(value).append("\n\n");
        });
        return sb.toString();
    }

    // Output requirement task list removed since it is now baked into the
    // individual prompt templates

    /**
     * Resolve lang code to full language name for prompt clarity
     */
    private String resolveLanguageName(String lang) {
        return "zh".equalsIgnoreCase(lang) ? "Chinese (中文)" : "English";
    }
}
