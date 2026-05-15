package com.springalpha.backend.service.research;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.springalpha.backend.financial.contract.AnalysisReport;
import com.springalpha.backend.financial.contract.ResearchTaskType;
import org.springframework.stereotype.Component;

import java.time.Instant;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

@Component
public class ResearchAgentReportMapper {

    private final ObjectMapper snakeCaseMapper;

    public ResearchAgentReportMapper() {
        this.snakeCaseMapper = new ObjectMapper()
                .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
    }

    public AnalysisReport toAnalysisReport(ResearchAgentResult result, String language) {
        Map<String, Object> finalReport = result.finalReport();
        if (finalReport == null || finalReport.isEmpty()) {
            return degradedAnalysisReport(result, language);
        }
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
                .filingDate(filingDate(finalReport))
                .sourceContext(sourceContext(result))
                .metadata(AnalysisReport.AnalysisMetadata.builder()
                        .modelName("python-research-service")
                        .generatedAt(Instant.now().toString())
                        .language(language)
                        .agentEvents(agentEvents(result))
                        .build())
                .citations(citations(finalReport))
                .taskSections(taskSections(result, finalReport))
                .ragTelemetry(ragTelemetry(result, finalReport))
                .build();
    }

    private AnalysisReport degradedAnalysisReport(ResearchAgentResult result, String language) {
        String message = String.join("; ",
                result.degradedReasons() == null ? List.of() : result.degradedReasons());
        if (message.isBlank()) {
            message = "Research agent failed before producing a final report.";
        }
        return AnalysisReport.builder()
                .executiveSummary(message)
                .sourceContext(sourceContext(result))
                .metadata(AnalysisReport.AnalysisMetadata.builder()
                        .modelName("python-research-service")
                        .generatedAt(Instant.now().toString())
                        .language(language)
                        .agentEvents(agentEvents(result))
                        .build())
                .citations(List.of())
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
                        .eventKind(event.eventKind())
                        .agentName(event.agentName())
                        .modelName(event.modelName())
                        .toolInput(event.toolInput())
                        .usage(event.usage())
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

    private String filingDate(Map<String, Object> finalReport) {
        String explicitFilingDate = firstNonBlank(
                stringValue(finalReport.get("filing_date")),
                stringValue(finalReport.get("filingDate")));
        if (explicitFilingDate != null) {
            return explicitFilingDate;
        }
        return findFilingDate(finalReport).orElse(null);
    }

    private Optional<String> findFilingDate(Object value) {
        if (value instanceof Map<?, ?> map) {
            String filingDate = firstNonBlank(
                    stringValue(map.get("filing_date")),
                    stringValue(map.get("filingDate")));
            if (filingDate != null) {
                return Optional.of(filingDate);
            }
            for (Object nestedValue : map.values()) {
                Optional<String> nestedFilingDate = findFilingDate(nestedValue);
                if (nestedFilingDate.isPresent()) {
                    return nestedFilingDate;
                }
            }
        }
        if (value instanceof List<?> list) {
            for (Object item : list) {
                Optional<String> nestedFilingDate = findFilingDate(item);
                if (nestedFilingDate.isPresent()) {
                    return nestedFilingDate;
                }
            }
        }
        return Optional.empty();
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
        List<String> degradedReasons = result.degradedReasons() == null ? List.of() : result.degradedReasons();
        boolean completed = "ok".equalsIgnoreCase(result.status());
        String status = completed
                ? (degradedReasons.isEmpty() ? "GROUNDED" : "LIMITED")
                : "DEGRADED";
        String message = completed && degradedReasons.isEmpty()
                ? "Generated by Python Research Service."
                : String.join("; ", degradedReasons);
        if (message.isBlank()) {
            message = "Python Research Service returned a degraded result.";
        }
        return AnalysisReport.SourceContext.builder()
                .status(status)
                .message(message)
                .build();
    }

    private AnalysisReport.RagTelemetry ragTelemetry(ResearchAgentResult result, Map<String, Object> finalReport) {
        List<Map<String, Object>> records = listOfMaps(finalReport.get("retrieval_records"));
        if (records.isEmpty()) {
            records = listOfMaps(finalReport.get("retrievalRecords"));
        }
        if (records.isEmpty() && result.retrievalRecords() != null) {
            records = result.retrievalRecords();
        }
        if (records.isEmpty()) {
            return null;
        }

        int evidenceRetrieved = 0;
        int evidenceUsed = 0;
        int metricFacts = 0;
        long retrievalLatencyMs = 0;
        int evidencePackBytes = 0;
        boolean observedEmptyPack = false;
        Set<String> sections = new HashSet<>();

        for (Map<String, Object> record : records) {
            retrievalLatencyMs += longValue(record.get("latency_ms"));
            retrievalLatencyMs += longValue(record.get("latencyMs"));
            int retrievedNodeCount = listOfMaps(record.get("retrieved_nodes")).size()
                    + listOfMaps(record.get("retrievedNodes")).size();
            evidenceRetrieved += retrievedNodeCount;

            int recordCount = intValue(record.get("record_count"));
            if (recordCount > 0) {
                metricFacts = Math.max(metricFacts, recordCount);
            }

            Map<String, Object> evidencePack = mapValue(record.get("evidence_pack"));
            if (evidencePack.isEmpty()) {
                evidencePack = mapValue(record.get("evidencePack"));
            }
            if (!evidencePack.isEmpty()) {
                String retrievalStatus = stringValue(firstNonNull(
                        evidencePack.get("retrieval_status"),
                        evidencePack.get("retrievalStatus")));
                observedEmptyPack = observedEmptyPack || "empty".equalsIgnoreCase(retrievalStatus);
                int filingEvidenceCount = intValue(firstNonNull(
                        evidencePack.get("filing_evidence_count"),
                        evidencePack.get("filingEvidenceCount")));
                int metricFactCount = intValue(firstNonNull(
                        evidencePack.get("metric_fact_count"),
                        evidencePack.get("metricFactCount")));
                evidenceUsed += filingEvidenceCount;
                if (retrievedNodeCount == 0) {
                    evidenceRetrieved += filingEvidenceCount;
                }
                metricFacts = Math.max(metricFacts, metricFactCount);
                evidencePackBytes = Math.max(evidencePackBytes, intValue(firstNonNull(
                        evidencePack.get("serialized_length"),
                        evidencePack.get("serializedLength"))));
                sections.addAll(stringList(evidencePack.get("sections")));
                sections.addAll(stringList(evidencePack.get("sectionNames")));
            }

            for (Map<String, Object> node : listOfMaps(record.get("retrieved_nodes"))) {
                addSection(sections, node);
            }
            for (Map<String, Object> node : listOfMaps(record.get("retrievedNodes"))) {
                addSection(sections, node);
            }
        }

        return AnalysisReport.RagTelemetry.builder()
                .evidenceRetrieved(evidenceRetrieved)
                .evidenceUsed(evidenceUsed)
                .metricFacts(metricFacts)
                .sectionsCovered(sections.size())
                .retrievalLatencyMs(retrievalLatencyMs)
                .emptyRetrieval(evidenceRetrieved == 0 || observedEmptyPack)
                .evidencePackBytes(evidencePackBytes)
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

    private Object firstNonNull(Object... candidates) {
        for (Object candidate : candidates) {
            if (candidate != null) {
                return candidate;
            }
        }
        return null;
    }

    private int intValue(Object value) {
        if (value instanceof Number number) {
            return number.intValue();
        }
        if (value instanceof String text && !text.isBlank()) {
            try {
                return Integer.parseInt(text);
            } catch (NumberFormatException ignored) {
                return 0;
            }
        }
        return 0;
    }

    private long longValue(Object value) {
        if (value instanceof Number number) {
            return number.longValue();
        }
        if (value instanceof String text && !text.isBlank()) {
            try {
                return Long.parseLong(text);
            } catch (NumberFormatException ignored) {
                return 0;
            }
        }
        return 0;
    }

    private List<String> stringList(Object value) {
        if (value instanceof List<?> list) {
            return list.stream()
                    .map(this::stringValue)
                    .filter(item -> item != null && !item.isBlank())
                    .toList();
        }
        return List.of();
    }

    private void addSection(Set<String> sections, Map<String, Object> record) {
        String section = firstNonBlank(
                stringValue(record.get("section")),
                stringValue(record.get("section_name")),
                stringValue(record.get("sectionName")));
        if (section != null) {
            sections.add(section);
        }
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
