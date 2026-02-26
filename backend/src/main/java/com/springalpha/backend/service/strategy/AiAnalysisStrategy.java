package com.springalpha.backend.service.strategy;

import com.springalpha.backend.financial.contract.AnalysisContract;
import com.springalpha.backend.financial.contract.AnalysisReport;
import reactor.core.publisher.Flux;

/**
 * AI 分析策略接口 (Strategy Pattern Interface)
 * <p>
 * 定义了所有 AI 模型实现的统一契约。
 * 
 * **关键设计原则**:
 * 1. **Interpret Only**: LLM 只能解释事实，严禁"创造"新的数字 (避免幻觉)。
 * 2. **Fact Injection**: 所有财务指标必须来自 `AnalysisContract` 里的 `financialFacts`。
 * 3. **Structured Output**: 输出必须符合 `AnalysisReport` 的 JSON 结构。
 * 4. **Consistency**: 不同模型 (Groq, OpenAI, Gemini) 写作风格可能不同，但结论逻辑应一致。
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
