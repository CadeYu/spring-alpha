package com.springalpha.backend.service.research;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.springalpha.backend.financial.contract.ResearchTaskType;

import java.util.Map;

public record ResearchAgentEvent(
        @JsonProperty("run_id") String runId,
        @JsonProperty("task_type") ResearchTaskType taskType,
        String phase,
        String status,
        String summary,
        @JsonProperty("tool_name") String toolName,
        @JsonProperty("event_kind") String eventKind,
        @JsonProperty("agent_name") String agentName,
        @JsonProperty("model_name") String modelName,
        @JsonProperty("tool_input") Map<String, Object> toolInput,
        Map<String, Object> usage,
        @JsonProperty("latency_ms") long latencyMs,
        @JsonProperty("degraded_reason") String degradedReason) {
}
