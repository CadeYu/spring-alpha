#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_PATH="${PROVIDER_REPORT_SYNTHESIS_ARTIFACT_PATH:-${TMPDIR:-/tmp}/spring-alpha-provider-report-synthesis.json}"

if [[ -z "${PROVIDER:-}" && -z "${PROVIDER_REPORT_SYNTHESIS_PROVIDER:-}" ]]; then
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

echo "Writing provider report synthesis artifact for ${PROVIDER:-${PROVIDER_REPORT_SYNTHESIS_PROVIDER}}..."
uv run python scripts/write_provider_report_synthesis_artifact.py "${ARTIFACT_PATH}" >/dev/null

python - "${ARTIFACT_PATH}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as artifact_file:
    artifact = json.load(artifact_file)

if artifact["stage"] != "stage_1_provider_report_synthesis":
    raise SystemExit("unexpected provider report synthesis stage")
if artifact["finalReportTaskType"] not in {
    "latest_earnings_readout",
    "business_driver_deep_dive",
}:
    raise SystemExit("provider synthesis did not return supported task sections")
if artifact["synthesis"] != "llm":
    raise SystemExit("provider synthesis did not use llm final synthesis")
if artifact["claimCount"] <= 0:
    raise SystemExit("provider synthesis returned no claims")
if not artifact["citedSourceIds"]:
    raise SystemExit("provider synthesis returned no cited source ids")
PY

echo "Provider report synthesis verification passed: ${ARTIFACT_PATH}"
