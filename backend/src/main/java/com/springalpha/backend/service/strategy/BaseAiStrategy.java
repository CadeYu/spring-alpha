package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.BusinessSignals;
import com.springalpha.backend.financial.contract.CompanyProfile;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.service.prompt.PromptTemplateService;
import com.springalpha.backend.service.validation.AnalysisReportValidator;
import lombok.extern.slf4j.Slf4j;
import reactor.core.Exceptions;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;
import java.util.regex.Matcher;
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
    private static final Pattern NUMERIC_FRAGMENT_PATTERN = Pattern.compile(
            "(?:US\\$|\\$)?\\d[\\d,]*(?:\\.\\d+)?\\s*(?:%|亿美元|亿元|十亿美元|百万美元|万亿美元|billion|million|trillion|bn|mn|b|m)?",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern FISCAL_QUARTER_PATTERN = Pattern.compile("^FY\\s*(\\d{4})\\s*Q([1-4])$",
            Pattern.CASE_INSENSITIVE);
    private static final BigDecimal EXTREME_POSITIVE_YOY_THRESHOLD = new BigDecimal("5.00");
    private static final List<String> METRIC_RECAP_TERMS = List.of(
            "revenue", "gross margin", "operating margin", "net income", "net margin",
            "free cash flow", "cash flow", "revenue yoy", "eps", "roe", "roa",
            "营收", "收入", "毛利率", "营业利润", "净利润", "净利率", "自由现金流", "同比", "%", "亿美元");
    private static final List<String> BUSINESS_CONTEXT_TERMS = List.of(
            "advertising", "ads", "impression", "pricing", "reels", "threads", "ai",
            "recommendation", "engagement", "monetization", "platform", "cloud", "azure",
            "subscription", "service", "enterprise", "copilot", "demand", "product", "segment",
            "family of apps", "reality labs", "infrastructure", "capex", "data center", "gpu",
            "广告", "定价", "推荐", "变现", "平台", "云", "订阅", "服务", "企业", "需求", "产品", "业务线",
            "算力", "资本开支", "数据中心", "商业化", "管理层", "执行", "效率");

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
    protected Mono<AnalysisReport> executeAgent(String systemPrompt, String userPrompt, AnalysisContract contract,
            String lang, String apiKeyOverride, String agentName) {
        log.debug("🚀 Launching {}", agentName);
        return callLlmApi(systemPrompt, userPrompt, lang, apiKeyOverride)
                .reduce("", String::concat)
                .flatMap(jsonResponse -> parseAndValidate(jsonResponse, contract, lang, agentName))
                .timeout(java.time.Duration.ofSeconds(60))
                .onErrorResume(e -> {
                    Throwable root = Exceptions.unwrap(e);
                    if (containsProviderAuthenticationException(root)) {
                        return Mono.error(root);
                    }
                    log.error("⚠️ {} failed ({}), returning empty report. Remaining agents will continue.",
                            agentName, e.getMessage());
                    return Mono.just(AnalysisReport.builder().build());
                });
    }

    protected Mono<AnalysisReport> emitFallbackAgentReport(String agentName, AnalysisContract contract, String lang) {
        AnalysisReport fallbackReport = buildFallbackReportForAgent(agentName, contract, lang);
        applyStructuredContext(fallbackReport, contract);
        enrichMetadata(fallbackReport, lang);
        applySourceContext(fallbackReport, contract, agentName);
        return Mono.just(fallbackReport);
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
    protected Mono<AnalysisReport> parseAndValidate(String jsonResponse, AnalysisContract contract, String lang,
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
            if ("SummaryAgent".equals(agentName)) {
                enforceBusinessFirstCoreThesis(report, contract, lang);
            }
            normalizeSentiments(report);
            applyStructuredContext(report, contract);
            applyAgentFallbackIfNeeded(report, contract, lang, agentName);
            normalizeFiscalPeriodReferences(report, contract, lang);

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

            }

            if ("SummaryAgent".equals(agentName) && contract.getFinancialFacts() != null) {
                report.setCurrency(contract.getFinancialFacts().getCurrency());
                report.setCompanyName(contract.getFinancialFacts().getCompanyName());
                report.setReportType(contract.getReportType());
                report.setPeriod(contract.getFinancialFacts().getPeriod());
                report.setFilingDate(contract.getFinancialFacts().getFilingDate());
                injectFixedKeyMetrics(report, contract.getFinancialFacts(), lang);
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

            if ((report.getCitations() == null || report.getCitations().isEmpty())
                    && report.getSourceContext() != null
                    && "GROUNDED".equalsIgnoreCase(report.getSourceContext().getStatus())) {
                report.getSourceContext().setStatus("LIMITED");
                report.getSourceContext().setMessage(
                        "SEC source evidence was retrieved, but this run did not retain a display-ready high-confidence verbatim quote. The analysis remains grounded in the filing.");
            }

            return Mono.just(report);

        } catch (Exception e) {
            log.error("❌ Failed to parse LLM response from {} [{}]", getName(), agentName, e);
            AnalysisReport fallbackReport = buildFallbackReportForAgent(agentName, contract, lang);
            applyStructuredContext(fallbackReport, contract);
            normalizeFiscalPeriodReferences(fallbackReport, contract, lang);
            enrichMetadata(fallbackReport, lang);
            applySourceContext(fallbackReport, contract, agentName);
            return Mono.just(fallbackReport);
        }
    }

    private void applyStructuredContext(AnalysisReport report, AnalysisContract contract) {
        if (report == null || contract == null) {
            return;
        }

        if (report.getBusinessSignals() == null) {
            report.setBusinessSignals(contract.getBusinessSignals());
        }

        FinancialFacts facts = contract.getFinancialFacts();
        if (facts == null) {
            return;
        }

        if (report.getCurrency() == null) {
            report.setCurrency(facts.getCurrency());
        }
        if (report.getCompanyName() == null) {
            report.setCompanyName(facts.getCompanyName());
        }
        if (report.getReportType() == null) {
            report.setReportType(contract.getReportType());
        }
        if (report.getPeriod() == null) {
            report.setPeriod(facts.getPeriod());
        }
        if (report.getFilingDate() == null) {
            report.setFilingDate(facts.getFilingDate());
        }
    }

    private boolean containsProviderAuthenticationException(Throwable error) {
        Throwable current = error;
        while (current != null) {
            if (current instanceof ProviderAuthenticationException) {
                return true;
            }
            current = current.getCause();
        }
        return false;
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
                "whatChanged", "drivers", "strategicBets",
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
     * 用硬数据重建关键指标，优先展示可用且有解释价值的指标，避免把缺失值伪装成 0。
     */
    private void injectFixedKeyMetrics(AnalysisReport report, FinancialFacts facts, String lang) {
        boolean isZh = "zh".equalsIgnoreCase(lang);

        List<AnalysisReport.MetricInsight> fixed = new ArrayList<>();

        addMetricIfPresent(
                fixed,
                facts.getRevenue(),
                buildMetric(
                        isZh ? "营收" : "Revenue",
                        formatCurrency(facts.getRevenue(), facts.getCurrency()),
                        buildRevenueInterpretation(facts, isZh),
                        sentimentFromTrend(facts.getRevenueYoY(), new BigDecimal("0.005"))));

        if (hasReliableGrossMargin(facts)) {
            addMetricIfPresent(
                    fixed,
                    facts.getGrossMargin(),
                    buildMetric(
                            isZh ? "毛利率" : "Gross Margin",
                            formatPercent(facts.getGrossMargin()),
                            buildMarginInterpretation(
                                    facts.getGrossMargin(),
                                    facts.getGrossMarginChange(),
                                    isZh ? "毛利率" : "Gross margin",
                                    isZh),
                            sentimentFromTrend(facts.getGrossMarginChange(), new BigDecimal("0.0025"))));
        } else {
            addMetricIfPresent(
                    fixed,
                    facts.getOperatingMargin(),
                    buildMetric(
                            isZh ? "营业利润率" : "Operating Margin",
                            formatPercent(facts.getOperatingMargin()),
                            buildMarginInterpretation(
                                    facts.getOperatingMargin(),
                                    facts.getOperatingMarginChange(),
                                    isZh ? "营业利润率" : "Operating margin",
                                    isZh),
                            sentimentFromTrend(facts.getOperatingMarginChange(), new BigDecimal("0.0025"))));
        }

        addMetricIfPresent(
                fixed,
                facts.getNetIncome(),
                buildMetric(
                        isZh ? "净利润" : "Net Income",
                        formatCurrency(facts.getNetIncome(), facts.getCurrency()),
                        buildNetIncomeInterpretation(facts, isZh),
                        sentimentFromTrend(facts.getNetMarginChange(), new BigDecimal("0.0025"))));

        if (facts.getRevenueYoY() != null) {
            addMetricIfPresent(
                    fixed,
                    facts.getRevenueYoY(),
                    buildMetric(
                            isZh ? "营收同比增长" : "Revenue YoY Growth",
                            formatPercent(facts.getRevenueYoY()),
                            buildRevenueGrowthInterpretation(facts.getRevenueYoY(), isZh),
                            sentimentFromTrend(facts.getRevenueYoY(), new BigDecimal("0.005"))));
        } else if (facts.getFreeCashFlow() != null) {
            addMetricIfPresent(
                    fixed,
                    facts.getFreeCashFlow(),
                    buildMetric(
                            isZh ? "自由现金流" : "Free Cash Flow",
                            formatCurrency(facts.getFreeCashFlow(), facts.getCurrency()),
                            buildCashFlowInterpretation(
                                    facts.getFreeCashFlow(),
                                    facts.getFreeCashFlowYoY(),
                                    isZh ? "自由现金流" : "Free cash flow",
                                    facts.getCurrency(),
                                    isZh),
                            sentimentFromTrend(facts.getFreeCashFlowYoY(), new BigDecimal("0.005"))));
        } else {
            addMetricIfPresent(
                    fixed,
                    facts.getOperatingCashFlow(),
                    buildMetric(
                            isZh ? "经营现金流" : "Operating Cash Flow",
                            formatCurrency(facts.getOperatingCashFlow(), facts.getCurrency()),
                            buildCashFlowInterpretation(
                                    facts.getOperatingCashFlow(),
                                    facts.getOperatingCashFlowYoY(),
                                    isZh ? "经营现金流" : "Operating cash flow",
                                    facts.getCurrency(),
                                    isZh),
                            sentimentFromTrend(facts.getOperatingCashFlowYoY(), new BigDecimal("0.005"))));
        }

        report.setKeyMetrics(fixed);
        log.info("✅ Injected {} quantitative keyMetrics for {}", fixed.size(), facts.getTicker());
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

    private void addMetricIfPresent(List<AnalysisReport.MetricInsight> target,
            BigDecimal rawValue,
            AnalysisReport.MetricInsight metric) {
        if (rawValue == null || metric == null) {
            return;
        }
        target.add(metric);
    }

    private String buildRevenueInterpretation(FinancialFacts facts, boolean isZh) {
        String revenue = formatCurrency(facts.getRevenue(), facts.getCurrency());
        if (facts.getRevenueYoY() == null) {
            return isZh
                    ? String.format(Locale.ROOT, "本季营收为%s，当前缺少可比同期增速。", revenue)
                    : String.format(Locale.ROOT, "Revenue was %s for the reported period; comparable prior-period growth was unavailable.", revenue);
        }
        if (isEffectivelyFlat(facts.getRevenueYoY(), new BigDecimal("0.005"))) {
            return isZh
                    ? String.format(Locale.ROOT, "本季营收为%s，同比基本持平。", revenue)
                    : String.format(Locale.ROOT, "Revenue was %s and remained broadly flat year over year.", revenue);
        }
        return isZh
                ? String.format(Locale.ROOT, "本季营收为%s，同比%s。", revenue, describeGrowthDirection(facts.getRevenueYoY(), true))
                : String.format(Locale.ROOT, "Revenue was %s, %s year over year.", revenue, describeGrowthDirection(facts.getRevenueYoY(), false));
    }

    private String buildRevenueGrowthInterpretation(BigDecimal growth, boolean isZh) {
        String formatted = formatPercent(growth);
        if (isEffectivelyFlat(growth, new BigDecimal("0.005"))) {
            return isZh
                    ? String.format(Locale.ROOT, "营收同比为%s，整体收入与可比同期基本持平。", formatted)
                    : String.format(Locale.ROOT, "Revenue growth was %s year over year, leaving revenue broadly flat versus the comparison period.", formatted);
        }
        return isZh
                ? String.format(Locale.ROOT, "营收同比为%s，收入%s。", formatted, growth.compareTo(BigDecimal.ZERO) > 0 ? "继续扩张" : "较可比同期回落")
                : String.format(Locale.ROOT, "Revenue growth was %s year over year, meaning revenue %s versus the comparison period.", formatted, growth.compareTo(BigDecimal.ZERO) > 0 ? "expanded" : "declined");
    }

    private String buildMarginInterpretation(BigDecimal margin, BigDecimal change, String label, boolean isZh) {
        String formattedMargin = formatPercent(margin);
        if (change == null) {
            return isZh
                    ? String.format(Locale.ROOT, "%s为%s，当前缺少稳定的可比口径变化。", label, formattedMargin)
                    : String.format(Locale.ROOT, "%s was %s, but a stable comparison-period delta was unavailable.", label, formattedMargin);
        }
        return isZh
                ? String.format(Locale.ROOT, "%s为%s，%s。", label, formattedMargin, describeMarginDelta(change, true))
                : String.format(Locale.ROOT, "%s was %s, %s.", label, formattedMargin, describeMarginDelta(change, false));
    }

    private String buildNetIncomeInterpretation(FinancialFacts facts, boolean isZh) {
        String netIncome = formatCurrency(facts.getNetIncome(), facts.getCurrency());
        if (facts.getNetMargin() == null) {
            return isZh
                    ? String.format(Locale.ROOT, "净利润为%s。", netIncome)
                    : String.format(Locale.ROOT, "Net income was %s.", netIncome);
        }
        return isZh
                ? String.format(Locale.ROOT, "净利润为%s，净利率为%s。", netIncome, formatPercent(facts.getNetMargin()))
                : String.format(Locale.ROOT, "Net income was %s, with net margin at %s.", netIncome, formatPercent(facts.getNetMargin()));
    }

    private String buildCashFlowInterpretation(
            BigDecimal cashFlow,
            BigDecimal growth,
            String label,
            String currency,
            boolean isZh) {
        String formattedCashFlow = formatCurrency(cashFlow, currency);
        if (growth == null) {
            return isZh
                    ? String.format(Locale.ROOT, "%s为%s，可作为补充衡量现金创造能力。", label, formattedCashFlow)
                    : String.format(Locale.ROOT, "%s was %s, providing a supplemental read on cash generation.", label, formattedCashFlow);
        }
        if (isEffectivelyFlat(growth, new BigDecimal("0.005"))) {
            return isZh
                    ? String.format(Locale.ROOT, "%s为%s，同比基本持平。", label, formattedCashFlow)
                    : String.format(Locale.ROOT, "%s was %s and remained broadly flat year over year.", label, formattedCashFlow);
        }
        return isZh
                ? String.format(Locale.ROOT, "%s为%s，同比%s。", label, formattedCashFlow, describeGrowthDirection(growth, true))
                : String.format(Locale.ROOT, "%s was %s, %s year over year.", label, formattedCashFlow, describeGrowthDirection(growth, false));
    }

    private String describeGrowthDirection(BigDecimal growth, boolean isZh) {
        if (growth == null) {
            return isZh ? "缺少可比增速" : "lacked a comparable growth baseline";
        }
        if (isEffectivelyFlat(growth, new BigDecimal("0.005"))) {
            return isZh ? "基本持平" : "was broadly flat";
        }
        if (growth.compareTo(BigDecimal.ZERO) > 0) {
            return isZh ? "增长" + formatPercent(growth) : "grew " + formatPercent(growth);
        }
        return isZh ? "下降" + formatPercentAbs(growth) : "declined " + formatPercentAbs(growth);
    }

    private String sentimentFromTrend(BigDecimal value, BigDecimal flatThreshold) {
        if (value == null) {
            return "neutral";
        }
        if (isEffectivelyFlat(value, flatThreshold)) {
            return "neutral";
        }
        return value.compareTo(BigDecimal.ZERO) > 0 ? "positive" : "negative";
    }

    private boolean isEffectivelyFlat(BigDecimal value, BigDecimal threshold) {
        if (value == null || threshold == null) {
            return false;
        }
        return value.abs().compareTo(threshold) <= 0;
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
        thesis.setWhatChanged(cleanStringList(thesis.getWhatChanged()));
        thesis.setDrivers(cleanSupportingEvidence(thesis.getDrivers()));
        thesis.setStrategicBets(cleanSupportingEvidence(thesis.getStrategicBets()));
        thesis.setKeyPoints(cleanStringList(thesis.getKeyPoints()));
        thesis.setWatchItems(cleanStringList(thesis.getWatchItems()));
        thesis.setSupportingEvidence(cleanSupportingEvidence(thesis.getSupportingEvidence()));

        if ((thesis.getWhatChanged() == null || thesis.getWhatChanged().isEmpty())
                && thesis.getKeyPoints() != null && !thesis.getKeyPoints().isEmpty()) {
            thesis.setWhatChanged(thesis.getKeyPoints());
        }
        if ((thesis.getDrivers() == null || thesis.getDrivers().isEmpty())
                && thesis.getSupportingEvidence() != null && !thesis.getSupportingEvidence().isEmpty()) {
            thesis.setDrivers(thesis.getSupportingEvidence());
        }

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

        if (thesis.getKeyPoints() == null || thesis.getKeyPoints().isEmpty()) {
            thesis.setKeyPoints(thesis.getWhatChanged());
        }
        if (thesis.getSupportingEvidence() == null || thesis.getSupportingEvidence().isEmpty()) {
            thesis.setSupportingEvidence(mergeSupportingEvidence(thesis.getDrivers(), thesis.getStrategicBets()));
        }
    }

    private void enforceBusinessFirstCoreThesis(AnalysisReport report, AnalysisContract contract, String lang) {
        if (report == null || contract == null) {
            return;
        }

        boolean isZh = "zh".equalsIgnoreCase(lang);
        AnalysisReport.CoreThesis thesis = report.getCoreThesis();
        if (thesis == null) {
            thesis = AnalysisReport.CoreThesis.builder().build();
            report.setCoreThesis(thesis);
        }

        if (thesis.getHeadline() == null || isMetricHeavyText(thesis.getHeadline()) || isLowValueHeadline(thesis.getHeadline())) {
            thesis.setHeadline(buildBusinessHeadline(contract, isZh));
        }
        if (thesis.getSummary() == null || isMetricHeavyText(thesis.getSummary())) {
            thesis.setSummary(buildBusinessSummary(contract, isZh));
        }
        if (isLowValueStringList(thesis.getWhatChanged())) {
            thesis.setWhatChanged(buildWhatChanged(contract, isZh));
        }
        if (isLowValueEvidence(thesis.getDrivers())) {
            thesis.setDrivers(buildDriverEvidence(contract, isZh));
        }
        if (isLowValueEvidence(thesis.getStrategicBets())) {
            thesis.setStrategicBets(buildStrategicBetEvidence(contract, isZh));
        }
        if (isLowValueStringList(thesis.getWatchItems())) {
            thesis.setWatchItems(buildWatchItems(contract, isZh));
        }

        quantifyBusinessFirstThesis(thesis, contract, isZh);
        thesis.setKeyPoints(thesis.getWhatChanged());
        thesis.setSupportingEvidence(mergeSupportingEvidence(thesis.getDrivers(), thesis.getStrategicBets()));
        report.setExecutiveSummary(thesis.getSummary());
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

    protected void applySourceContext(AnalysisReport report, AnalysisContract contract, String agentName) {
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

    private void applyAgentFallbackIfNeeded(AnalysisReport report, AnalysisContract contract, String lang,
            String agentName) {
        if (!"InsightsAgent".equals(agentName)) {
            return;
        }

        AnalysisReport fallback = buildFallbackReportForAgent(agentName, contract, lang);
        if (report.getDupontAnalysis() == null) {
            report.setDupontAnalysis(fallback.getDupontAnalysis());
        }

        boolean missingInsightEngine = report.getInsightEngine() == null
                || ((report.getInsightEngine().getAccountingChanges() == null
                        || report.getInsightEngine().getAccountingChanges().isEmpty())
                        && (report.getInsightEngine().getRootCauseAnalysis() == null
                                || report.getInsightEngine().getRootCauseAnalysis().isEmpty()));
        if (missingInsightEngine) {
            report.setInsightEngine(fallback.getInsightEngine());
        }
    }

    private boolean isLowValueStringList(List<String> items) {
        return items == null || items.isEmpty()
                || items.stream().allMatch(item -> isMetricHeavyText(item) || isLowValueBusinessStatement(item));
    }

    private boolean isLowValueEvidence(List<AnalysisReport.SupportingEvidence> items) {
        if (items == null || items.isEmpty()) {
            return true;
        }
        return items.stream()
                .map(item -> item == null ? null : trimToNull((item.getLabel() == null ? "" : item.getLabel()) + " " + (item.getDetail() == null ? "" : item.getDetail())))
                .filter(Objects::nonNull)
                .allMatch(text -> isMetricHeavyText(text) || isLowValueBusinessStatement(text));
    }

    private boolean isMetricHeavyText(String text) {
        String value = trimToNull(text);
        if (value == null) {
            return false;
        }
        int metricHits = countKeywordHits(value, METRIC_RECAP_TERMS);
        int businessHits = countKeywordHits(value, BUSINESS_CONTEXT_TERMS);
        return metricHits >= 2 && metricHits >= businessHits + 1;
    }

    private int countKeywordHits(String text, List<String> keywords) {
        String lower = text.toLowerCase(Locale.ROOT);
        int count = 0;
        for (String keyword : keywords) {
            if (lower.contains(keyword.toLowerCase(Locale.ROOT))) {
                count++;
            }
        }
        return count;
    }

    private String buildBusinessHeadline(AnalysisContract contract, boolean isZh) {
        List<ThemeDescriptor> themes = collectThemeDescriptors(contract, isZh);
        String businessDescriptor = trimToNull(describeCompanyBusiness(contract, isZh));
        if (themes.size() >= 2) {
            return isZh
                    ? firstNonBlank(businessDescriptor, "公司") + "的" + themes.get(0).zh() + "仍是本期主线，"
                            + themes.get(1).zh() + "开始进入下一阶段"
                    : capitalize(themes.get(0).en()) + " stayed central while " + themes.get(1).en()
                            + " moved into the next phase";
        }
        if (!themes.isEmpty()) {
            return isZh
                    ? firstNonBlank(businessDescriptor, "公司") + "的" + themes.get(0).zh() + "仍是本期最重要的业务主线"
                    : capitalize(themes.get(0).en()) + " remained the defining business theme this period";
        }

        FinancialFacts facts = contract.getFinancialFacts();
        if (facts != null && facts.getRevenueYoY() != null && facts.getRevenueYoY().compareTo(BigDecimal.ZERO) >= 0) {
            return isZh
                    ? firstNonBlank(businessDescriptor, "公司") + "的业务动能仍在，管理层继续为下一阶段增长做准备"
                    : "Core business momentum held up while management kept preparing the next phase of growth";
        }
        return isZh
                ? firstNonBlank(businessDescriptor, "公司") + "仍在调整中，接下来要看执行与投入能否继续兑现"
                : "The core business is still being reset, and the next question is whether execution and investment can keep delivering";
    }

    private String buildBusinessSummary(AnalysisContract contract, boolean isZh) {
        return buildQuantifiedBusinessSummary(contract, isZh);
    }

    private void quantifyBusinessFirstThesis(AnalysisReport.CoreThesis thesis, AnalysisContract contract, boolean isZh) {
        if (thesis == null || contract == null) {
            return;
        }

        thesis.setSummary(enrichBusinessSummaryText(thesis.getSummary(), contract, isZh));
        thesis.setWhatChanged(enrichQuantifiedSentences(thesis.getWhatChanged(), contract, isZh));
        thesis.setDrivers(enrichQuantifiedEvidence(thesis.getDrivers(), contract, isZh));
        thesis.setStrategicBets(enrichQuantifiedEvidence(thesis.getStrategicBets(), contract, isZh));
        thesis.setWatchItems(enrichQuantifiedSentences(thesis.getWatchItems(), contract, isZh));
    }

    private String enrichBusinessSummaryText(String summary, AnalysisContract contract, boolean isZh) {
        String value = trimToNull(summary);
        if (value == null || containsGenericSummaryScaffold(value) || !containsNumericContent(value)) {
            return buildQuantifiedBusinessSummary(contract, isZh);
        }
        return value;
    }

    private boolean isLowValueHeadline(String text) {
        String value = trimToNull(text);
        if (value == null) {
            return false;
        }
        String lower = value.toLowerCase(Locale.ROOT);
        return lower.contains("核心业务主线")
                || lower.contains("业务继续推进")
                || lower.contains("business narrative")
                || lower.contains("core business");
    }

    private List<String> enrichQuantifiedSentences(List<String> items, AnalysisContract contract, boolean isZh) {
        if (items == null) {
            return null;
        }
        return items.stream()
                .map(item -> maybeAppendMetricAnchor(item, contract, isZh))
                .toList();
    }

    private List<AnalysisReport.SupportingEvidence> enrichQuantifiedEvidence(
            List<AnalysisReport.SupportingEvidence> items,
            AnalysisContract contract,
            boolean isZh) {
        if (items == null) {
            return null;
        }
        return items.stream()
                .map(item -> item == null ? null : AnalysisReport.SupportingEvidence.builder()
                        .label(item.getLabel())
                        .detail(maybeAppendMetricAnchor(item.getDetail(), contract, isZh))
                        .build())
                .filter(Objects::nonNull)
                .toList();
    }

    private String maybeAppendMetricAnchor(String text, AnalysisContract contract, boolean isZh) {
        String value = trimToNull(text);
        if (value == null || containsNumericContent(value)) {
            return value;
        }

        String anchor = buildMetricAnchorForText(value, contract, isZh);
        if (anchor == null) {
            return value;
        }
        return appendMetricAnchor(value, anchor, isZh);
    }

    private String appendMetricAnchor(String text, String anchor, boolean isZh) {
        String base = trimToNull(text);
        String value = trimToNull(anchor);
        if (base == null || value == null) {
            return base;
        }

        String normalizedBase = base.replaceAll("[。.!?]+$", "");
        return isZh ? normalizedBase + "，" + value + "。" : normalizedBase + ", " + value + ".";
    }

    private boolean containsNumericContent(String text) {
        return text != null && text.chars().anyMatch(Character::isDigit);
    }

    private boolean containsGenericSummaryScaffold(String text) {
        String lower = text == null ? "" : text.toLowerCase(Locale.ROOT);
        return lower.contains("本期最值得关注的不是单一财务指标")
                || lower.contains("核心业务主线仍在延续")
                || lower.contains("继续主导业务表现")
                || lower.contains("背后的关键驱动在于")
                || lower.contains("highest-value takeaway")
                || lower.contains("not the raw metric recap")
                || lower.contains("kept driving the business");
    }

    private boolean isLowValueBusinessStatement(String text) {
        String lower = text == null ? "" : text.toLowerCase(Locale.ROOT);
        return lower.contains("新产品开发与市场扩展")
                || lower.contains("新产品推出后的市场反应")
                || lower.contains("市场需求与定价能力")
                || lower.contains("成本控制与效率提升")
                || lower.contains("需求与产品组合")
                || lower.contains("执行与效率")
                || lower.contains("核心需求仍有韧性")
                || lower.contains("积极开发新产品")
                || lower.contains("market demand and pricing")
                || lower.contains("cost control and efficiency")
                || lower.contains("new product development")
                || lower.contains("demand and mix");
    }

    private String buildQuantifiedBusinessSummary(AnalysisContract contract, boolean isZh) {
        List<ThemeDescriptor> primaryThemes = collectThemeDescriptors(contract, isZh);
        ThemeDescriptor primary = primaryThemes.isEmpty() ? genericBusinessTheme() : primaryThemes.get(0);
        ThemeDescriptor bet = firstThemeFromSignals(contract.getBusinessSignals(), isZh,
                collectStrategicSignals(contract.getBusinessSignals()));
        ThemeDescriptor strategicTheme = bet != null ? bet : infrastructureTheme();
        String businessIdentityLead = buildBusinessIdentityLead(contract, isZh);
        String firstAnchor = buildThemeMetricAnchor(primary, contract, isZh);
        String secondAnchor = firstNonBlank(
                buildThemeMetricAnchor(strategicTheme, contract, isZh),
                buildOperatingProfitAnchor(contract.getFinancialFacts(), isZh),
                buildCashFlowAnchor(contract.getFinancialFacts(), isZh));
        if (sameMetricAnchor(firstAnchor, secondAnchor)) {
            secondAnchor = firstNonBlank(
                    buildOperatingProfitAnchor(contract.getFinancialFacts(), isZh),
                    buildCashFlowAnchor(contract.getFinancialFacts(), isZh),
                    secondAnchor);
        }

        String firstClause = appendMetricAnchor(
                prependBusinessIdentity(summaryLeadForTheme(primary, isZh), businessIdentityLead, isZh),
                firstAnchor,
                isZh);
        String secondClause = appendMetricAnchor(
                strategicLeadForTheme(strategicTheme, isZh),
                secondAnchor,
                isZh);
        String normalizedFirst = stripTrailingSentenceEnd(firstClause);
        String normalizedSecond = stripTrailingSentenceEnd(secondClause);

        return isZh
                ? normalizedFirst + "；与此同时，" + normalizedSecond + "，这会决定下一阶段商业化与盈利兑现能否延续。"
                : normalizedFirst + ". At the same time, " + normalizedSecond
                        + ", which will determine whether the next phase of commercialization and profit delivery can hold.";
    }

    private String summaryLeadForTheme(ThemeDescriptor theme, boolean isZh) {
        ThemeDescriptor resolved = theme == null ? genericBusinessTheme() : theme;
        return switch (resolved.key()) {
            case "ad_monetization" -> isZh ? "广告定价与展示量继续改善" : "Ad pricing and impressions kept improving";
            case "new_surfaces" -> isZh ? "Reels、Threads 等新流量场景的商业化仍在推进"
                    : "Monetization on newer surfaces like Reels and Threads kept progressing";
            case "ai_efficiency" -> isZh ? "AI能力与产品效率继续提升"
                    : "AI capabilities and product efficiency kept improving";
            case "ai_productization" -> isZh ? "AI相关产品与模型商业化仍在推进"
                    : "AI product and model commercialization kept progressing";
            case "cloud" -> isZh ? "云业务需求与AI工作负载仍然稳健"
                    : "Cloud demand and AI workloads remained healthy";
            case "service_mix" -> isZh ? "服务与订阅组合继续优化"
                    : "Service and subscription mix kept improving";
            case "enterprise" -> isZh ? "企业客户需求与续费表现仍然稳定"
                    : "Enterprise demand and renewal behavior stayed solid";
            case "execution", "pricing_mix" -> isZh ? "成本纪律与执行效率仍在兑现"
                    : "Cost discipline and execution quality still showed through";
            case "infrastructure" -> isZh ? "算力与基础设施投入继续抬升"
                    : "Infrastructure and compute investment kept rising";
            case "hardware" -> isZh ? "硬件与前沿业务押注仍在推进"
                    : "Hardware and frontier bets kept moving forward";
            case "competition" -> isZh ? "竞争格局仍在影响业务节奏"
                    : "Competition is still shaping the operating pace";
            case "regulatory" -> isZh ? "监管与平台约束仍需纳入经营判断"
                    : "Regulatory and platform constraints still matter to the operating story";
            default -> isZh ? "核心业务主线仍在延续" : "The core business narrative remained intact";
        };
    }

    private String strategicLeadForTheme(ThemeDescriptor theme, boolean isZh) {
        ThemeDescriptor resolved = theme == null ? infrastructureTheme() : theme;
        return switch (resolved.key()) {
            case "infrastructure" -> isZh ? "公司仍在加大算力与基础设施投入"
                    : "The company is still stepping up infrastructure and compute investment";
            case "ai_efficiency" -> isZh ? "公司仍在推进AI能力的产品化与商业化"
                    : "The company is still pushing AI productization and commercialization";
            case "ai_productization" -> isZh ? "公司仍在围绕AI产品与模型能力推进商业化"
                    : "The company is still commercializing AI products and model capabilities";
            case "new_surfaces" -> isZh ? "公司仍在推动新流量场景的变现"
                    : "The company is still scaling monetization on newer surfaces";
            case "hardware" -> isZh ? "公司仍在为硬件与前沿业务押注投入资源"
                    : "The company is still allocating resources to hardware and frontier bets";
            default -> isZh ? "公司仍在为下一阶段增长保留投入空间"
                    : "The company is still preserving room to invest for the next phase of growth";
        };
    }

    private String buildThemeMetricAnchor(ThemeDescriptor theme, AnalysisContract contract, boolean isZh) {
        FinancialFacts facts = contract.getFinancialFacts();
        ThemeDescriptor resolved = theme == null ? genericBusinessTheme() : theme;

        return switch (resolved.key()) {
            case "ad_monetization" -> firstNonBlank(
                    buildSignalMetricAnchor(contract.getBusinessSignals(), Set.of("ad_monetization", "new_surfaces"),
                            isZh, "广告相关披露数字为", "the disclosed advertising figures were "),
                    buildRevenueAnchor(facts, isZh));
            case "new_surfaces", "ai_efficiency", "ai_productization", "cloud", "service_mix", "enterprise", "demand" -> firstNonBlank(
                    buildSignalMetricAnchor(contract.getBusinessSignals(), Set.of(resolved.key()),
                            isZh, "相关披露数字为", "the disclosed figures were "),
                    buildRevenueAnchor(facts, isZh));
            case "execution", "pricing_mix" -> firstNonBlank(
                    buildOperatingProfitAnchor(facts, isZh),
                    buildMarginAnchor(facts, isZh));
            case "infrastructure", "hardware" -> firstNonBlank(
                    buildSignalMetricAnchor(contract.getBusinessSignals(), Set.of(resolved.key()),
                            isZh, "相关投入数字为", "the disclosed investment figures were "),
                    buildCashFlowAnchor(facts, isZh));
            case "competition", "regulatory" -> firstNonBlank(
                    buildSignalMetricAnchor(contract.getBusinessSignals(), Set.of(resolved.key()),
                            isZh, "相关风险信号数字为", "the disclosed risk figures were "),
                    buildRevenueAnchor(facts, isZh));
            default -> firstNonBlank(buildRevenueAnchor(facts, isZh), buildMarginAnchor(facts, isZh));
        };
    }

    private String buildMetricAnchorForText(String text, AnalysisContract contract, boolean isZh) {
        if (text == null || contract == null || contract.getFinancialFacts() == null) {
            return null;
        }
        String lower = text.toLowerCase(Locale.ROOT);
        FinancialFacts facts = contract.getFinancialFacts();
        LinkedHashSet<String> anchors = new LinkedHashSet<>();

        if (containsAny(lower, "广告", "advertis", "ads", "reels", "threads")) {
            addIfPresent(anchors, firstNonBlank(
                    buildSignalMetricAnchor(contract.getBusinessSignals(), Set.of("ad_monetization", "new_surfaces"),
                            isZh, "广告相关披露数字为", "the disclosed advertising figures were "),
                    buildRevenueAnchor(facts, isZh)));
        }
        if (containsAny(lower, "营收", "收入", "revenue", "growth", "demand")) {
            addIfPresent(anchors, buildRevenueAnchor(facts, isZh));
        }
        if (containsAny(lower, "运营利润", "operating income", "operating profit")) {
            addIfPresent(anchors, buildOperatingProfitAnchor(facts, isZh));
        }
        if (containsAny(lower, "净利润", "净利", "net income", "net profit")) {
            addIfPresent(anchors, buildNetIncomeAnchor(facts, isZh));
        }
        if (containsAny(lower, "毛利率", "gross margin", "profitability", "盈利能力", "利润率")) {
            addIfPresent(anchors, buildMarginAnchor(facts, isZh));
        }
        if (containsAny(lower, "现金流", "cash flow", "free cash flow", "operating cash flow")) {
            addIfPresent(anchors, buildCashFlowAnchor(facts, isZh));
        }
        if (containsAny(lower, "基础设施", "算力", "capex", "infrastructure", "investment", "投资", "商业化", "ai")) {
            addIfPresent(anchors, firstNonBlank(
                    buildSignalMetricAnchor(contract.getBusinessSignals(), Set.of("infrastructure", "hardware", "ai_efficiency", "ai_productization"),
                            isZh, "相关投入数字为", "the disclosed investment figures were "),
                    buildCashFlowAnchor(facts, isZh)));
        }

        return anchors.isEmpty() ? null : String.join(isZh ? "；" : "; ", anchors);
    }

    private String buildSignalMetricAnchor(
            BusinessSignals signals,
            Set<String> themeKeys,
            boolean isZh,
            String zhPrefix,
            String enPrefix) {
        if (signals == null || themeKeys == null || themeKeys.isEmpty()) {
            return null;
        }

        for (BusinessSignals.SignalItem item : collectAllSignals(signals)) {
            if (!themeKeys.contains(inferThemeDescriptor(item).key())) {
                continue;
            }
            String snippet = extractNumericSnippet(item);
            if (snippet != null) {
                return (isZh ? zhPrefix : enPrefix) + (isZh ? snippet : snippet.replace("、", " and "));
            }
        }
        return null;
    }

    private List<BusinessSignals.SignalItem> collectAllSignals(BusinessSignals signals) {
        List<BusinessSignals.SignalItem> items = new ArrayList<>();
        appendSignals(items, signals == null ? null : signals.getSegmentPerformance());
        appendSignals(items, signals == null ? null : signals.getProductServiceUpdates());
        appendSignals(items, signals == null ? null : signals.getManagementFocus());
        appendSignals(items, signals == null ? null : signals.getStrategicMoves());
        appendSignals(items, signals == null ? null : signals.getCapexSignals());
        appendSignals(items, signals == null ? null : signals.getRiskSignals());
        return items;
    }

    private String extractNumericSnippet(BusinessSignals.SignalItem item) {
        String source = trimToNull(item == null ? null
                : firstNonBlank(item.getSummary(), item.getEvidenceSnippet()));
        if (source == null) {
            return null;
        }

        LinkedHashSet<String> matches = new LinkedHashSet<>();
        var matcher = NUMERIC_FRAGMENT_PATTERN.matcher(source);
        while (matcher.find()) {
            String fragment = trimToNull(matcher.group());
            if (fragment == null || !looksLikeMetricFragment(fragment)) {
                continue;
            }
            matches.add(fragment);
            if (matches.size() >= 3) {
                break;
            }
        }
        if (matches.isEmpty()) {
            return null;
        }
        return String.join("、", matches);
    }

    private boolean looksLikeMetricFragment(String fragment) {
        String lower = fragment.toLowerCase(Locale.ROOT);
        return lower.contains("%")
                || lower.contains("$")
                || lower.contains("亿")
                || lower.contains("万")
                || lower.contains("billion")
                || lower.contains("million")
                || lower.contains("trillion");
    }

    private String buildRevenueAnchor(FinancialFacts facts, boolean isZh) {
        if (facts == null || facts.getRevenue() == null) {
            return null;
        }
        if (facts.getRevenueYoY() != null) {
            return isZh
                    ? String.format(Locale.ROOT, "本季营收为%s，%s",
                            formatCurrencyNarrative(facts.getRevenue(), facts.getCurrency(), true),
                            describeDeltaForNarrative(facts.getRevenueYoY(), true))
                    : String.format(Locale.ROOT, "revenue was %s, %s",
                            formatCurrencyNarrative(facts.getRevenue(), facts.getCurrency(), false),
                            describeDeltaForNarrative(facts.getRevenueYoY(), false));
        }
        return isZh
                ? "本季营收为" + formatCurrencyNarrative(facts.getRevenue(), facts.getCurrency(), true)
                : "revenue was " + formatCurrencyNarrative(facts.getRevenue(), facts.getCurrency(), false);
    }

    private String buildOperatingProfitAnchor(FinancialFacts facts, boolean isZh) {
        if (facts == null) {
            return null;
        }
        List<String> parts = new ArrayList<>();
        if (facts.getOperatingIncome() != null) {
            parts.add(isZh
                    ? "运营利润为" + formatCurrencyNarrative(facts.getOperatingIncome(), facts.getCurrency(), true)
                    : "operating income was " + formatCurrencyNarrative(facts.getOperatingIncome(), facts.getCurrency(), false));
        }
        if (facts.getNetIncome() != null) {
            parts.add(isZh
                    ? "净利润为" + formatCurrencyNarrative(facts.getNetIncome(), facts.getCurrency(), true)
                    : "net income was " + formatCurrencyNarrative(facts.getNetIncome(), facts.getCurrency(), false));
        }
        if (parts.isEmpty()) {
            return null;
        }
        return String.join(isZh ? "，" : ", ", parts);
    }

    private String buildNetIncomeAnchor(FinancialFacts facts, boolean isZh) {
        if (facts == null || facts.getNetIncome() == null) {
            return null;
        }
        if (facts.getNetMargin() != null) {
            return isZh
                    ? String.format(Locale.ROOT, "净利润为%s，净利率为%s",
                            formatCurrencyNarrative(facts.getNetIncome(), facts.getCurrency(), true),
                            formatPercentOrFallback(facts.getNetMargin()))
                    : String.format(Locale.ROOT, "net income was %s with a net margin of %s",
                            formatCurrencyNarrative(facts.getNetIncome(), facts.getCurrency(), false),
                            formatPercentOrFallback(facts.getNetMargin()));
        }
        return isZh
                ? "净利润为" + formatCurrencyNarrative(facts.getNetIncome(), facts.getCurrency(), true)
                : "net income was " + formatCurrencyNarrative(facts.getNetIncome(), facts.getCurrency(), false);
    }

    private String buildMarginAnchor(FinancialFacts facts, boolean isZh) {
        if (facts == null) {
            return null;
        }
        List<String> parts = new ArrayList<>();
        if (hasReliableGrossMargin(facts)) {
            parts.add(isZh
                    ? "毛利率为" + formatPercentOrFallback(facts.getGrossMargin())
                    : "gross margin was " + formatPercentOrFallback(facts.getGrossMargin()));
        }
        if (facts.getOperatingMargin() != null) {
            parts.add(isZh
                    ? "运营利润率为" + formatPercentOrFallback(facts.getOperatingMargin())
                    : "operating margin was " + formatPercentOrFallback(facts.getOperatingMargin()));
        } else if (facts.getNetMargin() != null) {
            parts.add(isZh
                    ? "净利率为" + formatPercentOrFallback(facts.getNetMargin())
                    : "net margin was " + formatPercentOrFallback(facts.getNetMargin()));
        }
        if (parts.isEmpty()) {
            return null;
        }
        return String.join(isZh ? "，" : ", ", parts);
    }

    private boolean hasReliableGrossMargin(FinancialFacts facts) {
        if (facts == null || facts.getGrossMargin() == null) {
            return false;
        }
        if (facts.getGrossProfit() != null) {
            return true;
        }
        return facts.getGrossMargin().compareTo(BigDecimal.ZERO) != 0;
    }

    private String buildCashFlowAnchor(FinancialFacts facts, boolean isZh) {
        if (facts == null) {
            return null;
        }

        if (facts.getFreeCashFlow() != null) {
            if (facts.getFreeCashFlowYoY() != null) {
                return isZh
                        ? String.format(Locale.ROOT, "自由现金流为%s，%s",
                                formatCurrencyNarrative(facts.getFreeCashFlow(), facts.getCurrency(), true),
                                describeDeltaForNarrative(facts.getFreeCashFlowYoY(), true))
                        : String.format(Locale.ROOT, "free cash flow was %s, %s",
                                formatCurrencyNarrative(facts.getFreeCashFlow(), facts.getCurrency(), false),
                                describeDeltaForNarrative(facts.getFreeCashFlowYoY(), false));
            }
            return isZh
                    ? "自由现金流为" + formatCurrencyNarrative(facts.getFreeCashFlow(), facts.getCurrency(), true)
                    : "free cash flow was " + formatCurrencyNarrative(facts.getFreeCashFlow(), facts.getCurrency(), false);
        }

        if (facts.getOperatingCashFlow() != null) {
            if (facts.getOperatingCashFlowYoY() != null) {
                return isZh
                        ? String.format(Locale.ROOT, "经营现金流为%s，%s",
                                formatCurrencyNarrative(facts.getOperatingCashFlow(), facts.getCurrency(), true),
                                describeDeltaForNarrative(facts.getOperatingCashFlowYoY(), true))
                        : String.format(Locale.ROOT, "operating cash flow was %s, %s",
                                formatCurrencyNarrative(facts.getOperatingCashFlow(), facts.getCurrency(), false),
                                describeDeltaForNarrative(facts.getOperatingCashFlowYoY(), false));
            }
            return isZh
                    ? "经营现金流为" + formatCurrencyNarrative(facts.getOperatingCashFlow(), facts.getCurrency(), true)
                    : "operating cash flow was " + formatCurrencyNarrative(facts.getOperatingCashFlow(), facts.getCurrency(), false);
        }
        return null;
    }

    private String describeDeltaForNarrative(BigDecimal delta, boolean isZh) {
        if (delta == null) {
            return null;
        }
        if (delta.compareTo(BigDecimal.ZERO) > 0) {
            if (delta.abs().compareTo(EXTREME_POSITIVE_YOY_THRESHOLD) >= 0) {
                return isZh
                        ? "同比大幅跳升（" + formatSignedPercent(delta) + "，主要因去年同期基数较低）"
                        : "jumped sharply year over year (" + formatSignedPercent(delta)
                                + "), likely because the prior-year base was unusually low";
            }
            return isZh ? "同比增长" + formatPercentAbs(delta) : "up " + formatPercentAbs(delta) + " year over year";
        }
        if (delta.compareTo(BigDecimal.ZERO) < 0) {
            return isZh ? "同比下滑" + formatPercentAbs(delta) : "down " + formatPercentAbs(delta) + " year over year";
        }
        return isZh ? "同比持平" : "flat year over year";
    }

    private String formatCurrencyNarrative(BigDecimal value, String currency, boolean isZh) {
        if (!isZh) {
            return formatCurrency(value, currency);
        }
        if (value == null) {
            return "N/A";
        }

        BigDecimal abs = value.abs();
        String suffix = currency == null || currency.isBlank() || "USD".equalsIgnoreCase(currency)
                ? "美元"
                : currency;
        if (abs.compareTo(new BigDecimal("1000000000000")) >= 0) {
            return abs.divide(new BigDecimal("1000000000000"), 2, RoundingMode.HALF_UP).toPlainString() + "万亿" + suffix;
        }
        if (abs.compareTo(new BigDecimal("100000000")) >= 0) {
            return abs.divide(new BigDecimal("100000000"), 2, RoundingMode.HALF_UP).toPlainString() + "亿" + suffix;
        }
        if (abs.compareTo(new BigDecimal("10000")) >= 0) {
            return abs.divide(new BigDecimal("10000"), 2, RoundingMode.HALF_UP).toPlainString() + "万" + suffix;
        }
        return value.setScale(2, RoundingMode.HALF_UP).toPlainString() + suffix;
    }

    private void addIfPresent(Set<String> target, String value) {
        String normalized = trimToNull(value);
        if (normalized != null) {
            target.add(normalized);
        }
    }

    private String firstNonBlank(String... candidates) {
        if (candidates == null) {
            return null;
        }
        for (String candidate : candidates) {
            String normalized = trimToNull(candidate);
            if (normalized != null) {
                return normalized;
            }
        }
        return null;
    }

    private String stripTrailingSentenceEnd(String text) {
        String value = trimToNull(text);
        if (value == null) {
            return null;
        }
        return value.replaceAll("[。.!?]+$", "");
    }

    private List<String> buildWhatChanged(AnalysisContract contract, boolean isZh) {
        BusinessSignals signals = contract.getBusinessSignals();
        List<BusinessSignals.SignalItem> items = collectPrimarySignals(signals);
        List<String> bullets = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();

        for (BusinessSignals.SignalItem item : items) {
            String signalBullet = buildSignalBullet(item, contract, isZh);
            if (addUniqueNarrative(bullets, seen, signalBullet) && bullets.size() >= 3) {
                return bullets;
            }
        }

        FinancialFacts facts = contract.getFinancialFacts();
        if (facts != null) {
            if (facts.getRevenueYoY() != null) {
                addUniqueNarrative(bullets, seen, isZh
                        ? (facts.getRevenueYoY().compareTo(BigDecimal.ZERO) >= 0
                                ? "核心需求仍有韧性，业务主线没有失速。"
                                : "核心需求仍在调整，业务恢复仍需更多证据。")
                        : (facts.getRevenueYoY().compareTo(BigDecimal.ZERO) >= 0
                                ? "Core demand still showed enough resilience to keep the business story intact."
                                : "Core demand still looks unsettled, and the recovery story needs more proof."));
            }
            if (facts.getGrossMarginChange() != null) {
                addUniqueNarrative(bullets, seen, isZh
                        ? (facts.getGrossMarginChange().compareTo(BigDecimal.ZERO) >= 0
                                ? "盈利质量并未恶化，产品组合和执行节奏仍在支撑本期表现。"
                                : "盈利质量开始承压，产品组合和成本结构值得继续跟踪。")
                        : (facts.getGrossMarginChange().compareTo(BigDecimal.ZERO) >= 0
                                ? "Earnings quality did not deteriorate, which suggests mix and execution are still supportive."
                                : "Profit quality is starting to come under pressure, so mix and cost structure need closer attention."));
            }
        }

        String profileWhatChanged = buildProfileWhatChanged(contract, isZh);
        if (profileWhatChanged != null) {
            String key = normalizeNarrativeBullet(profileWhatChanged);
            if (key != null && !seen.contains(key)) {
                bullets.add(0, profileWhatChanged);
                seen.add(key);
            }
        }
        return bullets.stream().limit(3).toList();
    }

    private List<AnalysisReport.SupportingEvidence> buildDriverEvidence(AnalysisContract contract, boolean isZh) {
        List<AnalysisReport.SupportingEvidence> items = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (BusinessSignals.SignalItem signal : collectDriverSignals(contract.getBusinessSignals())) {
            String label = localizedSignalTitle(signal, isZh);
            AnalysisReport.SupportingEvidence evidence = AnalysisReport.SupportingEvidence.builder()
                    .label(firstNonBlank(label, themeLabel(inferThemeDescriptor(signal), isZh)))
                    .detail(buildSignalEvidenceDetail(signal, contract, isZh, "driver"))
                    .build();
            if (addUniqueEvidence(items, seen, evidence) && items.size() >= 3) {
                return items;
            }
        }

        FinancialFacts facts = contract.getFinancialFacts();
        if (items.isEmpty() && facts != null) {
            String profileDriver = buildProfileDriverDetail(contract, isZh);
            if (profileDriver != null) {
                addUniqueEvidence(items, seen, AnalysisReport.SupportingEvidence.builder()
                        .label(isZh ? "产品线与客户需求" : "Product lines and customer demand")
                        .detail(profileDriver)
                        .build());
            }
            addUniqueEvidence(items, seen, AnalysisReport.SupportingEvidence.builder()
                    .label(isZh ? "需求与产品组合" : "Demand and mix")
                    .detail(isZh
                            ? "如果没有足够的叙事证据，当前最可能驱动结果的仍是需求韧性与产品组合变化。"
                            : "When narrative evidence is thin, the most plausible driver remains demand resilience and product mix.")
                    .build());
            addUniqueEvidence(items, seen, AnalysisReport.SupportingEvidence.builder()
                    .label(isZh ? "执行与效率" : "Execution and efficiency")
                    .detail(isZh
                            ? "管理层是否继续维持成本纪律和执行效率，决定了利润质量能否站稳。"
                            : "Management's ability to preserve cost discipline and execution quality still determines whether margins can hold.")
                    .build());
        }
        return items;
    }

    private List<AnalysisReport.SupportingEvidence> buildStrategicBetEvidence(AnalysisContract contract, boolean isZh) {
        List<AnalysisReport.SupportingEvidence> items = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (BusinessSignals.SignalItem signal : collectStrategicSignals(contract.getBusinessSignals())) {
            String label = localizedSignalTitle(signal, isZh);
            AnalysisReport.SupportingEvidence evidence = AnalysisReport.SupportingEvidence.builder()
                    .label(firstNonBlank(label, themeLabel(inferThemeDescriptor(signal), isZh)))
                    .detail(buildSignalEvidenceDetail(signal, contract, isZh, "bet"))
                    .build();
            if (addUniqueEvidence(items, seen, evidence) && items.size() >= 2) {
                return items;
            }
        }

        FinancialFacts facts = contract.getFinancialFacts();
        if (items.isEmpty() && facts != null) {
            String profileBet = buildProfileStrategicBetDetail(contract, isZh);
            if (profileBet != null) {
                addUniqueEvidence(items, seen, AnalysisReport.SupportingEvidence.builder()
                        .label(isZh ? "核心产品押注" : "Core product bet")
                        .detail(profileBet)
                        .build());
            }
            addUniqueEvidence(items, seen, AnalysisReport.SupportingEvidence.builder()
                    .label(isZh ? "投资节奏" : "Investment pace")
                    .detail(isZh
                            ? "即便没有明确的新业务披露，市场接下来仍会观察公司是否继续为下一阶段增长保留投入空间。"
                            : "Even without explicit new-product disclosure, the market will still watch whether the company preserves room to invest for the next phase of growth.")
                    .build());
        }
        return items;
    }

    private List<String> buildWatchItems(AnalysisContract contract, boolean isZh) {
        List<String> watchItems = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();
        for (BusinessSignals.SignalItem signal : collectWatchSignals(contract.getBusinessSignals())) {
            String item = buildSignalWatchItem(signal, contract, isZh);
            if (addUniqueNarrative(watchItems, seen, item) && watchItems.size() >= 3) {
                return watchItems;
            }
        }

        FinancialFacts facts = contract.getFinancialFacts();
        if (watchItems.isEmpty() && facts != null) {
            String profileWatchItem = buildProfileWatchItem(contract, isZh);
            addUniqueNarrative(watchItems, seen, profileWatchItem);
            addUniqueNarrative(watchItems, seen, isZh
                    ? "继续观察需求韧性能否支撑当前业务主线，而不是只看单季数字是否漂亮。"
                    : "Keep watching whether demand resilience still supports the core story rather than focusing only on one-quarter numbers.");
            addUniqueNarrative(watchItems, seen, isZh
                    ? "观察利润质量与现金转化能否继续为投入节奏提供空间。"
                    : "Watch whether profit quality and cash conversion still leave room for the current investment pace.");
        }
        return watchItems;
    }

    private boolean addUniqueNarrative(List<String> target, Set<String> seen, String value) {
        String normalized = trimToNull(value);
        String key = normalizeNarrativeBullet(normalized);
        if (normalized == null || key == null || seen.contains(key)) {
            return false;
        }
        seen.add(key);
        target.add(normalized);
        return true;
    }

    private boolean addUniqueEvidence(
            List<AnalysisReport.SupportingEvidence> target,
            Set<String> seen,
            AnalysisReport.SupportingEvidence evidence) {
        if (evidence == null) {
            return false;
        }
        String key = normalizeNarrativeBullet(
                firstNonBlank(
                        trimToNull(evidence.getLabel()) + "::" + trimToNull(evidence.getDetail()),
                        trimToNull(evidence.getDetail())));
        if (key == null || seen.contains(key)) {
            return false;
        }
        seen.add(key);
        target.add(evidence);
        return true;
    }

    private String buildSignalBullet(BusinessSignals.SignalItem signal, AnalysisContract contract, boolean isZh) {
        String title = resolveSignalDisplayTitle(signal, contract, isZh);
        String metricAnchor = buildMetricAnchorForText(firstNonBlank(signal.getSummary(), signal.getTitle()), contract, isZh);
        if (title == null) {
            return null;
        }
        String base = isZh
                ? "与“" + title + "”相关的业务进展是本期最值得关注的变化之一"
                : title + " was one of the clearest business changes this period";
        return appendMetricAnchor(base, metricAnchor, isZh);
    }

    private String buildSignalEvidenceDetail(
            BusinessSignals.SignalItem signal,
            AnalysisContract contract,
            boolean isZh,
            String mode) {
        String title = resolveSignalDisplayTitle(signal, contract, isZh);
        String metricAnchor = buildMetricAnchorForText(
                firstNonBlank(signal == null ? null : signal.getSummary(), signal == null ? null : signal.getTitle()),
                contract,
                isZh);
        if (title == null) {
            return metricAnchor;
        }

        String base;
        if ("bet".equals(mode)) {
            base = isZh
                    ? "管理层当前仍在围绕“" + title + "”投入资源、推进客户导入或商业化，这更像下一阶段增长押注，而不只是单季结果"
                    : "Management is still allocating resources to " + title
                            + ", which looks more like a next-phase growth bet than a one-quarter outcome";
        } else {
            base = isZh
                    ? "本期更具体的驱动来自“" + title + "”，它直接影响了需求、产品放量、客户导入或盈利兑现节奏"
                    : "A more specific operating driver this period was " + title
                            + ", which directly shaped demand, product ramp, customer adoption, or earnings delivery";
        }
        return appendMetricAnchor(base, metricAnchor, isZh);
    }

    private String buildSignalWatchItem(BusinessSignals.SignalItem signal, AnalysisContract contract, boolean isZh) {
        String title = resolveSignalDisplayTitle(signal, contract, isZh);
        String metricAnchor = buildMetricAnchorForText(firstNonBlank(signal.getSummary(), signal.getTitle()), contract, isZh);
        if (title == null) {
            return null;
        }
        String base = isZh
                ? "继续跟踪“" + title + "”的客户导入、放量节奏和商业化兑现情况"
                : "Keep tracking customer adoption, ramp, and commercialization progress around " + title;
        return appendMetricAnchor(base, metricAnchor, isZh);
    }

    private String localizedSignalTitle(BusinessSignals.SignalItem signal, boolean isZh) {
        String title = trimToNull(signal == null ? null : signal.getTitle());
        if (title == null) {
            return null;
        }
        if (!isZh) {
            return title;
        }
        String lower = title.toLowerCase(Locale.ROOT);
        if (lower.contains("serdes")) {
            return "SerDes 高速连接产品";
        }
        if (lower.contains("aec")) {
            return "AEC 连接产品";
        }
        if (lower.contains("optical dsp")) {
            return "Optical DSP 产品";
        }
        if (lower.contains("retimer")) {
            return "Retimer 连接芯片";
        }
        if (lower.contains("pcie")) {
            return "PCIe 连接产品";
        }
        if (lower.contains("ethernet")) {
            return "以太网连接产品组合";
        }
        if (lower.contains("hyperscaler")) {
            return "超大规模客户导入";
        }
        if (lower.contains("data-center connectivity") || lower.contains("high-speed connectivity")) {
            return "AI 数据中心高速互连产品";
        }
        if (lower.contains("cloud")) {
            return "云业务需求";
        }
        if (lower.contains("copilot")) {
            return "Copilot 商业化";
        }
        if (lower.contains("advertising")) {
            return "广告变现";
        }
        if (lower.contains("infrastructure")) {
            return "基础设施投入";
        }
        return title;
    }

    private String resolveSignalDisplayTitle(BusinessSignals.SignalItem signal, AnalysisContract contract, boolean isZh) {
        String localized = localizedSignalTitle(signal, isZh);
        if (localized != null
                && !"战略动作".equals(localized)
                && !"业务线 / 分部表现".equals(localized)
                && !"产品与服务进展".equals(localized)
                && !"管理层强调点".equals(localized)) {
            return localized;
        }

        FinancialFacts facts = contract == null ? null : contract.getFinancialFacts();
        String summary = trimToNull(facts == null ? null : facts.getMarketBusinessSummary());
        if (summary == null) {
            return localized;
        }

        List<String> productHints = extractProductHints(summary.toLowerCase(Locale.ROOT), isZh);
        if (!productHints.isEmpty()) {
            return String.join(isZh ? " / " : " / ", productHints);
        }
        return localized;
    }

    private List<BusinessSignals.SignalItem> collectPrimarySignals(BusinessSignals signals) {
        List<BusinessSignals.SignalItem> items = new ArrayList<>();
        appendSignals(items, signals == null ? null : signals.getSegmentPerformance());
        appendSignals(items, signals == null ? null : signals.getProductServiceUpdates());
        return items;
    }

    private List<BusinessSignals.SignalItem> collectDriverSignals(BusinessSignals signals) {
        List<BusinessSignals.SignalItem> items = new ArrayList<>();
        appendSignals(items, signals == null ? null : signals.getManagementFocus());
        appendSignals(items, signals == null ? null : signals.getSegmentPerformance());
        appendSignals(items, signals == null ? null : signals.getProductServiceUpdates());
        return items;
    }

    private List<BusinessSignals.SignalItem> collectStrategicSignals(BusinessSignals signals) {
        List<BusinessSignals.SignalItem> items = new ArrayList<>();
        appendSignals(items, signals == null ? null : signals.getStrategicMoves());
        appendSignals(items, signals == null ? null : signals.getCapexSignals());
        appendSignals(items, signals == null ? null : signals.getProductServiceUpdates());
        return items;
    }

    private List<BusinessSignals.SignalItem> collectWatchSignals(BusinessSignals signals) {
        List<BusinessSignals.SignalItem> items = new ArrayList<>();
        appendSignals(items, signals == null ? null : signals.getRiskSignals());
        appendSignals(items, signals == null ? null : signals.getCapexSignals());
        appendSignals(items, signals == null ? null : signals.getStrategicMoves());
        return items;
    }

    private void appendSignals(List<BusinessSignals.SignalItem> target, List<BusinessSignals.SignalItem> source) {
        if (source != null) {
            target.addAll(source.stream().filter(Objects::nonNull).toList());
        }
    }

    private List<ThemeDescriptor> collectThemeDescriptors(AnalysisContract contract, boolean isZh) {
        BusinessSignals signals = contract.getBusinessSignals();
        List<ThemeDescriptor> themes = new ArrayList<>();
        Set<String> seen = new LinkedHashSet<>();

        for (BusinessSignals.SignalItem item : collectPrimarySignals(signals)) {
            ThemeDescriptor theme = inferThemeDescriptor(item);
            if (seen.add(theme.key())) {
                themes.add(theme);
            }
            if (themes.size() >= 3) {
                return themes;
            }
        }

        for (BusinessSignals.SignalItem item : collectStrategicSignals(signals)) {
            ThemeDescriptor theme = inferThemeDescriptor(item);
            if (seen.add(theme.key())) {
                themes.add(theme);
            }
            if (themes.size() >= 3) {
                return themes;
            }
        }

        if (themes.isEmpty()) {
            themes.add(genericBusinessTheme());
        }
        return themes;
    }

    private ThemeDescriptor firstThemeFromSignals(BusinessSignals signals, boolean isZh, List<BusinessSignals.SignalItem> items) {
        for (BusinessSignals.SignalItem item : items) {
            ThemeDescriptor theme = inferThemeDescriptor(item);
            if (theme != null) {
                return theme;
            }
        }
        return null;
    }

    private ThemeDescriptor inferThemeDescriptor(BusinessSignals.SignalItem item) {
        String text = trimToNull(String.join(" ",
                item == null || item.getTitle() == null ? "" : item.getTitle(),
                item == null || item.getSummary() == null ? "" : item.getSummary(),
                item == null || item.getEvidenceSnippet() == null ? "" : item.getEvidenceSnippet()));
        return inferThemeDescriptor(text);
    }

    private ThemeDescriptor inferThemeDescriptor(String rawText) {
        String text = rawText == null ? "" : rawText.toLowerCase(Locale.ROOT);

        if (containsAny(text, "advertising", "ads", "ad pricing", "pricing", "impressions", "ad load", "business messaging")) {
            return new ThemeDescriptor("ad_monetization", "advertising monetization", "广告定价与变现");
        }
        if (containsAny(text, "reels", "threads", "short-form", "creator", "family of apps")) {
            return new ThemeDescriptor("new_surfaces", "new-surface monetization", "新流量场景商业化");
        }
        if (containsAny(text, "data center", "gpu", "capex", "capital expenditure", "infrastructure", "server", "compute", "cluster", "capacity")) {
            return new ThemeDescriptor("infrastructure", "infrastructure buildout", "算力与基础设施投入");
        }
        if (containsAny(text, "recommendation", "ranking")) {
            return new ThemeDescriptor("ai_efficiency", "AI products and recommendation efficiency", "AI产品与推荐效率");
        }
        if (containsAny(text, "meta ai", "copilot", "ai product", "ai assistant", "model", "inference", "genai")) {
            return new ThemeDescriptor("ai_productization", "AI product and model commercialization", "AI产品化与模型商业化");
        }
        if (containsAny(text, "azure", "cloud")) {
            return new ThemeDescriptor("cloud", "cloud demand", "云业务需求");
        }
        if (containsAny(text, "service", "services", "subscription", "renewal", "subscriber", "saas")) {
            return new ThemeDescriptor("service_mix", "service and subscription mix", "服务与订阅组合");
        }
        if (containsAny(text, "enterprise", "commercial", "dynamics", "office", "linkedin", "seat", "pipeline")) {
            return new ThemeDescriptor("enterprise", "enterprise demand", "企业客户需求");
        }
        if (containsAny(text, "reality labs", "hardware", "device", "vr", "wearables")) {
            return new ThemeDescriptor("hardware", "hardware and frontier bets", "硬件与前沿押注");
        }
        if (containsAny(text, "pricing", "mix")) {
            return new ThemeDescriptor("pricing_mix", "pricing and mix", "定价与产品组合");
        }
        if (containsAny(text, "engagement", "usage", "dau", "mau", "time spent")) {
            return new ThemeDescriptor("engagement", "engagement and user time", "用户参与度与使用时长");
        }
        if (containsAny(text, "efficiency", "discipline", "optimiz", "execution")) {
            return new ThemeDescriptor("execution", "execution discipline", "执行与效率");
        }
        if (containsAny(text, "competition", "competitive")) {
            return new ThemeDescriptor("competition", "competitive pressure", "竞争压力");
        }
        if (containsAny(text, "regulatory", "privacy", "litigation", "tariff")) {
            return new ThemeDescriptor("regulatory", "regulatory and platform risk", "监管与平台风险");
        }
        if (containsAny(text, "demand", "volume", "orders", "backlog")) {
            return new ThemeDescriptor("demand", "core demand", "核心需求");
        }
        return genericBusinessTheme();
    }

    private boolean containsAny(String text, String... keywords) {
        for (String keyword : keywords) {
            if (text.contains(keyword)) {
                return true;
            }
        }
        return false;
    }

    private String themeLabel(ThemeDescriptor descriptor, boolean isZh) {
        ThemeDescriptor resolved = descriptor == null ? genericBusinessTheme() : descriptor;
        return isZh ? resolved.zh() : resolved.en();
    }

    private ThemeDescriptor genericBusinessTheme() {
        return new ThemeDescriptor("generic_business", "core business execution", "核心业务执行");
    }

    private String prependBusinessIdentity(String sentence, String businessIdentityLead, boolean isZh) {
        String core = trimToNull(sentence);
        String identity = trimToNull(businessIdentityLead);
        if (core == null || identity == null) {
            return core;
        }
        return isZh ? identity + "，" + core : identity + ", " + core;
    }

    private String buildBusinessIdentityLead(AnalysisContract contract, boolean isZh) {
        FinancialFacts facts = contract == null ? null : contract.getFinancialFacts();
        String companyName = trimToNull(firstNonBlank(
                facts == null ? null : facts.getCompanyName(),
                contract == null ? null : contract.getCompanyName(),
                contract == null ? null : contract.getTicker()));
        String business = firstNonBlank(describeConcreteProductBusiness(contract, isZh), describeCompanyBusiness(contract, isZh));
        if (companyName == null || business == null || !isMeaningfulBusinessDescriptor(business, companyName,
                contract == null ? null : contract.getTicker())) {
            return null;
        }
        return isZh ? companyName + "是一家" + business : companyName + " is a " + business;
    }

    private String describeCompanyBusiness(AnalysisContract contract, boolean isZh) {
        CompanyProfile profile = contract == null ? null : contract.getCompanyProfile();
        String modeDriven = describeBusinessFromAnalysisMode(profile, isZh);
        if (modeDriven != null) {
            return modeDriven;
        }
        if (profile != null && profile.hasHighConfidenceBusinessDescription()) {
            String businessModelSummary = trimToNull(profile.getBusinessModelSummary());
            if (businessModelSummary != null) {
                String translated = isZh ? translateBusinessModelSummary(businessModelSummary) : businessModelSummary;
                if (translated != null) {
                    return translated;
                }
            }
        }
        return describeIndustryLevelBusiness(contract, isZh);
    }

    private String describeBusinessFromAnalysisMode(CompanyProfile profile, boolean isZh) {
        if (profile == null || !profile.hasHighConfidenceAnalysisMode() || profile.getAnalysisMode() == null) {
            return null;
        }
        List<String> tags = profile.getBusinessTags() == null ? List.of() : profile.getBusinessTags();
        return switch (profile.getAnalysisMode()) {
            case CRYPTO_TREASURY -> {
                if (tags.contains("ethereum_treasury")) {
                    yield isZh ? "以太坊财库策略公司" : "ethereum treasury strategy company";
                }
                if (tags.contains("bitcoin_treasury")) {
                    yield isZh ? "比特币财库策略公司" : "bitcoin treasury strategy company";
                }
                yield isZh ? "数字资产财库策略公司" : "digital asset treasury strategy company";
            }
            case CRYPTO_EXCHANGE -> isZh ? "加密资产交易与金融基础设施平台" : "crypto asset trading and financial infrastructure platform";
            case PAYMENT_FINTECH -> isZh ? "支付与金融科技平台" : "payments and fintech platform";
            case EXCHANGE_MARKET_INFRA -> isZh ? "金融市场基础设施与数据服务公司" : "financial market infrastructure and data services company";
            case ASSET_MANAGER -> isZh ? "资产管理公司" : "asset management company";
            case INSURANCE -> isZh ? "保险公司" : "insurance company";
            case REIT -> isZh ? "房地产投资信托" : "real estate investment trust";
            case SEMICONDUCTOR -> isZh ? "半导体与连接方案公司" : "semiconductor and connectivity solutions company";
            case TELECOM_NETWORKING -> isZh ? "通信与网络设备公司" : "communications and networking equipment company";
            case CONSUMER_PLATFORM -> isZh ? "消费互联网平台公司" : "consumer internet platform company";
            case BIOTECH_PRE_REVENUE -> isZh ? "临床阶段生物科技公司" : "clinical-stage biotech company";
            case COMMODITY_ENERGY -> isZh ? "资源与能源公司" : "commodity and energy company";
            case FINANCIAL -> isZh ? "金融服务公司" : "financial services company";
            case HOLDING -> isZh ? "控股与资本配置平台" : "holding and capital allocation platform";
            default -> null;
        };
    }

    private String describeIndustryLevelBusiness(AnalysisContract contract, boolean isZh) {
        FinancialFacts facts = contract == null ? null : contract.getFinancialFacts();
        String summary = trimToNull(facts == null ? null : facts.getMarketBusinessSummary());
        String industry = trimToNull(facts == null ? null : facts.getMarketIndustry());
        String sector = trimToNull(facts == null ? null : facts.getMarketSector());

        if (summary != null) {
            String lowerSummary = summary.toLowerCase(Locale.ROOT);
            if (containsAny(lowerSummary,
                    "ethereum treasury", "ether treasury", "eth treasury", "ethereum holdings", "ether holdings",
                    "digital asset treasury", "treasury strategy", "eth reserve")) {
                return isZh ? "以太坊财库策略公司" : "ethereum treasury strategy company";
            }
            if (containsAny(lowerSummary,
                    "bitcoin treasury", "btc treasury", "bitcoin holdings", "btc holdings",
                    "digital asset treasury", "treasury strategy", "bitcoin reserve")) {
                return isZh ? "比特币财库策略公司" : "bitcoin treasury strategy company";
            }
            if (containsAny(lowerSummary, "crypto", "cryptocurrency", "digital asset", "blockchain", "stablecoin", "staking", "custody")) {
                return isZh ? "加密资产交易与金融基础设施平台" : "crypto asset trading and financial infrastructure platform";
            }
            if (containsAny(lowerSummary, "advertising", "ads", "advertisers", "search", "youtube")
                    && containsAny(lowerSummary, "cloud", "google cloud")) {
                return isZh ? "数字广告与云服务公司" : "digital advertising and cloud services company";
            }
            if (containsAny(lowerSummary, "advertising", "ads", "advertisers", "search", "youtube")) {
                return isZh ? "数字广告与互联网平台公司" : "digital advertising and internet platform company";
            }
            if (containsAny(lowerSummary, "electric vehicle", "electric vehicles", "vehicle", "vehicles")
                    && containsAny(lowerSummary, "energy storage", "energy generation", "solar")) {
                return isZh ? "电动车与储能公司" : "electric vehicle and energy storage company";
            }
            if (containsAny(lowerSummary, "smartphone", "smartphones", "iphone", "personal computer", "ipad", "wearables")) {
                return isZh ? "消费电子与软件服务公司" : "consumer electronics and software services company";
            }
            if (containsAny(lowerSummary,
                    "serdes", "serializer/deserializer", "active electrical cable", "aec", "optical dsp", "retimer", "pcie", "ethernet")) {
                return isZh ? "高速互连芯片与连接方案公司" : "high-speed interconnect chip and connectivity solutions company";
            }
            if (containsAny(lowerSummary, "brokerage", "event contracts", "index options", "futures")) {
                return isZh ? "零售经纪与衍生品交易平台" : "retail brokerage and derivatives trading platform";
            }
        }

        if (industry != null) {
            String lower = industry.toLowerCase(Locale.ROOT);
            if (lower.contains("semiconductor")) {
                return isZh ? "半导体公司" : "semiconductor company";
            }
            if (lower.contains("software - infrastructure")) {
                return isZh ? "企业基础设施软件公司" : "enterprise infrastructure software company";
            }
            if (lower.contains("software - application")) {
                return isZh ? "应用软件公司" : "application software company";
            }
            if (lower.contains("communication equipment") || lower.contains("networking")) {
                return isZh ? "通信与网络设备公司" : "communications and networking equipment company";
            }
            if (lower.contains("computer hardware")) {
                return isZh ? "计算硬件公司" : "computer hardware company";
            }
            if (lower.contains("information technology services")) {
                return isZh ? "信息技术服务公司" : "information technology services company";
            }
            if (lower.contains("internet content") || lower.contains("internet content & information")) {
                return isZh ? "互联网平台公司" : "internet platform company";
            }
            if (lower.contains("banks")) {
                return isZh ? "银行" : "bank";
            }
            if (lower.contains("insurance")) {
                return isZh ? "保险公司" : "insurance company";
            }
            if (lower.contains("asset management")) {
                return isZh ? "资产管理公司" : "asset management company";
            }
            if (lower.contains("credit services")) {
                return isZh ? "消费信贷与支付公司" : "consumer credit and payments company";
            }
            if (lower.contains("capital markets") || lower.contains("financial data") || lower.contains("financial exchanges")) {
                return isZh ? "金融基础设施与数据服务公司" : "financial infrastructure and data services company";
            }
            return isZh ? industry + "领域公司" : industry + " company";
        }

        if (sector != null) {
            String lower = sector.toLowerCase(Locale.ROOT);
            if (lower.contains("technology")) {
                return isZh ? "科技公司" : "technology company";
            }
            if (lower.contains("financial")) {
                return isZh ? "金融服务公司" : "financial services company";
            }
        }
        return null;
    }

    private String describeConcreteProductBusiness(AnalysisContract contract, boolean isZh) {
        CompanyProfile profile = contract == null ? null : contract.getCompanyProfile();
        if (profile != null && profile.hasHighConfidenceAnalysisMode()
                && CompanyProfile.AnalysisMode.CRYPTO_TREASURY.equals(profile.getAnalysisMode())) {
            List<String> tags = profile.getBusinessTags() == null ? List.of() : profile.getBusinessTags();
            if (tags.contains("ethereum_treasury")) {
                return isZh ? "以以太坊储备与资本配置为核心的公司" : "company centered on ethereum reserves and capital allocation";
            }
            if (tags.contains("bitcoin_treasury")) {
                return isZh ? "以比特币储备与资本配置为核心的公司" : "company centered on bitcoin reserves and capital allocation";
            }
            return isZh ? "以数字资产储备与资本配置为核心的公司" : "company centered on digital asset reserves and capital allocation";
        }
        if (profile != null
                && profile.hasHighConfidenceBusinessDescription()
                && profile.getProductLines() != null
                && !profile.getProductLines().isEmpty()) {
            List<String> displayProductLines = selectDisplayProductLines(profile.getProductLines(), isZh);
            String productPhrase = displayProductLines.isEmpty()
                    ? null
                    : String.join(isZh ? "、" : ", ", displayProductLines);
            String rawCustomer = firstListItem(profile.getCustomerTypes());
            String customerPhrase = shouldDisplayCustomerType(rawCustomer)
                    ? localizeCustomerType(rawCustomer, isZh)
                    : null;
            if (productPhrase == null) {
                return null;
            }
            if (customerPhrase != null) {
                return isZh
                        ? "提供" + productPhrase + "、面向" + customerPhrase + "的公司"
                        : "company providing " + productPhrase + " for " + customerPhrase;
            }
            return isZh ? "提供" + productPhrase + "的公司" : "company providing " + productPhrase;
        }

        FinancialFacts facts = contract == null ? null : contract.getFinancialFacts();
        String summary = trimToNull(facts == null ? null : facts.getMarketBusinessSummary());
        if (summary == null) {
            return null;
        }

        String lower = summary.toLowerCase(Locale.ROOT);
        if (containsAny(lower, "serdes", "serializer/deserializer", "active electrical cable", "aec", "optical dsp", "retimer", "pcie", "ethernet")) {
            List<String> products = extractProductHints(lower, isZh);
            String productPhrase = products.isEmpty()
                    ? (isZh ? "高速互连芯片与连接方案" : "high-speed interconnect chips and connectivity solutions")
                    : String.join(isZh ? "、" : ", ", products);
            return isZh
                    ? "提供" + productPhrase + "的数据中心高速互连芯片公司"
                    : "data-center connectivity chip company providing " + productPhrase;
        }
        return null;
    }

    private List<String> extractProductHints(String lowerSummary, boolean isZh) {
        List<String> products = new ArrayList<>();
        if (lowerSummary == null) {
            return products;
        }

        addIfMissing(products, containsAny(lowerSummary, "serdes", "serializer/deserializer"),
                isZh ? "SerDes 芯片" : "SerDes chips");
        addIfMissing(products, containsAny(lowerSummary, "active electrical cable", "aec"),
                isZh ? "AEC 连接方案" : "AEC connectivity");
        addIfMissing(products, containsAny(lowerSummary, "optical dsp"),
                isZh ? "Optical DSP 芯片" : "Optical DSP chips");
        addIfMissing(products, containsAny(lowerSummary, "retimer"),
                isZh ? "Retimer 芯片" : "retimer chips");
        addIfMissing(products, containsAny(lowerSummary, "pcie"),
                isZh ? "PCIe 连接产品" : "PCIe connectivity products");
        addIfMissing(products, containsAny(lowerSummary, "ethernet"),
                isZh ? "以太网连接产品" : "Ethernet connectivity products");
        return products.stream().limit(3).toList();
    }

    private List<String> selectDisplayProductLines(List<String> productLines, boolean isZh) {
        if (productLines == null || productLines.isEmpty()) {
            return List.of();
        }
        return productLines.stream()
                .filter(Objects::nonNull)
                .map(String::trim)
                .filter(value -> !value.isBlank())
                .sorted(Comparator.comparingInt(this::productDisplayPriority))
                .map(value -> localizeProductLine(value, isZh))
                .distinct()
                .limit(3)
                .toList();
    }

    private int productDisplayPriority(String productLine) {
        String lower = productLine.toLowerCase(Locale.ROOT);
        if (containsAny(lower,
                "smartphones", "personal computers", "tablets", "wearables", "accessories",
                "electric vehicles", "energy storage", "energy generation",
                "serdes", "aec", "optical dsp", "retimer", "pcie", "ethernet",
                "brokerage", "crypto asset trading", "custody", "staking", "stablecoin",
                "gold subscription", "event contracts", "index options", "futures", "cloud services", "youtube")) {
            return 0;
        }
        if (containsAny(lower, "services")) {
            return 1;
        }
        if (containsAny(lower, "subscriptions", "advertising", "credit card", "deposit")) {
            return 3;
        }
        return 2;
    }

    private String localizeProductLine(String value, boolean isZh) {
        String normalized = trimToNull(value);
        if (normalized == null || !isZh) {
            return normalized;
        }
        String lower = normalized.toLowerCase(Locale.ROOT);
        if (lower.contains("smartphones")) {
            return "智能手机";
        }
        if (lower.contains("personal computers")) {
            return "个人电脑";
        }
        if (lower.contains("tablets")) {
            return "平板";
        }
        if (lower.contains("wearables")) {
            return "可穿戴设备与配件";
        }
        if (lower.contains("services")) {
            return "服务";
        }
        if (lower.contains("electric vehicles")) {
            return "电动车";
        }
        if (lower.contains("energy storage")) {
            return "储能系统";
        }
        if (lower.contains("energy generation")) {
            return "能源发电系统";
        }
        if (lower.contains("brokerage")) {
            return "经纪业务";
        }
        if (lower.contains("crypto asset trading")) {
            return "加密资产交易";
        }
        if (lower.contains("custody")) {
            return "托管";
        }
        if (lower.contains("staking")) {
            return "质押";
        }
        if (lower.contains("stablecoin")) {
            return "稳定币基础设施";
        }
        if (lower.contains("gold subscription")) {
            return "Gold 订阅";
        }
        if (lower.contains("event contracts")) {
            return "事件合约";
        }
        if (lower.contains("index options")) {
            return "指数期权";
        }
        if (lower.contains("futures")) {
            return "期货";
        }
        if (lower.contains("credit card")) {
            return "信用卡";
        }
        if (lower.contains("advertising")) {
            return "广告";
        }
        if (lower.contains("deposit")) {
            return "存款产品";
        }
        if (lower.contains("cloud services")) {
            return "云服务";
        }
        if (lower.contains("youtube")) {
            return "YouTube";
        }
        return normalized;
    }

    private String localizeCustomerType(String value, boolean isZh) {
        String normalized = trimToNull(value);
        if (normalized == null || !isZh) {
            return normalized;
        }
        String lower = normalized.toLowerCase(Locale.ROOT);
        if (lower.contains("enterprise customers")) {
            return "企业客户";
        }
        if (lower.contains("advertisers")) {
            return "广告主";
        }
        if (lower.contains("merchants")) {
            return "商户";
        }
        if (lower.contains("financial institutions")) {
            return "金融机构";
        }
        if (lower.contains("institutional customers")) {
            return "机构客户";
        }
        if (lower.contains("retail investors")) {
            return "零售投资者";
        }
        if (lower.contains("cloud and data-center customers")) {
            return "云和数据中心客户";
        }
        if (lower.contains("hyperscalers")) {
            return "超大规模云客户";
        }
        if (lower.contains("networking equipment customers")) {
            return "网络设备客户";
        }
        return normalized;
    }

    private String localizeWhatItSells(String value, boolean isZh) {
        String normalized = trimToNull(value);
        if (normalized == null || !isZh) {
            return normalized;
        }
        return firstNonBlank(
                translateBusinessModelSummary(normalized),
                normalized);
    }

    private void addIfMissing(List<String> target, boolean condition, String value) {
        if (condition && value != null && !target.contains(value)) {
            target.add(value);
        }
    }

    private String firstListItem(List<String> values) {
        if (values == null || values.isEmpty()) {
            return null;
        }
        return trimToNull(values.get(0));
    }

    private boolean isMeaningfulBusinessDescriptor(String business, String companyName, String ticker) {
        String normalizedBusiness = normalizeForComparison(business);
        if (normalizedBusiness == null) {
            return false;
        }
        String normalizedCompanyName = normalizeForComparison(companyName);
        String normalizedTicker = normalizeForComparison(ticker);
        if (normalizedBusiness.equals(normalizedCompanyName)
                || normalizedBusiness.equals(normalizedTicker)
                || (normalizedCompanyName != null && normalizedBusiness.contains(normalizedCompanyName))) {
            return false;
        }
        return normalizedBusiness.length() >= 8;
    }

    private String normalizeForComparison(String value) {
        String normalized = trimToNull(value);
        if (normalized == null) {
            return null;
        }
        return normalized.toLowerCase(Locale.ROOT).replaceAll("[^a-z0-9\\u4e00-\\u9fa5]+", "");
    }

    private boolean sameMetricAnchor(String first, String second) {
        String normalizedFirst = normalizeAnchor(first);
        String normalizedSecond = normalizeAnchor(second);
        return normalizedFirst != null && normalizedFirst.equals(normalizedSecond);
    }

    private String normalizeAnchor(String value) {
        String normalized = trimToNull(value);
        if (normalized == null) {
            return null;
        }
        return normalized.replaceAll("[，,。.!?；;\\s]+", "").toLowerCase(Locale.ROOT);
    }

    private String translateBusinessModelSummary(String summary) {
        String lower = summary.toLowerCase(Locale.ROOT);
        if (containsAny(lower, "smartphones", "personal computers", "tablets", "wearables", "accessories", "services")) {
            return "消费电子与软件服务公司";
        }
        if (containsAny(lower, "electric vehicles", "energy generation", "energy storage")) {
            return "电动车与储能公司";
        }
        if (containsAny(lower, "serdes", "active electrical cable", "optical dsp", "retimer", "pcie", "ethernet")) {
            return "高速互连芯片与连接方案公司";
        }
        if (containsAny(lower, "crypto", "cryptocurrency", "digital asset", "blockchain", "stablecoin", "staking", "custody")) {
            return "加密资产交易与金融基础设施平台";
        }
        if (containsAny(lower, "brokerage", "gold subscription", "event contracts", "index options", "futures")) {
            return "零售经纪与衍生品交易平台";
        }
        if (containsAny(lower, "advertising", "ads", "advertisers", "search", "youtube")
                && containsAny(lower, "cloud", "google cloud")) {
            return "数字广告与云服务公司";
        }
        if (containsAny(lower, "advertising", "ads", "advertisers", "search", "youtube")) {
            return "数字广告与互联网平台公司";
        }
        return null;
    }

    private boolean shouldDisplayCustomerType(String customerType) {
        String normalized = trimToNull(customerType);
        if (normalized == null) {
            return false;
        }
        String lower = normalized.toLowerCase(Locale.ROOT);
        return !containsAny(lower, "enterprise customers");
    }

    private String buildProfileWhatChanged(AnalysisContract contract, boolean isZh) {
        CompanyProfile profile = contract == null ? null : contract.getCompanyProfile();
        if (profile == null || profile.isEmpty()) {
            return null;
        }
        String products = joinTop(profile.getProductLines(), isZh);
        String customers = joinTop(profile.getCustomerTypes(), isZh);
        String anchor = buildMetricAnchorForText(firstNonBlank(products, customers), contract, isZh);
        if (products == null && customers == null) {
            return null;
        }
        String base = isZh
                ? firstNonBlank(
                        products != null && customers != null ? products + " 对 " + customers + " 的出货和导入仍在推进" : null,
                        products != null ? products + " 这条产品线仍是本期变化的核心载体" : null,
                        customers != null ? customers + " 的需求变化仍是本期最值得关注的业务线索" : null)
                : firstNonBlank(
                        products != null && customers != null ? products + " shipments and adoption into " + customers + " continued moving the quarter" : null,
                        products != null ? products + " remained at the center of the business change this period" : null,
                        customers != null ? demandPhrase(customers) + " remained the clearest business clue this period" : null);
        return appendMetricAnchor(base, anchor, isZh);
    }

    private String buildProfileDriverDetail(AnalysisContract contract, boolean isZh) {
        CompanyProfile profile = contract == null ? null : contract.getCompanyProfile();
        if (profile == null || profile.isEmpty()) {
            return null;
        }
        String products = joinTop(profile.getProductLines(), isZh);
        String customers = joinTop(profile.getCustomerTypes(), isZh);
        String kpis = joinTop(profile.getKeyKpis(), isZh);
        if (products == null && customers == null && kpis == null) {
            return null;
        }
        if (isZh) {
            return firstNonBlank(
                    products != null && customers != null
                            ? "更具体的驱动应落在" + products + "面向" + customers + "的放量、导入和订单节奏，而不是泛泛的行业需求表述。"
                            : null,
                    products != null && kpis != null
                            ? "更具体的驱动应围绕" + products + "的表现，并结合" + kpis + "去验证需求和盈利兑现。"
                            : null,
                    "更具体的驱动应优先围绕公司画像中的产品线、客户类型和专属 KPI 来理解。");
        }
        return firstNonBlank(
                products != null && customers != null
                        ? "The more specific driver should be product ramp, customer adoption, and order timing in " + products + " sold into " + customers + ", not a generic industry-demand recap."
                        : null,
                products != null && kpis != null
                        ? "The more specific driver should be read through " + products + " and validated against company KPIs such as " + kpis + "."
                        : null,
                "The more specific driver should be framed around the company's product lines, customer types, and company-specific KPIs.");
    }

    private String buildProfileStrategicBetDetail(AnalysisContract contract, boolean isZh) {
        CompanyProfile profile = contract == null ? null : contract.getCompanyProfile();
        if (profile == null || profile.isEmpty()) {
            return null;
        }
        String products = joinTop(profile.getProductLines(), isZh);
        String customers = joinTop(profile.getCustomerTypes(), isZh);
        if (products == null) {
            return null;
        }
        return isZh
                ? firstNonBlank(
                        customers != null
                                ? "下一阶段最值得跟踪的押注，仍是" + products + "在" + customers + "中的扩张、导入和商业化兑现。"
                                : null,
                        "下一阶段最值得跟踪的押注，仍是" + products + "这条产品线能否继续扩大收入与利润贡献。")
                : firstNonBlank(
                        customers != null
                                ? "The next strategic bet to watch is still the expansion, adoption, and commercialization of " + products + " within " + customers + "."
                                : null,
                        "The next strategic bet to watch is whether " + products + " can keep expanding its revenue and profit contribution.");
    }

    private String buildProfileWatchItem(AnalysisContract contract, boolean isZh) {
        CompanyProfile profile = contract == null ? null : contract.getCompanyProfile();
        if (profile == null || profile.isEmpty()) {
            return null;
        }
        String products = joinTop(profile.getProductLines(), isZh);
        String kpis = joinTop(profile.getKeyKpis(), isZh);
        if (products == null && kpis == null) {
            return null;
        }
        return isZh
                ? firstNonBlank(
                        products != null && kpis != null
                                ? "继续跟踪" + products + "的放量与导入，并用" + kpis + "来验证商业化是否真的在兑现。"
                                : null,
                        products != null
                                ? "继续跟踪" + products + "的放量、客户导入和贡献占比变化。"
                                : null,
                        "继续跟踪公司画像里最关键的专属 KPI 是否继续改善。")
                : firstNonBlank(
                        products != null && kpis != null
                                ? "Keep tracking adoption and ramp in " + products + " and validate commercialization against KPIs such as " + kpis + "."
                                : null,
                        products != null
                                ? "Keep tracking ramp, customer adoption, and contribution mix around " + products + "."
                                : null,
                        "Keep tracking whether the company's most important bespoke KPIs continue to improve.");
    }

    private String joinTop(List<String> values, boolean isZh) {
        if (values == null || values.isEmpty()) {
            return null;
        }
        return String.join(isZh ? "、" : ", ", values.stream().filter(Objects::nonNull).limit(3).toList());
    }

    private String demandPhrase(String customerPhrase) {
        return customerPhrase == null ? "Customer demand" : customerPhrase + " demand";
    }

    private ThemeDescriptor executionTheme() {
        return new ThemeDescriptor("execution", "execution discipline", "执行与效率");
    }

    private ThemeDescriptor infrastructureTheme() {
        return new ThemeDescriptor("infrastructure", "infrastructure buildout", "算力与基础设施投入");
    }

    private List<AnalysisReport.SupportingEvidence> mergeSupportingEvidence(
            List<AnalysisReport.SupportingEvidence> first,
            List<AnalysisReport.SupportingEvidence> second) {
        List<AnalysisReport.SupportingEvidence> merged = new ArrayList<>();
        if (first != null) {
            merged.addAll(first);
        }
        if (second != null) {
            merged.addAll(second);
        }
        if (merged.isEmpty()) {
            return null;
        }
        return merged.stream().limit(4).toList();
    }

    private String capitalize(String value) {
        if (value == null || value.isBlank()) {
            return value;
        }
        return Character.toUpperCase(value.charAt(0)) + value.substring(1);
    }

    protected AnalysisReport buildFallbackReportForAgent(String agentName, AnalysisContract contract, String lang) {
        if (contract == null || contract.getFinancialFacts() == null) {
            return AnalysisReport.builder().build();
        }

        FinancialFacts facts = contract.getFinancialFacts();
        String periodLabel = trimToNull(facts.getPeriod()) != null ? facts.getPeriod() : trimToNull(contract.getPeriod());
        boolean isZh = "zh".equalsIgnoreCase(lang);

        return switch (agentName) {
            case "InsightsAgent" -> AnalysisReport.builder()
                    .dupontAnalysis(buildFallbackDupontAnalysis(facts, periodLabel, isZh))
                    .insightEngine(AnalysisReport.InsightEngine.builder()
                            .accountingChanges(List.of())
                            .rootCauseAnalysis(buildFallbackRootCauseAnalysis(facts, periodLabel, isZh))
                            .build())
                    .build();
            case "FactorsAgent" -> AnalysisReport.builder()
                    .factorAnalysis(buildFallbackFactorAnalysis(facts, periodLabel, isZh))
                    .topicTrends(buildFallbackTopicTrends(facts, isZh))
                    .build();
            case "DriversAgent" -> AnalysisReport.builder()
                    .businessDrivers(buildFallbackBusinessDrivers(contract, facts, periodLabel, isZh))
                    .riskFactors(buildFallbackRiskFactors(contract, periodLabel, isZh))
                    .bullCase(buildFallbackBullCase(contract, facts, periodLabel, isZh))
                    .bearCase(buildFallbackBearCase(contract, facts, periodLabel, isZh))
                    .build();
            default -> AnalysisReport.builder().build();
        };
    }

    private AnalysisReport.DuPontAnalysis buildFallbackDupontAnalysis(FinancialFacts facts, String periodLabel,
            boolean isZh) {
        BigDecimal netProfitMargin = facts.getNetMargin();
        BigDecimal assetTurnover = safeDivide(facts.getRevenue(), facts.getTotalAssets());
        BigDecimal equityMultiplier = safeDivide(facts.getTotalAssets(), facts.getTotalEquity());
        BigDecimal returnOnEquity = facts.getReturnOnEquity();

        String interpretation = isZh
                ? String.format(Locale.ROOT,
                        "%s的ROE拆解采用财务事实直接回填。净利率%s、资产周转率%s、权益乘数%s，反映了公司当前盈利能力、资产使用效率和资本结构的共同作用。",
                        describePeriod(periodLabel, true),
                        formatPercentOrFallback(netProfitMargin),
                        formatRatio(assetTurnover),
                        formatRatio(equityMultiplier))
                : String.format(Locale.ROOT,
                        "This fallback DuPont view for %s is derived directly from financial facts. Net margin of %s, asset turnover of %s, and an equity multiplier of %s summarize profitability, asset efficiency, and capital structure.",
                        describePeriod(periodLabel, false),
                        formatPercentOrFallback(netProfitMargin),
                        formatRatio(assetTurnover),
                        formatRatio(equityMultiplier));

        return AnalysisReport.DuPontAnalysis.builder()
                .netProfitMargin(formatPercentOrFallback(netProfitMargin))
                .assetTurnover(formatRatio(assetTurnover))
                .equityMultiplier(formatRatio(equityMultiplier))
                .returnOnEquity(formatPercentOrFallback(returnOnEquity))
                .interpretation(interpretation)
                .build();
    }

    private List<AnalysisReport.InsightEngine.RootCause> buildFallbackRootCauseAnalysis(FinancialFacts facts,
            String periodLabel, boolean isZh) {
        List<AnalysisReport.InsightEngine.RootCause> items = new ArrayList<>();

        if (facts.getRevenueYoY() != null) {
            items.add(buildRootCause(
                    isZh ? "营收" : "Revenue",
                    isZh
                            ? String.format(Locale.ROOT, "%s营收同比%s%s，说明需求和产品组合仍是本期表现的主要驱动。",
                                    describePeriod(periodLabel, true),
                                    facts.getRevenueYoY().compareTo(BigDecimal.ZERO) >= 0 ? "增长" : "下滑",
                                    formatPercentAbs(facts.getRevenueYoY()))
                            : String.format(Locale.ROOT,
                                    "%s revenue changed by %s year over year, making demand and mix the primary operating driver in the reported quarter.",
                                    describePeriod(periodLabel, false),
                                    formatSignedPercent(facts.getRevenueYoY())),
                    isZh
                            ? String.format(Locale.ROOT, "%s营收为%s，同比%s。", describePeriod(periodLabel, true),
                                    formatCurrency(facts.getRevenue(), facts.getCurrency()),
                                    formatSignedPercent(facts.getRevenueYoY()))
                            : String.format(Locale.ROOT, "%s revenue was %s with %s YoY growth.",
                                    describePeriod(periodLabel, false),
                                    formatCurrency(facts.getRevenue(), facts.getCurrency()),
                                    formatSignedPercent(facts.getRevenueYoY()))));
        }

        if (facts.getGrossMargin() != null) {
            items.add(buildRootCause(
                    isZh ? "毛利率" : "Gross Margin",
                    isZh
                            ? String.format(Locale.ROOT, "毛利率为%s，%s，显示定价能力和成本控制仍在主导利润质量。",
                                    formatPercentOrFallback(facts.getGrossMargin()),
                                    describeMarginDelta(facts.getGrossMarginChange(), true))
                            : String.format(Locale.ROOT,
                                    "Gross margin came in at %s, %s, indicating that pricing power and cost control remain central to profit quality.",
                                    formatPercentOrFallback(facts.getGrossMargin()),
                                    describeMarginDelta(facts.getGrossMarginChange(), false)),
                    isZh
                            ? String.format(Locale.ROOT, "毛利率%s，变动%s。", formatPercentOrFallback(facts.getGrossMargin()),
                                    formatSignedPercent(facts.getGrossMarginChange()))
                            : String.format(Locale.ROOT, "Gross margin was %s with a %s change.",
                                    formatPercentOrFallback(facts.getGrossMargin()),
                                    formatSignedPercent(facts.getGrossMarginChange()))));
        }

        BigDecimal cashFlowDelta = facts.getOperatingCashFlowYoY() != null ? facts.getOperatingCashFlowYoY()
                : facts.getFreeCashFlowYoY();
        if (cashFlowDelta != null) {
            items.add(buildRootCause(
                    isZh ? "现金流" : "Cash Flow",
                    isZh
                            ? String.format(Locale.ROOT, "现金流同比%s%s，说明利润向现金的转化仍是本期的重要支撑因素。",
                                    cashFlowDelta.compareTo(BigDecimal.ZERO) >= 0 ? "改善" : "承压",
                                    formatPercentAbs(cashFlowDelta))
                            : String.format(Locale.ROOT,
                                    "Cash generation moved %s year over year, showing that cash conversion is still a major support for the quarter.",
                                    formatSignedPercent(cashFlowDelta)),
                    isZh
                            ? String.format(Locale.ROOT, "经营现金流%s，同比%s。",
                                    formatCurrency(facts.getOperatingCashFlow(), facts.getCurrency()),
                                    formatSignedPercent(cashFlowDelta))
                            : String.format(Locale.ROOT, "Operating cash flow was %s with %s YoY change.",
                                    formatCurrency(facts.getOperatingCashFlow(), facts.getCurrency()),
                                    formatSignedPercent(cashFlowDelta))));
        }

        if (items.isEmpty()) {
            items.add(buildRootCause(
                    isZh ? "盈利能力" : "Profitability",
                    isZh ? "财务事实表明公司仍保持可解释的盈利能力轮廓，后端已提供最小兜底分析。" :
                            "Financial facts still provide a coherent profitability profile, so the backend supplied a minimum fallback analysis.",
                    isZh ? "已使用财务事实进行后端兜底。" : "Backend fallback derived directly from financial facts."));
        }

        return items;
    }

    private AnalysisReport.FactorAnalysis buildFallbackFactorAnalysis(FinancialFacts facts, String periodLabel,
            boolean isZh) {
        return AnalysisReport.FactorAnalysis.builder()
                .revenueBridge(List.of(
                        buildFactor(
                                isZh ? "需求/销量" : "Demand / Volume",
                                impactSign(facts.getRevenueYoY()),
                                isZh
                                        ? String.format(Locale.ROOT, "%s营收同比%s，说明需求仍在驱动收入表现。",
                                                describePeriod(periodLabel, true),
                                                formatSignedPercent(facts.getRevenueYoY()))
                                        : String.format(Locale.ROOT,
                                                "%s revenue changed %s year over year, indicating that demand is still the primary top-line driver.",
                                                describePeriod(periodLabel, false),
                                                formatSignedPercent(facts.getRevenueYoY()))),
                        buildFactor(
                                isZh ? "产品组合/定价" : "Mix / Pricing",
                                impactSign(facts.getGrossMarginChange()),
                                isZh
                                        ? String.format(Locale.ROOT, "毛利率%s，%s，显示产品组合和定价仍在影响收入质量。",
                                                formatPercentOrFallback(facts.getGrossMargin()),
                                                describeMarginDelta(facts.getGrossMarginChange(), true))
                                        : String.format(Locale.ROOT,
                                                "Gross margin was %s, %s, showing that mix and pricing still influence revenue quality.",
                                                formatPercentOrFallback(facts.getGrossMargin()),
                                                describeMarginDelta(facts.getGrossMarginChange(), false))),
                        buildFactor(
                                isZh ? "其他因素" : "Other",
                                "flat",
                                isZh ? "未直接观测到足够的结构化外汇或一次性项目数据，兜底分析保持中性。"
                                        : "No direct FX or one-off structured signal was available in facts, so the fallback keeps this bucket neutral.")))
                .marginBridge(List.of(
                        buildFactor(
                                isZh ? "毛利率变化" : "Gross Margin Change",
                                impactSign(facts.getGrossMarginChange()),
                                isZh
                                        ? String.format(Locale.ROOT, "毛利率变动为%s，直接影响本期利润质量。",
                                                formatSignedPercent(facts.getGrossMarginChange()))
                                        : String.format(Locale.ROOT,
                                                "Gross margin changed by %s, directly affecting profit quality for the period.",
                                                formatSignedPercent(facts.getGrossMarginChange()))),
                        buildFactor(
                                isZh ? "经营杠杆" : "Operating Leverage",
                                impactSign(facts.getNetMarginChange()),
                                isZh
                                        ? String.format(Locale.ROOT, "净利率变动为%s，说明经营杠杆和费用控制仍在影响利润率。",
                                                formatSignedPercent(facts.getNetMarginChange()))
                                        : String.format(Locale.ROOT,
                                                "Net margin changed by %s, suggesting that operating leverage and expense control continue to drive margins.",
                                                formatSignedPercent(facts.getNetMarginChange()))),
                        buildFactor(
                                isZh ? "现金转化" : "Cash Conversion",
                                impactSign(facts.getOperatingCashFlowYoY() != null ? facts.getOperatingCashFlowYoY()
                                        : facts.getFreeCashFlowYoY()),
                                isZh
                                        ? String.format(Locale.ROOT, "现金流同比%s，说明利润向现金的转化%s。",
                                                formatSignedPercent(
                                                        facts.getOperatingCashFlowYoY() != null
                                                                ? facts.getOperatingCashFlowYoY()
                                                                : facts.getFreeCashFlowYoY()),
                                                (facts.getOperatingCashFlowYoY() != null
                                                        ? facts.getOperatingCashFlowYoY()
                                                        : facts.getFreeCashFlowYoY()) != null
                                                                && (facts.getOperatingCashFlowYoY() != null
                                                                        ? facts.getOperatingCashFlowYoY()
                                                                        : facts.getFreeCashFlowYoY())
                                                                        .compareTo(BigDecimal.ZERO) >= 0
                                                                                ? "改善"
                                                                                : "承压")
                                        : String.format(Locale.ROOT,
                                                "Cash flow moved %s year over year, showing that profit-to-cash conversion is %s.",
                                                formatSignedPercent(
                                                        facts.getOperatingCashFlowYoY() != null
                                                                ? facts.getOperatingCashFlowYoY()
                                                                : facts.getFreeCashFlowYoY()),
                                                (facts.getOperatingCashFlowYoY() != null
                                                        ? facts.getOperatingCashFlowYoY()
                                                        : facts.getFreeCashFlowYoY()) != null
                                                                && (facts.getOperatingCashFlowYoY() != null
                                                                        ? facts.getOperatingCashFlowYoY()
                                                                        : facts.getFreeCashFlowYoY())
                                                                        .compareTo(BigDecimal.ZERO) >= 0
                                                                                ? "improving"
                                                                                : "under pressure"))))
                .build();
    }

    private List<AnalysisReport.TopicTrend> buildFallbackTopicTrends(FinancialFacts facts, boolean isZh) {
        return List.of(
                buildTopicTrend(
                        isZh ? "营收增长" : "Revenue Growth",
                        scoreTopicFrequency(facts.getRevenueYoY(), 72, 58, 44),
                        sentimentFromDelta(facts.getRevenueYoY())),
                buildTopicTrend(
                        isZh ? "利润率" : "Margins",
                        scoreTopicFrequency(facts.getGrossMarginChange(), 68, 54, 40),
                        sentimentFromDelta(facts.getGrossMarginChange())),
                buildTopicTrend(
                        isZh ? "现金流" : "Cash Flow",
                        scoreTopicFrequency(preferredCashDelta(facts), 64, 50, 36),
                        sentimentFromDelta(preferredCashDelta(facts))),
                buildTopicTrend(
                        isZh ? "资本效率" : "Capital Efficiency",
                        scoreTopicFrequency(facts.getReturnOnEquity(), 61, 49, 37),
                        sentimentFromLevel(facts.getReturnOnEquity(), new BigDecimal("0.12"), new BigDecimal("0.06"))),
                buildTopicTrend(
                        isZh ? "估值" : "Valuation",
                        34,
                        "neutral"));
    }

    private List<AnalysisReport.BusinessDriver> buildFallbackBusinessDrivers(AnalysisContract contract, FinancialFacts facts,
            String periodLabel, boolean isZh) {
        List<AnalysisReport.BusinessDriver> drivers = new ArrayList<>();
        CompanyProfile profile = contract == null ? null : contract.getCompanyProfile();
        String products = profile == null ? null : joinTop(profile.getProductLines(), isZh);
        String customers = profile == null ? null : joinTop(profile.getCustomerTypes(), isZh);
        String kpis = profile == null ? null : joinTop(profile.getKeyKpis(), isZh);

        drivers.add(AnalysisReport.BusinessDriver.builder()
                .title(firstNonBlank(
                        products != null ? (isZh ? products + "放量与导入" : products + " ramp and adoption") : null,
                        isZh ? "收入增长质量" : "Revenue Growth Quality"))
                .impact(impactLevel(facts.getRevenueYoY()))
                .description(firstNonBlank(
                        products != null && customers != null
                                ? (isZh
                                        ? String.format(Locale.ROOT, "%s营收为%s，%s，结合公司画像看，更值得关注的是%s面向%s的放量和客户导入节奏。",
                                                describePeriod(periodLabel, true),
                                                formatCurrency(facts.getRevenue(), facts.getCurrency()),
                                                describeRevenueGrowthNarrative(facts.getRevenueYoY(), true),
                                                products,
                                                customers)
                                        : String.format(Locale.ROOT,
                                                "%s revenue was %s and %s, but the more specific driver from the company profile is ramp and customer adoption in %s sold into %s.",
                                                describePeriod(periodLabel, false),
                                                formatCurrency(facts.getRevenue(), facts.getCurrency()),
                                                describeRevenueGrowthNarrative(facts.getRevenueYoY(), false),
                                                products,
                                                customers))
                                : null,
                        isZh
                        ? String.format(Locale.ROOT, "%s营收为%s，%s，显示需求整体保持稳定。",
                                describePeriod(periodLabel, true),
                                formatCurrency(facts.getRevenue(), facts.getCurrency()),
                                describeRevenueGrowthNarrative(facts.getRevenueYoY(), true))
                        : String.format(Locale.ROOT,
                                "%s revenue was %s and %s, suggesting demand remained broadly stable.",
                                describePeriod(periodLabel, false),
                                formatCurrency(facts.getRevenue(), facts.getCurrency()),
                                describeRevenueGrowthNarrative(facts.getRevenueYoY(), false))))
                .build());

        BigDecimal profitabilityMargin = preferredProfitabilityMargin(facts);
        BigDecimal profitabilityChange = preferredProfitabilityChange(facts);
        boolean usingGrossMargin = facts.getGrossMargin() != null;
        if (profitabilityMargin != null) {
            drivers.add(AnalysisReport.BusinessDriver.builder()
                    .title(usingGrossMargin
                            ? (isZh ? "盈利能力与定价" : "Profitability and Pricing")
                            : (isZh ? "运营效率与利润兑现" : "Operating Efficiency and Margin Delivery"))
                    .impact(impactLevel(profitabilityChange != null ? profitabilityChange : profitabilityMargin))
                    .description(usingGrossMargin
                            ? (isZh
                                    ? String.format(Locale.ROOT, "毛利率为%s，%s，说明定价能力和成本纪律仍在支撑盈利质量。",
                                            formatPercentOrFallback(profitabilityMargin),
                                            describeMarginDelta(profitabilityChange, true))
                                    : String.format(Locale.ROOT,
                                            "Gross margin was %s, %s, showing that pricing power and cost discipline still support earnings quality.",
                                            formatPercentOrFallback(profitabilityMargin),
                                            describeMarginDelta(profitabilityChange, false)))
                            : (isZh
                                    ? String.format(Locale.ROOT, "营业利润率为%s，%s，说明运营效率和成本纪律仍在支撑利润兑现。",
                                            formatPercentOrFallback(profitabilityMargin),
                                            describeMarginDelta(profitabilityChange, true))
                                    : String.format(Locale.ROOT,
                                            "Operating margin was %s, %s, showing that operating discipline still supports profit delivery.",
                                            formatPercentOrFallback(profitabilityMargin),
                                            describeMarginDelta(profitabilityChange, false))))
                    .build());
        }

        BigDecimal cashMetric = facts.getOperatingCashFlow() != null ? facts.getOperatingCashFlow() : facts.getFreeCashFlow();
        BigDecimal cashDelta = preferredCashDelta(facts);
        boolean usingOperatingCashFlow = facts.getOperatingCashFlow() != null;
        if (cashMetric != null) {
            drivers.add(AnalysisReport.BusinessDriver.builder()
                    .title(firstNonBlank(
                            kpis != null ? (isZh ? "KPI 与现金兑现" : "KPIs and cash conversion") : null,
                            isZh ? "现金生成能力" : "Cash Generation"))
                    .impact(impactLevel(cashDelta))
                    .description(firstNonBlank(
                            kpis != null
                                    ? (isZh
                                            ? String.format(Locale.ROOT, "除现金流外，后续还应结合%s去验证产品导入和商业化是否真的在兑现。", kpis)
                                            : String.format(Locale.ROOT,
                                                    "Beyond cash flow, the next check should be whether company KPIs such as %s keep validating product adoption and commercialization.", kpis))
                                    : null,
                            isZh
                            ? (cashDelta != null
                                    ? String.format(Locale.ROOT, "%s为%s，同比%s，仍为后续投入与资本配置提供缓冲。",
                                            usingOperatingCashFlow ? "经营现金流" : "自由现金流",
                                            formatCurrency(cashMetric, facts.getCurrency()),
                                            formatSignedPercent(cashDelta))
                                    : String.format(Locale.ROOT, "%s为%s，仍为后续投入与资本配置提供缓冲。",
                                            usingOperatingCashFlow ? "经营现金流" : "自由现金流",
                                            formatCurrency(cashMetric, facts.getCurrency())))
                            : (cashDelta != null
                                    ? String.format(Locale.ROOT,
                                            "%s was %s with %s YoY change, leaving room to support future investment and capital allocation.",
                                            usingOperatingCashFlow ? "Operating cash flow" : "Free cash flow",
                                            formatCurrency(cashMetric, facts.getCurrency()),
                                            formatSignedPercent(cashDelta))
                                    : String.format(Locale.ROOT,
                                            "%s was %s, leaving room to support future investment and capital allocation.",
                                            usingOperatingCashFlow ? "Operating cash flow" : "Free cash flow",
                                            formatCurrency(cashMetric, facts.getCurrency())))))
                    .build());
        }

        return drivers;
    }

    private List<AnalysisReport.RiskFactor> buildFallbackRiskFactors(AnalysisContract contract, String periodLabel,
            boolean isZh) {
        if (contract == null) {
            return List.of();
        }

        List<AnalysisReport.RiskFactor> risks = new ArrayList<>();
        risks.addAll(buildSignalBackedRiskFactors(contract.getBusinessSignals(), isZh));

        FinancialFacts facts = contract.getFinancialFacts();
        if (facts != null) {
            risks.addAll(buildQuantitativeFallbackRiskFactors(facts, periodLabel, isZh));
        }

        if (risks.isEmpty()) {
            return List.of();
        }

        LinkedHashMap<String, AnalysisReport.RiskFactor> deduped = new LinkedHashMap<>();
        for (AnalysisReport.RiskFactor risk : risks) {
            if (risk == null) {
                continue;
            }
            String category = trimToNull(risk.getCategory());
            String description = trimToNull(risk.getDescription());
            if (category == null || description == null) {
                continue;
            }
            String key = category.toLowerCase(Locale.ROOT) + "::" + description.toLowerCase(Locale.ROOT);
            deduped.putIfAbsent(key, risk);
            if (deduped.size() >= 4) {
                break;
            }
        }

        return new ArrayList<>(deduped.values());
    }

    private List<AnalysisReport.RiskFactor> buildSignalBackedRiskFactors(BusinessSignals signals, boolean isZh) {
        if (signals == null || signals.getRiskSignals() == null || signals.getRiskSignals().isEmpty()) {
            return List.of();
        }

        List<AnalysisReport.RiskFactor> risks = new ArrayList<>();
        for (BusinessSignals.SignalItem signal : signals.getRiskSignals()) {
            String summary = firstNonBlank(
                    signal == null ? null : signal.getSummary(),
                    signal == null ? null : signal.getEvidenceSnippet());
            if (summary == null) {
                continue;
            }

            String title = trimToNull(signal == null ? null : signal.getTitle());
            risks.add(buildRiskFactor(
                    inferSignalRiskCategory(title, summary, isZh),
                    inferSignalRiskSeverity(title, summary),
                    localizeRiskSignalDescription(summary, isZh)));
            if (risks.size() >= 3) {
                break;
            }
        }
        return risks;
    }

    private List<AnalysisReport.RiskFactor> buildQuantitativeFallbackRiskFactors(FinancialFacts facts, String periodLabel,
            boolean isZh) {
        List<AnalysisReport.RiskFactor> risks = new ArrayList<>();

        if (facts.getRevenueYoY() != null && facts.getRevenueYoY().compareTo(new BigDecimal("-0.02")) <= 0) {
            risks.add(buildRiskFactor(
                    isZh ? "增长放缓" : "Growth Deceleration",
                    facts.getRevenueYoY().compareTo(new BigDecimal("-0.05")) <= 0 ? "high" : "medium",
                    isZh
                            ? String.format(Locale.ROOT, "%s营收同比下滑%s，若后续需求继续走弱，增长弹性可能进一步承压。",
                                    describePeriod(periodLabel, true), formatSignedPercent(facts.getRevenueYoY()))
                            : String.format(Locale.ROOT,
                                    "%s revenue declined %s year over year, so any further demand weakness could pressure growth momentum.",
                                    describePeriod(periodLabel, false), formatSignedPercent(facts.getRevenueYoY()))));
        }

        BigDecimal profitabilityChange = preferredProfitabilityChange(facts);
        boolean usingGrossMargin = facts.getGrossMargin() != null;
        if (profitabilityChange != null && profitabilityChange.compareTo(new BigDecimal("-0.01")) <= 0) {
            risks.add(buildRiskFactor(
                    isZh ? "利润率波动" : "Margin Volatility",
                    profitabilityChange.compareTo(new BigDecimal("-0.03")) <= 0 ? "high" : "medium",
                    usingGrossMargin
                            ? (isZh
                                    ? String.format(Locale.ROOT, "毛利率%s，若产品组合或成本结构继续恶化，盈利质量可能进一步承压。",
                                            describeMarginDelta(profitabilityChange, true))
                                    : String.format(Locale.ROOT,
                                            "Gross margin is %s, so further mix or cost pressure could weigh on earnings quality.",
                                            describeMarginDelta(profitabilityChange, false)))
                            : (isZh
                                    ? String.format(Locale.ROOT, "营业利润率%s，若后续投入加快或费用率反弹，利润兑现可能承压。",
                                            describeMarginDelta(profitabilityChange, true))
                                    : String.format(Locale.ROOT,
                                            "Operating margin is %s, so heavier reinvestment or expense pressure could weigh on profit delivery.",
                                            describeMarginDelta(profitabilityChange, false))))
                    );
        }

        if (facts.getPriceToEarningsRatio() != null
                && facts.getPriceToEarningsRatio().compareTo(new BigDecimal("30")) > 0) {
            risks.add(buildRiskFactor(
                    isZh ? "估值约束" : "Valuation Constraint",
                    "medium",
                    isZh
                            ? String.format(Locale.ROOT, "当前P/E为%s，若市场预期下修，估值回撤可能放大股价波动。",
                                    facts.getPriceToEarningsRatio().setScale(2, RoundingMode.HALF_UP).toPlainString())
                            : String.format(Locale.ROOT,
                                    "Current P/E is %s, so any reset in market expectations could amplify equity volatility.",
                                    facts.getPriceToEarningsRatio().setScale(2, RoundingMode.HALF_UP).toPlainString())));
        }

        return risks;
    }

    private String inferSignalRiskCategory(String title, String summary, boolean isZh) {
        String haystack = String.join(" ",
                trimToNull(title) == null ? "" : trimToNull(title),
                trimToNull(summary) == null ? "" : trimToNull(summary))
                .toLowerCase(Locale.ROOT);

        if (containsAny(haystack, "tariff", "government incentives", "policy", "trade")) {
            return isZh ? "政策与外部环境" : "Policy and External Environment";
        }
        if (containsAny(haystack, "competition", "competitive")) {
            return isZh ? "竞争压力" : "Competitive Pressure";
        }
        if (containsAny(haystack, "regulatory", "compliance", "privacy", "legal", "litigation")) {
            return isZh ? "监管与合规" : "Regulatory and Compliance";
        }
        if (containsAny(haystack, "credit", "loan", "default", "allowance", "reserve")) {
            return isZh ? "信用质量" : "Credit Quality";
        }
        if (containsAny(haystack, "supply chain", "manufacturing", "production", "delivery", "autonomy", "financing")) {
            return isZh ? "运营执行与交付" : "Operational Execution and Delivery";
        }
        if (containsAny(haystack, "service mix", "mix shift", "revenue recognition", "product mix")) {
            return isZh ? "产品结构与收入质量" : "Product Mix and Revenue Quality";
        }
        if (containsAny(haystack, "liquidity", "funding", "deposit", "interest rate", "market", "macro", "volatility")) {
            return isZh ? "流动性与市场敏感性" : "Liquidity and Market Sensitivity";
        }
        if (containsAny(haystack, "cyber", "technology", "outage", "operational", "execution")) {
            return isZh ? "运营与技术执行" : "Operational and Technology Execution";
        }
        if (containsAny(haystack, "demand", "slowdown", "pricing")) {
            return isZh ? "需求与定价" : "Demand and Pricing";
        }

        if (isZh && title != null && !containsChineseCharacters(title)) {
            return "经营风险";
        }
        if (title != null) {
            return title;
        }
        return isZh ? "经营风险" : "Operating Risk";
    }

    private String inferSignalRiskSeverity(String title, String summary) {
        String haystack = String.join(" ",
                trimToNull(title) == null ? "" : trimToNull(title),
                trimToNull(summary) == null ? "" : trimToNull(summary))
                .toLowerCase(Locale.ROOT);

        if (containsAny(haystack,
                "material", "significant", "severe", "substantial", "liquidity", "funding",
                "credit", "default", "cyber", "regulatory", "litigation")) {
            return "high";
        }
        if (containsAny(haystack,
                "competition", "competitive", "macro", "market", "volatility", "demand",
                "pricing", "execution", "operational")) {
            return "medium";
        }
        return "medium";
    }

    private String localizeRiskSignalDescription(String summary, boolean isZh) {
        String normalized = stripTrailingSentenceEnd(summary);
        if (normalized == null) {
            return null;
        }
        String localizedFallback = localizeKnownEnglishRiskSummary(normalized, isZh);
        if (localizedFallback != null) {
            return localizedFallback;
        }
        if (isZh && !containsChineseCharacters(normalized)) {
            return firstNonBlank(
                    summarizeEnglishRiskSnippetToChinese(normalized),
                    "SEC 风险披露提到：" + normalized + "。");
        }
        if (!isZh && !normalized.endsWith(".")) {
            return normalized + ".";
        }
        if (isZh && !normalized.endsWith("。")) {
            return normalized + "。";
        }
        return normalized;
    }

    private String localizeKnownEnglishRiskSummary(String summary, boolean isZh) {
        if (!isZh) {
            return null;
        }

        String normalized = summary.toLowerCase(Locale.ROOT).trim();
        if (normalized.equals(
                "when narrative evidence is sparse, the next question is whether management can keep funding its priorities without letting margins or demand momentum slip")) {
            return "在缺少更充分叙事证据时，后续需要重点验证管理层能否在不拖累利润率或需求动能的前提下持续投入核心优先事项。";
        }
        if (normalized.equals(
                "with limited narrative detail, the main risk is that thinner profit buffers leave less room to absorb weaker pricing, mix, or demand")) {
            return "在缺少更充分叙事证据时，主要风险在于利润缓冲较薄，面对定价、产品结构或需求走弱时的承压空间更小。";
        }
        return null;
    }

    private String summarizeEnglishRiskSnippetToChinese(String summary) {
        String normalized = trimToNull(summary);
        if (normalized == null) {
            return null;
        }

        String lower = normalized.toLowerCase(Locale.ROOT);
        String leadingTopic = extractLeadingRiskTopic(normalized);

        if (containsAny(lower, "revenue recognition", "service mix", "mix shift", "revenue by source")) {
            return firstNonBlank(
                    leadingTopic != null
                            ? "SEC 风险披露提到：" + leadingTopic + "变化可能影响收入结构与利润质量，后续需要继续跟踪产品组合和确认节奏。"
                            : null,
                    "SEC 风险披露提到：收入结构与服务组合变化可能影响利润质量，后续需要继续跟踪产品组合和确认节奏。");
        }
        if (containsAny(lower, "government incentives", "tariff", "economic incentives", "policy", "trade")) {
            return "SEC 风险披露提到：政策激励、关税或外部环境变化，可能影响成交价格、合同执行和需求表现。";
        }
        if (containsAny(lower, "autonomy", "product roadmap", "supply chain", "financing options")) {
            return "SEC 风险披露提到：自动驾驶投入、供应链整合、产品路线图推进和客户融资方案，都会影响后续执行与竞争表现。";
        }
        if (containsAny(lower, "competition", "competitive")) {
            return "SEC 风险披露提到：竞争加剧可能压缩定价能力，并拖累后续需求与盈利兑现。";
        }
        if (containsAny(lower, "demand", "pricing")) {
            return "SEC 风险披露提到：需求波动或定价承压，可能影响收入增长与利润率表现。";
        }
        if (containsAny(lower, "regulatory", "legal", "litigation", "compliance")) {
            return "SEC 风险披露提到：监管、合规或诉讼风险，可能影响经营节奏与资本配置。";
        }
        if (containsAny(lower, "market", "macro", "volatility", "interest rate", "liquidity", "funding")) {
            return "SEC 风险披露提到：宏观环境、市场波动或融资条件变化，可能放大经营与估值波动。";
        }
        if (containsAny(lower, "production", "delivery", "manufacturing", "supply chain")) {
            return "SEC 风险披露提到：生产、交付与供应链执行风险，可能影响收入确认和盈利兑现。";
        }
        return "SEC 风险披露提到：相关风险主要落在经营执行、需求变化或外部环境扰动上，后续需要结合财报继续验证。";
    }

    private String extractLeadingRiskTopic(String summary) {
        String normalized = trimToNull(summary);
        if (normalized == null) {
            return null;
        }
        int colonIndex = normalized.indexOf(':');
        if (colonIndex <= 0 || colonIndex > 60) {
            return null;
        }
        String candidate = trimToNull(normalized.substring(0, colonIndex));
        if (candidate == null || containsNumericContent(candidate)) {
            return null;
        }
        return candidate;
    }

    private boolean containsChineseCharacters(String text) {
        if (text == null) {
            return false;
        }
        for (int i = 0; i < text.length(); i++) {
            Character.UnicodeBlock block = Character.UnicodeBlock.of(text.charAt(i));
            if (block == Character.UnicodeBlock.CJK_UNIFIED_IDEOGRAPHS
                    || block == Character.UnicodeBlock.CJK_UNIFIED_IDEOGRAPHS_EXTENSION_A
                    || block == Character.UnicodeBlock.CJK_UNIFIED_IDEOGRAPHS_EXTENSION_B
                    || block == Character.UnicodeBlock.CJK_COMPATIBILITY_IDEOGRAPHS) {
                return true;
            }
        }
        return false;
    }

    private String buildFallbackBullCase(AnalysisContract contract, FinancialFacts facts, String periodLabel, boolean isZh) {
        CompanyProfile profile = contract == null ? null : contract.getCompanyProfile();
        String products = profile == null ? null : joinTop(profile.getProductLines(), isZh);
        String kpis = profile == null ? null : joinTop(profile.getKeyKpis(), isZh);
        String profitabilityLabelZh = facts.getGrossMargin() != null ? "毛利率" :
                facts.getOperatingMargin() != null ? "营业利润率" : "净利率";
        String profitabilityLabelEn = facts.getGrossMargin() != null ? "gross margin" :
                facts.getOperatingMargin() != null ? "operating margin" : "net margin";
        BigDecimal profitabilityMetric = preferredProfitabilityMargin(facts) != null
                ? preferredProfitabilityMargin(facts)
                : facts.getNetMargin();
        BigDecimal cashMetric = facts.getOperatingCashFlow() != null ? facts.getOperatingCashFlow() : facts.getFreeCashFlow();

        return firstNonBlank(
                profile != null && products != null
                        ? (isZh
                                ? String.format(Locale.ROOT,
                                        "%s若%s继续放量，并且%s等专属 KPI 持续改善，当前营收和利润率表现有机会继续兑现。",
                                        describePeriod(periodLabel, true),
                                        products,
                                        firstNonBlank(kpis, "核心运营指标"))
                                : String.format(Locale.ROOT,
                                        "If %s keeps ramping and company KPIs such as %s continue improving, the current revenue and margin profile can keep validating the bull case.",
                                        products,
                                        firstNonBlank(kpis, "core operating KPIs")))
                        : null,
                isZh
                ? String.format(Locale.ROOT,
                        "%s营收为%s，%s，且%s维持在%s，说明需求韧性和利润兑现仍有支撑%s",
                        describePeriod(periodLabel, true),
                        formatCurrency(facts.getRevenue(), facts.getCurrency()),
                        describeRevenueGrowthNarrative(facts.getRevenueYoY(), true),
                        profitabilityLabelZh,
                        formatPercentOrFallback(profitabilityMetric),
                        cashMetric != null ? "；若后续现金生成继续改善，估值弹性仍有修复空间。" : "。")
                : String.format(Locale.ROOT,
                        "%s revenue was %s and %s, while %s held at %s, so demand resilience and profit delivery still support a constructive case%s",
                        describePeriod(periodLabel, false),
                        formatCurrency(facts.getRevenue(), facts.getCurrency()),
                        describeRevenueGrowthNarrative(facts.getRevenueYoY(), false),
                        profitabilityLabelEn,
                        formatPercentOrFallback(profitabilityMetric),
                        cashMetric != null ? " if cash generation improves from here." : "."));
    }

    private String buildFallbackBearCase(AnalysisContract contract, FinancialFacts facts, String periodLabel, boolean isZh) {
        CompanyProfile profile = contract == null ? null : contract.getCompanyProfile();
        String products = profile == null ? null : joinTop(profile.getProductLines(), isZh);
        BigDecimal cashDelta = preferredCashDelta(facts);
        String revenueRiskClause;
        if (facts.getRevenueYoY() != null && facts.getRevenueYoY().compareTo(new BigDecimal("-0.02")) <= 0) {
            revenueRiskClause = isZh ? "营收继续下滑" : "revenue continues to decline";
        } else if (isApproximatelyFlat(facts.getRevenueYoY())) {
            revenueRiskClause = isZh ? "收入迟迟不能重新加速" : "revenue fails to reaccelerate";
        } else {
            revenueRiskClause = isZh ? "增长动能继续放缓" : "growth momentum keeps slowing";
        }

        BigDecimal profitabilityMetric = preferredProfitabilityMargin(facts) != null
                ? preferredProfitabilityMargin(facts)
                : facts.getNetMargin();
        String profitabilityLabelZh = facts.getGrossMargin() != null ? "毛利率" :
                facts.getOperatingMargin() != null ? "营业利润率" : "净利率";
        String profitabilityLabelEn = facts.getGrossMargin() != null ? "gross margin" :
                facts.getOperatingMargin() != null ? "operating margin" : "net margin";

        return firstNonBlank(
                profile != null && products != null
                        ? (isZh
                                ? String.format(Locale.ROOT,
                                        "若%s的导入、放量或商业化节奏低于预期，当前增长叙事很快会重新回到需求和估值承压的框架。", products)
                                : String.format(Locale.ROOT,
                                        "If adoption, ramp, or commercialization in %s disappoints, the current growth story can quickly revert to a weaker demand and valuation reset narrative.", products))
                        : null,
                isZh
                ? String.format(Locale.ROOT,
                        "%s若%s、%s从当前%s回落%s，市场可能继续担心增长弹性和盈利兑现能力。",
                        describePeriod(periodLabel, true),
                        revenueRiskClause,
                        profitabilityLabelZh,
                        formatPercentOrFallback(profitabilityMetric),
                        cashDelta != null ? String.format(Locale.ROOT, "，且现金流同比继续%s", formatSignedPercent(cashDelta)) : "")
                : String.format(Locale.ROOT,
                        "If %s and %s slips from %s%s, the market may price in a more persistent slowdown and weaker profitability.",
                        describePeriod(periodLabel, false),
                        revenueRiskClause,
                        profitabilityLabelEn,
                        formatPercentOrFallback(profitabilityMetric),
                        cashDelta != null ? String.format(Locale.ROOT, " while cash flow keeps moving %s year over year", formatSignedPercent(cashDelta)) : ""));
    }

    private AnalysisReport.FactorAnalysis.Factor buildFactor(String name, String impact, String description) {
        return AnalysisReport.FactorAnalysis.Factor.builder()
                .name(name)
                .impact(impact)
                .description(description)
                .build();
    }

    private AnalysisReport.RiskFactor buildRiskFactor(String category, String severity, String description) {
        return AnalysisReport.RiskFactor.builder()
                .category(category)
                .severity(severity)
                .description(description)
                .build();
    }

    private AnalysisReport.TopicTrend buildTopicTrend(String topic, int frequency, String sentiment) {
        return AnalysisReport.TopicTrend.builder()
                .topic(topic)
                .frequency(Math.max(1, Math.min(100, frequency)))
                .sentiment(sentiment)
                .build();
    }

    private String impactSign(BigDecimal value) {
        if (value == null) {
            return "flat";
        }
        int sign = value.compareTo(BigDecimal.ZERO);
        if (sign > 0) {
            return "+";
        }
        if (sign < 0) {
            return "-";
        }
        return "flat";
    }

    private String impactLevel(BigDecimal value) {
        if (value == null) {
            return "medium";
        }
        BigDecimal abs = value.abs();
        if (abs.compareTo(new BigDecimal("0.15")) >= 0) {
            return "high";
        }
        if (abs.compareTo(new BigDecimal("0.05")) >= 0) {
            return "medium";
        }
        return "low";
    }

    private BigDecimal preferredCashDelta(FinancialFacts facts) {
        return facts.getOperatingCashFlowYoY() != null ? facts.getOperatingCashFlowYoY() : facts.getFreeCashFlowYoY();
    }

    private int scoreTopicFrequency(BigDecimal value, int strong, int moderate, int weak) {
        if (value == null) {
            return weak;
        }
        BigDecimal abs = value.abs();
        if (abs.compareTo(new BigDecimal("0.15")) >= 0) {
            return strong;
        }
        if (abs.compareTo(new BigDecimal("0.05")) >= 0) {
            return moderate;
        }
        return weak;
    }

    private String sentimentFromDelta(BigDecimal value) {
        if (value == null) {
            return "neutral";
        }
        int sign = value.compareTo(BigDecimal.ZERO);
        if (sign > 0) {
            return "positive";
        }
        if (sign < 0) {
            return "negative";
        }
        return "neutral";
    }

    private String sentimentFromLevel(BigDecimal value, BigDecimal positiveThreshold, BigDecimal neutralThreshold) {
        if (value == null) {
            return "neutral";
        }
        if (value.compareTo(positiveThreshold) >= 0) {
            return "positive";
        }
        if (value.compareTo(neutralThreshold) >= 0) {
            return "neutral";
        }
        return "negative";
    }

    private AnalysisReport.InsightEngine.RootCause buildRootCause(String metric, String reason, String evidence) {
        return AnalysisReport.InsightEngine.RootCause.builder()
                .metric(metric)
                .reason(reason)
                .evidence(evidence)
                .build();
    }

    private BigDecimal safeDivide(BigDecimal numerator, BigDecimal denominator) {
        if (numerator == null || denominator == null || denominator.compareTo(BigDecimal.ZERO) == 0) {
            return null;
        }
        return numerator.divide(denominator, 4, RoundingMode.HALF_UP);
    }

    private String formatRatio(BigDecimal value) {
        if (value == null) {
            return "N/A";
        }
        return value.setScale(2, RoundingMode.HALF_UP).toPlainString() + "x";
    }

    private String formatPercentOrFallback(BigDecimal value) {
        return value == null ? "N/A" : formatPercent(value);
    }

    private String formatSignedPercent(BigDecimal value) {
        if (value == null) {
            return "N/A";
        }
        BigDecimal scaled = value.multiply(new BigDecimal("100")).setScale(2, RoundingMode.HALF_UP);
        return (scaled.compareTo(BigDecimal.ZERO) > 0 ? "+" : "") + scaled.toPlainString() + "%";
    }

    private String formatPercentAbs(BigDecimal value) {
        if (value == null) {
            return "N/A";
        }
        return value.abs().multiply(new BigDecimal("100")).setScale(2, RoundingMode.HALF_UP).toPlainString() + "%";
    }

    private String describeMarginDelta(BigDecimal delta, boolean isZh) {
        if (delta == null) {
            return isZh ? "较上期基本稳定" : "roughly stable versus the comparison period";
        }
        if (delta.compareTo(BigDecimal.ZERO) > 0) {
            return isZh ? "较上期改善" : "improving versus the comparison period";
        }
        if (delta.compareTo(BigDecimal.ZERO) < 0) {
            return isZh ? "较上期承压" : "under pressure versus the comparison period";
        }
        return isZh ? "较上期持平" : "flat versus the comparison period";
    }

    private BigDecimal preferredProfitabilityMargin(FinancialFacts facts) {
        if (facts.getGrossMargin() != null) {
            return facts.getGrossMargin();
        }
        return facts.getOperatingMargin();
    }

    private BigDecimal preferredProfitabilityChange(FinancialFacts facts) {
        if (facts.getGrossMargin() != null) {
            return facts.getGrossMarginChange();
        }
        return facts.getOperatingMarginChange();
    }

    private boolean isApproximatelyFlat(BigDecimal value) {
        return value != null && value.abs().compareTo(new BigDecimal("0.01")) < 0;
    }

    private String describeRevenueGrowthNarrative(BigDecimal revenueYoY, boolean isZh) {
        if (revenueYoY == null) {
            return isZh ? "同比表现暂未披露" : "year-over-year growth was not disclosed";
        }
        if (isApproximatelyFlat(revenueYoY)) {
            return isZh ? "同比基本持平" : "roughly flat year over year";
        }
        return isZh ? String.format(Locale.ROOT, "同比%s", formatSignedPercent(revenueYoY))
                : String.format(Locale.ROOT, "%s year over year", formatSignedPercent(revenueYoY));
    }

    private String describePeriod(String periodLabel, boolean isZh) {
        String resolved = trimToNull(periodLabel);
        if (resolved == null) {
            return isZh ? "本期" : "the reported period";
        }
        FiscalQuarterLabel fiscalQuarter = parseFiscalQuarterLabel(resolved);
        if (fiscalQuarter == null) {
            return resolved;
        }
        return isZh ? fiscalQuarter.zhCompact() : fiscalQuarter.enCanonical();
    }

    private void normalizeFiscalPeriodReferences(AnalysisReport report, AnalysisContract contract, String lang) {
        if (report == null || contract == null) {
            return;
        }

        FinancialFacts facts = contract.getFinancialFacts();
        String resolvedPeriod = trimToNull(facts != null ? facts.getPeriod() : report.getPeriod());
        FiscalQuarterLabel fiscalQuarter = parseFiscalQuarterLabel(resolvedPeriod);
        if (fiscalQuarter == null) {
            return;
        }

        boolean isZh = "zh".equalsIgnoreCase(lang);
        report.setPeriod(fiscalQuarter.enCanonical());
        report.setExecutiveSummary(rewriteFiscalPeriodReferences(report.getExecutiveSummary(), fiscalQuarter, isZh));

        AnalysisReport.CoreThesis thesis = report.getCoreThesis();
        if (thesis == null) {
            return;
        }

        thesis.setHeadline(rewriteFiscalPeriodReferences(thesis.getHeadline(), fiscalQuarter, isZh));
        thesis.setSummary(rewriteFiscalPeriodReferences(thesis.getSummary(), fiscalQuarter, isZh));
        thesis.setWhatChanged(rewriteFiscalPeriodList(thesis.getWhatChanged(), fiscalQuarter, isZh));
        thesis.setWatchItems(rewriteFiscalPeriodList(thesis.getWatchItems(), fiscalQuarter, isZh));
        thesis.setDrivers(rewriteFiscalPeriodEvidence(thesis.getDrivers(), fiscalQuarter, isZh));
        thesis.setStrategicBets(rewriteFiscalPeriodEvidence(thesis.getStrategicBets(), fiscalQuarter, isZh));
        thesis.setSupportingEvidence(rewriteFiscalPeriodEvidence(thesis.getSupportingEvidence(), fiscalQuarter, isZh));
    }

    private List<String> rewriteFiscalPeriodList(List<String> values, FiscalQuarterLabel fiscalQuarter, boolean isZh) {
        if (values == null) {
            return null;
        }
        return values.stream()
                .map(value -> rewriteFiscalPeriodReferences(value, fiscalQuarter, isZh))
                .toList();
    }

    private List<AnalysisReport.SupportingEvidence> rewriteFiscalPeriodEvidence(
            List<AnalysisReport.SupportingEvidence> values,
            FiscalQuarterLabel fiscalQuarter,
            boolean isZh) {
        if (values == null) {
            return null;
        }
        return values.stream()
                .map(value -> value == null ? null : AnalysisReport.SupportingEvidence.builder()
                        .label(rewriteFiscalPeriodReferences(value.getLabel(), fiscalQuarter, isZh))
                        .detail(rewriteFiscalPeriodReferences(value.getDetail(), fiscalQuarter, isZh))
                        .build())
                .filter(Objects::nonNull)
                .toList();
    }

    private String rewriteFiscalPeriodReferences(String text, FiscalQuarterLabel fiscalQuarter, boolean isZh) {
        String normalized = trimToNull(text);
        if (normalized == null) {
            return null;
        }

        String rewritten = normalized;
        String quarter = fiscalQuarter.quarter();
        String year = fiscalQuarter.fiscalYear();
        String replacement = isZh ? fiscalQuarter.zhCompact() : fiscalQuarter.enCanonical();

        rewritten = rewritten.replaceAll("(?i)\\bQ\\s*" + quarter + "\\s*FY\\s*" + year + "\\b",
                Matcher.quoteReplacement(replacement));
        rewritten = rewritten.replaceAll("(?i)\\bQ\\s*" + quarter + "\\s+" + year + "\\b",
                Matcher.quoteReplacement(replacement));
        rewritten = rewritten.replaceAll("(?i)\\b" + year + "\\s*Q\\s*" + quarter + "\\b",
                Matcher.quoteReplacement(replacement));
        rewritten = rewritten.replace("FY" + year + " Q" + quarter, replacement);
        rewritten = rewritten.replace(year + "年Q" + quarter, replacement);

        String chineseQuarter = toChineseQuarter(quarter);
        if (chineseQuarter != null) {
            rewritten = rewritten.replace(year + "年" + chineseQuarter + "季度",
                    isZh ? fiscalQuarter.zhLong() : fiscalQuarter.enCanonical());
            rewritten = rewritten.replace(year + "年" + chineseQuarter + "财季",
                    isZh ? fiscalQuarter.zhLong() : fiscalQuarter.enCanonical());
        }
        rewritten = rewritten.replace(year + "财年Q" + quarter, replacement);

        return rewritten;
    }

    private FiscalQuarterLabel parseFiscalQuarterLabel(String periodLabel) {
        String normalized = trimToNull(periodLabel);
        if (normalized == null) {
            return null;
        }

        Matcher matcher = FISCAL_QUARTER_PATTERN.matcher(normalized);
        if (!matcher.matches()) {
            return null;
        }
        return new FiscalQuarterLabel(matcher.group(1), matcher.group(2));
    }

    private String toChineseQuarter(String quarter) {
        return switch (quarter) {
            case "1" -> "第一";
            case "2" -> "第二";
            case "3" -> "第三";
            case "4" -> "第四";
            default -> null;
        };
    }

    private record FiscalQuarterLabel(String fiscalYear, String quarter) {
        private String enCanonical() {
            return "FY" + fiscalYear + " Q" + quarter;
        }

        private String zhCompact() {
            return fiscalYear + "财年Q" + quarter;
        }

        private String zhLong() {
            return fiscalYear + "财年第" + switch (quarter) {
                case "1" -> "一";
                case "2" -> "二";
                case "3" -> "三";
                case "4" -> "四";
                default -> quarter;
            } + "季度";
        }
    }

    private List<String> cleanStringList(List<String> items) {
        if (items == null) {
            return null;
        }
        LinkedHashMap<String, String> deduped = new LinkedHashMap<>();
        for (String item : items) {
            String normalized = trimToNull(item);
            if (normalized == null) {
                continue;
            }
            String key = normalizeNarrativeBullet(normalized);
            if (key == null || deduped.containsKey(key)) {
                continue;
            }
            deduped.put(key, normalized);
        }
        return new ArrayList<>(deduped.values());
    }

    private List<AnalysisReport.SupportingEvidence> cleanSupportingEvidence(
            List<AnalysisReport.SupportingEvidence> items) {
        if (items == null) {
            return null;
        }
        LinkedHashMap<String, AnalysisReport.SupportingEvidence> deduped = new LinkedHashMap<>();
        for (AnalysisReport.SupportingEvidence item : items) {
            if (item == null) {
                continue;
            }
            String label = trimToNull(item.getLabel());
            String detail = trimToNull(item.getDetail());
            if (label == null && detail == null) {
                continue;
            }
            AnalysisReport.SupportingEvidence normalizedItem = AnalysisReport.SupportingEvidence.builder()
                    .label(label != null ? label : "Evidence")
                    .detail(detail != null ? detail : "")
                    .build();
            String key = normalizeNarrativeBullet(
                    firstNonBlank(normalizedItem.getLabel(), "") + " " + firstNonBlank(normalizedItem.getDetail(), ""));
            if (key == null || deduped.containsKey(key)) {
                continue;
            }
            deduped.put(key, normalizedItem);
        }
        return new ArrayList<>(deduped.values());
    }

    private String normalizeNarrativeBullet(String text) {
        String normalized = trimToNull(text);
        if (normalized == null) {
            return null;
        }
        normalized = normalized
                .replace('“', '"')
                .replace('”', '"')
                .replace('’', '\'')
                .replace('‘', '\'')
                .replaceAll("\"[^\"]+\"", "\"quoted\"")
                .replaceAll("\\s+", " ")
                .replaceAll("[，,。.!?；;：:]+", "")
                .toLowerCase(Locale.ROOT)
                .trim();
        return normalized.isBlank() ? null : normalized;
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
    protected void enrichMetadata(AnalysisReport report, String lang) {
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

    private record ThemeDescriptor(String key, String en, String zh) {
    }
}
