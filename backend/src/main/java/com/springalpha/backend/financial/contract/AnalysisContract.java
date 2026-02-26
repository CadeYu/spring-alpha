package com.springalpha.backend.financial.contract;

import com.springalpha.backend.financial.model.FinancialFacts;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.List;
import java.util.Map;

/**
 * 分析契约 (Analysis Contract)
 * <p>
 * 这是一个 DTO (Data Transfer Object)，封装了 **所有** AI 分析所需的上下文。
 * <p>
 * **包含内容**:
 * 1. `financialFacts`: 真实的财务数字 (防止幻觉)。
 * 2. `textEvidence`: RAG 检索到的文本片段 (提供定性分析依据)。
 * 3. `analysisTasks`: 本次分析的具体任务 (e.g. "分析毛利率趋势")。
 * <p>
 * 它可以被序列化为 JSON，方便调试或存入数据库。
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
