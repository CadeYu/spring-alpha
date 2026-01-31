package com.springalpha.backend.financial.model;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class HistoricalDataPoint {
    private String period; // e.g. "Q3 2023"
    private BigDecimal grossMargin;
    private BigDecimal operatingMargin;
    private BigDecimal netMargin;
}
