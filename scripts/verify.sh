#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Checking required project files..."
required_files=(
  "AGENTS.md"
  "docs/architecture.md"
  "docs/verification.md"
  "docs/testing.md"
  "docs/api/postman_collection.json"
  "docs/spec.md"
  "docs/decisions.md"
  "docs/ui-guidelines.md"
  "docs/task-contract.md"
  "docs/dynamic-agent-loop.md"
  "planning/FEATURES.json"
  "planning/TASKS.md"
  "planning/PROGRESS.md"
  "planning/TOOLS.md"
  "scripts/verify.sh"
  "scripts/dev.sh"
  "scripts/e2e-local.sh"
  "scripts/verify-research-service-bridge.sh"
  "scripts/verify-compose-full-e2e.sh"
  "scripts/verify-pgvector-rag.sh"
  "scripts/verify-gemini-pgvector-rag.sh"
  "scripts/verify-pgvector-rag-eval.sh"
  "scripts/verify-provider-mini-rag-eval.sh"
  "backend/research-service/Dockerfile"
  ".github/workflows/ci.yml"
  ".github/workflows/deploy-vultr.yml"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing required file: $file" >&2
    exit 1
  fi
done

echo "Checking root directory hygiene..."
forbidden_root_files=(
  "ARCHITECTURE.md"
  "VERIFY.md"
  "testing.md"
  "postman_collection.json"
  "metalogo.jpeg"
  "openailogo.png"
  "run_checks.sh"
  "start_backend.example.sh"
  "test.html"
  "verify_backend.sh"
)

for file in "${forbidden_root_files[@]}"; do
  if [[ -e "$file" ]] && git ls-files --error-unmatch "$file" >/dev/null 2>&1; then
    echo "Tracked root file should be moved or removed: $file" >&2
    exit 1
  fi
done

echo "Checking required directories..."
required_dirs=(
  "docs"
  "docs/api"
  "planning"
  "backend/research-service"
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
bash -n scripts/verify-compose-full-e2e.sh
bash -n scripts/verify-pgvector-rag.sh
bash -n scripts/verify-gemini-pgvector-rag.sh
bash -n scripts/verify-pgvector-rag-eval.sh
bash -n scripts/verify-provider-mini-rag-eval.sh

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
  'pgvector:',
  'pgvector/pgvector:pg16',
  'research-service:',
  'RAG_VECTOR_STORE_PROVIDER=${RAG_VECTOR_STORE_PROVIDER:-pgvector}',
  'RAG_VECTOR_DATABASE_URL=postgresql://',
  'RAG_VECTOR_INITIALIZE_SCHEMA=${RAG_VECTOR_INITIALIZE_SCHEMA:-true}',
  'RESEARCH_SERVICE_BASE_URL=http://research-service:8090',
  'condition: service_healthy',
];

for (const snippet of requiredSnippets) {
  if (!compose.includes(snippet)) {
    throw new Error(`Missing docker-compose Research Service wiring: ${snippet}`);
  }
}
NODE

echo "Checking Vultr deploy workflow contract..."
node - <<'NODE'
const fs = require('fs');

const deployWorkflow = fs.readFileSync('.github/workflows/deploy-vultr.yml', 'utf8');
const requiredSnippets = [
  'workflow_run:',
  'workflow_dispatch:',
  'workflows: ["CI"]',
  "github.event.workflow_run.conclusion == 'success'",
  'Check deploy secrets',
  "Missing required deployment secrets:",
  "VULTR_PORT: ${{ secrets.VULTR_PORT || '2222' }}",
  'appleboy/ssh-action@v1.0.3',
  'docker compose -f deploy/vultr/docker-compose.yml up -d --build --remove-orphans',
  'curl -fsS http://127.0.0.1/health >/dev/null',
  'curl -fsS http://127.0.0.1/api/sec/models >/dev/null',
];

for (const snippet of requiredSnippets) {
  if (!deployWorkflow.includes(snippet)) {
    throw new Error(`Missing Vultr deploy workflow snippet: ${snippet}`);
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
  'docs/architecture.md',
  'docs/verification.md',
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

echo "Checking Python RAG production readiness gates..."
node - <<'NODE'
const fs = require('fs');

const evalScript = fs.readFileSync('backend/research-service/scripts/write_pgvector_eval_artifact.py', 'utf8');
const releaseScript = fs.readFileSync('backend/research-service/scripts/write_release_readiness_artifact.py', 'utf8');
const evalModule = fs.readFileSync('backend/research-service/app/evals/baseline.py', 'utf8');
const readinessLib = fs.readFileSync('frontend/src/lib/releaseReadiness.ts', 'utf8');
const readinessComponent = fs.readFileSync('frontend/src/components/app/release-readiness-checklist.tsx', 'utf8');
const readinessFixture = fs.readFileSync('frontend/src/data/release-readiness.json', 'utf8');
const verifyDocs = fs.readFileSync('docs/verification.md', 'utf8');

const requiredSnippets = [
  [evalScript, 'assert_rag_production_readiness'],
  [evalScript, 'build_stage1_hard_eval_suite'],
  [evalModule, 'class RagProductionReadinessThresholds'],
  [evalModule, 'def assert_rag_production_readiness'],
  [evalModule, 'build_stage1_provider_mini_eval_dataset'],
  [evalModule, 'build_stage1_provider_sample_eval_dataset'],
  [evalModule, 'build_stage1_provider_trend_record'],
  [evalModule, 'build_release_readiness_artifact'],
  [releaseScript, 'build_release_readiness_artifact'],
  [readinessLib, 'RELEASE_READINESS_ARTIFACT'],
  [readinessComponent, 'Release Readiness'],
  [readinessFixture, 'provider_rag_sample_gate'],
  [verifyDocs, './scripts/verify-compose-full-e2e.sh'],
  [verifyDocs, '../../scripts/verify-pgvector-rag-eval.sh'],
  [verifyDocs, './scripts/verify-provider-mini-rag-eval.sh'],
  [verifyDocs, 'RAG_PROVIDER_EVAL_SUITE=sample'],
  [verifyDocs, 'write_release_readiness_artifact.py'],
];

for (const [content, snippet] of requiredSnippets) {
  if (!content.includes(snippet)) {
    throw new Error(`Missing Python RAG readiness gate snippet: ${snippet}`);
  }
}
NODE

echo "Checking tool-calling agent production telemetry contract..."
node - <<'NODE'
const fs = require('fs');

const agentContract = fs.readFileSync('backend/research-service/app/contracts/agent.py', 'utf8');
const workflow = fs.readFileSync('backend/research-service/app/agents/research_workflow.py', 'utf8');
const toolGraph = fs.readFileSync('backend/research-service/app/agents/tool_calling_graph.py', 'utf8');
const toolCallingScript = fs.readFileSync('backend/research-service/scripts/write_provider_tool_calling_agent_artifact.py', 'utf8');
const toolE2EGate = fs.readFileSync('scripts/verify-provider-tool-e2e.sh', 'utf8');
const reportSynthesis = fs.readFileSync('backend/research-service/app/agents/report_synthesizer.py', 'utf8');
const reportSynthesisScript = fs.readFileSync('backend/research-service/scripts/write_provider_report_synthesis_artifact.py', 'utf8');
const reportSynthesisGate = fs.readFileSync('scripts/verify-provider-report-synthesis.sh', 'utf8');
const verifyDocs = fs.readFileSync('docs/verification.md', 'utf8');

const requiredSnippets = [
  [agentContract, 'class EvidenceMemory'],
  [workflow, 'ResearchAgentWorkflow'],
  [toolGraph, 'StateGraph'],
  [toolGraph, 'planned_tool_calls'],
  [toolCallingScript, 'stage_1_provider_tool_calling_agent'],
  [toolCallingScript, 'OpenAiCompatibleLlmClient'],
  [toolE2EGate, 'write_provider_tool_e2e_artifact.py'],
  [reportSynthesis, 'synthesize_latest_earnings_report'],
  [reportSynthesis, 'def _sanitize_source_ids'],
  [reportSynthesis, 'CitationStatus.UNVERIFIED'],
  [reportSynthesisScript, 'stage_1_provider_report_synthesis'],
  [reportSynthesisGate, 'write_provider_report_synthesis_artifact.py'],
  [verifyDocs, './scripts/verify-provider-tool-e2e.sh'],
  [verifyDocs, './scripts/verify-provider-report-synthesis.sh'],
];

for (const [content, snippet] of requiredSnippets) {
  if (!content.includes(snippet)) {
    throw new Error(`Missing tool-calling agent telemetry snippet: ${snippet}`);
  }
}
NODE

echo "Project structure verification passed."
