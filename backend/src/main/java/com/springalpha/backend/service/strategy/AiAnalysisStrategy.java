package com.springalpha.backend.service.strategy;

import reactor.core.publisher.Flux;

public interface AiAnalysisStrategy {
    /**
     * 执行财报分析
     * @param ticker 股票代码
     * @param textContent 财报纯文本
     * @return 流式分析结果
     */
    Flux<String> analyze(String ticker, String textContent);

    /**
     * 策略名称 (用于配置选择)
     */
    String getName();
}
