import { CheckCircle2, CircleAlert, ClipboardCheck } from "lucide-react";

import {
  formatReleaseMetric,
  RELEASE_READINESS_ARTIFACT,
  type ReleaseReadinessGate,
} from "@/lib/releaseReadiness";
import { cn } from "@/lib/utils";

const featuredMetricKeysByGate: Record<string, string[]> = {
  rag_hard_gate: [
    "expectedTermHitRate",
    "expectedSectionHitRate",
    "emptyRetrievalRate",
  ],
  provider_rag_sample_gate: [
    "caseCount",
    "expectedTermHitRate",
    "emptyRetrievalRate",
  ],
  provider_live_planner_gate: [
    "providerDecisionCount",
    "fallbackCount",
    "stopReason",
  ],
  provider_tool_e2e_gate: [
    "latestEarningsPath",
    "businessDriverPath",
    "cashFlowPath",
  ],
  compose_full_e2e: ["services", "agentTaskType", "retrievalRecords"],
};

export function ReleaseReadinessChecklist() {
  const artifact = RELEASE_READINESS_ARTIFACT;

  return (
    <section
      aria-labelledby="release-readiness-title"
      className="rounded-md border border-slate-800 bg-slate-900/70 p-4"
    >
      <div className="flex flex-col gap-3 border-b border-slate-800 pb-4 md:flex-row md:items-start md:justify-between">
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <ClipboardCheck className="h-5 w-5 text-cyan-300" />
            <h2
              id="release-readiness-title"
              className="text-lg font-semibold text-cyan-200"
            >
              Release Readiness
            </h2>
          </div>
          <p className="max-w-3xl text-sm leading-6 text-slate-400">
            Unified checklist for the latest RAG, provider planner, provider
            embedding, and compose E2E gates.
          </p>
        </div>
        <span
          className={cn(
            "inline-flex min-h-9 items-center gap-2 rounded-md border px-3 py-2 text-xs font-semibold uppercase tracking-widest",
            artifact.overallStatus === "passed"
              ? "border-emerald-500/30 bg-emerald-950/30 text-emerald-200"
              : "border-amber-500/30 bg-amber-950/30 text-amber-200",
          )}
        >
          {artifact.overallStatus === "passed" ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : (
            <CircleAlert className="h-4 w-4" />
          )}
          {artifact.overallStatus}
        </span>
      </div>

      <div className="mt-4 grid gap-3">
        {artifact.gates.map((gate) => (
          <ReleaseGateRow key={gate.id} gate={gate} />
        ))}
      </div>

      <div className="mt-4 rounded-md border border-slate-800 bg-slate-950/70 p-3">
        <p className="text-xs font-semibold uppercase tracking-widest text-slate-500">
          Checklist Limits
        </p>
        <ul className="mt-2 grid gap-1 text-xs leading-5 text-slate-400 md:grid-cols-3">
          {artifact.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function ReleaseGateRow({ gate }: { gate: ReleaseReadinessGate }) {
  const metricKeys = featuredMetricKeysByGate[gate.id] ?? [];

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/60 p-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={cn(
                "inline-flex h-6 items-center gap-1 rounded-md border px-2 text-xs font-semibold",
                gate.status === "passed"
                  ? "border-emerald-500/30 bg-emerald-950/30 text-emerald-200"
                  : "border-amber-500/30 bg-amber-950/30 text-amber-200",
              )}
            >
              {gate.status === "passed" ? (
                <CheckCircle2 className="h-3.5 w-3.5" />
              ) : (
                <CircleAlert className="h-3.5 w-3.5" />
              )}
              {gate.status}
            </span>
            <h3 className="text-sm font-semibold text-slate-100">
              {gate.label}
            </h3>
          </div>
          <p className="text-xs leading-5 text-slate-400">{gate.summary}</p>
          {gate.id !== "rag_hard_gate" && gate.details.length > 0 && (
            <p className="text-xs leading-5 text-slate-500">
              {gate.details[0]}
            </p>
          )}
        </div>

        <div className="grid shrink-0 gap-2 sm:grid-cols-3 md:min-w-[420px]">
          {metricKeys.map((metricKey) => (
            <div
              key={metricKey}
              className="min-h-[58px] rounded-md border border-slate-800 bg-slate-900 px-3 py-2"
            >
              <p className="text-[10px] uppercase leading-tight tracking-widest text-slate-500">
                {metricKey}
              </p>
              <p className="mt-2 break-words text-xs font-semibold text-slate-200">
                {formatReleaseMetric(gate.metrics[metricKey])}
              </p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
