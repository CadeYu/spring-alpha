import { expect, test } from "@playwright/test";

type TaskCase = {
  taskType:
    | "latest_earnings_readout"
    | "business_driver_deep_dive"
    | "cash_flow_capital_allocation";
  tabName: RegExp;
  headline: string;
  summary: string;
  sections: string[];
};

const TICKERS = [
  { ticker: "AAPL", companyName: "Apple Inc." },
  { ticker: "MSFT", companyName: "Microsoft Corporation" },
  { ticker: "NVDA", companyName: "NVIDIA Corporation" },
  { ticker: "AMZN", companyName: "Amazon.com, Inc." },
  { ticker: "GOOGL", companyName: "Alphabet Inc." },
  { ticker: "META", companyName: "Meta Platforms, Inc." },
  { ticker: "TSLA", companyName: "Tesla, Inc." },
  { ticker: "JPM", companyName: "JPMorgan Chase & Co." },
  { ticker: "V", companyName: "Visa Inc." },
  { ticker: "UNH", companyName: "UnitedHealth Group Incorporated" },
] as const;

const TASK_CASES: TaskCase[] = [
  {
    taskType: "latest_earnings_readout",
    tabName: /latest earnings readout/i,
    headline: "Typed latest earnings thesis",
    summary: "Latest earnings typed summary.",
    sections: [
      "Earnings Readout View",
      "Earnings Verdict",
      "KPI Strip",
      "What Changed",
      "Watch Next",
    ],
  },
  {
    taskType: "business_driver_deep_dive",
    tabName: /market narrative & sentiment/i,
    headline: "Typed market sentiment thesis",
    summary: "Market sentiment typed summary.",
    sections: [
      "Market Narrative & Sentiment",
      "Market Narrative",
      "Narrative Snapshot",
      "Bull Case",
      "Bear Case",
      "Balanced Read",
      "Source Divergence",
      "Noise & Sample Limits",
    ],
  },
  {
    taskType: "cash_flow_capital_allocation",
    tabName: /cash flow & capital allocation/i,
    headline: "Typed cash quality thesis",
    summary: "Cash flow typed summary.",
    sections: [
      "Capital Allocation View",
      "Cash Quality",
      "Cash Flow Bridge",
      "Capex and Reinvestment",
      "Balance Sheet Resilience and Debt",
      "Risk Signals and Watch Next",
      "Key Cash Metrics Table",
      "Final Analyst Outlook",
    ],
  },
];

function sseBody(payloads: unknown[]) {
  return payloads
    .map((payload) => `data: ${JSON.stringify(payload)}\n`)
    .join("");
}

function openAgentReport(page: import("@playwright/test").Page, name: RegExp) {
  return page.getByRole("tab", { name }).click();
}

function typedTaskSections(taskType: TaskCase["taskType"]) {
  const coverage = {
    status: "complete",
    missingSections: [],
    evidenceCount: 3,
  };
  const supportedPoint = {
    title: "Typed supported point",
    summary: "Typed evidence-backed summary.",
    evidenceRefs: [],
    citationStatus: "supported",
  };
  const partialPoint = {
    title: "Typed partial point",
    summary: "Typed partial evidence summary.",
    evidenceRefs: [],
    citationStatus: "partial",
  };
  const supportedMetric = {
    name: "Typed metric",
    value: "Positive",
    period: "latest quarter",
    interpretation: "Typed metric interpretation.",
    evidenceRefs: [],
    citationStatus: "supported",
  };

  if (taskType === "business_driver_deep_dive") {
    return {
      schemaVersion: "task_sections.v1",
      taskType,
      coverage,
      sentimentHeader: {
        overallBand: "Mixed",
        overallScore: 5.8,
        confidence: "medium",
        summary: "Market sentiment typed summary.",
      },
      narrativeSnapshot: {
        ...supportedPoint,
        title: "Typed market sentiment thesis",
        summary: "Market sentiment typed summary.",
      },
      bullBearNarrative: {
        bullCase: "Bullish holders emphasize product momentum and resilient demand.",
        bearCase: "Bearish holders emphasize valuation risk and crowded expectations.",
        balancedRead: "The narrative is constructive but still needs confirmation from fundamentals.",
      },
      sourceDivergence: {
        summary: "News is constructive while social discussion is more mixed.",
        newsDirection: "constructive",
        stocktwitsDirection: "mixed",
        redditDirection: "thin",
      },
      noiseWarnings: ["Social sample size is limited for this mocked run."],
    };
  }

  if (taskType === "cash_flow_capital_allocation") {
    return {
      schemaVersion: "task_sections.v1",
      taskType,
      coverage,
      cashFlowCapitalAllocation: {
        cashQualityVerdict: {
          headline: "Typed cash quality thesis",
          earningsBackedByCash: "mixed",
          summary: "Cash flow typed summary.",
        },
        cashMetrics: [supportedMetric],
        capitalAllocation: {
          capex: [supportedPoint],
          buybacks: [supportedPoint],
          dividends: [],
          debt: [],
          liquidity: [supportedPoint],
        },
        allocationDiscipline: [supportedPoint],
        redFlags: [partialPoint],
      },
    };
  }

  return {
    schemaVersion: "task_sections.v1",
    taskType,
    coverage,
    latestEarnings: {
      toplineVerdict: {
        headline: "Typed latest earnings thesis",
        verdict: "mixed",
        summary: "Latest earnings typed summary.",
      },
      keyTakeaways: [supportedPoint],
      financialDashboard: {
        metrics: [supportedMetric],
        chartFocus: ["revenue"],
      },
      driverSnapshot: [supportedPoint],
      riskSnapshot: [partialPoint],
    },
  };
}

