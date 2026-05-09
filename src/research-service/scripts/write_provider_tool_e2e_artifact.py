from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.deterministic_workflow import DeterministicAgentWorkflow
from app.agents.domain_tools import LlamaIndexResearchToolService, SecCompanyFactsProvider
from app.agents.llm_gateway import (
    LlmRequest,
    LlmResponse,
    OpenAiCompatibleLlmClient,
    default_model_for_provider,
)
from app.agents.tool_registry import default_tool_registry
from app.contracts.agent import AgentFilingDocument, AgentRequest, LlmProvider
from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline

STAGE = "stage_1_provider_tool_e2e"


@dataclass(frozen=True)
class ProviderToolE2EConfig:
    provider: LlmProvider
    model: str
    api_key: str


def write_provider_tool_e2e_artifact(
    target_path: Path,
    *,
    config: ProviderToolE2EConfig,
) -> Path:
    started_at = perf_counter()
    llm_client = OpenAiCompatibleLlmClient(
        config.provider,
        config.api_key,
        base_url=_base_url_for_provider(config.provider),
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
    workflow = DeterministicAgentWorkflow(
        registry=default_tool_registry(
            LlamaIndexResearchToolService(
                pipeline,
                facts_provider=SecCompanyFactsProvider(),
            )
        ),
        llm_client=_DeterministicPlannerClient(config.provider),
        report_synthesis_client=llm_client,
        enable_report_synthesis=True,
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


class _DeterministicPlannerClient:
    def __init__(self, provider: LlmProvider) -> None:
        self.provider = provider
        self._calls = 0

    def complete_json(self, request: LlmRequest) -> LlmResponse:
        self._calls += 1
        if self._calls == 1:
            content = {
                "decision": "call_tool",
                "summary": "Collect SEC company facts before tool E2E synthesis.",
                "tool_name": "get_company_facts",
                "tool_input": {
                    "period": "latest_quarter",
                    "metrics": ["revenue", "gross margin"],
                },
            }
        elif self._calls == 2:
            content = {
                "decision": "call_tool",
                "summary": "Search RAG filing evidence before tool E2E synthesis.",
                "tool_name": "search_filing_sections",
                "tool_input": {
                    "sections": ["MD&A", "Risk Factors"],
                    "query": "services revenue demand gross margin operating income risk",
                },
            }
        else:
            content = {
                "decision": "finalize",
                "summary": "SEC facts and RAG evidence are ready for synthesis.",
            }
        return LlmResponse(
            provider=request.provider,
            model=request.model,
            content=content,
        )


def _agent_request(config: ProviderToolE2EConfig) -> AgentRequest:
    return AgentRequest(
        run_id="provider_tool_e2e_smoke",
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
Services revenue increased because demand improved and installed base engagement expanded.
Gross margin benefited from mix, while operating income reflected disciplined expenses.

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
    return ProviderToolE2EConfig(provider=provider, model=model, api_key=api_key)


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
    if payload.get("factSource") != "sec_companyfacts":
        raise RuntimeError("provider tool E2E did not use SEC company facts")
    if int(payload.get("factMetricCount", 0)) <= 0:
        raise RuntimeError("provider tool E2E returned no SEC fact metrics")
    if int(payload.get("ragSourceRefCount", 0)) <= 0:
        raise RuntimeError("provider tool E2E returned no RAG source refs")


def _source_ref_count(retrieval_records: object) -> int:
    if not isinstance(retrieval_records, list):
        return 0
    return sum(
        int(record.get("source_ref_count", 0))
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


def _fact_metric_count(facts: dict[str, object], fact_record: dict[str, object]) -> int:
    metrics = facts.get("metrics")
    if isinstance(metrics, list):
        return len(metrics)
    metric_count = fact_record.get("metric_count")
    if isinstance(metric_count, int):
        return metric_count
    return 0


def _json_dumps(payload: dict[str, object]) -> str:
    import json

    return json.dumps(payload, indent=2, sort_keys=True)


if __name__ == "__main__":
    raise SystemExit(main())
