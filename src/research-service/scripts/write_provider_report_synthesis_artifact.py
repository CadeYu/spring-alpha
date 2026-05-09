from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.deterministic_workflow import DeterministicAgentWorkflow
from app.agents.llm_gateway import (
    LlmRequest,
    LlmResponse,
    LlmTransport,
    OpenAiCompatibleLlmClient,
    default_model_for_provider,
)
from app.contracts.agent import AgentRequest, LlmProvider
from app.contracts.research_task import ResearchTaskType

STAGE = "stage_1_provider_report_synthesis"


@dataclass(frozen=True)
class ProviderReportSynthesisConfig:
    provider: LlmProvider
    model: str
    api_key: str
    task_type: ResearchTaskType = ResearchTaskType.LATEST_EARNINGS_READOUT


def write_provider_report_synthesis_artifact(
    target_path: Path,
    *,
    config: ProviderReportSynthesisConfig,
    transport: LlmTransport | None = None,
    strict: bool = True,
) -> Path:
    started_at = perf_counter()
    synthesis_client = OpenAiCompatibleLlmClient(
        config.provider,
        config.api_key,
        base_url=_base_url_for_provider(config.provider),
        transport=transport,
    )
    workflow = DeterministicAgentWorkflow(
        llm_client=_deterministic_planner_client(config.provider, config.task_type),
        report_synthesis_client=synthesis_client,
        enable_report_synthesis=True,
    )
    result = workflow.run(_agent_request(config))
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    payload = _artifact_payload(result, config=config, elapsed_ms=elapsed_ms)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(_json_dumps(payload), encoding="utf-8")
    assert_provider_report_synthesis_gate(payload, strict=strict)
    return target_path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: write_provider_report_synthesis_artifact.py <target-json>", file=sys.stderr)
        return 2

    written_path = write_provider_report_synthesis_artifact(
        Path(sys.argv[1]),
        config=_config_from_env(),
    )
    print(written_path)
    return 0


class _DeterministicPlannerClient:
    def __init__(self, provider: LlmProvider, task_type: ResearchTaskType) -> None:
        self.provider = provider
        self.task_type = task_type
        self._calls = 0

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        self._calls += 1
        if self._calls == 1:
            content = _first_tool_decision(self.task_type)
        else:
            content = {
                "decision": "finalize",
                "summary": "Evidence is ready for provider report synthesis.",
            }
        return LlmResponse(
            provider=request.provider,
            model=request.model,
            content=content,
        )


def _deterministic_planner_client(
    provider: LlmProvider,
    task_type: ResearchTaskType,
) -> _DeterministicPlannerClient:
    return _DeterministicPlannerClient(provider, task_type)


def _first_tool_decision(task_type: ResearchTaskType) -> dict[str, object]:
    if task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        return {
            "decision": "call_tool",
            "summary": "Search business driver evidence before provider report synthesis.",
            "tool_name": "search_filing_sections",
            "tool_input": {
                "sections": ["MD&A", "Business"],
                "query": "business drivers services demand segment product strategy",
            },
        }
    return {
        "decision": "call_tool",
        "summary": "Search evidence before provider report synthesis.",
        "tool_name": "search_filing_sections",
        "tool_input": {
            "sections": ["MD&A"],
            "query": "latest earnings revenue gross margin demand risk",
        },
    }


def _config_from_env() -> ProviderReportSynthesisConfig:
    provider = _provider_from_env()
    api_key = _api_key_for_provider(provider)
    model = os.getenv("PROVIDER_REPORT_SYNTHESIS_MODEL") or default_model_for_provider(provider)
    task_type = _task_type_from_env()
    return ProviderReportSynthesisConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        task_type=task_type,
    )


def _task_type_from_env() -> ResearchTaskType:
    raw_task_type = os.getenv("PROVIDER_REPORT_SYNTHESIS_TASK_TYPE")
    if raw_task_type:
        return ResearchTaskType(raw_task_type.strip().lower())
    return ResearchTaskType.LATEST_EARNINGS_READOUT


def _provider_from_env() -> LlmProvider:
    raw_provider = os.getenv("PROVIDER") or os.getenv("PROVIDER_REPORT_SYNTHESIS_PROVIDER")
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
        raise SystemExit(f"{env_names[provider]} is required for provider synthesis smoke.")
    return api_key


def _base_url_for_provider(provider: LlmProvider) -> str:
    base_urls = {
        LlmProvider.SILICONFLOW: "https://api.siliconflow.cn/v1",
        LlmProvider.OPENAI: "https://api.openai.com/v1",
        LlmProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta/openai",
    }
    return base_urls[provider]


def _agent_request(config: ProviderReportSynthesisConfig) -> AgentRequest:
    return AgentRequest(
        run_id="provider_report_synthesis_smoke",
        ticker="AAPL",
        task_type=config.task_type,
        language="en",
        llm_provider=config.provider,
        llm_model=config.model,
        llm_api_key=config.api_key,
    )


def _artifact_payload(
    result: object,
    *,
    config: ProviderReportSynthesisConfig,
    elapsed_ms: int,
) -> dict[str, object]:
    result_payload = result.model_dump(mode="json")
    final_report = result_payload.get("final_report") or {}
    task_sections = final_report.get("task_sections") or {}
    sections = final_report.get("sections") or {}
    claims = final_report.get("claims") or []
    source_ids = sorted(
        {
            source_ref.get("source_id")
            for claim in claims
            for source_ref in claim.get("source_refs", [])
            if source_ref.get("source_id")
        }
    )
    headline = _headline_from_task_sections(task_sections)
    return {
        "stage": STAGE,
        "provider": config.provider.value,
        "model": config.model,
        "status": result_payload["status"],
        "elapsedMs": elapsed_ms,
        "synthesis": sections.get("synthesis"),
        "finalReportTaskType": task_sections.get("task_type"),
        "headline": headline,
        "claimCount": len(claims),
        "citedSourceIds": source_ids,
        "degradedReasons": result_payload.get("degraded_reasons", []),
    }


def _headline_from_task_sections(task_sections: dict[str, object]) -> object:
    topline_verdict = task_sections.get("topline_verdict")
    if isinstance(topline_verdict, dict):
        return topline_verdict.get("headline")
    driver_thesis = task_sections.get("driver_thesis")
    if isinstance(driver_thesis, dict):
        return driver_thesis.get("headline")
    return None


def assert_provider_report_synthesis_gate(
    payload: dict[str, object],
    *,
    strict: bool = False,
) -> None:
    if payload["stage"] != STAGE:
        raise RuntimeError("unexpected provider report synthesis stage")
    expected_task_types = {"latest_earnings_readout", "business_driver_deep_dive"}
    if payload["finalReportTaskType"] not in expected_task_types:
        raise RuntimeError("provider synthesis did not return supported task sections")
    if payload.get("synthesis") != "llm":
        raise RuntimeError("provider synthesis did not mark final report as llm synthesized")
    if int(payload.get("claimCount", 0)) <= 0:
        raise RuntimeError("provider synthesis returned no claims")
    if not payload.get("citedSourceIds"):
        raise RuntimeError("provider synthesis returned no cited source ids")
    if strict and payload["status"] != "ok":
        raise RuntimeError("provider synthesis strict gate requires ok status")


def _json_dumps(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
