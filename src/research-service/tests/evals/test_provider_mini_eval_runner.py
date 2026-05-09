from __future__ import annotations

import json

import pytest

from scripts.write_provider_mini_eval_artifact import (
    ProviderEvalSuite,
    RetryingCountingEmbeddingBackend,
    _append_trend_record,
    _dataset_for_suite,
    _stage_for_suite,
)


class FlakyEmbeddingBackend:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self.attempts = 0

    def embed(self, text: str) -> dict[str, float]:
        self.attempts += 1
        if self.attempts <= self.failures_before_success:
            raise TimeoutError("provider handshake timed out")
        return {text: 1.0}


def test_retrying_counting_embedding_backend_retries_transient_provider_failures() -> None:
    backend = FlakyEmbeddingBackend(failures_before_success=1)
    sleeper_calls: list[float] = []
    retrying_backend = RetryingCountingEmbeddingBackend(
        backend,
        max_attempts=3,
        base_backoff_seconds=0.25,
        sleep=sleeper_calls.append,
    )

    embedding = retrying_backend.embed("gross margin")

    assert embedding == {"gross margin": 1.0}
    assert retrying_backend.calls == 1
    assert retrying_backend.attempts == 2
    assert retrying_backend.retries == 1
    assert sleeper_calls == [0.25]


def test_retrying_counting_embedding_backend_raises_after_attempt_budget() -> None:
    backend = FlakyEmbeddingBackend(failures_before_success=3)
    retrying_backend = RetryingCountingEmbeddingBackend(
        backend,
        max_attempts=2,
        base_backoff_seconds=0.25,
        sleep=_ignore_sleep,
    )

    with pytest.raises(TimeoutError, match="provider handshake timed out"):
        retrying_backend.embed("free cash flow")

    assert retrying_backend.calls == 1
    assert retrying_backend.attempts == 2
    assert retrying_backend.retries == 1


def test_provider_eval_runner_selects_mini_and_sample_datasets() -> None:
    mini_dataset = _dataset_for_suite(ProviderEvalSuite.MINI)
    sample_dataset = _dataset_for_suite(ProviderEvalSuite.SAMPLE)

    assert _stage_for_suite(ProviderEvalSuite.MINI) == "stage_1_provider_mini_rag"
    assert _stage_for_suite(ProviderEvalSuite.SAMPLE) == "stage_1_provider_sample_rag"
    assert mini_dataset.name == "stage1_provider_mini_rag_eval"
    assert sample_dataset.name == "stage1_provider_sample_rag_eval"
    assert 10 <= len(mini_dataset.cases) <= 15
    assert 18 <= len(sample_dataset.cases) <= 24


def test_provider_eval_runner_appends_trend_jsonl(tmp_path) -> None:
    trend_path = tmp_path / "rag-provider-trends.jsonl"
    trend_payload = {
        "schemaVersion": "0.1.0",
        "stage": "stage_1_provider_sample_rag",
        "runId": "run-001",
        "recordedAt": "2026-05-09T00:00:00Z",
        "metrics": {"emptyRetrievalRate": 0.0},
    }

    _append_trend_record(trend_path, trend_payload)
    _append_trend_record(trend_path, {**trend_payload, "runId": "run-002"})

    lines = trend_path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["runId"] for line in lines] == ["run-001", "run-002"]


def _ignore_sleep(_: float) -> None:
    return None
