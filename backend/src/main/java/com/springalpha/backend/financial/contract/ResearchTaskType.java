package com.springalpha.backend.financial.contract;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

import java.util.Arrays;

public enum ResearchTaskType {
    LATEST_EARNINGS_READOUT("latest_earnings_readout"),
    BUSINESS_DRIVER_DEEP_DIVE("business_driver_deep_dive"),
    CASH_FLOW_CAPITAL_ALLOCATION("cash_flow_capital_allocation");

    public static final String DEFAULT_REQUEST_VALUE = "latest_earnings_readout";

    private final String requestValue;

    ResearchTaskType(String requestValue) {
        this.requestValue = requestValue;
    }

    @JsonValue
    public String requestValue() {
        return requestValue;
    }

    @JsonCreator(mode = JsonCreator.Mode.DELEGATING)
    public static ResearchTaskType fromRequestValue(String value) {
        if (value == null || value.isBlank()) {
            return LATEST_EARNINGS_READOUT;
        }

        return Arrays.stream(values())
                .filter(taskType -> taskType.requestValue.equals(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Unsupported taskType: " + value));
    }
}
