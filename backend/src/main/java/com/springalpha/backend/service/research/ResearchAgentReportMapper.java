package com.springalpha.backend.service.research;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.ResearchTaskType;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Map;

@Component
public class ResearchAgentReportMapper {

    private final ObjectMapper snakeCaseMapper;

    public ResearchAgentReportMapper() {
        this.snakeCaseMapper = new ObjectMapper()
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
    }

    public AnalysisReport toAnalysisReport(ResearchAgentResult result, String language) {
        Map<String, Object> finalReport = result.finalReport();
        Map<String, Object> sections = mapValue(finalReport.get("sections"));
        String summary = stringValue(sections.get("summary"));
        if (summary == null || summary.isBlank()) {
            summary = "Research agent completed without a summary section.";
        }

        return AnalysisReport.builder()
                .executiveSummary(summary)
                .companyName(stringValue(finalReport.get("company_name")))
                .period(stringValue(finalReport.get("period")))
                .reportType(stringValue(finalReport.get("report_type")))
                .sourceContext(sourceContext(result))
                .metadata(AnalysisReport.AnalysisMetadata.builder()
                        .modelName("python-research-service")
                        .language(language)
                        .agentEvents(agentEvents(result))
                        .build())
                .citations(citations(finalReport))
                .taskSections(taskSections(result, finalReport))
                .build();
    }

    private List<AnalysisReport.AgentEventMetadata> agentEvents(ResearchAgentResult result) {
        if (result.events() == null) {
            return List.of();
        }
        return result.events().stream()
                .map(event -> AnalysisReport.AgentEventMetadata.builder()
                        .phase(event.phase())
                        .status(event.status())
                        .summary(event.summary())
                        .toolName(event.toolName())
                        .latencyMs(event.latencyMs())
                        .degradedReason(event.degradedReason())
                        .build())
                .toList();
    }

    private AnalysisReport.TaskSpecificSections taskSections(ResearchAgentResult result, Map<String, Object> finalReport) {
        Map<String, Object> rawSections = mapValue(finalReport.get("task_sections"));
        if (rawSections.isEmpty()) {
            rawSections = mapValue(finalReport.get("taskSections"));
        }
        if (rawSections.isEmpty()) {
            return null;
        }

        ResearchTaskType taskType = taskType(result, rawSections);
        AnalysisReport.TaskSpecificSections.TaskSpecificSectionsBuilder builder = AnalysisReport.TaskSpecificSections.builder()
                .schemaVersion(firstNonBlank(stringValue(rawSections.get("schema_version")), stringValue(rawSections.get("schemaVersion"))))
                .taskType(taskType)
                .coverage(convert(rawSections.get("coverage"), AnalysisReport.TaskSectionCoverage.class));

        return switch (taskType) {
            case BUSINESS_DRIVER_DEEP_DIVE -> builder
                    .businessDriver(convert(rawSections, AnalysisReport.BusinessDriverSections.class))
                    .build();
            case CASH_FLOW_CAPITAL_ALLOCATION -> builder
                    .cashFlowCapitalAllocation(convert(rawSections,
                            AnalysisReport.CashFlowCapitalAllocationSections.class))
                    .build();
            case LATEST_EARNINGS_READOUT -> builder
                    .latestEarnings(convert(rawSections, AnalysisReport.LatestEarningsSections.class))
                    .build();
        };
    }

    private ResearchTaskType taskType(ResearchAgentResult result, Map<String, Object> rawSections) {
        String rawTaskType = firstNonBlank(
                stringValue(rawSections.get("task_type")),
                stringValue(rawSections.get("taskType")));
        if (rawTaskType != null) {
            return ResearchTaskType.fromRequestValue(rawTaskType);
        }
        if (result.taskType() != null) {
            return result.taskType();
        }
        return ResearchTaskType.LATEST_EARNINGS_READOUT;
    }

    private <T> T convert(Object value, Class<T> targetType) {
        if (value == null) {
            return null;
        }
        return snakeCaseMapper.convertValue(value, targetType);
    }

    private AnalysisReport.SourceContext sourceContext(ResearchAgentResult result) {
        String status = "ok".equalsIgnoreCase(result.status()) ? "GROUNDED" : "DEGRADED";
        String message = "ok".equalsIgnoreCase(result.status())
                ? "Generated by Python Research Service."
                : String.join("; ", result.degradedReasons() == null ? List.of() : result.degradedReasons());
        if (message.isBlank()) {
            message = "Python Research Service returned a degraded result.";
        }
        return AnalysisReport.SourceContext.builder()
                .status(status)
                .message(message)
                .build();
    }

    private List<AnalysisReport.Citation> citations(Map<String, Object> finalReport) {
        List<Map<String, Object>> claims = listOfMaps(finalReport.get("claims"));
        return claims.stream()
                .flatMap(claim -> listOfMaps(claim.get("source_refs")).stream())
                .map(sourceRef -> AnalysisReport.Citation.builder()
                        .section(stringValue(sourceRef.get("section")))
                        .excerpt(stringValue(sourceRef.get("snippet")))
                        .verificationStatus(verificationStatus(stringValue(sourceRef.get("citation_status"))))
                        .build())
                .toList();
    }

    private String verificationStatus(String citationStatus) {
        if ("supported".equalsIgnoreCase(citationStatus)) {
            return "VERIFIED";
        }
        if ("missing".equalsIgnoreCase(citationStatus)) {
            return "NOT_FOUND";
        }
        return "UNVERIFIED";
    }

    @SuppressWarnings("unchecked")
    private Map<String, Object> mapValue(Object value) {
        if (value instanceof Map<?, ?> map) {
            return (Map<String, Object>) map;
        }
        return Map.of();
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> listOfMaps(Object value) {
        if (value instanceof List<?> list) {
            return list.stream()
                    .filter(Map.class::isInstance)
                    .map(item -> (Map<String, Object>) item)
                    .toList();
        }
        return List.of();
    }

    private String stringValue(Object value) {
        return value == null ? null : value.toString();
    }

    private String firstNonBlank(String... candidates) {
        for (String candidate : candidates) {
            if (candidate != null && !candidate.isBlank()) {
                return candidate;
            }
        }
        return null;
    }
}
