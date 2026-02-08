package com.springalpha.backend.controller;

import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.service.FinancialDataService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.HashMap;
import java.util.Map;

/**
 * Financial Data Test Controller - For validating the financial calculation
 * engine.
 * This endpoint will be used to verify that FinancialFacts are computed
 * correctly.
 */
@RestController
@RequestMapping("/api/financial")
public class FinancialDataController {

    private final FinancialDataService financialDataService;

    public FinancialDataController(FinancialDataService financialDataService) {
        this.financialDataService = financialDataService;
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
