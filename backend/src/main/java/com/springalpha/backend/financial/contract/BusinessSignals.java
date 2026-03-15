package com.springalpha.backend.financial.contract;

import com.fasterxml.jackson.annotation.JsonIgnore;
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonInclude;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.util.Collections;
import java.util.List;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@JsonIgnoreProperties(ignoreUnknown = true)
@JsonInclude(JsonInclude.Include.NON_NULL)
public class BusinessSignals {

    private String ticker;
    private String reportType;
    private String period;
    private String filingDate;

    private List<SignalItem> segmentPerformance;
    private List<SignalItem> productServiceUpdates;
    private List<SignalItem> managementFocus;
    private List<SignalItem> strategicMoves;
    private List<SignalItem> capexSignals;
    private List<SignalItem> riskSignals;
    private List<EvidenceRef> evidenceRefs;

    @JsonIgnore
    public boolean isEmpty() {
        return safe(segmentPerformance).isEmpty()
                && safe(productServiceUpdates).isEmpty()
                && safe(managementFocus).isEmpty()
                && safe(strategicMoves).isEmpty()
                && safe(capexSignals).isEmpty()
                && safe(riskSignals).isEmpty()
                && safe(evidenceRefs).isEmpty();
    }

    private <T> List<T> safe(List<T> items) {
        return items == null ? Collections.emptyList() : items;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class SignalItem {
        private String title;
        private String summary;
        private String evidenceSection;
        private String evidenceSnippet;
    }

    @Data
    @Builder
    @NoArgsConstructor
    @AllArgsConstructor
    @JsonIgnoreProperties(ignoreUnknown = true)
    @JsonInclude(JsonInclude.Include.NON_NULL)
    public static class EvidenceRef {
        private String topic;
        private String section;
        private String excerpt;
    }
}
