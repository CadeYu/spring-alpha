package com.springalpha.backend.service.strategy;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.ai.chat.client.ChatClient;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.context.annotation.Description;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

import java.util.List;
import java.util.Map;
import java.util.function.Function;

/**
 * Spring AI 框架集成策略
 * 
 * 亮点：
 * 1. 使用 Spring AI 官方 ChatClient API，简化流式调用
 * 2. 支持 Function Calling - AI 可以自动调用工具函数获取实时数据
 * 3. 展示框架与手动实现的对比
 */
@Component
public class SpringAiStrategy implements AiAnalysisStrategy {

    private static final Logger log = LoggerFactory.getLogger(SpringAiStrategy.class);
    private final ChatClient chatClient;
    private final ObjectMapper objectMapper;

    public SpringAiStrategy(ChatModel chatModel, ObjectMapper objectMapper) {
        if (chatModel == null) {
            throw new IllegalArgumentException("ChatModel cannot be null");
        }
        this.chatClient = ChatClient.builder(chatModel)
                .defaultFunctions("getStockPrice", "getCompetitorTickers") // 注册工具函数
                .build();
        this.objectMapper = objectMapper;
        log.info("✅ SpringAiStrategy initialized with Function Calling support");
    }

    @Override
    public Flux<String> analyze(String ticker, String textContent, String lang) {
        log.info("🤖 使用策略: Spring AI (with Function Calling)");

        // 动态构建 Prompt
        boolean isChinese = "zh".equalsIgnoreCase(lang);
        String systemPrompt = isChinese
                ? "你是一位精通美股的资深金融分析师。你可以调用工具获取实时数据来增强分析。"
                : "You are a senior Wall Street Analyst. You can call tools to get real-time data.";

        String userPrompt;
        if (isChinese) {
            userPrompt = String.format("""
                    请分析这篇关于 %s 的 SEC 10-K 财报。

                    你的任务：
                    1. 使用**中文**回答。
                    2. 使用 Markdown 格式。
                    3. 重点分析：关键财务指标（营收、净利、毛利）、主要风险、未来展望。
                    4. **如果需要，可以调用 getStockPrice 获取实时股价，调用 getCompetitorTickers 获取竞品公司**。
                    5. 风格：专业、客观，多用数据说话，适当使用 Emojis 增强可读性。

                    财报内容如下：
                    %s
                    """, ticker, textContent);
        } else {
            userPrompt = String.format(
                    """
                            Please analyze this SEC 10-K report for %s.

                            Task:
                            1. Answer in **English**.
                            2. Use Markdown format.
                            3. Focus on: Key Financial Metrics (Revenue, Net Income, Gross Margin), Key Risks, and Future Outlook.
                            4. **You can call getStockPrice to get real-time price, and getCompetitorTickers to get competitors**.
                            5. Style: Professional, objective, data-driven, use Emojis.

                            Report Content:
                            %s
                            """,
                    ticker, textContent);
        }

        return chatClient.prompt()
                .system(systemPrompt)
                .user(userPrompt != null ? userPrompt : "")
                .stream()
                .content()
                .doOnNext(chunk -> log.debug("📥 Received chunk: {}", chunk))
                .map(chunk -> {
                    try {
                        // 将每个 chunk 包装成 JSON 格式，保持与其他策略的一致性
                        return objectMapper.writeValueAsString(Map.of("text", chunk));
                    } catch (Exception e) {
                        log.error("❌ Failed to serialize chunk", e);
                        return "";
                    }
                })
                .filter(json -> !json.isEmpty())
                .doOnComplete(() -> log.info("✅ Spring AI streaming completed"));
    }

    @Override
    public String getName() {
        return "spring-ai";
    }

    // ========== Tool Functions (Function Calling) ==========

    /**
     * 工具函数：获取股票的实时价格
     * AI 可以自动调用这个方法来获取最新股价
     */
    @Description("Get the current real-time stock price for a given ticker symbol")
    public Function<StockPriceRequest, StockPriceResponse> getStockPrice() {
        return request -> {
            String ticker = request.ticker();
            log.info("🔧 Function Called: getStockPrice({})", ticker);

            // TODO: 接入真实的股价 API (如 Alpha Vantage, Yahoo Finance)
            // 目前返回模拟数据
            double mockPrice = switch (ticker.toUpperCase()) {
                case "AAPL" -> 178.25;
                case "TSLA" -> 252.75;
                case "NVDA" -> 875.50;
                case "MSFT" -> 420.15;
                default -> 100.00 + Math.random() * 200;
            };

            return new StockPriceResponse(ticker, mockPrice, "USD", "2026-01-24");
        };
    }

    /**
     * 工具函数：获取竞争对手公司列表
     * AI 可以调用这个方法来进行横向对比分析
     */
    @Description("Get a list of competitor ticker symbols for a given company")
    public Function<CompetitorRequest, CompetitorResponse> getCompetitorTickers() {
        return request -> {
            String ticker = request.ticker();
            log.info("🔧 Function Called: getCompetitorTickers({})", ticker);

            // 基于行业的竞品映射 (可以扩展为从数据库查询)
            List<String> competitors = switch (ticker.toUpperCase()) {
                case "AAPL" -> List.of("MSFT", "GOOGL", "AMZN", "META");
                case "TSLA" -> List.of("F", "GM", "RIVN", "LCID");
                case "NVDA" -> List.of("AMD", "INTC", "QCOM");
                case "MSFT" -> List.of("AAPL", "GOOGL", "AMZN");
                default -> List.of("SPY"); // 默认与大盘对比
            };

            return new CompetitorResponse(ticker, competitors);
        };
    }

    // ========== Request/Response Records (Function Calling 参数定义) ==========

    public record StockPriceRequest(String ticker) {
    }

    public record StockPriceResponse(
            String ticker,
            double price,
            String currency,
            String timestamp) {
    }

    public record CompetitorRequest(String ticker) {
    }

    public record CompetitorResponse(
            String ticker,
            List<String> competitors) {
    }
}
