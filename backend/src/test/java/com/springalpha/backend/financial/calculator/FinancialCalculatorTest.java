package com.springalpha.backend.financial.calculator;

import com.springalpha.backend.financial.model.FinancialFacts;
import com.springalpha.backend.financial.model.IncomeStatement;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class FinancialCalculatorTest {

    private final FinancialCalculator calculator = new FinancialCalculator();

    @Test
    void leavesGrowthMetricsNullWhenComparablePeriodIsUnavailable() {
        IncomeStatement currentIncome = IncomeStatement.builder()
                .reportedCurrency("USD")
                .revenue(new BigDecimal("14130000000"))
                .netIncome(new BigDecimal("2936000000"))
                .build();

        FinancialFacts facts = calculator.buildFinancialFacts(
                "ORCL",
                "Oracle Corporation",
                "Q3 2026",
                currentIncome,
                null,
                null,
                null,
                null);

        assertEquals(new BigDecimal("14130000000"), facts.getRevenue());
        assertEquals(new BigDecimal("2936000000"), facts.getNetIncome());
        assertNull(facts.getRevenueYoY());
        assertNull(facts.getGrossMargin());
        assertNull(facts.getOperatingMargin());
        assertEquals(new BigDecimal("0.2078"), facts.getNetMargin());
    }
}
