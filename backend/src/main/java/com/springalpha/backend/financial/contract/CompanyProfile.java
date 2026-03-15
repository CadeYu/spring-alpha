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
public class CompanyProfile {

    private String ticker;
    private String reportType;
    private String period;
    private String filingDate;

    private List<String> whatItSells;
    private List<String> customerTypes;
    private List<String> productLines;
    private List<String> keyKpis;
    private String businessModelSummary;
    private List<SourceRef> sourceRefs;

    @JsonIgnore
    public boolean isEmpty() {
        return safe(whatItSells).isEmpty()
                && safe(customerTypes).isEmpty()
                && safe(productLines).isEmpty()
                && safe(keyKpis).isEmpty()
                && (businessModelSummary == null || businessModelSummary.isBlank())
                && safe(sourceRefs).isEmpty();
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
    public static class SourceRef {
        private String field;
        private String source;
        private String excerpt;
    }
}
