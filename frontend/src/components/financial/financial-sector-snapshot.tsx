"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Building2 } from "lucide-react";
import { DashboardModeNotice } from "./dashboard-mode-notice";
import type { FinancialFactsSnapshot } from "@/types/FinancialFacts";
import { formatFinancialValue } from "@/lib/utils";

interface FinancialSectorSnapshotProps {
  facts: FinancialFactsSnapshot;
  lang?: string;
}

interface SnapshotMetric {
  label: string;
  name: string;
  value: string | number | null | undefined;
}

function buildMetricRows(
  facts: FinancialFactsSnapshot,
  lang: string,
): SnapshotMetric[] {
  const isZh = lang === "zh";

  return [
    {
      label: isZh ? "净利率" : "Net Margin",
      name: "Net Margin",
      value: facts.netMargin,
    },
    {
      label: "ROE",
      name: "ROE",
      value: facts.returnOnEquity,
    },
    {
      label: "ROA",
      name: "ROA",
      value: facts.returnOnAssets,
    },
    {
      label: "EPS",
      name: "EPS",
      value: facts.earningsPerShare,
    },
    {
      label: "P/E",
      name: "P/E",
      value: facts.priceToEarningsRatio,
    },
    {
      label: "P/B",
      name: "P/B",
      value: facts.priceToBookRatio,
    },
    {
      label: isZh ? "总资产" : "Total Assets",
      name: "Total Assets",
      value: facts.totalAssets,
    },
    {
      label: isZh ? "股东权益" : "Total Equity",
      name: "Total Equity",
      value: facts.totalEquity,
    },
  ];
}

export function FinancialSectorSnapshot({
  facts,
  lang = "en",
}: FinancialSectorSnapshotProps) {
  const isZh = lang === "zh";
  const currency = facts.currency ?? "USD";
  const metrics = buildMetricRows(facts, lang);

  return (
    <Card className="bg-slate-900/50 backdrop-blur-sm border-slate-800">
      <CardHeader className="space-y-4">
        <CardTitle className="text-emerald-400 flex items-center gap-2">
          <Building2 className="w-5 h-5" />
          {isZh ? "🏦 银行财务快照" : "🏦 Financial Sector Snapshot"}
        </CardTitle>
        <DashboardModeNotice
          mode="financial_sector"
          lang={lang}
          message={facts.dashboardMessage}
        />
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-slate-400">
          {isZh
            ? "银行类个股优先展示净利率、资本回报、估值与资产负债表规模，避免用不适用的工业股毛利率/营业利润率模板误导判断。"
            : "Bank-style issuers are shown with net margin, returns, valuation, and balance-sheet scale instead of generic operating-company gross and operating margin templates."}
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {metrics.map((metric) => (
            <div
              key={metric.label}
              className="rounded-xl border border-slate-800 bg-slate-950/70 px-4 py-3"
            >
              <div className="text-xs uppercase tracking-wide text-slate-500">
                {metric.label}
              </div>
              <div className="mt-2 text-xl font-semibold text-slate-100">
                {formatFinancialValue(metric.value, metric.name, currency)}
              </div>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
