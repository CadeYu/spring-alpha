import { expect, test } from "@playwright/test";

type TaskType =
  | "latest_earnings_readout"
  | "business_driver_deep_dive"
  | "cash_flow_capital_allocation";

type TaskCase = {
  taskType: TaskType;
  tabName: RegExp;
  reportHeading: RegExp;
  requiredComponents: RegExp[];
  qualitySignals: RegExp[];
};

const liveEnabled = process.env.RUN_LIVE_OUTPUT_MATRIX === "true";
const liveSiliconFlowKey = process.env.SILICONFLOW_API_KEY;

const TASK_CASES: TaskCase[] = [
  {
    taskType: "latest_earnings_readout",
    tabName: /latest earnings readout/i,
    reportHeading: /Earnings Readout View/i,
    requiredComponents: [
      /Earnings Readout View/i,
      /Earnings Verdict/i,
      /KPI Strip/i,
      /What Changed/i,
      /Watch Next/i,
    ],
    qualitySignals: [
      /\bpositive\b|\bmixed\b|\bnegative\b/i,
      /\brevenue\b|\bgross\b|\boperating income\b|\bmargin\b/i,
      /\bwatch\b|\brisk\b|\bmonitor\b|\binflect\b|\bpressure\b/i,
    ],
  },
  {
    taskType: "business_driver_deep_dive",
    tabName: /business driver deep dive/i,
    reportHeading: /Business Driver Research View/i,
    requiredComponents: [
      /Business Driver Research View/i,
      /Thesis/i,
      /Driver Map/i,
      /Impact Table/i,
      /Signals/i,
      /Watchlist/i,
    ],
    qualitySignals: [
      /\bdurable\b|\bmixed\b|\btemporary\b|\bunclear\b/i,
      /\bproduct\b|\bsegment\b|\bdemand\b|\bpricing\b|\bcustomer\b|\bstrategy\b/i,
      /\bdriver\b|\bimpact\b|\bsignal\b|\bwatchlist\b|\bmargin\b/i,
    ],
  },
  {
    taskType: "cash_flow_capital_allocation",
    tabName: /cash flow & capital allocation/i,
    reportHeading: /Capital Allocation View/i,
    requiredComponents: [
      /Capital Allocation View/i,
      /Cash Quality/i,
      /Cash Flow Bridge/i,
      /Capital Allocation Scorecard/i,
      /Allocation Discipline/i,
      /Red Flags/i,
    ],
    qualitySignals: [
      /\bcash\b|\boperating cash flow\b|\bfree cash flow\b|\bcapex\b|\bbuyback\b|\bdividend\b|\bdebt\b|\bliquidity\b/i,
      /\bunclear\b|\bmixed\b|\bcash-backed\b|\bnot discernible\b|\bnot provided\b/i,
      /\ballocation\b|\bdiscipline\b|\bred flags\b|\bscorecard\b|\bquality\b/i,
    ],
  },
];

const FORBIDDEN_OUTPUT_PATTERNS = [
  /requires you to enter and save your api key/i,
  /invalid or unauthorized/i,
  /Network response error/i,
  /Waiting for the model/i,
  /Deterministic evidence point/i,
  /Raw planner decision should stay in diagnostics/i,
  /Agent Progress/i,
];

const REQUIRED_BY_TASK: Record<TaskType, RegExp[]> = {
  latest_earnings_readout: [
    /Earnings Readout View/i,
    /Earnings Verdict/i,
    /KPI Strip/i,
    /What Changed/i,
    /Watch Next/i,
  ],
  business_driver_deep_dive: [
    /Business Driver Research View/i,
    /Thesis/i,
    /Driver Map/i,
    /Impact Table/i,
    /Signals/i,
    /Watchlist/i,
  ],
  cash_flow_capital_allocation: [
    /Capital Allocation View/i,
    /Cash Quality/i,
    /Cash Flow Bridge/i,
    /Capital Allocation Scorecard/i,
    /Allocation Discipline/i,
    /Red Flags/i,
  ],
};

const LIVE_CASES = [
  { ticker: "AAPL", task: TASK_CASES[0] },
  { ticker: "MSFT", task: TASK_CASES[1] },
  { ticker: "NVDA", task: TASK_CASES[2] },
  { ticker: "AMZN", task: TASK_CASES[0] },
  { ticker: "GOOGL", task: TASK_CASES[1] },
  { ticker: "META", task: TASK_CASES[2] },
  { ticker: "TSLA", task: TASK_CASES[0] },
  { ticker: "JPM", task: TASK_CASES[1] },
  { ticker: "V", task: TASK_CASES[2] },
  { ticker: "UNH", task: TASK_CASES[0] },
] as const;

