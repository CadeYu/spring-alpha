from __future__ import annotations

import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.domain_tools import LlamaIndexResearchToolService, SecCompanyFactsProvider
from app.agents.llm_gateway import (
    OpenAiCompatibleLlmClient,
    default_model_for_provider,
)
from app.agents.research_workflow import ResearchAgentWorkflow
from app.contracts.agent import AgentFilingDocument, AgentRequest, LlmProvider
from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline

STAGE = "stage_1_provider_tool_e2e"
type ToolCallSpec = tuple[str, str, dict[str, object]]


@dataclass(frozen=True)
class ProviderToolE2EConfig:
    provider: LlmProvider
    model: str
    api_key: str
    task_type: ResearchTaskType = ResearchTaskType.LATEST_EARNINGS_READOUT


def write_provider_tool_e2e_artifact(
    target_path: Path,
    *,
    config: ProviderToolE2EConfig,
    synthesis_transport: Callable[[str, dict[str, object], dict[str, str], int], dict[str, object]]
    | None = None,
) -> Path:
    started_at = perf_counter()
    llm_client = OpenAiCompatibleLlmClient(
        config.provider,
        config.api_key,
        base_url=_base_url_for_provider(config.provider),
        transport=_smoke_transport(config, synthesis_transport)
        if synthesis_transport is not None
        else None,
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
    payload = _artifact_payload(result.model_dump(mode="json"), config, elapsed_ms)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(_json_dumps(payload), encoding="utf-8")
    assert_provider_tool_e2e_gate(payload)
    return target_path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: write_provider_tool_e2e_artifact.py <target-json>", file=sys.stderr)
        return 2
    written_path = write_provider_tool_e2e_artifact(
        Path(sys.argv[1]),
        config=_config_from_env(),
    )
    print(written_path)
    return 0


def _agent_request(config: ProviderToolE2EConfig) -> AgentRequest:
    if config.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        return _business_driver_agent_request(config)
    if config.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        return _cash_flow_agent_request(config)
    return AgentRequest(
        run_id="provider_tool_e2e_smoke",
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
                accession_number="0000320193-26-000777",
                text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased because demand improved and installed base engagement expanded.
Gross margin benefited from mix, while operating income reflected disciplined expenses.

Item 1A. Risk Factors
Foreign exchange, supply constraints, and competitive pressure could affect future results.
""",
            )
        ],
    )


def _cash_flow_agent_request(config: ProviderToolE2EConfig) -> AgentRequest:
    return AgentRequest(
        run_id="provider_tool_e2e_smoke",
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
                accession_number="0000320193-26-000779",
                text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Operating cash flow funded capital expenditures and share repurchases.
Free cash flow remained supported by working capital discipline and services profitability.

Consolidated Statements of Cash Flows
Net cash provided by operating activities increased, while capital expenditures and buybacks
remained the primary uses of cash.
""",
            )
        ],
    )


