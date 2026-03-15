"use client";

import {
  Bar,
  BarChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import type { HistoricalDataPoint } from "./MarginAnalysisChart";

interface RevenueChartProps {
  ticker?: string;
  lang?: string;
  currency?: string;
  data?: HistoricalDataPoint[];
  loading?: boolean;
}

function formatAxisCurrency(value: number, symbol: string): string {
  const absolute = Math.abs(value);
  const prefix = value < 0 ? "-" : "";
  if (absolute >= 1_000_000_000_000) {
    return `${prefix}${symbol}${(absolute / 1_000_000_000_000).toFixed(1)}T`;
  }
  if (absolute >= 1_000_000_000) {
    return `${prefix}${symbol}${(absolute / 1_000_000_000).toFixed(1)}B`;
  }
  if (absolute >= 1_000_000) {
    return `${prefix}${symbol}${(absolute / 1_000_000).toFixed(0)}M`;
  }
  return `${prefix}${symbol}${absolute.toFixed(0)}`;
}

function renderUnavailableState(
  title: string,
  description: string,
  message: string,
  subdued = false,
) {
  return (
    <Card
      className={`bg-slate-900 border-slate-800 ${subdued ? "border-dashed" : ""}`}
    >
      <CardHeader className="border-b border-slate-800">
        <CardTitle
          className={subdued ? "text-emerald-400/60" : "text-emerald-400"}
        >
          📊 {title}
        </CardTitle>
        <CardDescription
          className={subdued ? "text-slate-500" : "text-slate-400"}
        >
          {description}
        </CardDescription>
      </CardHeader>
      <CardContent className="py-12 flex items-center justify-center text-slate-500 text-sm">
        {message}
      </CardContent>
    </Card>
  );
}

export function RevenueChart({
  lang = "en",
  currency = "USD",
  data = [],
  loading = false,
}: RevenueChartProps) {
  const isZh = lang === "zh";
  const quarterCount = data.length || 5;
  const rangeLabel = isZh
    ? `营收趋势 (近${quarterCount}季)`
    : `Revenue Trend (Last ${quarterCount} Quarters)`;
  const descriptionLabel = isZh
    ? "季度营收与净利润表现"
    : "Quarterly revenue and net income performance.";
  const hasRevenueSeries = data.some(
    (point) =>
      typeof point.revenue === "number" && Number.isFinite(point.revenue),
  );

  // Determine symbol
  let symbol = "$";
  if (currency === "JPY") symbol = "¥";
  else if (currency === "EUR") symbol = "€";
  else if (currency === "CNY") symbol = "¥";
  else if (currency === "GBP") symbol = "£";
  else if (currency !== "USD" && currency.length === 3) symbol = currency + " ";

  // Internal fetch removed in favor of parent hoisting to avoid race conditions

  if (loading || data.length === 0) {
    return renderUnavailableState(
      rangeLabel,
      descriptionLabel,
      loading
        ? isZh
          ? "加载中..."
          : "Loading..."
        : isZh
          ? "历史图表数据暂不可用。"
          : "Historical chart data is not available right now.",
      true,
    );
  }

  if (!hasRevenueSeries) {
    return renderUnavailableState(
      rangeLabel,
      descriptionLabel,
      isZh
        ? "该证券缺少可展示的季度营收序列。"
        : "Quarterly revenue data is not available for this issuer.",
    );
  }

  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardHeader className="border-b border-slate-800">
        <CardTitle className="text-emerald-400">📊 {rangeLabel}</CardTitle>
        <CardDescription className="text-slate-400">
          {descriptionLabel}
        </CardDescription>
      </CardHeader>
      <CardContent className="h-[400px] p-6">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data}>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="#334155"
              vertical={false}
            />
            <XAxis
              dataKey="period"
              stroke="#94a3b8"
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#94a3b8"
              fontSize={12}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) =>
                formatAxisCurrency(Number(value), symbol)
              }
            />
            <Tooltip
              contentStyle={{
                backgroundColor: "#0f172a",
                borderColor: "#1e293b",
                color: "#f8fafc",
              }}
              itemStyle={{ color: "#f8fafc" }}
              formatter={(value: number | string | undefined) => {
                const numericValue = Number(value);
                return [formatAxisCurrency(numericValue, symbol), ""];
              }}
            />
            <Bar
              dataKey="revenue"
              name={isZh ? "营收" : "Revenue"}
              fill="#10b981"
              radius={[4, 4, 0, 0]}
              barSize={40}
            />
            <Bar
              dataKey="netIncome"
              name={isZh ? "净利润" : "Net Income"}
              fill="#3b82f6"
              radius={[4, 4, 0, 0]}
              barSize={40}
            />
          </BarChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
