#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-spring-alpha-e2e}"
POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-15433}"
FRONTEND_HOST_PORT="${FRONTEND_HOST_PORT:-13000}"
BACKEND_HOST_PORT="${BACKEND_HOST_PORT:-18081}"
RESEARCH_SERVICE_HOST_PORT="${RESEARCH_SERVICE_HOST_PORT:-18090}"
FRONTEND_URL="${FRONTEND_URL:-http://127.0.0.1:${FRONTEND_HOST_PORT}}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_HOST_PORT}}"
RESEARCH_SERVICE_URL="${RESEARCH_SERVICE_URL:-http://127.0.0.1:${RESEARCH_SERVICE_HOST_PORT}}"

compose() {
  docker compose -p "${COMPOSE_PROJECT_NAME}" "$@"
}

cleanup() {
  if [[ "${KEEP_COMPOSE_E2E:-false}" != "true" ]]; then
    compose down -v --remove-orphans >/dev/null 2>&1 || true
  fi
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local deadline=$((SECONDS + 240))

  until curl -fsS "${url}" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for ${label}: ${url}" >&2
      compose ps >&2 || true
      compose logs --tail=200 >&2 || true
      exit 1
    fi
    sleep 3
  done
}

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command: docker" >&2
  exit 1
fi

if ! command -v curl >/dev/null 2>&1; then
  echo "Missing required command: curl" >&2
  exit 1
fi

trap cleanup EXIT

cd "${ROOT_DIR}"

compose down -v --remove-orphans >/dev/null 2>&1 || true

echo "Building and starting full compose stack..."
POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT}" \
FRONTEND_HOST_PORT="${FRONTEND_HOST_PORT}" \
BACKEND_HOST_PORT="${BACKEND_HOST_PORT}" \
RESEARCH_SERVICE_HOST_PORT="${RESEARCH_SERVICE_HOST_PORT}" \
compose up --build -d pgvector research-service backend frontend

wait_for_http "${RESEARCH_SERVICE_URL}/health" "Python Research Service"
wait_for_http "${BACKEND_URL}/api/sec/models" "Spring Boot backend"
wait_for_http "${FRONTEND_URL}/app" "Next.js frontend"

echo "Checking Python Agent run with request-scoped filing evidence..."
AGENT_RESPONSE="$(
  curl -fsS \
    -H "Content-Type: application/json" \
    -d '{
      "run_id": "compose_full_e2e_agent",
      "ticker": "AAPL",
      "task_type": "latest_earnings_readout",
      "language": "en",
      "filings": [
        {
          "ticker": "AAPL",
          "filing_type": "10-Q",
          "filing_date": "2026-01-01",
          "accession_number": "compose-e2e",
          "text": "Management Discussion and Analysis. Apple revenue increased because services demand, iPhone demand, and gross margin improved. Risk Factors include supply chain disruption and foreign exchange volatility. Liquidity and Capital Resources show operating cash flow, capital expenditures, and share repurchases."
        }
      ]
    }' \
    "${RESEARCH_SERVICE_URL}/agent/runs"
)"

AGENT_RESPONSE="${AGENT_RESPONSE}" python - <<'PY'
import json
import os

payload = json.loads(os.environ["AGENT_RESPONSE"])
if payload["run_id"] != "compose_full_e2e_agent":
    raise SystemExit("agent run_id mismatch")
if payload["status"] not in {"ok", "degraded"}:
    raise SystemExit(f"unexpected agent status: {payload['status']}")
events = payload.get("events") or []
if not events:
    raise SystemExit("agent run returned no events")
final_report = payload.get("final_report") or {}
task_sections = final_report.get("task_sections") or {}
if task_sections.get("task_type") != "latest_earnings_readout":
    raise SystemExit("agent run did not return latest earnings task sections")
if not final_report.get("retrieval_records"):
    raise SystemExit("agent run did not return retrieval records")
if not any(event.get("tool_name") == "search_filing_sections" for event in events):
    raise SystemExit("agent run did not execute filing section retrieval")
PY

echo "Checking compose service health..."
compose ps

echo "Compose full E2E verification passed."
