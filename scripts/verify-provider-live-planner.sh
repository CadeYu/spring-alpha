#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_PATH="${PROVIDER_LIVE_PLANNER_ARTIFACT_PATH:-${TMPDIR:-/tmp}/spring-alpha-provider-live-planner.json}"

if [[ -z "${PROVIDER:-}" && -z "${PROVIDER_LIVE_PLANNER_PROVIDER:-}" ]]; then
  if [[ -n "${SILICONFLOW_API_KEY:-}" ]]; then
    export PROVIDER="siliconflow"
  elif [[ -n "${GEMINI_API_KEY:-}" ]]; then
    export PROVIDER="gemini"
  elif [[ -n "${OPENAI_API_KEY:-}" ]]; then
    export PROVIDER="openai"
  else
    echo "Set PROVIDER plus a matching API key, or provide SILICONFLOW_API_KEY, GEMINI_API_KEY, or OPENAI_API_KEY." >&2
    exit 2
  fi
fi

cd "${ROOT_DIR}/src/research-service"

echo "Writing provider live planner artifact for ${PROVIDER:-${PROVIDER_LIVE_PLANNER_PROVIDER}}..."
uv run python scripts/write_provider_live_planner_artifact.py "${ARTIFACT_PATH}" >/dev/null

python - "${ARTIFACT_PATH}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as artifact_file:
    artifact = json.load(artifact_file)

if artifact["stage"] != "stage_1_provider_live_planner":
    raise SystemExit("unexpected provider live planner stage")
if artifact["status"] not in {"ok", "degraded"}:
    raise SystemExit("unexpected provider live planner status")
if artifact["eventCount"] <= 0:
    raise SystemExit("provider live planner did not record events")
if artifact["plannerEventCount"] <= 0:
    raise SystemExit("provider live planner did not record planner events")
if artifact["hasPlannerContext"] is not True:
    raise SystemExit("provider live planner did not preserve planner context")
if artifact["finalReportTaskType"] != "latest_earnings_readout":
    raise SystemExit("provider live planner did not return latest earnings sections")
if not artifact["toolNames"]:
    raise SystemExit("provider live planner did not execute any tools")
PY

echo "Provider live planner verification passed: ${ARTIFACT_PATH}"
