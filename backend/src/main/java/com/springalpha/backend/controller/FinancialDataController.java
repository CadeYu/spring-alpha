package com.springalpha.backend.controller;

import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import com.springalpha.backend.financial.service.FinancialDataService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Financial Data Test Controller - For validating the financial calculation
 * engine.
 * This endpoint will be used to verify that FinancialFacts are computed
 * correctly.
 */
/**
 * 财务数据控制器 (Financial Data Controller)
 * <p>
 * 负责为前端图表组件提供历史数据。
 * 主要服务于:
 * 1. Revenue Trend Chart (营收趋势图)
 * 2. Margin Analysis Chart (利润率分析图)
 */
@RestController
@RequestMapping("/api/financial")
@CrossOrigin(origins = "*")
public class FinancialDataController {

    private final FinancialDataService financialDataService;

    public FinancialDataController(FinancialDataService financialDataService) {
        this.financialDataService = financialDataService;
    }

    /**
     * 获取历史财务数据 (for Charts)
     * <p>
     * 返回过去 5 年的 Revenue, Net Income, Margins 等数据。
     * 前端拿到 JSON 后，使用 Recharts 库绘制折线图和柱状图。
     */
    @GetMapping("/history/{ticker}")
    public Mono<List<HistoricalDataPoint>> getHistoricalData(@PathVariable String ticker) {
        return Mono.fromCallable(() -> financialDataService.getHistoricalData(ticker))
                .subscribeOn(Schedulers.boundedElastic()); // 数据库/API IO 操作，放入弹性线程池
    }

    /**
     * Get financial facts for a given ticker.
     * Test endpoint: GET /api/financial/{ticker}
     */
    @GetMapping("/{ticker}")
    public ResponseEntity<?> getFinancialFacts(@PathVariable String ticker) {
        FinancialFacts facts = financialDataService.getFinancialFacts(ticker);

        if (facts == null) {
            Map<String, Object> error = new HashMap<>();
            error.put("error", "Ticker not supported");
            error.put("ticker", ticker);
            error.put("supportedTickers", financialDataService.getSupportedTickers());
            return ResponseEntity.notFound().build();
        }

        return ResponseEntity.ok(facts);
    }

    /**
     * Get list of supported tickers.
     * Test endpoint: GET /api/financial/supported
     */
    @GetMapping("/supported")
    public ResponseEntity<Map<String, Object>> getSupportedTickers() {
        Map<String, Object> response = new HashMap<>();
        response.put("supportedTickers", financialDataService.getSupportedTickers());
        response.put("count", financialDataService.getSupportedTickers().length);
        return ResponseEntity.ok(response);
    }
}
