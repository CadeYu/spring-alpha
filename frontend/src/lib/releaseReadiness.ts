import releaseReadinessArtifact from "@/data/release-readiness.json";

export type ReleaseGateStatus = "passed" | "attention";

export interface ReleaseReadinessGate {
  id: string;
  label: string;
  status: ReleaseGateStatus;
  summary: string;
  metrics: Record<string, number | string | string[]>;
  details: string[];
}

export interface ReleaseReadinessArtifact {
  schemaVersion: string;
  stage: "release_readiness";
  overallStatus: ReleaseGateStatus;
  gates: ReleaseReadinessGate[];
  limitations: string[];
}

export const RELEASE_READINESS_ARTIFACT =
  releaseReadinessArtifact as unknown as ReleaseReadinessArtifact;

export function formatReleaseMetric(value: number | string | string[]): string {
  if (Array.isArray(value)) {
    return value.join(", ");
  }

  if (typeof value === "number") {
    if (value >= 0 && value <= 1) {
      return `${(value * 100).toFixed(1)}%`;
    }
    return Number.isInteger(value) ? `${value}` : value.toFixed(2);
  }

  return value;
}
