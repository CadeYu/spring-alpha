import { expect, test } from "@playwright/test";

const liveAgentEnabled = process.env.RUN_LIVE_AGENT_E2E === "true";
const liveSiliconFlowKey = process.env.SILICONFLOW_API_KEY;

function sseBody(payloads: unknown[]) {
  return payloads
    .map((payload) => `data: ${JSON.stringify(payload)}\n`)
    .join("");
}

async function mockAnalyzeRoute(
  page: import("@playwright/test").Page,
  handler: Parameters<import("@playwright/test").Page["route"]>[1],
) {
  await page.route("**/api/sec/analyze/**", handler);
  await page.route("**/api/java/sec/analyze/**", handler);
}

async function mockHistoryRoute(
  page: import("@playwright/test").Page,
  handler: Parameters<import("@playwright/test").Page["route"]>[1],
) {
  await page.route("**/api/sec/history/**", handler);
  await page.route("**/api/java/sec/history/**", handler);
}

async function mockFinancialFactsRoute(
  page: import("@playwright/test").Page,
  handler: Parameters<import("@playwright/test").Page["route"]>[1],
) {
  await page.route("**/api/financial/**", handler);
  await page.route("**/api/java/financial/**", handler);
}

async function mockTickerSearchRoute(
  page: import("@playwright/test").Page,
  handler: Parameters<import("@playwright/test").Page["route"]>[1],
) {
  await page.route("**/api/tickers/search**", handler);
}

async function mockMarketChartRoute(
  page: import("@playwright/test").Page,
  observedIntervals?: string[],
) {
  await page.route("**/api/market/chart/**", async (route) => {
    const url = new URL(route.request().url());
    observedIntervals?.push(url.searchParams.get("interval") ?? "1d");
    const start = new Date("2020-01-01T00:00:00.000Z").getTime();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        candles: Array.from({ length: 220 }, (_, index) => {
          const date = new Date(start + index * 86400 * 1000)
            .toISOString()
            .slice(0, 10);
          return {
            date,
            open: 100 + index * 0.5,
            high: 112 + index * 0.5,
            low: 98 + index * 0.5,
            close: 108 + index * 0.5,
            volume: 123456 + index,
          };
        }),
      }),
    });
  });
}

async function openAgentReport(
  page: import("@playwright/test").Page,
  name: RegExp,
) {
  await page.getByRole("tab", { name }).click();
}

