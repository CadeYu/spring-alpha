import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/components/app/earnings-analyst-app";

vi.mock("@/components/analysis/ExecutiveSummary", () => ({
  ExecutiveSummary: ({
    summary,
    thesis,
  }: {
    summary?: string;
    thesis?: { summary?: string };
  }) => (
    <div data-testid="executive-summary">
      {thesis?.summary || summary || "summary"}
    </div>
  ),
}));

vi.mock("@/components/analysis/KeyMetrics", () => ({
  KeyMetrics: ({
    ticker,
    historyData,
  }: {
    ticker?: string;
    historyData?: Array<{ period: string }>;
  }) => (
    <div data-testid="key-metrics">
      key-metrics:{ticker || "none"}:
      {historyData?.map((item) => item.period).join("|") || "none"}
    </div>
  ),
}));

vi.mock("@/components/analysis/BusinessDrivers", () => ({
  BusinessDrivers: () => (
    <div data-testid="business-drivers">business-drivers</div>
  ),
}));

vi.mock("@/components/analysis/RiskFactors", () => ({
  RiskFactors: () => <div data-testid="risk-factors">risk-factors</div>,
}));

vi.mock("@/components/analysis/BullBearCase", () => ({
  BullBearCase: () => <div data-testid="bull-bear-case">bull-bear-case</div>,
}));

vi.mock("@/components/financial/dupont-chart", () => ({
  DuPontChart: () => <div data-testid="dupont-chart">dupont-chart</div>,
}));

vi.mock("@/components/financial/insight-cards", () => ({
  InsightCards: () => <div data-testid="insight-cards">insight-cards</div>,
}));

vi.mock("@/components/financial/financial-health-radar", () => ({
  FinancialHealthRadar: () => (
    <div data-testid="financial-health-radar">financial-health-radar</div>
  ),
}));

vi.mock("@/components/analysis/TopicWordCloud", () => ({
  TopicWordCloud: () => (
    <div data-testid="topic-word-cloud">topic-word-cloud</div>
  ),
}));

