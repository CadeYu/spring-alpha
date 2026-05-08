import { describe, expect, it } from "vitest";

import {
  formatRagEvalMetric,
  STAGE0_RAG_EVAL_ARTIFACT,
  STAGE1_HARD_RAG_EVAL_ARTIFACT,
} from "@/lib/ragEvalDashboard";

describe("rag eval dashboard artifact", () => {
  it("loads the stage 0 baseline from a fixture artifact", () => {
    expect(STAGE0_RAG_EVAL_ARTIFACT.datasetName).toBe(
      "stage0_mvp_retrieval_baseline",
    );
    expect(STAGE0_RAG_EVAL_ARTIFACT.baselineLabel).toBe(
      "current_placeholder_retrieval",
    );
    expect(STAGE0_RAG_EVAL_ARTIFACT.stageComparisons).toEqual([]);
  });

  it("formats ratio metrics with one decimal point for comparisons", () => {
    expect(formatRagEvalMetric(0.994, "ratio")).toBe("99.4%");
    expect(formatRagEvalMetric(1, "ratio")).toBe("100.0%");
    expect(formatRagEvalMetric(12, "milliseconds")).toBe("12 ms");
    expect(formatRagEvalMetric(0, "usd")).toBe("$0.00");
  });

  it("loads the persisted stage 1 hard RAG experiment artifact", () => {
    expect(STAGE1_HARD_RAG_EVAL_ARTIFACT.datasetName).toBe(
      "stage1_hard_rag_eval",
    );
    expect(STAGE1_HARD_RAG_EVAL_ARTIFACT.baselineLabel).toBe(
      "hybrid_semantic_lexical_retrieval",
    );
    expect(STAGE1_HARD_RAG_EVAL_ARTIFACT.stageComparisons.length).toBeGreaterThan(
      0,
    );
    expect(STAGE1_HARD_RAG_EVAL_ARTIFACT.metrics.map((metric) => metric.key)).toContain(
      "badSectionLeakRate",
    );
  });
});
