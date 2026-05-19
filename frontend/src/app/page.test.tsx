import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/components/app/earnings-analyst-app";

vi.mock("@/components/pdf/PdfDownloadButton", () => ({
  PdfDownloadButton: () => <button type="button">pdf</button>,
}));

vi.mock("next-auth/react", () => ({
  useSession: () => ({ data: null, status: "unauthenticated" }),
  signIn: vi.fn(),
  signOut: vi.fn(),
  SessionProvider: ({ children }: { children: React.ReactNode }) => children,
}));

const chartTimeScaleMock = {
  fitContent: vi.fn(),
  scrollToRealTime: vi.fn(),
  setVisibleLogicalRange: vi.fn(),
};

vi.mock("lightweight-charts", () => ({
  CandlestickSeries: "CandlestickSeries",
  ColorType: {
    Solid: "solid",
  },
  CrosshairMode: {
    Normal: 0,
  },
  HistogramSeries: "HistogramSeries",
  LineStyle: {
    Dashed: 2,
  },
  createChart: vi.fn(() => ({
    addSeries: vi.fn(() => ({
      priceScale: vi.fn(() => ({
        applyOptions: vi.fn(),
      })),
      setData: vi.fn(),
    })),
    applyOptions: vi.fn(),
    remove: vi.fn(),
    subscribeCrosshairMove: vi.fn(),
    timeScale: vi.fn(() => chartTimeScaleMock),
  })),
}));

function createSseResponse(payloads: unknown[]): Response {
  const body = payloads
    .map((payload) => `data: ${JSON.stringify(payload)}\n`)
    .join("");
  return new Response(body, {
    status: 200,
    headers: { "Content-Type": "text/event-stream" },
  });
}

function createDeferredResponse() {
  let resolve!: (response: Response) => void;
  let reject!: (error: unknown) => void;

  const promise = new Promise<Response>((res, rej) => {
    resolve = res;
    reject = rej;
  });

  return { promise, resolve, reject };
}

function latestTaskSections(headline: string, summary = `${headline} summary.`) {
  return {
    schemaVersion: "task_sections.v1",
    taskType: "latest_earnings_readout",
    coverage: {
      status: "complete",
      missingSections: [],
      evidenceCount: 1,
    },
    latestEarnings: {
      toplineVerdict: {
        headline,
        verdict: "mixed",
        summary,
      },
      keyTakeaways: [],
      financialDashboard: {
        metrics: [],
        chartFocus: [],
      },
      driverSnapshot: [],
      riskSnapshot: [],
    },
  };
}

function openAgentReport(name: RegExp) {
  fireEvent.click(screen.getByRole("tab", { name }));
}

function submitTicker(ticker = "AAPL") {
  fireEvent.change(screen.getByPlaceholderText(/enter ticker/i), {
    target: { value: ticker },
  });
  fireEvent.click(screen.getByRole("button", { name: /analyze/i }));
}

