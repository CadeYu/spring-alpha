package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import lombok.extern.slf4j.Slf4j;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

/**
 * AI 策略基类 (Template Method Pattern)
 * <p>
 * 这使用 **模板方法模式** 定义了分析的标准流程。
 * 子类只需要实现 `callLlmApi` (如何调 API)，其余的 Prompt 构建、流式聚合、
 * JSON 解析、数据校验都由基类统一处理。
 * 这样可以避免代码重复，确保障眼全性 (Validation)。
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
     * 分析流程模板方法 (The Orchestrator)
     * <p>
     * 1. **Prepare**: 根据语言 (zh/en) 加载 Prompt 模板，并填入数据。
     * 2. **Execute**: 调用子类的 `callLlmApi` 获取流式响应。
     * 3. **Accumulate**: 将流式碎片 (Tokens) 拼成完整的 JSON 字符串。
     * 4. **Validate**: 解析 JSON 并校验数据准确性 (Anti-Hallucination)。
     */
    @Override
    public Flux<AnalysisReport> analyze(AnalysisContract contract, String lang) {
        log.info("🤖 Analyzing {} with strategy: {}", contract.getTicker(), getName());

        // 1. 构建 Prompt (根据语言选择中文或英文模板)
        String systemPrompt = promptService.getSystemPrompt(lang);
        String userPrompt = promptService.buildUserPrompt(contract, lang);

        // 2. 调用 LLM API (多态调用子类实现)
        return callLlmApi(systemPrompt, userPrompt, lang)
                // 3. 聚合流式响应 (Reduce stream chunks into full string)
                .reduce("", String::concat)
                // 4. 解析与校验 (Parse & Validate)
                .flatMap(jsonResponse -> parseAndValidate(jsonResponse, contract, lang))
                .flux();
    }

    /**
     * 抽象方法：调用 LLM API
     * <p>
     * 子类需实现具体的 API 调用逻辑 (使用 WebClient 或 SDK)。
     * 返回 Flux<String> 以支持流式传输 (Streaming)。
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

            // Validate against financial facts FIRST (before FMP injection)
            // This way the validator checks AI-generated values which should match raw FMP
            // numbers
            AnalysisReportValidator.ValidationResult validationResult = validator.validate(report,
                    contract.getFinancialFacts());

            if (!validationResult.isValid()) {
                log.error("❌ Validation failed for {}: {}", getName(), validationResult.getErrors());
            }

            if (!validationResult.getWarnings().isEmpty()) {
                log.warn("⚠️ Validation warnings for {}: {}", getName(), validationResult.getWarnings());
            }

            // THEN inject currency and fixed key metrics from FMP data
            // This overwrites AI-generated keyMetrics with formatted FMP hard data
            if (contract.getFinancialFacts() != null) {
                report.setCurrency(contract.getFinancialFacts().getCurrency());
                injectFixedKeyMetrics(report, contract.getFinancialFacts(), lang);
            }

            // Validate citations against text evidence
            if (contract.getTextEvidence() != null) {
                String fullSourceText = String.join("\n", contract.getTextEvidence().values());
                validator.validateCitations(report, fullSourceText);
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
     * 用 FMP 硬数据覆盖 keyMetrics 的数值，保留 AI 生成的 interpretation 和 sentiment。
     * 固定输出 4 个指标：Revenue, Gross Margin, Net Income, Revenue YoY Growth。
     */
    private void injectFixedKeyMetrics(AnalysisReport report, FinancialFacts facts, String lang) {
        boolean isZh = "zh".equalsIgnoreCase(lang);

        // Build a lookup map from AI-generated metrics (fuzzy match by name keywords)
        Map<String, AnalysisReport.MetricInsight> aiMetrics = new HashMap<>();
        if (report.getKeyMetrics() != null) {
            for (AnalysisReport.MetricInsight m : report.getKeyMetrics()) {
                if (m.getMetricName() != null) {
                    aiMetrics.put(m.getMetricName().toLowerCase(), m);
                }
            }
        }

        List<AnalysisReport.MetricInsight> fixed = new ArrayList<>();

        // 1. Revenue
        fixed.add(buildMetric(
                isZh ? "营收" : "Revenue",
                formatCurrency(facts.getRevenue(), facts.getCurrency()),
                findAiInsight(aiMetrics, "revenue", "营收"),
                facts.getRevenueYoY() != null && facts.getRevenueYoY().compareTo(BigDecimal.ZERO) >= 0
                        ? "positive"
                        : "negative"));

        // 2. Gross Margin
        fixed.add(buildMetric(
                isZh ? "毛利率" : "Gross Margin",
                formatPercent(facts.getGrossMargin()),
                findAiInsight(aiMetrics, "gross margin", "毛利率"),
                facts.getGrossMarginChange() != null && facts.getGrossMarginChange().compareTo(BigDecimal.ZERO) >= 0
                        ? "positive"
                        : "negative"));

        // 3. Net Income
        fixed.add(buildMetric(
                isZh ? "净利润" : "Net Income",
                formatCurrency(facts.getNetIncome(), facts.getCurrency()),
                findAiInsight(aiMetrics, "net income", "净利润", "net profit"),
                facts.getNetMarginChange() != null && facts.getNetMarginChange().compareTo(BigDecimal.ZERO) >= 0
                        ? "positive"
                        : "negative"));

        // 4. Revenue YoY Growth
        fixed.add(buildMetric(
                isZh ? "营收同比增长" : "Revenue YoY Growth",
                formatPercent(facts.getRevenueYoY()),
                findAiInsight(aiMetrics, "revenue yoy", "growth", "增长"),
                facts.getRevenueYoY() != null && facts.getRevenueYoY().compareTo(BigDecimal.ZERO) >= 0
                        ? "positive"
                        : "negative"));

        report.setKeyMetrics(fixed);
        log.info("✅ Injected 4 fixed keyMetrics from FMP data for {}", facts.getTicker());
    }

    private AnalysisReport.MetricInsight buildMetric(String name, String value,
            String interpretation, String sentiment) {
        return AnalysisReport.MetricInsight.builder()
                .metricName(name)
                .value(value)
                .interpretation(interpretation != null ? interpretation : "")
                .sentiment(sentiment)
                .build();
    }

    /**
     * Fuzzy-match AI-generated interpretation by metric name keywords.
     */
    private String findAiInsight(Map<String, AnalysisReport.MetricInsight> aiMetrics, String... keywords) {
        for (Map.Entry<String, AnalysisReport.MetricInsight> entry : aiMetrics.entrySet()) {
            String key = entry.getKey();
            for (String kw : keywords) {
                if (key.contains(kw.toLowerCase())) {
                    return entry.getValue().getInterpretation();
                }
            }
        }
        return null;
    }

    private String formatCurrency(BigDecimal value, String currency) {
        if (value == null)
            return "N/A";
        String prefix = "USD".equals(currency) ? "$" : (currency != null ? currency + " " : "");
        BigDecimal abs = value.abs();
        if (abs.compareTo(new BigDecimal("1000000000000")) >= 0) {
            return prefix + abs.divide(new BigDecimal("1000000000000"), 2, RoundingMode.HALF_UP) + "T";
        } else if (abs.compareTo(new BigDecimal("1000000000")) >= 0) {
            return prefix + abs.divide(new BigDecimal("1000000000"), 2, RoundingMode.HALF_UP) + "B";
        } else if (abs.compareTo(new BigDecimal("1000000")) >= 0) {
            return prefix + abs.divide(new BigDecimal("1000000"), 2, RoundingMode.HALF_UP) + "M";
        }
        return prefix + value.setScale(2, RoundingMode.HALF_UP).toPlainString();
    }

    private String formatPercent(BigDecimal value) {
        if (value == null)
            return "N/A";
        // FMP returns decimals (e.g., 0.0643 for 6.43%), multiply by 100
        return value.multiply(new BigDecimal("100")).setScale(2, RoundingMode.HALF_UP).toPlainString() + "%";
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
