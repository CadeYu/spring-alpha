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
    }
}
