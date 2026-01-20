package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

import java.time.Duration;
import java.util.Map;

@Component
public class MockStrategy implements AiAnalysisStrategy {

    private static final Logger log = LoggerFactory.getLogger(MockStrategy.class);
    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public Flux<String> analyze(String ticker, String textContent) {
        log.info("🤖 使用策略: Mock Strategy (本地模拟数据)");

        String mockResponse = """
            ### 📊 %s 财报智能分析 (演示模式)
            
            > **注意**: 由于 API 配额限制或网络问题，当前显示的是**本地模拟数据**。
            
            #### 1. 核心财务指标 💰
            *   **总营收**: $1000 亿 (📈 +5%% YoY) - 尽管宏观环境充满挑战，核心业务依然稳健。
            *   **净利润**: $250 亿 (持平) - 研发投入增加导致利润率略有承压。
            *   **每股收益 (EPS)**: $6.50
            
            #### 2. 关键风险因素 ⚠️
            *   **宏观经济**: 通胀压力可能抑制消费者支出。
            *   **供应链**: 全球物流波动可能影响新品交付。
            *   **监管合规**: 欧盟及北美反垄断调查仍在持续。
            
            #### 3. 分析师观点 👨‍⚖️
            公司展现了极强的**韧性**。尽管短期面临逆风，但长期基本面未变。建议 **持有 (HOLD)** 观望。
            """.formatted(ticker);

        // 模拟打字机效果，把整段文本拆成字符流，每 50ms 发一个字
        return Flux.fromArray(mockResponse.split(""))
                .delayElements(Duration.ofMillis(20))
                .map(charStr -> {
                    try {
                        return objectMapper.writeValueAsString(Map.of("text", charStr));
                    } catch (Exception e) {
                        return "";
                    }
                });
    }

    @Override
    public String getName() {
        return "mock";
    }
}
