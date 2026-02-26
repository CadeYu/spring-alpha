package com.springalpha.backend.financial.model;

import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;

/**
 * 历史数据点 (for Frontend Charts)
 * <p>
 * 这是一个专门为前端图表 (Recharts) 优化的扁平化数据结构。
 * <p>
 * **包含数据**:
 * - `date`: 财报日期 (X轴)。
 * - `revenue`, `netIncome`: 核心业绩指标 (Y轴)。
 * - `grossMargin`, `netMargin`: 利润率指标 (Y轴)。
 * <p>
 * 前端直接使用这个数组渲染 "Revenue Trend" 和 "Margin Analysis" 图表。
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class HistoricalDataPoint {
    private String period; // e.g. "Q3 2023"
    private BigDecimal grossMargin;
    private BigDecimal operatingMargin;
    private BigDecimal netMargin;

    // New fields for Revenue Chart
    private BigDecimal revenue;
    private BigDecimal netIncome;
}
