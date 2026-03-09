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
import java.util.regex.Pattern;

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

    private static final Pattern SENTENCE_SPLIT_PATTERN = Pattern.compile("(?<=[.!?。！？])\\s+");

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
    public Flux<AnalysisReport> analyze(AnalysisContract contract, String lang, String apiKeyOverride) {
        log.info("🤖 Starting Map-Reduce Agentic Analysis for {} with strategy: {}", contract.getTicker(), getName());

        String systemPrompt = promptService.getSystemPrompt(lang);

        // Execute agents SEQUENTIALLY to avoid API rate limits (429).
        // Each agent completes fully before the next starts.
        // Frontend still gets progressive rendering — each completed agent
        // emits its partial AnalysisReport immediately via SSE.
        Mono<AnalysisReport> summaryAgent = executeAgent(
                systemPrompt,
                promptService.buildSummaryPrompt(contract, lang),
                contract, lang, apiKeyOverride, "SummaryAgent");

        Mono<AnalysisReport> insightsAgent = executeAgent(
                systemPrompt,
                promptService.buildInsightsPrompt(contract, lang),
                contract, lang, apiKeyOverride, "InsightsAgent");

        Mono<AnalysisReport> factorsAgent = executeAgent(
                systemPrompt,
                promptService.buildFactorsPrompt(contract, lang),
                contract, lang, apiKeyOverride, "FactorsAgent");

        Mono<AnalysisReport> driversAgent = executeAgent(
                systemPrompt,
                promptService.buildDriversPrompt(contract, lang),
                contract, lang, apiKeyOverride, "DriversAgent");

        // concat = sequential: Summary → Insights → Factors → Drivers
        return Flux.concat(summaryAgent, insightsAgent, factorsAgent, driversAgent);
    }

    /**
     * Executes a single prompt agent, collects the result, parses and validates it.
     * Each agent is isolated — if one fails, it returns an empty report instead of
     * killing the entire concat pipeline.
     */
    private Mono<AnalysisReport> executeAgent(String systemPrompt, String userPrompt, AnalysisContract contract,
            String lang, String apiKeyOverride, String agentName) {
        log.debug("🚀 Launching {}", agentName);
        return callLlmApi(systemPrompt, userPrompt, lang, apiKeyOverride)
                .reduce("", String::concat)
                .flatMap(jsonResponse -> parseAndValidate(jsonResponse, contract, lang, agentName))
                .timeout(java.time.Duration.ofSeconds(60))
                .onErrorResume(e -> {
                    log.error("⚠️ {} failed ({}), returning empty report. Remaining agents will continue.",
                            agentName, e.getMessage());
                    return Mono.just(AnalysisReport.builder().build());
                });
    }

    /**
     * 抽象方法：调用 LLM API
     * <p>
     * 子类需实现具体的 API 调用逻辑 (使用 WebClient 或 SDK)。
     * 返回 Flux<String> 以支持流式传输 (Streaming)。
     */
    protected abstract Flux<String> callLlmApi(String systemPrompt, String userPrompt, String lang,
            String apiKeyOverride);

    /**
     * Parse JSON response to AnalysisReport and validate against facts
     */
    private Mono<AnalysisReport> parseAndValidate(String jsonResponse, AnalysisContract contract, String lang,
            String agentName) {
        try {
            // Debug: log raw response info
            log.debug("📝 {} raw response length: {} chars, preview: {}", agentName,
                    jsonResponse.length(),
                    jsonResponse.substring(0, Math.min(500, jsonResponse.length())));

            // Parse JSON fragment
            AnalysisReport report = parseJsonResponse(jsonResponse);
            log.info("✅ {} completed successfully.", agentName);

            normalizeCoreThesis(report);
            normalizeSentiments(report);

            // Add metadata
            enrichMetadata(report, lang);
            applySourceContext(report, contract, agentName);

            // Validate against financial facts FIRST (before FMP injection)
            if (report.getKeyMetrics() != null && !report.getKeyMetrics().isEmpty()) {
                AnalysisReportValidator.ValidationResult validationResult = validator.validate(report,
                        contract.getFinancialFacts());

                if (!validationResult.isValid()) {
                    log.error("❌ Validation failed for {} [{}]: {}", getName(), agentName,
                            validationResult.getErrors());
                }

                if (!validationResult.getWarnings().isEmpty()) {
                    log.warn("⚠️ Validation warnings for {} [{}]: {}", getName(), agentName,
                            validationResult.getWarnings());
                }

                // THEN inject currency and fixed key metrics from FMP data
                if (contract.getFinancialFacts() != null) {
                    report.setCurrency(contract.getFinancialFacts().getCurrency());
                    report.setCompanyName(contract.getFinancialFacts().getCompanyName());
                    report.setPeriod(contract.getFinancialFacts().getPeriod());
                    report.setFilingDate(contract.getFinancialFacts().getFilingDate());
                    injectFixedKeyMetrics(report, contract.getFinancialFacts(), lang);
                }
            }

            // Validate citations against text evidence
            if (report.getCitations() != null && !report.getCitations().isEmpty()) {
                String fullSourceText = contract.getTextEvidence() == null ? "" : String.join("\n",
                        contract.getTextEvidence().values());
                validator.validateCitations(report, fullSourceText);
            }

            if (report.getCitations() != null && report.getCitations().isEmpty()) {
                report.setCitations(null);
            }

            return Mono.just(report);

        } catch (Exception e) {
            log.error("❌ Failed to parse LLM response from {} [{}]", getName(), agentName, e);
            // Return an empty report fragment on failure so it doesn't crash the Flux
            // stream
            return Mono.just(new AnalysisReport());
        }
    }

    /**
     * Parse JSON string to AnalysisReport object.
     * Includes a lenient fallback: if initial parse fails (e.g., LLM puts strings
     * where arrays are expected), fix type mismatches in the JSON tree and retry.
     */
    protected AnalysisReport parseJsonResponse(String jsonResponse) throws JsonProcessingException {
        // Try to extract JSON from markdown code blocks if present
        String cleanJson = extractJsonFromMarkdown(jsonResponse);

        // Unwrap {"analysisReport": {...}} if LLM wraps the response
        try {
            var tree = objectMapper.readTree(cleanJson);
            if (tree.has("analysisReport") && tree.size() == 1) {
                cleanJson = tree.get("analysisReport").toString();
                log.debug("🔄 Unwrapped 'analysisReport' wrapper from LLM response");
            }
        } catch (Exception e) {
            // If tree parsing fails, just try direct deserialization below
        }

        try {
            return objectMapper.readValue(cleanJson, AnalysisReport.class);
        } catch (JsonProcessingException e) {
            // Lenient fallback: LLMs sometimes put strings where arrays are expected
            // (e.g., "accountingChanges": "None" instead of an array).
            // Fix type mismatches in the JSON tree instead of stripping entire sections.
            log.warn("⚠️ Initial JSON parse failed ({}), trying lenient parse by fixing type mismatches...",
                    e.getOriginalMessage());
            try {
                var tree = (com.fasterxml.jackson.databind.node.ObjectNode) objectMapper.readTree(cleanJson);
                fixTypeMismatches(tree);
                AnalysisReport report = objectMapper.treeToValue(tree, AnalysisReport.class);
                log.info("✅ Lenient parse succeeded (fixed type mismatches in JSON tree)");
                return report;
            } catch (Exception fallbackError) {
                // If even the fallback fails, throw the original error
                throw e;
            }
        }
    }

    /**
     * Fix common type mismatches in LLM-generated JSON.
     * GPT-4o-mini sometimes puts strings where arrays are expected
     * (e.g., "accountingChanges": "None" instead of []).
     * This walks the tree and fixes such mismatches in-place.
     */
    private void fixTypeMismatches(com.fasterxml.jackson.databind.node.ObjectNode root) {
        // Fields that must be arrays (LLMs sometimes put strings here)
        var arrayFields = java.util.Set.of(
                "accountingChanges", "rootCauseAnalysis",
                "revenueBridge", "marginBridge", "topicTrends",
                "keyPoints", "supportingEvidence", "watchItems");

        fixNodeRecursive(root, arrayFields);
    }

    private void fixNodeRecursive(com.fasterxml.jackson.databind.node.ObjectNode node,
            java.util.Set<String> arrayFields) {
        var fieldNames = new java.util.ArrayList<String>();
        node.fieldNames().forEachRemaining(fieldNames::add);

        for (String field : fieldNames) {
            var value = node.get(field);
            if (arrayFields.contains(field) && !value.isArray()) {
                // Convert string/number to empty array
                node.set(field, objectMapper.createArrayNode());
                log.debug("🔧 Fixed type mismatch: '{}' was {} → converted to empty array", field,
                        value.getNodeType());
            } else if (value.isObject()) {
                fixNodeRecursive((com.fasterxml.jackson.databind.node.ObjectNode) value, arrayFields);
            }
        }
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

    /**
     * Keep legacy summary consumers working while the UI migrates to the new
     * structured thesis object.
     */
    protected void normalizeCoreThesis(AnalysisReport report) {
        if (report == null) {
            return;
        }

        AnalysisReport.CoreThesis thesis = report.getCoreThesis();
        String legacySummary = trimToNull(report.getExecutiveSummary());

        if (thesis == null && legacySummary != null) {
            thesis = AnalysisReport.CoreThesis.builder()
                    .headline(createHeadlineFromText(legacySummary))
                    .summary(legacySummary)
                    .build();
            report.setCoreThesis(thesis);
        }

        if (thesis == null) {
            return;
        }

        thesis.setVerdict(normalizeVerdict(thesis.getVerdict()));
        thesis.setHeadline(trimToNull(thesis.getHeadline()));
        thesis.setSummary(trimToNull(thesis.getSummary()));
        thesis.setKeyPoints(cleanStringList(thesis.getKeyPoints()));
        thesis.setWatchItems(cleanStringList(thesis.getWatchItems()));
        thesis.setSupportingEvidence(cleanSupportingEvidence(thesis.getSupportingEvidence()));

        if (thesis.getHeadline() == null) {
            thesis.setHeadline(createHeadlineFromText(
                    thesis.getSummary() != null ? thesis.getSummary() : legacySummary));
        }
        if (thesis.getSummary() == null) {
            thesis.setSummary(legacySummary != null ? legacySummary : thesis.getHeadline());
        }
        if (report.getExecutiveSummary() == null || report.getExecutiveSummary().isBlank()) {
            report.setExecutiveSummary(thesis.getSummary() != null ? thesis.getSummary() : thesis.getHeadline());
        }
    }

    protected void normalizeSentiments(AnalysisReport report) {
        if (report == null || report.getKeyMetrics() == null) {
            return;
        }

        for (AnalysisReport.MetricInsight metric : report.getKeyMetrics()) {
            if (metric == null) {
                continue;
            }
            metric.setSentiment(normalizeSentimentValue(metric.getSentiment()));
        }
    }

    private String normalizeSentimentValue(String sentiment) {
        if (sentiment == null) {
            return null;
        }

        String normalized = sentiment.trim().toLowerCase(Locale.ROOT);
        return switch (normalized) {
            case "positive", "bullish", "pos", "利好", "正面", "积极", "看多", "上涨" -> "positive";
            case "negative", "bearish", "neg", "利空", "负面", "消极", "看空", "下滑", "下降" -> "negative";
            case "neutral", "mixed", "中性", "持平", "一般" -> "neutral";
            default -> sentiment;
        };
    }

    private void applySourceContext(AnalysisReport report, AnalysisContract contract, String agentName) {
        if (report.getSourceContext() != null && report.getSourceContext().getStatus() != null
                && !report.getSourceContext().getStatus().isBlank()) {
            return;
        }

        if (contract.isEvidenceAvailable()) {
            report.setSourceContext(AnalysisReport.SourceContext.builder()
                    .status("GROUNDED")
                    .message("Grounded in SEC text evidence.")
                    .build());
            return;
        }

        report.setSourceContext(AnalysisReport.SourceContext.builder()
                .status("DEGRADED")
                .message(contract.getEvidenceStatusMessage() == null || contract.getEvidenceStatusMessage().isBlank()
                        ? "Text evidence was unavailable for this run."
                        : contract.getEvidenceStatusMessage())
                .build());
        report.setCitations(null);
        log.info("ℹ️ {} produced report without grounded citations because evidence is unavailable", agentName);
    }

    private List<String> cleanStringList(List<String> items) {
        if (items == null) {
            return null;
        }
        return items.stream()
                .map(this::trimToNull)
                .filter(Objects::nonNull)
                .toList();
    }

    private List<AnalysisReport.SupportingEvidence> cleanSupportingEvidence(
            List<AnalysisReport.SupportingEvidence> items) {
        if (items == null) {
            return null;
        }
        return items.stream()
                .map(item -> {
                    if (item == null) {
                        return null;
                    }
                    String label = trimToNull(item.getLabel());
                    String detail = trimToNull(item.getDetail());
                    if (label == null && detail == null) {
                        return null;
                    }
                    return AnalysisReport.SupportingEvidence.builder()
                            .label(label != null ? label : "Evidence")
                            .detail(detail != null ? detail : "")
                            .build();
                })
                .filter(Objects::nonNull)
                .toList();
    }

    private String normalizeVerdict(String verdict) {
        String normalized = trimToNull(verdict);
        if (normalized == null) {
            return null;
        }
        String lower = normalized.toLowerCase(Locale.ROOT);
        return switch (lower) {
            case "positive", "bullish", "bull" -> "positive";
            case "negative", "bearish", "bear" -> "negative";
            case "mixed", "neutral" -> "mixed";
            default -> normalized;
        };
    }

    private String createHeadlineFromText(String text) {
        String source = trimToNull(text);
        if (source == null) {
            return null;
        }
        String[] parts = SENTENCE_SPLIT_PATTERN.split(source);
        String headline = parts.length > 0 ? parts[0].trim() : source;
        return headline.length() > 120 ? headline.substring(0, 117).trim() + "..." : headline;
    }

    private String trimToNull(String value) {
        if (value == null) {
            return null;
        }
        String trimmed = value.trim();
        return trimmed.isEmpty() ? null : trimmed;
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
                    .modelName(getDisplayName())
                    .generatedAt(LocalDateTime.now().format(DateTimeFormatter.ISO_DATE_TIME))
                    .language(lang)
                    .build());
        } else {
            report.getMetadata().setModelName(getDisplayName());
            report.getMetadata().setGeneratedAt(LocalDateTime.now().format(DateTimeFormatter.ISO_DATE_TIME));
            report.getMetadata().setLanguage(lang);
        }
    }
}
