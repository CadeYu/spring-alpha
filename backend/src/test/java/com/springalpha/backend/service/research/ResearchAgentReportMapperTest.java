package com.springalpha.backend.service.research;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.ResearchTaskType;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

class ResearchAgentReportMapperTest {

    private final ResearchAgentReportMapper mapper = new ResearchAgentReportMapper();

    @Test
    void mapsPythonTaskSectionsIntoJavaTaskSpecificSections() {
        ResearchAgentResult result = new ResearchAgentResult(
                "run_java_001",
                ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
                "ok",
                List.of(new ResearchAgentEvent(
                        "run_java_001",
                        ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
                        "build_evidence_plan",
                        "ok",
                        "Plan next step.",
                        "search_filing_sections",
                        "tool",
                        "Business Analyst",
                        "test-model",
                        Map.of("query", "services demand"),
                        Map.of(),
                        0,
                        null)),
                List.of(),
                Map.of(
                        "company_name", "Apple Inc.",
                        "period", "FY2026 Q2",
                        "report_type", "quarterly",
                        "sections", Map.of("summary", "Business drivers improved."),
                        "task_sections", Map.of(
                                "schema_version", "task_sections.v1",
                                "task_type", "business_driver_deep_dive",
                                "coverage", Map.of(
                                        "status", "complete",
                                        "missing_sections", List.of(),
                                        "evidence_count", 1),
                                "driver_thesis", Map.of(
                                        "headline", "Services drove growth",
                                        "durability", "durable",
                                        "summary", "Services momentum appears durable."),
                                "driver_map", Map.of(
                                        "product", List.of(Map.of(
                                                "title", "Services",
                                                "summary", "Services revenue increased.",
                                                "evidence_refs", List.of(),
                                                "citation_status", "supported")),
                                        "segment", List.of(),
                                        "geography", List.of(),
                                        "demand", List.of(),
                                        "pricing", List.of(),
                                        "customer", List.of(),
                                        "strategy", List.of()),
                                "positive_signals", List.of(),
                                "negative_signals", List.of(),
                                "watchlist", List.of("Track Services adoption."))));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        assertNotNull(report.getTaskSections());
        assertEquals("task_sections.v1", report.getTaskSections().getSchemaVersion());
        assertEquals(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, report.getTaskSections().getTaskType());
        assertNotNull(report.getTaskSections().getBusinessDriver());
        assertEquals("Services drove growth",
                report.getTaskSections().getBusinessDriver().getDriverThesis().getHeadline());
        assertEquals("Services",
                report.getTaskSections().getBusinessDriver().getDriverMap().getProduct().get(0).getTitle());
        assertNotNull(report.getMetadata().getAgentEvents());
        assertEquals("build_evidence_plan", report.getMetadata().getAgentEvents().get(0).getPhase());
        assertEquals("Plan next step.", report.getMetadata().getAgentEvents().get(0).getSummary());
        assertEquals("tool", report.getMetadata().getAgentEvents().get(0).getEventKind());
        assertEquals("Business Analyst", report.getMetadata().getAgentEvents().get(0).getAgentName());
        assertEquals("test-model", report.getMetadata().getAgentEvents().get(0).getModelName());
        assertEquals("services demand",
                report.getMetadata().getAgentEvents().get(0).getToolInput().get("query"));
    }

    @Test
    void mapsCashFlowLlmSynthesisTaskSectionsIntoJavaContract() {
        Map<String, Object> sourceRef = Map.of(
                "section", "Liquidity and Capital Resources",
                "excerpt", "Operating cash flow funded repurchases and capital expenditures.",
                "filing_date", "2026-04-30",
                "accession_number", "0000320193-26-000003",
                "source_id", "cash_src_1");
        Map<String, Object> point = Map.of(
                "title", "Buybacks remained self-funded",
                "summary", "The company repurchased shares while operating cash flow stayed positive.",
                "evidence_refs", List.of(sourceRef),
                "citation_status", "supported");
        ResearchAgentResult result = new ResearchAgentResult(
                "run_cash_001",
                ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
                "ok",
                List.of(),
                List.of(),
                Map.of(
                        "company_name", "Apple Inc.",
                        "period", "FY2026 Q2",
                        "report_type", "quarterly",
                        "sections", Map.of("summary", "Cash conversion remained investable.", "synthesis", "llm"),
                        "task_sections", Map.of(
                                "schema_version", "task_sections.v1",
                                "task_type", "cash_flow_capital_allocation",
                                "coverage", Map.of(
                                        "status", "complete",
                                        "missing_sections", List.of(),
                                        "evidence_count", 2),
                                "cash_quality_verdict", Map.of(
                                        "headline", "Cash flow supports capital returns",
                                        "earnings_backed_by_cash", "mixed",
                                        "summary", "Operating cash flow covered core allocation needs."),
                                "cash_metrics", List.of(Map.of(
                                        "name", "Operating cash flow",
                                        "value", "positive",
                                        "period", "latest quarter",
                                        "interpretation", "Cash generation remained positive.",
                                        "evidence_refs", List.of(sourceRef),
                                        "citation_status", "supported")),
                                "capital_allocation", Map.of(
                                        "capex", List.of(point),
                                        "buybacks", List.of(point),
                                        "dividends", List.of(),
                                        "debt", List.of(),
                                        "liquidity", List.of(point)),
                                "allocation_discipline", List.of(point),
                                "red_flags", List.of(point)),
                        "claims", List.of(Map.of(
                                "source_refs", List.of(Map.of(
                                        "section", "Liquidity and Capital Resources",
                                        "snippet", "Operating cash flow funded repurchases.",
                                        "citation_status", "supported"))))));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        AnalysisReport.CashFlowCapitalAllocationSections cashFlow = report.getTaskSections()
                .getCashFlowCapitalAllocation();
        assertNotNull(cashFlow);
        assertEquals("Cash flow supports capital returns", cashFlow.getCashQualityVerdict().getHeadline());
        assertEquals("mixed", cashFlow.getCashQualityVerdict().getEarningsBackedByCash());
        assertEquals("Operating cash flow", cashFlow.getCashMetrics().get(0).getName());
        assertEquals("Liquidity and Capital Resources",
                cashFlow.getCashMetrics().get(0).getEvidenceRefs().get(0).getSection());
        assertEquals("Buybacks remained self-funded", cashFlow.getCapitalAllocation().getBuybacks().get(0).getTitle());
        assertEquals("Buybacks remained self-funded", cashFlow.getCapitalAllocation().getLiquidity().get(0).getTitle());
        assertEquals("Buybacks remained self-funded", cashFlow.getAllocationDiscipline().get(0).getTitle());
        assertEquals("Buybacks remained self-funded", cashFlow.getRedFlags().get(0).getTitle());
        assertEquals("VERIFIED", report.getCitations().get(0).getVerificationStatus());
    }

