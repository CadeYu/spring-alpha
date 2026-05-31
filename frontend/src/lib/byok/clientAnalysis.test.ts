import { afterEach, describe, expect, it, vi } from "vitest";

import { runClientByokAnalysis } from "./clientAnalysis";

describe("runClientByokAnalysis", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("retries once when the provider returns truncated JSON", async () => {
    let providerCalls = 0;
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/api/java/financial/NVDA")) {
        return new Response(
          JSON.stringify({
            companyName: "NVIDIA Corporation",
            period: "Q1 FY2027",
            filingDate: "2026-05-27",
            revenue: "$44.1B",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.includes("/api/java/sec/10k/NVDA")) {
        return new Response(
          "Revenue increased as data center demand remained strong.",
          { status: 200, headers: { "Content-Type": "text/plain" } },
        );
      }

      if (url.includes("api.siliconflow.cn/v1/chat/completions")) {
        providerCalls += 1;
        const content =
          providerCalls === 1
            ? '{"executiveSummary":"NVIDIA revenue growth was driven'
            : JSON.stringify({
                executiveSummary:
                  "NVIDIA revenue growth was led by data center demand.",
                companyName: "NVIDIA Corporation",
                period: "Q1 FY2027",
                filingDate: "2026-05-27",
                citations: [],
                taskSections: {
                  schemaVersion: "task_sections.v1",
                  taskType: "latest_earnings_readout",
                  latestEarnings: {
                    toplineVerdict: {
                      headline: "Data center demand carried the quarter.",
                      summary:
                        "NVIDIA revenue growth was led by data center demand.",
                      verdict: "positive",
                      confidence: "high",
                    },
                    keyTakeaways: [],
                    financialDashboard: { metrics: [], chartFocus: [] },
                    driverSnapshot: [],
                    riskSnapshot: [],
                  },
                },
              });

        return new Response(
          JSON.stringify({
            choices: [{ message: { content } }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    const report = await runClientByokAnalysis({
      ticker: "NVDA",
      taskId: "latest_earnings_readout",
      lang: "en",
      provider: "siliconflow",
      model: "Pro/moonshotai/Kimi-K2.6",
      apiKey: "sk-test",
    });

    expect(providerCalls).toBe(2);
    expect(report.companyName).toBe("NVIDIA Corporation");
    if (
      !report.taskSections ||
      !("latestEarnings" in report.taskSections) ||
      !report.taskSections.latestEarnings
    ) {
      throw new Error("Expected latest earnings task section envelope.");
    }
    expect(report.taskSections.latestEarnings.toplineVerdict.summary).toBe(
      "NVIDIA revenue growth was led by data center demand.",
    );
  });

  it("throws an actionable error when retry still returns invalid JSON", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/api/java/financial/NVDA")) {
        return new Response(JSON.stringify({ companyName: "NVIDIA Corporation" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      if (url.includes("/api/java/sec/10k/NVDA")) {
        return new Response("Revenue evidence.", {
          status: 200,
          headers: { "Content-Type": "text/plain" },
        });
      }

      if (url.includes("api.siliconflow.cn/v1/chat/completions")) {
        return new Response(
          JSON.stringify({
            choices: [
              {
                message: {
                  content: '{"executiveSummary":"NVIDIA revenue growth',
                },
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    await expect(
      runClientByokAnalysis({
        ticker: "NVDA",
        taskId: "latest_earnings_readout",
        lang: "en",
        provider: "siliconflow",
        model: "Pro/moonshotai/Kimi-K2.6",
        apiKey: "sk-test",
      }),
    ).rejects.toThrow(/provider returned incomplete json/i);
    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).includes("api.siliconflow.cn/v1/chat/completions"),
      ),
    ).toHaveLength(2);
  });

  it("sends a task-focused evidence pack instead of the full filing text", async () => {
    const longRiskText = Array.from({ length: 80 }, (_, index) =>
      `Generic risk disclosure ${index} about legal proceedings and markets.`,
    ).join(" ");
    let providerPrompt = "";
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.includes("/api/java/financial/NVDA")) {
        return new Response(
          JSON.stringify({
            companyName: "NVIDIA Corporation",
            period: "Q1 FY2027",
            filingDate: "2026-05-27",
            revenue: "$44.1B",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      if (url.includes("/api/java/sec/10k/NVDA")) {
        return new Response(
          [
            "Revenue increased as data center demand remained strong.",
            "Gross margin expanded because product mix shifted toward accelerated computing.",
            longRiskText,
          ].join(" "),
          { status: 200, headers: { "Content-Type": "text/plain" } },
        );
      }

      if (url.includes("api.siliconflow.cn/v1/chat/completions")) {
        const body = JSON.parse(String(init?.body ?? "{}")) as {
          messages?: Array<{ content?: string }>;
        };
        providerPrompt = body.messages?.[0]?.content ?? "";
        return new Response(
          JSON.stringify({
            choices: [
              {
                message: {
                  content: JSON.stringify({
                    executiveSummary:
                      "NVIDIA revenue growth was led by data center demand.",
                    companyName: "NVIDIA Corporation",
                    period: "Q1 FY2027",
                    filingDate: "2026-05-27",
                    citations: [],
                    taskSections: {
                      schemaVersion: "task_sections.v1",
                      taskType: "latest_earnings_readout",
                      latestEarnings: {
                        toplineVerdict: {
                          headline: "Data center demand carried the quarter.",
                          summary:
                            "NVIDIA revenue growth was led by data center demand.",
                          verdict: "positive",
                          confidence: "high",
                        },
                        keyTakeaways: [],
                        financialDashboard: { metrics: [], chartFocus: [] },
                        driverSnapshot: [],
                        riskSnapshot: [],
                      },
                    },
                  }),
                },
              },
            ],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }

      throw new Error(`Unexpected fetch: ${url}`);
    });

    vi.stubGlobal("fetch", fetchMock);

    await runClientByokAnalysis({
      ticker: "NVDA",
      taskId: "latest_earnings_readout",
      lang: "en",
      provider: "siliconflow",
      model: "Pro/moonshotai/Kimi-K2.6",
      apiKey: "sk-test",
    });

    expect(providerPrompt).toContain("Task-focused evidence pack");
    expect(providerPrompt).toContain(
      "Revenue increased as data center demand remained strong.",
    );
    expect(providerPrompt).toContain(
      "Gross margin expanded because product mix shifted toward accelerated computing.",
    );
    expect(providerPrompt).not.toContain(longRiskText);
    expect(providerPrompt.length).toBeLessThan(16_000);
  });
});
