"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export interface HistoricalDataPoint {
  period: string;
  grossMargin: number | string | null;
  operatingMargin: number | string | null;
  netMargin: number | string | null;
  revenue?: number;
  netIncome?: number;
}

interface MarginAnalysisProps {
  lang?: string;
  data?: HistoricalDataPoint[];
  loading?: boolean;
  strictSanityChecks?: boolean;
  financialSectorMode?: boolean;
}

export function MarginAnalysisChart({
  lang = "en",
  data: rawData = [],
  loading = false,
  strictSanityChecks = false,
  financialSectorMode = false,
}: MarginAnalysisProps) {
  const toPercent = (
    value: number | string | null | undefined,
  ): number | null => {
    if (value === null || value === undefined || value === "") {
      return null;
    }
    const rawValue = typeof value === "string" ? value.trim() : value;
    const hasPercentSuffix =
      typeof rawValue === "string" && rawValue.endsWith("%");
    const normalizedValue =
      typeof rawValue === "string" && hasPercentSuffix
        ? rawValue.slice(0, -1)
        : rawValue;
    const numericValue =
      typeof normalizedValue === "string"
        ? Number(normalizedValue)
        : normalizedValue;
    if (!Number.isFinite(numericValue)) {
      return null;
    }
    if (strictSanityChecks && !hasPercentSuffix && Math.abs(numericValue) > 1) {
      return null;
    }
    if (Math.abs(numericValue) <= 1) {
      return Number((numericValue * 100).toFixed(1));
    }
    if (Math.abs(numericValue) <= 100) {
      return Number(numericValue.toFixed(1));
    }
    return null;
  };

  // useMemo: 数据转换同步完成，避免 useEffect 的额外渲染周期导致图表闪烁/消失
  const data = useMemo(() => {
    if (rawData.length === 0) return [];
    return rawData
      .map((item) => ({
        period: item.period,
        grossMargin: toPercent(item.grossMargin),
        operatingMargin: toPercent(item.operatingMargin),
        netMargin: toPercent(item.netMargin),
      }))
      .filter(
        (item) =>
          item.grossMargin !== null ||
          item.operatingMargin !== null ||
          item.netMargin !== null,
      );
  }, [rawData, strictSanityChecks]);
  const hasGrossMargin = data.some((item) => item.grossMargin !== null);
  const hasOperatingMargin = data.some((item) => item.operatingMargin !== null);
  const hasNetMargin = data.some((item) => item.netMargin !== null);
  const visibleSeriesCount = [
    hasGrossMargin,
    hasOperatingMargin,
    hasNetMargin,
  ].filter(Boolean).length;
  const formatTooltipValue = (
    value: number | string | readonly (number | string)[] | null | undefined,
  ) => {
    const resolvedValue = Array.isArray(value) ? value[0] : value;
    return [
      resolvedValue === null || resolvedValue === undefined
        ? "N/A"
        : `${resolvedValue}%`,
      "",
    ] as const;
  };

  const isZh = lang === "zh";
  const quarterCount = data.length || 5;
  const rangeLabel = financialSectorMode
    ? isZh
      ? `盈利能力趋势 (近${quarterCount}季)`
      : `Profitability Trend (Last ${quarterCount} Quarters)`
    : isZh
      ? `利润率趋势分析 (近${quarterCount}季)`
      : `Margin Trend Analysis (Last ${quarterCount} Quarters)`;
  const descriptionLabel = financialSectorMode
    ? isZh
      ? "银行类发行人优先展示稳定可得的净利率序列，避免用缺失的毛利率或营业利润率误导判断。"
      : "Bank-style issuers emphasize the stable net-margin series instead of missing gross or operating margin inputs."
    : isZh
      ? "追踪季度盈利效率随时间的变化"
      : "Tracking quarterly profitability efficiency over time.";

  if (loading || data.length === 0) {
    return null;
  }

  if (!hasGrossMargin && !hasOperatingMargin && !hasNetMargin) {
    return (
      <Card className="border-slate-800 bg-slate-900 border-dashed">
        <CardHeader className="border-b border-slate-800">
          <CardTitle className="text-emerald-400/60">{rangeLabel}</CardTitle>
          <CardDescription className="text-slate-500">
            {descriptionLabel}
          </CardDescription>
        </CardHeader>
        <CardContent className="py-12 flex items-center justify-center text-slate-500 text-sm">
          {isZh ? "当前缺少可展示的季度利润率序列。" : "Quarterly profitability series are not available for this issuer."}
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-slate-800 bg-slate-900">
      <CardHeader className="border-b border-slate-800">
        <CardTitle className="text-emerald-400">{rangeLabel}</CardTitle>
        <CardDescription className="text-slate-400">
          {descriptionLabel}
        </CardDescription>
      </CardHeader>
      <CardContent className="h-[400px] p-6">
        <div className="h-full w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data}>
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
                dy={10}
              />
              <YAxis
                stroke="#94a3b8"
                fontSize={12}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => `${value}%`}
                dx={-10}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: "#0f172a",
                  borderColor: "#1e293b",
                  color: "#f8fafc",
                }}
                itemStyle={{ color: "#f8fafc" }}
                formatter={formatTooltipValue}
              />
              {visibleSeriesCount > 1 && (
                <Legend wrapperStyle={{ paddingTop: "20px" }} />
              )}
              {hasNetMargin && (
                <Line
                  type="monotone"
                  dataKey="netMargin"
                  name={isZh ? "净利率" : "Net Margin"}
                  stroke="#8b5cf6"
                  strokeWidth={2}
                  dot={{ r: 4, strokeWidth: 0, fill: "#8b5cf6" }}
                  activeDot={{ r: 6, strokeWidth: 0 }}
                />
              )}
              {hasGrossMargin && (
                <Line
                  type="monotone"
                  dataKey="grossMargin"
                  name={isZh ? "毛利率" : "Gross Margin"}
                  stroke="#34d399"
                  strokeWidth={2}
                  dot={{ r: 4, strokeWidth: 0, fill: "#34d399" }}
                  activeDot={{ r: 6, strokeWidth: 0 }}
                />
              )}
              {hasOperatingMargin && (
                <Line
                  type="monotone"
                  dataKey="operatingMargin"
                  name={isZh ? "营业利润率" : "Operating Margin"}
                  stroke="#2dd4bf"
                  strokeWidth={2}
                  dot={{ r: 4, strokeWidth: 0, fill: "#2dd4bf" }}
                  activeDot={{ r: 6, strokeWidth: 0 }}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
