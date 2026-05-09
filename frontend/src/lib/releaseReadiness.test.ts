import { describe, expect, it } from "vitest";

import {
  formatReleaseMetric,
  RELEASE_READINESS_ARTIFACT,
} from "@/lib/releaseReadiness";

describe("release readiness artifact", () => {
  it("loads production gate summaries for the dashboard checklist", () => {
    expect(RELEASE_READINESS_ARTIFACT.stage).toBe("release_readiness");
    expect(RELEASE_READINESS_ARTIFACT.overallStatus).toBe("passed");
    expect(RELEASE_READINESS_ARTIFACT.gates.map((gate) => gate.id)).toEqual([
      "rag_hard_gate",
      "provider_rag_sample_gate",
      "provider_live_planner_gate",
      "compose_full_e2e",
    ]);
    expect(
      RELEASE_READINESS_ARTIFACT.gates.find(
        (gate) => gate.id === "provider_rag_sample_gate",
      )?.metrics.caseCount,
    ).toBe(24);
  });

  it("formats compact release metrics for checklist rows", () => {
    expect(formatReleaseMetric(1)).toBe("100.0%");
    expect(formatReleaseMetric(24)).toBe("24");
    expect(formatReleaseMetric("coverage_stop")).toBe("coverage_stop");
    expect(formatReleaseMetric(["frontend", "backend"])).toBe(
      "frontend, backend",
    );
  });
});
