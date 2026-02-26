package com.springalpha.backend.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import com.springalpha.backend.service.FinancialAnalysisService;
import com.springalpha.backend.service.SecService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;

/**
 * SEC 财报控制器 (Controller)
 * <p>
 * 提供与 SEC 财报相关的 API 接口。
 * 主要功能:
 * 1. 触发 AI 分析任务 (`/analyze/{ticker}`)
 * 2. 获取原始 10-K 文本 (`/10k/{ticker}`) - 用于调试 RAG 内容
 */
@RestController
@RequestMapping("/api/sec")
@CrossOrigin(origins = "*")
public class SecController {

    private static final Logger log = LoggerFactory.getLogger(SecController.class);

    private final SecService secService;
    private final FinancialAnalysisService analysisService;

    public SecController(SecService secService, FinancialAnalysisService analysisService) {
        this.secService = secService;
        this.analysisService = analysisService;
    }

    /**
     * 触发股票分析 (AI Analysis Endpoint)
     * <p>
     * 使用 Server-Sent Events (SSE) 流式返回分析结果。
     * 这样前端可以像打印机一样实时显示 AI 生成的内容，避免用户长时间等待。
     *
     * @param ticker 股票代码 (e.g., AAPL)
     * @param lang   语言 (en/zh)
     * @param model  指定模型 (可选)
     */
    @GetMapping(value = "/analyze/{ticker}", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<AnalysisReport> analyzeStock(
            @PathVariable String ticker,
            @RequestParam(defaultValue = "en") String lang,
            @RequestParam(defaultValue = "") String model) {
        log.info("REST request to analyze stock: {}, lang: {}, model: {}", ticker, lang, model);
        return analysisService.analyzeStock(ticker, lang, model);
    }

    /**
     * 获取清洗后的 10-K 文本 (Debug Endpoint)
     * <p>
     * 用于验证 ETL 效果，检查 Markdown 表格是否正确转换。
     */
    @GetMapping("/10k/{ticker}")
    public Mono<String> get10kContent(@PathVariable String ticker) {
        log.info("REST request to get 10-K content for: {}", ticker);
        return secService.getLatest10KContent(ticker)
                .map(content -> {
                    // 只返回前 10000 字符用于预览，防止浏览器卡死
                    if (content.length() > 10000) {
                        return content.substring(0, 10000) + "\n\n... (truncated)";
                    }
                    return content;
                });
    }

    /**
     * 获取可用的 AI 模型列表
     * <p>
     * 返回当前系统支持的所有模型 (e.g. "groq", "openai", "gemini", "enhanced-mock")
     * 以及默认模型。
     */
    @GetMapping("/models")
    public Map<String, Object> getAvailableModels() {
        List<String> models = analysisService.getAvailableModels();
        String defaultModel = analysisService.getDefaultModel();
        return Map.of(
                "models", models,
                "default", defaultModel,
                "count", models.size());
    }

    // Historical Data endpoint for charts
    @GetMapping("/history/{ticker}")
    public Flux<HistoricalDataPoint> getHistory(@PathVariable String ticker) {
        return Mono.fromCallable(() -> secService.getFinancialDataService().getHistoricalData(ticker))
                .subscribeOn(reactor.core.scheduler.Schedulers.boundedElastic())
                .flatMapMany(Flux::fromIterable);
    }
}
