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
    llm_client = OpenAiCompatibleLlmClient(
        config.provider,
        config.api_key,
        base_url=_base_url_for_provider(config.provider),
        transport=_smoke_transport(config, transport) if transport is not None else None,
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
        llm_client=llm_client,
        rag_pipeline=pipeline,
    )
    result = workflow.run(request)
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
    if config.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        filing_text = """
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services demand improved as installed base engagement expanded.
Gross margin benefited from favorable mix and pricing.
"""
        accession_number = "0000320193-26-000778"
    else:
        filing_text = """
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue and gross margin improved as Services demand increased.
Operating income reflected disciplined expenses and favorable mix.
"""
        accession_number = "0000320193-26-000777"
    return AgentRequest(
        run_id="provider_report_synthesis_smoke",
        ticker="AAPL",
        task_type=config.task_type,
        language="en",
        llm_provider=config.provider,
        llm_model=config.model,
        llm_api_key=config.api_key,
        filings=[
            AgentFilingDocument(
                ticker="AAPL",
                filing_type="10-Q",
                filing_date="2026-04-30",
                accession_number=accession_number,
                text=filing_text,
            )
        ],
    )


def _smoke_transport(
    config: ProviderReportSynthesisConfig,
    final_transport: LlmTransport,
) -> LlmTransport:
    def transport(
        url: str,
        payload: dict[str, object],
        headers: dict[str, str],
        timeout_seconds: int,
    ) -> dict[str, object]:
        if "tools" not in payload:
            return final_transport(url, payload, headers, timeout_seconds)
        tool_messages = _tool_message_count(payload)
        tool_call = _next_tool_call(config.task_type, tool_messages)
        if tool_call is None:
            return final_transport(url, payload, headers, timeout_seconds)
        return _tool_call_response(tool_call)

    return transport


def _tool_message_count(payload: dict[str, object]) -> int:
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return 0
    return sum(
        1
        for message in messages
        if isinstance(message, dict) and message.get("role") == "tool"
    )


def _next_tool_call(
    task_type: ResearchTaskType,
    tool_message_count: int,
) -> tuple[str, str, dict[str, object]] | None:
    if task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        business_calls: list[tuple[str, str, dict[str, object]]] = [
            (
                "call_filing",
                "search_filing_sections",
                {
                    "sections": ["MD&A", "Business"],
                    "query": "business drivers services demand segment product strategy",
                },
            ),
            (
                "call_metrics",
                "search_metric_evidence",
                {
                    "metrics": ["revenue", "segment revenue"],
                    "period": "latest_quarter",
                    "query": "revenue segment revenue services demand",
                },
            ),
            (
                "call_signals",
                "get_business_signals",
                {"signal_types": ["product", "demand", "pricing", "risk"]},
            ),
        ]
        return (
            business_calls[tool_message_count]
            if tool_message_count < len(business_calls)
            else None
        )
    earnings_calls: list[tuple[str, str, dict[str, object]]] = [
        (
            "call_facts",
            "get_company_facts",
            {
                "period": "latest_quarter",
                "metrics": ["revenue", "gross margin", "operating income"],
            },
        ),
        (
            "call_metrics",
            "search_metric_evidence",
            {
                "metrics": ["revenue", "gross margin", "operating income"],
                "period": "latest_quarter",
                "query": "latest earnings revenue gross margin operating income",
            },
        ),
    ]
    return (
        earnings_calls[tool_message_count]
        if tool_message_count < len(earnings_calls)
        else None
    )


def _tool_call_response(tool_call: tuple[str, str, dict[str, object]]) -> dict[str, object]:
    call_id, name, arguments = tool_call
    return {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": _json_dumps(arguments),
                            },
                        }
                    ],
                }
            }
        ]
    }


def _artifact_payload(
    result: Any,
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
    if _int_metric(payload, "claimCount") <= 0:
        raise RuntimeError("provider synthesis returned no claims")
    if not payload.get("citedSourceIds"):
        raise RuntimeError("provider synthesis returned no cited source ids")
    if strict and payload["status"] != "ok":
        raise RuntimeError("provider synthesis strict gate requires ok status")


def _json_dumps(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True)


def _int_metric(payload: dict[str, object], key: str) -> int:
    value = payload.get(key, 0)
    return value if isinstance(value, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
