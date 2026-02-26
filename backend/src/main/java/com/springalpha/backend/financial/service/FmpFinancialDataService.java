package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.calculator.FinancialCalculator;
import com.springalpha.backend.financial.model.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/**
 * FMP Financial Data Service - 由于 FMP 是付费数据源，这里实现了真实的财务数据获取。
 * <p>
 * **为什么需要这个服务？**
 * LLM 虽然能读文本，但数学很差，而且 RAG 里的数字可能不全。
 * FMP (Financial Modeling Prep) 提供了结构化的 JSON 财务报表，
 * 我们用它来提供 "Ground Truth" (基准事实)。
 * <p>
 * **主要功能**:
 * 1. **Snapshot**: 获取当前最新的财务快照 (用于生成分析报告)。
 * 2. **Historical**: 获取过去 5 年的历史数据 (用于绘制前端趋势图)。
 */
@Service
@Primary
public class FmpFinancialDataService implements FinancialDataService {

    private static final Logger log = LoggerFactory.getLogger(FmpFinancialDataService.class);

    private final WebClient webClient;
    private final FinancialCalculator calculator;
    private final String apiKey;

    public FmpFinancialDataService(
            @Value("${app.fmp.base-url:https://financialmodelingprep.com/api/v3}") String baseUrl,
            @Value("${app.fmp.api-key}") String apiKey,
            FinancialCalculator calculator) {
        this.apiKey = apiKey;
        this.calculator = calculator;

        // Configure HttpClient with timeouts
        reactor.netty.http.client.HttpClient httpClient = reactor.netty.http.client.HttpClient.create()
                .option(io.netty.channel.ChannelOption.CONNECT_TIMEOUT_MILLIS, 10000)
                .responseTimeout(java.time.Duration.ofSeconds(10))
                .followRedirect(true)
                .doOnConnected(conn -> conn.addHandlerLast(new io.netty.handler.timeout.ReadTimeoutHandler(10))
                        .addHandlerLast(new io.netty.handler.timeout.WriteTimeoutHandler(10)));

        this.webClient = WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(new org.springframework.http.client.reactive.ReactorClientHttpConnector(httpClient))
                .build();
        log.info("🚀 FmpFinancialDataService initialized with base URL: {}", baseUrl);
    }

    /**
     * 获取财务事实快照 (Snapshot)
     * <p>
     * 一次性拉取三大报表 (Income, Balance, Cash Flow)，并组装成 FinancialFacts 对象。
     * 这些数据会被直接注入到 Prompt 里，告诉 AI "今年的确切数字是多少"。
     */
    @Override
    public FinancialFacts getFinancialFacts(String ticker) {
        String upperTicker = ticker.toUpperCase();
        log.info("📊 Fetching real financial data from FMP for: {}", upperTicker);

        try {
            // 1. 获取利润表 (Income Statement)
            // 必须强制 period=annual，否则免费版 key 可能会报错 403/402
            List<Map<String, Object>> incomeData = fetchData(
                    "/income-statement?symbol=" + upperTicker + "&period=annual&limit=5&apikey=" + apiKey);
            if (incomeData == null || incomeData.isEmpty()) {
                log.warn("⚠️ No income statement data found for {}", upperTicker);
                return null;
            }

            // 2. 获取资产负债表 (Balance Sheet)
            List<Map<String, Object>> balanceData = fetchData(
                    "/balance-sheet-statement?symbol=" + upperTicker + "&period=annual&limit=1&apikey=" + apiKey);

            // 3. 获取现金流量表 (Cash Flow)
            List<Map<String, Object>> cashFlowData = fetchData(
                    "/cash-flow-statement?symbol=" + upperTicker + "&period=annual&limit=5&apikey=" + apiKey);

            // 解析 JSON 数据并映射到 Java 对象
            // 我们取最近两年 (Index 0 和 1) 的数据来计算 YoY (同比变化)
            IncomeStatement currentIncome = parseIncomeStatement(incomeData.get(0));
            IncomeStatement previousIncome = incomeData.size() > 1 ? parseIncomeStatement(incomeData.get(1)) : null;

            BalanceSheet currentBalance = (balanceData != null && !balanceData.isEmpty())
                    ? parseBalanceSheet(balanceData.get(0))
                    : null;

            CashFlowStatement currentCashFlow = (cashFlowData != null && !cashFlowData.isEmpty())
                    ? parseCashFlowStatement(cashFlowData.get(0))
                    : null;
            CashFlowStatement previousCashFlow = (cashFlowData != null && cashFlowData.size() > 1)
                    ? parseCashFlowStatement(cashFlowData.get(1))
                    : null;

            // 获取公司名称和财报年份
            String companyName = getStringValue(incomeData.get(0), "symbol");
            String period = getStringValue(incomeData.get(0), "period") + " "
                    + getStringValue(incomeData.get(0), "calendarYear");

            log.info("✅ Successfully fetched FMP data for {} ({})", upperTicker, period);

            // 使用计算器模块，计算各种衍生指标 (如毛利率、净利率增长率)
            return calculator.buildFinancialFacts(
                    upperTicker,
                    companyName,
                    period,
                    currentIncome,
                    currentBalance,
                    currentCashFlow,
                    previousIncome,
                    previousCashFlow);

        } catch (Exception e) {
            log.error("❌ Failed to fetch FMP data for {}: {}", upperTicker, e.getMessage(), e);
            return null;
        }
    }

