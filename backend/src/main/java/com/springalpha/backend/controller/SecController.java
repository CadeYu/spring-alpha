package com.springalpha.backend.controller;

import com.springalpha.backend.service.FinancialAnalysisService;
import com.springalpha.backend.service.SecService;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/sec")
@CrossOrigin(origins = "*") // 允许所有跨域请求，解决前端 Fetch Error
public class SecController {

    private final SecService secService;
    private final FinancialAnalysisService analysisService;

    public SecController(SecService secService, FinancialAnalysisService analysisService) {
        this.secService = secService;
        this.analysisService = analysisService;
    }

    // 调试用接口：直接返回清洗后的 10-K 文本
    @GetMapping("/10k/{ticker}")
    public Mono<String> get10K(@PathVariable String ticker) {
        return secService.getLatest10KContent(ticker);
    }

    // 🚀 AI 分析接口 (SSE 流式输出)
    // 浏览器访问会看到文字一个个蹦出来
    // 支持 ?lang=zh 参数
    @GetMapping(value = "/analyze/{ticker}", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<String> analyze(
            @PathVariable String ticker,
            @RequestParam(defaultValue = "en") String lang) {
        return analysisService.analyzeStock(ticker, lang);
    }
}
