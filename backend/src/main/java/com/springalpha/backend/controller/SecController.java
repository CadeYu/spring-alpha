package com.springalpha.backend.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.service.FinancialAnalysisService;
import com.springalpha.backend.service.SecService;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api/sec")
@CrossOrigin(origins = "*")
public class SecController {

    private final SecService secService;
    private final FinancialAnalysisService analysisService;
    private final ObjectMapper objectMapper = new ObjectMapper();

    public SecController(SecService secService, FinancialAnalysisService analysisService) {
        this.secService = secService;
        this.analysisService = analysisService;
    }

    // Debug endpoint: return cleaned 10-K text
    @GetMapping("/10k/{ticker}")
    public Mono<String> get10K(@PathVariable String ticker) {
        return secService.getLatest10KContent(ticker);
    }

    /**
     * AI Analysis endpoint (SSE streaming output)
     * Returns structured JSON instead of raw text
     * 
     * @param ticker Stock ticker (e.g., AAPL, MSFT)
     * @param lang   Language for analysis ("en" or "zh")
     * @param model  LLM model to use (e.g., "groq", "openai", "enhanced-mock")
     */
    @GetMapping(value = "/analyze/{ticker}", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> analyze(
            @PathVariable String ticker,
            @RequestParam(defaultValue = "en") String lang,
            @RequestParam(defaultValue = "") String model) {
        return analysisService.analyzeStock(ticker, lang, model)
                .flatMap(report -> {
                    try {
                        // Serialize AnalysisReport to JSON
                        String json = objectMapper.writeValueAsString(report);
                        return Flux.just(json);
                    } catch (Exception e) {
                        return Flux.error(new RuntimeException("Failed to serialize report", e));
                    }
                });
    }

    /**
     * Get available AI models for analysis
     * 
     * @return List of available model names
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
    public Flux<com.springalpha.backend.financial.model.HistoricalDataPoint> getHistory(@PathVariable String ticker) {
        return Flux.fromIterable(secService.getFinancialDataService().getHistoricalData(ticker));
    }
}
