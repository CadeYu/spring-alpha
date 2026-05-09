import { Activity, BarChart3, Database, Timer } from "lucide-react";

import {
  formatRagEvalMetric,
  STAGE1_HARD_RAG_EVAL_ARTIFACT,
} from "@/lib/ragEvalDashboard";
import { cn } from "@/lib/utils";
import { ReleaseReadinessChecklist } from "@/components/app/release-readiness-checklist";

const metricToneByIndex = [
  "border-emerald-500/30 bg-emerald-950/20 text-emerald-200",
  "border-cyan-500/30 bg-cyan-950/20 text-cyan-200",
  "border-amber-500/30 bg-amber-950/20 text-amber-200",
  "border-slate-600 bg-slate-900 text-slate-200",
] as const;

export function RagEvalDashboard() {
  const artifact = STAGE1_HARD_RAG_EVAL_ARTIFACT;

  return (
    <div className="space-y-4">
      <section
        aria-labelledby="rag-eval-dashboard-title"
        className="rounded-md border border-slate-800 bg-slate-900/70 p-4"
      >
      <div className="flex flex-col gap-3 border-b border-slate-800 pb-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <BarChart3 className="h-5 w-5 text-emerald-400" />
            <h2
              id="rag-eval-dashboard-title"
              className="text-lg font-semibold text-emerald-300"
            >
              RAG Eval Dashboard
            </h2>
          </div>
          <p className="max-w-3xl text-sm leading-6 text-slate-400">
            Read-only experiment view for the current RAG professionalization
            report. The dashboard now displays the persisted hard-suite
            retrieval artifact and strategy comparisons.
          </p>
        </div>

        <div className="grid min-w-[260px] grid-cols-1 gap-2 text-xs text-slate-400">
          <span className="inline-flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950 px-3 py-2">
            <Database className="h-3.5 w-3.5 text-cyan-300" />
            {artifact.datasetName}
          </span>
          <span className="inline-flex items-center gap-2 rounded-md border border-slate-800 bg-slate-950 px-3 py-2">
            <Activity className="h-3.5 w-3.5 text-emerald-300" />
            {artifact.baselineLabel}
          </span>
        </div>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs uppercase tracking-widest text-slate-500">
                {artifact.stage}
              </p>
              <h3 className="text-base font-semibold text-slate-100">
                {artifact.stageLabel}
              </h3>
            </div>
            <span className="rounded-md border border-slate-800 bg-slate-950 px-3 py-1 text-xs text-slate-400">
              {artifact.systemUnderTest}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
            {artifact.metrics.map((metric, index) => (
              <div
                key={metric.key}
                className={cn(
                  "min-h-[86px] rounded-md border p-3",
                  metricToneByIndex[index % metricToneByIndex.length],
                )}
              >
                <p className="text-[11px] uppercase leading-tight tracking-widest opacity-75">
                  {metric.label}
                </p>
                <p className="mt-3 text-xl font-semibold">
                  {formatRagEvalMetric(metric.value, metric.format)}
                </p>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-md border border-slate-800 bg-slate-950/60">
          <div className="flex items-center gap-2 border-b border-slate-800 px-3 py-2 text-sm font-semibold text-slate-200">
            <Timer className="h-4 w-4 text-amber-300" />
            Eval Cases
          </div>
          <div className="divide-y divide-slate-800">
            {artifact.cases.map((evalCase) => (
              <div key={evalCase.caseId} className="grid gap-2 px-3 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="rounded-md bg-slate-800 px-2 py-1 text-xs font-semibold text-slate-200">
                      {evalCase.ticker}
                    </span>
                    <span className="text-xs text-slate-500">
                      {evalCase.taskType}
                    </span>
                  </div>
                  <span className="text-xs text-slate-500">
                    {evalCase.caseId}
                  </span>
                </div>
                <p className="text-xs text-slate-400">
                  Sections: {evalCase.retrievedSections.join(", ")}
                </p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-4 rounded-md border border-slate-800 bg-slate-950/70 p-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          Stage Comparison
        </p>
        {artifact.stageComparisons.length > 0 ? (
          <div className="mt-2 grid gap-2 text-xs text-slate-400 md:grid-cols-3">
            {artifact.stageComparisons.map((comparison) => (
              <div
                key={comparison.baselineLabel}
                className="rounded-md border border-slate-800 bg-slate-900/80 p-3"
              >
                <p className="font-semibold text-slate-200">
                  {comparison.stageLabel}
                </p>
                <p className="mt-1 text-slate-500">
                  {comparison.baselineLabel}
                </p>
                <div className="mt-3 grid gap-1">
                  {comparison.metrics.slice(0, 3).map((metric) => (
                    <div
                      key={metric.key}
                      className="flex items-center justify-between gap-2"
                    >
                      <span>{metric.label}</span>
                      <span className="font-semibold text-slate-200">
                        {formatRagEvalMetric(metric.value, metric.format)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-xs leading-5 text-slate-400">
            No later-stage comparison artifacts yet.
          </p>
        )}
      </div>

      <div className="mt-4 rounded-md border border-slate-800 bg-slate-950/70 p-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          Current Limits
        </p>
        <ul className="mt-2 grid gap-1 text-xs leading-5 text-slate-400 md:grid-cols-3">
          {artifact.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </div>
      </section>
      <ReleaseReadinessChecklist />
    </div>
  );
}
