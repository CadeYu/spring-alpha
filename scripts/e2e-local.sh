#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-mocked}"

for env_file in "${ROOT_DIR}/.env" "${ROOT_DIR}/.env.local"; do
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "${env_file}"
    set +a
  fi
done

FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8081}"
RESEARCH_SERVICE_PORT="${RESEARCH_SERVICE_PORT:-8090}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"
RESEARCH_SERVICE_BASE_URL="${RESEARCH_SERVICE_BASE_URL:-http://127.0.0.1:${RESEARCH_SERVICE_PORT}}"
RESEARCH_SERVICE_TIMEOUT="${RESEARCH_SERVICE_TIMEOUT:-PT75S}"
LIVE_AGENT_RESEARCH_SERVICE_TIMEOUT="${LIVE_AGENT_RESEARCH_SERVICE_TIMEOUT:-PT75S}"

usage() {
  cat <<EOF
Usage:
  ./scripts/e2e-local.sh [mocked|services|live-agent|--print]

Modes:
  mocked      Run frontend Playwright tests with mocked backend responses.
  services    Start Python Research Service and Spring Boot, then run Playwright.
  live-agent  Start services, then run only the live Agent Playwright path.
  --print     Print resolved commands without starting services.

Environment:
  FRONTEND_PORT=${FRONTEND_PORT}
  BACKEND_PORT=${BACKEND_PORT}
  RESEARCH_SERVICE_PORT=${RESEARCH_SERVICE_PORT}
  BACKEND_URL=${BACKEND_URL}
  RESEARCH_SERVICE_BASE_URL=${RESEARCH_SERVICE_BASE_URL}
  RESEARCH_SERVICE_TIMEOUT=${RESEARCH_SERVICE_TIMEOUT}
  LIVE_AGENT_RESEARCH_SERVICE_TIMEOUT=${LIVE_AGENT_RESEARCH_SERVICE_TIMEOUT}
EOF
}

backend_command() {
  if [[ -x "${ROOT_DIR}/backend/mvnw" ]]; then
    printf './mvnw spring-boot:run'
  else
    printf 'mvn spring-boot:run'
  fi
}

print_plan() {
  cat <<EOF
Spring Alpha E2E local plan

Mocked mode:
  cd "${ROOT_DIR}/frontend"
  BACKEND_URL="${BACKEND_URL}" npm run test:e2e

Services mode:
  cd "${ROOT_DIR}/src/research-service"
  uv run uvicorn app.main:app --host 127.0.0.1 --port "${RESEARCH_SERVICE_PORT}"

  cd "${ROOT_DIR}/backend"
  RESEARCH_SERVICE_BASE_URL="${RESEARCH_SERVICE_BASE_URL}" \\
  RESEARCH_SERVICE_TIMEOUT="${RESEARCH_SERVICE_TIMEOUT}" \\
  $(backend_command)

  cd "${ROOT_DIR}/frontend"
  BACKEND_URL="${BACKEND_URL}" npm run test:e2e

Live Agent mode:
  Same services as above, then:
  RESEARCH_SERVICE_TIMEOUT="${LIVE_AGENT_RESEARCH_SERVICE_TIMEOUT}"

  cd "${ROOT_DIR}/frontend"
  BACKEND_URL="${BACKEND_URL}" \\
  RUN_LIVE_AGENT_E2E=true \\
  SILICONFLOW_API_KEY="<runtime only>" \\
  npx playwright test e2e/smoke.spec.ts -g "live Agent"
EOF
}

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

require_services_env() {
  require_command curl
  require_command uv
  require_command npm

  if [[ -x "${ROOT_DIR}/backend/mvnw" ]]; then
    :
  else
    require_command mvn
  fi

  if [[ -z "${NEON_PASSWORD:-}" && -z "${SPRING_DATASOURCE_PASSWORD:-}" ]]; then
    cat >&2 <<EOF
Missing database password for services mode.

Set one of:
  NEON_PASSWORD
  SPRING_DATASOURCE_PASSWORD

The backend currently initializes JPA on startup, so cross-service E2E cannot
start Spring Boot without a database password.
EOF
    exit 1
  fi
}

require_live_agent_env() {
  require_services_env

  if [[ -z "${SILICONFLOW_API_KEY:-}" ]]; then
    cat >&2 <<EOF
Missing SiliconFlow API key for live-agent mode.

Set:
  SILICONFLOW_API_KEY

The key is used only as a runtime environment variable for the browser E2E run.
EOF
    exit 1
  fi
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local deadline=$((SECONDS + 90))

  until curl -fsS "$url" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for ${label}: ${url}" >&2
      exit 1
    fi
    sleep 2
  done
}

start_background() {
  local label="$1"
  shift

  echo "Starting ${label}..."
  "$@" &
  STARTED_PIDS+=("$!")
}

cleanup() {
  if ((${#STARTED_PIDS[@]} == 0)); then
    return
  fi

  echo "Stopping E2E services..."
  for pid in "${STARTED_PIDS[@]}"; do
    if kill -0 "$pid" >/dev/null 2>&1; then
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
}

run_mocked() {
  cd "${ROOT_DIR}/frontend"
  BACKEND_URL="${BACKEND_URL}" npm run test:e2e
}

run_live_agent_playwright() {
  cd "${ROOT_DIR}/frontend"
  BACKEND_URL="${BACKEND_URL}" \
    RUN_LIVE_AGENT_E2E=true \
    npx playwright test e2e/smoke.spec.ts -g "live Agent"
}

run_services() {
  STARTED_PIDS=()
  trap cleanup EXIT
  local playwright_mode="${1:-mocked}"
  local effective_research_service_timeout="${RESEARCH_SERVICE_TIMEOUT}"
  if [[ "${playwright_mode}" == "live-agent" ]]; then
    require_live_agent_env
    effective_research_service_timeout="${LIVE_AGENT_RESEARCH_SERVICE_TIMEOUT}"
  else
    require_services_env
  fi

  start_background "Python Research Service" \
    bash -lc "cd '${ROOT_DIR}/src/research-service' && uv run uvicorn app.main:app --host 127.0.0.1 --port '${RESEARCH_SERVICE_PORT}'"
  wait_for_http "${RESEARCH_SERVICE_BASE_URL}/health" "Python Research Service"

  start_background "Spring Boot backend" \
    bash -lc "cd '${ROOT_DIR}/backend' && RESEARCH_SERVICE_BASE_URL='${RESEARCH_SERVICE_BASE_URL}' RESEARCH_SERVICE_TIMEOUT='${effective_research_service_timeout}' $(backend_command)"
  wait_for_http "${BACKEND_URL}/api/sec/models" "Spring Boot backend"

  if [[ "${playwright_mode}" == "live-agent" ]]; then
    run_live_agent_playwright
  else
    run_mocked
  fi
}

case "${MODE}" in
  --help|-h)
    usage
    ;;
  --print)
    print_plan
    ;;
  mocked)
    run_mocked
    ;;
  services)
    run_services
    ;;
  live-agent)
    run_services live-agent
    ;;
  *)
    echo "Unsupported mode: ${MODE}" >&2
    usage >&2
    exit 1
    ;;
esac
