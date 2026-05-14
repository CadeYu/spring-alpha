import json
from collections.abc import Callable
from typing import Any

from langchain_core.tools import StructuredTool

from app.contracts.agent import AgentRequest, AgentState, ToolResult
from app.rag.langchain_tools import EvidencePackInput, create_evidence_pack_tool
from app.rag.llamaindex_pipeline import LlamaIndexRagPipeline


def create_agent_evidence_pack_tool(
    *,
    request: AgentRequest,
    state_getter: Callable[[], AgentState],
    state_setter: Callable[[AgentState], None],
    rag_pipeline: LlamaIndexRagPipeline | None,
    summary: str,
    run_domain_tool: Callable[
        [AgentState, str, str, ToolResult, dict[str, Any] | None],
        tuple[AgentState, str],
    ],
) -> StructuredTool:
    def build_evidence_pack(
        focus: str | None = None,
        top_k: int = 5,
    ) -> str:
        if rag_pipeline is None:
            result = ToolResult.empty(
                data={"evidence_pack": None, "source_refs": []},
                degraded_reason="RAG pipeline is not available for evidence pack collection.",
            )
        else:
            evidence_pack_tool = create_evidence_pack_tool(
                rag_pipeline=rag_pipeline,
                run_id=request.run_id,
                ticker=request.ticker,
                task_type=request.task_type,
            )
            raw_payload = evidence_pack_tool.invoke({"focus": focus, "top_k": top_k})
            data = json.loads(raw_payload)
            data = _with_metric_facts(data, state_getter())
            source_refs = source_refs_from_evidence_pack_result(data)
            evidence_pack = data.get("evidence_pack")
            if isinstance(evidence_pack, dict) and evidence_pack.get("retrieval_status") == "empty":
                result = ToolResult.empty(
                    data=data,
                    degraded_reason="No evidence pack filing evidence matched the task template.",
                )
            else:
                result = ToolResult.ok(data=data, source_refs=source_refs)
        next_state, payload = run_domain_tool(
            state_getter(),
            "build_evidence_pack",
            summary,
            result,
            {"focus": focus, "top_k": top_k},
        )
        state_setter(next_state)
        return payload

    return StructuredTool.from_function(
        build_evidence_pack,
        name="build_evidence_pack",
        description=(
            "Build one compact Evidence Pack for the current research task from fixed "
            "SEC filing query templates."
        ),
        args_schema=EvidencePackInput,
    )


def source_refs_from_evidence_pack_result(data: dict[str, Any]) -> list[dict[str, Any]]:
    source_refs = data.get("source_refs")
    if isinstance(source_refs, list):
        return [source_ref for source_ref in source_refs if isinstance(source_ref, dict)]
    return []


def _with_metric_facts(data: dict[str, Any], state: AgentState) -> dict[str, Any]:
    evidence_pack = data.get("evidence_pack")
    if not isinstance(evidence_pack, dict):
        return data
    enriched_pack = {
        **evidence_pack,
        "metric_facts": _metric_facts_from_state(state),
    }
    if not enriched_pack.get("filing_evidence"):
        enriched_pack.pop("filing_evidence", None)
    enriched_data = {
        **data,
        "evidence_pack": enriched_pack,
    }
    if not enriched_data.get("source_refs"):
        enriched_data.pop("source_refs", None)
    return enriched_data


def _metric_facts_from_state(state: AgentState) -> list[dict[str, Any]]:
    return [
        *_sec_companyfacts_metric_facts(state.evidence_memory.facts),
        *_profile_facts(state.evidence_memory.facts),
        *_metric_evidence_facts(state.evidence_memory.metric_evidence),
    ]


def _sec_companyfacts_metric_facts(facts: dict[str, Any]) -> list[dict[str, Any]]:
    metrics = facts.get("metrics")
    if not isinstance(metrics, list):
        return []
    metric_facts = []
    for metric in metrics:
        if not isinstance(metric, dict):
            continue
        name = _optional_str(metric.get("name"))
        if not name:
            continue
        metric_facts.append(
            _compact_dict(
                {
                "source_type": "sec_companyfacts",
                "metric": name,
                "value": metric.get("value"),
                "unit": _optional_str(metric.get("unit")),
                "period": _optional_str(metric.get("period")),
                }
            )
        )
    return metric_facts


def _profile_facts(facts: dict[str, Any]) -> list[dict[str, Any]]:
    business_summary = (
        _optional_str(facts.get("business_summary"))
        or _optional_str(facts.get("businessSummary"))
        or _optional_str(facts.get("market_business_summary"))
        or _optional_str(facts.get("marketBusinessSummary"))
    )
    if not business_summary:
        return []
    return [
        _compact_dict({
            "source_type": "yahoo_profile",
            "company_name": _optional_str(facts.get("company_name")),
            "business_summary": business_summary,
            "sector": _optional_str(facts.get("sector")),
            "industry": _optional_str(facts.get("industry")),
            "security_type": _optional_str(facts.get("security_type")),
            "profile_source": _optional_str(facts.get("profile_source")),
        })
    ]


def _metric_evidence_facts(metric_evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    facts = []
    seen_source_ids: set[str] = set()
    for record in metric_evidence:
        metric = _optional_str(record.get("metric") or record.get("normalized_metric"))
        source_id = _optional_str(record.get("source_id"))
        if not metric or not source_id:
            continue
        if source_id in seen_source_ids:
            continue
        seen_source_ids.add(source_id)
        facts.append(
            _compact_dict(
                {
                "source_type": "metric_evidence",
                "metric": metric,
                "source_id": source_id,
                }
            )
        )
    return facts


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}
