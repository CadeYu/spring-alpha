import json
import re
from collections.abc import Callable, Mapping
from urllib import request as url_request

from app.contracts.agent import AgentState, ToolResult
from app.contracts.tools import (
    BusinessSignalsInput,
    CitationVerificationInput,
    CompanyFactsInput,
    FilingSectionSearchInput,
    FinalizeReportInput,
    MetricEvidenceInput,
)
from app.rag.llamaindex_pipeline import LlamaIndexRagPipeline, RetrieveEvidenceResult

SecJsonTransport = Callable[[str, float], dict[str, object]]


class SecCompanyFactsProvider:
    def __init__(
        self,
        *,
        transport: SecJsonTransport | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._transport = transport or _sec_json_transport
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
        cik = int(ticker_record["cik_str"])
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
        found_metric_names = {str(record["name"]) for record in metric_records}
        missing_metrics = [
            metric
            for metric in requested_metrics
            if _normalize_metric_name(metric) not in found_metric_names
        ]
        return {
            "ticker": ticker.upper(),
            "company_name": companyfacts.get("entityName") or ticker_record.get("title"),
            "source": "sec_companyfacts",
            "period": period or "latest_quarter",
            "metrics": metric_records,
            "missing_metrics": missing_metrics,
        }

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


class DeterministicResearchToolService:
    def __init__(self, facts_provider: SecCompanyFactsProvider | None = None) -> None:
        self._facts_provider = facts_provider

    def get_company_facts(self, tool_input: CompanyFactsInput, state: AgentState) -> ToolResult:
        if self._facts_provider is not None:
            facts = self._facts_provider.fetch_company_facts(
                ticker=state.ticker,
                period=tool_input.period,
                metrics=tool_input.metrics,
            )
            missing_metrics = [
                str(metric) for metric in facts.get("missing_metrics", []) if str(metric)
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

    def verify_citations(
        self,
        tool_input: CitationVerificationInput,
        state: AgentState,
    ) -> ToolResult:
        records = [
            _score_claim_against_sources(claim, tool_input.source_refs)
            for claim in tool_input.claims
        ]
        source_refs = _source_refs_with_citation_status(tool_input.source_refs, records)
        return ToolResult.ok(
            data={
                "records": records,
                "claim_count": len(tool_input.claims),
                "source_ref_count": len(tool_input.source_refs),
            },
            source_refs=source_refs,
        )

    def finalize_report(self, tool_input: FinalizeReportInput, state: AgentState) -> ToolResult:
        return ToolResult.ok(
            data={
                "coverage": tool_input.coverage,
                "draft_sections": tool_input.draft_sections,
                "tool_name": "finalize_report",
                "ticker": state.ticker,
                "task_type": state.task_type.value,
            }
        )


class LlamaIndexResearchToolService(DeterministicResearchToolService):
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
        result = self._rag_pipeline.retrieve_evidence(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            query=tool_input.query,
            sections=tool_input.sections,
            top_k=tool_input.limit,
        )
        source_refs = [source_ref.model_dump(mode="json") for source_ref in result.source_refs]
        if not source_refs:
            return ToolResult.empty(
                data={"query": tool_input.query, "retrieved_nodes": []},
                degraded_reason="No filing section evidence matched the query.",
                latency_ms=result.latency_ms,
            )
        return ToolResult.ok(
            data={
                "query": tool_input.query,
                "retrieved_nodes": _retrieved_nodes(result),
                "fallback_status": result.fallback_status.value,
            },
            latency_ms=result.latency_ms,
            source_refs=source_refs,
        )

    def search_metric_evidence(
        self,
        tool_input: MetricEvidenceInput,
        state: AgentState,
    ) -> ToolResult:
        query = tool_input.query or " ".join(tool_input.metrics)
        result = self._rag_pipeline.retrieve_evidence(
            run_id=state.run_id,
            ticker=state.ticker,
            task_type=state.task_type,
            query=query,
            sections=_preferred_metric_sections(tool_input.metrics),
            top_k=5,
        )
        source_refs = [source_ref.model_dump(mode="json") for source_ref in result.source_refs]
        if not source_refs:
            return ToolResult.empty(
                data={"records": [], "retrieved_nodes": []},
                degraded_reason="No metric evidence matched the query.",
                latency_ms=result.latency_ms,
            )
        return ToolResult.ok(
            data={
                "records": [
                    {
                        "metric": metric,
                        "period": tool_input.period or "latest_quarter",
                        "source_id": source_refs[0]["source_id"],
                    }
                    for metric in tool_input.metrics
                ],
                "retrieved_nodes": _retrieved_nodes(result),
                "fallback_status": result.fallback_status.value,
            },
            latency_ms=result.latency_ms,
            source_refs=source_refs,
        )


def _score_claim_against_sources(
    claim: dict[str, object],
    source_refs: list[dict[str, object]],
) -> dict[str, object]:
    claim_terms = _content_terms(str(claim.get("text", "")))
    best_overlap = 0.0
    best_source_id: str | None = None
    for source_ref in source_refs:
        source_terms = _content_terms(str(source_ref.get("snippet", "")))
        if not claim_terms or not source_terms:
            continue
        overlap = len(claim_terms & source_terms) / len(claim_terms)
        if overlap > best_overlap:
            best_overlap = overlap
            best_source_id = str(source_ref.get("source_id", "unknown"))

    status = "missing"
    if best_overlap >= 0.75:
        status = "supported"
    elif best_overlap >= 0.35:
        status = "partial"

    return {
        "claim_id": str(claim.get("claim_id", "unknown")),
        "status": status,
        "support_score": round(best_overlap, 4),
        "source_id": best_source_id,
    }


def _source_refs_with_citation_status(
    source_refs: list[dict[str, object]],
    records: list[dict[str, object]],
) -> list[dict[str, object]]:
    best_status = _best_citation_status(records)
    return [
        {
            **source_ref,
            "citation_status": best_status,
        }
        for source_ref in source_refs
    ]


def _best_citation_status(records: list[dict[str, object]]) -> str:
    statuses = [str(record.get("status", "missing")) for record in records]
    if "supported" in statuses:
        return "supported"
    if "partial" in statuses:
        return "partial"
    return "missing"


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
        return unit, max(facts, key=_fact_sort_key)
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


def _fact_sort_key(fact: Mapping[str, object]) -> tuple[int, str]:
    fy = fact.get("fy")
    fiscal_year = int(fy) if isinstance(fy, int | float) else 0
    filed = str(fact.get("filed") or "")
    return fiscal_year, filed


def _fact_period(fact: Mapping[str, object]) -> str | None:
    fy = fact.get("fy")
    fp = fact.get("fp")
    if fy is None or fp is None:
        return None
    return f"{fy}{fp}"


def _normalize_metric_name(metric: str) -> str:
    return re.sub(r"\s+", " ", metric.strip().lower().replace("_", " "))


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
