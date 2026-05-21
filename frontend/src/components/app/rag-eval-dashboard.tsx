import { Activity, Boxes, SearchCheck } from "lucide-react";

import type { AnalysisReport, RagTelemetry } from "@/types/AnalysisReport";
import {
  buildRagEvalMetricCopy,
  ragEvalDashboardDescription,
  ragEvalDashboardReportCountLabel,
  ragEvalDashboardStatusLabel,
  ragEvalDashboardTitle,
  type RagEvalLocale,
} from "@/lib/ragEvalCopy";
import { cn } from "@/lib/utils";

type LiveRagMetric = {
  key: string;
  label: string;
  value: string;
  detail: string;
  tone: RagMetricTone;
};

const metricTone = {
  strong: "border-emerald-500/30 bg-emerald-950/20 text-emerald-200",
  stable: "border-cyan-500/30 bg-cyan-950/20 text-cyan-200",
  caution: "border-amber-500/30 bg-amber-950/20 text-amber-200",
  muted: "border-slate-700 bg-slate-950/70 text-slate-200",
} as const;

type RagMetricTone = keyof typeof metricTone;

export function RagEvalDashboard({
  reports,
  lang,
}: {
  reports?: AnalysisReport[];
  lang: RagEvalLocale;
}) {
  const locale = lang;
  const telemetry = aggregateRagTelemetry(reports ?? []);
  const metrics = buildLiveRagMetrics(telemetry, locale);

  return (
    <section
      aria-labelledby="rag-live-telemetry-title"
      className="rounded-md border border-slate-800 bg-slate-900/70 p-4"
    >
      <div className="flex flex-col gap-3 border-b border-slate-800 pb-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <SearchCheck className="h-5 w-5 text-emerald-300" />
            <h2
              id="rag-live-telemetry-title"
              className="text-lg font-semibold text-emerald-300"
            >
              {ragEvalDashboardTitle(locale)}
            </h2>
          </div>
          <p className="max-w-2xl text-sm leading-6 text-slate-400">
            {ragEvalDashboardDescription(locale)}
          </p>
        </div>

        <div className="grid min-w-[240px] grid-cols-1 gap-2 text-xs text-slate-400">
          <span className="inline-flex min-h-9 items-center gap-2 rounded-md border border-slate-800 bg-slate-950 px-3 py-2">
            <Activity className="h-3.5 w-3.5 text-cyan-300" />
            {ragEvalDashboardReportCountLabel(
              telemetry ? telemetry.reportCount : null,
              locale,
            )}
          </span>
          <span className="inline-flex min-h-9 items-center gap-2 rounded-md border border-slate-800 bg-slate-950 px-3 py-2">
            <Boxes className="h-3.5 w-3.5 text-emerald-300" />
            {ragEvalDashboardStatusLabel(Boolean(telemetry), locale)}
          </span>
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-7">
        {metrics.map((metric) => (
          <div
            key={metric.label}
            className={cn(
              "min-h-[112px] rounded-md border p-3",
              metricTone[metric.tone],
            )}
          >
            <p className="text-[11px] uppercase leading-tight tracking-widest opacity-75">
              {metric.label}
            </p>
            <p className="mt-3 text-2xl font-semibold tabular-nums">
              {metric.value}
            </p>
            <p className="mt-2 text-xs leading-5 opacity-70">{metric.detail}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

type AggregatedRagTelemetry = RagTelemetry & {
  reportCount: number;
};

export function aggregateRagTelemetry(
  reports: AnalysisReport[],
): AggregatedRagTelemetry | null {
  const telemetryReports = reports
    .map((report) => report.ragTelemetry)
    .filter((item): item is RagTelemetry => Boolean(item));
  if (telemetryReports.length === 0) return null;

  return telemetryReports.reduce<AggregatedRagTelemetry>(
    (total, item) => ({
      reportCount: total.reportCount + 1,
      evidenceRetrieved: total.evidenceRetrieved + item.evidenceRetrieved,
      evidenceUsed: total.evidenceUsed + item.evidenceUsed,
      metricFacts: total.metricFacts + item.metricFacts,
      sectionsCovered: total.sectionsCovered + item.sectionsCovered,
      retrievalLatencyMs: total.retrievalLatencyMs + item.retrievalLatencyMs,
      emptyRetrieval: total.emptyRetrieval || item.emptyRetrieval,
      evidencePackBytes: total.evidencePackBytes + item.evidencePackBytes,
    }),
    {
      reportCount: 0,
      evidenceRetrieved: 0,
      evidenceUsed: 0,
      metricFacts: 0,
      sectionsCovered: 0,
      retrievalLatencyMs: 0,
      emptyRetrieval: false,
      evidencePackBytes: 0,
    },
  );
}

function buildLiveRagMetrics(
  telemetry: AggregatedRagTelemetry | null,
  locale: RagEvalLocale,
): LiveRagMetric[] {
  return buildRagEvalMetricCopy(locale).map((metric) => ({
    ...metric,
    value: telemetry ? formatMetricValue(metric.key, telemetry) : "N/A",
    tone:
      metric.key === "emptyRetrieval" && telemetry?.emptyRetrieval
        ? "caution"
        : metric.tone,
  }));
}

function formatMetricValue(
  key: LiveRagMetric["key"],
  telemetry: AggregatedRagTelemetry,
) {
  switch (key) {
    case "evidenceRetrieved":
      return String(telemetry.evidenceRetrieved);
    case "evidenceUsed":
      return String(telemetry.evidenceUsed);
    case "metricFacts":
      return String(telemetry.metricFacts);
    case "sectionsCovered":
      return String(telemetry.sectionsCovered);
    case "retrievalLatency":
      return formatLatency(telemetry.retrievalLatencyMs);
    case "emptyRetrieval":
      return telemetry.emptyRetrieval ? "Yes" : "No";
    case "evidencePackSize":
      return formatBytes(telemetry.evidencePackBytes);
  }
  return "N/A";
}

function formatLatency(value: number) {
  if (value >= 1000) {
    return `${(value / 1000).toFixed(1).replace(/\.0$/, "")}s`;
  }
  return `${value} ms`;
}

function formatBytes(value: number) {
  if (value >= 1024 * 1024) {
    return `${(value / (1024 * 1024)).toFixed(1).replace(/\.0$/, "")} MB`;
  }
  if (value >= 1024) {
    return `${(value / 1024).toFixed(1).replace(/\.0$/, "")} KB`;
  }
  return `${value} B`;
}
