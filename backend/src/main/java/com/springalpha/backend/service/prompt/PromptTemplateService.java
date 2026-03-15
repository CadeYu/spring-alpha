package com.springalpha.backend.service.prompt;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.contract.CompanyProfile;
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

    private static final int DEFAULT_MAX_SECTION_CHARS = Integer.MAX_VALUE;
    private static final int DEFAULT_MAX_TOTAL_CHARS = Integer.MAX_VALUE;
    private static final int INSIGHTS_MAX_SECTION_CHARS = 2600;
    private static final int INSIGHTS_MAX_TOTAL_CHARS = 5200;
    private static final int CHATA_SUMMARY_MAX_SECTION_CHARS = 1800;
    private static final int CHATA_SUMMARY_MAX_TOTAL_CHARS = 5200;
    private static final int CHATA_INSIGHTS_MAX_SECTION_CHARS = 1500;
    private static final int CHATA_INSIGHTS_MAX_TOTAL_CHARS = 3200;
    private static final int GROQ_SUMMARY_MAX_SECTION_CHARS = 1800;
    private static final int GROQ_SUMMARY_MAX_TOTAL_CHARS = 4200;
    private static final int GROQ_INSIGHTS_MAX_SECTION_CHARS = 1800;
    private static final int GROQ_INSIGHTS_MAX_TOTAL_CHARS = 3600;

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
     * 构建 ChatAnywhere 免费版专用 Summary Prompt
     * <p>
     * ChatAnywhere 免费 API 的真实 token 限制比字符截断更严格，
     * 因此这里直接在模板层缩小证据预算。
     */
    public String buildChatAnywhereSummaryPrompt(AnalysisContract contract, String lang) {
        return buildPromptFromTemplate("prompts/user/task_summary.txt", contract, lang,
                CHATA_SUMMARY_MAX_SECTION_CHARS, CHATA_SUMMARY_MAX_TOTAL_CHARS);
    }

    /**
     * 构建 Groq 专用 Summary Prompt
     * <p>
     * Groq 更容易被 TPM / 速率限制击中，因此这里使用更紧的证据预算。
     */
    public String buildGroqSummaryPrompt(AnalysisContract contract, String lang) {
        return buildPromptFromTemplate("prompts/user/task_summary.txt", contract, lang,
                GROQ_SUMMARY_MAX_SECTION_CHARS, GROQ_SUMMARY_MAX_TOTAL_CHARS);
    }

    /**
     * 构建 Task 2 Prompt: DuPont Analysis, Insight Engine
     */
    public String buildInsightsPrompt(AnalysisContract contract, String lang) {
        return buildPromptFromTemplate("prompts/user/task_insights.txt", contract, lang,
                INSIGHTS_MAX_SECTION_CHARS, INSIGHTS_MAX_TOTAL_CHARS);
    }

    /**
     * 构建 ChatAnywhere 免费版专用 Insights Prompt
     */
    public String buildChatAnywhereInsightsPrompt(AnalysisContract contract, String lang) {
        return buildPromptFromTemplate("prompts/user/task_insights.txt", contract, lang,
                CHATA_INSIGHTS_MAX_SECTION_CHARS, CHATA_INSIGHTS_MAX_TOTAL_CHARS);
    }

    /**
     * 构建 Groq 专用 Insights Prompt
     * <p>
     * Groq 的 Insights prompt 再进一步缩小，优先保证请求能稳定完成。
     */
    public String buildGroqInsightsPrompt(AnalysisContract contract, String lang) {
        return buildPromptFromTemplate("prompts/user/task_insights.txt", contract, lang,
                GROQ_INSIGHTS_MAX_SECTION_CHARS, GROQ_INSIGHTS_MAX_TOTAL_CHARS);
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
        return buildPromptFromTemplate(templatePath, contract, lang, DEFAULT_MAX_SECTION_CHARS, DEFAULT_MAX_TOTAL_CHARS);
    }

    private String buildPromptFromTemplate(String templatePath, AnalysisContract contract, String lang,
            int maxSectionChars, int maxTotalChars) {
        String template = loadTemplate(templatePath);

        Map<String, String> variables = new HashMap<>();
        variables.put("ticker", contract.getTicker());
        variables.put("period", contract.getPeriod());
        variables.put("reportType", normalizeReportType(contract.getReportType()));
        variables.put("reportTypeLabel", describeReportType(contract.getReportType()));
        variables.put("reportModeGuidance", buildReportModeGuidance(contract.getReportType()));
        variables.put("financialFacts", formatFinancialFacts(contract));
        variables.put("companyProfile", formatCompanyProfile(contract));
        variables.put("businessSignals", formatBusinessSignals(contract));
        variables.put("textEvidence", formatTextEvidence(contract, maxSectionChars, maxTotalChars));
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
        return formatTextEvidence(contract, DEFAULT_MAX_SECTION_CHARS, DEFAULT_MAX_TOTAL_CHARS);
    }

    private String formatBusinessSignals(AnalysisContract contract) {
        BusinessSignals signals = contract.getBusinessSignals();
        if (signals == null || signals.isEmpty()) {
            return "No structured business signals were extracted. Use TEXTUAL EVIDENCE conservatively and avoid repeating metric cards.";
        }

        StringBuilder sb = new StringBuilder();
        appendSignalSection(sb, "Segment Performance", signals.getSegmentPerformance());
        appendSignalSection(sb, "Product & Service Updates", signals.getProductServiceUpdates());
        appendSignalSection(sb, "Management Focus", signals.getManagementFocus());
        appendSignalSection(sb, "Strategic Moves", signals.getStrategicMoves());
        appendSignalSection(sb, "Capex / Investment Direction", signals.getCapexSignals());
        appendSignalSection(sb, "Risk & Competition Signals", signals.getRiskSignals());

        if (signals.getEvidenceRefs() != null && !signals.getEvidenceRefs().isEmpty()) {
            sb.append("### Evidence Refs\n");
            signals.getEvidenceRefs().stream().limit(4).forEach(ref -> sb.append("- ")
                    .append(ref.getTopic())
                    .append(" [")
                    .append(ref.getSection())
                    .append("]: ")
                    .append(ref.getExcerpt())
                    .append('\n'));
            sb.append('\n');
        }

        return sb.toString().trim();
    }

    private String formatCompanyProfile(AnalysisContract contract) {
        CompanyProfile profile = contract.getCompanyProfile();
        if (profile == null || profile.isEmpty()) {
            return "No cached company profile is available yet. Infer company identity conservatively from FINANCIAL FACTS, BUSINESS SIGNALS, and TEXTUAL EVIDENCE.";
        }

        try {
            return objectMapper.writerWithDefaultPrettyPrinter().writeValueAsString(profile);
        } catch (Exception e) {
            log.error("Failed to serialize company profile", e);
            return "{}";
        }
    }

    private String formatTextEvidence(AnalysisContract contract, int maxSectionChars, int maxTotalChars) {
        if (contract.getTextEvidence() == null || contract.getTextEvidence().isEmpty()) {
            return "";
        }

        StringBuilder sb = new StringBuilder();
        contract.getTextEvidence().forEach((key, value) -> {
            if (sb.length() >= maxTotalChars) {
                return;
            }

            String sectionValue = value == null ? "" : value;
            boolean truncatedSection = sectionValue.length() > maxSectionChars;
            if (truncatedSection) {
                sectionValue = sectionValue.substring(0, maxSectionChars)
                        + "\n[truncated for prompt budget]";
            }

            int remainingChars = maxTotalChars - sb.length();
            if (remainingChars <= 0) {
                return;
            }

            String renderedSection = "## " + key + "\n" + sectionValue + "\n\n";
            if (renderedSection.length() > remainingChars) {
                int availableForBody = Math.max(0, remainingChars - ("## " + key + "\n\n").length());
                String shortened = sectionValue;
                if (availableForBody < sectionValue.length()) {
                    shortened = sectionValue.substring(0, Math.max(0, availableForBody))
                            + "\n[truncated for prompt budget]";
                }
                renderedSection = "## " + key + "\n" + shortened + "\n\n";
            }

            if (renderedSection.length() <= remainingChars) {
                sb.append(renderedSection);
            }
        });

        if (sb.length() >= maxTotalChars && maxTotalChars != Integer.MAX_VALUE) {
            sb.append("[additional evidence omitted for prompt budget]\n");
        }
        return sb.toString();
    }

    private void appendSignalSection(StringBuilder sb, String label, java.util.List<BusinessSignals.SignalItem> items) {
        if (items == null || items.isEmpty()) {
            return;
        }

        sb.append("### ").append(label).append('\n');
        items.stream().limit(3).forEach(item -> sb.append("- ")
                .append(item.getTitle())
                .append(": ")
                .append(item.getSummary())
                .append(" [")
                .append(item.getEvidenceSection())
                .append("]\n"));
        sb.append('\n');
    }

    // Output requirement task list removed since it is now baked into the
    // individual prompt templates

    /**
     * Resolve lang code to full language name for prompt clarity
     */
    private String resolveLanguageName(String lang) {
        return "zh".equalsIgnoreCase(lang) ? "Chinese (中文)" : "English";
    }

    private String normalizeReportType(String reportType) {
        return "quarterly";
    }

    private String describeReportType(String reportType) {
        return "latest quarterly filing";
    }

    private String buildReportModeGuidance(String reportType) {
        return """
                REPORT MODE GUIDANCE:
                - Treat this as a quarterly filing by default.
                - Describe results as a quarter, not as a full fiscal year, unless FINANCIAL FACTS explicitly indicate FY.
                - Prefer quarter-specific language such as "this quarter" or "the reported quarter".
                - Do not infer full-year trends from a single quarter unless the evidence clearly supports it.
                """;
    }
}
