package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.cache.MarketDataCacheService;
import com.springalpha.backend.financial.calculator.FinancialCalculator;
import com.springalpha.backend.financial.model.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.time.Duration;
import java.time.LocalDate;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;
import java.util.stream.Stream;

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
public class FmpFinancialDataService implements FinancialDataService {

    private static final Logger log = LoggerFactory.getLogger(FmpFinancialDataService.class);
    private static final int FMP_REQUEST_TIMEOUT_SECONDS = 15;

    private final WebClient webClient;
    private final WebClient ratiosWebClient;
    private final FinancialCalculator calculator;
    private final MarketDataCacheService cacheService;
    private final List<String> apiKeys;
    private final int requestTimeoutSeconds;
    private final Duration factsCacheTtl;
    private final Duration historyCacheTtl;
    private final AtomicInteger apiKeyCursor = new AtomicInteger();
    private final ConcurrentHashMap<String, CompletableFuture<?>> inFlightRequests = new ConcurrentHashMap<>();

    @Autowired
    public FmpFinancialDataService(
            @Value("${app.fmp.base-url:https://financialmodelingprep.com/api/v3}") String baseUrl,
            @Value("${app.fmp.api-key:}") String apiKey,
            @Value("${app.fmp.api-keys:}") String configuredApiKeys,
            @Value("${app.fmp.cache.facts-ttl:PT6H}") Duration factsCacheTtl,
            @Value("${app.fmp.cache.history-ttl:PT24H}") Duration historyCacheTtl,
            FinancialCalculator calculator,
            MarketDataCacheService cacheService) {
        this(baseUrl, parseApiKeys(apiKey, configuredApiKeys), calculator, buildWebClient(baseUrl),
                buildWebClient("https://financialmodelingprep.com"), cacheService, FMP_REQUEST_TIMEOUT_SECONDS,
                factsCacheTtl, historyCacheTtl);
    }

    FmpFinancialDataService(
            String baseUrl,
            String apiKey,
            FinancialCalculator calculator) {
        this(baseUrl, List.of(apiKey), calculator, buildWebClient(baseUrl),
                buildWebClient("https://financialmodelingprep.com"), null, FMP_REQUEST_TIMEOUT_SECONDS,
                Duration.ofHours(6), Duration.ofHours(24));
    }

    FmpFinancialDataService(
            String baseUrl,
            String apiKey,
            FinancialCalculator calculator,
            WebClient webClient,
            WebClient ratiosWebClient,
            int requestTimeoutSeconds) {
        this(baseUrl, List.of(apiKey), calculator, webClient, ratiosWebClient, null, requestTimeoutSeconds,
                Duration.ofHours(6), Duration.ofHours(24));
    }

    FmpFinancialDataService(
            String baseUrl,
            List<String> apiKeys,
            FinancialCalculator calculator,
            WebClient webClient,
            WebClient ratiosWebClient,
            MarketDataCacheService cacheService,
            int requestTimeoutSeconds,
            Duration factsCacheTtl,
            Duration historyCacheTtl) {
        this.calculator = calculator;
        this.webClient = webClient;
        this.ratiosWebClient = ratiosWebClient;
        this.cacheService = cacheService;
        this.apiKeys = apiKeys;
        this.requestTimeoutSeconds = requestTimeoutSeconds;
        this.factsCacheTtl = factsCacheTtl;
        this.historyCacheTtl = historyCacheTtl;
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
        return getFinancialFacts(ticker, "quarterly");
    }

    @Override
    public FinancialFacts getFinancialFacts(String ticker, String reportType) {
        String upperTicker = ticker.toUpperCase();
        String normalizedReportType = normalizeReportType(reportType);
        log.info("📊 Fetching real financial data from FMP for: {} ({})", upperTicker, normalizedReportType);

        Optional<FinancialFacts> cachedFacts = getCachedFinancialFacts(upperTicker, normalizedReportType, false);
        if (cachedFacts.isPresent()) {
            log.info("💾 Returning cached financial facts for {} ({})", upperTicker, normalizedReportType);
            return cachedFacts.get();
        }

        try {
            return executeDeduped(buildFactsCacheKey(upperTicker, normalizedReportType),
                    () -> loadFinancialFacts(upperTicker, normalizedReportType));
        } catch (FmpQuotaExceededException e) {
            Optional<FinancialFacts> staleFacts = getCachedFinancialFacts(upperTicker, normalizedReportType, true);
            if (staleFacts.isPresent()) {
                log.warn("⚠️ FMP quota exceeded for {} ({}). Returning stale cached financial facts.",
                        upperTicker, normalizedReportType);
                return staleFacts.get();
            }
            throw e;
        } catch (Exception e) {
            log.error("❌ Failed to fetch FMP data for {}: {}", upperTicker, e.getMessage(), e);
            return null;
        }
    }