test.use({ screenshot: "off", trace: "off", video: "off" });

async function submitTicker(page: import("@playwright/test").Page, ticker: string) {
  await page.goto("/app");
  await page.locator("select").selectOption("en");
  const tickerInput = page.getByPlaceholder("Enter Ticker (e.g., AAPL, MSFT, TSLA)");
  await tickerInput.fill(ticker);
  await page.getByRole("button", { name: "Analyze ticker" }).click();
}

async function waitForAllAgentResponses(
  page: import("@playwright/test").Page,
  analyzeResponses: string[],
) {
  await expect
    .poll(() => analyzeResponses.length, {
      timeout: 420_000,
      message: "all three live agent responses should return",
    })
    .toBe(3);
}

test.describe("Spring Alpha live 10 ticker output-line matrix", () => {
  test.skip(
    !liveEnabled,
    "Set RUN_LIVE_OUTPUT_MATRIX=true to run live provider-backed output-line E2E.",
  );
  test.skip(
    liveEnabled && !liveSiliconFlowKey,
    "Set SILICONFLOW_API_KEY to run live provider-backed output-line E2E.",
  );

  test.beforeEach(async ({ page }) => {
    await page.addInitScript((key) => {
      window.localStorage.setItem("spring-alpha-siliconflow-key", key);
    }, liveSiliconFlowKey);
  });

  for (const liveCase of LIVE_CASES) {
    test(`${liveCase.ticker} validates ${liveCase.task.taskType} output quality from live backend`, async ({
      page,
    }, testInfo) => {
      testInfo.setTimeout(480_000);

      const analyzeRequests: string[] = [];
      const analyzeResponses: string[] = [];
      page.on("request", (request) => {
        const url = request.url();
        if (url.includes("/api/sec/analyze/")) {
          analyzeRequests.push(url);
        }
      });
      page.on("response", (response) => {
        const url = response.url();
        if (url.includes("/api/sec/analyze/")) {
          analyzeResponses.push(`${response.status()} ${url}`);
        }
      });

      await submitTicker(page, liveCase.ticker);
      await expect(page.getByText("Saved")).toBeVisible();

      await waitForAllAgentResponses(page, analyzeResponses);
      expect(analyzeResponses.every((entry) => entry.startsWith("200 "))).toBe(
        true,
      );
      expect(analyzeRequests.length).toBe(3);
      expect(analyzeRequests.join("\n")).toContain(liveCase.task.taskType);

      await expect(page.getByText(`${liveCase.ticker} Market Chart`)).toBeVisible();
      await expect(page.getByRole("tab", { name: /market chart/i })).toHaveAttribute(
        "aria-selected",
        "true",
      );
      await page.getByRole("tab", { name: liveCase.task.tabName }).click();

      await expect(
        page.getByRole("heading", {
          name: new RegExp(`${liveCase.ticker} Analysis Report`, "i"),
        }),
      ).toBeVisible();

      const bodyText =
        (await page.locator("body").innerText({ timeout: 10_000 })) ?? "";

      expect(bodyText).toContain(liveCase.ticker);
      for (const forbiddenPattern of FORBIDDEN_OUTPUT_PATTERNS) {
        expect(bodyText).not.toMatch(forbiddenPattern);
      }

      for (const componentPattern of liveCase.task.requiredComponents) {
        expect(bodyText).toMatch(componentPattern);
      }
      for (const qualityPattern of liveCase.task.qualitySignals) {
        expect(bodyText).toMatch(qualityPattern);
      }

      expect(bodyText).not.toMatch(/Trust Summary/i);
      expect(bodyText).not.toMatch(/Evidence Count/i);
      expect(bodyText).not.toMatch(/Supported Citations/i);
      expect(bodyText).not.toMatch(/Partial \/ Missing/i);

      for (const requiredPattern of REQUIRED_BY_TASK[liveCase.task.taskType]) {
        await expect(page.getByText(requiredPattern).first()).toBeVisible();
      }

      await expect(
        page.getByRole("region", { name: /messages and tools/i }),
      ).toContainText(/Reasoning|Tool/i);
      await page.getByRole("button", { name: /developer diagnostics/i }).click();
      await expect(page.getByText("Live RAG Telemetry")).toBeVisible();
      await expect(page.getByText("Evidence Retrieved")).toBeVisible();
      await expect(page.getByText("Evidence Used")).toBeVisible();
      await expect(page.getByText("Metric Facts")).toBeVisible();
      await expect(page.getByText("Evidence Pack Size")).toBeVisible();

      await expect(page.getByText(liveCase.task.reportHeading).first()).toBeVisible();
    });
  }
});
