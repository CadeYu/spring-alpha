from __future__ import annotations

import pytest

from scripts.write_provider_mini_eval_artifact import RetryingCountingEmbeddingBackend


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


def _ignore_sleep(_: float) -> None:
    return None