    @Override
    public boolean isSupported(String ticker) {
        return ticker != null && ticker.matches("^[A-Za-z]{1,5}$");
    }

    @Override
    public String[] getSupportedTickers() {
        return new String[] { "AAPL", "MSFT", "TSLA", "GOOGL", "AMZN", "META", "NVDA" };
    }

    /**
     * 获取历史趋势数据 (for Charts)
     * <p>
     * 前端的 "Revenue Trend" 和 "Margin Analysis" 图表就是靠这个方法喂数据的。
     * 它通过拉取过去 5 年的利润表，构建出一个时间序列数组。
     */
    @Override
    public List<HistoricalDataPoint> getHistoricalData(String ticker) {
        String upperTicker = ticker.toUpperCase();
        log.info("📈 Fetching historical margin data from FMP for: {}", upperTicker);

        try {
            // 拉取过去 5 年的年报
            List<Map<String, Object>> incomeData = fetchData(
                    "/income-statement?symbol=" + upperTicker + "&period=annual&limit=5&apikey=" + apiKey);
            if (incomeData == null || incomeData.isEmpty()) {
                return Collections.emptyList();
            }

            List<HistoricalDataPoint> history = new ArrayList<>();
            // 倒序遍历 (从旧到新)，方便前端图表按时间轴绘制
            for (int i = incomeData.size() - 1; i >= 0; i--) {
                Map<String, Object> data = incomeData.get(i);

                // 优先使用 calendarYear (例如 2023)，如果没有则回退到 fiscalYear
                String year = getStringValue(data, "calendarYear");
                if (year.isEmpty()) {
                    year = getStringValue(data, "fiscalYear");
                }
                String period = getStringValue(data, "period") + " " + year;

                // 提取关键指标
                BigDecimal revenue = getBigDecimalValue(data, "revenue");
                BigDecimal grossProfit = getBigDecimalValue(data, "grossProfit");
                BigDecimal operatingIncome = getBigDecimalValue(data, "operatingIncome");
                BigDecimal netIncome = getBigDecimalValue(data, "netIncome");

                // 计算三大利润率 (Margins)
                BigDecimal grossMargin = BigDecimal.ZERO;
                BigDecimal operatingMargin = BigDecimal.ZERO;
                BigDecimal netMargin = BigDecimal.ZERO;

                if (revenue != null && revenue.compareTo(BigDecimal.ZERO) > 0) {
                    if (grossProfit != null) {
                        grossMargin = grossProfit.divide(revenue, 4, java.math.RoundingMode.HALF_UP);
                    }
                    if (operatingIncome != null) {
                        operatingMargin = operatingIncome.divide(revenue, 4, java.math.RoundingMode.HALF_UP);
                    }
                    if (netIncome != null) {
                        netMargin = netIncome.divide(revenue, 4, java.math.RoundingMode.HALF_UP);
                    }
                }

                history.add(
                        new HistoricalDataPoint(period, grossMargin, operatingMargin, netMargin, revenue, netIncome));
            }

            log.info("✅ Retrieved {} quarters of historical data for {}", history.size(), upperTicker);
            return history;

        } catch (Exception e) {
            log.error("❌ Failed to fetch historical data for {}: {}", upperTicker, e.getMessage());
            return Collections.emptyList();
        }
    }

