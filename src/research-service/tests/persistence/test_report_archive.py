import json
from pathlib import Path

from pytest import MonkeyPatch

from app.agents.bounded_workflow import BoundedAgentWorkflow
from app.contracts.agent import (
    AgentEvent,
    AgentPhase,
    AgentRequest,
    AgentRunStatus,
    BoundedAgentResult,
    ToolStatus,
)
from app.contracts.archive import ReportArchiveArtifact
from app.contracts.research_task import ResearchTaskType
from app.persistence.report_archive import JsonReportArchiveWriter


def test_archive_artifact_captures_agent_run_for_handoff() -> None:
    workflow = BoundedAgentWorkflow()

    result = workflow.run(
        AgentRequest(
            run_id="run_archive_001",
            ticker="tsla",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        )
    )

    artifact = ReportArchiveArtifact.from_agent_result(result)

    assert artifact.run_id == "run_archive_001"
    assert artifact.ticker == "TSLA"
    assert artifact.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE
    assert artifact.final_report is not None
    assert artifact.agent_events
    assert artifact.retrieval_records
    assert artifact.citation_validation.status == "not_run"
    assert artifact.eval_artifacts == []


def test_json_report_archive_writer_persists_stable_artifact(tmp_path: Path) -> None:
    workflow = BoundedAgentWorkflow()
    result = workflow.run(
        AgentRequest(
            run_id="run_archive_002",
            ticker="AAPL",
            task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
        )
    )
    artifact = ReportArchiveArtifact.from_agent_result(result)
    writer = JsonReportArchiveWriter(base_dir=tmp_path)

    path = writer.write(artifact)

    assert path == tmp_path / "run_archive_002.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run_archive_002"
    assert payload["ticker"] == "AAPL"
    assert payload["task_type"] == "cash_flow_capital_allocation"
    assert payload["agent_events"]
    assert payload["retrieval_records"]
    assert payload["final_report"]["run_id"] == "run_archive_002"


def test_archive_artifact_preserves_review_data_without_final_report() -> None:
    result = _agent_result_without_final_report()
    retrieval_records = [
        {
            "status": "ok",
            "data": {
                "retrieved_nodes": [
                    {
                        "node_id": "run_archive_003:node:1",
                        "section": "MD&A",
                        "snippet": "A source snippet.",
                    }
                ]
            },
        }
    ]

    artifact = ReportArchiveArtifact.from_agent_result(
        result,
        ticker="msft",
        retrieval_records=retrieval_records,
    )

    assert artifact.ticker == "MSFT"
    assert artifact.final_report is None
    assert artifact.retrieval_records == retrieval_records


def test_json_report_archive_writer_preserves_validation_and_eval_artifacts(
    tmp_path: Path,
) -> None:
    result = _agent_result_without_final_report()
    artifact = ReportArchiveArtifact.from_agent_result(
        result,
        ticker="MSFT",
        citation_validation={"status": "partial", "checked_claims": 2},
        eval_artifacts=[{"name": "baseline_smoke", "metric": "citation_coverage", "value": 0.5}],
    )
    writer = JsonReportArchiveWriter(base_dir=tmp_path)

    path = writer.write(artifact)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["citation_validation"] == {"status": "partial", "checked_claims": 2}
    assert payload["eval_artifacts"] == [
        {"name": "baseline_smoke", "metric": "citation_coverage", "value": 0.5}
    ]


def test_json_report_archive_writer_uses_atomic_replace(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    result = _agent_result_without_final_report()
    artifact = ReportArchiveArtifact.from_agent_result(result, ticker="MSFT")
    writer = JsonReportArchiveWriter(base_dir=tmp_path)
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = Path.replace

    def spy_replace(self: Path, target: Path) -> Path:
        replace_calls.append((self, target))
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy_replace)

    path = writer.write(artifact)

    assert path == tmp_path / "run_archive_003.json"
    assert replace_calls == [(tmp_path / "run_archive_003.json.tmp", path)]
    assert not (tmp_path / "run_archive_003.json.tmp").exists()


def _agent_result_without_final_report() -> BoundedAgentResult:
    return BoundedAgentResult(
        run_id="run_archive_003",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        status=AgentRunStatus.DEGRADED,
        events=[
            AgentEvent(
                run_id="run_archive_003",
                task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
                phase=AgentPhase.RETRIEVE_EVIDENCE,
                status=ToolStatus.OK,
                summary="Retrieved evidence records.",
                tool_name="retrieve_evidence",
            )
        ],
        degraded_reasons=["finalize_report failed: provider unavailable"],
        final_report=None,
    )
