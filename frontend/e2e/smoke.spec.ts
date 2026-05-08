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

const TASK_E2E_CASES = [
  {
    taskType: "latest_earnings_readout",
    radioName: /latest earnings readout/i,
    ticker: "AAPL",
    companyName: "Apple Inc.",
    summary: "Latest earnings readout mocked E2E summary.",
    citation: "Latest earnings citation from MD&A.",
  },
  {
    taskType: "business_driver_deep_dive",
    radioName: /business driver deep dive/i,
    ticker: "MSFT",
    companyName: "Microsoft Corporation",
    summary: "Business driver deep dive mocked E2E summary.",
    citation: "Business drivers citation from the business section.",
  },
  {
    taskType: "cash_flow_capital_allocation",
    radioName: /cash flow & capital allocation/i,
    ticker: "NVDA",
    companyName: "NVIDIA Corporation",
    summary: "Cash flow capital allocation mocked E2E summary.",
    citation: "Cash flow citation from liquidity and capital resources.",
  },
] as const;

test.describe("Spring Alpha smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "spring-alpha-siliconflow-key",
        "test-skip-provider-validation",
      );
    });
  });

  for (const taskCase of TASK_E2E_CASES) {
    test(`${taskCase.taskType} runs through the mocked analysis path`, async ({
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
        const taskType = url.searchParams.get("taskType");
        observedTaskTypes.push(taskType ?? "");

        if (taskType !== taskCase.taskType) {
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
                  excerpt: taskCase.citation,
                  verificationStatus: "VERIFIED",
                },
              ],
              metadata: {
                modelName: "gpt-4o-mini",
                generatedAt: "2026-03-09T10:00:00Z",
                language: "en",
              },
              sourceContext: {
                status: "GROUNDED",
                message: "Grounded in SEC text evidence.",
              },
            },
          ]),
        });
      });

      await page.goto("/app");
      await page
        .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
        .fill(taskCase.ticker);
      await page.getByRole("radio", { name: taskCase.radioName }).click();
      await expect(
        page.getByRole("radio", { name: taskCase.radioName }),
      ).toBeChecked();
      await page.getByRole("button", { name: /analyze/i }).click();

      await expect(
        page.getByText(`${taskCase.companyName} · Q1 2026 · 2026-03-31`),
      ).toBeVisible();
      await expect(page.getByText(taskCase.summary).first()).toBeVisible();
      await expect(page.getByText(taskCase.citation)).toBeVisible();
      expect(observedTaskTypes).toEqual([taskCase.taskType]);
    });
  }

  test("BYOK analysis renders grounded report metadata and citations", async ({
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
            sourceContext: {
              status: "GROUNDED",
              message: "Grounded in SEC text evidence.",
            },
          },
        ]),
      });
    });

    await page.goto("/app");
    await page
      .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
      .fill("TSLA");
    await page.getByRole("button", { name: /analyze/i }).click();

    await expect(
      page.getByText("Tesla, Inc. · Q1 2026 · 2026-03-31"),
    ).toBeVisible();
    await expect(
      page
        .getByText(
          "Tesla remains under margin pressure but keeps investing aggressively.",
        )
        .first(),
    ).toBeVisible();
    await expect(
      page.getByText("Revenue increased due to stronger deliveries."),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /download pdf|下载 pdf 报告/i }),
    ).toBeVisible();
  });

  test("BYOK mode blocks submission when no key is saved", async ({ page }) => {
    await page.addInitScript(() => {
      window.localStorage.removeItem("spring-alpha-siliconflow-key");
    });
    await page.goto("/app");
    await page.getByRole("button", { name: /analyze/i }).click();

    await expect(
      page.getByText(/SiliconFlow BYOK mode requires you to enter and save your api key first/i),
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
            sourceContext: {
              status: "DEGRADED",
              message:
                "SEC filing was available, but semantic grounding was not ready yet.",
            },
          },
        ]),
      });
    });

    await page.goto("/app");
    await page.getByRole("combobox").selectOption("zh");
    await page
      .locator('input[placeholder*="股票代码"], input[placeholder*="Ticker"]')
      .fill("TSLA");
    await page.getByRole("button", { name: /开始分析/i }).click();

    await expect(
      page.getByText("Tesla, Inc. · Q1 2026 · 2026-03-31"),
    ).toBeVisible();
    await expect(page.getByText("当前状态：降级模式")).toBeVisible();
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
            sourceContext: firstRun
              ? {
                  status: "DEGRADED",
                  message:
                    "SEC filing was available, but semantic grounding was not ready yet.",
                }
              : {
                  status: "GROUNDED",
                  message: "Grounded in SEC text evidence.",
                },
          },
        ]),
      });
    });

    await page.goto("/app");
    await page.getByRole("combobox").selectOption("zh");
    await page
      .locator('input[placeholder*="股票代码"], input[placeholder*="Ticker"]')
      .fill("TSLA");

    await page.getByRole("button", { name: /开始分析/i }).click();
    await expect(page.getByText("当前状态：降级模式")).toBeVisible();

    await page.getByRole("button", { name: /开始分析/i }).click();
    await expect(
      page.getByText("Revenue increased due to stronger deliveries."),
    ).toBeVisible();
    await expect(page.getByText("当前状态：降级模式")).not.toBeVisible();
  });

  test("financial-sector tickers keep revenue but hide generic margin dashboards", async ({
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

    await expect(
      page.getByText("JPMorgan Chase & Co. · Q4 2025 · 2026-01-14"),
    ).toBeVisible();
    await expect(page.getByText("Financial Sector Mode").first()).toBeVisible();
    await expect(
      page.getByText("Revenue Trend (Last 1 Quarters)"),
    ).toBeVisible();
    await expect(
      page.getByText("Margin Trend Analysis (Last 1 Quarters)"),
    ).not.toBeVisible();
  });

  test("unsupported REIT tickers show notices and suppress generic charts", async ({
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

    await expect(
      page.getByText("Prologis, Inc. · Q4 2025 · 2026-01-28"),
    ).toBeVisible();
    await expect(
      page.getByText("Unsupported Security Type").first(),
    ).toBeVisible();
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
    await expect(
      page.getByText("Tesla, Inc. · Q1 2026 · 2026-03-31"),
    ).toBeVisible();

    await tickerInput.fill("MSFT");
    await page.getByRole("button", { name: /analyze/i }).click();
    await expect(
      page.getByText("Microsoft Corporation · Q2 2026 · 2026-07-30"),
    ).toBeVisible();

    resolveFirstHistory();
    await page.waitForTimeout(300);

    await expect(page.getByText("Microsoft thesis.").first()).toBeVisible();
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

    await page.goto("/app");
    await page
      .getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)")
      .fill("AAPL");
    await page
      .getByRole("radio", { name: /business driver deep dive/i })
      .click();
    await page.getByRole("button", { name: /analyze/i }).click();

    await expect(
      page.getByText("Deterministic business driver deep dive generated").first(),
    ).toBeVisible({ timeout: 120_000 });
    await expect(
      page.getByText(/Source Citations & Verification/i),
    ).toBeVisible();
    await expect(page.getByText(/Agent Progress/i)).toBeVisible();
    await expect(page.getByText(/search_filing_sections/i).first()).toBeVisible();
    await expect(
      page
        .locator("#pdf-section-citations")
        .getByText(/SOURCE/i)
        .first(),
    ).toBeVisible();
  });
});
