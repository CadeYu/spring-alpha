#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_PATH="${PROVIDER_TOOL_E2E_ARTIFACT_PATH:-${TMPDIR:-/tmp}/spring-alpha-provider-tool-e2e.json}"

if [[ -z "${PROVIDER:-}" && -z "${PROVIDER_TOOL_E2E_PROVIDER:-}" ]]; then
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

echo "Writing provider tool E2E artifact for ${PROVIDER:-${PROVIDER_TOOL_E2E_PROVIDER}}..."
uv run python scripts/write_provider_tool_e2e_artifact.py "${ARTIFACT_PATH}" >/dev/null

python - "${ARTIFACT_PATH}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as artifact_file:
    artifact = json.load(artifact_file)

if artifact["stage"] != "stage_1_provider_tool_e2e":
    raise SystemExit("unexpected provider tool E2E stage")
if artifact["status"] != "ok":
    raise SystemExit("provider tool E2E did not finish ok")
if artifact["synthesis"] != "llm":
    raise SystemExit("provider tool E2E did not use llm final synthesis")
if artifact["factSource"] != "sec_companyfacts":
    raise SystemExit("provider tool E2E did not use SEC company facts")
if artifact["factMetricCount"] <= 0:
    raise SystemExit("provider tool E2E returned no fact metrics")
if artifact["ragSourceRefCount"] <= 0:
    raise SystemExit("provider tool E2E returned no RAG source refs")
PY

echo "Provider tool E2E verification passed: ${ARTIFACT_PATH}"
