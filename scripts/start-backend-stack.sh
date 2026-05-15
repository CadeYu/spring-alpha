#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${LOG_DIR:-${ROOT_DIR}/tmp/dev-logs}"

POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5433}"
POSTGRES_USER="${POSTGRES_USER:-spring_alpha}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-spring_alpha}"
POSTGRES_DB="${POSTGRES_DB:-spring_alpha}"

RESEARCH_SERVICE_PORT="${RESEARCH_SERVICE_PORT:-8090}"
RESEARCH_SERVICE_BASE_URL="${RESEARCH_SERVICE_BASE_URL:-http://127.0.0.1:${RESEARCH_SERVICE_PORT}}"
RESEARCH_SERVICE_TIMEOUT="${RESEARCH_SERVICE_TIMEOUT:-PT300S}"
BACKEND_STACK_RESEARCH_SERVICE_TIMEOUT="${BACKEND_STACK_RESEARCH_SERVICE_TIMEOUT:-PT300S}"

BACKEND_PORT="${BACKEND_PORT:-8082}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:${BACKEND_PORT}}"

RAG_VECTOR_TABLE_NAME="${RAG_VECTOR_TABLE_NAME:-rag_chunks_product_e2e}"
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

cleanup() {
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

start_research_service() {
  mkdir -p "${LOG_DIR}"
  echo "Starting Python Research Service on ${RESEARCH_SERVICE_BASE_URL}"
  (
    cd "${ROOT_DIR}/src/research-service"
    RAG_VECTOR_STORE_PROVIDER=pgvector \
      RAG_VECTOR_DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_HOST_PORT}/${POSTGRES_DB}" \
      RAG_VECTOR_TABLE_NAME="${RAG_VECTOR_TABLE_NAME}" \
      RAG_VECTOR_INITIALIZE_SCHEMA=true \
      RAG_EMBEDDING_PROVIDER="${RAG_EMBEDDING_PROVIDER}" \
      RAG_EMBEDDING_DIMENSION="${RAG_EMBEDDING_DIMENSION}" \
      SILICONFLOW_MODEL="${SILICONFLOW_MODEL}" \
      uv run uvicorn app.main:app --host 127.0.0.1 --port "${RESEARCH_SERVICE_PORT}"
  ) >"${LOG_DIR}/research-service.log" 2>&1 &
  BACKGROUND_PIDS+=("$!")
}

start_pgvector() {
  echo "Starting PGVector on 127.0.0.1:${POSTGRES_HOST_PORT}"
  (
    cd "${ROOT_DIR}"
    POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT}" \
      POSTGRES_USER="${POSTGRES_USER}" \
      POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
      POSTGRES_DB="${POSTGRES_DB}" \
      docker compose up -d pgvector
  )
}

start_backend() {
  echo "Starting Spring Boot backend on ${BACKEND_URL}"
  echo "Logs: ${LOG_DIR}/backend.log"
  (
    cd "${ROOT_DIR}/backend"
    SERVER_PORT="${BACKEND_PORT}" \
      SPRING_PROFILES_ACTIVE="${SPRING_PROFILES_ACTIVE:-compose}" \
      SPRING_DATASOURCE_URL="jdbc:postgresql://127.0.0.1:${POSTGRES_HOST_PORT}/${POSTGRES_DB}" \
      SPRING_DATASOURCE_USERNAME="${POSTGRES_USER}" \
      SPRING_DATASOURCE_PASSWORD="${POSTGRES_PASSWORD}" \
      RESEARCH_SERVICE_BASE_URL="${RESEARCH_SERVICE_BASE_URL}" \
      RESEARCH_SERVICE_TIMEOUT="${RESEARCH_SERVICE_TIMEOUT}" \
      MAVEN_OPTS="${MAVEN_OPTS:--Xms256m -Xmx1024m}" \
      bash -lc "$(backend_command)"
  ) 2>&1 | tee "${LOG_DIR}/backend.log"
}

print_ready_summary() {
  cat <<EOF

Backend stack status
  PGVector:                127.0.0.1:${POSTGRES_HOST_PORT}
  Python Research Service: ${RESEARCH_SERVICE_BASE_URL}
  Spring Boot backend:     ${BACKEND_URL}

Logs
  Python Research Service: ${LOG_DIR}/research-service.log
  Spring Boot backend:     ${LOG_DIR}/backend.log

Keep this terminal open. Press Ctrl+C here to stop Python Research Service and Spring Boot.
PGVector stays running in Docker; stop it with:
  docker compose stop pgvector

EOF
}

main() {
  load_env
  mkdir -p "${LOG_DIR}"
  RESEARCH_SERVICE_TIMEOUT="${BACKEND_STACK_RESEARCH_SERVICE_TIMEOUT}"

  require_command curl
  require_command docker
  require_command lsof
  require_command uv
  if [[ ! -x "${ROOT_DIR}/backend/mvnw" ]]; then
    require_command mvn
  fi

  kill_port_if_busy "${RESEARCH_SERVICE_PORT}" "Python Research Service"
  kill_port_if_busy "${BACKEND_PORT}" "Spring Boot backend"

  trap cleanup EXIT

  start_pgvector
  start_research_service
  wait_for_http "${RESEARCH_SERVICE_BASE_URL}/health" "Python Research Service"

  print_ready_summary
  start_backend
}

main "$@"
