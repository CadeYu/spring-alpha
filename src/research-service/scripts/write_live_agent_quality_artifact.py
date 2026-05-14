from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, cast
from urllib import request as url_request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agents.domain_tools import (
    LlamaIndexResearchToolService,
    SecCompanyFactsProvider,
    YahooCompanyProfileProvider,
)
from app.agents.llm_gateway import OpenAiCompatibleLlmClient, default_model_for_provider
from app.agents.research_workflow import ResearchAgentWorkflow
from app.contracts.agent import AgentFilingDocument, AgentRequest, BoundedAgentResult, LlmProvider
from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline

STAGE = "live_agent_quality_aapl_msft_nvda"
DEFAULT_TICKERS = ("AAPL", "MSFT", "NVDA")
DEFAULT_TASKS = (
    ResearchTaskType.LATEST_EARNINGS_READOUT,
    ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
    ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
)
SEC_USER_AGENT = "spring-alpha-research-service/0.1 contact@example.com"


@dataclass(frozen=True)
class LiveAgentQualityConfig:
    provider: LlmProvider
    model: str
    api_key: str
    tickers: tuple[str, ...] = DEFAULT_TICKERS
    task_types: tuple[ResearchTaskType, ...] = DEFAULT_TASKS


def write_live_agent_quality_artifact(
    target_path: Path,
    *,
    config: LiveAgentQualityConfig,
) -> Path:
    started_at = perf_counter()
    runs: list[dict[str, Any]] = []
    filings_by_ticker: dict[str, AgentFilingDocument] = {}
    for ticker in config.tickers:
        try:
            filings_by_ticker[ticker] = fetch_latest_sec_filing(ticker)
        except Exception as exc:
            runs.append(
                {
                    "ticker": ticker,
                    "status": "filing_fetch_failed",
                    "error": str(exc),
                }
            )

    for ticker, filing in filings_by_ticker.items():
        for task_type in config.task_types:
            runs.append(
                _run_one_agent(
                    config=config,
                    ticker=ticker,
                    task_type=task_type,
                    filing=filing,
                )
            )

    payload = {
        "stage": STAGE,
        "provider": config.provider.value,
        "model": config.model,
        "tickers": list(config.tickers),
        "taskTypes": [task_type.value for task_type in config.task_types],
        "elapsedMs": int((perf_counter() - started_at) * 1000),
        "runs": runs,
        "summary": summarize_runs(runs),
    }
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return target_path


def _run_one_agent(
    *,
    config: LiveAgentQualityConfig,
    ticker: str,
    task_type: ResearchTaskType,
    filing: AgentFilingDocument,
) -> dict[str, Any]:
    started_at = perf_counter()
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker=filing.ticker,
            filing_type=filing.filing_type,
            filing_date=filing.filing_date,
            accession_number=filing.accession_number,
            text=filing.text,
        )
    )
    client = OpenAiCompatibleLlmClient(
        config.provider,
        config.api_key,
        base_url=_base_url_for_provider(config.provider),
    )
    workflow = ResearchAgentWorkflow(
        tool_service=LlamaIndexResearchToolService(
            pipeline,
            facts_provider=SecCompanyFactsProvider(
                profile_provider=YahooCompanyProfileProvider()
            ),
        ),
        llm_client=client,
        rag_pipeline=pipeline,
    )
    request = AgentRequest(
        run_id=f"live_quality_{ticker.lower()}_{task_type.value}",
        ticker=ticker,
        task_type=task_type,
        language="en",
        llm_provider=config.provider,
        llm_model=config.model,
        llm_api_key=config.api_key,
        filings=[filing],
    )
    try:
        result = workflow.run(request)
    except Exception as exc:
        return {
            "ticker": ticker,
            "taskType": task_type.value,
            "status": "exception",
            "elapsedMs": int((perf_counter() - started_at) * 1000),
            "error": str(exc),
        }
    result_payload = result.model_dump(mode="json")
    return {
        "ticker": ticker,
        "taskType": task_type.value,
        "status": result_payload["status"],
        "elapsedMs": int((perf_counter() - started_at) * 1000),
        "filing": {
            "filingType": filing.filing_type,
            "filingDate": filing.filing_date,
            "accessionNumber": filing.accession_number,
            "textChars": len(filing.text),
        },
        "toolNames": _tool_names(result),
        "events": result_payload["events"],
        "degradedReasons": result_payload.get("degraded_reasons", []),
        "evidencePack": summarize_evidence_pack(_latest_evidence_pack_record(result_payload)),
        "qualityFlags": quality_flags_for_report(result_payload.get("final_report")),
        "qualityFlagEvidence": quality_flag_evidence_for_report(
            result_payload.get("final_report")
        ),
        "reportPreview": report_preview(result_payload.get("final_report")),
    }