    private FinancialFacts loadFinancialFacts(String upperTicker, String reportType) {
        Optional<FinancialFacts> cachedFacts = getCachedFinancialFacts(upperTicker, reportType, false);
        if (cachedFacts.isPresent()) {
            return cachedFacts.get();
        }

        try {
            String fmpPeriod = toFmpPeriod(reportType);

            // 1. 获取利润表 (Income Statement)
            List<Map<String, Object>> incomeData = fetchData(
                    "/income-statement?symbol=" + upperTicker + "&period=" + fmpPeriod + "&limit=5");
            if (incomeData == null || incomeData.isEmpty()) {
                log.warn("⚠️ No income statement data found for {}", upperTicker);
                return null;
            }

            // 2. 获取资产负债表 (Balance Sheet)
            List<Map<String, Object>> balanceData = fetchData(
                    "/balance-sheet-statement?symbol=" + upperTicker + "&period=" + fmpPeriod + "&limit=1");

            // 3. 获取现金流量表 (Cash Flow)
            List<Map<String, Object>> cashFlowData = fetchData(
                    "/cash-flow-statement?symbol=" + upperTicker + "&period=" + fmpPeriod + "&limit=5");

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

            // 获取公司名称、财报期和文件日期
            String companyName = resolveCompanyName(upperTicker, incomeData.get(0));
            String period = resolveReportingPeriod(incomeData.get(0));
            String filingDate = resolveFilingDate(incomeData.get(0));

            log.info("✅ Successfully fetched FMP data for {} ({})", upperTicker, period);

            // 使用计算器模块，计算各种衍生指标 (如毛利率、净利率增长率)
            FinancialFacts facts = calculator.buildFinancialFacts(
                    upperTicker,
                    companyName,
                    period,
                    currentIncome,
                    currentBalance,
                    currentCashFlow,
                    previousIncome,
                    previousCashFlow);
            facts.setFilingDate(filingDate);

            // 4. Fetch valuation ratios (P/E, P/B) from FMP /stable/ratios
            try {
                List<Map<String, Object>> ratiosData = fetchRatios(upperTicker, reportType);
                if (ratiosData != null && !ratiosData.isEmpty()) {
                    Map<String, Object> ratios = ratiosData.get(0);
                    facts.setPriceToEarningsRatio(getBigDecimalValue(ratios, "priceToEarningsRatio"));
                    facts.setPriceToBookRatio(getBigDecimalValue(ratios, "priceToBookRatio"));
                    log.info("✅ Fetched valuation ratios for {}: P/E={}, P/B={}",
                            upperTicker, facts.getPriceToEarningsRatio(), facts.getPriceToBookRatio());
                }
            } catch (Exception e) {
                log.warn("⚠️ Failed to fetch valuation ratios for {}: {}", upperTicker, e.getMessage());
            }

            cacheFinancialFacts(upperTicker, reportType, facts);
            return facts;

        } catch (FmpQuotaExceededException e) {
            throw e;
        } catch (Exception e) {
            throw new FmpApiException("Failed to fetch FMP data for " + upperTicker, e);
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
        return getHistoricalData(ticker, "quarterly");
    }

    @Override
    public List<HistoricalDataPoint> getHistoricalData(String ticker, String reportType) {
        String upperTicker = ticker.toUpperCase();
        String normalizedReportType = normalizeReportType(reportType);
        log.info("📈 Fetching historical margin data from FMP for: {} ({})", upperTicker, normalizedReportType);

        Optional<List<HistoricalDataPoint>> cachedHistory = getCachedHistoricalData(upperTicker, normalizedReportType, false);
        if (cachedHistory.isPresent()) {
            log.info("💾 Returning cached historical data for {} ({})", upperTicker, normalizedReportType);
            return cachedHistory.get();
        }

        try {
            return executeDeduped(buildHistoryCacheKey(upperTicker, normalizedReportType),
                    () -> loadHistoricalData(upperTicker, normalizedReportType));
        } catch (FmpQuotaExceededException e) {
            Optional<List<HistoricalDataPoint>> staleHistory = getCachedHistoricalData(upperTicker, normalizedReportType, true);
            if (staleHistory.isPresent()) {
                log.warn("⚠️ FMP quota exceeded for {} ({}). Returning stale cached historical data.",
                        upperTicker, normalizedReportType);
                return staleHistory.get();
            }
            throw e;
        } catch (Exception e) {
            log.error("❌ Failed to fetch historical data for {}: {}", upperTicker, e.getMessage());
            return Collections.emptyList();
        }
    }

    private List<HistoricalDataPoint> loadHistoricalData(String upperTicker, String reportType) {
        Optional<List<HistoricalDataPoint>> cachedHistory = getCachedHistoricalData(upperTicker, reportType, false);
        if (cachedHistory.isPresent()) {
            return cachedHistory.get();
        }

        try {
            String fmpPeriod = toFmpPeriod(reportType);

            List<Map<String, Object>> incomeData = fetchData(
                    "/income-statement?symbol=" + upperTicker + "&period=" + fmpPeriod + "&limit=5");
            if (incomeData == null || incomeData.isEmpty()) {
                return Collections.emptyList();
            }

            List<HistoricalDataPoint> history = new ArrayList<>();
            // 倒序遍历 (从旧到新)，方便前端图表按时间轴绘制
            for (int i = incomeData.size() - 1; i >= 0; i--) {
                Map<String, Object> data = incomeData.get(i);

                String period = resolveReportingPeriod(data);

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
            cacheHistoricalData(upperTicker, reportType, history);
            return history;

        } catch (FmpQuotaExceededException e) {
            throw e;
        } catch (Exception e) {
            throw new FmpApiException("Failed to fetch historical data for " + upperTicker, e);
        }
    }

    // ------------------- Helper Methods -------------------

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> fetchData(String endpoint) {
        return fetchWithKeyRotation(webClient, endpoint);
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> fetchWithKeyRotation(WebClient client, String endpoint) {
        if (apiKeys == null || apiKeys.isEmpty()) {
            throw new FmpApiException("FMP API key is not configured");
        }

        RuntimeException lastFailure = null;
        int startIndex = Math.floorMod(apiKeyCursor.getAndIncrement(), apiKeys.size());

        for (int attempt = 0; attempt < apiKeys.size(); attempt++) {
            String key = apiKeys.get((startIndex + attempt) % apiKeys.size());
            String endpointWithKey = appendApiKey(endpoint, key);

            try {
                List<?> raw = client.get()
                        .uri(endpointWithKey)
                        .exchangeToMono(response -> decodeListResponse(response, endpoint))
                        .timeout(Duration.ofSeconds(requestTimeoutSeconds))
                        .block();
                return raw == null ? null : (List<Map<String, Object>>) raw;
            } catch (FmpQuotaExceededException e) {
                log.warn("⚠️ FMP quota exceeded for one key on {}. Trying next key if available.", endpoint);
                lastFailure = e;
            } catch (Exception e) {
                log.warn("⚠️ FMP request failed for {} using current key: {}", endpoint, rootMessage(e));
                lastFailure = e instanceof RuntimeException runtimeException
                        ? runtimeException
                        : new FmpApiException("FMP API call failed for " + endpoint, e);
            }
        }

        if (lastFailure != null) {
            throw lastFailure;
        }
        return null;
    }

    @SuppressWarnings("unchecked")
    List<Map<String, Object>> fetchRatios(String ticker, String reportType) {
        // Valuation ratios are point-in-time market multiples. FMP's quarterly
        // `period=quarter` ratio endpoint is premium-only on lower plans, so use the
        // annual endpoint for both modes to avoid plan-specific 402 failures.
        return fetchWithKeyRotation(ratiosWebClient,
                "/stable/ratios?symbol=" + ticker + "&period=annual&limit=1");
    }

    public FmpSupplementalData getSupplementalData(String ticker, String reportType) {
        String upperTicker = ticker.toUpperCase();
        String normalizedReportType = normalizeReportType(reportType);

        boolean profileAvailable = false;
        boolean quoteAvailable = false;
        boolean valuationAvailable = false;
        String companyName = null;
        BigDecimal latestPrice = null;
        BigDecimal marketCap = null;
        BigDecimal priceToEarningsRatio = null;
        BigDecimal priceToBookRatio = null;
        List<String> missingSources = new ArrayList<>();

        try {
            List<Map<String, Object>> profileData = fetchData("/profile?symbol=" + upperTicker);
            if (profileData != null && !profileData.isEmpty()) {
                profileAvailable = true;
                companyName = firstNonBlank(
                        getStringValue(profileData.get(0), "companyName"),
                        getStringValue(profileData.get(0), "name"));
                marketCap = firstNonNullBigDecimal(
                        getBigDecimalValue(profileData.get(0), "mktCap"),
                        getBigDecimalValue(profileData.get(0), "marketCap"));
            } else {
                missingSources.add("profile");
            }
        } catch (Exception e) {
            missingSources.add("profile");
            log.warn("⚠️ Failed to fetch company profile for {}: {}", upperTicker, e.getMessage());
        }

        try {
            List<Map<String, Object>> quoteData = fetchData("/quote?symbol=" + upperTicker);
            if (quoteData != null && !quoteData.isEmpty()) {
                latestPrice = getBigDecimalValue(quoteData.get(0), "price");
                quoteAvailable = latestPrice != null;
            }
            if (!quoteAvailable) {
                missingSources.add("quote");
            }
        } catch (Exception e) {
            missingSources.add("quote");
            log.warn("⚠️ Failed to fetch quote for {}: {}", upperTicker, e.getMessage());
        }

        try {
            List<Map<String, Object>> ratiosData = fetchRatios(upperTicker, normalizedReportType);
            if (ratiosData != null && !ratiosData.isEmpty()) {
                Map<String, Object> ratios = ratiosData.get(0);
                priceToEarningsRatio = getBigDecimalValue(ratios, "priceToEarningsRatio");
                priceToBookRatio = getBigDecimalValue(ratios, "priceToBookRatio");
                valuationAvailable = priceToEarningsRatio != null || priceToBookRatio != null;
            }
            if (!valuationAvailable) {
                missingSources.add("valuation");
            }
        } catch (Exception e) {
            missingSources.add("valuation");
            log.warn("⚠️ Failed to fetch valuation data for {}: {}", upperTicker, e.getMessage());
        }

        String message = missingSources.isEmpty()
                ? null
                : "Supplemental FMP data unavailable for: " + String.join(", ", missingSources);

        return new FmpSupplementalData(
                profileAvailable,
                quoteAvailable,
                valuationAvailable,
                companyName,
                latestPrice,
                marketCap,
                priceToEarningsRatio,
                priceToBookRatio,
                message);
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

    String getStringValue(Map<String, Object> data, String key) {
        Object value = data.get(key);
        return value != null ? value.toString() : "";
    }

    String resolveCompanyName(String ticker, Map<String, Object> incomeRow) {
        String companyName = firstNonBlank(
                getStringValue(incomeRow, "companyName"),
                getStringValue(incomeRow, "name"));

        if (!companyName.isBlank()) {
            return companyName;
        }

        try {
            List<Map<String, Object>> profileData = fetchData("/profile?symbol=" + ticker);
            if (profileData != null && !profileData.isEmpty()) {
                return firstNonBlank(
                        getStringValue(profileData.get(0), "companyName"),
                        getStringValue(profileData.get(0), "name"),
                        ticker);
            }
        } catch (Exception e) {
            log.warn("⚠️ Failed to fetch company profile for {}: {}", ticker, e.getMessage());
        }

        return ticker;
    }

    String resolveReportingPeriod(Map<String, Object> incomeRow) {
        String rawPeriod = getStringValue(incomeRow, "period").trim();
        String filingDate = firstNonBlank(
                getStringValue(incomeRow, "date"),
                getStringValue(incomeRow, "acceptedDate"),
                getStringValue(incomeRow, "fillingDate"));
        String year = firstNonBlank(
                getStringValue(incomeRow, "fiscalYear"),
                deriveFiscalYear(rawPeriod, filingDate),
                getStringValue(incomeRow, "calendarYear"),
                extractYear(filingDate));

        if (rawPeriod.isBlank()) {
            rawPeriod = "FY";
        }

        if (year.isBlank()) {
            return rawPeriod;
        }

        return rawPeriod + " " + year;
    }

    String deriveFiscalYear(String rawPeriod, String filingDate) {
        if (rawPeriod == null || rawPeriod.isBlank() || filingDate == null || filingDate.isBlank()) {
            return "";
        }

        String baseYear = extractYear(filingDate);
        if (baseYear.isBlank()) {
            return "";
        }

        String normalizedPeriod = rawPeriod.trim().toUpperCase();
        if (!normalizedPeriod.startsWith("Q1")) {
            return baseYear;
        }

        try {
            LocalDate parsed = LocalDate.parse(filingDate.substring(0, 10));
            return parsed.getMonthValue() >= 10
                    ? Integer.toString(parsed.getYear() + 1)
                    : Integer.toString(parsed.getYear());
        } catch (DateTimeParseException e) {
            return baseYear;
        }
    }

    String resolveFilingDate(Map<String, Object> incomeRow) {
        String filingDate = firstNonBlank(
                getStringValue(incomeRow, "date"),
                getStringValue(incomeRow, "acceptedDate"),
                getStringValue(incomeRow, "fillingDate"));

        if (filingDate.contains(" ")) {
            filingDate = filingDate.substring(0, filingDate.indexOf(' '));
        }

        return filingDate;
    }

    String extractYear(String dateValue) {
        if (dateValue == null || dateValue.isBlank()) {
            return "";
        }

        String trimmed = dateValue.trim();
        return trimmed.length() >= 4 ? trimmed.substring(0, 4) : "";
    }

    String firstNonBlank(String... values) {
        for (String value : values) {
            if (value != null && !value.isBlank()) {
                return value.trim();
            }
        }
        return "";
    }

    BigDecimal getBigDecimalValue(Map<String, Object> data, String key) {
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

    private BigDecimal firstNonNullBigDecimal(BigDecimal... values) {
        for (BigDecimal value : values) {
            if (value != null) {
                return value;
            }
        }
        return null;
    }

    private static WebClient buildWebClient(String baseUrl) {
        reactor.netty.http.client.HttpClient httpClient = reactor.netty.http.client.HttpClient.create()
                .option(io.netty.channel.ChannelOption.CONNECT_TIMEOUT_MILLIS, 10000)
                .responseTimeout(java.time.Duration.ofSeconds(10))
                .followRedirect(true)
                .doOnConnected(conn -> conn.addHandlerLast(new io.netty.handler.timeout.ReadTimeoutHandler(10))
                        .addHandlerLast(new io.netty.handler.timeout.WriteTimeoutHandler(10)));

        return WebClient.builder()
                .baseUrl(baseUrl)
                .clientConnector(new org.springframework.http.client.reactive.ReactorClientHttpConnector(httpClient))
                .build();
    }

    private Optional<FinancialFacts> getCachedFinancialFacts(String ticker, String reportType, boolean includeExpired) {
        if (cacheService == null) {
            return Optional.empty();
        }
        Optional<FinancialFacts> cached = cacheService.getFinancialFacts(ticker, reportType, includeExpired);
        if (cached.isPresent() && shouldBypassCachedFacts(cached.get(), reportType)) {
            log.info("♻️ Ignoring cached financial facts for {} ({}) because the stored period label is stale",
                    ticker, reportType);
            return Optional.empty();
        }
        return cached;
    }

    boolean shouldBypassCachedFacts(FinancialFacts facts, String reportType) {
        if (facts == null || !"quarterly".equalsIgnoreCase(reportType) || facts.getPeriod() == null
                || facts.getFilingDate() == null) {
            return false;
        }

        String normalizedPeriod = facts.getPeriod().trim().toUpperCase();
        if (!normalizedPeriod.startsWith("Q1 ")) {
            return false;
        }

        String cachedYear = normalizedPeriod.substring(3).trim();
        String derivedFiscalYear = deriveFiscalYear("Q1", facts.getFilingDate());
        return !derivedFiscalYear.isBlank() && !derivedFiscalYear.equals(cachedYear);
    }

    private void cacheFinancialFacts(String ticker, String reportType, FinancialFacts facts) {
        if (cacheService != null && facts != null) {
            cacheService.putFinancialFacts(ticker, reportType, facts, factsCacheTtl);
        }
    }

    private Optional<List<HistoricalDataPoint>> getCachedHistoricalData(String ticker, String reportType,
            boolean includeExpired) {
        return cacheService == null ? Optional.empty()
                : cacheService.getHistoricalData(ticker, reportType, includeExpired);
    }

    private void cacheHistoricalData(String ticker, String reportType, List<HistoricalDataPoint> history) {
        if (cacheService != null && history != null && !history.isEmpty()) {
            cacheService.putHistoricalData(ticker, reportType, history, historyCacheTtl);
        }
    }

    @SuppressWarnings("unchecked")
    private <T> T executeDeduped(String cacheKey, java.util.function.Supplier<T> supplier) {
        CompletableFuture<T> created = new CompletableFuture<>();
        CompletableFuture<T> existing = (CompletableFuture<T>) inFlightRequests.putIfAbsent(cacheKey, created);
        if (existing != null) {
            return existing.join();
        }

        try {
            T result = supplier.get();
            created.complete(result);
            return result;
        } catch (Throwable t) {
            created.completeExceptionally(t);
            throw t;
        } finally {
            inFlightRequests.remove(cacheKey, created);
        }
    }

    private Mono<List<?>> decodeListResponse(ClientResponse response, String endpoint) {
        if (response.statusCode().is2xxSuccessful()) {
            return response.bodyToMono(List.class).map(body -> (List<?>) body);
        }

        return response.bodyToMono(String.class)
                .defaultIfEmpty("")
                .flatMap(body -> Mono.error(buildFmpException(endpoint, response.statusCode().value(), body)));
    }

    private RuntimeException buildFmpException(String endpoint, int statusCode, String body) {
        String message = "FMP request failed for " + endpoint + " (" + statusCode + ")";
        if (isQuotaExceeded(statusCode, body)) {
            return new FmpQuotaExceededException(
                    "FMP daily quota exceeded. Configure additional API keys or wait for quota reset.");
        }
        return new FmpApiException(message + (body.isBlank() ? "" : ": " + body));
    }

    private String buildFactsCacheKey(String ticker, String reportType) {
        return "fmp:facts:" + normalizeReportType(reportType) + ":" + ticker.toUpperCase();
    }

    private String buildHistoryCacheKey(String ticker, String reportType) {
        return "fmp:history:" + normalizeReportType(reportType) + ":" + ticker.toUpperCase();
    }

    private String normalizeReportType(String reportType) {
        return "quarterly";
    }

    private String toFmpPeriod(String reportType) {
        return "quarter";
    }

    private boolean isQuotaExceeded(int statusCode, String body) {
        String normalized = body == null ? "" : body.toLowerCase();
        return statusCode == 429
                || normalized.contains("quota")
                || normalized.contains("too many requests")
                || normalized.contains("api calls per day")
                || normalized.contains("limit reached")
                || (statusCode == 403 && normalized.contains("limit"))
                || (statusCode == 401 && normalized.contains("plan"));
    }

    private String appendApiKey(String endpoint, String key) {
        String separator = endpoint.contains("?") ? "&" : "?";
        return endpoint + separator + "apikey=" + key;
    }

    private static List<String> parseApiKeys(String apiKey, String configuredApiKeys) {
        List<String> keys = Stream.concat(
                        configuredApiKeys == null ? Stream.empty() : Stream.of(configuredApiKeys.split(",")),
                        apiKey == null ? Stream.empty() : Stream.of(apiKey))
                .map(String::trim)
                .filter(value -> !value.isBlank())
                .distinct()
                .collect(Collectors.toList());
        return keys.isEmpty() ? Collections.emptyList() : keys;
    }

    private String rootMessage(Throwable throwable) {
        Throwable current = throwable;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        if (current instanceof TimeoutException) {
            return "timeout";
        }
        return current.getMessage() != null ? current.getMessage() : throwable.getMessage();
    }
}
