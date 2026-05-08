#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONTAINER_NAME="${RAG_PROVIDER_MINI_EVAL_CONTAINER:-spring-alpha-rag-provider-mini-eval-test}"
POSTGRES_USER="${RAG_PGVECTOR_TEST_USER:-spring_alpha}"
POSTGRES_PASSWORD="${RAG_PGVECTOR_TEST_PASSWORD:-spring_alpha}"
POSTGRES_DB="${RAG_PGVECTOR_TEST_DB:-spring_alpha_rag}"
POSTGRES_PORT="${RAG_PROVIDER_MINI_EVAL_PORT:-55435}"
IMAGE="${RAG_PGVECTOR_TEST_IMAGE:-pgvector/pgvector:pg16}"
DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:${POSTGRES_PORT}/${POSTGRES_DB}"
ARTIFACT_PATH="${RAG_PROVIDER_MINI_EVAL_ARTIFACT:-${TMPDIR:-/tmp}/spring-alpha-provider-mini-rag.json}"
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
      echo "Timed out waiting for provider mini eval database" >&2
      docker logs "${CONTAINER_NAME}" >&2 || true
      exit 1
    fi
    sleep 2
  done
}

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "GEMINI_API_KEY is required for the provider-backed mini RAG eval gate." >&2
  exit 1
fi

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

echo "Starting provider mini eval database on 127.0.0.1:${POSTGRES_PORT}..."
docker run \
  --name "${CONTAINER_NAME}" \
  -e POSTGRES_USER="${POSTGRES_USER}" \
  -e POSTGRES_PASSWORD="${POSTGRES_PASSWORD}" \
  -e POSTGRES_DB="${POSTGRES_DB}" \
  -p "${POSTGRES_PORT}:5432" \
  -d "${IMAGE}" >/dev/null
STARTED_CONTAINER="${CONTAINER_NAME}"

wait_for_postgres

echo "Writing provider-backed Gemini + PGVector mini RAG eval artifact..."
cd "${ROOT_DIR}/src/research-service"
RAG_PGVECTOR_TEST_DATABASE_URL="${DATABASE_URL}" \
PYTHONPATH=. \
uv run python scripts/write_provider_mini_eval_artifact.py "${ARTIFACT_PATH}" >/dev/null

python - "${ARTIFACT_PATH}" <<'PY'
import json
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as artifact_file:
    artifact = json.load(artifact_file)

metrics = artifact["metrics"]
if artifact["stage"] != "stage_1_provider_mini_rag":
    raise SystemExit("unexpected provider mini eval stage")
if artifact["provider"] != "gemini":
    raise SystemExit("unexpected provider mini eval provider")
if artifact["vectorStore"] != "pgvector":
    raise SystemExit("unexpected provider mini eval vector store")
if artifact["caseCount"] != 5:
    raise SystemExit("provider mini eval must run exactly 5 cases")
if artifact["embeddingCalls"] <= 0:
    raise SystemExit("provider mini eval did not record embedding calls")
if metrics.get("emptyRetrievalRate") != 0.0:
    raise SystemExit("provider mini eval produced empty retrievals")
if metrics.get("badSectionLeakRate") != 0.0:
    raise SystemExit("provider mini eval leaked bad sections")
if metrics.get("expectedTermHitRate", 0.0) < 0.8:
    raise SystemExit("provider mini eval expected term hit rate is below threshold")
PY

echo "Provider-backed mini RAG eval verification passed: ${ARTIFACT_PATH}"
