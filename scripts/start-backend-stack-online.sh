#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/lib/backend-stack-common.sh
source "${SCRIPT_DIR}/lib/backend-stack-common.sh"

QDRANT_COLLECTION="${QDRANT_COLLECTION:-spring_alpha_rag_chunks}"

require_online_env() {
  require_env SPRING_DATASOURCE_URL
  require_env SPRING_DATASOURCE_USERNAME
  require_env SPRING_DATASOURCE_PASSWORD
  require_env QDRANT_URL
  require_env QDRANT_API_KEY
}

start_research_service() {
  echo "Starting Python Research Service with Qdrant RAG on ${RESEARCH_SERVICE_BASE_URL}"
  (
    cd "${ROOT_DIR}/src/research-service"
    RAG_VECTOR_STORE_PROVIDER=qdrant \
      QDRANT_URL="${QDRANT_URL}" \
      QDRANT_API_KEY="${QDRANT_API_KEY}" \
      QDRANT_COLLECTION="${QDRANT_COLLECTION}" \
      RAG_EMBEDDING_PROVIDER="${RAG_EMBEDDING_PROVIDER}" \
      RAG_EMBEDDING_DIMENSION="${RAG_EMBEDDING_DIMENSION}" \
      SILICONFLOW_MODEL="${SILICONFLOW_MODEL}" \
      uv run uvicorn app.main:app --host 127.0.0.1 --port "${RESEARCH_SERVICE_PORT}"
  ) >"${LOG_DIR}/research-service-online.log" 2>&1 &
  BACKGROUND_PIDS+=("$!")
}

start_backend() {
  echo "Starting Spring Boot backend with online Supabase DB on ${BACKEND_URL}"
  echo "Logs: ${LOG_DIR}/backend-online.log"
  (
    cd "${ROOT_DIR}/backend"
    SERVER_PORT="${BACKEND_PORT}" \
      SPRING_PROFILES_ACTIVE="${SPRING_PROFILES_ACTIVE:-prod}" \
      SPRING_DATASOURCE_URL="${SPRING_DATASOURCE_URL}" \
      SPRING_DATASOURCE_USERNAME="${SPRING_DATASOURCE_USERNAME}" \
      SPRING_DATASOURCE_PASSWORD="${SPRING_DATASOURCE_PASSWORD}" \
      SPRING_JPA_HIBERNATE_DDL_AUTO="${SPRING_JPA_HIBERNATE_DDL_AUTO:-update}" \
      RESEARCH_SERVICE_BASE_URL="${RESEARCH_SERVICE_BASE_URL}" \
      RESEARCH_SERVICE_TIMEOUT="${RESEARCH_SERVICE_TIMEOUT}" \
      MAVEN_OPTS="${MAVEN_OPTS:--Xms256m -Xmx1024m}" \
      bash -lc "$(backend_command)"
  ) 2>&1 | tee "${LOG_DIR}/backend-online.log"
}

print_ready_summary() {
  cat <<EOF

Online backend stack status
  Metadata DB:             Supabase (${SPRING_DATASOURCE_USERNAME})
  RAG vector store:        Qdrant collection ${QDRANT_COLLECTION}
  Python Research Service: ${RESEARCH_SERVICE_BASE_URL}
  Spring Boot backend:     ${BACKEND_URL}

Logs
  Python Research Service: ${LOG_DIR}/research-service-online.log
  Spring Boot backend:     ${LOG_DIR}/backend-online.log

Keep this terminal open. Press Ctrl+C here to stop Python Research Service and Spring Boot.
This script does not start local Docker PGVector.

EOF
}

main() {
  load_env
  require_backend_stack_commands
  require_online_env
  prepare_backend_stack_ports

  trap cleanup_background_services EXIT

  start_research_service
  wait_for_http "${RESEARCH_SERVICE_BASE_URL}/health" "Python Research Service"

  print_ready_summary
  start_backend
}

main "$@"
