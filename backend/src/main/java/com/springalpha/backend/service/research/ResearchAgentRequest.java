package com.springalpha.backend.service.research;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.springalpha.backend.financial.contract.ResearchTaskType;

import java.util.List;
import java.util.Map;

public record ResearchAgentRequest(
        @JsonProperty("run_id") String runId,
        String ticker,
        @JsonProperty("task_type") ResearchTaskType taskType,
        String language,
        @JsonProperty("max_evidence_repair_loops") int maxEvidenceRepairLoops,
        @JsonProperty("llm_provider") String llmProvider,
        @JsonProperty("llm_model") String llmModel,
        @JsonProperty("llm_api_key") String llmApiKey,
        Map<String, Object> facts,
        List<FilingDocument> filings) {

    public ResearchAgentRequest(
            String runId,
            String ticker,
            ResearchTaskType taskType,
            String language,
            int maxEvidenceRepairLoops) {
        this(runId, ticker, taskType, language, maxEvidenceRepairLoops, null, null, null, Map.of(), List.of());
    }

    public record FilingDocument(
            String ticker,
            @JsonProperty("filing_type") String filingType,
            @JsonProperty("filing_date") String filingDate,
            @JsonProperty("accession_number") String accessionNumber,
            String text) {
    }
}