const TASK_E2E_CASES = [
  {
    taskType: "latest_earnings_readout",
    tabName: /latest earnings readout/i,
    ticker: "AAPL",
    companyName: "Apple Inc.",
    summary: "Latest earnings readout mocked E2E summary.",
    typedHeadline: "Typed latest earnings thesis",
    expectedSections: [
      "Company Profile",
      "Earnings Readout View",
      "Earnings Verdict",
      "KPI Strip",
      "What Changed",
      "Watch Next",
    ],
  },
  {
    taskType: "business_driver_deep_dive",
    tabName: /business driver deep dive/i,
    ticker: "MSFT",
    companyName: "Microsoft Corporation",
    summary: "Business driver deep dive mocked E2E summary.",
    typedHeadline: "Typed business driver thesis",
    expectedSections: [
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
    tabName: /cash flow & capital allocation/i,
    ticker: "NVDA",
    companyName: "NVIDIA Corporation",
    summary: "Cash flow capital allocation mocked E2E summary.",
    typedHeadline: "Typed cash quality thesis",
    expectedSections: [
      "Capital Allocation View",
      "Cash Quality",
      "Cash Flow Bridge",
      "Capital Allocation Scorecard",
      "Allocation Discipline",
      "Red Flags",
    ],
  },
] as const;

const TASK_E2E_CASE_BY_TYPE = Object.fromEntries(
  TASK_E2E_CASES.map((taskCase) => [taskCase.taskType, taskCase]),
) as Record<(typeof TASK_E2E_CASES)[number]["taskType"], (typeof TASK_E2E_CASES)[number]>;

function typedTaskSections(
  taskType: (typeof TASK_E2E_CASES)[number]["taskType"],
) {
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
      companyProfile: {
        summary:
          "Apple Inc. designs consumer devices, software, and services for a global installed base.",
        evidenceRefs: [],
        citationStatus: "supported",
      },
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

test.describe("Spring Alpha smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "spring-alpha-siliconflow-key",
        "test-skip-provider-validation",
      );
    });
    await mockMarketChartRoute(page);
  });

  test("ticker autocomplete uses the server ticker catalog", async ({ page }) => {
    await mockTickerSearchRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          suggestions: [
            {
              ticker: "LLY",
              companyName: "Eli Lilly and Company",
            },
          ],
        }),
      });
    });

    await page.goto("/app");
    await page
      .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
      .fill("lil");

    const option = page.getByRole("option", {
      name: /LLY Eli Lilly and Company/i,
    });
    await expect(option).toBeVisible();
    await option.click();

    await expect(
      page.getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)"),
    ).toHaveValue("LLY");
  });

  test("runs all research agents through the mocked analysis path", async ({
    page,
  }) => {
      const observedTaskTypes: string[] = [];

      await mockHistoryRoute(page, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
      });

      await mockFinancialFactsRoute(page, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({}),
        });
      });

      await mockAnalyzeRoute(page, async (route) => {
        const url = new URL(route.request().url());
        const taskType = url.searchParams.get(
          "taskType",
        ) as (typeof TASK_E2E_CASES)[number]["taskType"] | null;
        observedTaskTypes.push(taskType ?? "");
        const taskCase = taskType ? TASK_E2E_CASE_BY_TYPE[taskType] : undefined;

        if (!taskType || !taskCase) {
          await route.fulfill({
            status: 400,
            contentType: "application/json",
            body: JSON.stringify({
              error: `Unexpected taskType: ${taskType ?? "missing"}`,
            }),
          });
          return;
        }

        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          body: sseBody([
            {
              executiveSummary: taskCase.summary,
              companyName: taskCase.companyName,
              period: "Q1 2026",
              filingDate: "2026-03-31",
              keyMetrics: [],
              businessDrivers: [],
              riskFactors: [],
              citations: [
                {
                  section: "MD&A",
                  excerpt: `${taskCase.companyName} verified citation.`,
                  verificationStatus: "VERIFIED",
                },
              ],
              metadata: {
                modelName: "gpt-4o-mini",
                generatedAt: "2026-03-09T10:00:00Z",
                language: "en",
              },
              taskSections: typedTaskSections(taskCase.taskType),
            },
          ]),
        });
      });

      await page.goto("/app");
      await page
        .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
        .fill("AAPL");
      await expect(
        page.getByRole("region", { name: /agent pipeline/i }),
      ).toBeVisible();
      await page.getByRole("button", { name: /analyze/i }).click();

      for (const taskCase of TASK_E2E_CASES) {
        await openAgentReport(page, taskCase.tabName);
        await expect(
          page.getByText(taskCase.typedHeadline).first(),
        ).toBeVisible();
        for (const section of taskCase.expectedSections) {
          await expect(page.getByText(section).first()).toBeVisible();
        }
      }
      await expect(page.getByText("Trust Summary")).toHaveCount(0);
      await expect(page.getByText("Evidence Count")).toHaveCount(0);
      expect(observedTaskTypes).toEqual([
        "latest_earnings_readout",
        "business_driver_deep_dive",
        "cash_flow_capital_allocation",
      ]);
    });

  test("ticker-submitted market chart renders an interactive trading terminal canvas", async ({
    page,
  }) => {
    const observedIntervals: string[] = [];
    await page.unroute("**/api/market/chart/**");
    await mockMarketChartRoute(page, observedIntervals);

    await page.goto("/app");
    const tickerInput = page.getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)");
    await tickerInput.fill("AAPL");
    await page.getByRole("button", { name: /analyze/i }).click();

    const chart = page.getByTestId("market-candlestick-chart");
    await expect(chart).toBeVisible();
    await expect(page.getByText(/Scroll to zoom/i).first()).toBeVisible();
    await expect(page.getByText(/Drag to pan/i).first()).toBeVisible();
    await expect(chart).toHaveAttribute("data-candle-count", "220");
    await expect(chart).toHaveAttribute("data-visible-from", "2020-04-10");
    await expect(chart).toHaveAttribute("data-visible-to", "2020-08-07");
    await expect.poll(async () => chart.locator("canvas").count()).toBeGreaterThan(0);

    const pixelSample = await chart.locator("canvas").first().evaluate((element) => {
      const canvas = element as HTMLCanvasElement;
      const context = canvas.getContext("2d");
      if (!context) {
        return { nonEmptyPixels: 0, width: canvas.width, height: canvas.height };
      }
      const width = canvas.width;
      const height = canvas.height;
      const image = context.getImageData(0, 0, width, height).data;
      let nonEmptyPixels = 0;
      for (let index = 3; index < image.length; index += 4) {
        if (image[index] !== 0) nonEmptyPixels += 1;
      }
      return { nonEmptyPixels, width, height };
    });

    expect(pixelSample.width).toBeGreaterThan(300);
    expect(pixelSample.height).toBeGreaterThan(300);
    expect(pixelSample.nonEmptyPixels).toBeGreaterThan(1000);

    await page.getByRole("tab", { name: "1W" }).click();
    await page.getByRole("tab", { name: "1M" }).click();
    await page.getByRole("tab", { name: "1Y" }).click();
    await expect.poll(() => observedIntervals).toContain("1y");
    expect(observedIntervals).toEqual(
      expect.arrayContaining(["1d", "1wk", "1mo", "1y"]),
    );

    const box = await chart.boundingBox();
    expect(box).not.toBeNull();
    if (!box) return;

    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.mouse.wheel(0, -500);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 - 90, box.y + box.height / 2, {
      steps: 8,
    });
    await page.mouse.up();
  });

  test("BYOK analysis renders grounded report metadata and typed sections", async ({
    page,
  }) => {
    await mockFinancialFactsRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    await mockHistoryRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            period: "Q1 2026",
            grossMargin: 0.18,
            operatingMargin: 0.05,
            netMargin: 0.04,
            revenue: 94.8,
            netIncome: 3.8,
          },
        ]),
      });
    });

    await mockAnalyzeRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody([
          {
            executiveSummary:
              "Tesla remains under margin pressure but keeps investing aggressively.",
            companyName: "Tesla, Inc.",
            period: "Q1 2026",
            filingDate: "2026-03-31",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [
              {
                section: "MD&A",
                excerpt: "Revenue increased due to stronger deliveries.",
                verificationStatus: "VERIFIED",
              },
            ],
            metadata: {
              modelName: "gpt-4o-mini",
              generatedAt: "2026-03-09T10:00:00Z",
              language: "en",
            },
            taskSections: typedTaskSections("latest_earnings_readout"),
          },
        ]),
      });
    });

    await page.goto("/app");
    await page
      .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
      .fill("TSLA");
    await page.getByRole("button", { name: /analyze/i }).click();
    await openAgentReport(page, /latest earnings readout/i);

    await expect(
      page.getByText("Tesla, Inc. · Q1 2026 · 2026-03-31"),
    ).toBeVisible();
    await expect(
      page.getByText("Typed latest earnings thesis").first(),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /download pdf|下载 pdf 报告/i }),
    ).toBeVisible();
  });

  test("typed report sections keep noisy SEC snippets inside the report column", async ({
    page,
  }) => {
    const noisyTableExcerpt =
      "/ Q2 2026 Form 10-Q / 15 Gross Margin Products and Services gross margin and gross margin percentage for the three- and six-month periods ended March 28, 2026 and March 29, 2025, were as follows (dollars in millions): | | | | | | | | | | | | | | | | | | | | |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---| | Three Months Ended | | Six Months Ended | | | | | | | | | | | | March 28, 2026 | | March 29, 2025 | | March 28, 2026 | | March 29, 2025 |";
    const longConceptExcerpt =
      "SEC companyfacts RevenueFromContractWithCustomerExcludingAssessedTax reports revenue of 219659000000 USD for 2026Q2 filed 2026-05-01.";

    await mockFinancialFactsRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    await mockHistoryRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await mockAnalyzeRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody([
          {
            executiveSummary: "Noisy citation layout regression.",
            companyName: "Apple Inc.",
            period: "Q2 2026",
            filingDate: "2026-05-01",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [
              {
                section: "SEC companyfacts",
                excerpt: longConceptExcerpt,
                verificationStatus: "VERIFIED",
              },
              {
                section: "Full filing",
                excerpt: noisyTableExcerpt,
                verificationStatus: "UNVERIFIED",
              },
            ],
            metadata: {
              modelName: "python-research-service",
              generatedAt: "2026-05-01T10:00:00Z",
              language: "en",
            },
            taskSections: {
              ...typedTaskSections("latest_earnings_readout"),
              latestEarnings: {
                ...typedTaskSections("latest_earnings_readout").latestEarnings,
                toplineVerdict: {
                  headline: "Typed latest earnings thesis",
                  verdict: "mixed",
                  summary: noisyTableExcerpt,
                },
              },
            },
          },
        ]),
      });
    });

    await page.goto("/app");
    await page
      .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
      .fill("AAPL");
    await page.getByRole("button", { name: /analyze/i }).click();
    await openAgentReport(page, /latest earnings readout/i);

    const summarySection = page.locator('[data-pdf-section="summary"]').first();
    await expect(summarySection).toBeVisible();
    await expect(
      summarySection.getByText(/Earnings Readout View/i),
    ).toBeVisible();
    await expect(
      summarySection.getByText("What Changed", { exact: true }),
    ).toBeVisible();
    await expect(
      summarySection.getByText(/gross margin and gross margin percentage/i),
    ).toBeVisible();

    const layout = await summarySection.evaluate((element) => {
      const sectionRect = element.getBoundingClientRect();
      const body = document.documentElement;
      const leakingElements = Array.from(element.querySelectorAll("*"))
        .map((child) => {
          const rect = child.getBoundingClientRect();
          return {
            tag: child.tagName,
            text: (child.textContent || "").slice(0, 80),
            right: rect.right,
            left: rect.left,
          };
        })
        .filter(
          (rect) =>
            rect.right > sectionRect.right + 1 || rect.left < sectionRect.left - 1,
        );

      return {
        pageOverflows: body.scrollWidth > body.clientWidth + 1,
        sectionOverflows: element.scrollWidth > element.clientWidth + 1,
        leakingElements,
      };
    });

    expect(layout).toEqual({
      pageOverflows: false,
      sectionOverflows: false,
      leakingElements: [],
    });
  });

  test("typed evidence cards wrap long SEC-derived text without horizontal overflow", async ({
    page,
  }) => {
    const longConcept =
      "RevenueFromContractWithCustomerExcludingAssessedTaxRevenueFromContractWithCustomerExcludingAssessedTax";
    const noisySummary =
      "/ Q2 2026 Form 10-Q / 15 Gross Margin Products and Services gross margin percentage | | | | | | | | | | | | |---|---|---|---|---|---|---|---|---|---|---|---|---|---| Three Months Ended March 28, 2026 March 29, 2025";

    await mockFinancialFactsRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    await mockHistoryRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await mockAnalyzeRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody([
          {
            executiveSummary: "Typed evidence layout regression.",
            companyName: "Apple Inc.",
            period: "Q2 2026",
            filingDate: "2026-05-01",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            metadata: {
              modelName: "python-research-service",
              generatedAt: "2026-05-01T10:00:00Z",
              language: "en",
            },
            taskSections: {
              schemaVersion: "task_sections.v1",
              taskType: "latest_earnings_readout",
              coverage: {
                status: "complete",
                missingSections: [],
                evidenceCount: 2,
              },
              latestEarnings: {
                toplineVerdict: {
                  headline: "Typed latest earnings thesis",
                  verdict: "mixed",
                  summary: "Typed latest earnings summary.",
                },
                keyTakeaways: [
                  {
                    title: longConcept,
                    summary: noisySummary,
                    evidenceRefs: [],
                    citationStatus: "supported",
                  },
                ],
                financialDashboard: {
                  metrics: [
                    {
                      name: longConcept,
                      value: "219659000000 USD",
                      period: "2026Q2",
                      interpretation: noisySummary,
                      evidenceRefs: [],
                      citationStatus: "supported",
                    },
                  ],
                  chartFocus: ["gross margin"],
                },
                driverSnapshot: [],
                riskSnapshot: [],
              },
            },
          },
        ]),
      });
    });

    await page.goto("/app");
    await page
      .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
      .fill("AAPL");
    await page.getByRole("button", { name: /analyze/i }).click();
    await openAgentReport(page, /latest earnings readout/i);

    const report = page.locator("#pdf-report-root");
    await expect(report).toBeVisible();
    await expect(page.getByText(longConcept).first()).toBeVisible();
    await expect(page.getByText("$219.7B")).toBeVisible();
    await expect(page.getByText("219659000000 USD")).toHaveCount(0);

    const layout = await report.evaluate((element) => {
      const reportRect = element.getBoundingClientRect();
      const body = document.documentElement;
      const leakingElements = Array.from(element.querySelectorAll("*"))
        .map((child) => {
          const rect = child.getBoundingClientRect();
          return {
            tag: child.tagName,
            text: (child.textContent || "").slice(0, 80),
            right: rect.right,
            left: rect.left,
          };
        })
        .filter(
          (rect) =>
            rect.right > reportRect.right + 1 || rect.left < reportRect.left - 1,
        );

      return {
        pageOverflows: body.scrollWidth > body.clientWidth + 1,
        reportOverflows: element.scrollWidth > element.clientWidth + 1,
        leakingElements,
      };
    });

    expect(layout).toEqual({
      pageOverflows: false,
      reportOverflows: false,
      leakingElements: [],
    });
  });

  test("BYOK mode blocks submission when no key is saved", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.removeItem("spring-alpha-siliconflow-key");
    });
    await page.goto("/app");
    await page
      .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
      .fill("AAPL");
    await page.getByRole("button", { name: /analyze/i }).click();

    await expect(
      page.getByText(
        /SiliconFlow BYOK mode requires you to enter and save your api key first/i,
      ),
    ).toBeVisible();
  });

  test("TSLA first run in Chinese shows degraded-source notice", async ({
    page,
  }) => {
    await mockFinancialFactsRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    await mockHistoryRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await mockAnalyzeRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody([
          {
            executiveSummary: "特斯拉首轮分析使用了降级路径。",
            companyName: "Tesla, Inc.",
            period: "Q1 2026",
            filingDate: "2026-03-31",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            metadata: {
              modelName: "gpt-4o-mini",
              generatedAt: "2026-03-09T10:00:00Z",
              language: "zh",
            },
            taskSections: typedTaskSections("latest_earnings_readout"),
          },
        ]),
      });
    });

    await page.goto("/app");
    await page.locator("select").selectOption("zh");
    await page
      .locator('input[placeholder*="股票代码"], input[placeholder*="Ticker"]')
      .fill("TSLA");
    await page.getByRole("button", { name: /开始分析/i }).click();
    await openAgentReport(page, /最新财报速读/i);

    await expect(
      page.getByText("Tesla, Inc. · Q1 2026 · 2026-03-31"),
    ).toBeVisible();
    await expect(page.getByText("Typed latest earnings thesis")).toBeVisible();
  });

  test("TSLA second run in Chinese can recover grounded citations", async ({
    page,
  }) => {
    let analyzeCount = 0;

    await mockFinancialFactsRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    await mockHistoryRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await mockAnalyzeRoute(page, async (route) => {
      analyzeCount += 1;
      const firstRun = analyzeCount === 1;
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody([
          {
            executiveSummary: firstRun
              ? "首轮分析为降级态。"
              : "二轮分析已经恢复引用。",
            companyName: "Tesla, Inc.",
            period: "Q1 2026",
            filingDate: "2026-03-31",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: firstRun
              ? []
              : [
                  {
                    section: "MD&A",
                    excerpt: "Revenue increased due to stronger deliveries.",
                    verificationStatus: "VERIFIED",
                  },
                ],
            metadata: {
              modelName: "gpt-4o-mini",
              generatedAt: "2026-03-09T10:00:00Z",
              language: "zh",
            },
            taskSections: typedTaskSections("latest_earnings_readout"),
          },
        ]),
      });
    });

    await page.goto("/app");
    await page.locator("select").selectOption("zh");
    await page
      .locator('input[placeholder*="股票代码"], input[placeholder*="Ticker"]')
      .fill("TSLA");

    await page.getByRole("button", { name: /开始分析/i }).click();
    await openAgentReport(page, /最新财报速读/i);
    await expect(page.getByText("Typed latest earnings thesis")).toBeVisible();

    await page.getByRole("button", { name: /开始分析/i }).click();
    await openAgentReport(page, /最新财报速读/i);
    await expect(page.getByText("Typed latest earnings thesis")).toBeVisible();
  });

  test("financial-sector tickers require typed sections instead of generic margin dashboards", async ({
    page,
  }) => {
    await mockFinancialFactsRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          dashboardMode: "financial_sector",
          dashboardMessage: "Financial sector mode is active.",
        }),
      });
    });

    await mockHistoryRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            period: "FY2025 Q4",
            revenue: 45000000000,
            netIncome: 9800000000,
          },
        ]),
      });
    });

    await mockAnalyzeRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody([
          {
            executiveSummary: "JPMorgan remains well-capitalized.",
            companyName: "JPMorgan Chase & Co.",
            period: "Q4 2025",
            filingDate: "2026-01-14",
            keyMetrics: [
              {
                metricName: "Revenue",
                value: "$45B",
                interpretation: "Revenue remained resilient.",
                sentiment: "neutral",
              },
            ],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            metadata: {
              modelName: "gpt-4o-mini",
              generatedAt: "2026-03-09T10:00:00Z",
              language: "en",
            },
          },
        ]),
      });
    });

    await page.goto("/app");
    await page
      .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
      .fill("JPM");
    await page.getByRole("button", { name: /analyze/i }).click();
    await openAgentReport(page, /latest earnings readout/i);

    await expect(
      page.getByText("JPMorgan Chase & Co. · Q4 2025 · 2026-01-14"),
    ).toBeVisible();
    await expect(
      page.getByText("Missing typed taskSections").first(),
    ).toBeVisible();
    await expect(page.getByText("Financial Sector Mode").first()).not.toBeVisible();
    await expect(page.getByText("Revenue Trend (Last 1 Quarters)")).not.toBeVisible();
    await expect(
      page.getByText("Margin Trend Analysis (Last 1 Quarters)"),
    ).not.toBeVisible();
  });

  test("unsupported REIT tickers require typed sections and suppress generic charts", async ({
    page,
  }) => {
    await mockFinancialFactsRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          dashboardMode: "unsupported_reit",
          dashboardMessage:
            "This ticker is categorized as a REIT / trust-like issuer.",
        }),
      });
    });

    await mockHistoryRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            period: "FY2025 Q4",
            revenue: 2100000000,
            netIncome: 820000000,
          },
        ]),
      });
    });

    await mockAnalyzeRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody([
          {
            executiveSummary:
              "This REIT is outside the generic operating-company dashboard flow.",
            companyName: "Prologis, Inc.",
            period: "Q4 2025",
            filingDate: "2026-01-28",
            keyMetrics: [
              {
                metricName: "Revenue",
                value: "$2.1B",
                interpretation: "Revenue remained stable.",
                sentiment: "neutral",
              },
            ],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            metadata: {
              modelName: "gpt-4o-mini",
              generatedAt: "2026-03-09T10:00:00Z",
              language: "en",
            },
          },
        ]),
      });
    });

    await page.goto("/app");
    await page
      .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
      .fill("PLD");
    await page.getByRole("button", { name: /analyze/i }).click();
    await openAgentReport(page, /latest earnings readout/i);

    await expect(
      page.getByText("Prologis, Inc. · Q4 2025 · 2026-01-28"),
    ).toBeVisible();
    await expect(
      page.getByText("Missing typed taskSections").first(),
    ).toBeVisible();
    await expect(page.getByText("Unsupported Security Type").first()).not.toBeVisible();
    await expect(
      page.getByText("Revenue Trend (Last 1 Quarters)"),
    ).not.toBeVisible();
    await expect(
      page.getByText("Margin Trend Analysis (Last 1 Quarters)"),
    ).not.toBeVisible();
  });

  test("rapid ticker switch keeps the final ticker state", async ({ page }) => {
    let historyCount = 0;
    let resolveFirstHistory!: () => void;
    const firstHistoryGate = new Promise<void>((resolve) => {
      resolveFirstHistory = resolve;
    });

    await mockFinancialFactsRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    await mockHistoryRoute(page, async (route) => {
      historyCount += 1;

      if (historyCount === 1) {
        await firstHistoryGate;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              period: "FY 2024",
              grossMargin: 0.1,
              operatingMargin: 0.1,
              netMargin: 0.1,
              revenue: 10,
              netIncome: 1,
            },
          ]),
        });
        return;
      }

      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            period: "FY 2025",
            grossMargin: 0.4,
            operatingMargin: 0.3,
            netMargin: 0.2,
            revenue: 100,
            netIncome: 20,
          },
        ]),
      });
    });

    await mockAnalyzeRoute(page, async (route) => {
      const url = route.request().url();
      const isMsft = url.includes("/MSFT");

      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody([
          {
            executiveSummary: isMsft ? "Microsoft thesis." : "Tesla thesis.",
            companyName: isMsft ? "Microsoft Corporation" : "Tesla, Inc.",
            period: isMsft ? "Q2 2026" : "Q1 2026",
            filingDate: isMsft ? "2026-07-30" : "2026-03-31",
            keyMetrics: [
              {
                metricName: "Revenue",
                value: isMsft ? "$245B" : "$95B",
                interpretation: isMsft
                  ? "Microsoft revenue stayed strong."
                  : "Tesla revenue stayed under pressure.",
                sentiment: "positive",
              },
            ],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            metadata: {
              modelName: "gpt-4o-mini",
              generatedAt: "2026-03-09T10:00:00Z",
              language: "en",
            },
            taskSections: {
              ...typedTaskSections("latest_earnings_readout"),
              latestEarnings: {
                ...typedTaskSections("latest_earnings_readout").latestEarnings,
                toplineVerdict: {
                  headline: isMsft ? "Microsoft typed thesis." : "Tesla typed thesis.",
                  verdict: "mixed",
                  summary: isMsft
                    ? "Microsoft revenue stayed strong."
                    : "Tesla revenue stayed under pressure.",
                },
              },
            },
          },
        ]),
      });
    });

    await page.goto("/app");
    const tickerInput = page.getByPlaceholder(
      "Enter Ticker (e.g., AAPL, MSFT, TSLA)",
    );

    await tickerInput.fill("TSLA");
    await page.getByRole("button", { name: /analyze/i }).click();
    await openAgentReport(page, /latest earnings readout/i);
    await expect(
      page.getByText("Tesla, Inc. · Q1 2026 · 2026-03-31"),
    ).toBeVisible();

    await tickerInput.fill("MSFT");
    await page.getByRole("button", { name: /analyze/i }).click();
    await openAgentReport(page, /latest earnings readout/i);
    await expect(
      page.getByText("Microsoft Corporation · Q2 2026 · 2026-07-30"),
    ).toBeVisible();

    resolveFirstHistory();
    await page.waitForTimeout(300);

    await expect(page.getByText("Microsoft typed thesis.").first()).toBeVisible();
    await expect(
      page.getByText("Tesla, Inc. · Q1 2026 · 2026-03-31"),
    ).not.toBeVisible();
    await expect(
      page.getByText("Microsoft Corporation · Q2 2026 · 2026-07-30"),
    ).toBeVisible();
    await expect(page.getByText("FY 2024")).not.toBeVisible();
  });
});