async function mockCommonRoutes(
  page: import("@playwright/test").Page,
  companyName: string,
) {
  await page.route("**/api/sec/history/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
  await page.route("**/api/java/sec/history/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });
  await page.route("**/api/financial/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });
  await page.route("**/api/java/financial/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
    });
  });

  const analyzeHandler: Parameters<
    import("@playwright/test").Page["route"]
  >[1] = async (route) => {
    const taskType = new URL(route.request().url()).searchParams.get(
      "taskType",
    );
    expect(taskType).not.toBeNull();
    expect([
      "latest_earnings_readout",
      "business_driver_deep_dive",
      "cash_flow_capital_allocation",
    ]).toContain(taskType);
    const typedTaskType = taskType as TaskCase["taskType"];
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: sseBody([
        {
          executiveSummary: `${companyName} legacy summary should not drive typed views.`,
          companyName,
          period: "Q1 2026",
          filingDate: "2026-03-31",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [
            {
              section: "MD&A",
              excerpt: `${companyName} verified citation.`,
              verificationStatus: "VERIFIED",
            },
          ],
          metadata: {
            modelName: "browser-e2e",
            generatedAt: "2026-03-09T10:00:00Z",
            language: "en",
          },
          taskSections: typedTaskSections(typedTaskType),
        },
      ]),
    });
  };

  await page.route("**/api/sec/analyze/**", analyzeHandler);
  await page.route("**/api/java/sec/analyze/**", analyzeHandler);
}

test.describe("Spring Alpha 10 ticker output-line matrix", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.removeItem("spring-alpha-siliconflow-key");
      window.localStorage.removeItem("spring-alpha-anonymous-trial-used");
      window.localStorage.removeItem("spring-alpha-anonymous-trial-count");
    });
  });

  for (const tickerCase of TICKERS) {
    for (const taskCase of TASK_CASES) {
      test(`${tickerCase.ticker} renders ${taskCase.taskType}`, async ({
        page,
      }) => {
        await mockCommonRoutes(page, tickerCase.companyName);

        await page.goto("/app");
        await page
          .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
          .fill(tickerCase.ticker);
        await page.getByRole("button", { name: /analyze/i }).click();
        await openAgentReport(page, taskCase.tabName);

        await expect(
          page.getByText(`${tickerCase.companyName} · Q1 2026 · 2026-03-31`),
        ).toBeVisible();
        await expect(page.getByText(taskCase.summary).first()).toBeVisible();
        await expect(page.getByText(taskCase.headline)).toHaveCount(0);
        for (const section of taskCase.sections) {
          await expect(page.getByText(section).first()).toBeVisible();
        }
        await expect(page.getByText("Trust Summary")).toHaveCount(0);
        await expect(page.getByText("Evidence Count")).toHaveCount(0);
      });
    }
  }
});
