from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

from app.evals.baseline import RetrievalExperimentStrategy, write_stage1_hard_dashboard_artifact
from app.rag.llamaindex_pipeline import (
    DeterministicFinancialEmbeddingBackend,
    LlamaIndexRagPipeline,
    PgVectorStore,
    PgVectorStoreConfig,
)


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: write_pgvector_eval_artifact.py <target-json>", file=sys.stderr)
        return 2

    database_url = os.getenv("RAG_PGVECTOR_TEST_DATABASE_URL")
    if not database_url:
        print("RAG_PGVECTOR_TEST_DATABASE_URL is required", file=sys.stderr)
        return 2

    target_path = Path(sys.argv[1])
    embedding_backend = DeterministicFinancialEmbeddingBackend()

    def pipeline_factory(strategy: RetrievalExperimentStrategy) -> LlamaIndexRagPipeline:
        table_name = f"rag_eval_{_slug(strategy.value)}_{uuid4().hex}"
        store = PgVectorStore(
            config=PgVectorStoreConfig(
                database_url=database_url,
                table_name=table_name,
                embedding_dimension=64,
            ),
            embedding_backend=embedding_backend,
        )
        store.initialize_schema()
        return LlamaIndexRagPipeline(
            enable_section_filter=strategy != RetrievalExperimentStrategy.NO_SECTION_FILTER,
            enable_query_expansion=strategy != RetrievalExperimentStrategy.NO_QUERY_EXPANSION,
            enable_hybrid_retrieval=strategy
            == RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL,
            embedding_backend=embedding_backend,
            vector_store=store,
        )

    write_stage1_hard_dashboard_artifact(target_path, pipeline_factory=pipeline_factory)
    print(target_path)
    return 0


def _slug(value: str) -> str:
    return value.replace("-", "_").replace(" ", "_")


if __name__ == "__main__":
    raise SystemExit(main())
