import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { RevenueChart } from "./RevenueChart";
import { MarginAnalysisChart } from "./MarginAnalysisChart";
import { FinancialHealthRadar } from "@/components/financial/financial-health-radar";

describe("quarterly charts and radar", () => {
  it("renders quarterly chart labels by default", () => {
    render(
      <RevenueChart
        lang="en"
        currency="USD"
        data={[
          {
            period: "Q1 2026",
            grossMargin: 0.5,
            operatingMargin: 0.3,
            netMargin: 0.2,
            revenue: 10,
            netIncome: 2,
          },
        ]}
      />,
    );

    expect(
      screen.getByText("📊 Revenue Trend (Last 1 Quarters)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Quarterly revenue and net income performance."),
    ).toBeInTheDocument();
  });

  it("falls back to an unavailable state when revenue is missing for every quarter", () => {
    render(
      <RevenueChart
        lang="en"
        currency="USD"
        data={[
          {
            period: "Q1 2026",
            grossMargin: null,
            operatingMargin: null,
            netMargin: null,
            revenue: undefined,
            netIncome: 2,
          },
        ]}
      />,
    );

    expect(
      screen.getByText(
        "Quarterly revenue data is not available for this issuer.",
      ),
    ).toBeInTheDocument();
  });

  it("renders quarterly margin labels by default", () => {
    render(
      <MarginAnalysisChart
        lang="zh"
        data={[
          {
            period: "Q4 2025",
            grossMargin: 0.5,
            operatingMargin: 0.3,
            netMargin: 0.2,
            revenue: 10,
            netIncome: 2,
          },
        ]}
      />,
    );

    expect(screen.getByText("利润率趋势分析 (近1季)")).toBeInTheDocument();
    expect(
      screen.getByText("追踪季度盈利效率随时间的变化"),
    ).toBeInTheDocument();
  });

  it("drops implausible ratio outliers when strict sanity checks are enabled", () => {
    const { container } = render(
      <MarginAnalysisChart
        lang="en"
        strictSanityChecks
        data={[
          {
            period: "Q3 2025",
            grossMargin: 1.7,
            operatingMargin: 1.1,
            netMargin: 2.2,
            revenue: 10,
            netIncome: 2,
          },
        ]}
      />,
    );

    expect(
      screen.queryByText(/Margin Trend Analysis/i),
    ).not.toBeInTheDocument();
    expect(container).toBeEmptyDOMElement();
  });

  it("requests radar facts without a report-type switch", async () => {
    const fetchMock = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            grossMargin: 0.4,
            netMargin: 0.2,
            operatingMargin: 0.25,
            revenueYoY: 0.1,
            operatingCashFlowYoY: 0.12,
            freeCashFlowYoY: 0.08,
            debtToEquityRatio: 0.6,
            returnOnEquity: 0.2,
            returnOnAssets: 0.1,
            priceToEarningsRatio: 25,
            priceToBookRatio: 6,
            dashboardMode: "standard",
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
    );

    vi.stubGlobal("fetch", fetchMock);

    render(
      <FinancialHealthRadar ticker="AAPL" lang="en" apiBase="/api/java" />,
    );

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith("/api/java/financial/AAPL");
    });
  });
});