    // ------------------- Helper Methods -------------------

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> fetchData(String endpoint) {
        try {
            // Use CompletableFuture to run blocking WebClient call on separate thread pool
            // This avoids "block() not supported in reactor-http-nio" error
            return java.util.concurrent.CompletableFuture.supplyAsync(() -> {
                try {
                    return (List<Map<String, Object>>) webClient.get()
                            .uri(endpoint)
                            .retrieve()
                            .bodyToMono(List.class)
                            .block();
                } catch (Exception e) {
                    log.error("FMP HTTP call failed: {}", e.getMessage());
                    return null;
                }
            }).join(); // join() waits for result from ForkJoinPool, safe from reactor thread
        } catch (Exception e) {
            log.error("FMP API call failed for {}: {}", endpoint, e.getMessage());
            return null;
        }
    }

    private IncomeStatement parseIncomeStatement(Map<String, Object> data) {
        return IncomeStatement.builder()
                .period(getStringValue(data, "period") + " " + getStringValue(data, "calendarYear"))
                .reportedCurrency(getStringValue(data, "reportedCurrency"))
                .revenue(getBigDecimalValue(data, "revenue"))
                .costOfRevenue(getBigDecimalValue(data, "costOfRevenue"))
                .grossProfit(getBigDecimalValue(data, "grossProfit"))
                .researchAndDevelopment(getBigDecimalValue(data, "researchAndDevelopmentExpenses"))
                .sellingGeneralAndAdministrative(getBigDecimalValue(data, "sellingGeneralAndAdministrativeExpenses"))
                .operatingIncome(getBigDecimalValue(data, "operatingIncome"))
                .netIncome(getBigDecimalValue(data, "netIncome"))
                .earningsPerShareDiluted(getBigDecimalValue(data, "epsdiluted"))
                .build();
    }

    private BalanceSheet parseBalanceSheet(Map<String, Object> data) {
        return BalanceSheet.builder()
                .period(getStringValue(data, "period") + " " + getStringValue(data, "calendarYear"))
                .cashAndCashEquivalents(getBigDecimalValue(data, "cashAndCashEquivalents"))
                .totalCurrentAssets(getBigDecimalValue(data, "totalCurrentAssets"))
                .totalAssets(getBigDecimalValue(data, "totalAssets"))
                .totalCurrentLiabilities(getBigDecimalValue(data, "totalCurrentLiabilities"))
                .longTermDebt(getBigDecimalValue(data, "longTermDebt"))
                .totalLiabilities(getBigDecimalValue(data, "totalLiabilities"))
                .totalEquity(getBigDecimalValue(data, "totalStockholdersEquity"))
                .build();
    }

    private CashFlowStatement parseCashFlowStatement(Map<String, Object> data) {
        BigDecimal operatingCashFlow = getBigDecimalValue(data, "operatingCashFlow");
        BigDecimal capex = getBigDecimalValue(data, "capitalExpenditure");

        return CashFlowStatement.builder()
                .period(getStringValue(data, "period") + " " + getStringValue(data, "calendarYear"))
                .netIncome(getBigDecimalValue(data, "netIncome"))
                .depreciationAndAmortization(getBigDecimalValue(data, "depreciationAndAmortization"))
                .operatingCashFlow(operatingCashFlow)
                .capitalExpenditures(capex != null ? capex.negate() : null) // FMP returns positive, we need negative
                .build();
    }

    private String getStringValue(Map<String, Object> data, String key) {
        Object value = data.get(key);
        return value != null ? value.toString() : "";
    }

    private BigDecimal getBigDecimalValue(Map<String, Object> data, String key) {
        Object value = data.get(key);
        if (value == null) {
            return null;
        }
        try {
            if (value instanceof Number) {
                return new BigDecimal(value.toString());
            }
            return new BigDecimal(value.toString());
        } catch (NumberFormatException e) {
            return null;
        }
    }
}
