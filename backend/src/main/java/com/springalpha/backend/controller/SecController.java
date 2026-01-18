package com.springalpha.backend.controller;

import com.springalpha.backend.service.SecService;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/sec")
public class SecController {

    private final SecService secService;

    public SecController(SecService secService) {
        this.secService = secService;
    }

    // 调试用接口：直接返回清洗后的 10-K 文本
    // 生产环境不建议直接把几十MB文本吐给前端，这里仅用于 MVP 验证
    @GetMapping("/10k/{ticker}")
    public Mono<String> get10K(@PathVariable String ticker) {
        return secService.getLatest10KContent(ticker);
    }
}
