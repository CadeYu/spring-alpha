#!/usr/bin/env bash

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/tmp/dev-logs}"

RESEARCH_SERVICE_PORT="${RESEARCH_SERVICE_PORT:-8090}"
RESEARCH_SERVICE_BASE_URL="${RESEARCH_SERVICE_BASE_URL:-http://127.0.0.1:${RESEARCH_SERVICE_PORT}}"
BACKEND_STACK_RESEARCH_SERVICE_TIMEOUT="${BACKEND_STACK_RESEARCH_SERVICE_TIMEOUT:-PT300S}"
RESEARCH_SERVICE_TIMEOUT="${RESEARCH_SERVICE_TIMEOUT:-${BACKEND_STACK_RESEARCH_SERVICE_TIMEOUT}}"

BACKEND_PORT="${BACKEND_PORT:-8082}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"

RAG_EMBEDDING_PROVIDER="${RAG_EMBEDDING_PROVIDER:-deterministic}"
RAG_EMBEDDING_DIMENSION="${RAG_EMBEDDING_DIMENSION:-3072}"
SILICONFLOW_MODEL="${SILICONFLOW_MODEL:-Pro/moonshotai/Kimi-K2.6}"

BACKGROUND_PIDS=()

load_env() {
  for env_file in "${ROOT_DIR}/.env" "${ROOT_DIR}/.env.local"; do
    if [[ -f "${env_file}" ]]; then
      set -a
      # shellcheck source=/dev/null
      source "${env_file}"
      set +a
    fi
  done
}

require_command() {
  local command_name="$1"
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Missing required command: ${command_name}" >&2
    exit 1
  fi
}

require_env() {
  local name="$1"
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 1
  fi
}

backend_command() {
  if [[ -x "${ROOT_DIR}/backend/mvnw" ]]; then
    printf './mvnw spring-boot:run'
  else
    printf 'mvn spring-boot:run'
  fi
}

port_is_busy() {
  local port="$1"
  lsof -ti TCP:"${port}" -sTCP:LISTEN >/dev/null 2>&1
}

kill_port_if_busy() {
  local port="$1"
  local label="$2"
  local pids

  pids="$(lsof -ti TCP:"${port}" -sTCP:LISTEN || true)"
  if [[ -z "${pids}" ]]; then
    echo "${label} port ${port} is available."
    return
  fi

  echo "${label} port ${port} is occupied by PID(s): ${pids}"
  echo "Stopping process(es) on port ${port}..."
  # shellcheck disable=SC2086
  kill ${pids} >/dev/null 2>&1 || true
  sleep 1

  if port_is_busy "${port}"; then
    echo "Process on port ${port} did not stop gracefully; forcing shutdown..."
    pids="$(lsof -ti TCP:"${port}" -sTCP:LISTEN || true)"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill -9 ${pids} >/dev/null 2>&1 || true
      sleep 1
    fi
  fi

  if port_is_busy "${port}"; then
    echo "Failed to free ${label} port ${port}." >&2
    exit 1
  fi

  echo "${label} port ${port} is now free."
}

wait_for_http() {
  local url="$1"
  local label="$2"
  local deadline=$((SECONDS + 180))

  until curl -fsS "${url}" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for ${label}: ${url}" >&2
      exit 1
    fi
    sleep 2
  done
}

cleanup_background_services() {
  if ((${#BACKGROUND_PIDS[@]} == 0)); then
    return
  fi

  echo "Stopping background services..."
  for pid in "${BACKGROUND_PIDS[@]}"; do
    if kill -0 "${pid}" >/dev/null 2>&1; then
      kill "${pid}" >/dev/null 2>&1 || true
    fi
  done
}

require_backend_stack_commands() {
  require_command curl
  require_command lsof
  require_command uv
  if [[ ! -x "${ROOT_DIR}/backend/mvnw" ]]; then
    require_command mvn
  fi
}

prepare_backend_stack_ports() {
  mkdir -p "${LOG_DIR}"
  kill_port_if_busy "${RESEARCH_SERVICE_PORT}" "Python Research Service"
  kill_port_if_busy "${BACKEND_PORT}" "Spring Boot backend"
}
