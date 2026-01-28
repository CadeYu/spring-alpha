package com.springalpha.backend.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.service.FinancialAnalysisService;
import com.springalpha.backend.service.SecService;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

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

    // AI Analysis endpoint (SSE streaming output)
    // Returns structured JSON instead of raw text
    @GetMapping(value = "/analyze/{ticker}", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> analyze(
            @PathVariable String ticker,
            @RequestParam(defaultValue = "en") String lang) {
        return analysisService.analyzeStock(ticker, lang)
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
}
