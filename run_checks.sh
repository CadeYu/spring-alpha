#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "== Backend tests =="
cd "$ROOT_DIR/backend"
mvn -Dtest=SecControllerTest,SecServiceTest,FinancialAnalysisServiceTest,BaseAiStrategyTest,AnalysisReportValidatorTest,FmpFinancialDataServiceTest test

echo "== Frontend lint =="
cd "$ROOT_DIR/frontend"
npm run lint

echo "== Frontend typecheck =="
npx tsc --noEmit

echo "== Frontend unit/component tests =="
npm test

echo "== Frontend E2E smoke =="
npm run test:e2e
