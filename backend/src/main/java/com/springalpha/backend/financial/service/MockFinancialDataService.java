package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.calculator.FinancialCalculator;
import com.springalpha.backend.financial.model.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;

/**
 * Mock Financial Data Service - Provides hardcoded financial data for initial
 * validation.
 * This will be replaced with real XBRL parsing in future iterations.
 * 
 * Currently supports: AAPL, MSFT, TSLA
 */
@Service
public class MockFinancialDataService implements FinancialDataService {

        private static final Logger log = LoggerFactory.getLogger(MockFinancialDataService.class);
        private final FinancialCalculator calculator;
        private final Map<String, FinancialFacts> mockData;

        public MockFinancialDataService(FinancialCalculator calculator) {
                this.calculator = calculator;
                this.mockData = new HashMap<>();
                initializeMockData();
        }

        /**
         * Get financial facts for a given ticker.
         * Returns null if ticker is not supported.
         */
        @Override
        public FinancialFacts getFinancialFacts(String ticker) {
                String upperTicker = ticker.toUpperCase();
                FinancialFacts facts = mockData.get(upperTicker);

                if (facts == null) {
                        log.warn("🚫 Ticker {} not found in mock data. Supported: {}", ticker, mockData.keySet());
                } else {
                        log.info("✅ Retrieved mock financial data for {}", ticker);
                }

                return facts;
        }

        /**
         * Check if a ticker is supported
         */
        @Override
        public boolean isSupported(String ticker) {
                return mockData.containsKey(ticker.toUpperCase());
        }

        /**
         * Get list of supported tickers
         */
        @Override
        public String[] getSupportedTickers() {
                return mockData.keySet().toArray(new String[0]);
        }

        private void initializeMockData() {
                // AAPL Q4 2024 data (approximate based on real filings)
                mockData.put("AAPL", createAppleQ4_2024());

                // MSFT Q2 FY2024 data
                mockData.put("MSFT", createMicrosoftQ2_FY2024());

                // TSLA Q3 2024 data
                mockData.put("TSLA", createTeslaQ3_2024());

                log.info("🎯 Initialized mock financial data for: {}", mockData.keySet());
        }

        private FinancialFacts createAppleQ4_2024() {
                // Q4 2024 (FY2024) - Current period
                // AAPL Q4 2024
                IncomeStatement currentIncome = IncomeStatement.builder()
                                .period("Q4 2024")
                                .revenue(new BigDecimal("94930000000")) // $94.93B
                                .costOfRevenue(new BigDecimal("52300000000"))
                                .grossProfit(new BigDecimal("42630000000"))
                                .researchAndDevelopment(new BigDecimal("8100000000"))
                                .sellingGeneralAndAdministrative(new BigDecimal("6500000000"))
                                .operatingIncome(new BigDecimal("28030000000"))
                                .netIncome(new BigDecimal("22956000000")) // $22.96B
                                .earningsPerShareDiluted(new BigDecimal("1.46")) // Added EPS
                                .build();

                // ... (previous year income skipped for brevity in replace, ensure context
                // matches)

                // Q4 2023 - Previous year for YoY comparison
                IncomeStatement previousIncome = IncomeStatement.builder()
                                .period("Q4 2023")
                                .revenue(new BigDecimal("89498000000")) // $89.50B
                                .costOfRevenue(new BigDecimal("49370000000"))
                                .grossProfit(new BigDecimal("40128000000"))
                                .operatingIncome(new BigDecimal("26350000000"))
                                .netIncome(new BigDecimal("22956000000"))
                                .build();

                BalanceSheet currentBalance = BalanceSheet.builder()
                                .period("Q4 2024")
                                .cashAndCashEquivalents(new BigDecimal("30740000000"))
                                .totalCurrentAssets(new BigDecimal("143566000000"))
                                .totalAssets(new BigDecimal("365730000000"))
                                .totalCurrentLiabilities(new BigDecimal("176620000000"))
                                .longTermDebt(new BigDecimal("106630000000"))
                                .totalLiabilities(new BigDecimal("308030000000"))
                                .totalEquity(new BigDecimal("57700000000"))
                                .build();

                CashFlowStatement currentCashFlow = CashFlowStatement.builder()
                                .period("Q4 2024")
                                .netIncome(new BigDecimal("22956000000"))
                                .depreciationAndAmortization(new BigDecimal("3050000000"))
                                .operatingCashFlow(new BigDecimal("31200000000"))
                                .capitalExpenditures(new BigDecimal("-2910000000"))
                                .build();

                CashFlowStatement previousCashFlow = CashFlowStatement.builder()
                                .period("Q4 2023")
                                .operatingCashFlow(new BigDecimal("29540000000"))
                                .capitalExpenditures(new BigDecimal("-2710000000"))
                                .build();

                return calculator.buildFinancialFacts(
                                "AAPL",
                                "Apple Inc.",
                                "Q4 2024",
                                currentIncome,
                                currentBalance,
                                currentCashFlow,
                                previousIncome,
                                previousCashFlow);
        }