vi.mock("@/components/pdf/PdfDownloadButton", () => ({
  PdfDownloadButton: () => <button type="button">pdf</button>,
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

describe("Home page", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.localStorage.clear();
    window.localStorage.setItem("spring-alpha-siliconflow-key", "sk-test-123");
  });

  it("renders degraded source metadata from the quarterly-only analysis stream", async () => {
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
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText("Tesla, Inc. · Q1 2026 · 2026-03-31"),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        "SEC filing was available, but semantic grounding was not ready yet.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("executive-summary")).toHaveTextContent(
      "Tesla remained under pressure.",
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/sec/history/AAPL"),
      expect.anything(),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/sec/analyze/AAPL?lang=en&model=siliconflow"),
      expect.anything(),
    );
  });

  it("routes analysis through the local SSE bridge while history still uses the java proxy", async () => {
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
        },
      ]);
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText("Apple Inc. · Q1 2026 · 2026-02-01"),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/java/sec/history/AAPL",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=latest_earnings_readout",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  it("renders MVP task cards and submits the selected task type", async () => {
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
      screen.getByRole("radiogroup", { name: /research tasks/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /latest earnings readout/i }),
    ).toBeChecked();
    expect(
      screen.getByRole("radio", { name: /business driver deep dive/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("radio", {
        name: /cash flow & capital allocation/i,
      }),
    ).toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("radio", { name: /business driver deep dive/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText("Apple Inc. · Q1 2026 · 2026-02-01"),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sec/analyze/AAPL?lang=en&model=siliconflow&taskType=business_driver_deep_dive",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
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

    fireEvent.click(
      screen.getByRole("radio", { name: /business driver deep dive/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText("Business Driver Research View"),
    ).toBeInTheDocument();
    expect(screen.getByText("Product / Segment Signals")).toBeInTheDocument();
    expect(screen.getByText("Driver Map")).toBeInTheDocument();
    expect(screen.getByText("Driver Evidence")).toBeInTheDocument();
    expect(screen.getByTestId("business-drivers")).toBeInTheDocument();
    expect(screen.queryByTestId("key-metrics")).not.toBeInTheDocument();
    expect(screen.queryByTestId("dupont-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("bull-bear-case")).not.toBeInTheDocument();
    expect(screen.queryByText("Capital Allocation View")).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole("radio", {
        name: /cash flow & capital allocation/i,
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(await screen.findByText("Capital Allocation View")).toBeInTheDocument();
    expect(screen.getByText("Cash Conversion Quality")).toBeInTheDocument();
    expect(screen.getByText("Cash Quality Verdict")).toBeInTheDocument();
    expect(screen.getByText("Capital Allocation Lens")).toBeInTheDocument();
    expect(screen.getAllByText("Operating Cash Flow").length).toBeGreaterThan(0);
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

    fireEvent.click(
      screen.getByRole("radio", { name: /business driver deep dive/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(await screen.findByText("Typed driver thesis")).toBeInTheDocument();
    expect(screen.getByText("Typed product signal")).toBeInTheDocument();
    expect(screen.getByText("Track typed product adoption.")).toBeInTheDocument();
    expect(screen.queryByText("Legacy services momentum")).not.toBeInTheDocument();
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

    fireEvent.click(
      screen.getByRole("radio", { name: /cash flow & capital allocation/i }),
    );
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(await screen.findByText("Typed cash quality verdict")).toBeInTheDocument();
    expect(screen.getByText("Typed operating cash flow")).toBeInTheDocument();
    expect(screen.getByText("Typed capex signal")).toBeInTheDocument();
    expect(screen.getByText("Typed buyback signal")).toBeInTheDocument();
    expect(screen.getByText("Typed liquidity signal")).toBeInTheDocument();
    expect(screen.getByText("Typed allocation discipline")).toBeInTheDocument();
    expect(screen.getByText("Typed red flag")).toBeInTheDocument();
    expect(screen.queryByText("Legacy Free Cash Flow")).not.toBeInTheDocument();
  });

  it("renders the RAG eval dashboard with persisted stage 1 hard-suite comparisons", () => {
    render(<Home />);

    expect(screen.getByText("Experiment Lab")).toBeInTheDocument();
    expect(screen.getByText("RAG Eval Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Stage 1 Hard RAG")).toBeInTheDocument();
    expect(screen.getAllByText("hybrid_semantic_lexical_retrieval")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Expected Term Hit Rate")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Top-1 Section Correctness")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Bad Section Leak Rate")[0]).toBeInTheDocument();
    expect(screen.getByText("Context Precision")).toBeInTheDocument();
    expect(screen.getByText("stage1_hard_rag_eval")).toBeInTheDocument();
    expect(screen.getByText("hard_msft_semantic_platform_driver")).toBeInTheDocument();
    expect(screen.getByText("Section-Aware Lexical")).toBeInTheDocument();
    expect(screen.getByText("No Section Filter")).toBeInTheDocument();
    expect(screen.getByText("No Query Expansion")).toBeInTheDocument();
    expect(
      screen.getByText("Generated from the local hard RAG eval suite."),
    ).toBeInTheDocument();
    expect(screen.getByText("Release Readiness")).toBeInTheDocument();
    expect(screen.getByText("Provider RAG sample gate")).toBeInTheDocument();
    expect(screen.getByText("Provider live planner gate")).toBeInTheDocument();
    expect(screen.getByText("Compose full E2E")).toBeInTheDocument();
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

    expect(
      await screen.findByText("Visa Inc. · Q1 2026 · 2026-02-01"),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/java/sec/history/V",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/sec/analyze/V?lang=en&model=siliconflow&taskType=latest_earnings_readout",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByTestId("key-metrics")).toHaveTextContent(
      "key-metrics:V:none",
    );
  });

  it("requires a saved provider key before running BYOK mode", async () => {
    vi.stubGlobal("fetch", vi.fn());
    window.localStorage.removeItem("spring-alpha-siliconflow-key");

    render(<Home />);

    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText(
        /requires you to enter and save your api key first/i,
      ),
    ).toBeInTheDocument();
    expect(global.fetch).not.toHaveBeenCalled();
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

    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));
    unmount();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    expect(consoleError).not.toHaveBeenCalledWith(
      expect.stringContaining("Fetch Error:"),
    );
  });

  it("renders grounded citations instead of degraded fallback when citations exist", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText("Revenue increased due to stronger deliveries."),
    ).toBeInTheDocument();
    expect(screen.getByText("MD&A")).toBeInTheDocument();
    expect(
      screen.queryByText(/semantic grounding was not ready yet/i),
    ).not.toBeInTheDocument();
  });

  it("renders a grounded no-citation explanation when all citations were filtered out", async () => {
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
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText(
        /did not retain a display-ready high-confidence verbatim quote/i,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Current status: grounded evidence, citation display limited/i,
      ),
    ).toBeInTheDocument();
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

    fireEvent.change(screen.getByPlaceholderText(/enter your siliconflow key/i), {
      target: { value: "sk-test-123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

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
          error: "SiliconFlow API key is invalid or unauthorized for this project",
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

    fireEvent.change(screen.getByPlaceholderText(/enter your siliconflow key/i), {
      target: { value: "sk-invalid-test" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText(
        /SiliconFlow API key is invalid or unauthorized for this project/i,
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Analysis Report/i)).not.toBeInTheDocument();
  });

  it("surfaces backend quota errors instead of a generic internal server error", async () => {
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
            "FMP daily quota exceeded. Configure additional API keys or wait for quota reset.",
        }),
        {
          status: 429,
          headers: { "Content-Type": "application/json" },
        },
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText(/FMP daily quota exceeded/i),
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
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

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

  it("ignores stale history responses after switching to a new ticker", async () => {
    const firstHistory = createDeferredResponse();
    const secondHistory = createDeferredResponse();
    let historyCallCount = 0;

    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);

      if (url.includes("/sec/history/")) {
        historyCallCount += 1;
        return historyCallCount === 1
          ? firstHistory.promise
          : secondHistory.promise;
      }

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
          },
        ]),
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    fireEvent.change(screen.getByPlaceholderText(/enter ticker/i), {
      target: { value: "TSLA" },
    });
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText("Tesla, Inc. · FY 2025 · 2026-01-29"),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(/enter ticker/i), {
      target: { value: "MSFT" },
    });
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText("Microsoft Corporation · FY 2025 · 2026-01-29"),
    ).toBeInTheDocument();

    await act(async () => {
      secondHistory.resolve(
        new Response(
          JSON.stringify([
            {
              period: "FY 2025",
              grossMargin: 0.4,
              operatingMargin: 0.3,
              netMargin: 0.2,
              revenue: 10,
              netIncome: 2,
            },
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    });

    await waitFor(() => {
      expect(screen.getByTestId("key-metrics")).toHaveTextContent("FY 2025");
    });

    await act(async () => {
      firstHistory.resolve(
        new Response(
          JSON.stringify([
            {
              period: "FY 2024",
              grossMargin: 0.1,
              operatingMargin: 0.1,
              netMargin: 0.1,
              revenue: 1,
              netIncome: 1,
            },
          ]),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    });

    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(screen.getByTestId("key-metrics")).not.toHaveTextContent("FY 2024");
    expect(screen.getByTestId("key-metrics")).toHaveTextContent("FY 2025");
    expect(screen.getByTestId("key-metrics")).toHaveTextContent(
      "key-metrics:MSFT",
    );
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
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText("Tesla, Inc. · FY 2025 · 2026-01-29"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("executive-summary")).toHaveTextContent(
      "Initial thesis from the first agent.",
    );
    expect(await screen.findByText("First citation.")).toBeInTheDocument();
    expect(await screen.findByText("Second citation.")).toBeInTheDocument();
  });

  it("prevents overlapping analyses while an existing analysis is still loading", async () => {
    const firstAnalysis = createDeferredResponse();

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
        return firstAnalysis.promise;
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
        String(input).includes("/sec/analyze/"),
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
          },
        ]),
      );
    });

    expect(
      await screen.findByText("Tesla, Inc. · FY 2025 · 2026-01-29"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("executive-summary")).toHaveTextContent(
      "Tesla thesis still owns the active run.",
    );
  });
});
