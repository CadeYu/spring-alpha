from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.domain_tools import LlamaIndexResearchToolService, SecCompanyFactsProvider
from app.agents.llm_gateway import (
    LlmTransport,
    OpenAiCompatibleLlmClient,
    default_model_for_provider,
)
from app.agents.research_workflow import ResearchAgentWorkflow
from app.contracts.agent import AgentFilingDocument, AgentRequest, LlmProvider
from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline

STAGE = "stage_1_provider_tool_calling_agent"


@dataclass(frozen=True)
class ProviderToolCallingAgentConfig:
    provider: LlmProvider
    model: str
    api_key: str


def write_provider_tool_calling_agent_artifact(
    target_path: Path,
    *,
    config: ProviderToolCallingAgentConfig,
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
    pipeline = LlamaIndexRagPipeline()
    request = _agent_request(config)
    for filing in request.filings:
        pipeline.ingest_filing(
            FilingDocument(
                ticker=filing.ticker,
                filing_type=filing.filing_type,
                filing_date=filing.filing_date,
                accession_number=filing.accession_number,
                text=filing.text,
            )
        )
    workflow = ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            pipeline,
            facts_provider=SecCompanyFactsProvider(),
        ),
        llm_client=client,
        rag_pipeline=pipeline,
    )
    result = workflow.run(request)
    elapsed_ms = int((perf_counter() - started_at) * 1000)
    payload = _artifact_payload(result, config=config, elapsed_ms=elapsed_ms)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(_json_dumps(payload), encoding="utf-8")
    assert_provider_tool_calling_agent_gate(payload, strict=strict)
    return target_path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: write_provider_tool_calling_agent_artifact.py <target-json>", file=sys.stderr)
        return 2

    config = _config_from_env()
    target_path = Path(sys.argv[1])
    written_path = write_provider_tool_calling_agent_artifact(target_path, config=config)
    print(written_path)
    return 0


def _config_from_env() -> ProviderToolCallingAgentConfig:
    provider = _provider_from_env()
    api_key = _api_key_for_provider(provider)
    model = os.getenv("PROVIDER_TOOL_CALLING_AGENT_MODEL") or default_model_for_provider(provider)
    return ProviderToolCallingAgentConfig(provider=provider, model=model, api_key=api_key)


def _provider_from_env() -> LlmProvider:
    raw_provider = os.getenv("PROVIDER") or os.getenv("PROVIDER_TOOL_CALLING_AGENT_PROVIDER")
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
        raise SystemExit(
            f"{env_names[provider]} is required for provider tool-calling agent smoke."
        )
    return api_key


def _base_url_for_provider(provider: LlmProvider) -> str:
    base_urls = {
        LlmProvider.SILICONFLOW: "https://api.siliconflow.cn/v1",
        LlmProvider.OPENAI: "https://api.openai.com/v1",
        LlmProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta/openai",
    }
    return base_urls[provider]


def _agent_request(config: ProviderToolCallingAgentConfig) -> AgentRequest:
    return AgentRequest(
        run_id="provider_tool_calling_agent_smoke",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
        language="en",
        llm_provider=config.provider,
        llm_model=config.model,
        llm_api_key=config.api_key,
        filings=[
            AgentFilingDocument(
                ticker="AAPL",
                filing_type="10-Q",
                filing_date="2026-04-30",
                accession_number="0000320193-26-000777",
                text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue and gross margin improved as Services demand increased.
Operating income reflected disciplined expenses and favorable mix.
""",
            )
        ],
    )


def _artifact_payload(
    result: Any,
    *,
    config: ProviderToolCallingAgentConfig,
    elapsed_ms: int,
) -> dict[str, object]:
    result_payload = result.model_dump(mode="json")
    events = result_payload["events"]
    tool_events = [event for event in events if event.get("tool_name") is not None]
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
        "agentEventCount": len(tool_events),
        "toolNames": tool_names,
        "hasToolCalls": bool(tool_events),
        "stopReason": _stop_reason(events),
        "elapsedMs": elapsed_ms,
        "finalReportTaskType": task_sections.get("task_type"),
        "degradedReasons": result_payload.get("degraded_reasons", []),
        "events": events,
    }


def _stop_reason(events: list[dict[str, object]]) -> str:
    if not events:
        return "no_events"
    if any(event.get("tool_name") for event in events):
        return "tool_calling_complete"
    return "completed"


def assert_provider_tool_calling_agent_gate(
    payload: dict[str, object],
    *,
    strict: bool = False,
) -> None:
    if payload["stage"] != STAGE:
        raise RuntimeError("unexpected provider tool-calling agent stage")
    if _int_metric(payload, "eventCount") <= 0:
        raise RuntimeError("provider tool-calling agent returned no events")
    if _int_metric(payload, "agentEventCount") <= 0:
        raise RuntimeError("provider tool-calling agent returned no tool events")
    if payload["hasToolCalls"] is not True:
        raise RuntimeError("provider tool-calling agent did not record tool calls")
    if payload["finalReportTaskType"] != "latest_earnings_readout":
        raise RuntimeError(
            "provider tool-calling agent did not return latest earnings task sections"
        )
    if not strict:
        return
    if payload["stopReason"] != "tool_calling_complete":
        raise RuntimeError("provider tool-calling agent must finish after tool calls")
    raw_tool_names = payload.get("toolNames", [])
    tool_names = set(raw_tool_names) if isinstance(raw_tool_names, list) else set()
    if not (tool_names & {"search_filing_sections", "search_metric_evidence"}):
        raise RuntimeError(
            "provider tool-calling agent must execute at least one evidence retrieval tool"
        )


def _json_dumps(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True)


def _int_metric(payload: dict[str, object], key: str) -> int:
    value = payload.get(key, 0)
    return value if isinstance(value, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
