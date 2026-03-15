package com.springalpha.backend.financial.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.springalpha.backend.financial.cache.MarketDataCacheService;
import com.springalpha.backend.financial.calculator.FinancialCalculator;
import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.model.HistoricalDataPoint;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatusCode;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class FmpFinancialDataServiceTest {

    private final FmpFinancialDataService service = new FmpFinancialDataService(
            "https://example.com",
            "demo-key",
            new FinancialCalculator());

    @Test
    void resolveCompanyNamePrefersIncomeStatementMetadata() {
        String companyName = service.resolveCompanyName("TSLA", Map.of("companyName", "Tesla, Inc."));

        assertEquals("Tesla, Inc.", companyName);
    }

    @Test
    void resolveCompanyNameFallsBackToProfileEndpoint() {
        FmpFinancialDataService service = testService(
                newStubClient(Map.of(
                        "/profile?symbol=TSLA&apikey=demo-key",
                        stubJson(200, """
                    [{"companyName":"Tesla, Inc."}]
                    """))),
                newStubClient(Map.of()),
                1);

        String companyName = service.resolveCompanyName("TSLA", Map.of());

        assertEquals("Tesla, Inc.", companyName);
    }

    @Test
    void resolveReportingPeriodBuildsAnnualLabelFromDateFallback() {
        String period = service.resolveReportingPeriod(Map.of(
                "period", "FY",
                "date", "2025-12-31"));

        assertEquals("FY 2025", period);
    }

    @Test
    void resolveReportingPeriodFallsBackToFyWhenPeriodMissing() {
        String period = service.resolveReportingPeriod(Map.of(
                "acceptedDate", "2026-01-29 16:05:00"));

        assertEquals("FY 2026", period);
    }

    @Test
    void resolveReportingPeriodPrefersFiscalYearForQuarterlyFiling() {
        String period = service.resolveReportingPeriod(Map.of(
                "period", "Q1",
                "calendarYear", "2025",
                "fiscalYear", "2026",
                "date", "2025-12-27"));

        assertEquals("Q1 2026", period);
    }

    @Test
    void resolveReportingPeriodDerivesFiscalYearForQ1LateCalendarQuarter() {
        String period = service.resolveReportingPeriod(Map.of(
                "period", "Q1",
                "calendarYear", "2025",
                "date", "2025-12-27"));

        assertEquals("Q1 2026", period);
    }

    @Test
    void resolveFilingDateTrimsAcceptedDateTimestamp() {
        String filingDate = service.resolveFilingDate(Map.of(
                "acceptedDate", "2026-01-29 16:05:00"));

        assertEquals("2026-01-29", filingDate);
    }

    @Test
    void getBigDecimalValueParsesNumericStringsAndRejectsGarbage() {
        BigDecimal parsed = service.getBigDecimalValue(Map.of("revenue", "12345.67"), "revenue");
        BigDecimal missing = service.getBigDecimalValue(Map.of("revenue", "N/A"), "revenue");

        assertEquals(new BigDecimal("12345.67"), parsed);
        assertNull(missing);
    }

    @Test
    void extractYearAndFirstNonBlankHandleEmptyInputs() {
        assertEquals("2025", service.extractYear("2025-12-31"));
        assertEquals("", service.extractYear(""));
        assertEquals("Tesla", service.firstNonBlank("", " Tesla ", "TSLA"));
        assertEquals("", service.firstNonBlank("", " "));
    }

    @Test
    void fetchTimeoutDoesNotBlockForever() {
        FmpFinancialDataService service = testService(
                newStubClient(Map.of(
                        "/income-statement?symbol=TSLA&period=annual&limit=5&apikey=demo-key",
                        stubJsonDelayed(200, "[]", Duration.ofSeconds(2)))),
                newStubClient(Map.of()),
                1);

        long start = System.nanoTime();
        FinancialFacts facts = service.getFinancialFacts("TSLA");
        long elapsedMillis = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start);

        assertNull(facts);
        assertTrue(elapsedMillis < 1_900, "expected timeout-backed return, got " + elapsedMillis + " ms");
    }

    @Test
    void ratioEndpointFailureDoesNotKillFullAnalysisFacts() {
        Map<String, StubResponse> fmpResponses = new HashMap<>();
        fmpResponses.put("/income-statement?symbol=TSLA&period=annual&limit=5&apikey=demo-key", stubJson(200, """
                    [{
                      "companyName":"Tesla, Inc.",
                      "period":"FY",
                      "calendarYear":"2025",
                      "date":"2025-12-31",
                      "revenue":94827000000,
                      "costOfRevenue":77730000000,
                      "grossProfit":17097000000,
                      "researchAndDevelopmentExpenses":4500000000,
                      "sellingGeneralAndAdministrativeExpenses":8200000000,
                      "operatingIncome":4355000000,
                      "netIncome":3794000000,
                      "epsdiluted":1.22
                    },{
                      "companyName":"Tesla, Inc.",
                      "period":"FY",
                      "calendarYear":"2024",
                      "date":"2024-12-31",
                      "revenue":97600000000,
                      "costOfRevenue":80700000000,
                      "grossProfit":16900000000,
                      "researchAndDevelopmentExpenses":4200000000,
                      "sellingGeneralAndAdministrativeExpenses":7800000000,
                      "operatingIncome":7100000000,
                      "netIncome":5500000000,
                      "epsdiluted":1.70
                    }]
                    """));
        fmpResponses.put("/balance-sheet-statement?symbol=TSLA&period=annual&limit=1&apikey=demo-key", stubJson(200, """
                    [{
                      "period":"FY",
                      "calendarYear":"2025",
                      "cashAndCashEquivalents":16510000000,
                      "totalCurrentAssets":59630000000,
                      "totalAssets":137806000000,
                      "totalCurrentLiabilities":28990000000,
                      "longTermDebt":8180000000,
                      "totalLiabilities":54941000000,
                      "totalStockholdersEquity":82865000000
                    }]
                    """));
        fmpResponses.put("/cash-flow-statement?symbol=TSLA&period=annual&limit=5&apikey=demo-key", stubJson(200, """
                    [{
                      "period":"FY",
                      "calendarYear":"2025",
                      "netIncome":3794000000,
                      "depreciationAndAmortization":5100000000,
                      "operatingCashFlow":14747000000,
                      "capitalExpenditure":8527000000
                    },{
                      "period":"FY",
                      "calendarYear":"2024",
                      "netIncome":5500000000,
                      "depreciationAndAmortization":4700000000,
                      "operatingCashFlow":14923000000,
                      "capitalExpenditure":11341000000
                    }]
                    """));

        FmpFinancialDataService service = testService(
                newStubClient(fmpResponses),
                newStubClient(Map.of(
                        "/stable/ratios?symbol=TSLA&period=annual&limit=1&apikey=demo-key",
                        stubJson(500, "boom"))),
                1);

        FinancialFacts facts = service.getFinancialFacts("TSLA");

        assertNotNull(facts);
        assertEquals("Tesla, Inc.", facts.getCompanyName());
        assertEquals("FY 2025", facts.getPeriod());
        assertEquals("2025-12-31", facts.getFilingDate());
        assertNull(facts.getPriceToEarningsRatio());
        assertNull(facts.getPriceToBookRatio());
        assertNotNull(facts.getRevenue());
    }

    @Test
    void getFinancialFactsSupportsQuarterlyMode() {
        Map<String, StubResponse> fmpResponses = new HashMap<>();
        fmpResponses.put("/income-statement?symbol=TSLA&period=quarter&limit=5&apikey=demo-key", stubJson(200, """
                    [{
                      "companyName":"Tesla, Inc.",
                      "period":"Q1",
                      "calendarYear":"2026",
                      "date":"2026-03-31",
                      "revenue":25000000000,
                      "costOfRevenue":20000000000,
                      "grossProfit":5000000000,
                      "researchAndDevelopmentExpenses":1200000000,
                      "sellingGeneralAndAdministrativeExpenses":1800000000,
                      "operatingIncome":2000000000,
                      "netIncome":1500000000,
                      "epsdiluted":0.45
                    },{
                      "companyName":"Tesla, Inc.",
                      "period":"Q1",
                      "calendarYear":"2025",
                      "date":"2025-03-31",
                      "revenue":23000000000,
                      "costOfRevenue":18800000000,
                      "grossProfit":4200000000,
                      "researchAndDevelopmentExpenses":1100000000,
                      "sellingGeneralAndAdministrativeExpenses":1700000000,
                      "operatingIncome":1400000000,
                      "netIncome":1100000000,
                      "epsdiluted":0.35
                    }]
                    """));
        fmpResponses.put("/balance-sheet-statement?symbol=TSLA&period=quarter&limit=1&apikey=demo-key", stubJson(200, """
                    [{
                      "period":"Q1",
                      "calendarYear":"2026",
                      "cashAndCashEquivalents":15000000000,
                      "totalCurrentAssets":58000000000,
                      "totalAssets":136000000000,
                      "totalCurrentLiabilities":29000000000,
                      "longTermDebt":8000000000,
                      "totalLiabilities":54000000000,
                      "totalStockholdersEquity":82000000000
                    }]
                    """));
        fmpResponses.put("/cash-flow-statement?symbol=TSLA&period=quarter&limit=5&apikey=demo-key", stubJson(200, """
                    [{
                      "period":"Q1",
                      "calendarYear":"2026",
                      "netIncome":1500000000,
                      "depreciationAndAmortization":1200000000,
                      "operatingCashFlow":3200000000,
                      "capitalExpenditure":1600000000
                    },{
                      "period":"Q1",
                      "calendarYear":"2025",
                      "netIncome":1100000000,
                      "depreciationAndAmortization":1000000000,
                      "operatingCashFlow":2600000000,
                      "capitalExpenditure":1400000000
                    }]
                    """));

        FmpFinancialDataService service = testService(
                newStubClient(fmpResponses),
                newStubClient(Map.of(
                        "/stable/ratios?symbol=TSLA&period=annual&limit=1&apikey=demo-key",
                        stubJson(200, """
                                    [{
                                      "priceToEarningsRatio":40.5,
                                      "priceToBookRatio":9.2
                                    }]
                                """))),
                1);

        FinancialFacts facts = service.getFinancialFacts("TSLA", "quarterly");

        assertNotNull(facts);
        assertEquals("Q1 2026", facts.getPeriod());
        assertEquals("2026-03-31", facts.getFilingDate());
        assertEquals(new BigDecimal("40.5"), facts.getPriceToEarningsRatio());
    }

    @Test
    void quarterlyModeUsesAnnualRatiosEndpointToAvoidPremiumQuarterPlanGate() {
        Map<String, StubResponse> fmpResponses = new HashMap<>();
        fmpResponses.put("/income-statement?symbol=TSLA&period=quarter&limit=5&apikey=demo-key", stubJson(200, """
                    [{
                      "companyName":"Tesla, Inc.",
                      "period":"Q1",
                      "calendarYear":"2026",
                      "date":"2026-03-31",
                      "revenue":25000000000,
                      "costOfRevenue":20000000000,
                      "grossProfit":5000000000,
                      "researchAndDevelopmentExpenses":1200000000,
                      "sellingGeneralAndAdministrativeExpenses":1800000000,
                      "operatingIncome":2000000000,
                      "netIncome":1500000000,
                      "epsdiluted":0.45
                    }]
                    """));
        fmpResponses.put("/balance-sheet-statement?symbol=TSLA&period=quarter&limit=1&apikey=demo-key", stubJson(200, """
                    [{
                      "period":"Q1",
                      "calendarYear":"2026",
                      "cashAndCashEquivalents":15000000000,
                      "totalCurrentAssets":58000000000,
                      "totalAssets":136000000000,
                      "totalCurrentLiabilities":29000000000,
                      "longTermDebt":8000000000,
                      "totalLiabilities":54000000000,
                      "totalStockholdersEquity":82000000000
                    }]
                    """));
        fmpResponses.put("/cash-flow-statement?symbol=TSLA&period=quarter&limit=5&apikey=demo-key", stubJson(200, """
                    [{
                      "period":"Q1",
                      "calendarYear":"2026",
                      "netIncome":1500000000,
                      "depreciationAndAmortization":1200000000,
                      "operatingCashFlow":3200000000,
                      "capitalExpenditure":1600000000
                    }]
                    """));

        FmpFinancialDataService service = testService(
                newStubClient(fmpResponses),
                newStubClient(Map.of(
                        "/stable/ratios?symbol=TSLA&period=annual&limit=1&apikey=demo-key",
                        stubJson(200, """
                                    [{
                                      "priceToEarningsRatio":31.2,
                                      "priceToBookRatio":7.8
                                    }]
                                """))),
                1);

        FinancialFacts facts = service.getFinancialFacts("TSLA", "quarterly");

        assertNotNull(facts);
        assertEquals(new BigDecimal("31.2"), facts.getPriceToEarningsRatio());
        assertEquals(new BigDecimal("7.8"), facts.getPriceToBookRatio());
    }

    @Test
    void getHistoricalDataSupportsQuarterlyMode() {
        FmpFinancialDataService service = testService(
                newStubClient(Map.of(
                        "/income-statement?symbol=TSLA&period=quarter&limit=5&apikey=demo-key",
                        stubJson(200, """
                                    [{
                                      "period":"Q1",
                                      "calendarYear":"2026",
                                      "revenue":25000000000,
                                      "grossProfit":5000000000,
                                      "operatingIncome":2000000000,
                                      "netIncome":1500000000
                                    },{
                                      "period":"Q4",
                                      "calendarYear":"2025",
                                      "revenue":24000000000,
                                      "grossProfit":4800000000,
                                      "operatingIncome":1800000000,
                                      "netIncome":1300000000
                                    }]
                                """))),
                newStubClient(Map.of()),
                1);

        List<HistoricalDataPoint> history = service.getHistoricalData("TSLA", "quarterly");

        assertEquals(2, history.size());
        assertEquals("Q4 2025", history.get(0).getPeriod());
        assertEquals("Q1 2026", history.get(1).getPeriod());
    }

    @Test
    void cacheEntriesAreScopedByReportType() {
        StubCacheService cacheService = new StubCacheService();
        FinancialFacts annualFacts = FinancialFacts.builder().ticker("TSLA").period("FY 2025").build();
        FinancialFacts quarterlyFacts = FinancialFacts.builder().ticker("TSLA").period("Q1 2026").build();
        cacheService.annualFacts = Optional.of(annualFacts);
        cacheService.quarterlyFacts = Optional.of(quarterlyFacts);

        FmpFinancialDataService service = new FmpFinancialDataService(
                "https://example.com",
                List.of("demo-key"),
                new FinancialCalculator(),
                newStubClient(Map.of()),
                newStubClient(Map.of()),
                cacheService,
                1,
                Duration.ofHours(6),
                Duration.ofHours(24));

        assertSame(annualFacts, service.getFinancialFacts("TSLA", "annual"));
        assertSame(quarterlyFacts, service.getFinancialFacts("TSLA", "quarterly"));
    }

    @Test
    void staleQuarterlyCacheLabelIsBypassedWhenFiscalYearCanBeDerivedFromFilingDate() {
        FinancialFacts staleQuarterlyFacts = FinancialFacts.builder()
                .ticker("AAPL")
                .period("Q1 2025")
                .filingDate("2025-12-27")
                .build();

        assertTrue(service.shouldBypassCachedFacts(staleQuarterlyFacts, "quarterly"));
        assertFalse(service.shouldBypassCachedFacts(staleQuarterlyFacts, "annual"));
    }

    @Test
    void rotatesToNextApiKeyWhenCurrentKeyHitsQuota() {
        Map<String, StubResponse> fmpResponses = new HashMap<>();
        fmpResponses.put("/income-statement?symbol=TSLA&period=annual&limit=5&apikey=bad-key", stubJson(429,
                "{\"error\":\"API calls per day limit reached\"}"));
        fmpResponses.put("/income-statement?symbol=TSLA&period=annual&limit=5&apikey=good-key", stubJson(200, """
                    [{
                      "companyName":"Tesla, Inc.",
                      "period":"FY",
                      "calendarYear":"2025",
                      "date":"2025-12-31",
                      "revenue":94827000000,
                      "costOfRevenue":77730000000,
                      "grossProfit":17097000000,
                      "researchAndDevelopmentExpenses":4500000000,
                      "sellingGeneralAndAdministrativeExpenses":8200000000,
                      "operatingIncome":4355000000,
                      "netIncome":3794000000,
                      "epsdiluted":1.22
                    }]
                    """));
        fmpResponses.put("/balance-sheet-statement?symbol=TSLA&period=annual&limit=1&apikey=good-key", stubJson(200,
                """
                            [{
                              "period":"FY",
                              "calendarYear":"2025",
                              "cashAndCashEquivalents":16510000000,
                              "totalCurrentAssets":59630000000,
                              "totalAssets":137806000000,
                              "totalCurrentLiabilities":28990000000,
                              "longTermDebt":8180000000,
                              "totalLiabilities":54941000000,
                              "totalStockholdersEquity":82865000000
                            }]
                        """));
        fmpResponses.put("/cash-flow-statement?symbol=TSLA&period=annual&limit=5&apikey=good-key", stubJson(200, """
                    [{
                      "period":"FY",
                      "calendarYear":"2025",
                      "netIncome":3794000000,
                      "depreciationAndAmortization":5100000000,
                      "operatingCashFlow":14747000000,
                      "capitalExpenditure":8527000000
                    }]
                    """));

        FmpFinancialDataService service = new FmpFinancialDataService(
                "https://example.com",
                List.of("bad-key", "good-key"),
                new FinancialCalculator(),
                newStubClient(fmpResponses),
                newStubClient(Map.of()),
                null,
                1,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("TSLA");

        assertNotNull(facts);
        assertEquals("Tesla, Inc.", facts.getCompanyName());
    }

    @Test
    void quotaExceededFallsBackToStaleCachedFacts() {
        StubCacheService cacheService = new StubCacheService();
        FinancialFacts staleFacts = FinancialFacts.builder()
                .ticker("TSLA")
                .companyName("Tesla, Inc.")
                .period("FY 2024")
                .revenue(new BigDecimal("1"))
                .build();
        cacheService.anyFacts = Optional.of(staleFacts);

        FmpFinancialDataService service = new FmpFinancialDataService(
                "https://example.com",
                List.of("quota-key"),
                new FinancialCalculator(),
                newStubClient(Map.of(
                        "/income-statement?symbol=TSLA&period=annual&limit=5&apikey=quota-key",
                        stubJson(429, "{\"error\":\"API calls per day limit reached\"}"))),
                newStubClient(Map.of()),
                cacheService,
                1,
                Duration.ofHours(6),
                Duration.ofHours(24));

        FinancialFacts facts = service.getFinancialFacts("TSLA");

        assertSame(staleFacts, facts);
    }

    private FmpFinancialDataService testService(WebClient fmpClient, WebClient ratiosClient, int timeoutSeconds) {
        return new FmpFinancialDataService(
                "https://example.com",
                "demo-key",
                new FinancialCalculator(),
                fmpClient,
                ratiosClient,
                timeoutSeconds);
    }

    private WebClient newStubClient(Map<String, StubResponse> routes) {
        ExchangeFunction exchangeFunction = request -> {
            StubResponse response = routes.get(request.url().getPath() +
                    (request.url().getQuery() == null ? "" : "?" + request.url().getQuery()));
            if (response == null) {
                return Mono.just(ClientResponse.create(HttpStatusCode.valueOf(404)).build());
            }

            Mono<ClientResponse> result = Mono.just(ClientResponse.create(HttpStatusCode.valueOf(response.status()))
                    .header("Content-Type", "application/json")
                    .body(response.body())
                    .build());
            if (!response.delay().isZero()) {
                return result.delaySubscription(response.delay());
            }
            return result;
        };
        return WebClient.builder().baseUrl("https://example.com").exchangeFunction(exchangeFunction).build();
    }

    private static StubResponse stubJson(int status, String body) {
        return new StubResponse(status, body, Duration.ZERO);
    }

    private static StubResponse stubJsonDelayed(int status, String body, Duration delay) {
        return new StubResponse(status, body, delay);
    }

    private record StubResponse(int status, String body, Duration delay) {
    }

    private static final class StubCacheService extends MarketDataCacheService {
        private Optional<FinancialFacts> freshFacts = Optional.empty();
        private Optional<FinancialFacts> anyFacts = Optional.empty();
        private Optional<FinancialFacts> annualFacts = Optional.empty();
        private Optional<FinancialFacts> quarterlyFacts = Optional.empty();

        private StubCacheService() {
            super(null, new ObjectMapper());
        }

        @Override
        public Optional<FinancialFacts> getFinancialFacts(String ticker, boolean includeExpired) {
            return includeExpired ? anyFacts : freshFacts;
        }

        @Override
        public Optional<FinancialFacts> getFinancialFacts(String ticker, String reportType, boolean includeExpired) {
            if (includeExpired && anyFacts.isPresent()) {
                return anyFacts;
            }
            return "quarterly".equalsIgnoreCase(reportType) ? quarterlyFacts : annualFacts.or(() -> freshFacts);
        }

        @Override
        public void putFinancialFacts(String ticker, FinancialFacts facts, Duration ttl) {
        }

        @Override
        public Optional<List<HistoricalDataPoint>> getHistoricalData(String ticker, boolean includeExpired) {
            return Optional.of(Collections.emptyList());
        }

        @Override
        public Optional<List<HistoricalDataPoint>> getHistoricalData(String ticker, String reportType,
                boolean includeExpired) {
            return Optional.of(Collections.emptyList());
        }

        @Override
        public void putHistoricalData(String ticker, List<HistoricalDataPoint> historyData, Duration ttl) {
        }
    }
}
