package com.springalpha.backend.financial.contract;

import com.springalpha.backend.financial.model.FinancialFacts;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * Analysis Contract - The standardized input format for all AI strategies.
 * This contract ensures that LLMs only interpret facts, never create new data.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AnalysisContract {

    /**
     * Stock ticker symbol
     */
    private String ticker;

    /**
     * Company name
     */
    private String companyName;

    /**
     * Reporting period (e.g., "Q3 2024", "FY 2023")
     */
    private String period;

    /**
     * Computed financial facts - the ONLY source of numerical data.
     * LLMs must not introduce any numbers not present in this object.
     */
    private FinancialFacts financialFacts;

    /**
     * Text evidence extracted from SEC filings.
     * Key: section name (e.g., "MD&A", "Risk Factors", "Business")
     * Value: extracted text content
     */
    private Map<String, String> textEvidence;

    /**
     * List of specific analysis tasks for the LLM to perform.
     * Examples:
     * - "Explain the primary drivers of revenue growth"
     * - "Analyze the sustainability of margin expansion"
     * - "Summarize the most material risk factors"
     */
    private List<String> analysisTasks;

    /**
     * User's preferred language for analysis output
     */
    private String language;
}
