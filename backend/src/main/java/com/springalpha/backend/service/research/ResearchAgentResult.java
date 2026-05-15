package com.springalpha.backend.service.research;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.springalpha.backend.financial.contract.ResearchTaskType;

import java.util.List;
import java.util.Map;

public record ResearchAgentResult(
        @JsonProperty("run_id") String runId,
        @JsonProperty("task_type") ResearchTaskType taskType,
        String status,
        List<ResearchAgentEvent> events,
        @JsonProperty("degraded_reasons") List<String> degradedReasons,
        @JsonProperty("retrieval_records") List<Map<String, Object>> retrievalRecords,
        @JsonProperty("final_report") Map<String, Object> finalReport) {
}
