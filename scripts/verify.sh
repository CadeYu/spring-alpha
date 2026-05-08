#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Checking required project files..."
required_files=(
  "AGENTS.md"
  "ARCHITECTURE.md"
  "VERIFY.md"
  "docs/spec.md"
  "docs/decisions.md"
  "docs/ui-guidelines.md"
  "planning/FEATURES.json"
  "planning/TASKS.md"
  "planning/PROGRESS.md"
  "planning/TOOLS.md"
  "scripts/verify.sh"
  "scripts/dev.sh"
  "scripts/e2e-local.sh"
  "scripts/verify-research-service-bridge.sh"
  "scripts/verify-pgvector-rag.sh"
  "scripts/verify-gemini-pgvector-rag.sh"
  "scripts/verify-pgvector-rag-eval.sh"
  "src/research-service/Dockerfile"
  ".github/workflows/ci.yml"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required file: $file" >&2
    exit 1
  fi
done

echo "Checking required directories..."
required_dirs=(
  "docs"
  "planning"
  "src"
  "tests"
  "scripts"
  ".github/workflows"
)

for dir in "${required_dirs[@]}"; do
  if [[ ! -d "$dir" ]]; then
    echo "Missing required directory: $dir" >&2
    exit 1
  fi
done

echo "Validating planning/FEATURES.json..."
node -e "JSON.parse(require('fs').readFileSync('planning/FEATURES.json', 'utf8'));"

echo "Checking shell script syntax..."
bash -n scripts/verify.sh
bash -n scripts/dev.sh
bash -n scripts/e2e-local.sh
bash -n scripts/verify-research-service-bridge.sh
bash -n scripts/verify-pgvector-rag.sh
bash -n scripts/verify-gemini-pgvector-rag.sh
bash -n scripts/verify-pgvector-rag-eval.sh

echo "Checking research task contract consistency..."
node - <<'NODE'
const fs = require('fs');

const frontendPath = 'frontend/src/lib/researchTasks.ts';
const backendPath = 'backend/src/main/java/com/springalpha/backend/financial/contract/ResearchTaskType.java';

const frontend = fs.readFileSync(frontendPath, 'utf8');
const backend = fs.readFileSync(backendPath, 'utf8');

const frontendListMatch = frontend.match(/RESEARCH_TASK_IDS\s*=\s*\[([\s\S]*?)\]\s*as const;/);
if (!frontendListMatch) {
  throw new Error(`Unable to find RESEARCH_TASK_IDS in ${frontendPath}`);
}

const frontendTasks = [...frontendListMatch[1].matchAll(/"([^"]+)"/g)].map((match) => match[1]);
const backendTasks = [...backend.matchAll(/\b[A-Z0-9_]+\("([^"]+)"\)/g)].map((match) => match[1]);

if (JSON.stringify(frontendTasks) !== JSON.stringify(backendTasks)) {
  throw new Error(
    `Research task contract mismatch: frontend=${JSON.stringify(frontendTasks)} backend=${JSON.stringify(backendTasks)}`,
  );
}

const frontendDefault = frontend.match(/DEFAULT_RESEARCH_TASK_ID[\s\S]*?=\s*"([^"]+)"/)?.[1];
const backendDefault = backend.match(/DEFAULT_REQUEST_VALUE\s*=\s*"([^"]+)"/)?.[1];

if (frontendDefault !== backendDefault) {
  throw new Error(`Research task default mismatch: frontend=${frontendDefault} backend=${backendDefault}`);
}
NODE

echo "Checking Research Service compose wiring..."
node - <<'NODE'
const fs = require('fs');

const compose = fs.readFileSync('docker-compose.yml', 'utf8');
const requiredSnippets = [
  'research-service:',
  'RESEARCH_SERVICE_BASE_URL=http://research-service:8090',
  'condition: service_healthy',
];

for (const snippet of requiredSnippets) {
  if (!compose.includes(snippet)) {
    throw new Error(`Missing docker-compose Research Service wiring: ${snippet}`);
  }
}
NODE

echo "Checking production analysis path documentation..."
node - <<'NODE'
const fs = require('fs');

const forbidden = [
  'RESEARCH_SERVICE_ENABLED',
  'Legacy Java analysis path remains available',
  'legacy Java fallback',
  'Java 主链路可以保留稳定 fallback',
  '旧 Java 分析链路保持可用',
  '旧分析链路回退',
];

const files = [
  'ARCHITECTURE.md',
  'VERIFY.md',
  'docs/decisions.md',
  'docs/spec.md',
  'docs/task-contract.md',
  'docs/dynamic-agent-loop.md',
  'backend/src/main/resources/application.yml',
];

for (const file of files) {
  const content = fs.readFileSync(file, 'utf8');
  for (const phrase of forbidden) {
    if (content.includes(phrase)) {
      throw new Error(`Production path docs still mention forbidden legacy phrase "${phrase}" in ${file}`);
    }
  }
}
NODE

echo "Project structure verification passed."