def _business_driver_agent_request(config: ProviderToolE2EConfig) -> AgentRequest:
    return AgentRequest(
        run_id="provider_tool_e2e_smoke",
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
                accession_number="0000320193-26-000778",
                text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased because demand improved and installed base engagement expanded.
Gross margin benefited from favorable mix and pricing.

Item 1A. Risk Factors
Foreign exchange, supply constraints, and competitive pressure could affect future results.
""",
            )
        ],
    )


def _config_from_env() -> ProviderToolE2EConfig:
    provider = _provider_from_env()
    api_key = _api_key_for_provider(provider)
    model = os.getenv("PROVIDER_TOOL_E2E_MODEL") or default_model_for_provider(provider)
    task_type = ResearchTaskType(
        os.getenv("PROVIDER_TOOL_E2E_TASK_TYPE") or ResearchTaskType.LATEST_EARNINGS_READOUT.value
    )
    return ProviderToolE2EConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        task_type=task_type,
    )


def _provider_from_env() -> LlmProvider:
    raw_provider = os.getenv("PROVIDER") or os.getenv("PROVIDER_TOOL_E2E_PROVIDER")
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
        raise SystemExit(f"{env_names[provider]} is required for provider tool E2E.")
    return api_key


def _base_url_for_provider(provider: LlmProvider) -> str:
    base_urls = {
        LlmProvider.SILICONFLOW: "https://api.siliconflow.cn/v1",
        LlmProvider.OPENAI: "https://api.openai.com/v1",
        LlmProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta/openai",
    }
    return base_urls[provider]


def _smoke_transport(
    config: ProviderToolE2EConfig,
    final_transport: Callable[[str, dict[str, object], dict[str, str], int], dict[str, object]],
) -> Callable[[str, dict[str, object], dict[str, str], int], dict[str, object]]:
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
) -> ToolCallSpec | None:
    if task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        business_calls: list[ToolCallSpec] = [
            (
                "call_filing",
                "search_filing_sections",
                {
                    "sections": ["MD&A", "Risk Factors"],
                    "query": (
                        "services demand installed base engagement pricing "
                        "supply constraints competition"
                    ),
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
    if task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        cash_flow_calls: list[ToolCallSpec] = [
            (
                "call_facts",
                "get_company_facts",
                {
                    "period": "latest_quarter",
                    "metrics": ["operating cash flow", "capital expenditures", "buybacks"],
                },
            ),
            (
                "call_filing",
                "search_filing_sections",
                {
                    "sections": ["Cash Flows", "MD&A"],
                    "query": "operating cash flow capex buybacks liquidity working capital",
                },
            ),
            (
                "call_metrics",
                "search_metric_evidence",
                {
                    "metrics": ["operating cash flow", "capital expenditures"],
                    "period": "latest_quarter",
                    "query": "operating cash flow capital expenditures buybacks liquidity",
                },
            ),
        ]
        return (
            cash_flow_calls[tool_message_count]
            if tool_message_count < len(cash_flow_calls)
            else None
        )
    earnings_calls: list[ToolCallSpec] = [
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
                "query": "revenue gross margin operating income",
            },
        ),
    ]
    return (
        earnings_calls[tool_message_count]
        if tool_message_count < len(earnings_calls)
        else None
    )


def _tool_call_response(tool_call: ToolCallSpec) -> dict[str, object]:
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
    result_payload: dict[str, object],
    config: ProviderToolE2EConfig,
    elapsed_ms: int,
) -> dict[str, object]:
    final_report = result_payload.get("final_report") or {}
    if not isinstance(final_report, dict):
        final_report = {}
    sections = final_report.get("sections") or {}
    task_sections = final_report.get("task_sections") or {}
    retrieval_records = final_report.get("retrieval_records") or []
    facts = sections.get("facts") if isinstance(sections, dict) else {}
    if not isinstance(facts, dict):
        facts = {}
    fact_record = _fact_record(retrieval_records)
    signal_record = _signal_record(retrieval_records)
    metric_record = _metric_evidence_record(retrieval_records)
    return {
        "stage": STAGE,
        "provider": config.provider.value,
        "model": config.model,
        "status": result_payload.get("status"),
        "elapsedMs": elapsed_ms,
        "synthesis": sections.get("synthesis") if isinstance(sections, dict) else None,
        "finalReportTaskType": task_sections.get("task_type")
        if isinstance(task_sections, dict)
        else None,
        "factSource": facts.get("source") or fact_record.get("fact_source"),
        "factMetricCount": _fact_metric_count(facts, fact_record),
        "ragSourceRefCount": _source_ref_count(retrieval_records),
        "metricEvidenceCount": _metric_evidence_count(metric_record),
        "signalCount": _signal_count(signal_record),
        "signalTypes": signal_record.get("signal_types", []),
        "toolNames": [
            record.get("tool_name")
            for record in retrieval_records
            if isinstance(record, dict) and record.get("tool_name")
        ],
        "degradedReasons": result_payload.get("degraded_reasons", []),
    }


def assert_provider_tool_e2e_gate(payload: dict[str, object]) -> None:
    if payload["stage"] != STAGE:
        raise RuntimeError("unexpected provider tool E2E stage")
    if payload.get("status") != "ok":
        raise RuntimeError("provider tool E2E requires ok status")
    if payload.get("synthesis") != "llm":
        raise RuntimeError("provider tool E2E did not use llm final synthesis")
    if _int_metric(payload, "ragSourceRefCount") <= 0:
        raise RuntimeError("provider tool E2E returned no RAG source refs")
    if payload.get("finalReportTaskType") == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE.value:
        if _int_metric(payload, "signalCount") <= 0:
            raise RuntimeError("provider tool E2E returned no business signals")
        tool_names = payload.get("toolNames")
        if not isinstance(tool_names, list) or "get_business_signals" not in tool_names:
            raise RuntimeError("provider tool E2E did not run business signals tool")
        return
    if payload.get("finalReportTaskType") == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION.value:
        if payload.get("factSource") != "sec_companyfacts":
            raise RuntimeError("provider tool E2E did not use SEC company facts")
        if _int_metric(payload, "factMetricCount") <= 0:
            raise RuntimeError("provider tool E2E returned no SEC fact metrics")
        if _int_metric(payload, "metricEvidenceCount") <= 0:
            raise RuntimeError("provider tool E2E returned no metric evidence")
        tool_names = payload.get("toolNames")
        if not isinstance(tool_names, list) or "search_metric_evidence" not in tool_names:
            raise RuntimeError("provider tool E2E did not run metric evidence tool")
        return
    if payload.get("factSource") != "sec_companyfacts":
        raise RuntimeError("provider tool E2E did not use SEC company facts")
    if _int_metric(payload, "factMetricCount") <= 0:
        raise RuntimeError("provider tool E2E returned no SEC fact metrics")


def _source_ref_count(retrieval_records: object) -> int:
    if not isinstance(retrieval_records, list):
        return 0
    return sum(
        _int_from_object(record.get("source_ref_count", 0))
        for record in retrieval_records
        if isinstance(record, dict)
    )


def _fact_record(retrieval_records: object) -> dict[str, object]:
    if not isinstance(retrieval_records, list):
        return {}
    for record in retrieval_records:
        if isinstance(record, dict) and record.get("tool_name") == "get_company_facts":
            return record
    return {}


def _signal_record(retrieval_records: object) -> dict[str, object]:
    if not isinstance(retrieval_records, list):
        return {}
    for record in retrieval_records:
        if isinstance(record, dict) and record.get("tool_name") == "get_business_signals":
            return record
    return {}


def _metric_evidence_record(retrieval_records: object) -> dict[str, object]:
    if not isinstance(retrieval_records, list):
        return {}
    for record in retrieval_records:
        if isinstance(record, dict) and record.get("tool_name") == "search_metric_evidence":
            return record
    return {}


def _fact_metric_count(facts: dict[str, object], fact_record: dict[str, object]) -> int:
    metrics = facts.get("metrics")
    if isinstance(metrics, list):
        return len(metrics)
    record_count = fact_record.get("record_count")
    if isinstance(record_count, int):
        return record_count
    metric_count = fact_record.get("metric_count")
    if isinstance(metric_count, int):
        return metric_count
    return 0


def _metric_evidence_count(metric_record: dict[str, object]) -> int:
    retrieved_nodes = metric_record.get("retrieved_nodes")
    if isinstance(retrieved_nodes, list):
        return len(retrieved_nodes)
    return _int_from_object(metric_record.get("source_ref_count", 0))


def _signal_count(signal_record: dict[str, object]) -> int:
    signal_count = signal_record.get("signal_count")
    if isinstance(signal_count, int):
        return signal_count
    record_count = signal_record.get("record_count")
    if isinstance(record_count, int):
        return record_count
    return 0


def _int_metric(payload: dict[str, object], key: str) -> int:
    return _int_from_object(payload.get(key, 0))


def _int_from_object(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return 0


def _json_dumps(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
