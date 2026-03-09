package com.springalpha.backend.financial.service;

import com.springalpha.backend.financial.calculator.FinancialCalculator;
import org.junit.jupiter.api.Test;

import java.math.BigDecimal;
import java.util.Map;

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
}
