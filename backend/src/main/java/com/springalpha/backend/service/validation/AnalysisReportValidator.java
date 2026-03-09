package com.springalpha.backend.service.validation;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.model.FinancialFacts;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * 幻觉校验器 (Hallucination Validator)
 * <p>
 * **核心职能**: 防止 LLM "一本正经地胡说八道"。
 * **工作原理**:
 * 1. 从 LLM 生成的文本报告中提取所有数字。
 * 2. 尝试在 "Ground Truth" (FinancialFacts) 中找到这些数字 (允许 1% 误差)。
 * 3. 如果通过 ETL 获取的财报里没有这个数字，则标记为 "Possible Hallucination" (潜在幻觉)。
 * <p>
 * 这是金融 AI 应用中 **最重要** 的安全网。
 */
@Slf4j
@Service
public class AnalysisReportValidator {

    // Pattern to extract numbers from text (including percentages and currency)
    private static final Pattern NUMBER_PATTERN = Pattern.compile("-?\\d+\\.?\\d*[%]?");
    private static final List<String> PLACEHOLDER_CITATION_PATTERNS = List.of(
            "no textual evidence available",
            "source identifier",
            "exact quoted text from source",
            "quote from text",
            "not available",
            "n/a");

    /**
     * Validate an analysis report against its source facts
     */
    public ValidationResult validate(AnalysisReport report, FinancialFacts facts) {
        List<String> errors = new ArrayList<>();
        List<String> warnings = new ArrayList<>();

        // Validate required fields
        boolean hasLegacySummary = report.getExecutiveSummary() != null && !report.getExecutiveSummary().isBlank();
        boolean hasCoreThesis = report.getCoreThesis() != null
                && ((report.getCoreThesis().getSummary() != null && !report.getCoreThesis().getSummary().isBlank())
                        || (report.getCoreThesis().getHeadline() != null
                                && !report.getCoreThesis().getHeadline().isBlank()));
        if (!hasLegacySummary && !hasCoreThesis) {
            errors.add("coreThesis or executiveSummary is required");
        }

        if (report.getKeyMetrics() == null || report.getKeyMetrics().isEmpty()) {
            errors.add("keyMetrics cannot be empty");
        }

        // Validate key metrics values
        if (report.getKeyMetrics() != null) {
            for (AnalysisReport.MetricInsight metric : report.getKeyMetrics()) {
                validateMetricValue(metric, facts, warnings);
            }
        }

        // Validate sentiment values
        if (report.getKeyMetrics() != null) {
            for (AnalysisReport.MetricInsight metric : report.getKeyMetrics()) {
                if (!isValidSentiment(metric.getSentiment())) {
                    errors.add(
                            "Invalid sentiment for metric '" + metric.getMetricName() + "': " + metric.getSentiment());
                }
            }
        }

        // Log results
        if (!errors.isEmpty()) {
            log.warn("Validation errors: {}", errors);
        }
        if (!warnings.isEmpty()) {
            log.info("Validation warnings: {}", warnings);
        }

        return new ValidationResult(errors.isEmpty(), errors, warnings);
    }

    /**
     * Validate that a metric value appears to come from financial facts
     */
    private void validateMetricValue(AnalysisReport.MetricInsight metric, FinancialFacts facts, List<String> warnings) {
        String value = metric.getValue();
        if (value == null || value.isBlank()) {
            warnings.add("Metric '" + metric.getMetricName() + "' has no value");
            return;
        }

        // Extract numbers from the value string
        List<BigDecimal> numbers = extractNumbers(value);

        if (numbers.isEmpty()) {
            // No numbers to validate (might be qualitative description)
            return;
        }

        // Check if any of the numbers appear in the financial facts
        boolean foundInFacts = false;
        for (BigDecimal number : numbers) {
            if (isNumberInFacts(number, facts)) {
                foundInFacts = true;
                break;
            }
        }

        if (!foundInFacts) {
            warnings.add("Metric '" + metric.getMetricName() + "' value '" + value +
                    "' could not be traced to financial facts (possible hallucination)");
        }
    }

    /**
     * Check if a sentiment value is valid
     */
    private boolean isValidSentiment(String sentiment) {
        if (sentiment == null)
            return false;
        String lower = sentiment.toLowerCase();
        return lower.equals("positive") || lower.equals("negative") || lower.equals("neutral");
    }

    /**
     * Extract all numbers from a string
     */
    private List<BigDecimal> extractNumbers(String text) {
        List<BigDecimal> numbers = new ArrayList<>();
        Matcher matcher = NUMBER_PATTERN.matcher(text.replace(",", "").replace("%", ""));

        while (matcher.find()) {
            try {
                numbers.add(new BigDecimal(matcher.group()));
            } catch (NumberFormatException e) {
                // Ignore invalid numbers
            }
        }

        return numbers;
    }

