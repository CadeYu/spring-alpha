import { expect, test } from "@playwright/test";

type TaskCase = {
  taskType:
    | "latest_earnings_readout"
    | "business_driver_deep_dive"
    | "cash_flow_capital_allocation";
  radioName: RegExp;
  headline: string;
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
    radioName: /latest earnings readout/i,
    headline: "Typed latest earnings thesis",
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
    radioName: /business driver deep dive/i,
    headline: "Typed business driver thesis",
    sections: [
      "Business Driver Research View",
      "Thesis",
      "Driver Map",
      "Impact Table",
      "Signals",
      "Watchlist",
    ],
  },
  {
    taskType: "cash_flow_capital_allocation",
    radioName: /cash flow & capital allocation/i,
    headline: "Typed cash quality thesis",
    sections: [
      "Capital Allocation View",
      "Cash Quality",
      "Cash Flow Bridge",
      "Capital Allocation Scorecard",
      "Allocation Discipline",
      "Red Flags",
    ],
  },
];

function sseBody(payloads: unknown[]) {
  return payloads
    .map((payload) => `data: ${JSON.stringify(payload)}\n`)
    .join("");
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
      businessDriver: {
        driverThesis: {
          headline: "Typed business driver thesis",
          durability: "durable",
          summary: "Business driver typed summary.",
        },
        driverMap: {
          product: [supportedPoint],
          segment: [],
          geography: [],
          demand: [],
          pricing: [],
          customer: [],
          strategy: [],
        },
        positiveSignals: [supportedPoint],
        negativeSignals: [partialPoint],
        watchlist: ["Track typed business driver watchlist."],
      },
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
  taskCase: TaskCase,
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
    expect(taskType).toBe(taskCase.taskType);
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
          sourceContext: {
            status: "GROUNDED",
            message: "Grounded in SEC text evidence.",
          },
          taskSections: typedTaskSections(taskCase.taskType),
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
      window.localStorage.setItem(
        "spring-alpha-siliconflow-key",
        "test-skip-provider-validation",
      );
    });
  });

  for (const tickerCase of TICKERS) {
    for (const taskCase of TASK_CASES) {
      test(`${tickerCase.ticker} renders ${taskCase.taskType}`, async ({
        page,
      }) => {
        await mockCommonRoutes(page, taskCase, tickerCase.companyName);

        await page.goto("/app");
        await page
          .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
          .fill(tickerCase.ticker);
        await page.getByRole("radio", { name: taskCase.radioName }).click();
        await page.getByRole("button", { name: /analyze/i }).click();

        await expect(
          page.getByText(`${tickerCase.companyName} · Q1 2026 · 2026-03-31`),
        ).toBeVisible();
        await expect(page.getByText(taskCase.headline).first()).toBeVisible();
        for (const section of taskCase.sections) {
          await expect(page.getByText(section).first()).toBeVisible();
        }
        await expect(page.getByText("Trust Summary")).toHaveCount(0);
        await expect(page.getByText("Evidence Count")).toHaveCount(0);
      });
    }
  }
});
