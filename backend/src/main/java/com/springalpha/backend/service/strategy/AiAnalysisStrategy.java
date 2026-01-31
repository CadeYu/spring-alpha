package com.springalpha.backend.service.strategy;

import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import reactor.core.publisher.Flux;

/**
 * AI Analysis Strategy Interface - Defines the contract for all AI
 * implementations.
 * 
 * Key Design Principles:
 * 1. LLMs only INTERPRET facts, never CREATE new numerical data
 * 2. All financial metrics must come from AnalysisContract.financialFacts
 * 3. Output must conform to the AnalysisReport structure
 * 4. Different models may have different writing styles, but conclusions should
 * be consistent
 */
public interface AiAnalysisStrategy {

    /**
     * Get strategy name (e.g., "openai", "gemini", "mock")
     */
    String getName();

    /**
     * Analyze financial data and generate structured report.
     * 
     * @param contract AnalysisContract containing all input data and tasks
     * @param lang     Language for analysis ("en" or "zh")
     * @return Flux<AnalysisReport> streaming the analysis report
     *         Can emit partial reports for progressive rendering
     */
    Flux<AnalysisReport> analyze(AnalysisContract contract, String lang);
}