test.describe("Spring Alpha live Agent path", () => {
  test.skip(
    !liveAgentEnabled,
    "Set RUN_LIVE_AGENT_E2E=true to run the non-mocked Agent E2E path.",
  );
  test.skip(
    liveAgentEnabled && !liveSiliconFlowKey,
    "Set SILICONFLOW_API_KEY to run the live SiliconFlow Agent E2E path.",
  );

  test("renders Python Research Service agent output through the browser", async ({
    page,
  }, testInfo) => {
    testInfo.setTimeout(180_000);
    const siliconFlowKey = liveSiliconFlowKey;
    test.skip(!siliconFlowKey, "SILICONFLOW_API_KEY is required.");

    await mockHistoryRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await mockFinancialFactsRoute(page, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({}),
      });
    });

    await page.addInitScript((key) => {
      window.localStorage.setItem("spring-alpha-siliconflow-key", key);
    }, siliconFlowKey);
    await mockMarketChartRoute(page);

    await page.goto("/app");
    await page
      .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
      .fill("AAPL");
    await page.getByRole("button", { name: /analyze/i }).click();
    await openAgentReport(page, /business driver deep dive/i);

    await expect(
      page.getByRole("heading", { name: /AAPL Analysis Report/i }),
    ).toBeVisible({ timeout: 120_000 });
    await expect(
      page.getByText(/Business Driver Research View/i).first(),
    ).toBeVisible();
    await expect(page.getByText(/Trust Summary/i)).toHaveCount(0);

    const layout = await page.locator("#pdf-report-root").evaluate((element) => {
      const body = document.documentElement;
      return {
        pageOverflows: body.scrollWidth > body.clientWidth + 1,
        reportOverflows: element.scrollWidth > element.clientWidth + 1,
      };
    });
    expect(layout).toEqual({
      pageOverflows: false,
      reportOverflows: false,
    });
  });
});
