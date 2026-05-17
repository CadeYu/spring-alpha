#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/backend-stack-common.sh
source "${SCRIPT_DIR}/lib/backend-stack-common.sh"

POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT:-5433}"
POSTGRES_USER="${POSTGRES_USER:-spring_alpha}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-spring_alpha}"
POSTGRES_DB="${POSTGRES_DB:-spring_alpha}"
RAG_VECTOR_TABLE_NAME="${RAG_VECTOR_TABLE_NAME:-rag_chunks_product_e2e}"

start_pgvector() {
  echo "Starting local PGVector on 127.0.0.1:${POSTGRES_HOST_PORT}"
  (
    cd "${ROOT_DIR}"
    POSTGRES_HOST_PORT="${POSTGRES_HOST_PORT}" \
      POSTGRES_USER="${POSTGRES_USER}" \
      POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
      POSTGRES_DB="${POSTGRES_DB}" \
      docker compose up -d pgvector
  )
}

start_research_service() {
  echo "Starting Python Research Service with local PGVector RAG on ${RESEARCH_SERVICE_BASE_URL}"
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
  ) >"${LOG_DIR}/research-service-local.log" 2>&1 &
  BACKGROUND_PIDS+=("$!")
}

start_backend() {
  echo "Starting Spring Boot backend with local Postgres on ${BACKEND_URL}"
  echo "Logs: ${LOG_DIR}/backend-local.log"
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
  ) 2>&1 | tee "${LOG_DIR}/backend-local.log"
}

print_ready_summary() {
  cat <<EOF

Local backend stack status
  Metadata DB:             local Postgres/PGVector 127.0.0.1:${POSTGRES_HOST_PORT}
  RAG vector store:        local PGVector table ${RAG_VECTOR_TABLE_NAME}
  Python Research Service: ${RESEARCH_SERVICE_BASE_URL}
  Spring Boot backend:     ${BACKEND_URL}

Logs
  Python Research Service: ${LOG_DIR}/research-service-local.log
  Spring Boot backend:     ${LOG_DIR}/backend-local.log

Keep this terminal open. Press Ctrl+C here to stop Python Research Service and Spring Boot.
PGVector stays running in Docker; stop it with:
  docker compose stop pgvector

EOF
}

main() {
  load_env
  require_backend_stack_commands
  require_command docker
  prepare_backend_stack_ports

  trap cleanup_background_services EXIT

  start_pgvector
  start_research_service
  wait_for_http "${RESEARCH_SERVICE_BASE_URL}/health" "Python Research Service"

  print_ready_summary
  start_backend
}

main "$@"
