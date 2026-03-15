import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "./page";

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
      expect.stringContaining("/sec/analyze/AAPL?lang=en&model=chatanywhere"),
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
      "/api/sec/analyze/AAPL?lang=en&model=chatanywhere",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
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
      "/api/sec/analyze/V?lang=en&model=chatanywhere",
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
    expect(screen.getByTestId("key-metrics")).toHaveTextContent(
      "key-metrics:V:none",
    );
  });

  it("requires a saved OpenAI key before running BYOK mode", async () => {
    vi.stubGlobal("fetch", vi.fn());

    render(<Home />);

    fireEvent.click(screen.getByRole("button", { name: /openai \(byok\)/i }));
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

  it("sends the saved OpenAI key when BYOK mode is used", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: /openai \(byok\)/i }));
    fireEvent.change(screen.getByPlaceholderText(/enter your openai key/i), {
      target: { value: "sk-test-123" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/sec/analyze/"),
        expect.objectContaining({
          headers: { "X-OpenAI-API-Key": "sk-test-123" },
          signal: expect.any(AbortSignal),
        }),
      );
    });
  });

  it("surfaces explicit invalid-key errors for OpenAI BYOK instead of rendering an empty report shell", async () => {
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
          error: "OpenAI API key is invalid or unauthorized for this project",
          code: "OPENAI_API_KEY_INVALID",
          source: "openai",
        }),
        {
          status: 401,
          headers: { "Content-Type": "application/json" },
        },
      );
    });

    vi.stubGlobal("fetch", fetchMock);

    render(<Home />);

    fireEvent.click(screen.getByRole("button", { name: /openai \(byok\)/i }));
    fireEvent.change(screen.getByPlaceholderText(/enter your openai key/i), {
      target: { value: "sk-invalid-test" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    fireEvent.click(screen.getByRole("button", { name: /analyze/i }));

    expect(
      await screen.findByText(
        /OpenAI API key is invalid or unauthorized for this project/i,
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
