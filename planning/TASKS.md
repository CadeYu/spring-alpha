# Spring Alpha MVP Tasks

## 目标

本文档是后续实现任务的人工 checklist。机器可读 feature 状态以 `planning/FEATURES.json` 为准。

## Phase 0: Project Structure

- [x] Create architecture, verification, and progress documents.
- [x] Move MVP feature checklist into `planning/`.
- [x] Add docs for decisions and UI guidelines.
- [x] Add scripts for verification and local development guidance.

## Phase 1: Contracts

- [x] Define task type contract.
- [x] Define agent request contract.
- [x] Define agent event contract.
- [x] Define retrieval record contract.
- [x] Define citation status contract.
- [x] Define report extension contract.

## Phase 2: Agent Path

- [x] Route backend analysis through the Python Agent path.
- [ ] Add frontend feature flag for task card entry.
- [ ] Add degraded state display contract.

## Phase 3: Agent Skeleton

- [x] Create Python Research Service skeleton.
- [x] Add FastAPI health endpoint.
- [x] Add LangGraph placeholder state graph.
- [ ] Add structured event stream contract.

## Phase 4: RAG Baseline

- [x] Build Stage 0 eval dataset.
- [x] Record current baseline retrieval behavior.
- [x] Store eval artifact format.

## Phase 5: MVP UI

- [ ] Add task cards.
- [ ] Add agent progress area.
- [ ] Add evidence trail display.
- [ ] Preserve existing dashboard behavior.

## Phase 6: Verification

- [ ] Wire `scripts/verify.sh` to full frontend/backend verification.
- [x] Add research task contract consistency check.
- [ ] Add Python verification after Research Service exists.
- [x] Add local E2E orchestration script.
- [ ] Add CI workflow coverage for MVP gates.
