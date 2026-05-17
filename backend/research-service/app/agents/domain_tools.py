import json
import re
from collections.abc import Callable, Iterable, Mapping
from urllib import request as url_request

from app.contracts.agent import AgentState, ToolResult
from app.contracts.research_task import ResearchTaskType
from app.contracts.tools import (
    BusinessSignalsInput,
    CompanyFactsInput,
    FilingSectionSearchInput,
    MetricEvidenceInput,
)
from app.rag.llamaindex_pipeline import LlamaIndexRagPipeline, RetrieveEvidenceResult

SecJsonTransport = Callable[[str, float], dict[str, object]]
MarketProfileTransport = Callable[[str, float], dict[str, object]]


class YahooCompanyProfileProvider:
    def __init__(
        self,
        *,
        transport: MarketProfileTransport | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self._transport = transport or _yahoo_json_transport
        self._timeout_seconds = timeout_seconds

    def fetch_company_profile(self, *, ticker: str) -> dict[str, object]:
        payload = self._transport(
            (
                "https://query2.finance.yahoo.com/v10/finance/quoteSummary/"
                f"{ticker.upper()}?modules=assetProfile,price"
            ),
            self._timeout_seconds,
        )
        result = _first_quote_summary_result(payload)
        asset_profile = result.get("assetProfile")
        price = result.get("price")
        if not isinstance(asset_profile, dict):
            asset_profile = {}
        if not isinstance(price, dict):
            price = {}

        business_summary = _yahoo_raw_value(
            asset_profile.get("longBusinessSummary")
            or asset_profile.get("description")
        )
        if not business_summary:
            return {}

        profile: dict[str, object] = {
            "business_summary": business_summary,
            "businessSummary": business_summary,
            "market_business_summary": business_summary,
            "marketBusinessSummary": business_summary,
            "profile_source": "yahoo_quote_summary",
        }
        for output_key, value in {
            "company_name": price.get("longName") or price.get("shortName"),
            "sector": asset_profile.get("sector"),
            "industry": asset_profile.get("industry"),
            "security_type": price.get("quoteType"),
        }.items():
            normalized = _yahoo_raw_value(value)
            if normalized:
                profile[output_key] = normalized
        return profile


class SecCompanyFactsProvider:
    def __init__(
        self,
        *,
        transport: SecJsonTransport | None = None,
        profile_provider: YahooCompanyProfileProvider | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._transport = transport or _sec_json_transport
        self._profile_provider = profile_provider
        self._timeout_seconds = timeout_seconds
        self._ticker_map: dict[str, dict[str, object]] | None = None

    def fetch_company_facts(
        self,
        *,
        ticker: str,
        period: str | None,
        metrics: list[str],
    ) -> dict[str, object]:
        ticker_record = self._ticker_record(ticker)
        cik = int(str(ticker_record["cik_str"]))
        companyfacts = self._transport(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
            self._timeout_seconds,
        )
        requested_metrics = metrics or ["revenue", "gross margin", "operating income"]
        metric_records = [
            record
            for metric in requested_metrics
            for record in [_latest_metric_record(companyfacts, metric, period or "latest_quarter")]
            if record is not None
        ]
        metric_records = _filter_metric_records_to_reporting_cohort(
            metric_records,
            period or "latest_quarter",
        )
        found_metric_names = {str(record["name"]) for record in metric_records}
        missing_metrics = [
            metric
            for metric in requested_metrics
            if _normalize_metric_name(metric) not in found_metric_names
        ]
        facts: dict[str, object] = {
            "ticker": ticker.upper(),
            "company_name": companyfacts.get("entityName") or ticker_record.get("title"),
            "source": "sec_companyfacts",
            "period": period or "latest_quarter",
            "metrics": metric_records,
            "missing_metrics": missing_metrics,
        }
        facts.update(self._safe_company_profile(ticker=ticker))
        return facts

    def _safe_company_profile(self, *, ticker: str) -> dict[str, object]:
        if self._profile_provider is None:
            return {}
        try:
            return self._profile_provider.fetch_company_profile(ticker=ticker)
        except Exception:
            return {}

    def _ticker_record(self, ticker: str) -> dict[str, object]:
        normalized_ticker = ticker.upper()
        known_cik = _KNOWN_CIK_BY_TICKER.get(normalized_ticker)
        if known_cik is not None:
            return {
                "cik_str": known_cik,
                "ticker": normalized_ticker,
                "title": normalized_ticker,
            }
        ticker_map = self._load_ticker_map()
        ticker_record = ticker_map.get(normalized_ticker)
        if ticker_record is None:
            raise ValueError(f"SEC ticker mapping not found for {normalized_ticker}")
        return ticker_record

    def _load_ticker_map(self) -> dict[str, dict[str, object]]:
        if self._ticker_map is not None:
            return self._ticker_map
        payload = self._transport(
            "https://www.sec.gov/files/company_tickers.json",
            self._timeout_seconds,
        )
        self._ticker_map = {
            str(record.get("ticker", "")).upper(): record
            for record in payload.values()
            if isinstance(record, dict) and record.get("ticker")
        }
        return self._ticker_map


class ResearchToolService:
    def __init__(self, facts_provider: SecCompanyFactsProvider | None = None) -> None:
        self._facts_provider = facts_provider

    def get_company_facts(self, tool_input: CompanyFactsInput, state: AgentState) -> ToolResult:
        if self._facts_provider is not None:
            facts = self._facts_provider.fetch_company_facts(
                ticker=state.ticker,
                period=tool_input.period,
                metrics=tool_input.metrics,
            )
            facts = {**state.evidence_memory.facts, **facts}
            raw_missing_metrics = facts.get("missing_metrics", [])
            missing_metric_values = (
                raw_missing_metrics if isinstance(raw_missing_metrics, list) else []
            )
            missing_metrics = [
                str(metric) for metric in missing_metric_values if str(metric)
            ]
            if missing_metrics:
                return ToolResult.partial(
                    data=facts,
                    degraded_reason=(
                        "SEC company facts missing metrics: " + ", ".join(missing_metrics)
                    ),
                )
            return ToolResult.ok(data=facts)
        return ToolResult.ok(
            data={
                "ticker": state.ticker,
                "task_type": state.task_type.value,
                "period": tool_input.period or "latest_quarter",
                "metrics": tool_input.metrics,
            }
        )

    def search_filing_sections(
        self,
        tool_input: FilingSectionSearchInput,
        state: AgentState,
    ) -> ToolResult:
        source_ref = {
            "source_id": f"{state.run_id}:filing:1",
            "section": tool_input.sections[0],
            "snippet": (
                f"Evidence placeholder for {tool_input.query} from the selected filing section."
            ),
            "citation_status": "unverified",
        }
        return ToolResult.ok(
            data={
                "query": tool_input.query,
                "retrieved_nodes": [
                    {
                        "node_id": source_ref["source_id"],
                        **source_ref,
                    }
                ],
            },
            source_refs=[source_ref],
        )

    def search_metric_evidence(
        self,
        tool_input: MetricEvidenceInput,
        state: AgentState,
    ) -> ToolResult:
        metric = tool_input.metrics[0]
        source_ref = {
            "source_id": f"{state.run_id}:metric:1",
            "section": "Financial Statements",
            "snippet": f"Evidence placeholder for {metric}.",
            "citation_status": "unverified",
        }
        return ToolResult.ok(
            data={
                "records": [
                    {
                        "metric": metric,
                        "period": tool_input.period or "latest_quarter",
                        "source_id": source_ref["source_id"],
                    }
                ]
            },
            source_refs=[source_ref],
        )

    def get_business_signals(
        self,
        tool_input: BusinessSignalsInput,
        state: AgentState,
    ) -> ToolResult:
        records = _extract_business_signal_records(
            state.evidence_memory.source_refs,
            tool_input.signal_types,
        )
        if not records:
            return ToolResult.empty(
                data={"records": []},
                degraded_reason="No evidence available for business signal extraction.",
            )
        return ToolResult.ok(
            data={"records": records},
        )

class LlamaIndexResearchToolService(ResearchToolService):
    def __init__(
        self,
        rag_pipeline: LlamaIndexRagPipeline,
        facts_provider: SecCompanyFactsProvider | None = None,
    ) -> None:
        super().__init__(facts_provider=facts_provider)
        self._rag_pipeline = rag_pipeline

    def search_filing_sections(
        self,
        tool_input: FilingSectionSearchInput,
        state: AgentState,
    ) -> ToolResult:
        queries = _task_scoped_filing_queries(tool_input.query, state)
        sections = _task_scoped_filing_sections(tool_input.sections, state)
        results = [
            self._rag_pipeline.retrieve_evidence(
                run_id=state.run_id,
                ticker=state.ticker,
                task_type=state.task_type,
                query=query,
                sections=sections,
                top_k=_top_k_for_task_query(tool_input.limit, state),
            )
            for query in queries
        ]
        source_refs = _dedupe_source_refs(
            source_ref.model_dump(mode="json")
            for result in results
            for source_ref in result.source_refs
        )
        retrieved_nodes = _dedupe_retrieved_nodes(
            node
            for result in results
            for node in _retrieved_nodes(result)
        )
        latency_ms = sum(result.latency_ms for result in results)
        if not source_refs:
            return ToolResult.empty(
                data={"query": " | ".join(queries), "retrieved_nodes": []},
                degraded_reason="No filing section evidence matched the query.",
                latency_ms=latency_ms,
            )
        return ToolResult.ok(
            data={
                "query": " | ".join(queries),
                "retrieved_nodes": retrieved_nodes,
                "fallback_status": _fallback_status_from_results(results),
            },
            latency_ms=latency_ms,
            source_refs=source_refs,
        )

    def search_metric_evidence(
        self,
        tool_input: MetricEvidenceInput,
        state: AgentState,
    ) -> ToolResult:
        queries = _task_scoped_metric_queries(
            tool_input.query or " ".join(tool_input.metrics), state
        )
        results = [
            self._rag_pipeline.retrieve_evidence(
                run_id=state.run_id,
                ticker=state.ticker,
                task_type=state.task_type,
                query=query,
                sections=_preferred_metric_sections(tool_input.metrics),
                top_k=2 if state.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION else 5,
            )
            for query in queries
        ]
        source_refs = _dedupe_source_refs(
            source_ref.model_dump(mode="json")
            for result in results
            for source_ref in result.source_refs
        )
        retrieved_nodes = _dedupe_retrieved_nodes(
            node
            for result in results
            for node in _retrieved_nodes(result)
        )
        latency_ms = sum(result.latency_ms for result in results)
        facts_by_metric = _facts_by_metric(state)
        fact_source_refs = _companyfacts_source_refs(
            run_id=state.run_id,
            metrics=tool_input.metrics,
            facts_by_metric=facts_by_metric,
        )
        combined_source_refs = _dedupe_source_refs([*fact_source_refs, *source_refs])
        if not combined_source_refs:
            return ToolResult.empty(
                data={"records": [], "retrieved_nodes": []},
                degraded_reason="No metric evidence matched the query.",
                latency_ms=latency_ms,
            )
        return ToolResult.ok(
            data={
                "records": [
                    _metric_evidence_record(
                        metric,
                        tool_input.period or "latest_quarter",
                        combined_source_refs,
                        facts_by_metric,
                    )
                    for metric in tool_input.metrics
                ],
                "retrieved_nodes": retrieved_nodes,
                "fallback_status": _fallback_status_from_results(results),
            },
            latency_ms=latency_ms,
            source_refs=combined_source_refs,
        )


def _content_terms(text: str) -> set[str]:
    stop_words = {
        "a",
        "an",
        "and",
        "because",
        "by",
        "for",
        "in",
        "of",
        "the",
        "to",
    }
    return {
        term
        for term in re.findall(r"[a-z0-9]+", text.lower())
        if len(term) > 2 and term not in stop_words
    }


def _retrieved_nodes(result: RetrieveEvidenceResult) -> list[dict[str, object]]:
    return [node.model_dump(mode="json") for node in result.retrieved_nodes]


def _task_scoped_filing_queries(query: str, state: AgentState) -> list[str]:
    if state.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        return [
            " ".join(
                [
                    query,
                    (
                        "net sales services product segment iPhone Mac iPad wearables "
                        "revenue demand installed base customer engagement channel inventory "
                        "pricing mix strategy operating income growth"
                    ),
                ]
            )
        ]
    if state.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        return [
            (
                "operating cash flow net cash provided by operating activities "
                "cash generated by operations"
            ),
            (
                "capital expenditures capex payments to acquire property plant equipment "
                "investment intensity"
            ),
            "repurchases of common stock share repurchases buybacks capital return program",
            "dividends dividend equivalents cash dividends capital return",
            "debt maturities liquidity cash equivalents marketable securities capital resources",
        ]
    if state.task_type == ResearchTaskType.LATEST_EARNINGS_READOUT:
        return [
            " ".join(
                [
                    query,
                    (
                        "net sales revenue gross margin operating income services products "
                        "results of operations segment performance demand pricing mix"
                    ),
                ]
            )
        ]
    return [query]


def _task_scoped_metric_queries(query: str, state: AgentState) -> list[str]:
    if state.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        return [
            "operating cash flow net cash provided by operating activities",
            "capital expenditures capex payments to acquire property plant equipment",
            "repurchases of common stock share repurchases buybacks",
            "dividends dividend equivalents",
            "debt maturities liquidity cash equivalents marketable securities",
        ]
    if state.task_type == ResearchTaskType.LATEST_EARNINGS_READOUT:
        return [
            " ".join(
                [
                    query,
                    (
                        "net sales revenue gross margin gross profit operating income "
                        "results of operations services products segment"
                    ),
                ]
            )
        ]
    return [query]


def _task_scoped_filing_sections(sections: list[str], state: AgentState) -> list[str]:
    if state.task_type == ResearchTaskType.LATEST_EARNINGS_READOUT:
        operating_sections = [
            section
            for section in sections
            if section.strip().lower() not in {"risk factors", "market risk"}
        ]
        return _dedupe_sections([*operating_sections, "MD&A", "Net Sales", "Segment Information"])
    if state.task_type == ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE:
        return _dedupe_sections([*sections, "MD&A", "Business", "Segment Information"])
    if state.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        return _dedupe_sections(
            [*sections, "Liquidity and Capital Resources", "Cash Flow Statement"]
        )
    return sections


def _top_k_for_task_query(limit: int, state: AgentState) -> int:
    if state.task_type == ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION:
        return max(1, min(2, limit))
    return limit


def _dedupe_source_refs(source_refs: object) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    if not isinstance(source_refs, Iterable):
        return deduped
    for source_ref in source_refs:
        if not isinstance(source_ref, dict):
            continue
        key = (
            str(source_ref.get("source_id") or ""),
            str(source_ref.get("snippet") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source_ref)
    return deduped


def _dedupe_retrieved_nodes(nodes: object) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    if not isinstance(nodes, Iterable):
        return deduped
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_id = str(node.get("node_id") or "")
        text = str(node.get("text") or "")
        key = node_id or text
        if key in seen:
            continue
        seen.add(key)
        deduped.append(node)
    return deduped


def _fallback_status_from_results(results: list[RetrieveEvidenceResult]) -> str:
    if any(result.fallback_status.value == "degraded" for result in results):
        return "degraded"
    if all(result.fallback_status.value == "empty" for result in results):
        return "empty"
    return "none"


def _source_id_for_metric(metric: str, source_refs: list[dict[str, object]]) -> str:
    metric_terms = _content_terms(metric)
    best_source_id = str(source_refs[0].get("source_id") or "unknown")
    best_score = -1
    for source_ref in source_refs:
        snippet_terms = _content_terms(str(source_ref.get("snippet") or ""))
        score = len(metric_terms & snippet_terms)
        if score > best_score:
            best_source_id = str(source_ref.get("source_id") or best_source_id)
            best_score = score
    return best_source_id


def _companyfacts_source_refs(
    *,
    run_id: str,
    metrics: list[str],
    facts_by_metric: Mapping[str, Mapping[str, object]],
) -> list[dict[str, object]]:
    source_refs: list[dict[str, object]] = []
    for metric in metrics:
        normalized_metric = _normalize_metric_name(metric)
        fact = facts_by_metric.get(normalized_metric)
        if not fact:
            continue
        source_refs.append(_companyfacts_source_ref(run_id, normalized_metric, fact))
    return source_refs


def _companyfacts_source_ref(
    run_id: str,
    normalized_metric: str,
    fact: Mapping[str, object],
) -> dict[str, object]:
    concept = str(fact.get("concept") or normalized_metric)
    value = fact.get("value")
    unit = str(fact.get("unit") or "").strip()
    period = str(fact.get("period") or "latest period")
    filed = str(fact.get("filed") or "unknown filing date")
    accession_number = fact.get("accession_number")
    metric_slug = _metric_slug(normalized_metric)
    value_text = f"{value} {unit}".strip()
    return {
        "source_id": f"{run_id}:sec_companyfacts:{metric_slug}",
        "section": "SEC companyfacts",
        "snippet": (
            f"SEC companyfacts {concept} reports {normalized_metric} of "
            f"{value_text} for {period} filed {filed}."
        ),
        "citation_status": "supported",
        "filing_type": fact.get("form"),
        "filing_date": fact.get("filed"),
        "accession_number": accession_number,
    }


def _metric_evidence_record(
    metric: str,
    period: str,
    source_refs: list[dict[str, object]],
    facts_by_metric: Mapping[str, Mapping[str, object]],
) -> dict[str, object]:
    normalized_metric = _normalize_metric_name(metric)
    fact = facts_by_metric.get(normalized_metric)
    if fact:
        source_id = _companyfacts_source_id_from_refs(normalized_metric, source_refs)
        if source_id is None:
            source_id = _source_id_for_metric(metric, source_refs)
    else:
        source_id = _source_id_for_metric(metric, source_refs)
    source_ref = _source_ref_by_id(source_id, source_refs)
    record: dict[str, object] = {
        "metric": metric,
        "normalized_metric": normalized_metric,
        "period": period,
        "source_id": source_id,
        "section": str(source_ref.get("section") or "Unknown") if source_ref else "Unknown",
        "snippet": str(source_ref.get("snippet") or "") if source_ref else "",
    }
    if fact:
        record.update(
            {
                "value": fact.get("value"),
                "unit": fact.get("unit"),
                "fact_period": fact.get("period"),
                "fy": fact.get("fy"),
                "fp": fact.get("fp"),
                "form": fact.get("form"),
                "filed": fact.get("filed"),
                "accession_number": fact.get("accession_number"),
                "taxonomy": fact.get("taxonomy"),
                "concept": fact.get("concept"),
                "label": fact.get("label"),
                "source": "sec_companyfacts",
            }
        )
    return record


def _companyfacts_source_id_from_refs(
    normalized_metric: str,
    source_refs: list[dict[str, object]],
) -> str | None:
    suffix = f":sec_companyfacts:{_metric_slug(normalized_metric)}"
    for source_ref in source_refs:
        source_id = str(source_ref.get("source_id") or "")
        if source_id.endswith(suffix):
            return source_id
    return None


def _metric_slug(normalized_metric: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalized_metric).strip("-") or "metric"


def _source_ref_by_id(
    source_id: str,
    source_refs: list[dict[str, object]],
) -> dict[str, object] | None:
    for source_ref in source_refs:
        if str(source_ref.get("source_id") or "") == source_id:
            return source_ref
    return None


def _facts_by_metric(state: AgentState) -> dict[str, Mapping[str, object]]:
    metrics = state.evidence_memory.facts.get("metrics")
    if not isinstance(metrics, list):
        return {}
    facts: dict[str, Mapping[str, object]] = {}
    for metric in metrics:
        if not isinstance(metric, Mapping):
            continue
        name = _normalize_metric_name(str(metric.get("name") or ""))
        if name:
            facts[name] = metric
    return facts


def _dedupe_sections(sections: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for section in sections:
        key = section.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(section)
    return deduped


def _extract_business_signal_records(
    source_refs: list[dict[str, object]],
    requested_signal_types: list[str],
) -> list[dict[str, object]]:
    requested_types = {
        _normalize_signal_type(signal_type)
        for signal_type in requested_signal_types
        if signal_type.strip()
    }
    if not requested_types:
        requested_types = set(_BUSINESS_SIGNAL_KEYWORDS)

    records: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for source_ref in source_refs:
        source_id = str(source_ref.get("source_id") or "").strip()
        snippet = str(source_ref.get("snippet") or "").strip()
        if not source_id or not snippet:
            continue
        for sentence in _signal_candidate_sentences(snippet):
            matched_types = _matched_signal_types(sentence, requested_types)
            for signal_type in matched_types:
                key = (source_id, signal_type, sentence.lower())
                if key in seen:
                    continue
                seen.add(key)
                records.append(
                    {
                        "signal_type": signal_type,
                        "signal": _signal_title(signal_type, sentence),
                        "summary": sentence,
                        "source_id": source_id,
                        "section": str(source_ref.get("section") or "Unknown"),
                        "snippet": sentence,
                        "citation_status": str(source_ref.get("citation_status") or "unverified"),
                    }
                )
    return records


def _normalize_signal_type(signal_type: str) -> str:
    return re.sub(r"\s+", "_", signal_type.strip().lower())


def _signal_candidate_sentences(snippet: str) -> list[str]:
    sentences = [
        sentence.strip(" \n\t\r;:")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", snippet)
        if sentence.strip(" \n\t\r;:")
    ]
    return sentences or [snippet]


def _matched_signal_types(sentence: str, requested_types: set[str]) -> list[str]:
    normalized_sentence = sentence.lower()
    matched_types = [
        signal_type
        for signal_type in sorted(requested_types)
        if any(keyword in normalized_sentence for keyword in _keywords_for_signal(signal_type))
    ]
    return matched_types


def _keywords_for_signal(signal_type: str) -> tuple[str, ...]:
    return _BUSINESS_SIGNAL_KEYWORDS.get(signal_type, ())


def _signal_title(signal_type: str, sentence: str) -> str:
    label = signal_type.replace("_", " ").title()
    first_clause = re.split(r",| because | while | and ", sentence, maxsplit=1)[0].strip()
    return f"{label}: {first_clause[:96]}"


def _preferred_metric_sections(metrics: list[str]) -> list[str]:
    joined = " ".join(metrics).lower()
    if any(term in joined for term in ("cash", "capex", "buyback", "repurchase", "debt")):
        return ["Liquidity and Capital Resources", "Cash Flow Statement"]
    if any(term in joined for term in ("revenue", "margin", "income", "expense")):
        return ["MD&A", "Net Sales", "Segment Information"]
    return ["MD&A", "Financial Statements"]


def _sec_json_transport(url: str, timeout_seconds: float) -> dict[str, object]:
    request = url_request.Request(
        url,
        headers={"User-Agent": "spring-alpha-research-service/0.1 contact@example.com"},
    )
    with url_request.urlopen(request, timeout=timeout_seconds) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("SEC response must be a JSON object")
    return decoded


def _yahoo_json_transport(url: str, timeout_seconds: float) -> dict[str, object]:
    request = url_request.Request(
        url,
        headers={
            "User-Agent": "spring-alpha-research-service/0.1",
            "Accept": "application/json",
        },
    )
    with url_request.urlopen(request, timeout=timeout_seconds) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Yahoo response must be a JSON object")
    return decoded


def _first_quote_summary_result(payload: Mapping[str, object]) -> dict[str, object]:
    quote_summary = payload.get("quoteSummary")
    if not isinstance(quote_summary, dict):
        return {}
    results = quote_summary.get("result")
    if not isinstance(results, list) or not results:
        return {}
    first = results[0]
    return first if isinstance(first, dict) else {}


def _yahoo_raw_value(value: object) -> str:
    if isinstance(value, dict):
        raw = value.get("raw") or value.get("fmt") or value.get("longFmt")
        return str(raw or "").strip()
    return str(value or "").strip()


def _latest_metric_record(
    companyfacts: Mapping[str, object],
    requested_metric: str,
    period: str,
) -> dict[str, object] | None:
    normalized_metric = _normalize_metric_name(requested_metric)
    concepts = _CONCEPTS_BY_METRIC.get(normalized_metric, [])
    facts = companyfacts.get("facts")
    if not isinstance(facts, dict):
        return None
    for taxonomy, taxonomy_payload in facts.items():
        if not isinstance(taxonomy_payload, dict):
            continue
        for concept in concepts:
            concept_payload = taxonomy_payload.get(concept)
            if not isinstance(concept_payload, dict):
                continue
            unit, fact = _latest_fact(concept_payload, period)
            if fact is None:
                continue
            return {
                "name": normalized_metric,
                "label": str(concept_payload.get("label") or concept),
                "value": fact.get("val"),
                "unit": unit,
                "period": _fact_period(fact),
                "fy": fact.get("fy"),
                "fp": fact.get("fp"),
                "form": fact.get("form"),
                "filed": fact.get("filed"),
                "accession_number": fact.get("accn"),
                "taxonomy": str(taxonomy),
                "concept": concept,
            }
    return None


def _filter_metric_records_to_reporting_cohort(
    records: list[dict[str, object]],
    period: str,
) -> list[dict[str, object]]:
    normalized_period = period.lower()
    if normalized_period not in {"latest_quarter", "quarterly", "latest_annual", "annual", "fy"}:
        return records
    if len(records) < 2:
        return records
    anchor = max(records, key=_metric_record_sort_key)
    anchor_fy = anchor.get("fy")
    anchor_fp = str(anchor.get("fp") or "")
    if anchor_fy is None or not anchor_fp:
        return records
    return [
        record
        for record in records
        if record.get("fy") == anchor_fy and str(record.get("fp") or "") == anchor_fp
    ]


def _metric_record_sort_key(record: Mapping[str, object]) -> tuple[int, str]:
    fy = record.get("fy")
    fiscal_year = int(fy) if isinstance(fy, int | float) else 0
    return fiscal_year, str(record.get("filed") or "")


def _latest_fact(
    concept_payload: Mapping[str, object],
    period: str,
) -> tuple[str, dict[str, object] | None]:
    units = concept_payload.get("units")
    if not isinstance(units, dict):
        return "", None
    candidate_units = ["USD", "shares", "pure", *[str(unit) for unit in units]]
    for unit in candidate_units:
        unit_facts = units.get(unit)
        if not isinstance(unit_facts, list):
            continue
        facts = [
            fact
            for fact in unit_facts
            if isinstance(fact, dict)
            and fact.get("val") is not None
            and _matches_period(fact, period)
        ]
        if not facts:
            continue
        return unit, max(facts, key=lambda fact: _fact_sort_key(fact, period))
    return "", None


def _matches_period(fact: Mapping[str, object], period: str) -> bool:
    normalized = period.lower()
    if normalized in {"latest_quarter", "quarterly"}:
        return str(fact.get("form", "")).upper() == "10-Q" and str(
            fact.get("fp", "")
        ).upper().startswith("Q")
    if normalized in {"latest_annual", "annual", "fy"}:
        return str(fact.get("form", "")).upper() == "10-K"
    return True


def _fact_sort_key(fact: Mapping[str, object], period: str = "") -> tuple[int, str, int]:
    fy = fact.get("fy")
    fiscal_year = int(fy) if isinstance(fy, int | float) else 0
    filed = str(fact.get("filed") or "")
    return fiscal_year, filed, _quarterly_frame_score(fact, period)


def _quarterly_frame_score(fact: Mapping[str, object], period: str) -> int:
    if period.lower() not in {"latest_quarter", "quarterly"}:
        return 0
    frame = str(fact.get("frame") or "").upper()
    fp = str(fact.get("fp") or "").upper()
    if frame and re.fullmatch(r"(?:CY|FY)?\d{4}Q[1-4]", frame):
        return 2
    if frame and fp and frame.endswith(fp):
        return 1
    return 0


def _fact_period(fact: Mapping[str, object]) -> str | None:
    fy = fact.get("fy")
    fp = fact.get("fp")
    if fy is None or fp is None:
        return None
    return f"{fy}{fp}"


def _normalize_metric_name(metric: str) -> str:
    spaced = re.sub(r"(?<!^)(?=[A-Z])", " ", metric.strip())
    normalized = re.sub(r"\s+", " ", spaced.lower().replace("_", " "))
    return _METRIC_ALIASES.get(normalized, normalized)


_METRIC_ALIASES: dict[str, str] = {
    "total revenue": "revenue",
    "total revenues": "revenue",
    "net sales": "revenue",
    "gross profit": "gross profit",
    "gross margin": "gross margin",
    "operating income": "operating income",
    "operating income loss": "operating income",
    "operating cashflow": "operating cash flow",
    "operating cash flows": "operating cash flow",
    "capital expenditure": "capital expenditures",
    "capital expenditures": "capital expenditures",
    "share buybacks": "buybacks",
    "stock buybacks": "buybacks",
}


_CONCEPTS_BY_METRIC: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "gross margin": ["GrossProfit"],
    "gross profit": ["GrossProfit"],
    "operating income": ["OperatingIncomeLoss"],
    "net income": ["NetIncomeLoss"],
    "operating cash flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "capital expenditures": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpendituresIncurredButNotYetPaid",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "CapitalExpendituresIncurredButNotYetPaid",
    ],
    "buybacks": [
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfEquity",
    ],
    "share repurchases": [
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfEquity",
    ],
}

_BUSINESS_SIGNAL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "product": (
        "service",
        "services",
        "product",
        "hardware",
        "software",
        "platform",
        "device",
    ),
    "segment": (
        "segment",
        "enterprise",
        "consumer",
        "geography",
        "geographic",
        "region",
    ),
    "demand": (
        "demand",
        "engagement",
        "customer",
        "installed base",
        "growth",
        "grew",
        "increased",
    ),
    "pricing": (
        "pricing",
        "price",
        "mix",
        "margin",
        "gross margin",
        "favorable mix",
    ),
    "strategy": (
        "strategy",
        "investment",
        "launch",
        "ecosystem",
        "initiative",
        "expand",
    ),
    "risk": (
        "risk",
        "competition",
        "competitive",
        "supply",
        "foreign exchange",
        "constraint",
        "constraints",
        "pressure",
    ),
    "customer": (
        "customer",
        "customers",
        "installed base",
        "engagement",
        "retention",
    ),
    "geography": (
        "geography",
        "geographic",
        "region",
        "international",
        "foreign exchange",
    ),
}


_KNOWN_CIK_BY_TICKER: dict[str, int] = {
    "AAPL": 320193,
    "MSFT": 789019,
    "GOOGL": 1652044,
    "GOOG": 1652044,
    "AMZN": 1018724,
    "META": 1326801,
    "NVDA": 1045810,
    "TSLA": 1318605,
}
