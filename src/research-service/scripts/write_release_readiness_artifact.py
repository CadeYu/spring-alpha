from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.evals.baseline import (
    RagDashboardArtifact,
    RagProviderMiniEvalSummary,
    build_release_readiness_artifact,
)


def main() -> int:
    if len(sys.argv) != 6:
        print(
            "Usage: write_release_readiness_artifact.py "
            "<rag-hard-json> <provider-rag-json> <agent-json> <compose-json> <target-json>",
            file=sys.stderr,
        )
        return 2

    rag_hard_path = Path(sys.argv[1])
    provider_rag_path = Path(sys.argv[2])
    agent_path = Path(sys.argv[3])
    compose_path = Path(sys.argv[4])
    target_path = Path(sys.argv[5])

    artifact = build_release_readiness_artifact(
        rag_hard=RagDashboardArtifact.model_validate(_read_json(rag_hard_path)),
        provider_rag=RagProviderMiniEvalSummary.model_validate(_read_json(provider_rag_path)),
        provider_agent=_read_json(agent_path),
        compose_full_e2e=_read_json(compose_path),
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        artifact.model_dump_json(by_alias=True, indent=2),
        encoding="utf-8",
    )
    print(target_path)
    return 0


def _read_json(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as artifact_file:
        payload = json.load(artifact_file)
    if not isinstance(payload, dict):
        raise ValueError(f"Artifact must be a JSON object: {path}")
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
