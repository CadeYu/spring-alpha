#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

FRONTEND_PORT="${FRONTEND_PORT:-3001}"
BACKEND_PORT="${BACKEND_PORT:-8082}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"

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

main() {
  load_env
  require_command lsof
  require_command npm

  kill_port_if_busy "${FRONTEND_PORT}" "Frontend"

  echo "Starting Spring Alpha frontend"
  echo "URL: http://127.0.0.1:${FRONTEND_PORT}/app"
  echo "Backend URL: ${BACKEND_URL}"

  cd "${ROOT_DIR}/frontend"
  PORT="${FRONTEND_PORT}" BACKEND_URL="${BACKEND_URL}" npm run dev
}

main "$@"
