package com.springalpha.backend.service.research;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.springalpha.backend.financial.contract.ResearchTaskType;

public record ResearchAgentEvent(
        @JsonProperty("run_id") String runId,
        @JsonProperty("task_type") ResearchTaskType taskType,
        String phase,
        String status,
        String summary,
        @JsonProperty("tool_name") String toolName,
        @JsonProperty("latency_ms") long latencyMs,
        @JsonProperty("degraded_reason") String degradedReason) {
}
