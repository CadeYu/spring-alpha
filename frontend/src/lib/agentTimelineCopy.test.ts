import { describe, expect, it } from "vitest";
import {
  formatTimelineTokenUsage,
  timelineEmptyState,
  timelineEventKindLabel,
  timelineSectionTitle,
  translateTimelineSummary,
} from "./agentTimelineCopy";

describe("agentTimelineCopy", () => {
  it("localizes the timeline shell labels", () => {
    expect(timelineSectionTitle("zh")).toBe("消息与工具");
    expect(timelineSectionTitle("en")).toBe("Messages & Tools");
    expect(timelineEmptyState("zh")).toContain("reasoning 与 tool");
    expect(timelineEventKindLabel("reasoning", "zh")).toBe("推理");
    expect(timelineEventKindLabel("tool", "zh")).toBe("工具");
  });

  it("translates known summaries while preserving technical terms", () => {
    expect(
      translateTimelineSummary(
        "Earnings agent selected the required evidence tools.",
        "zh",
      ),
    ).toBe("财报分析师：已选择 required evidence tools。");
    expect(
      translateTimelineSummary(
        "Business driver agent planned the next evidence step.",
        "zh",
      ),
    ).toBe("市场情绪分析师：已规划下一步证据采集。");
    expect(
      translateTimelineSummary(
        "Sentiment analyst collected StockTwits messages for retail sentiment.",
        "zh",
      ),
    ).toBe("市场情绪分析师：已收集 StockTwits 消息用于散户情绪分析。");
    expect(
      translateTimelineSummary("Agent completed.", "zh"),
    ).toBe("Agent 已完成。");
  });

  it("formats token usage for chinese display", () => {
    expect(
      formatTimelineTokenUsage("test-model", 1416, 53, "zh"),
    ).toBe("test-model: 1416 输入，53 输出");
    expect(
      formatTimelineTokenUsage("test-model", 1416, 53, "en"),
    ).toBe("test-model: 1416 in, 53 out");
  });
});
