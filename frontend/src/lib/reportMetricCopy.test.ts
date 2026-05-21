import { describe, expect, it } from "vitest";
import {
  formatMetricInterpretation,
  formatMetricName,
} from "./reportMetricCopy";

describe("reportMetricCopy", () => {
  it("localizes common metric names for chinese UI", () => {
    expect(formatMetricName("Revenue", "zh")).toBe("营收");
    expect(formatMetricName("Gross Margin", "zh")).toBe("毛利率");
    expect(formatMetricName("Operating Income", "zh")).toBe("营业利润");
    expect(formatMetricName("Kimi K2.6", "zh")).toBe("Kimi K2.6");
  });

  it("localizes common metric interpretations for chinese UI", () => {
    expect(formatMetricInterpretation("Reported metric.", "zh")).toBe(
      "已披露指标。",
    );
    expect(formatMetricInterpretation("Revenue increased.", "zh")).toBe(
      "营收增长。",
    );
    expect(formatMetricInterpretation("Capex remained disciplined.", "zh")).toBe(
      "资本开支保持克制。",
    );
    expect(formatMetricInterpretation("Pro/moonshotai/Kimi-K2.6", "zh")).toBe(
      "Pro/moonshotai/Kimi-K2.6",
    );
  });
});