def summarize_evidence_pack(record: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(record, dict) and "serialized_length" in record:
        source_types = record.get("metric_fact_source_types")
        return {
            "filingEvidenceCount": _int_value(record.get("filing_evidence_count")),
            "metricFactCount": _int_value(record.get("metric_fact_count")),
            "metricFactSourceTypes": source_types if isinstance(source_types, dict) else {},
            "serializedLength": _int_value(record.get("serialized_length")),
            "snippetCharCount": 0,
        }
    pack = record.get("evidence_pack") if isinstance(record, dict) else None
    if not isinstance(pack, dict):
        return {
            "filingEvidenceCount": 0,
            "metricFactCount": 0,
            "metricFactSourceTypes": {},
            "serializedLength": 0,
            "snippetCharCount": 0,
        }
    metric_facts = pack.get("metric_facts")
    filing_evidence = pack.get("filing_evidence")
    metric_fact_items = metric_facts if isinstance(metric_facts, list) else []
    filing_items = filing_evidence if isinstance(filing_evidence, list) else []
    source_types = Counter(
        str(item.get("source_type") or "unknown")
        for item in metric_fact_items
        if isinstance(item, dict)
    )
    snippet_chars = sum(
        len(str(item.get("snippet") or ""))
        for item in filing_items
        if isinstance(item, dict)
    )
    return {
        "filingEvidenceCount": len(filing_items),
        "metricFactCount": len(metric_fact_items),
        "metricFactSourceTypes": dict(sorted(source_types.items())),
        "serializedLength": len(json.dumps(pack, sort_keys=True)),
        "snippetCharCount": snippet_chars,
    }


def quality_flags_for_report(final_report: object) -> list[str]:
    if not isinstance(final_report, dict):
        return ["missing_final_report"]
    flags: set[str] = set()
    authored_text = " ".join(_authored_text_values(final_report)).lower()
    task_sections = final_report.get("task_sections")
    claims = final_report.get("claims")
    if not isinstance(claims, list) or not claims:
        flags.add("no_claims")
    if re.search(r"\b(n/a|not available|placeholder|evidence point)\b", authored_text):
        flags.add("placeholder_text")
    if "important for investors" in authored_text and len(authored_text) < 2500:
        flags.add("generic_investor_language")
    if isinstance(task_sections, dict):
        task_type = task_sections.get("task_type")
        if task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE.value:
            driver_map = task_sections.get("driver_map")
            if isinstance(driver_map, dict) and not any(
                isinstance(value, list) and value for value in driver_map.values()
            ):
                flags.add("empty_driver_map")
        if task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION.value:
            cash_metrics = task_sections.get("cash_metrics")
            capital_allocation = task_sections.get("capital_allocation")
            if not isinstance(cash_metrics, list) or not cash_metrics:
                flags.add("empty_cash_metrics")
            if isinstance(capital_allocation, dict) and not any(
                isinstance(value, list) and value for value in capital_allocation.values()
            ):
                flags.add("empty_capital_allocation")
        if task_type == ResearchTaskType.LATEST_EARNINGS_READOUT.value:
            financial_dashboard = task_sections.get("financial_dashboard")
            metrics = (
                financial_dashboard.get("metrics")
                if isinstance(financial_dashboard, dict)
                else None
            )
            if not isinstance(metrics, list) or not metrics:
                flags.add("empty_financial_dashboard")
    return sorted(flags)


def quality_flag_evidence_for_report(final_report: object) -> dict[str, list[str]]:
    if not isinstance(final_report, dict):
        return {}
    authored_texts = _authored_text_values(final_report)
    placeholder_hits = [
        _truncate(text, 300)
        for text in authored_texts
        if re.search(r"\b(n/a|not available|placeholder|evidence point)\b", text.lower())
    ]
    evidence: dict[str, list[str]] = {}
    if placeholder_hits:
        evidence["placeholder_text"] = placeholder_hits[:5]
    generic_hits = [
        _truncate(text, 300)
        for text in authored_texts
        if "important for investors" in text.lower()
    ]
    if generic_hits:
        evidence["generic_investor_language"] = generic_hits[:5]
    return evidence


def _authored_text_values(value: object, *, parent_key: str | None = None) -> list[str]:
    skipped_keys = {
        "accession_number",
        "citation_status",
        "evidence_refs",
        "excerpt",
        "raw",
        "retrieval_records",
        "source_id",
        "source_ids",
        "source_refs",
    }
    if isinstance(value, str):
        return [] if parent_key in skipped_keys else [value]
    if isinstance(value, list):
        texts: list[str] = []
        for item in value:
            texts.extend(_authored_text_values(item, parent_key=parent_key))
        return texts
    if isinstance(value, dict):
        texts = []
        for key, child in value.items():
            if key in skipped_keys:
                continue
            texts.extend(_authored_text_values(child, parent_key=key))
        return texts
    return []


def report_preview(final_report: object) -> dict[str, Any]:
    if not isinstance(final_report, dict):
        return {}
    task_sections = final_report.get("task_sections")
    if not isinstance(task_sections, dict):
        return {}
    preview: dict[str, Any] = {"taskType": task_sections.get("task_type")}
    for path in (
        ("topline_verdict", "headline"),
        ("topline_verdict", "summary"),
        ("company_profile", "summary"),
        ("driver_thesis", "headline"),
        ("driver_thesis", "summary"),
        ("cash_quality_verdict", "headline"),
        ("cash_quality_verdict", "summary"),
    ):
        value = _nested_value(task_sections, path)
        if value:
            preview[".".join(path)] = _truncate(str(value), 500)
    return preview


def summarize_runs(runs: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(run.get("status") or "unknown") for run in runs)
    flags = Counter(
        flag
        for run in runs
        for flag in run.get("qualityFlags", [])
        if isinstance(flag, str)
    )
    evidence_lengths: list[int] = []
    for run in runs:
        evidence_pack = run.get("evidencePack")
        if not isinstance(evidence_pack, dict):
            continue
        serialized_length = evidence_pack.get("serializedLength")
        if isinstance(serialized_length, int):
            evidence_lengths.append(serialized_length)
    return {
        "statusCounts": dict(sorted(statuses.items())),
        "qualityFlagCounts": dict(sorted(flags.items())),
        "maxEvidencePackSerializedLength": max(evidence_lengths, default=0),
        "avgEvidencePackSerializedLength": int(sum(evidence_lengths) / len(evidence_lengths))
        if evidence_lengths
        else 0,
    }


def fetch_latest_sec_filing(ticker: str) -> AgentFilingDocument:
    cik = _cik_for_ticker(ticker)
    submissions = _sec_json(f"https://data.sec.gov/submissions/CIK{cik:010d}.json")
    recent = submissions.get("filings", {})
    recent_filings = recent.get("recent") if isinstance(recent, dict) else {}
    if not isinstance(recent_filings, dict):
        raise RuntimeError(f"SEC recent filings missing for {ticker}")
    forms = _list_value(recent_filings.get("form"))
    accession_numbers = _list_value(recent_filings.get("accessionNumber"))
    filing_dates = _list_value(recent_filings.get("filingDate"))
    primary_documents = _list_value(recent_filings.get("primaryDocument"))
    for index, form in enumerate(forms):
        if str(form) not in {"10-Q", "10-K"}:
            continue
        accession_number = str(accession_numbers[index])
        primary_document = str(primary_documents[index])
        text = _sec_text(
            "https://www.sec.gov/Archives/edgar/data/"
            f"{cik}/{accession_number.replace('-', '')}/{primary_document}"
        )
        return AgentFilingDocument(
            ticker=ticker,
            filing_type=str(form),
            filing_date=str(filing_dates[index]),
            accession_number=accession_number,
            text=text,
        )
    raise RuntimeError(f"No recent 10-Q or 10-K found for {ticker}")


def _latest_evidence_pack_record(result_payload: dict[str, Any]) -> dict[str, Any] | None:
    for record in reversed(result_payload.get("retrieval_records", [])):
        if not isinstance(record, dict):
            continue
        evidence_pack = record.get("evidence_pack")
        if isinstance(evidence_pack, dict):
            return evidence_pack
    return None


def _tool_names(result: BoundedAgentResult) -> list[str]:
    return [event.tool_name for event in result.events if event.tool_name]


def _nested_value(payload: dict[str, Any], path: tuple[str, ...]) -> object:
    current: object = payload
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _truncate(value: str, max_chars: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."


def _config_from_env() -> LiveAgentQualityConfig:
    provider = _provider_from_env()
    api_key = _api_key_for_provider(provider)
    model = (
        os.getenv("PROVIDER_MODEL")
        or os.getenv("LIVE_AGENT_QUALITY_MODEL")
        or default_model_for_provider(provider)
    )
    tickers = tuple(
        ticker.strip().upper()
        for ticker in (
            os.getenv("LIVE_AGENT_QUALITY_TICKERS") or ",".join(DEFAULT_TICKERS)
        ).split(",")
        if ticker.strip()
    )
    task_types = tuple(
        ResearchTaskType(task_type.strip())
        for task_type in (
            os.getenv("LIVE_AGENT_QUALITY_TASKS")
            or ",".join(task_type.value for task_type in DEFAULT_TASKS)
        ).split(",")
        if task_type.strip()
    )
    return LiveAgentQualityConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        tickers=tickers,
        task_types=task_types,
    )


def _provider_from_env() -> LlmProvider:
    raw_provider = os.getenv("PROVIDER") or os.getenv("LIVE_AGENT_QUALITY_PROVIDER")
    if raw_provider:
        return LlmProvider(raw_provider.strip().lower())
    if os.getenv("SILICONFLOW_API_KEY"):
        return LlmProvider.SILICONFLOW
    if os.getenv("GEMINI_API_KEY"):
        return LlmProvider.GEMINI
    if os.getenv("OPENAI_API_KEY"):
        return LlmProvider.OPENAI
    raise SystemExit("Set PROVIDER plus a matching provider API key.")


def _api_key_for_provider(provider: LlmProvider) -> str:
    env_names = {
        LlmProvider.SILICONFLOW: "SILICONFLOW_API_KEY",
        LlmProvider.GEMINI: "GEMINI_API_KEY",
        LlmProvider.OPENAI: "OPENAI_API_KEY",
    }
    api_key = os.getenv(env_names[provider])
    if not api_key:
        raise SystemExit(f"{env_names[provider]} is required for live agent quality.")
    return api_key


def _base_url_for_provider(provider: LlmProvider) -> str:
    base_urls = {
        LlmProvider.SILICONFLOW: "https://api.siliconflow.cn/v1",
        LlmProvider.OPENAI: "https://api.openai.com/v1",
        LlmProvider.GEMINI: "https://generativelanguage.googleapis.com/v1beta/openai",
    }
    return base_urls[provider]


def _cik_for_ticker(ticker: str) -> int:
    payload = _sec_json("https://www.sec.gov/files/company_tickers.json")
    for record in payload.values():
        if isinstance(record, dict) and str(record.get("ticker", "")).upper() == ticker.upper():
            return int(str(record["cik_str"]))
    raise RuntimeError(f"SEC ticker mapping not found for {ticker}")


def _sec_json(url: str) -> dict[str, Any]:
    request = url_request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
    with url_request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"SEC JSON response must be an object: {url}")
    return payload


def _sec_text(url: str) -> str:
    request = url_request.Request(url, headers={"User-Agent": SEC_USER_AGENT})
    with url_request.urlopen(request, timeout=30) as response:
        text = cast(str, response.read().decode("utf-8", errors="replace"))
    return text


def _list_value(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _int_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: write_live_agent_quality_artifact.py <target-json>", file=sys.stderr)
        return 2
    written_path = write_live_agent_quality_artifact(
        Path(sys.argv[1]),
        config=_config_from_env(),
    )
    print(written_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
