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
 * FMP Financial Data Service - Fetches real financial data from Financial
 * Modeling Prep API.
 * This replaces MockFinancialDataService when FMP_API_KEY is configured.
 * 
 * FMP API Endpoints Used:
 * - /income-statement/{ticker}?limit=5
 * - /balance-sheet-statement/{ticker}?limit=1
 * - /cash-flow-statement/{ticker}?limit=2
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
        this.webClient = WebClient.builder()
                .baseUrl(baseUrl)
                .build();
        log.info("🚀 FmpFinancialDataService initialized with base URL: {}", baseUrl);
    }

    @Override
    public FinancialFacts getFinancialFacts(String ticker) {
        String upperTicker = ticker.toUpperCase();
        log.info("📊 Fetching real financial data from FMP for: {}", upperTicker);

        try {
            // Fetch income statements (current + previous for YoY)
            // Fetch income statements (Force period=annual for free tier compatibility)
            // FMP Stable API uses query parameters:
            // /income-statement?symbol=AAPL&period=annual
            List<Map<String, Object>> incomeData = fetchData(
                    "/income-statement?symbol=" + upperTicker + "&period=annual&limit=5&apikey=" + apiKey);
            if (incomeData == null || incomeData.isEmpty()) {
                log.warn("⚠️ No income statement data found for {}", upperTicker);
                return null;
            }

            // Fetch balance sheet (annual)
            List<Map<String, Object>> balanceData = fetchData(
                    "/balance-sheet-statement?symbol=" + upperTicker + "&period=annual&limit=1&apikey=" + apiKey);

            // Fetch cash flow (annual)
            List<Map<String, Object>> cashFlowData = fetchData(
                    "/cash-flow-statement?symbol=" + upperTicker + "&period=annual&limit=5&apikey=" + apiKey);

            // Parse the data
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

            // Get company name from FMP data
            String companyName = getStringValue(incomeData.get(0), "symbol");
            String period = getStringValue(incomeData.get(0), "period") + " "
                    + getStringValue(incomeData.get(0), "calendarYear");

            log.info("✅ Successfully fetched FMP data for {} ({})", upperTicker, period);

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
        // FMP supports all US stocks; we'll do a lightweight check
        return ticker != null && ticker.matches("^[A-Za-z]{1,5}$");
    }

    @Override
    public String[] getSupportedTickers() {
        // FMP supports thousands of tickers; return common ones for demo
        return new String[] { "AAPL", "MSFT", "TSLA", "GOOGL", "AMZN", "META", "NVDA" };
    }

    @Override
    public List<HistoricalDataPoint> getHistoricalData(String ticker) {
        String upperTicker = ticker.toUpperCase();
        log.info("📈 Fetching historical margin data from FMP for: {}", upperTicker);

        try {
            // Fetch last 5 years of income statements (Annual data is free tier friendly)
            // FMP Stable API uses query parameters
            List<Map<String, Object>> incomeData = fetchData(
                    "/income-statement?symbol=" + upperTicker + "&period=annual&limit=5&apikey=" + apiKey);
            if (incomeData == null || incomeData.isEmpty()) {
                return Collections.emptyList();
            }

            List<HistoricalDataPoint> history = new ArrayList<>();
            // Reverse to get chronological order (oldest first)
            for (int i = incomeData.size() - 1; i >= 0; i--) {
                Map<String, Object> data = incomeData.get(i);
                String year = getStringValue(data, "calendarYear");
                if (year.isEmpty()) {
                    year = getStringValue(data, "fiscalYear");
                }
                String period = getStringValue(data, "period") + " " + year;

                BigDecimal revenue = getBigDecimalValue(data, "revenue");
                BigDecimal grossProfit = getBigDecimalValue(data, "grossProfit");
                BigDecimal operatingIncome = getBigDecimalValue(data, "operatingIncome");
                BigDecimal netIncome = getBigDecimalValue(data, "netIncome");

                // Calculate margins
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
