#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/app"

JAVA_PORT="${PORT:-8081}"
RESEARCH_PORT="${RESEARCH_SERVICE_PORT:-8090}"

export RESEARCH_SERVICE_BASE_URL="${RESEARCH_SERVICE_BASE_URL:-http://127.0.0.1:${RESEARCH_PORT}}"
export RESEARCH_SERVICE_TIMEOUT="${RESEARCH_SERVICE_TIMEOUT:-PT300S}"
export PYTHON_BIN="${PYTHON_BIN:-/opt/backend-venv/bin/python}"

start_research_service() {
  local research_venv="${APP_ROOT}/src/research-service/.venv/bin"
  export PATH="${research_venv}:${PATH}"

  if [[ ! -x "${research_venv}/python" ]]; then
    echo "Missing research service virtualenv at ${research_venv}" >&2
    exit 1
  fi

  echo "Starting Python Research Service on ${RESEARCH_SERVICE_BASE_URL}"
  (
    cd "${APP_ROOT}/src/research-service"
    exec "${research_venv}/python" -m uvicorn app.main:app --host 127.0.0.1 --port "${RESEARCH_PORT}"
  ) >"${APP_ROOT}/tmp/research-service.log" 2>&1 &
  RESEARCH_PID=$!
}

wait_for_research_service() {
  local deadline=$((SECONDS + 180))

  until curl -fsS "${RESEARCH_SERVICE_BASE_URL}/health" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for Python Research Service: ${RESEARCH_SERVICE_BASE_URL}/health" >&2
      exit 1
    fi
    sleep 2
  done
}

start_backend() {
  echo "Starting Spring Boot backend on http://127.0.0.1:${JAVA_PORT}"
  exec bash -lc "SERVER_PORT='${JAVA_PORT}' java ${JAVA_OPTS:-} -Dserver.port='${JAVA_PORT}' -jar /app/app.jar"
}

trap 'if [[ -n "${RESEARCH_PID:-}" ]] && kill -0 "${RESEARCH_PID}" >/dev/null 2>&1; then kill "${RESEARCH_PID}" >/dev/null 2>&1 || true; fi' EXIT

mkdir -p "${APP_ROOT}/tmp"
start_research_service
wait_for_research_service
start_backend
