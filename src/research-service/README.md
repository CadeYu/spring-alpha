# Spring Alpha Research Service

Spring Alpha 的 Python Research Service 负责 LangGraph tool-calling Agent
workflow、provider-backed final synthesis，以及请求级 filing evidence 的
LlamaIndex RAG tool execution。

当前生产主链路由 Spring Boot 获取最新 SEC filing 文本，并在调用 `/agent/runs`
时通过 `filings` 字段传给 Python。Python 会为本次请求构建
`LlamaIndexRagPipeline`，再把 `search_filing_sections`、`search_metric_evidence`
和 domain tools 接到 agent tool runtime。没有传入 filing 时，服务仍会返回透明的
degraded/error state，而不是生成旧 deterministic report fallback。

本服务不直接抓取 SEC；SEC fetching 仍由 Spring Boot 的 `SecService` 负责。

## Current Agent Production Path

Spring Boot 是产品 API 和 SEC filing fetch boundary；Python Research Service 是
分析、RAG、tool execution 和报告 synthesis 的生产主路径。Spring Boot 不再提供 Java
report-generation fallback。如果 Research Service 不可用，后端应返回明确的
unavailable/degraded 错误，而不是偷偷生成旧报告。

当前三个 MVP task 都支持 typed final synthesis：

| Task | Tool path | Final synthesis |
| --- | --- | --- |
| `latest_earnings_readout` | SEC companyfacts, filing section RAG, metric evidence | LLM typed latest earnings report |
| `business_driver_deep_dive` | filing section RAG, evidence-bound business signals | LLM typed business driver report |
| `cash_flow_capital_allocation` | SEC companyfacts, filing section RAG, metric evidence | LLM typed cash-quality and capital allocation report |

所有 provider synthesis 都必须通过 source id 白名单校验。LLM 只能引用 Agent
evidence memory 中已有的 `source_id`，不能发明 citation。

本地运行：

```bash
uv run uvicorn app.main:app --reload --host 127.0.0.1 --port 8090
```

Smoke check:

```bash
curl http://127.0.0.1:8090/health
```

PGVector RAG smoke:

```bash
../../scripts/verify-pgvector-rag.sh
```

Live Gemini embeddings with PGVector smoke:

```bash
GEMINI_API_KEY="$GEMINI_API_KEY" ../../scripts/verify-gemini-pgvector-rag.sh
```

PGVector-backed RAG production readiness eval gate:

```bash
../../scripts/verify-pgvector-rag-eval.sh
```

Manual provider-backed mini eval gate:

```bash
GEMINI_API_KEY="$GEMINI_API_KEY" ../../scripts/verify-provider-mini-rag-eval.sh
```

Provider tool E2E live gate:

```bash
PROVIDER=siliconflow SILICONFLOW_API_KEY="$SILICONFLOW_API_KEY" \
../../scripts/verify-provider-tool-e2e.sh

PROVIDER_TOOL_E2E_TASK_TYPE=business_driver_deep_dive \
PROVIDER=siliconflow SILICONFLOW_API_KEY="$SILICONFLOW_API_KEY" \
../../scripts/verify-provider-tool-e2e.sh

PROVIDER_TOOL_E2E_TASK_TYPE=cash_flow_capital_allocation \
PROVIDER=siliconflow SILICONFLOW_API_KEY="$SILICONFLOW_API_KEY" \
../../scripts/verify-provider-tool-e2e.sh
```

The live provider tool gate validates task-specific production paths:

- latest earnings: SEC facts + RAG source refs + LLM synthesis.
- business driver: RAG source refs + business signals + LLM synthesis.
- cash flow: SEC facts + RAG source refs + metric evidence + LLM synthesis.

It is intentionally manual because SEC and provider availability can fluctuate.
Provider keys must come from runtime environment variables only.

Production RAG defaults are environment-driven. When `RAG_VECTOR_STORE_PROVIDER`
is `qdrant`, the request pipeline stores SEC chunks in Qdrant Cloud using
`QDRANT_URL`, `QDRANT_API_KEY`, and `QDRANT_COLLECTION`. When
`RAG_VECTOR_DATABASE_URL` is present, the request pipeline uses PGVector unless
`RAG_VECTOR_STORE_PROVIDER` is explicitly set. When `GEMINI_API_KEY` is present,
the embedding backend defaults to Gemini unless `RAG_EMBEDDING_PROVIDER` is
explicitly set; otherwise deterministic local embeddings keep tests and local
smokes reproducible. Configure `RAG_EMBEDDING_DIMENSION=3072` for Gemini
embeddings. For PGVector, configure `RAG_VECTOR_TABLE_NAME` and optionally
`RAG_VECTOR_INITIALIZE_SCHEMA=true` when running the service against a real
database.

Render deployments should keep vector-store secrets in service environment
variables only:

```bash
RAG_VECTOR_STORE_PROVIDER=qdrant
QDRANT_URL=https://your-cluster.region.aws.cloud.qdrant.io
QDRANT_API_KEY=your-qdrant-api-key
QDRANT_COLLECTION=spring_alpha_rag_chunks
RAG_EMBEDDING_PROVIDER=gemini
RAG_EMBEDDING_DIMENSION=3072
```

The readiness eval gate runs the hard RAG suite through real PGVector storage
and fails if the primary hybrid retrieval artifact violates expected section
hit rate, expected term hit rate, top-1 section correctness, empty retrieval,
bad section leak, or source payload thresholds. High-dimensional embeddings such
as Gemini's 3072 dimension output are stored without an HNSW index because
pgvector HNSW has a dimension limit; exact cosine ordering is used for the gated
smoke path.

The provider-backed mini gate runs 10-15 representative hard cases through real
Gemini embeddings and PGVector. It records retrieval quality, elapsed time,
embedding call count, and estimated cost in a JSON artifact. It is intentionally
manual/optional so provider cost and availability do not affect default CI.

The release readiness artifact writer combines the latest RAG hard dashboard,
provider RAG summary, provider tool-calling agent smoke, and compose full E2E
summary into one frontend-safe checklist fixture:

```bash
uv run python scripts/write_release_readiness_artifact.py \
  ../../frontend/src/data/rag-eval/stage1-hard.json \
  /path/to/provider-rag-summary.json \
  /path/to/provider-tool-calling-agent.json \
  /path/to/compose-full-e2e.json \
  ../../frontend/src/data/release-readiness.json
```
