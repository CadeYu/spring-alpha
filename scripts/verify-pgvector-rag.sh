#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="${RAG_PGVECTOR_TEST_CONTAINER:-spring-alpha-rag-pgvector-test}"
POSTGRES_USER="${RAG_PGVECTOR_TEST_USER:-spring_alpha}"
POSTGRES_PASSWORD="${RAG_PGVECTOR_TEST_PASSWORD:-spring_alpha}"
POSTGRES_DB="${RAG_PGVECTOR_TEST_DB:-spring_alpha_rag}"
POSTGRES_PORT="${RAG_PGVECTOR_TEST_PORT:-55432}"
IMAGE="${RAG_PGVECTOR_TEST_IMAGE:-pgvector/pgvector:pg16}"
DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT}/${POSTGRES_DB}"
STARTED_CONTAINER=""

cleanup() {
  if [[ -n "${STARTED_CONTAINER}" ]]; then
    docker rm -f "${STARTED_CONTAINER}" >/dev/null 2>&1 || true
  fi
}

wait_for_postgres() {
  local deadline=$((SECONDS + 90))

  until docker exec "${CONTAINER_NAME}" pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; do
    if (( SECONDS >= deadline )); then
      echo "Timed out waiting for PGVector test database" >&2
      docker logs "${CONTAINER_NAME}" >&2 || true
      exit 1
    fi
    sleep 2
  done
}

if ! command -v docker >/dev/null 2>&1; then
  echo "Missing required command: docker" >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Missing required command: uv" >&2
  exit 1
fi

trap cleanup EXIT

docker rm -f "${CONTAINER_NAME}" >/dev/null 2>&1 || true

echo "Starting PGVector test database on 127.0.0.1:${POSTGRES_PORT}..."
docker run \
  --name "${CONTAINER_NAME}" \
  -e POSTGRES_USER="${POSTGRES_USER}" \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  -e POSTGRES_DB="${POSTGRES_DB}" \
  -p "${POSTGRES_PORT}:5432" \
  -d "${IMAGE}" >/dev/null
STARTED_CONTAINER="${CONTAINER_NAME}"

wait_for_postgres

echo "Running Python RAG PGVector integration test..."
cd "${ROOT_DIR}/src/research-service"
RAG_PGVECTOR_TEST_DATABASE_URL="${DATABASE_URL}" \
uv run pytest tests/rag/test_pgvector_integration.py -q

echo "PGVector RAG verification passed."