        private FinancialFacts createMicrosoftQ2_FY2024() {
                IncomeStatement currentIncome = IncomeStatement.builder()
                                .period("Q2 FY2024")
                                .revenue(new BigDecimal("62020000000")) // $62.02B
                                .costOfRevenue(new BigDecimal("19310000000"))
                                .grossProfit(new BigDecimal("42710000000"))
                                .operatingIncome(new BigDecimal("27030000000"))
                                .netIncome(new BigDecimal("21870000000"))
                                .earningsPerShareDiluted(new BigDecimal("2.93"))
                                .build();

                IncomeStatement previousIncome = IncomeStatement.builder()
                                .period("Q2 FY2023")
                                .revenue(new BigDecimal("52747000000"))
                                .grossProfit(new BigDecimal("36266000000"))
                                .operatingIncome(new BigDecimal("20399000000"))
                                .netIncome(new BigDecimal("16425000000"))
                                .build();

                BalanceSheet currentBalance = BalanceSheet.builder()
                                .period("Q2 FY2024")
                                .totalAssets(new BigDecimal("411976000000"))
                                .totalLiabilities(new BigDecimal("198298000000"))
                                .totalEquity(new BigDecimal("213678000000"))
                                .build();

                CashFlowStatement currentCashFlow = CashFlowStatement.builder()
                                .period("Q2 FY2024")
                                .operatingCashFlow(new BigDecimal("33740000000"))
                                .capitalExpenditures(new BigDecimal("-8950000000"))
                                .build();

                CashFlowStatement previousCashFlow = CashFlowStatement.builder()
                                .period("Q2 FY2023")
                                .operatingCashFlow(new BigDecimal("28523000000"))
                                .build();

                return calculator.buildFinancialFacts(
                                "MSFT",
                                "Microsoft Corporation",
                                "Q2 FY2024",
                                currentIncome,
                                currentBalance,
                                currentCashFlow,
                                previousIncome,
                                previousCashFlow);
        }

        private FinancialFacts createTeslaQ3_2024() {
                IncomeStatement currentIncome = IncomeStatement.builder()
                                .period("Q3 2024")
                                .revenue(new BigDecimal("25182000000")) // $25.18B
                                .costOfRevenue(new BigDecimal("20340000000"))
                                .grossProfit(new BigDecimal("4842000000"))
                                .operatingIncome(new BigDecimal("1762000000"))
                                .netIncome(new BigDecimal("2167000000"))
                                .earningsPerShareDiluted(new BigDecimal("0.72"))
                                .build();

                IncomeStatement previousIncome = IncomeStatement.builder()
                                .period("Q3 2023")
                                .revenue(new BigDecimal("23350000000"))
                                .grossProfit(new BigDecimal("4178000000"))
                                .operatingIncome(new BigDecimal("1757000000"))
                                .netIncome(new BigDecimal("1853000000"))
                                .build();

                BalanceSheet currentBalance = BalanceSheet.builder()
                                .period("Q3 2024")
                                .totalAssets(new BigDecimal("123000000000"))
                                .totalLiabilities(new BigDecimal("54100000000"))
                                .totalEquity(new BigDecimal("68900000000"))
                                .build();

                CashFlowStatement currentCashFlow = CashFlowStatement.builder()
                                .period("Q3 2024")
                                .operatingCashFlow(new BigDecimal("6250000000"))
                                .capitalExpenditures(new BigDecimal("-3510000000"))
                                .build();

                CashFlowStatement previousCashFlow = CashFlowStatement.builder()
                                .period("Q3 2023")
                                .operatingCashFlow(new BigDecimal("3305000000"))
                                .build();

                return calculator.buildFinancialFacts(
                                "TSLA",
                                "Tesla, Inc.",
                                "Q3 2024",
                                currentIncome,
                                currentBalance,
                                currentCashFlow,
                                previousIncome,
                                previousCashFlow);
        }

        /**
         * Get historical data (Mock implementation)
         */
        @Override
        public java.util.List<com.springalpha.backend.financial.model.HistoricalDataPoint> getHistoricalData(
                        String ticker) {
                if (!"AAPL".equalsIgnoreCase(ticker)) {
                        return java.util.Collections.emptyList();
                }

                // Mock 5 quarters of margin data for AAPL
                java.util.List<com.springalpha.backend.financial.model.HistoricalDataPoint> history = new java.util.ArrayList<>();

                history.add(new com.springalpha.backend.financial.model.HistoricalDataPoint("Q4 2023",
                                new BigDecimal("0.452"), new BigDecimal("0.301"), new BigDecimal("0.253"),
                                new BigDecimal("119580000000"), new BigDecimal("33920000000")));
                history.add(new com.springalpha.backend.financial.model.HistoricalDataPoint("Q1 2024",
                                new BigDecimal("0.459"), new BigDecimal("0.307"), new BigDecimal("0.261"),
                                new BigDecimal("90750000000"), new BigDecimal("23640000000")));
                history.add(new com.springalpha.backend.financial.model.HistoricalDataPoint("Q2 2024",
                                new BigDecimal("0.466"), new BigDecimal("0.312"), new BigDecimal("0.265"),
                                new BigDecimal("85780000000"), new BigDecimal("21450000000")));
                history.add(new com.springalpha.backend.financial.model.HistoricalDataPoint("Q3 2024",
                                new BigDecimal("0.463"), new BigDecimal("0.298"), new BigDecimal("0.248"),
                                new BigDecimal("89500000000"), new BigDecimal("22960000000"))); // Dip
                history.add(new com.springalpha.backend.financial.model.HistoricalDataPoint("Q4 2024",
                                new BigDecimal("0.449"), new BigDecimal("0.295"), new BigDecimal("0.242"),
                                new BigDecimal("94930000000"), new BigDecimal("22960000000"))); // Current

                return history;
        }
}
