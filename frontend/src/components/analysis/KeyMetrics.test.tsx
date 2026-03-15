import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { KeyMetrics } from "./KeyMetrics";

vi.mock("./RevenueChart", () => ({
  RevenueChart: ({ loading }: { loading?: boolean }) => (
    <div data-testid="revenue-chart">{loading ? "loading" : "ready"}</div>
  ),
}));

vi.mock("./MarginAnalysisChart", () => ({
  MarginAnalysisChart: ({
    loading,
    strictSanityChecks,
    financialSectorMode,
  }: {
    loading?: boolean;
    strictSanityChecks?: boolean;
    financialSectorMode?: boolean;
  }) =>
    loading ? null : (
      <div data-testid="margin-chart">
        strict:{String(strictSanityChecks)} mode:
        {financialSectorMode ? "financial" : "standard"}
      </div>
    ),
}));

const baseMetrics = [
  {
    metricName: "营业利润率",
    value: "30.84%",
    interpretation: "营业利润率为30.84%，较上期持平。",
    sentiment: "neutral" as const,
  },
];

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("KeyMetrics", () => {
  it("hides suspicious zero gross-margin cards when operating margin is available", () => {
    render(
      <KeyMetrics
        lang="zh"
        metrics={[
          {
            metricName: "毛利率",
            value: "0.00%",
            interpretation: "毛利率为0.00%，较上期持平。",
            sentiment: "neutral",
          },
          ...baseMetrics,
        ]}
      />,
    );

    expect(screen.queryByText("毛利率")).not.toBeInTheDocument();
    expect(screen.getByText("营业利润率")).toBeInTheDocument();
  });

  it("keeps revenue and swaps in a financial-sector margin chart", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        dashboardMode: "financial_sector",
        dashboardMessage: "Financial sector mode is active.",
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<KeyMetrics ticker="JPM" lang="en" metrics={baseMetrics} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/java/financial/JPM");
    });

    expect(
      await screen.findByText("Financial Sector Mode"),
    ).toBeInTheDocument();
    expect(screen.getByTestId("revenue-chart")).toHaveTextContent("ready");
    expect(screen.getByTestId("margin-chart")).toHaveTextContent(
      "mode:financial",
    );
  });

  it("disables both charts for unsupported REIT tickers", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        dashboardMode: "unsupported_reit",
        dashboardMessage:
          "This ticker is categorized as a REIT / trust-like issuer.",
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<KeyMetrics ticker="PLD" lang="en" metrics={baseMetrics} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/java/financial/PLD");
    });

    expect(
      await screen.findByText("Unsupported Security Type"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("revenue-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("margin-chart")).not.toBeInTheDocument();
  });

  it("localizes dashboard notices for chinese even when backend returns english text", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        dashboardMode: "financial_sector",
        dashboardMessage:
          "Financial sector mode is active for this ticker because generic operating-company margin and cash-conversion dashboards are not reliable for bank-style filings.",
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<KeyMetrics ticker="JPM" lang="zh" metrics={baseMetrics} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/java/financial/JPM");
    });

    expect(await screen.findByText("金融行业模式")).toBeInTheDocument();
    expect(
      screen.getByText("该 ticker 属于金融行业，通用毛利率、现金转化和雷达评分已隐藏，以避免误导性展示。"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Financial sector mode is active/i)).not.toBeInTheDocument();
  });

  it("keeps generic charts in a loading state until facts resolve for the submitted ticker", async () => {
    let resolveFetch!: (value: {
      ok: boolean;
      json: () => Promise<{ dashboardMode: string; dashboardMessage: string }>;
    }) => void;
    const fetchMock = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
    );
    vi.stubGlobal("fetch", fetchMock);

    render(<KeyMetrics ticker="EXR" lang="en" metrics={baseMetrics} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/java/financial/EXR");
    });

    expect(screen.getByTestId("revenue-chart")).toHaveTextContent("loading");
    expect(screen.queryByTestId("margin-chart")).not.toBeInTheDocument();

    resolveFetch({
      ok: true,
      json: async () => ({
        dashboardMode: "unsupported_reit",
        dashboardMessage:
          "This ticker is categorized as a REIT / trust-like issuer.",
      }),
    });

    expect(
      await screen.findByText("Unsupported Security Type"),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("revenue-chart")).not.toBeInTheDocument();
    expect(screen.queryByTestId("margin-chart")).not.toBeInTheDocument();
  });

  it("passes strict sanity checks to the standard margin chart", async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        dashboardMode: "standard",
      }),
    }));
    vi.stubGlobal("fetch", fetchMock);

    render(<KeyMetrics ticker="EW" lang="en" metrics={baseMetrics} />);

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/java/financial/EW");
    });

    expect(screen.getByTestId("margin-chart")).toHaveTextContent("strict:true");
    expect(screen.getByTestId("margin-chart")).toHaveTextContent(
      "mode:standard",
    );
  });
});
