import { describe, expect, it } from "vitest";
import {
  buildRagEvalMetricCopy,
  ragEvalDashboardDescription,
  ragEvalDashboardReportCountLabel,
  ragEvalDashboardStatusLabel,
  ragEvalDashboardTitle,
} from "./ragEvalCopy";

describe("ragEvalCopy", () => {
  it("localizes the dashboard shell copy", () => {
    expect(ragEvalDashboardTitle("zh")).toBe("实时 RAG 遥测");
    expect(ragEvalDashboardTitle("en")).toBe("Live RAG Telemetry");
    expect(ragEvalDashboardDescription("zh")).toContain("检索记录");
    expect(ragEvalDashboardStatusLabel(true, "zh")).toBe("实时运行数据");
    expect(ragEvalDashboardStatusLabel(false, "zh")).toBe("等待检索记录");
    expect(ragEvalDashboardReportCountLabel(null, "zh")).toBe("暂无报告");
    expect(ragEvalDashboardReportCountLabel(3, "zh")).toBe("3 份报告");
  });

  it("localizes the metric cards while preserving technical terms", () => {
    const zhMetrics = buildRagEvalMetricCopy("zh");
    expect(zhMetrics).toHaveLength(7);
    expect(zhMetrics[0].label).toBe("已检索证据");
    expect(zhMetrics[0].detail).toContain("SEC filing");
    expect(zhMetrics[4].label).toBe("检索延迟");
    expect(zhMetrics[4].detail).toContain("retrieval");
    expect(zhMetrics[6].label).toBe("证据包大小");
  });
});
