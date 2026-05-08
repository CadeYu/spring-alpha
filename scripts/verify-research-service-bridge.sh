#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESEARCH_SERVICE_PORT="${RESEARCH_SERVICE_PORT:-8090}"
RESEARCH_SERVICE_BASE_URL="${RESEARCH_SERVICE_BASE_URL:-http://127.0.0.1:${RESEARCH_SERVICE_PORT}}"

STARTED_PID=""

cleanup() {
  if [[ -n "${STARTED_PID}" ]] && kill -0 "${STARTED_PID}" >/dev/null 2>&1; then
    kill "${STARTED_PID}" >/dev/null 2>&1 || true
  fi
}

wait_for_http() {
  local url="$1"
  local deadline=$((SECONDS + 90))

  until curl -fsS "$url" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for ${url}" >&2
      exit 1
    fi
    sleep 2
  done
}

if ! command -v uv >/dev/null 2>&1; then
  echo "Missing required command: uv" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Missing required command: curl" >&2
  exit 1
fi

trap cleanup EXIT

echo "Starting Python Research Service on ${RESEARCH_SERVICE_BASE_URL}..."
bash -lc "cd '${ROOT_DIR}/src/research-service' && uv run uvicorn app.main:app --host 127.0.0.1 --port '${RESEARCH_SERVICE_PORT}'" &
STARTED_PID="$!"

wait_for_http "${RESEARCH_SERVICE_BASE_URL}/health"

echo "Running Java-to-Python Research Service contract test..."
cd "${ROOT_DIR}/backend"
RUN_RESEARCH_SERVICE_CONTRACT=true \
RESEARCH_SERVICE_BASE_URL="${RESEARCH_SERVICE_BASE_URL}" \
mvn -q -Dtest=ResearchServiceAgentClientPythonContractTest test

echo "Research Service bridge verification passed."
