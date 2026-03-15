import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { MetricInsight } from "@/types/AnalysisReport";
import { RevenueChart } from "./RevenueChart";
import {
  HistoricalDataPoint,
  MarginAnalysisChart,
} from "./MarginAnalysisChart";
import { formatFinancialValue } from "@/lib/utils";
import type { FinancialFactsSnapshot } from "@/types/FinancialFacts";
import { DashboardModeNotice } from "@/components/financial/dashboard-mode-notice";

interface KeyMetricsProps {
  metrics: MetricInsight[];
  ticker?: string;
  lang?: string;
  currency?: string;
  historyData?: HistoricalDataPoint[];
  historyLoading?: boolean;
  apiBase?: string;
}

export function KeyMetrics({
  metrics,
  ticker,
  lang = "en",
  currency,
  historyData = [],
  historyLoading = false,
  apiBase = "/api/java",
}: KeyMetricsProps) {
  const [facts, setFacts] = useState<FinancialFactsSnapshot | null>(null);
  const [factsLoading, setFactsLoading] = useState(false);
  const [factsResolvedTicker, setFactsResolvedTicker] = useState<string | null>(
    null,
  );
  const filteredMetrics =
    metrics?.filter(
      (metric) => !isSuspiciousZeroGrossMarginMetric(metric, metrics),
    ) ?? [];
  const factsForTicker =
    ticker && factsResolvedTicker === ticker ? facts : null;
  const factsPending = Boolean(ticker) && factsResolvedTicker !== ticker;
  const dashboardMode = factsForTicker?.dashboardMode ?? "standard";
  const isFinancialSectorMode = dashboardMode === "financial_sector";
  const isUnsupportedReit = dashboardMode === "unsupported_reit";

  useEffect(() => {
    if (!ticker) {
      setFacts(null);
      setFactsLoading(false);
      setFactsResolvedTicker(null);
      return;
    }

    let cancelled = false;
    const currentTicker = ticker;
    setFacts(null);
    setFactsLoading(true);
    setFactsResolvedTicker(null);

    async function loadFacts() {
      try {
        const response = await fetch(`${apiBase}/financial/${ticker}`);
        if (!response.ok) {
          if (!cancelled) {
            setFacts(null);
          }
          return;
        }
        const data = (await response.json()) as FinancialFactsSnapshot;
        if (!cancelled) {
          setFacts(data);
        }
      } catch {
        if (!cancelled) {
          setFacts(null);
        }
      } finally {
        if (!cancelled) {
          setFactsLoading(false);
          setFactsResolvedTicker(currentTicker);
        }
      }
    }

    void loadFacts();

    return () => {
      cancelled = true;
    };
  }, [ticker, apiBase]);

  if (filteredMetrics.length === 0) return null;

  return (
    <div className="space-y-6">
      <div className="space-y-4">
        <h2 className="text-xl font-semibold text-emerald-300">
          💰 {lang === "zh" ? "关键财务指标" : "Key Financial Metrics"}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredMetrics.map((metric, idx) => (
            <Card key={idx} className="bg-slate-900 border-slate-800">
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <h3 className="text-sm font-medium text-slate-400">
                      {metric.metricName}
                    </h3>
                    <p className="text-2xl font-bold text-emerald-400 mt-1">
                      {formatFinancialValue(
                        metric.value,
                        metric.metricName,
                        currency,
                      )}
                    </p>
                  </div>
                  <div
                    className={`p-2 rounded ${
                      metric.sentiment === "positive"
                        ? "bg-green-900/30 text-green-400"
                        : metric.sentiment === "negative"
                          ? "bg-red-900/30 text-red-400"
                          : "bg-slate-800 text-slate-400"
                    }`}
                  >
                    {metric.sentiment === "positive"
                      ? "📈"
                      : metric.sentiment === "negative"
                        ? "📉"
                        : "➡️"}
                  </div>
                </div>
                <p className="text-sm text-slate-400 mt-3">
                  {metric.interpretation}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 gap-6">
        {isUnsupportedReit && (
          <DashboardModeNotice
            mode="unsupported_reit"
            lang={lang}
            message={factsForTicker?.dashboardMessage}
          />
        )}

        {isFinancialSectorMode && (
          <DashboardModeNotice
            mode="financial_sector"
            lang={lang}
            message={factsForTicker?.dashboardMessage}
          />
        )}

        {!isUnsupportedReit && (
          <RevenueChart
            ticker={ticker}
            lang={lang}
            currency={currency}
            data={historyData}
            loading={historyLoading || factsLoading || factsPending}
          />
        )}

        {!isUnsupportedReit && !isFinancialSectorMode && (
          <MarginAnalysisChart
            lang={lang}
            data={historyData}
            loading={historyLoading || factsLoading || factsPending}
            strictSanityChecks
          />
        )}

        {!isUnsupportedReit && isFinancialSectorMode && (
          <MarginAnalysisChart
            lang={lang}
            data={historyData}
            loading={historyLoading || factsLoading || factsPending}
            strictSanityChecks
            financialSectorMode
          />
        )}
      </div>
    </div>
  );
}

function isSuspiciousZeroGrossMarginMetric(
  metric: MetricInsight,
  metrics: MetricInsight[],
): boolean {
  const name = metric.metricName?.toLowerCase() ?? "";
  const value = metric.value?.trim() ?? "";
  const isGrossMargin =
    name.includes("gross margin") || name.includes("毛利率");
  const hasOperatingMarginPeer = metrics.some((item) => {
    const itemName = item.metricName?.toLowerCase() ?? "";
    return (
      itemName.includes("operating margin") || itemName.includes("营业利润率")
    );
  });

  return isGrossMargin && value === "0.00%" && hasOperatingMarginPeer;
}
