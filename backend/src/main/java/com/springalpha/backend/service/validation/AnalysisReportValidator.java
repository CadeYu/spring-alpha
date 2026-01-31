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
 * Validates that AnalysisReport does not contain hallucinated data.
 * Ensures all numerical values can be traced back to FinancialFacts.
 */
@Slf4j
@Service
public class AnalysisReportValidator {

    // Pattern to extract numbers from text (including percentages and currency)
    private static final Pattern NUMBER_PATTERN = Pattern.compile("-?\\d+\\.?\\d*[%]?");

    /**
     * Validate an analysis report against its source facts
     */
    public ValidationResult validate(AnalysisReport report, FinancialFacts facts) {
        List<String> errors = new ArrayList<>();
        List<String> warnings = new ArrayList<>();

        // Validate required fields
        if (report.getExecutiveSummary() == null || report.getExecutiveSummary().isBlank()) {
            errors.add("executiveSummary is required");
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