    /**
     * Check if a number appears in the financial facts (with tolerance for
     * rounding)
     */
    private boolean isNumberInFacts(BigDecimal number, FinancialFacts facts) {
        // Convert facts to JSON and search for the number
        // This is a simplified check - in production, you'd want more sophisticated
        // matching

        // Check common metrics with tolerance
        double tolerance = 0.01; // 1% tolerance for rounding

        if (isApproximatelyEqual(number, facts.getRevenue(), tolerance))
            return true;
        if (isApproximatelyEqual(number, facts.getNetIncome(), tolerance))
            return true;
        if (isApproximatelyEqual(number, facts.getRevenueYoY(), tolerance))
            return true;
        if (isApproximatelyEqual(number, facts.getRevenueQoQ(), tolerance))
            return true;
        if (isApproximatelyEqual(number, facts.getGrossMargin(), tolerance))
            return true;
        if (isApproximatelyEqual(number, facts.getOperatingMargin(), tolerance))
            return true;
        if (isApproximatelyEqual(number, facts.getNetMargin(), tolerance))
            return true;
        if (isApproximatelyEqual(number, facts.getFreeCashFlow(), tolerance))
            return true;
        if (isApproximatelyEqual(number, facts.getReturnOnEquity(), tolerance))
            return true;
        if (isApproximatelyEqual(number, facts.getReturnOnAssets(), tolerance))
            return true;

        // Check additional metrics map
        if (facts.getAdditionalMetrics() != null) {
            for (BigDecimal value : facts.getAdditionalMetrics().values()) {
                if (isApproximatelyEqual(number, value, tolerance))
                    return true;
            }
        }

        return false;
    }

    /**
     * Check if two BigDecimals are approximately equal within tolerance
     */
    private boolean isApproximatelyEqual(BigDecimal a, BigDecimal b, double tolerance) {
        if (a == null || b == null)
            return false;

        double diff = Math.abs(a.doubleValue() - b.doubleValue());
        double avg = (Math.abs(a.doubleValue()) + Math.abs(b.doubleValue())) / 2.0;

        if (avg == 0)
            return diff < tolerance;

        return (diff / avg) < tolerance;
    }

    /**
     * Validate citations against the source text and deduplicate them
     */
    public void validateCitations(AnalysisReport report, String sourceText) {
        if (report.getCitations() == null) {
            return;
        }

        String normalizedSource = normalizeText(sourceText);
        List<AnalysisReport.Citation> uniqueCitations = new ArrayList<>();
        java.util.Set<String> seenNormalizedExcerpts = new java.util.HashSet<>();

        for (AnalysisReport.Citation citation : report.getCitations()) {
            if (isPlaceholderCitation(citation)) {
                log.warn("🚩 Dropping placeholder citation: section='{}', excerpt='{}'",
                        citation.getSection(), citation.getExcerpt());
                continue;
            }

            if (citation.getExcerpt() == null || citation.getExcerpt().isBlank()) {
                continue;
            }

            String normalizedExcerpt = normalizeText(citation.getExcerpt());

            // Deduplicate: If we already have this exact excerpt, skip it
            if (seenNormalizedExcerpts.contains(normalizedExcerpt)) {
                log.debug("Found duplicate citation, skipping: {}", citation.getExcerpt());
                continue;
            }
            seenNormalizedExcerpts.add(normalizedExcerpt);
            uniqueCitations.add(citation);

            // 1. Direct contains check (fastest)
            if (!normalizedSource.isBlank() && normalizedSource.contains(normalizedExcerpt)) {
                citation.setVerificationStatus("VERIFIED");
            } else {
                // 2. Fallback: Fuzzy match
                citation.setVerificationStatus(normalizedSource.isBlank() ? "UNVERIFIED" : "NOT_FOUND");
                if (!normalizedSource.isBlank()) {
                    log.warn("🚩 Citation not found in source text: '{}'", citation.getExcerpt());
                }
            }
        }

        // Replace with unique list
        report.setCitations(uniqueCitations);
    }

    private boolean isPlaceholderCitation(AnalysisReport.Citation citation) {
        String excerpt = normalizeText(citation.getExcerpt());
        String section = normalizeText(citation.getSection());

        if (excerpt.isBlank() && section.isBlank()) {
            return true;
        }

        for (String pattern : PLACEHOLDER_CITATION_PATTERNS) {
            if (excerpt.contains(pattern) || section.contains(pattern)) {
                return true;
            }
        }

        return false;
    }

    /**
     * Normalize text for comparison:
     * - Lowercase
     * - Remove punctuation
     * - Collapse whitespace
     */
    private String normalizeText(String text) {
        if (text == null)
            return "";
        return text.toLowerCase()
                .replaceAll("[^a-z0-9\\s]", " ") // Replace punctuation with space
                .replaceAll("\\s+", " ") // Collapse multiple spaces
                .trim();
    }

    /**
     * Result of validation
     */
    @Data
    public static class ValidationResult {
        private final boolean valid;
        private final List<String> errors;
        private final List<String> warnings;

        public static ValidationResult ok() {
            return new ValidationResult(true, List.of(), List.of());
        }

        public static ValidationResult failed(List<String> errors) {
            return new ValidationResult(false, errors, List.of());
        }
    }
}
