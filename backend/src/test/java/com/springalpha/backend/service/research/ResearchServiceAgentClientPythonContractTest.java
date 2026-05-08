package com.springalpha.backend.service.research;

import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.ResearchTaskType;
import org.junit.jupiter.api.Assumptions;
import org.junit.jupiter.api.Test;
import org.springframework.web.reactive.function.client.WebClient;

import java.time.Duration;

import static org.junit.jupiter.api.Assertions.*;

class ResearchServiceAgentClientPythonContractTest {

    @Test
    void runCallsLivePythonDeterministicAgentAndMapsRenderableTaskSections() {
        Assumptions.assumeTrue(
                "true".equalsIgnoreCase(System.getenv("RUN_RESEARCH_SERVICE_CONTRACT")),
                "Set RUN_RESEARCH_SERVICE_CONTRACT=true to verify the live Python Research Service bridge.");

        String baseUrl = System.getenv().getOrDefault("RESEARCH_SERVICE_BASE_URL", "http://127.0.0.1:8090");
        ResearchServiceAgentClient client = new ResearchServiceAgentClient(
                WebClient.builder(),
                baseUrl,
                Duration.ofSeconds(10));
        ResearchAgentReportMapper mapper = new ResearchAgentReportMapper();

        ResearchAgentResult result = client.run(new ResearchAgentRequest(
                "run_java_python_contract",
                "aapl",
                ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
                "en",
                2))
                .block(Duration.ofSeconds(15));

        assertNotNull(result);
        assertEquals("run_java_python_contract", result.runId());
        assertEquals(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, result.taskType());
        assertEquals("ok", result.status());
        assertNotNull(result.events());
        assertFalse(result.events().isEmpty());
        assertNotNull(result.finalReport());
        assertEquals("AAPL", result.finalReport().get("ticker"));

        AnalysisReport report = mapper.toAnalysisReport(result, "en");

        assertEquals("python-research-service", report.getMetadata().getModelName());
        assertEquals("GROUNDED", report.getSourceContext().getStatus());
        assertNotNull(report.getMetadata().getAgentEvents());
        assertTrue(report.getMetadata().getAgentEvents().stream()
                .anyMatch(event -> "search_filing_sections".equals(event.getToolName())));
        assertNotNull(report.getTaskSections());
        assertEquals(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE, report.getTaskSections().getTaskType());
        assertNotNull(report.getTaskSections().getBusinessDriver());
        assertNotNull(report.getTaskSections().getBusinessDriver().getDriverThesis());
        assertNotNull(report.getTaskSections().getCoverage());
        assertTrue(report.getTaskSections().getCoverage().getEvidenceCount() > 0);
        assertNotNull(report.getCitations());
        assertTrue(report.getCitations().stream()
                .anyMatch(citation -> "VERIFIED".equals(citation.getVerificationStatus())));
    }
}
