from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.deterministic_workflow import DeterministicAgentWorkflow
from app.agents.llm_gateway import (
    LlmTransport,
    OpenAiCompatibleLlmClient,
    default_model_for_provider,
)
from app.contracts.agent import AgentRequest, LlmProvider

STAGE = "stage_1_provider_live_planner"


@dataclass(frozen=True)
class ProviderLivePlannerConfig:
    provider: LlmProvider
    model: str
    api_key: str


def write_provider_live_planner_artifact(
    target_path: Path,
    *,
    config: ProviderLivePlannerConfig,
    transport: LlmTransport | None = None,
    strict: bool = True,
) -> Path:
    started_at = perf_counter()
    client = OpenAiCompatibleLlmClient(
        config.provider,
        config.api_key,
        base_url=_base_url_for_provider(config.provider),
        transport=transport,
    )
    workflow = DeterministicAgentWorkflow(llm_client=client)
    result = workflow.run(_agent_request(config))
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    payload = _artifact_payload(result, config=config, elapsed_ms=elapsed_ms)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(_json_dumps(payload), encoding="utf-8")
    assert_provider_live_planner_gate(payload, strict=strict)
    return target_path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: write_provider_live_planner_artifact.py <target-json>", file=sys.stderr)
        return 2

    config = _config_from_env()
    target_path = Path(sys.argv[1])
    written_path = write_provider_live_planner_artifact(target_path, config=config)
    print(written_path)
    return 0


def _config_from_env() -> ProviderLivePlannerConfig:
    provider = _provider_from_env()
    api_key = _api_key_for_provider(provider)
    model = os.getenv("PROVIDER_LIVE_PLANNER_MODEL") or default_model_for_provider(provider)
    return ProviderLivePlannerConfig(provider=provider, model=model, api_key=api_key)


def _provider_from_env() -> LlmProvider:
    raw_provider = os.getenv("PROVIDER") or os.getenv("PROVIDER_LIVE_PLANNER_PROVIDER")
    if raw_provider:
        return LlmProvider(raw_provider.strip().lower())
    if os.getenv("SILICONFLOW_API_KEY"):
        return LlmProvider.SILICONFLOW
    if os.getenv("GEMINI_API_KEY"):
        return LlmProvider.GEMINI
    if os.getenv("OPENAI_API_KEY"):
        return LlmProvider.OPENAI
    raise SystemExit(
        "Set PROVIDER plus a matching API key, or provide SILICONFLOW_API_KEY, "
        "GEMINI_API_KEY, or OPENAI_API_KEY."
    )


def _api_key_for_provider(provider: LlmProvider) -> str:
    env_names = {
        LlmProvider.SILICONFLOW: "SILICONFLOW_API_KEY",
        LlmProvider.GEMINI: "GEMINI_API_KEY",
        LlmProvider.OPENAI: "OPENAI_API_KEY",
    }
    api_key = os.getenv(env_names[provider])
    if not api_key:
        raise SystemExit(f"{env_names[provider]} is required for provider live planner smoke.")
    return api_key


def _base_url_for_provider(provider: LlmProvider) -> str:
    base_urls = {
        LlmProvider.SILICONFLOW: "https://api.siliconflow.cn/v1",
        LlmProvider.OPENAI: "https://api.openai.com/v1",
        LlmProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta/openai",
    }
    return base_urls[provider]


def _agent_request(config: ProviderLivePlannerConfig) -> AgentRequest:
    return AgentRequest(
        run_id="provider_live_planner_smoke",
        ticker="AAPL",
        task_type="latest_earnings_readout",
        language="en",
        llm_provider=config.provider,
        llm_model=config.model,
        llm_api_key=config.api_key,
    )


def _artifact_payload(
    result: object,
    *,
    config: ProviderLivePlannerConfig,
    elapsed_ms: int,
) -> dict[str, object]:
    result_payload = result.model_dump(mode="json")
    events = result_payload["events"]
    planner_events = [event for event in events if event.get("planner_context") is not None]
    fallback_events = [
        event
        for event in events
        if event["summary"].startswith("Planner decision was invalid; used deterministic fallback")
    ]
    provider_decision_events = [
        event
        for event in events
        if event.get("phase") == "build_evidence_plan"
        and event.get("tool_name") is not None
        and not str(event["summary"]).startswith("Plan next step: Deterministic fallback:")
    ]
    tool_names = sorted(
        {event["tool_name"] for event in events if event.get("tool_name") is not None}
    )
    final_report = result_payload.get("final_report") or {}
    task_sections = final_report.get("task_sections") or {}
    return {
        "stage": STAGE,
        "provider": config.provider.value,
        "model": config.model,
        "status": result_payload["status"],
        "eventCount": len(events),
        "plannerEventCount": len(planner_events),
        "toolNames": tool_names,
        "fallbackCount": len(fallback_events),
        "providerDecisionCount": len(provider_decision_events),
        "hasPlannerContext": bool(planner_events),
        "stopReason": _stop_reason(events),
        "elapsedMs": elapsed_ms,
        "finalReportTaskType": task_sections.get("task_type"),
        "degradedReasons": result_payload.get("degraded_reasons", []),
        "events": events,
    }


def _stop_reason(events: list[dict[str, object]]) -> str:
    if not events:
        return "no_events"
    last_summary = str(events[-1].get("summary", ""))
    if last_summary.startswith("Planner finalized:"):
        return "planner_finalize"
    if last_summary.startswith("Coverage is sufficient;"):
        return "coverage_stop"
    if last_summary.startswith("Planner step budget exhausted"):
        return "step_budget_exhausted"
    if last_summary.startswith("Tool budget exhausted"):
        return "tool_budget_exhausted"
    if last_summary.startswith("Planner decision was invalid"):
        return "planner_fallback"
    return "completed"


def assert_provider_live_planner_gate(
    payload: dict[str, object],
    *,
    strict: bool = False,
) -> None:
    if payload["stage"] != STAGE:
        raise RuntimeError("unexpected provider live planner stage")
    if int(payload["eventCount"]) <= 0:
        raise RuntimeError("provider live planner returned no events")
    if int(payload["plannerEventCount"]) <= 0:
        raise RuntimeError("provider live planner returned no planner events")
    if payload["hasPlannerContext"] is not True:
        raise RuntimeError("provider live planner did not record planner context")
    if payload["finalReportTaskType"] != "latest_earnings_readout":
        raise RuntimeError("provider live planner did not return latest earnings task sections")
    if not strict:
        return
    if int(payload.get("providerDecisionCount", 0)) <= 0:
        raise RuntimeError(
            "provider live planner must accept at least one provider planner decision"
        )
    if payload["stopReason"] not in {"planner_finalize", "coverage_stop"}:
        raise RuntimeError("provider live planner must stop via planner finalize or coverage stop")
    tool_names = set(payload["toolNames"])
    if not (tool_names & {"search_filing_sections", "search_metric_evidence"}):
        raise RuntimeError(
            "provider live planner must execute at least one evidence retrieval tool"
        )


def _json_dumps(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
