# Spring Alpha Research Service

Spring Alpha 的 Python Research Service 负责 bounded Agent workflow、live
planner provider adapter，以及请求级 filing evidence 的 LlamaIndex RAG tool
execution。

当前生产主链路由 Spring Boot 获取最新 SEC filing 文本，并在调用 `/agent/runs`
时通过 `filings` 字段传给 Python。Python 会为本次请求构建
`LlamaIndexRagPipeline`，再把 `search_filing_sections` 和
`search_metric_evidence` 接到 live RAG tool registry。没有传入 filing 时，服务仍可运行本地
deterministic workflow，便于 contract test 和降级验证。

本服务不直接抓取 SEC；SEC fetching 仍由 Spring Boot 的 `SecService` 负责。

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

Production RAG defaults are environment-driven. When `RAG_VECTOR_DATABASE_URL`
is present, the request pipeline uses PGVector unless
`RAG_VECTOR_STORE_PROVIDER` is explicitly set. When `GEMINI_API_KEY` is present,
the embedding backend defaults to Gemini unless `RAG_EMBEDDING_PROVIDER` is
explicitly set; otherwise deterministic local embeddings keep tests and local
smokes reproducible. Configure `RAG_VECTOR_TABLE_NAME`,
`RAG_EMBEDDING_DIMENSION`, and optionally `RAG_VECTOR_INITIALIZE_SCHEMA=true`
when running the service against a real database.

The readiness eval gate runs the hard RAG suite through real PGVector storage
and fails if the primary hybrid retrieval artifact violates expected section
hit rate, expected term hit rate, top-1 section correctness, empty retrieval,
bad section leak, or source payload thresholds. High-dimensional embeddings such
as Gemini's 3072 dimension output are stored without an HNSW index because
pgvector HNSW has a dimension limit; exact cosine ordering is used for the gated
smoke path.

The provider-backed mini gate runs five representative hard cases through real
Gemini embeddings and PGVector. It records retrieval quality, elapsed time,
embedding call count, and estimated cost in a JSON artifact. It is intentionally
manual/optional so provider cost and availability do not affect default CI.