describe("Home page", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    chartTimeScaleMock.fitContent.mockClear();
    chartTimeScaleMock.scrollToRealTime.mockClear();
    chartTimeScaleMock.setVisibleLogicalRange.mockClear();
    window.localStorage.clear();
    window.localStorage.setItem("spring-alpha-siliconflow-key", "sk-test-123");
  });

  it("starts with an empty ticker state instead of defaulting to AAPL", () => {
    const fetchMock = vi.fn(async () => {
      return new Response(JSON.stringify({ candles: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    expect(
      screen.getByPlaceholderText("Enter Ticker (e.g., AAPL, MSFT, TSLA)"),
    ).toHaveValue("");
    expect(
      screen.queryByText(/AAPL market chart/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/enter a ticker to load the market chart/i),
    ).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith(
      expect.stringContaining("/api/market/chart/AAPL"),
      expect.anything(),
    );
  });

  it("keeps the analyze button inset inside the ticker input", () => {
    vi.stubGlobal("fetch", vi.fn());

    render(<Home />);

    expect(screen.getByTestId("ticker-input-group")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /analyze ticker/i })).toHaveClass(
      "mr-2",
    );
  });

  it("selects a SiliconFlow model and forwards it with analysis requests", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Apple report.",
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          taskSections: latestTaskSections("Apple thesis"),
        },
      ]);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    fireEvent.click(
      screen.getByRole("radio", { name: /deepseek v4 flash/i }),
    );
    submitTicker("AAPL");

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(
          "llmModel=deepseek-ai%2Fdeepseek-v4-flash",
        ),
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      );
    });
  });

  it("shows a masked saved-key state after the provider key is saved", () => {
    window.localStorage.removeItem("spring-alpha-siliconflow-key");
    vi.stubGlobal("fetch", vi.fn());

    render(<Home />);

    fireEvent.change(screen.getByPlaceholderText("Enter your SiliconFlow key"), {
      target: { value: "sk-siliconflow-secret-1234" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^save$/i }));

    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(screen.getByText("Saved locally")).toBeInTheDocument();
    expect(screen.getByText("••••••••••••1234")).toBeInTheDocument();
    expect(
      screen.queryByPlaceholderText("Enter your SiliconFlow key"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /change key/i }),
    ).toBeInTheDocument();
  });

  it("keeps degraded source metadata hidden from the quarterly-only analysis stream", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Tesla remained under pressure.",
          companyName: "Tesla, Inc.",
          period: "Q1 2026",
          filingDate: "2026-03-31",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          metadata: {
            modelName: "gpt-4o-mini",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
          sourceContext: {
            status: "DEGRADED",
            message:
              "SEC filing was available, but semantic grounding was not ready yet.",
          },
          taskSections: latestTaskSections(
            "Typed degraded thesis",
            "Tesla remained under pressure.",
          ),
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker("TSLA");

    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Tesla, Inc. · Q1 2026 · 2026-03-31"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(
        "SEC filing was available, but semantic grounding was not ready yet.",
      ),
    ).not.toBeInTheDocument();
    expect(screen.getByText("Typed degraded thesis")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/sec/analyze/TSLA?lang=en&model=siliconflow"),
      expect.anything(),
    );
  });

  it("routes analysis through the local SSE bridge", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Quarterly report.",
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          metadata: {
            modelName: "gpt-4o-mini",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
          taskSections: latestTaskSections("Typed route thesis"),
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker("AAPL");

    openAgentReport(/latest earnings readout/i);

    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Apple Inc. · Q1 2026 · 2026-02-01"),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sec/analyze/AAPL?lang=en&model=siliconflow&llmModel=Pro%2Fmoonshotai%2FKimi-K2.6&taskType=latest_earnings_readout",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("auto-starts analysis when opened with a landing ticker", async () => {
    const taskOrder: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/tickers/search")) {
        return new Response(JSON.stringify({ suggestions: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/api/market/chart/")) {
        return new Response(JSON.stringify({ candles: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      const taskType = new URL(`http://test${url}`).searchParams.get(
        "taskType",
      );
      if (taskType) taskOrder.push(taskType);

      return createSseResponse([
        {
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          citations: [],
          taskSections: latestTaskSections("Auto-started thesis"),
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home initialTicker="aapl" />);

    expect(screen.getByPlaceholderText(/enter ticker/i)).toHaveValue("AAPL");
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/sec/analyze/AAPL?lang=en&model=siliconflow&llmModel=Pro%2Fmoonshotai%2FKimi-K2.6&taskType=latest_earnings_readout",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      ),
    );
    await waitFor(() =>
      expect(taskOrder).toEqual([
        "latest_earnings_readout",
        "business_driver_deep_dive",
        "cash_flow_capital_allocation",
      ]),
    );
  });

  it("runs all three research agents sequentially from one ticker submission", async () => {
    const taskOrder: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      const taskType = new URL(`http://test${url}`).searchParams.get(
        "taskType",
      );
      if (taskType) taskOrder.push(taskType);

      if (taskType === "business_driver_deep_dive") {
        return createSseResponse([
          {
            executiveSummary: "Business driver report.",
            companyName: "Apple Inc.",
            period: "Q1 2026",
            filingDate: "2026-02-01",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            taskSections: {
              schemaVersion: "task_sections.v1",
              taskType,
              coverage: {
                status: "complete",
                missingSections: [],
                evidenceCount: 1,
              },
              businessDriver: {
                driverThesis: {
                  headline: "Business driver agent thesis",
                  durability: "durable",
                  summary: "Business driver agent summary.",
                },
                driverMap: {
                  product: [],
                  segment: [],
                  geography: [],
                  demand: [],
                  pricing: [],
                  customer: [],
                  strategy: [],
                },
                positiveSignals: [],
                negativeSignals: [],
                watchlist: [],
              },
            },
          },
        ]);
      }

      if (taskType === "cash_flow_capital_allocation") {
        return createSseResponse([
          {
            executiveSummary: "Cash flow report.",
            companyName: "Apple Inc.",
            period: "Q1 2026",
            filingDate: "2026-02-01",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            taskSections: {
              schemaVersion: "task_sections.v1",
              taskType,
              coverage: {
                status: "complete",
                missingSections: [],
                evidenceCount: 1,
              },
              cashFlowCapitalAllocation: {
                cashQualityVerdict: {
                  headline: "Cash flow agent verdict",
                  earningsBackedByCash: "mixed",
                  summary: "Cash flow agent summary.",
                },
                cashMetrics: [],
                capitalAllocation: {
                  capex: [],
                  buybacks: [],
                  dividends: [],
                  debt: [],
                  liquidity: [],
                },
                allocationDiscipline: [],
                redFlags: [],
              },
            },
          },
        ]);
      }

      return createSseResponse([
        {
          executiveSummary: "Latest earnings report.",
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          taskSections: latestTaskSections("Earnings agent verdict"),
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker("TSLA");

    openAgentReport(/latest earnings readout/i);
    expect(await screen.findByText("Earnings agent verdict")).toBeInTheDocument();
    openAgentReport(/business driver deep dive/i);
    expect(await screen.findByText("Business driver agent thesis")).toBeInTheDocument();
    openAgentReport(/cash flow & capital allocation/i);
    expect(await screen.findByText("Cash flow agent verdict")).toBeInTheDocument();
    expect(taskOrder).toEqual([
      "latest_earnings_readout",
      "business_driver_deep_dive",
      "cash_flow_capital_allocation",
    ]);
  });

  it("surfaces degraded agent evidence when the backend returns a no-report chunk", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      const taskType = new URL(`http://test${url}`).searchParams.get(
        "taskType",
      );

      if (taskType === "business_driver_deep_dive") {
        return createSseResponse([
          {
            executiveSummary: "Business driver report.",
            companyName: "Apple Inc.",
            period: "Q1 2026",
            filingDate: "2026-02-01",
            citations: [],
            taskSections: {
              schemaVersion: "task_sections.v1",
              taskType,
              coverage: {
                status: "complete",
                missingSections: [],
                evidenceCount: 1,
              },
              businessDriver: {
                driverThesis: {
                  headline: "Business driver agent thesis",
                  durability: "durable",
                  summary: "Business driver agent summary.",
                },
                driverMap: {
                  product: [],
                  segment: [],
                  geography: [],
                  demand: [],
                  pricing: [],
                  customer: [],
                  strategy: [],
                },
                positiveSignals: [],
                negativeSignals: [],
                watchlist: [],
              },
            },
          },
        ]);
      }

      if (taskType === "cash_flow_capital_allocation") {
        return createSseResponse([
          {
            executiveSummary: "Cash flow research agent failed: validation error",
            sourceContext: {
              status: "DEGRADED",
              message: "Cash flow research agent failed: validation error",
            },
            metadata: {
              agentEvents: [
                {
                  phase: "degraded",
                  status: "degraded",
                  summary: "Cash flow research agent failed.",
                  eventKind: "reasoning",
                  agentName: "Cash Flow Analyst",
                  degradedReason:
                    "Cash flow research agent failed: validation error",
                },
              ],
            },
          },
        ]);
      }

      return createSseResponse([
        {
          executiveSummary: "Latest earnings report.",
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          citations: [],
          taskSections: latestTaskSections("Earnings agent verdict"),
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker("TSLA");

    expect(
      await screen.findByRole("tab", {
        name: /cash flow & capital allocation/i,
      }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText("Cash flow research agent failed: validation error"),
    ).toBeInTheDocument();
    expect(await screen.findByText("Cash Flow Analyst")).toBeInTheDocument();
  });

  it("shows the submitted ticker market chart and opens an agent report from the sidebar", async () => {
    const taskOrder: string[] = [];
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/market/chart/")) {
        return new Response(
          JSON.stringify({
            candles: Array.from({ length: 150 }, (_, index) => ({
              date: `2026-05-${String((index % 28) + 1).padStart(2, "0")}`,
              open: 100 + index,
              high: 112 + index,
              low: 98 + index,
              close: 108 + index,
              volume: 123456 + index,
            })),
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      if (url.includes("/api/market/chart/")) {
        return new Response(
          JSON.stringify({
            candles: Array.from({ length: 150 }, (_, index) => ({
              date: `2026-05-${String((index % 28) + 1).padStart(2, "0")}`,
              open: 100 + index,
              high: 112 + index,
              low: 98 + index,
              close: 108 + index,
              volume: 123456 + index,
            })),
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      const taskType = new URL(`http://test${url}`).searchParams.get(
        "taskType",
      );
      if (taskType) taskOrder.push(taskType);

      if (taskType === "business_driver_deep_dive") {
        return createSseResponse([
          {
            companyName: "Apple Inc.",
            period: "Q1 2026",
            filingDate: "2026-02-01",
            citations: [],
            taskSections: {
              schemaVersion: "task_sections.v1",
              taskType,
              coverage: {
                status: "complete",
                missingSections: [],
                evidenceCount: 1,
              },
              businessDriver: {
                driverThesis: {
                  headline: "Business driver agent thesis",
                  durability: "durable",
                  summary: "Business driver agent summary.",
                },
                driverMap: {
                  product: [],
                  segment: [],
                  geography: [],
                  demand: [],
                  pricing: [],
                  customer: [],
                  strategy: [],
                },
                positiveSignals: [],
                negativeSignals: [],
                watchlist: [],
              },
            },
          },
        ]);
      }

      return createSseResponse([
        {
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          citations: [],
          taskSections: latestTaskSections("Earnings agent verdict"),
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker("AAPL");
    expect(await screen.findByText(/AAPL market chart/i)).toBeInTheDocument();
    expect(
      await screen.findByTestId("market-candlestick-chart"),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/scroll to zoom/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/drag to pan/i).length).toBeGreaterThan(0);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/market/chart/AAPL?interval=1d",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    await waitFor(() =>
      expect(chartTimeScaleMock.setVisibleLogicalRange).toHaveBeenCalledWith({
        from: 30,
        to: 155,
      }),
    );

    fireEvent.click(screen.getByRole("tab", { name: "1W" }));
    fireEvent.click(screen.getByRole("tab", { name: "1M" }));
    fireEvent.click(screen.getByRole("tab", { name: "1Y" }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/market/chart/AAPL?interval=1y",
        expect.objectContaining({ signal: expect.any(AbortSignal) }),
      ),
    );
    expect(chartTimeScaleMock.fitContent).not.toHaveBeenCalled();

    await waitFor(() =>
      expect(taskOrder).toEqual([
        "latest_earnings_readout",
        "business_driver_deep_dive",
        "cash_flow_capital_allocation",
      ]),
    );
    expect(screen.getByText(/AAPL market chart/i)).toBeInTheDocument();
    expect(screen.queryByText("Earnings agent verdict")).not.toBeInTheDocument();
    expect(screen.queryByText("Business driver agent thesis")).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("tab", { name: /latest earnings readout/i }),
    );

    expect(await screen.findByText("Earnings agent verdict")).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("tab", { name: /business driver deep dive/i }),
    );

    expect(
      await screen.findByText("Business driver agent thesis"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Earnings agent verdict")).not.toBeInTheDocument();
  });

  it("renders the agent pipeline and submits all task types", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Business driver report.",
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          metadata: {
            modelName: "gpt-4o-mini",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    expect(
      screen.getByRole("region", { name: /agent pipeline/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Latest Earnings Readout")).toBeInTheDocument();
    expect(screen.getByText("Business Driver Deep Dive")).toBeInTheDocument();
    expect(screen.getByText("Cash Flow & Capital Allocation")).toBeInTheDocument();

    submitTicker();
    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Apple Inc. · Q1 2026 · 2026-02-01"),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sec/analyze/AAPL?lang=en&model=siliconflow&llmModel=Pro%2Fmoonshotai%2FKimi-K2.6&taskType=latest_earnings_readout",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sec/analyze/AAPL?lang=en&model=siliconflow&llmModel=Pro%2Fmoonshotai%2FKimi-K2.6&taskType=business_driver_deep_dive",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sec/analyze/AAPL?lang=en&model=siliconflow&llmModel=Pro%2Fmoonshotai%2FKimi-K2.6&taskType=cash_flow_capital_allocation",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("shows ticker suggestions from the server ticker catalog", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/tickers/search")) {
        return new Response(
          JSON.stringify({
            suggestions: [
              {
                ticker: "LLY",
                companyName: "Eli Lilly and Company",
              },
            ],
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      return new Response(JSON.stringify([]), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    fireEvent.change(screen.getByPlaceholderText(/enter ticker/i), {
      target: { value: "lil" },
    });

    const option = await screen.findByRole("option", {
      name: /LLY Eli Lilly and Company/i,
    });
    expect(option).toBeInTheDocument();
    expect(screen.getByText("LLY")).toBeInTheDocument();
    expect(screen.getByText("Eli Lilly and Company")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tickers/search?q=LIL&limit=8",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );

    fireEvent.click(option);

    expect(screen.getByPlaceholderText(/enter ticker/i)).toHaveValue("LLY");
  });

  it("renders task-specific report sections after selecting different research tasks", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      const taskType = new URL(`http://test${url}`).searchParams.get(
        "taskType",
      );
      return createSseResponse([
        {
          executiveSummary: `${taskType} report.`,
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          keyMetrics: [
            {
              metricName: "Revenue",
              value: "$100B",
              interpretation: "Revenue increased.",
              sentiment: "positive",
            },
            {
              metricName: "Operating Cash Flow",
              value: "$30B",
              interpretation: "Cash conversion improved.",
              sentiment: "positive",
            },
            {
              metricName: "Capital Expenditures",
              value: "$3B",
              interpretation: "Capex remained disciplined.",
              sentiment: "neutral",
            },
          ],
          businessDrivers: [
            {
              title: "Services momentum",
              description: "Services demand improved.",
              impact: "high",
            },
          ],
          riskFactors: [
            {
              category: "Competition",
              description: "Competition remains elevated.",
              severity: "medium",
            },
          ],
          citations: [],
          bullCase: "Bull case.",
          bearCase: "Bear case.",
          metadata: {
            modelName: "gpt-4o-mini",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    submitTicker();

    openAgentReport(/business driver deep dive/i);

    expect(
      (await screen.findAllByText("Missing typed taskSections")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/Business Driver Deep Dive report did not include/i)).toBeInTheDocument();
    expect(screen.queryByText("Business Driver Research View")).not.toBeInTheDocument();
    expect(screen.queryByTestId("business-drivers")).not.toBeInTheDocument();
    expect(screen.queryByTestId("key-metrics")).not.toBeInTheDocument();
    expect(screen.queryByTestId("dupont-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("bull-bear-case")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Capital Allocation View"),
    ).not.toBeInTheDocument();

    openAgentReport(/cash flow & capital allocation/i);

    expect(screen.getAllByText("Missing typed taskSections").length).toBeGreaterThan(0);
    expect(screen.getByText(/Cash Flow & Capital Allocation report did not include/i)).toBeInTheDocument();
    expect(screen.queryByText("Capital Allocation View")).not.toBeInTheDocument();
    expect(screen.queryByTestId("business-drivers")).not.toBeInTheDocument();
    expect(screen.queryByTestId("key-metrics")).not.toBeInTheDocument();
    expect(screen.queryByTestId("dupont-chart")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Business Driver Research View"),
    ).not.toBeInTheDocument();
  });

  it("prefers typed task sections over legacy inferred report fields", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Legacy business summary.",
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          keyMetrics: [],
          businessDrivers: [
            {
              title: "Legacy services momentum",
              description: "Legacy driver should not be the primary source.",
              impact: "high",
            },
          ],
          riskFactors: [],
          citations: [],
          bullCase: "Bull case.",
          bearCase: "Bear case.",
          taskSections: {
            schemaVersion: "task_sections.v1",
            taskType: "business_driver_deep_dive",
            coverage: {
              status: "complete",
              missingSections: [],
              evidenceCount: 1,
            },
            businessDriver: {
              driverThesis: {
                headline: "Typed driver thesis",
                durability: "durable",
                summary: "Typed driver summary.",
              },
              driverMap: {
                product: [
                  {
                    title: "Typed product signal",
                    summary: "Typed product evidence.",
                    evidenceRefs: [],
                    citationStatus: "supported",
                  },
                ],
                segment: [],
                geography: [],
                demand: [],
                pricing: [],
                customer: [],
                strategy: [],
              },
              positiveSignals: [],
              negativeSignals: [],
              watchlist: ["Track typed product adoption."],
            },
          },
          metadata: {
            modelName: "gpt-4o-mini",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    submitTicker();

    openAgentReport(/business driver deep dive/i);

    expect(await screen.findByText("Typed driver thesis")).toBeInTheDocument();
    expect(screen.getAllByText("Typed product signal").length).toBeGreaterThan(
      0,
    );
    expect(
      screen.getByText("Track typed product adoption."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Legacy services momentum"),
    ).not.toBeInTheDocument();
  });

  it("prefers typed latest earnings synthesis over legacy dashboard placeholders", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Legacy latest earnings summary.",
          companyName: "Apple Inc.",
          period: "Q2 2026",
          filingDate: "2026-05-01",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          bullCase: "Bull case.",
          bearCase: "Bear case.",
          taskSections: {
            schemaVersion: "task_sections.v1",
            taskType: "latest_earnings_readout",
            coverage: {
              status: "complete",
              missingSections: [],
              evidenceCount: 3,
            },
            latestEarnings: {
              companyProfile: {
                summary:
                  "Apple Inc. designs consumer devices, software, and services across a global installed base.",
                evidenceRefs: [],
                citationStatus: "supported",
              },
              toplineVerdict: {
                headline: "Typed latest earnings thesis",
                verdict: "mixed",
                summary: "Typed latest earnings summary.",
              },
              keyTakeaways: [
                {
                  title: "Typed revenue takeaway",
                  summary: "Typed revenue evidence.",
                  evidenceRefs: [],
                  citationStatus: "supported",
                },
              ],
              financialDashboard: {
                metrics: [
                  {
                    name: "Typed revenue metric",
                    value: 219659000000,
                    period: "latest quarter",
                    interpretation: "Typed metric interpretation.",
                    evidenceRefs: [],
                    citationStatus: "supported",
                  },
                ],
                chartFocus: ["revenue"],
              },
              driverSnapshot: [
                {
                  title: "Typed services driver",
                  summary: "Typed services evidence.",
                  evidenceRefs: [],
                  citationStatus: "supported",
                },
              ],
              riskSnapshot: [
                {
                  title: "Typed risk snapshot",
                  summary: "Typed risk evidence.",
                  evidenceRefs: [],
                  citationStatus: "partial",
                },
              ],
            },
          },
          metadata: {
            modelName: "python-research-service",
            language: "en",
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker();

    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Typed latest earnings thesis"),
    ).toBeInTheDocument();
    expect(screen.getByText("Company Profile")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Apple Inc. designs consumer devices, software, and services across a global installed base.",
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Earnings Verdict").length).toBeGreaterThan(0);
    expect(screen.getAllByText("KPI Strip").length).toBeGreaterThan(0);
    expect(screen.getAllByText("What Changed").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Watch Next").length).toBeGreaterThan(0);
    expect(screen.queryByText("Trust Summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence Count")).not.toBeInTheDocument();
    expect(screen.getByText("Typed revenue takeaway")).toBeInTheDocument();
    expect(screen.getByText("Typed revenue metric")).toBeInTheDocument();
    expect(screen.getByText("$219.7B")).toBeInTheDocument();
    expect(screen.queryByText("219659000000")).not.toBeInTheDocument();
    expect(screen.getByText("Typed services driver")).toBeInTheDocument();
    expect(screen.getByText("Typed risk snapshot")).toBeInTheDocument();
    expect(
      screen.queryByText(/Waiting for the model/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/1970/i)).not.toBeInTheDocument();
  });

  it("renders agent messages and tools in the side timeline", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Agent completed.",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          taskSections: {
            schemaVersion: "task_sections.v1",
            taskType: "latest_earnings_readout",
            coverage: {
              status: "complete",
              missingSections: [],
              evidenceCount: 1,
            },
            latestEarnings: {
              toplineVerdict: {
                headline: "Typed thesis",
                verdict: "mixed",
                summary: "Typed summary.",
              },
              keyTakeaways: [],
              financialDashboard: {
                metrics: [],
                chartFocus: [],
              },
              driverSnapshot: [],
              riskSnapshot: [],
            },
          },
          metadata: {
            modelName: "python-research-service",
            language: "en",
            agentEvents: [
              {
                phase: "build_evidence_plan",
                status: "ok",
                summary: "The analyst planned the next evidence step.",
                eventKind: "reasoning",
                agentName: "Earnings Analyst",
                modelName: "test-model",
                usage: {
                  prompt_tokens: 1416,
                  completion_tokens: 53,
                },
                latencyMs: 1000,
              },
              {
                phase: "retrieve_evidence",
                status: "ok",
                summary: "Searched SEC filing sections.",
                eventKind: "tool",
                agentName: "Earnings Analyst",
                toolName: "search_filing_sections",
                toolInput: {
                  sections: ["MD&A"],
                  query: "revenue margin",
                },
                latencyMs: 2000,
              },
            ],
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker();

    openAgentReport(/latest earnings readout/i);

    expect(await screen.findByText("Typed thesis")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: /messages and tools/i })).toBeInTheDocument();
    expect(screen.getAllByText("Messages & Tools").length).toBeGreaterThan(0);
    expect(screen.getByText("test-model: 1416 in, 53 out")).toBeInTheDocument();
    expect(
      screen.getByText(
        'search_filing_sections: {"sections":["MD&A"],"query":"revenue margin"}',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("Agent Progress")).not.toBeInTheDocument();
  });

  it("aggregates messages and tools from every completed agent by default", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      const taskType = new URL(`http://test${url}`).searchParams.get(
        "taskType",
      );
      if (taskType === "business_driver_deep_dive") {
        return createSseResponse([
          {
            companyName: "Apple Inc.",
            period: "Q1 2026",
            filingDate: "2026-02-01",
            taskSections: {
              schemaVersion: "task_sections.v1",
              taskType,
              coverage: { status: "complete", missingSections: [], evidenceCount: 1 },
              businessDriver: {
                driverThesis: {
                  headline: "Business thesis",
                  durability: "durable",
                  summary: "Business summary.",
                },
                driverMap: {
                  product: [],
                  segment: [],
                  geography: [],
                  demand: [],
                  pricing: [],
                  customer: [],
                  strategy: [],
                },
                positiveSignals: [],
                negativeSignals: [],
                watchlist: [],
              },
            },
            metadata: {
              agentEvents: [
                {
                  phase: "business_reasoning",
                  status: "ok",
                  summary: "Business agent selected evidence tools.",
                  eventKind: "reasoning",
                  agentName: "Business driver agent",
                  modelName: "test-business-model",
                  latencyMs: 1000,
                },
              ],
            },
          },
        ]);
      }

      if (taskType === "cash_flow_capital_allocation") {
        return createSseResponse([
          {
            companyName: "Apple Inc.",
            period: "Q1 2026",
            filingDate: "2026-02-01",
            taskSections: {
              schemaVersion: "task_sections.v1",
              taskType,
              coverage: { status: "complete", missingSections: [], evidenceCount: 1 },
              cashFlowCapitalAllocation: {
                cashGeneration: {
                  headline: "Cash thesis",
                  quality: "strong",
                  summary: "Cash summary.",
                },
                cashMetrics: [],
                capitalAllocation: [],
                allocationDiscipline: {
                  headline: "Disciplined",
                  strengths: [],
                  weaknesses: [],
                  investorImplication: "Balanced.",
                },
                watchlist: [],
              },
            },
            metadata: {
              agentEvents: [
                {
                  phase: "cash_reasoning",
                  status: "ok",
                  summary: "Cash flow agent selected evidence tools.",
                  eventKind: "reasoning",
                  agentName: "Cash flow agent",
                  modelName: "test-cash-model",
                  latencyMs: 1000,
                },
              ],
            },
          },
        ]);
      }

      return createSseResponse([
        {
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          taskSections: latestTaskSections("Earnings thesis"),
          metadata: {
            agentEvents: [
              {
                phase: "earnings_reasoning",
                status: "ok",
                summary: "Earnings agent selected evidence tools.",
                eventKind: "reasoning",
                agentName: "Earnings agent",
                modelName: "test-earnings-model",
                latencyMs: 1000,
              },
            ],
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker();

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([input]) =>
          String(input).includes("/api/sec/analyze/AAPL"),
        ),
      ).toHaveLength(3);
    });
    expect(screen.getByText("Earnings agent")).toBeInTheDocument();
    expect(screen.getByText("Business driver agent")).toBeInTheDocument();
    expect(screen.getByText("Cash flow agent")).toBeInTheDocument();
  });

  it("renders typed cash flow synthesis fields from the spring mapper envelope", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Legacy cash flow summary.",
          companyName: "Apple Inc.",
          period: "Q2 2026",
          filingDate: "2026-04-30",
          keyMetrics: [
            {
              metricName: "Legacy Free Cash Flow",
              value: "Pending",
              interpretation: "Legacy metric should not drive the typed view.",
              sentiment: "neutral",
            },
          ],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          bullCase: "Bull case.",
          bearCase: "Bear case.",
          taskSections: {
            schemaVersion: "task_sections.v1",
            taskType: "cash_flow_capital_allocation",
            coverage: {
              status: "complete",
              missingSections: [],
              evidenceCount: 2,
            },
            cashFlowCapitalAllocation: {
              cashQualityVerdict: {
                headline: "Typed cash quality verdict",
                earningsBackedByCash: "mixed",
                summary: "Typed cash conversion summary.",
              },
              cashMetrics: [
                {
                  name: "Typed operating cash flow",
                  value: "Positive",
                  period: "latest quarter",
                  interpretation: "Typed cash metric interpretation.",
                  evidenceRefs: [],
                  citationStatus: "supported",
                },
              ],
              capitalAllocation: {
                capex: [
                  {
                    title: "Typed capex signal",
                    summary: "Typed capex evidence.",
                    evidenceRefs: [],
                    citationStatus: "supported",
                  },
                ],
                buybacks: [
                  {
                    title: "Typed buyback signal",
                    summary: "Typed buyback evidence.",
                    evidenceRefs: [],
                    citationStatus: "supported",
                  },
                ],
                dividends: [],
                debt: [],
                liquidity: [
                  {
                    title: "Typed liquidity signal",
                    summary: "Typed liquidity evidence.",
                    evidenceRefs: [],
                    citationStatus: "supported",
                  },
                ],
              },
              allocationDiscipline: [
                {
                  title: "Typed allocation discipline",
                  summary: "Typed allocation discipline evidence.",
                  evidenceRefs: [],
                  citationStatus: "supported",
                },
              ],
              redFlags: [
                {
                  title: "Typed red flag",
                  summary: "Typed red flag evidence.",
                  evidenceRefs: [],
                  citationStatus: "partial",
                },
              ],
            },
          },
          metadata: {
            modelName: "python-research-service",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    submitTicker();

    openAgentReport(/cash flow & capital allocation/i);

    expect(
      await screen.findByText("Typed cash quality verdict"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Cash Quality").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Cash Flow Bridge").length).toBeGreaterThan(0);
    expect(
      screen.getAllByText("Capital Allocation Scorecard").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("Allocation Discipline").length).toBeGreaterThan(
      0,
    );
    expect(screen.getAllByText("Red Flags").length).toBeGreaterThan(0);
    expect(screen.queryByText("Trust Summary")).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence Count")).not.toBeInTheDocument();
    expect(screen.getByText("Typed operating cash flow")).toBeInTheDocument();
    expect(screen.getByText("Typed capex signal")).toBeInTheDocument();
    expect(screen.getByText("Typed buyback signal")).toBeInTheDocument();
    expect(screen.getByText("Typed liquidity signal")).toBeInTheDocument();
    expect(screen.getByText("Typed allocation discipline")).toBeInTheDocument();
    expect(screen.getByText("Typed red flag")).toBeInTheDocument();
    expect(screen.queryByText("Legacy Free Cash Flow")).not.toBeInTheDocument();
  });

  it("renders live RAG telemetry without offline benchmark scores", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          companyName: "Apple Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          taskSections: latestTaskSections("Earnings telemetry thesis"),
          ragTelemetry: {
            evidenceRetrieved: 3,
            evidenceUsed: 2,
            metricFacts: 7,
            sectionsCovered: 4,
            retrievalLatencyMs: 1280,
            emptyRetrieval: false,
            evidencePackBytes: 6144,
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker();

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.filter(([input]) =>
          String(input).includes("/api/sec/analyze/AAPL"),
        ).length,
      ).toBeGreaterThan(0);
    });

    expect(screen.queryByText("Live RAG Telemetry")).not.toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: /developer diagnostics/i }),
    );

    expect(screen.getByText("Developer diagnostics")).toBeInTheDocument();
    expect(screen.getByText("Live RAG Telemetry")).toBeInTheDocument();
    expect(screen.getByText("Evidence Retrieved")).toBeInTheDocument();
    expect(screen.getByText("Evidence Used")).toBeInTheDocument();
    expect(screen.getByText("Metric Facts")).toBeInTheDocument();
    expect(screen.getByText("Sections Covered")).toBeInTheDocument();
    expect(screen.getByText("Retrieval Latency")).toBeInTheDocument();
    expect(screen.getByText("Empty Retrieval")).toBeInTheDocument();
    expect(screen.getByText("Evidence Pack Size")).toBeInTheDocument();
    expect(screen.getByText("9")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("21")).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("3.8s")).toBeInTheDocument();
    expect(screen.getByText("No")).toBeInTheDocument();
    expect(screen.getByText("18 KB")).toBeInTheDocument();
    expect(screen.queryByText("Recall@5")).not.toBeInTheDocument();
    expect(screen.queryByText("Precision@5")).not.toBeInTheDocument();
    expect(screen.queryByText("Section Accuracy")).not.toBeInTheDocument();
    expect(screen.queryByText("Unsupported Risk")).not.toBeInTheDocument();
    expect(screen.queryByText("stage1_hard_rag_eval")).not.toBeInTheDocument();
    expect(
      screen.queryByText("hybrid_semantic_lexical_retrieval"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("RAG Eval Dashboard")).not.toBeInTheDocument();
    expect(screen.queryByText("Eval Cases")).not.toBeInTheDocument();
    expect(screen.queryByText("Stage Comparison")).not.toBeInTheDocument();
    expect(screen.queryByText("Current Limits")).not.toBeInTheDocument();
    expect(screen.queryByText("Release Readiness")).not.toBeInTheDocument();
    expect(screen.queryByText("hard_msft_semantic_platform_driver")).not.toBeInTheDocument();
  });

  it("submits the live input value instead of falling back to the stale default ticker", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Visa quarterly report.",
          companyName: "Visa Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          metadata: {
            modelName: "gpt-4o-mini",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
          taskSections: latestTaskSections("Visa typed thesis"),
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    const tickerInput = screen.getByPlaceholderText(
      /enter ticker/i,
    ) as HTMLInputElement;
    const nativeValueSetter = Object.getOwnPropertyDescriptor(
      HTMLInputElement.prototype,
      "value",
    )?.set;
    nativeValueSetter?.call(tickerInput, "V");

    fireEvent.keyDown(tickerInput, { key: "Enter" });

    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Visa Inc. · Q1 2026 · 2026-02-01"),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sec/analyze/V?lang=en&model=siliconflow&llmModel=Pro%2Fmoonshotai%2FKimi-K2.6&taskType=latest_earnings_readout",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByText("Visa typed thesis")).toBeInTheDocument();
    expect(screen.queryByTestId("key-metrics")).not.toBeInTheDocument();
  });

  it("allows one anonymous real analysis before the trial gate closes", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Anonymous trial report.",
          companyName: "Tesla, Inc.",
          period: "Q1 2026",
          filingDate: "2026-03-31",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          metadata: {
            modelName: "gpt-4o-mini",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
          taskSections: latestTaskSections("Anonymous trial thesis"),
        },
      ]);
    });

    window.localStorage.removeItem("spring-alpha-siliconflow-key");
    window.localStorage.removeItem("spring-alpha-anonymous-trial-used");
    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker("TSLA");
    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Tesla, Inc. · Q1 2026 · 2026-03-31"),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("button", { name: /sign in with google/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Free trial reached")).toBeInTheDocument();
    expect(window.localStorage.getItem("spring-alpha-anonymous-trial-used")).toBe(
      "true",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/sec/analyze/TSLA?lang=en&model=siliconflow"),
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Auth-Mode": "anonymous",
          "X-Trial-Run-Id": expect.any(String),
        }),
        signal: expect.any(AbortSignal),
      }),
    );
  });

  it("reuses one anonymous trial run id across all agent task requests", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/sec/history/")) {
          return new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
        }

        return createSseResponse([
          {
            executiveSummary: "Anonymous trial report.",
            companyName: "Apple Inc.",
            period: "Q1 2026",
            filingDate: "2026-02-01",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            taskSections: latestTaskSections("Anonymous trial thesis"),
          },
        ]);
    });

    window.localStorage.removeItem("spring-alpha-siliconflow-key");
    window.localStorage.removeItem("spring-alpha-anonymous-trial-used");
    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker("AAPL");

    let analyzeCalls: [RequestInfo | URL, RequestInit?][] = [];
    await waitFor(() => {
      analyzeCalls = fetchMock.mock.calls.filter(([input]) =>
        String(input).includes("/api/sec/analyze/AAPL"),
      );
      expect(analyzeCalls).toHaveLength(3);
    });
    const trialRunIds = analyzeCalls.map(([, init]) =>
      ((init?.headers ?? {}) as Record<string, string>)["X-Trial-Run-Id"],
    );

    expect(new Set(trialRunIds).size).toBe(1);
    expect(trialRunIds[0]).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
  });

  it("shows the login wall once the anonymous trial is already used", async () => {
    vi.stubGlobal("fetch", vi.fn());
    window.localStorage.removeItem("spring-alpha-siliconflow-key");
    window.localStorage.setItem("spring-alpha-anonymous-trial-used", "true");

    render(<Home />);

    submitTicker();

    expect(
      await screen.findByText(/your anonymous trial is over/i),
    ).toBeInTheDocument();
    expect(
      vi.mocked(global.fetch).mock.calls.some(([input]) =>
        String(input).includes("/sec/analyze/"),
      ),
    ).toBe(false);
  });

  it("shows the live run status while the real analysis request is in flight", async () => {
    const deferred = createDeferredResponse();
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.includes("taskType=latest_earnings_readout")) {
        return deferred.promise;
      }

      return createSseResponse([
        {
          executiveSummary: "Visa follow-up report.",
          companyName: "Visa Inc.",
          period: "Q1 2026",
          filingDate: "2026-02-01",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          metadata: {
            modelName: "python-research-service",
            language: "en",
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    submitTicker("V");

    expect(
      await screen.findByText("Live agent run in progress"),
    ).toBeInTheDocument();
    expect(screen.getByText("V")).toBeInTheDocument();
    expect(
      screen.getAllByText("Cash Flow & Capital Allocation").length,
    ).toBeGreaterThan(0);
    expect(screen.getAllByText("SiliconFlow").length).toBeGreaterThan(1);
    expect(screen.getByText("Backend and agent running")).toBeInTheDocument();

    act(() => {
      deferred.resolve(
        createSseResponse([
          {
            executiveSummary: "Visa cash flow report.",
            companyName: "Visa Inc.",
            period: "Q1 2026",
            filingDate: "2026-02-01",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            metadata: {
              modelName: "python-research-service",
              language: "en",
            },
          },
        ]),
      );
    });

    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Visa Inc. · Q1 2026 · 2026-02-01"),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(
        screen.queryByText("Live agent run in progress"),
      ).not.toBeInTheDocument();
    });
  });

  it("aborts in-flight requests on unmount without surfacing an error", async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      const signal = init?.signal;
      return new Promise<Response>((_resolve, reject) => {
        signal?.addEventListener("abort", () => {
          reject(new DOMException("The operation was aborted.", "AbortError"));
        });
      });
    });

    vi.stubGlobal("fetch", fetchMock);

    const consoleError = vi
      .spyOn(console, "error")
      .mockImplementation(() => {});
    const { unmount } = render(<Home />);

    submitTicker();
    unmount();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    expect(consoleError).not.toHaveBeenCalledWith(
      expect.stringContaining("Fetch Error:"),
    );
  });

  it("does not render source citations even when grounded citations exist", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Tesla stabilized margins.",
          companyName: "Tesla, Inc.",
          period: "FY 2025",
          filingDate: "2026-01-29",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          metadata: {
            modelName: "gpt-4o-mini",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
          citations: [
            {
              section: "MD&A",
              excerpt: "Revenue increased due to stronger deliveries.",
              verificationStatus: "VERIFIED",
            },
          ],
          sourceContext: {
            status: "GROUNDED",
            message: "Grounded in SEC text evidence.",
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker();

    openAgentReport(/latest earnings readout/i);

    await screen.findByText("Tesla, Inc. · FY 2025 · 2026-01-29");
    expect(
      screen.queryByText("Revenue increased due to stronger deliveries."),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("MD&A")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/Source Citations & Verification/i),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(/semantic grounding was not ready yet/i),
    ).not.toBeInTheDocument();
  });

  it("does not render source-context fallback messaging when citations are absent", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Microsoft delivered resilient growth.",
          companyName: "Microsoft Corporation",
          period: "Q2 2026",
          filingDate: "2026-01-31",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          metadata: {
            modelName: "llama-3.3-70b-versatile",
            generatedAt: "2026-03-10T14:00:00",
            language: "en",
          },
          citations: [],
          sourceContext: {
            status: "LIMITED",
            message:
              "SEC source evidence was retrieved, but this run did not retain a display-ready high-confidence verbatim quote. The analysis remains grounded in the filing.",
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker();
    openAgentReport(/latest earnings readout/i);

    await screen.findByText("Microsoft Corporation · Q2 2026 · 2026-01-31");
    expect(
      screen.queryByText(
        /did not retain a display-ready high-confidence verbatim quote/i,
      ),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText(
        /Current status: grounded evidence, citation display limited/i,
      ),
    ).not.toBeInTheDocument();
  });

  it("sends the saved provider key when BYOK mode is used", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Tesla remained under pressure.",
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
          citations: [],
          metadata: {
            modelName: "gpt-4o-mini",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    fireEvent.click(screen.getByRole("button", { name: /change key/i }));
    fireEvent.change(
      screen.getByPlaceholderText(/enter your siliconflow key/i),
      {
        target: { value: "sk-test-123" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: /save/i }));

    expect(screen.getByText("Saved")).toBeInTheDocument();
    expect(screen.getByText("Saved locally")).toBeInTheDocument();
    expect(screen.getByText("••••••••••••-123")).toBeInTheDocument();

    submitTicker();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/sec/analyze/"),
        expect.objectContaining({
          headers: { "X-Provider-API-Key": "sk-test-123" },
          signal: expect.any(AbortSignal),
        }),
      );
    });
  });

  it("surfaces explicit invalid-key errors for BYOK providers instead of rendering an empty report shell", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return new Response(
        JSON.stringify({
          error:
            "SiliconFlow API key is invalid or unauthorized for this project",
          code: "SILICONFLOW_API_KEY_INVALID",
          source: "siliconflow",
        }),
        {
          status: 401,
          headers: { "Content-Type": "application/json" },
        },
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    fireEvent.click(screen.getByRole("button", { name: /change key/i }));
    fireEvent.change(
      screen.getByPlaceholderText(/enter your siliconflow key/i),
      {
        target: { value: "sk-invalid-test" },
      },
    );
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    submitTicker();

    expect(
      await screen.findByText(
        /SiliconFlow API key is invalid or unauthorized for this project/i,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Analysis Report/i)).not.toBeInTheDocument();
  });

  it("surfaces backend dependency errors instead of a generic internal server error", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return new Response(
        JSON.stringify({
          error: "SEC company facts are temporarily unavailable.",
          code: "SEC_DATA_UNAVAILABLE",
          source: "sec",
        }),
        {
          status: 503,
          headers: { "Content-Type": "application/json" },
        },
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker();

    expect(
      await screen.findByText(/SEC company facts are temporarily unavailable/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/internal server error/i),
    ).not.toBeInTheDocument();
  });

  it("surfaces Python Research Service unavailable errors as degraded agent status", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return new Response(
        JSON.stringify({
          error:
            "Python Research Service is unavailable. Analysis cannot be generated right now.",
          code: "RESEARCH_SERVICE_UNAVAILABLE",
          source: "python-research-service",
          degraded: true,
        }),
        {
          status: 503,
          headers: { "Content-Type": "application/json" },
        },
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker();

    expect(
      await screen.findByText(/Python Research Service unavailable/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/Agent degraded/i)).toBeInTheDocument();
    expect(screen.getByText(/python-research-service/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Analysis cannot be generated right now/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Analysis Report/i)).not.toBeInTheDocument();
  });

  it("parses SSE-style proxy error bodies before rendering dependency errors", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return new Response(
        'data:{"error":"Python Research Service is unavailable: Did not observe any item or terminal signal within 180000ms in flatMap","source":"python-research-service","code":"RESEARCH_SERVICE_UNAVAILABLE","degraded":true}',
        {
          status: 503,
          headers: { "Content-Type": "text/plain" },
        },
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker();

    expect(
      await screen.findByText(/Python Research Service unavailable/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/The research agent took too long/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/data:\{/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/flatMap/i)).not.toBeInTheDocument();
  });

  it("does not request legacy history data for the removed dashboard fallback", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);

      return Promise.resolve(
        createSseResponse([
          {
            executiveSummary: "stub summary",
            companyName: url.includes("/MSFT")
              ? "Microsoft Corporation"
              : "Tesla, Inc.",
            period: "FY 2025",
            filingDate: "2026-01-29",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            metadata: {
              modelName: "gpt-4o-mini",
              generatedAt: "2026-03-09T10:00:00",
              language: "en",
            },
            taskSections: latestTaskSections(
              url.includes("/MSFT")
                ? "Microsoft typed thesis"
                : "Tesla typed thesis",
            ),
          },
        ]),
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    submitTicker("TSLA");

    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Tesla, Inc. · FY 2025 · 2026-01-29"),
    ).toBeInTheDocument();
    expect(screen.getByText("Tesla typed thesis")).toBeInTheDocument();

    submitTicker("MSFT");

    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Microsoft Corporation · FY 2025 · 2026-01-29"),
    ).toBeInTheDocument();
    expect(screen.getByText("Microsoft typed thesis")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([input]) =>
        String(input).includes("/sec/history/"),
      ),
    ).toBe(false);
    expect(screen.queryByTestId("key-metrics")).not.toBeInTheDocument();
  });

  it("merges progressive SSE chunks without overwriting earlier good fields", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/sec/history/")) {
        return new Response(JSON.stringify([]), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }

      return createSseResponse([
        {
          executiveSummary: "Initial thesis from the first agent.",
          companyName: "Tesla, Inc.",
          period: "FY 2025",
          filingDate: "2026-01-29",
          metadata: {
            modelName: "gpt-4o-mini",
            generatedAt: "2026-03-09T10:00:00",
            language: "en",
          },
          citations: [
            {
              section: "MD&A",
              excerpt: "First citation.",
              verificationStatus: "VERIFIED",
            },
          ],
          taskSections: latestTaskSections(
            "Initial typed thesis",
            "Initial thesis from the first agent.",
          ),
        },
        {
          executiveSummary: null,
          companyName: null,
          citations: [
            {
              section: "Risk Factors",
              excerpt: "Second citation.",
              verificationStatus: "UNVERIFIED",
            },
          ],
          sourceContext: {
            status: "GROUNDED",
            message: "Grounded in SEC text evidence.",
          },
          keyMetrics: [],
          businessDrivers: [],
          riskFactors: [],
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    submitTicker();
    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Tesla, Inc. · FY 2025 · 2026-01-29"),
    ).toBeInTheDocument();
    expect(screen.getByText("Initial typed thesis")).toBeInTheDocument();
    expect(screen.queryByText("First citation.")).not.toBeInTheDocument();
    expect(screen.queryByText("Second citation.")).not.toBeInTheDocument();
  });

  it("prevents overlapping analyses while an existing analysis is still loading", async () => {
    const firstAnalysis = createDeferredResponse();
    let followUpResponses = 0;

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/sec/history/")) {
        return Promise.resolve(
          new Response(JSON.stringify([]), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }

      if (url.includes("/sec/analyze/")) {
        if (url.includes("taskType=latest_earnings_readout")) {
          return firstAnalysis.promise;
        }
        followUpResponses += 1;
        return Promise.resolve(
          createSseResponse([
            {
              executiveSummary: `Tesla follow-up report ${followUpResponses}.`,
              companyName: "Tesla, Inc.",
              period: "FY 2025",
              filingDate: "2026-01-29",
              keyMetrics: [],
              businessDrivers: [],
              riskFactors: [],
              citations: [],
              metadata: {
                modelName: "gpt-4o-mini",
                generatedAt: "2026-03-09T10:00:00",
                language: "en",
              },
            },
          ]),
        );
      }

      return Promise.reject(new Error(`Unexpected fetch: ${url}`));
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    fireEvent.change(screen.getByPlaceholderText(/enter ticker/i), {
      target: { value: "TSLA" },
    });
    const analyzeButton = screen.getByRole("button", { name: /analyze/i });
    fireEvent.click(analyzeButton);

    fireEvent.change(screen.getByPlaceholderText(/enter ticker/i), {
      target: { value: "MSFT" },
    });
    fireEvent.click(analyzeButton);

    expect(
      fetchMock.mock.calls.filter(([input]) =>
        String(input).includes("taskType=latest_earnings_readout"),
      ),
    ).toHaveLength(1);
    expect(analyzeButton).toBeDisabled();

    await act(async () => {
      firstAnalysis.resolve(
        createSseResponse([
          {
            executiveSummary: "Tesla thesis still owns the active run.",
            companyName: "Tesla, Inc.",
            period: "FY 2025",
            filingDate: "2026-01-29",
            keyMetrics: [],
            businessDrivers: [],
            riskFactors: [],
            citations: [],
            metadata: {
              modelName: "gpt-4o-mini",
              generatedAt: "2026-03-09T10:00:00",
              language: "en",
            },
            taskSections: latestTaskSections(
              "Tesla active typed thesis",
              "Tesla thesis still owns the active run.",
            ),
          },
        ]),
      );
    });

    openAgentReport(/latest earnings readout/i);

    expect(
      await screen.findByText("Tesla, Inc. · FY 2025 · 2026-01-29"),
    ).toBeInTheDocument();
    expect(screen.getByText("Tesla active typed thesis")).toBeInTheDocument();
  });
});
