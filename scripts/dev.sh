#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cat <<EOF
Spring Alpha local development commands

Backend:
  cd "$ROOT_DIR/backend"
  mvn spring-boot:run

Frontend:
  cd "$ROOT_DIR/frontend"
  npm run dev

Research Service:
  cd "$ROOT_DIR/src/research-service"
  uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8090

Verification:
  cd "$ROOT_DIR"
  ./scripts/verify.sh

Mocked E2E:
  cd "$ROOT_DIR"
  ./scripts/e2e-local.sh mocked

Cross-service E2E prep:
  cd "$ROOT_DIR"
  ./scripts/e2e-local.sh --print
  ./scripts/e2e-local.sh services
EOF
