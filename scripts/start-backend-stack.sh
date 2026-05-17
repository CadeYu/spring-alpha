#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "start-backend-stack.sh is the local stack compatibility entrypoint."
echo "Use start-backend-stack-online.sh for Supabase + Qdrant."
echo

exec "${SCRIPT_DIR}/start-backend-stack-local.sh" "$@"
