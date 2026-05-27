from __future__ import annotations

import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from time import perf_counter, sleep
from uuid import uuid4

from app.evals.baseline import (
    RagProductionReadinessThresholds,
    RetrievalExperimentStrategy,
    assert_rag_production_readiness,
    build_stage1_provider_mini_eval_dataset,
    build_stage1_provider_mini_eval_summary,
    build_stage1_provider_sample_eval_dataset,
    build_stage1_provider_trend_record,
    run_live_pipeline_eval,
)
from app.rag.llamaindex_pipeline import (
    EmbeddingBackend,
    GeminiEmbeddingBackend,
    LlamaIndexRagPipeline,
    PgVectorStore,
    PgVectorStoreConfig,
)

GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_ESTIMATED_COST_PER_1K_CALLS = 0.0


class ProviderEvalSuite(StrEnum):
    MINI = "mini"
    SAMPLE = "sample"


class RetryingCountingEmbeddingBackend:
    def __init__(
        self,
        wrapped: EmbeddingBackend,
        *,
        max_attempts: int = 3,
        base_backoff_seconds: float = 1.0,
        sleep: Callable[[float], None] = sleep,
    ) -> None:
        self.wrapped = wrapped
        self.max_attempts = max_attempts
        self.base_backoff_seconds = base_backoff_seconds
        self.sleep = sleep
        self.calls = 0
        self.attempts = 0
        self.retries = 0

    def embed(self, text: str) -> dict[str, float]:
        self.calls += 1
        for attempt_index in range(self.max_attempts):
            self.attempts += 1
            try:
                return self.wrapped.embed(text)
            except Exception:
                if attempt_index == self.max_attempts - 1:
                    raise
                self.retries += 1
                self.sleep(self.base_backoff_seconds * (2**attempt_index))
        raise RuntimeError("unreachable embedding retry state")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: write_provider_mini_eval_artifact.py <target-json>", file=sys.stderr)
        return 2

    database_url = os.getenv("RAG_PGVECTOR_TEST_DATABASE_URL")
    api_key = os.getenv("GEMINI_API_KEY")
    if not database_url:
        print("RAG_PGVECTOR_TEST_DATABASE_URL is required", file=sys.stderr)
        return 2
    if not api_key:
        print("GEMINI_API_KEY is required", file=sys.stderr)
        return 2

    target_path = Path(sys.argv[1])
    embedding_backend = RetryingCountingEmbeddingBackend(
        GeminiEmbeddingBackend(api_key=api_key, model=GEMINI_EMBEDDING_MODEL)
    )

    def pipeline_factory(strategy: RetrievalExperimentStrategy) -> LlamaIndexRagPipeline:
        if strategy != RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL:
            raise ValueError("Provider mini eval only runs the hybrid retrieval strategy")
        table_name = f"rag_provider_mini_{uuid4().hex}"
        store = PgVectorStore(
            config=PgVectorStoreConfig(
                database_url=database_url,
                table_name=table_name,
                embedding_dimension=3072,
            ),
            embedding_backend=embedding_backend,
        )
        store.initialize_schema()
        return LlamaIndexRagPipeline(
            enable_hybrid_retrieval=True,
            embedding_backend=embedding_backend,
            vector_store=store,
        )

    started_at = perf_counter()
    suite = _suite_from_env()
    artifact = run_live_pipeline_eval(
        _dataset_for_suite(suite),
        strategy=RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL,
        pipeline_factory=pipeline_factory,
    )
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    assert_rag_production_readiness(
        artifact,
        thresholds=RagProductionReadinessThresholds(
            min_expected_section_hit_rate=1.0,
            min_expected_term_hit_rate=0.8,
            min_top_1_section_correctness=1.0,
            max_empty_retrieval_rate=0.0,
            max_bad_section_leak_rate=0.0,
            min_max_source_payload_bytes=1,
        ),
    )
    summary = build_stage1_provider_mini_eval_summary(
        artifact,
        provider="gemini",
        embedding_model=GEMINI_EMBEDDING_MODEL,
        vector_store="pgvector",
        embedding_calls=embedding_backend.calls,
        embedding_attempts=embedding_backend.attempts,
        estimated_cost_usd=_estimated_cost_usd(embedding_backend.calls),
        elapsed_ms=elapsed_ms,
    )
    if suite == ProviderEvalSuite.SAMPLE:
        summary = summary.model_copy(update={"stage": _stage_for_suite(suite)})
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(summary.model_dump_json(by_alias=True, indent=2), encoding="utf-8")
    trend_path = os.getenv("RAG_PROVIDER_EVAL_TREND_PATH")
    if trend_path:
        trend = build_stage1_provider_trend_record(
            summary,
            run_id=f"{summary.stage}:{uuid4().hex}",
            recorded_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        )
        _append_trend_record(Path(trend_path), trend.model_dump(mode="json", by_alias=True))
    print(target_path)
    return 0


def _suite_from_env() -> ProviderEvalSuite:
    return ProviderEvalSuite(os.getenv("RAG_PROVIDER_EVAL_SUITE", ProviderEvalSuite.MINI.value))


def _dataset_for_suite(suite: ProviderEvalSuite):
    if suite == ProviderEvalSuite.SAMPLE:
        return build_stage1_provider_sample_eval_dataset()
    return build_stage1_provider_mini_eval_dataset()


def _stage_for_suite(suite: ProviderEvalSuite) -> str:
    if suite == ProviderEvalSuite.SAMPLE:
        return "stage_1_provider_sample_rag"
    return "stage_1_provider_mini_rag"


def _append_trend_record(target_path: Path, payload: dict[str, object]) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    with target_path.open("a", encoding="utf-8") as trend_file:
        import json

        trend_file.write(json.dumps(payload, sort_keys=True))
        trend_file.write("\n")


def _estimated_cost_usd(embedding_calls: int) -> float:
    cost_per_1k_calls = float(
        os.getenv(
            "RAG_PROVIDER_MINI_EVAL_COST_PER_1K_CALLS",
            str(DEFAULT_ESTIMATED_COST_PER_1K_CALLS),
        )
    )
    return round((embedding_calls / 1000) * cost_per_1k_calls, 6)


if __name__ == "__main__":
    raise SystemExit(main())