    @Test
    void mapsLatestEarningsLlmSynthesisTaskSectionsIntoJavaContract() {
        Map<String, Object> sourceRef = Map.of(
                "section", "Management Discussion and Analysis",
                "excerpt", "Revenue increased year over year while margins remained mixed.",
                "filing_date", "2026-04-30",
                "accession_number", "0000320193-26-000003",
                "source_id", "latest_src_1");
        Map<String, Object> point = Map.of(
                "title", "Revenue improved",
                "summary", "Revenue increased year over year.",
                "evidence_refs", List.of(sourceRef),
                "citation_status", "supported");
        ResearchAgentResult result = new ResearchAgentResult(
                "run_latest_001",
                ResearchTaskType.LATEST_EARNINGS_READOUT,
                "ok",
                List.of(),
                List.of(),
                Map.of(
                        "company_name", "Apple Inc.",
                        "period", "FY2026 Q2",
                        "report_type", "quarterly",
                        "sections", Map.of("summary", "Typed summary.", "synthesis", "llm"),
                        "task_sections", Map.of(
                                "schema_version", "task_sections.v1",
                                "task_type", "latest_earnings_readout",
                                "coverage", Map.of(
                                "status", "complete",
                                "missing_sections", List.of(),
                                "evidence_count", 3),
                                "company_profile", Map.of(
                                        "summary", "Apple Inc. designs devices, software, and services for a global installed base.",
                                        "evidence_refs", List.of(sourceRef),
                                        "citation_status", "supported"),
                                "topline_verdict", Map.of(
                                        "headline", "Revenue growth with mixed margin signals",
                                        "summary", "Revenue improved, but margin evidence was mixed.",
                                        "verdict", "mixed"),
                                "key_takeaways", List.of(point),
                                "financial_dashboard", Map.of(
                                        "metrics", List.of(Map.of(
                                                "name", "Revenue",
                                                "value", "higher year over year",
                                                "period", "latest quarter",
                                                "interpretation", "Topline improved.",
                                                "evidence_refs", List.of(sourceRef),
                                                "citation_status", "supported")),
                                        "chart_focus", List.of("revenue")),
                                "driver_snapshot", List.of(point),
                                "risk_snapshot", List.of(point)),
                        "claims", List.of(Map.of(
                                "source_refs", List.of(Map.of(
                                        "section", "Management Discussion and Analysis",
                                        "snippet", "Revenue increased year over year.",
                                        "citation_status", "supported"))))));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        AnalysisReport.LatestEarningsSections latest = report.getTaskSections().getLatestEarnings();
        assertNotNull(latest);
        assertEquals("Apple Inc. designs devices, software, and services for a global installed base.",
                latest.getCompanyProfile().getSummary());
        assertEquals("supported", latest.getCompanyProfile().getCitationStatus());
        assertEquals("Revenue growth with mixed margin signals", latest.getToplineVerdict().getHeadline());
        assertEquals("Revenue improved", latest.getKeyTakeaways().get(0).getTitle());
        assertEquals("Revenue", latest.getFinancialDashboard().getMetrics().get(0).getName());
        assertEquals("Revenue improved", latest.getDriverSnapshot().get(0).getTitle());
        assertEquals("Revenue improved", latest.getRiskSnapshot().get(0).getTitle());
        assertNotNull(report.getMetadata().getGeneratedAt());
        assertFalse(report.getMetadata().getGeneratedAt().isBlank());
        assertEquals("2026-04-30", report.getFilingDate());
        assertEquals("VERIFIED", report.getCitations().get(0).getVerificationStatus());
    }
}
