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
                                        "revenue_bridge", Map.of(
                                                "title", "Services",
                                                "summary", "Services revenue increased.",
                                                "evidence_refs", List.of(),
                                                "citation_status", "supported")))));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        assertNotNull(report.getTaskSections());
        assertEquals("task_sections.v1", report.getTaskSections().getSchemaVersion());
        assertEquals(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, report.getTaskSections().getTaskType());
        assertNotNull(report.getTaskSections().getBusinessDriver());
        assertEquals("Services drove growth",
                report.getTaskSections().getBusinessDriver().getDriverThesis().getHeadline());
        assertEquals("Services",
                report.getTaskSections().getBusinessDriver().getDriverMap().getRevenueBridge().getTitle());
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
    void filtersLowInformationBusinessDriverEvidenceRefsAtTheResponseBoundary() {
        Map<String, Object> cleanRef = Map.of(
                "section", "MD&A demand",
                "excerpt", "Online sales increased as customer demand improved.",
                "source_id", "src_clean");
        Map<String, Object> noisyRef = Map.of(
                "section", "Table of Contents",
                "excerpt",
                "23 Table of Contents International segment revenue mix percentages and comparable sales percentage changes by revenue category were as follows: | | | | | | | | | |---|---|---|",
                "source_id", "src_table");
        ResearchAgentResult result = new ResearchAgentResult(
                "run_java_002",
                ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
                "ok",
                List.of(),
                List.of(),
                List.of(),
                Map.of(
                        "company_name", "Best Buy Co.",
                        "sections", Map.of("summary", "Business drivers were mixed."),
                        "task_sections", Map.of(
                                "schema_version", "task_sections.v1",
                                "task_type", "business_driver_deep_dive",
                                "coverage", Map.of(
                                        "status", "partial",
                                        "missing_sections", List.of(),
                                        "evidence_count", 2),
                                "driver_thesis", Map.of(
                                        "headline", "Demand evidence is mixed",
                                        "durability", "mixed",
                                        "summary", "Demand evidence is mixed."),
                                "driver_map", Map.of(
                                        "segment_momentum", Map.of(
                                                "title", "Segment momentum",
                                                "summary", "Segment momentum has partial support.",
                                                "evidence_refs", List.of(cleanRef, noisyRef),
                                                "citation_status", "supported"),
                                        "demand_signals", Map.of(
                                                "title", "Demand signals",
                                                "summary", "Demand signals remain partial.",
                                                "evidence_refs", List.of(noisyRef),
                                                "citation_status", "supported")))));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        AnalysisReport.DriverMap driverMap = report.getTaskSections().getBusinessDriver().getDriverMap();
        assertNotNull(driverMap.getSegmentMomentum());
        assertEquals(1, driverMap.getSegmentMomentum().getEvidenceRefs().size());
        assertEquals("src_clean", driverMap.getSegmentMomentum().getEvidenceRefs().get(0).getSourceId());
        assertEquals("partial", driverMap.getSegmentMomentum().getCitationStatus());
        assertNotNull(driverMap.getDemandSignals());
        assertTrue(driverMap.getDemandSignals().getEvidenceRefs().isEmpty());
        assertEquals("unverified", driverMap.getDemandSignals().getCitationStatus());
    }

    @Test
    void filtersLowInformationTopLevelCitationsForAllResearchTasks() {
        ResearchAgentResult result = new ResearchAgentResult(
                "run_java_citations_001",
                ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
                "ok",
                List.of(),
                List.of(),
                List.of(),
                Map.of(
                        "company_name", "Microsoft Corp.",
                        "sections", Map.of("summary", "Cash flow remained supported by operating cash flow."),
                        "task_sections", Map.of(
                                "schema_version", "task_sections.v1",
                                "task_type", "cash_flow_capital_allocation",
                                "coverage", Map.of(
                                        "status", "complete",
                                        "missing_sections", List.of(),
                                        "evidence_count", 2),
                                "cash_quality_verdict", Map.of(
                                        "headline", "Cash conversion remains useful",
                                        "earnings_backed_by_cash", "yes",
                                        "summary", "Operating cash flow supported capital allocation."),
                                "cash_metrics", List.of(),
                                "capital_allocation", Map.of(
                                        "capex", List.of(),
                                        "buybacks", List.of(),
                                        "dividends", List.of(),
                                        "debt", List.of(),
                                        "liquidity", List.of()),
                                "allocation_discipline", List.of(),
                                "red_flags", List.of()),
                        "claims", List.of(Map.of(
                                "source_refs", List.of(
                                        Map.of(
                                                "section", "Liquidity and Capital Resources",
                                                "snippet", "Operating cash flow funded investments and shareholder returns.",
                                                "citation_status", "supported"),
                                        Map.of(
                                                "section", "Table of Contents",
                                                "snippet",
                                                "23 Table of Contents Cash flow table | | | 6,402 | | | 15,509 | | | ---|---",
                                                "citation_status", "supported"))))));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        assertEquals(1, report.getCitations().size());
        assertEquals("Liquidity and Capital Resources", report.getCitations().get(0).getSection());
        assertEquals("Operating cash flow funded investments and shareholder returns.",
                report.getCitations().get(0).getExcerpt());
        assertEquals("VERIFIED", report.getCitations().get(0).getVerificationStatus());
    }

    @Test
    void filtersLowInformationTypedLatestEarningsEvidenceRefsAtTheResponseBoundary() {
        Map<String, Object> cleanRef = Map.of(
                "section", "Management Discussion and Analysis",
                "excerpt", "Revenue increased because product and services demand improved.",
                "source_id", "src_clean");
        Map<String, Object> noisyRef = Map.of(
                "section", "Net sales table",
                "excerpt", "976 | | | 26,645 | | | 60,989 | | | Total net sales | 111,184 | | |",
                "source_id", "src_table");
        Map<String, Object> point = Map.of(
                "title", "Revenue improved",
                "summary", "Revenue increased because demand improved.",
                "evidence_refs", List.of(cleanRef, noisyRef),
                "citation_status", "supported");
        ResearchAgentResult result = new ResearchAgentResult(
                "run_java_latest_refs_001",
                ResearchTaskType.LATEST_EARNINGS_READOUT,
                "ok",
                List.of(),
                List.of(),
                List.of(),
                Map.of(
                        "company_name", "Apple Inc.",
                        "sections", Map.of("summary", "Revenue improved and margins were mixed."),
                        "task_sections", Map.ofEntries(
                                Map.entry("schema_version", "task_sections.v1"),
                                Map.entry("task_type", "latest_earnings_readout"),
                                Map.entry("coverage", Map.of(
                                        "status", "complete",
                                        "missing_sections", List.of(),
                                        "evidence_count", 2)),
                                Map.entry("topline_verdict", Map.of(
                                        "headline", "Revenue improved",
                                        "summary", "Revenue improved and margins were mixed.",
                                        "verdict", "mixed")),
                                Map.entry("key_takeaways", List.of(point)),
                                Map.entry("financial_dashboard", Map.of(
                                        "metrics", List.of(Map.of(
                                                "name", "Revenue",
                                                "value", "$111.2B",
                                                "interpretation", "Revenue improved.",
                                                "evidence_refs", List.of(cleanRef, noisyRef),
                                                "citation_status", "supported")),
                                        "chart_focus", List.of("revenue"))),
                                Map.entry("driver_snapshot", List.of(point)),
                                Map.entry("risk_snapshot", List.of()),
                                Map.entry("quality_of_quarter", Map.of("growth_quality", point)),
                                Map.entry("drivers_and_draggers", Map.of(
                                        "drivers", List.of(point),
                                        "draggers", List.of())),
                                Map.entry("bull_bear_read", Map.of(
                                        "bull_case", List.of(point),
                                        "bear_case", List.of(),
                                        "balanced_read", point)),
                                Map.entry("watch_next", List.of(Map.of(
                                        "title", "Watch revenue",
                                        "metric", "Revenue",
                                        "why_it_matters", "Revenue trend confirms demand.",
                                        "evidence_refs", List.of(cleanRef, noisyRef),
                                        "citation_status", "supported"))))));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        AnalysisReport.LatestEarningsSections latest = report.getTaskSections().getLatestEarnings();
        assertEquals(1, latest.getKeyTakeaways().get(0).getEvidenceRefs().size());
        assertEquals("src_clean", latest.getKeyTakeaways().get(0).getEvidenceRefs().get(0).getSourceId());
        assertEquals("partial", latest.getKeyTakeaways().get(0).getCitationStatus());
        assertEquals(1, latest.getFinancialDashboard().getMetrics().get(0).getEvidenceRefs().size());
        assertEquals("partial", latest.getFinancialDashboard().getMetrics().get(0).getCitationStatus());
        assertEquals(1, latest.getWatchNext().get(0).getEvidenceRefs().size());
        assertEquals("partial", latest.getWatchNext().get(0).getCitationStatus());
    }

    @Test
    void filtersLowInformationTypedCashFlowEvidenceRefsAtTheResponseBoundary() {
        Map<String, Object> cleanRef = Map.of(
                "section", "Liquidity and Capital Resources",
                "excerpt", "Operating cash flow funded capital expenditures and dividends.",
                "source_id", "src_clean");
        Map<String, Object> noisyRef = Map.of(
                "section", "Cash flow table",
                "excerpt", "489 | | | Common stock repurchased | | | (4,627 | ) | | | Dividends paid | | |",
                "source_id", "src_table");
        Map<String, Object> point = Map.of(
                "title", "Buybacks used cash",
                "summary", "Capital returns were funded by operating cash flow.",
                "evidence_refs", List.of(cleanRef, noisyRef),
                "citation_status", "supported");
        ResearchAgentResult result = new ResearchAgentResult(
                "run_java_cash_refs_001",
                ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
                "ok",
                List.of(),
                List.of(),
                List.of(),
                Map.of(
                        "company_name", "Microsoft Corp.",
                        "sections", Map.of("summary", "Cash flow supported capital allocation."),
                        "task_sections", Map.of(
                                "schema_version", "task_sections.v1",
                                "task_type", "cash_flow_capital_allocation",
                                "coverage", Map.of(
                                        "status", "complete",
                                        "missing_sections", List.of(),
                                        "evidence_count", 2),
                                "cash_quality_verdict", Map.of(
                                        "headline", "Cash conversion remains useful",
                                        "earnings_backed_by_cash", "yes",
                                        "summary", "Operating cash flow supported capital allocation."),
                                "cash_metrics", List.of(Map.of(
                                        "name", "Operating cash flow",
                                        "value", "$30.0B",
                                        "interpretation", "Operating cash flow funded allocation.",
                                        "evidence_refs", List.of(cleanRef, noisyRef),
                                        "citation_status", "supported")),
                                "capital_allocation", Map.of(
                                        "capex", List.of(),
                                        "buybacks", List.of(point),
                                        "dividends", List.of(point),
                                        "debt", List.of(),
                                        "liquidity", List.of()),
                                "allocation_discipline", List.of(point),
                                "red_flags", List.of())));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        AnalysisReport.CashFlowCapitalAllocationSections cashFlow = report.getTaskSections()
                .getCashFlowCapitalAllocation();
        assertEquals(1, cashFlow.getCashMetrics().get(0).getEvidenceRefs().size());
        assertEquals("partial", cashFlow.getCashMetrics().get(0).getCitationStatus());
        assertEquals(1, cashFlow.getCapitalAllocation().getBuybacks().get(0).getEvidenceRefs().size());
        assertEquals("partial", cashFlow.getCapitalAllocation().getBuybacks().get(0).getCitationStatus());
        assertEquals(1, cashFlow.getAllocationDiscipline().get(0).getEvidenceRefs().size());
        assertEquals("partial", cashFlow.getAllocationDiscipline().get(0).getCitationStatus());
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
    void mapsDegradedResultWithoutFinalReportIntoTransparentAnalysisReport() {
        ResearchAgentResult result = new ResearchAgentResult(
                "run_degraded_001",
                ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
                "degraded",
                List.of(new ResearchAgentEvent(
                        "run_degraded_001",
                        ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
                        "degraded",
                        "degraded",
                        "Cash flow research agent failed.",
                        null,
                        "reasoning",
                        "Cash Flow Analyst",
                        "test-model",
                        Map.of(),
                        Map.of(),
                        0,
                        "Cash flow research agent failed: validation error")),
                List.of("Cash flow research agent failed: validation error"),
                List.of(),
                null);

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        assertEquals("Cash flow research agent failed: validation error", report.getExecutiveSummary());
        assertEquals("DEGRADED", report.getSourceContext().getStatus());
        assertEquals("Cash flow research agent failed: validation error",
                report.getSourceContext().getMessage());
        assertNull(report.getTaskSections());
        assertEquals("degraded", report.getMetadata().getAgentEvents().get(0).getPhase());
        assertEquals("Cash flow research agent failed: validation error",
                report.getMetadata().getAgentEvents().get(0).getDegradedReason());
    }

    @Test
    void mapsCompletedReportWithPartialEvidenceAsLimitedSourceContext() {
        ResearchAgentResult result = new ResearchAgentResult(
                "run_limited_001",
                ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
                "ok",
                List.of(new ResearchAgentEvent(
                        "run_limited_001",
                        ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
                        "collect_financial_facts",
                        "partial",
                        "Collected partial company facts.",
                        "get_company_facts",
                        "tool",
                        "Cash Flow Analyst",
                        "test-model",
                        Map.of("metrics", List.of("operating cash flow", "buybacks")),
                        Map.of(),
                        0,
                        "SEC company facts missing metrics: buybacks")),
                List.of("SEC company facts missing metrics: buybacks"),
                List.of(),
                Map.of(
                        "company_name", "Apple Inc.",
                        "sections", Map.of("summary", "Cash report completed with limited evidence."),
                        "task_sections", Map.of(
                                "schema_version", "task_sections.v1",
                                "task_type", "cash_flow_capital_allocation",
                                "coverage", Map.of(
                                        "status", "partial",
                                        "missing_sections", List.of(),
                                        "evidence_count", 1),
                                "cash_quality_verdict", Map.of(
                                        "headline", "Cash conversion remains usable",
                                        "earnings_backed_by_cash", "mixed",
                                        "summary", "Operating cash flow evidence is usable."),
                                "cash_metrics", List.of(),
                                "capital_allocation", Map.of(
                                        "capex", List.of(),
                                        "buybacks", List.of(),
                                        "dividends", List.of(),
                                        "debt", List.of(),
                                        "liquidity", List.of()),
                                "allocation_discipline", List.of(),
                                "red_flags", List.of())));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        assertEquals("LIMITED", report.getSourceContext().getStatus());
        assertEquals("SEC company facts missing metrics: buybacks",
                report.getSourceContext().getMessage());
        assertNotNull(report.getTaskSections());
        assertEquals("partial", report.getTaskSections().getCoverage().getStatus());
    }

    @Test
    void mapsRetrievalRecordsIntoLiveRagTelemetry() {
        ResearchAgentResult result = new ResearchAgentResult(
                "run_rag_telemetry_001",
                ResearchTaskType.LATEST_EARNINGS_READOUT,
                "ok",
                List.of(),
                List.of(),
                List.of(),
                Map.of(
                        "company_name", "Apple Inc.",
                        "sections", Map.of("summary", "Telemetry report."),
                        "task_sections", Map.of(
                                "schema_version", "task_sections.v1",
                                "task_type", "latest_earnings_readout",
                                "coverage", Map.of(
                                        "status", "complete",
                                        "missing_sections", List.of(),
                                        "evidence_count", 5),
                                "topline_verdict", Map.of(
                                        "headline", "Telemetry verdict",
                                        "summary", "Telemetry summary.",
                                        "verdict", "mixed"),
                                "key_takeaways", List.of(),
                                "financial_dashboard", Map.of(
                                        "metrics", List.of(),
                                        "chart_focus", List.of()),
                                "driver_snapshot", List.of(),
                                "risk_snapshot", List.of()),
                        "retrieval_records", List.of(
                                Map.of(
                                        "tool_name", "search_metric_evidence",
                                        "latency_ms", 120,
                                        "record_count", 4),
                                Map.of(
                                        "tool_name", "build_evidence_pack",
                                        "latency_ms", 380,
                                        "retrieved_nodes", List.of(
                                                Map.of("section", "Management Discussion and Analysis"),
                                                Map.of("section", "Risk Factors"),
                                                Map.of("section", "Segment Information"),
                                                Map.of("section", "Segment Information"),
                                                Map.of("section", "Notes to Consolidated Financial Statements")),
                                        "evidence_pack", Map.of(
                                                "retrieval_status", "ok",
                                                "filing_evidence_count", 3,
                                                "metric_fact_count", 7,
                                                "serialized_length", 6120,
                                                "sections", List.of(
                                                        "Management Discussion and Analysis",
                                                        "Segment Information"))))));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        assertNotNull(report.getRagTelemetry());
        assertEquals(5, report.getRagTelemetry().getEvidenceRetrieved());
        assertEquals(3, report.getRagTelemetry().getEvidenceUsed());
        assertEquals(7, report.getRagTelemetry().getMetricFacts());
        assertEquals(4, report.getRagTelemetry().getSectionsCovered());
        assertEquals(500, report.getRagTelemetry().getRetrievalLatencyMs());
        assertFalse(report.getRagTelemetry().isEmptyRetrieval());
        assertEquals(6120, report.getRagTelemetry().getEvidencePackBytes());
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
                List.of(),
                Map.of(
                        "company_name", "Apple Inc.",
                        "period", "FY2026 Q2",
                        "report_type", "quarterly",
                        "sections", Map.of("summary", "Typed summary.", "synthesis", "llm"),
                        "task_sections", Map.ofEntries(
                                Map.entry("schema_version", "task_sections.v1"),
                                Map.entry("task_type", "latest_earnings_readout"),
                                Map.entry("coverage", Map.of(
                                        "status", "complete",
                                        "missing_sections", List.of(),
                                        "evidence_count", 3)),
                                Map.entry("company_profile", Map.of(
                                        "summary", "Apple Inc. designs devices, software, and services for a global installed base.",
                                        "evidence_refs", List.of(sourceRef),
                                        "citation_status", "supported")),
                                Map.entry("topline_verdict", Map.of(
                                        "headline", "Revenue growth with mixed margin signals",
                                        "summary", "Revenue improved, but margin evidence was mixed.",
                                        "verdict", "mixed",
                                        "confidence", "medium")),
                                Map.entry("key_takeaways", List.of(point)),
                                Map.entry("financial_dashboard", Map.of(
                                        "metrics", List.of(Map.of(
                                                "name", "Revenue",
                                                "value", "higher year over year",
                                                "period", "latest quarter",
                                                "interpretation", "Topline improved.",
                                                "evidence_refs", List.of(sourceRef),
                                                "citation_status", "supported")),
                                        "chart_focus", List.of("revenue"))),
                                Map.entry("driver_snapshot", List.of(point)),
                                Map.entry("risk_snapshot", List.of(point)),
                                Map.entry("quality_of_quarter", Map.of(
                                        "growth_quality", point,
                                        "margin_quality", point,
                                        "cash_quality", point)),
                                Map.entry("drivers_and_draggers", Map.of(
                                        "drivers", List.of(point),
                                        "draggers", List.of(point))),
                                Map.entry("bull_bear_read", Map.of(
                                        "bull_case", List.of(point),
                                        "bear_case", List.of(point),
                                        "balanced_read", point)),
                                Map.entry("watch_next", List.of(Map.of(
                                        "title", "Watch operating margin",
                                        "metric", "operating_margin",
                                        "why_it_matters", "Operating margin will show whether revenue converts into better earnings.",
                                        "evidence_refs", List.of(sourceRef),
                                        "citation_status", "supported")))),
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
        assertEquals("medium", latest.getToplineVerdict().getConfidence());
        assertEquals("Revenue improved", latest.getKeyTakeaways().get(0).getTitle());
        assertEquals("Revenue", latest.getFinancialDashboard().getMetrics().get(0).getName());
        assertEquals("Revenue improved", latest.getDriverSnapshot().get(0).getTitle());
        assertEquals("Revenue improved", latest.getRiskSnapshot().get(0).getTitle());
        assertEquals("Revenue improved", latest.getQualityOfQuarter().getGrowthQuality().getTitle());
        assertEquals("Revenue improved", latest.getQualityOfQuarter().getCashQuality().getTitle());
        assertNull(latest.getQualityOfQuarter().getOneTimeItems());
        assertEquals("Revenue improved",
                latest.getDriversAndDraggers().getDrivers().get(0).getTitle());
        assertEquals("Revenue improved",
                latest.getDriversAndDraggers().getDraggers().get(0).getTitle());
        assertEquals("Revenue improved",
                latest.getBullBearRead().getBullCase().get(0).getTitle());
        assertEquals("Revenue improved",
                latest.getBullBearRead().getBearCase().get(0).getTitle());
        assertEquals("Revenue improved", latest.getBullBearRead().getBalancedRead().getTitle());
        assertEquals("Watch operating margin", latest.getWatchNext().get(0).getTitle());
        assertEquals("operating_margin", latest.getWatchNext().get(0).getMetric());
        assertEquals("supported", latest.getWatchNext().get(0).getCitationStatus());
        assertNotNull(report.getMetadata().getGeneratedAt());
        assertFalse(report.getMetadata().getGeneratedAt().isBlank());
        assertEquals("2026-04-30", report.getFilingDate());
        assertEquals("VERIFIED", report.getCitations().get(0).getVerificationStatus());
    }
}
