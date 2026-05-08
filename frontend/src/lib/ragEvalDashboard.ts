import stage0Artifact from "@/data/rag-eval/stage0.json";
import stage1HardArtifact from "@/data/rag-eval/stage1-hard.json";

export type RagEvalMetricKey =
  | "retrievalRecallAt5"
  | "contextPrecision"
  | "faithfulness"
  | "citationCoverage"
  | "fallbackRate"
  | "totalLatencyMs"
  | "costUsd"
  | "expectedTermHitRate"
  | "expectedSectionHitRate"
  | "top1SectionCorrectness"
  | "emptyRetrievalRate"
  | "badSectionLeakRate"
  | "maxSourcePayloadBytes";

export interface RagEvalMetric {
  key: RagEvalMetricKey;
  label: string;
  value: number;
  format: "ratio" | "milliseconds" | "usd";
}

export interface RagEvalCaseResult {
  caseId: string;
  ticker: string;
  taskType: string;
  retrievedSections: string[];
  metrics: Pick<RagEvalMetric, "key" | "value" | "format">[];
}

export interface RagEvalDashboardArtifact {
  stage: string;
  stageLabel: string;
  datasetName: string;
  systemUnderTest: string;
  baselineLabel: string;
  metrics: RagEvalMetric[];
  cases: RagEvalCaseResult[];
  stageComparisons: RagEvalDashboardArtifact[];
  limitations: string[];
}

export const STAGE0_RAG_EVAL_ARTIFACT =
  stage0Artifact as RagEvalDashboardArtifact;
export const STAGE1_HARD_RAG_EVAL_ARTIFACT =
  stage1HardArtifact as RagEvalDashboardArtifact;

export function formatRagEvalMetric(
  value: number,
  format: RagEvalMetric["format"],
): string {
  if (format === "ratio") {
    return `${(value * 100).toFixed(1)}%`;
  }

  if (format === "milliseconds") {
    return `${value} ms`;
  }

  return `$${value.toFixed(2)}`;
}
