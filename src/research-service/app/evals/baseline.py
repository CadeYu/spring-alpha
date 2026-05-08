import json
from collections.abc import Callable
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.agents.bounded_workflow import BoundedAgentWorkflow
from app.contracts.agent import AgentRequest, AgentRunStatus
from app.contracts.research_task import ResearchTaskType
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline


class RetrievalExperimentStrategy(StrEnum):
    HYBRID_SEMANTIC_LEXICAL = "hybrid_semantic_lexical_retrieval"
    SECTION_AWARE_LEXICAL = "section_aware_lexical_retrieval"
    NO_SECTION_FILTER = "no_section_filter_lexical_retrieval"
    NO_QUERY_EXPANSION = "no_query_expansion_lexical_retrieval"


PipelineFactory = Callable[[RetrievalExperimentStrategy], LlamaIndexRagPipeline]


class RagEvalMetricFormat(StrEnum):
    RATIO = "ratio"
    MILLISECONDS = "milliseconds"
    USD = "usd"


class RagEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    ticker: str = Field(min_length=1, max_length=16)
    filing_ref: str | None = None
    task_type: ResearchTaskType
    query: str
    expected_sections: list[str]
    expected_terms: list[str] = Field(default_factory=list)
    bad_sections: list[str] = Field(default_factory=list)


class RagEvalDataset(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    name: str
    cases: list[RagEvalCase]


class RagEvalFilingCorpus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filings: list[FilingDocument]


class RagBaselineMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retrieval_recall_at_5: float
    context_precision: float
    faithfulness: float
    answer_term_coverage: float
    citation_coverage: float
    fallback_rate: float
    total_latency_ms: int
    cost_usd: float
    expected_section_hit_rate: float = 0.0
    expected_term_hit_rate: float = 0.0
    top_1_section_correctness: float = 0.0
    empty_retrieval_rate: float = 0.0
    bad_section_leak_rate: float = 0.0
    average_snippet_length: float = 0.0
    max_source_payload_bytes: int = 0


class RagBaselineEvalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    ticker: str
    task_type: ResearchTaskType
    query: str
    expected_sections: list[str]
    expected_terms: list[str] = Field(default_factory=list)
    bad_sections: list[str] = Field(default_factory=list)
    retrieved_node_ids: list[str]
    retrieved_sections: list[str]
    metrics: RagBaselineMetrics


class RagBaselineEvalArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1.0"
    stage: str = "stage_0_baseline"
    system_under_test: str = "bounded_workflow_placeholder"
    baseline_label: str = "current_placeholder_retrieval"
    dataset_name: str
    records: list[RagBaselineEvalRecord]
    aggregate_metrics: RagBaselineMetrics


class RagProductionReadinessThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_expected_section_hit_rate: float = 1.0
    min_expected_term_hit_rate: float = 1.0
    min_top_1_section_correctness: float = 1.0
    max_empty_retrieval_rate: float = 0.0
    max_bad_section_leak_rate: float = 0.0
    min_max_source_payload_bytes: int = 1


class RagDashboardMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    key: str
    label: str
    value: float
    format: RagEvalMetricFormat


class RagDashboardCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    case_id: str = Field(alias="caseId")
    ticker: str
    task_type: str = Field(alias="taskType")
    retrieved_sections: list[str] = Field(alias="retrievedSections")
    metrics: list[RagDashboardMetric]


class RagDashboardArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    stage: str
    stage_label: str = Field(alias="stageLabel")
    dataset_name: str = Field(alias="datasetName")
    system_under_test: str = Field(alias="systemUnderTest")
    baseline_label: str = Field(alias="baselineLabel")
    metrics: list[RagDashboardMetric]
    cases: list[RagDashboardCaseResult]
    stage_comparisons: list["RagDashboardArtifact"] = Field(alias="stageComparisons")
    limitations: list[str]


def build_stage0_eval_dataset() -> RagEvalDataset:
    return RagEvalDataset(
        name="stage0_mvp_retrieval_baseline",
        cases=[
            RagEvalCase(
                case_id="stage0_latest_earnings_tsla",
                ticker="TSLA",
                task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
                query="latest earnings MD&A financial statements guidance",
                expected_sections=["MD&A"],
                expected_terms=["earnings", "financial", "guidance"],
            ),
            RagEvalCase(
                case_id="stage0_business_drivers_aapl",
                ticker="AAPL",
                task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
                query="products segments demand pricing customers strategy",
                expected_sections=["Business Drivers"],
                expected_terms=["products", "segments", "strategy"],
            ),
            RagEvalCase(
                case_id="stage0_cash_flow_msft",
                ticker="MSFT",
                task_type=ResearchTaskType.CASH_FLOW_CAPITAL_ALLOCATION,
                query="cash flow capex buybacks debt liquidity",
                expected_sections=["Cash Flow and Capital Allocation"],
                expected_terms=["cash flow", "capex", "liquidity"],
            ),
        ],
    )


def build_live_pipeline_eval_dataset() -> RagEvalDataset:
    return load_live_rag_eval_dataset()


def build_hard_live_pipeline_eval_dataset() -> RagEvalDataset:
    return load_live_rag_eval_dataset(_hard_dataset_path())


def load_live_rag_eval_dataset(
    dataset_path: Path | None = None,
) -> RagEvalDataset:
    path = dataset_path or _default_dataset_path()
    with path.open(encoding="utf-8") as dataset_file:
        payload = json.load(dataset_file)
    return RagEvalDataset.model_validate(payload)


def load_live_rag_filing_corpus(
    dataset: RagEvalDataset,
    *,
    dataset_path: Path | None = None,
) -> RagEvalFilingCorpus:
    path = dataset_path or _default_dataset_path()
    filing_dir = path.parent / "filings"
    filing_refs = sorted({case.filing_ref for case in dataset.cases if case.filing_ref})
    filings = [
        _filing_document_from_ref(filing_dir=filing_dir, filing_ref=filing_ref)
        for filing_ref in filing_refs
        if filing_ref is not None
    ]
    return RagEvalFilingCorpus(filings=filings)


def run_stage0_baseline_eval(
    dataset: RagEvalDataset,
    *,
    workflow: BoundedAgentWorkflow | None = None,
) -> RagBaselineEvalArtifact:
    agent = workflow or BoundedAgentWorkflow()
    records = [_evaluate_case(agent, case) for case in dataset.cases]
    return RagBaselineEvalArtifact(
        dataset_name=dataset.name,
        records=records,
        aggregate_metrics=_average_metrics([record.metrics for record in records]),
    )


def run_live_pipeline_eval(
    dataset: RagEvalDataset,
    *,
    corpus: RagEvalFilingCorpus | None = None,
    strategy: RetrievalExperimentStrategy = RetrievalExperimentStrategy.SECTION_AWARE_LEXICAL,
    pipeline_factory: PipelineFactory | None = None,
) -> RagBaselineEvalArtifact:
    pipeline = pipeline_factory(strategy) if pipeline_factory else _pipeline_for_strategy(strategy)
    eval_corpus = corpus or load_live_rag_filing_corpus(dataset)
    for filing in eval_corpus.filings:
        pipeline.ingest_filing(filing)
    records = [_evaluate_live_pipeline_case(pipeline, case) for case in dataset.cases]
    return RagBaselineEvalArtifact(
        stage="stage_1_live_pipeline",
        system_under_test="llamaindex_request_pipeline",
        baseline_label=strategy.value,
        dataset_name=dataset.name,
        records=records,
        aggregate_metrics=_average_metrics([record.metrics for record in records]),
    )


def run_live_pipeline_experiment_suite(
    dataset: RagEvalDataset,
    *,
    corpus: RagEvalFilingCorpus | None = None,
    pipeline_factory: PipelineFactory | None = None,
) -> list[RagBaselineEvalArtifact]:
    eval_corpus = corpus or load_live_rag_filing_corpus(dataset)
    return [
        run_live_pipeline_eval(
            dataset,
            corpus=eval_corpus,
            strategy=strategy,
            pipeline_factory=pipeline_factory,
        )
        for strategy in RetrievalExperimentStrategy
    ]


def build_stage1_hard_dashboard_artifact(
    *,
    pipeline_factory: PipelineFactory | None = None,
) -> RagDashboardArtifact:
    suite = build_stage1_hard_eval_suite(pipeline_factory=pipeline_factory)
    return build_stage1_hard_dashboard_artifact_from_suite(suite)


def build_stage1_hard_dashboard_artifact_from_suite(
    suite: list[RagBaselineEvalArtifact],
) -> RagDashboardArtifact:
    artifacts_by_label = {artifact.baseline_label: artifact for artifact in suite}
    primary = artifacts_by_label[RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL.value]
    comparisons = [
        _dashboard_artifact_from_eval_artifact(
            artifact,
            stage="stage_1_hard_rag",
            stage_label=_strategy_stage_label(artifact.baseline_label),
            comparisons=[],
            limitations=[],
        )
        for artifact in suite
        if artifact.baseline_label != primary.baseline_label
    ]
    return _dashboard_artifact_from_eval_artifact(
        primary,
        stage="stage_1_hard_rag",
        stage_label="Stage 1 Hard RAG",
        comparisons=comparisons,
        limitations=[
            "Generated from the local hard RAG eval suite.",
            (
                "Hybrid vector retrieval uses a deterministic local embedding backend, "
                "not provider-backed embeddings."
            ),
            "Artifact is a reproducible regression baseline, not a production-scale benchmark.",
        ],
    )


def build_stage1_hard_eval_suite(
    *,
    pipeline_factory: PipelineFactory | None = None,
) -> list[RagBaselineEvalArtifact]:
    dataset = build_hard_live_pipeline_eval_dataset()
    return run_live_pipeline_experiment_suite(dataset, pipeline_factory=pipeline_factory)


def build_stage1_hard_primary_eval_artifact(
    *,
    pipeline_factory: PipelineFactory | None = None,
) -> RagBaselineEvalArtifact:
    suite = build_stage1_hard_eval_suite(pipeline_factory=pipeline_factory)
    artifacts_by_label = {artifact.baseline_label: artifact for artifact in suite}
    return artifacts_by_label[RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL.value]


def write_stage1_hard_dashboard_artifact(
    target_path: Path,
    *,
    pipeline_factory: PipelineFactory | None = None,
) -> Path:
    artifact = build_stage1_hard_dashboard_artifact(pipeline_factory=pipeline_factory)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        artifact.model_dump_json(by_alias=True, indent=2),
        encoding="utf-8",
    )
    return target_path


def assert_rag_production_readiness(
    artifact: RagBaselineEvalArtifact,
    *,
    thresholds: RagProductionReadinessThresholds | None = None,
) -> None:
    gate = thresholds or RagProductionReadinessThresholds()
    metrics = artifact.aggregate_metrics
    failures: list[str] = []

    _check_minimum(
        failures,
        name="expected_section_hit_rate",
        actual=metrics.expected_section_hit_rate,
        minimum=gate.min_expected_section_hit_rate,
    )
    _check_minimum(
        failures,
        name="expected_term_hit_rate",
        actual=metrics.expected_term_hit_rate,
        minimum=gate.min_expected_term_hit_rate,
    )
    _check_minimum(
        failures,
        name="top_1_section_correctness",
        actual=metrics.top_1_section_correctness,
        minimum=gate.min_top_1_section_correctness,
    )
    _check_maximum(
        failures,
        name="empty_retrieval_rate",
        actual=metrics.empty_retrieval_rate,
        maximum=gate.max_empty_retrieval_rate,
    )
    _check_maximum(
        failures,
        name="bad_section_leak_rate",
        actual=metrics.bad_section_leak_rate,
        maximum=gate.max_bad_section_leak_rate,
    )
    _check_minimum(
        failures,
        name="max_source_payload_bytes",
        actual=float(metrics.max_source_payload_bytes),
        minimum=float(gate.min_max_source_payload_bytes),
    )

    if failures:
        joined_failures = "; ".join(failures)
        raise AssertionError(
            f"RAG production readiness gate failed for {artifact.stage} "
            f"{artifact.baseline_label}: {joined_failures}"
        )


def _evaluate_case(
    workflow: BoundedAgentWorkflow,
    case: RagEvalCase,
) -> RagBaselineEvalRecord:
    result = workflow.run(
        AgentRequest(
            run_id=case.case_id,
            ticker=case.ticker,
            task_type=case.task_type,
        )
    )
    final_report = result.final_report or {}
    retrieval_records = final_report.get("retrieval_records", [])
    nodes = _retrieved_nodes(retrieval_records)
    retrieved_sections = [str(node.get("section", "")) for node in nodes]
    expected_sections = set(case.expected_sections)
    matched_nodes = [node for node in nodes if str(node.get("section", "")) in expected_sections]
    top_5_sections = {str(node.get("section", "")) for node in nodes[:5]}
    matched_expected_sections = expected_sections.intersection(top_5_sections)
    citation_nodes = [node for node in nodes if node.get("citation_status")]
    answer_text = _final_report_text(final_report)
    answer_term_coverage = _answer_term_coverage(answer_text, case.expected_terms)

    metrics = RagBaselineMetrics(
        retrieval_recall_at_5=_safe_ratio(
            len(matched_expected_sections),
            len(expected_sections),
        ),
        context_precision=_safe_ratio(len(matched_nodes), len(nodes)),
        faithfulness=answer_term_coverage,
        answer_term_coverage=answer_term_coverage,
        citation_coverage=_safe_ratio(len(citation_nodes), len(nodes)),
        fallback_rate=1.0 if result.status != AgentRunStatus.OK else 0.0,
        total_latency_ms=sum(_record_latency_ms(record) for record in retrieval_records),
        cost_usd=0.0,
    )

    return RagBaselineEvalRecord(
        case_id=case.case_id,
        ticker=case.ticker,
        task_type=case.task_type,
        query=case.query,
        expected_sections=case.expected_sections,
        expected_terms=case.expected_terms,
        retrieved_node_ids=[str(node.get("node_id", "")) for node in nodes],
        retrieved_sections=retrieved_sections,
        metrics=metrics,
    )


def _evaluate_live_pipeline_case(
    pipeline: LlamaIndexRagPipeline,
    case: RagEvalCase,
) -> RagBaselineEvalRecord:
    result = pipeline.retrieve_evidence(
        run_id=case.case_id,
        ticker=case.ticker,
        task_type=case.task_type,
        query=case.query,
        sections=case.expected_sections,
        top_k=5,
    )
    nodes = [
        {
            "node_id": node.node_id,
            "section": str(node.metadata.get("section", "")),
            "text": node.text,
        }
        for node in result.retrieved_nodes
    ]
    source_payload_bytes = [
        len(source_ref.model_dump_json().encode("utf-8")) for source_ref in result.source_refs
    ]
    snippets = [source_ref.snippet for source_ref in result.source_refs]
    retrieved_sections = [str(node.get("section", "")) for node in nodes]
    expected_sections = set(case.expected_sections)
    bad_sections = set(case.bad_sections)
    expected_terms = [term.lower() for term in case.expected_terms]
    joined_snippets = " ".join(snippets).lower()

    metrics = RagBaselineMetrics(
        retrieval_recall_at_5=_safe_ratio(
            len(expected_sections.intersection(set(retrieved_sections[:5]))),
            len(expected_sections),
        ),
        context_precision=_safe_ratio(
            len([section for section in retrieved_sections if section in expected_sections]),
            len(retrieved_sections),
        ),
        faithfulness=_term_hit_rate(joined_snippets, expected_terms),
        answer_term_coverage=_term_hit_rate(joined_snippets, expected_terms),
        citation_coverage=_safe_ratio(len(result.source_refs), len(result.retrieved_nodes)),
        fallback_rate=0.0,
        total_latency_ms=result.latency_ms,
        cost_usd=0.0,
        expected_section_hit_rate=1.0
        if expected_sections.intersection(set(retrieved_sections))
        else 0.0,
        expected_term_hit_rate=_term_hit_rate(joined_snippets, expected_terms),
        top_1_section_correctness=1.0
        if retrieved_sections and retrieved_sections[0] in expected_sections
        else 0.0,
        empty_retrieval_rate=0.0 if result.retrieved_nodes else 1.0,
        bad_section_leak_rate=1.0 if bad_sections.intersection(set(retrieved_sections)) else 0.0,
        average_snippet_length=sum(len(snippet) for snippet in snippets) / len(snippets)
        if snippets
        else 0.0,
        max_source_payload_bytes=max(source_payload_bytes) if source_payload_bytes else 0,
    )

    return RagBaselineEvalRecord(
        case_id=case.case_id,
        ticker=case.ticker,
        task_type=case.task_type,
        query=case.query,
        expected_sections=case.expected_sections,
        expected_terms=case.expected_terms,
        bad_sections=case.bad_sections,
        retrieved_node_ids=[str(node.get("node_id", "")) for node in nodes],
        retrieved_sections=retrieved_sections,
        metrics=metrics,
    )


def _retrieved_nodes(retrieval_records: Any) -> list[dict[str, Any]]:
    if not isinstance(retrieval_records, list):
        return []
    nodes: list[dict[str, Any]] = []
    for record in retrieval_records:
        if not isinstance(record, dict):
            continue
        data = record.get("data", {})
        if not isinstance(data, dict):
            continue
        retrieved_nodes = data.get("retrieved_nodes", [])
        if isinstance(retrieved_nodes, list):
            nodes.extend(node for node in retrieved_nodes if isinstance(node, dict))
    return nodes


def _record_latency_ms(record: Any) -> int:
    if not isinstance(record, dict):
        return 0
    latency_ms = record.get("latency_ms", 0)
    return latency_ms if isinstance(latency_ms, int) else 0


def _final_report_text(final_report: dict[str, Any]) -> str:
    sections = final_report.get("sections", {})
    if not isinstance(sections, dict):
        return ""
    return " ".join(str(value) for value in sections.values()).lower()


def _answer_term_coverage(answer_text: str, expected_terms: list[str]) -> float:
    if not expected_terms:
        return 0.0
    matched_terms = [term for term in expected_terms if term.strip().lower() in answer_text]
    return _safe_ratio(len(matched_terms), len(expected_terms))


def _term_hit_rate(text: str, expected_terms: list[str]) -> float:
    if not expected_terms:
        return 0.0
    matched_terms = [term for term in expected_terms if term in text]
    return _safe_ratio(len(matched_terms), len(expected_terms))


def _safe_ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _check_minimum(
    failures: list[str],
    *,
    name: str,
    actual: float,
    minimum: float,
) -> None:
    if actual < minimum:
        failures.append(f"{name}={actual:.4f} below minimum {minimum:.4f}")


def _check_maximum(
    failures: list[str],
    *,
    name: str,
    actual: float,
    maximum: float,
) -> None:
    if actual > maximum:
        failures.append(f"{name}={actual:.4f} above maximum {maximum:.4f}")


def _average_metrics(metrics: list[RagBaselineMetrics]) -> RagBaselineMetrics:
    count = len(metrics)
    if count == 0:
        return RagBaselineMetrics(
            retrieval_recall_at_5=0.0,
            context_precision=0.0,
            faithfulness=0.0,
            answer_term_coverage=0.0,
            citation_coverage=0.0,
            fallback_rate=0.0,
            total_latency_ms=0,
            cost_usd=0.0,
        )

    return RagBaselineMetrics(
        retrieval_recall_at_5=sum(metric.retrieval_recall_at_5 for metric in metrics) / count,
        context_precision=sum(metric.context_precision for metric in metrics) / count,
        faithfulness=sum(metric.faithfulness for metric in metrics) / count,
        answer_term_coverage=sum(metric.answer_term_coverage for metric in metrics) / count,
        citation_coverage=sum(metric.citation_coverage for metric in metrics) / count,
        fallback_rate=sum(metric.fallback_rate for metric in metrics) / count,
        total_latency_ms=sum(metric.total_latency_ms for metric in metrics),
        cost_usd=sum(metric.cost_usd for metric in metrics),
        expected_section_hit_rate=sum(metric.expected_section_hit_rate for metric in metrics)
        / count,
        expected_term_hit_rate=sum(metric.expected_term_hit_rate for metric in metrics) / count,
        top_1_section_correctness=sum(metric.top_1_section_correctness for metric in metrics)
        / count,
        empty_retrieval_rate=sum(metric.empty_retrieval_rate for metric in metrics) / count,
        bad_section_leak_rate=sum(metric.bad_section_leak_rate for metric in metrics) / count,
        average_snippet_length=sum(metric.average_snippet_length for metric in metrics) / count,
        max_source_payload_bytes=max(metric.max_source_payload_bytes for metric in metrics),
    )


def _pipeline_for_strategy(strategy: RetrievalExperimentStrategy) -> LlamaIndexRagPipeline:
    if strategy == RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL:
        return LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
    if strategy == RetrievalExperimentStrategy.NO_SECTION_FILTER:
        return LlamaIndexRagPipeline(enable_section_filter=False)
    if strategy == RetrievalExperimentStrategy.NO_QUERY_EXPANSION:
        return LlamaIndexRagPipeline(enable_query_expansion=False)
    return LlamaIndexRagPipeline()


def _dashboard_artifact_from_eval_artifact(
    artifact: RagBaselineEvalArtifact,
    *,
    stage: str,
    stage_label: str,
    comparisons: list[RagDashboardArtifact],
    limitations: list[str],
) -> RagDashboardArtifact:
    return RagDashboardArtifact(
        stage=stage,
        stageLabel=stage_label,
        datasetName=artifact.dataset_name,
        systemUnderTest=artifact.system_under_test,
        baselineLabel=artifact.baseline_label,
        metrics=_dashboard_metrics(artifact.aggregate_metrics),
        cases=[
            RagDashboardCaseResult(
                caseId=record.case_id,
                ticker=record.ticker,
                taskType=record.task_type.value,
                retrievedSections=record.retrieved_sections,
                metrics=_dashboard_case_metrics(record.metrics),
            )
            for record in artifact.records
        ],
        stageComparisons=comparisons,
        limitations=limitations,
    )


def _dashboard_metrics(metrics: RagBaselineMetrics) -> list[RagDashboardMetric]:
    return [
        _dashboard_ratio(
            "expectedTermHitRate",
            "Expected Term Hit Rate",
            metrics.expected_term_hit_rate,
        ),
        _dashboard_ratio(
            "expectedSectionHitRate",
            "Expected Section Hit Rate",
            metrics.expected_section_hit_rate,
        ),
        _dashboard_ratio(
            "top1SectionCorrectness",
            "Top-1 Section Correctness",
            metrics.top_1_section_correctness,
        ),
        _dashboard_ratio(
            "emptyRetrievalRate",
            "Empty Retrieval Rate",
            metrics.empty_retrieval_rate,
        ),
        _dashboard_ratio(
            "badSectionLeakRate",
            "Bad Section Leak Rate",
            metrics.bad_section_leak_rate,
        ),
        _dashboard_ratio("contextPrecision", "Context Precision", metrics.context_precision),
        RagDashboardMetric(
            key="maxSourcePayloadBytes",
            label="Max Source Payload Bytes",
            value=float(metrics.max_source_payload_bytes),
            format=RagEvalMetricFormat.MILLISECONDS,
        ),
    ]


def _dashboard_case_metrics(metrics: RagBaselineMetrics) -> list[RagDashboardMetric]:
    return [
        _dashboard_ratio(
            "expectedTermHitRate",
            "Expected Term Hit Rate",
            metrics.expected_term_hit_rate,
        ),
        _dashboard_ratio(
            "top1SectionCorrectness",
            "Top-1 Section Correctness",
            metrics.top_1_section_correctness,
        ),
        _dashboard_ratio(
            "badSectionLeakRate",
            "Bad Section Leak Rate",
            metrics.bad_section_leak_rate,
        ),
    ]


def _dashboard_ratio(key: str, label: str, value: float) -> RagDashboardMetric:
    return RagDashboardMetric(
        key=key,
        label=label,
        value=value,
        format=RagEvalMetricFormat.RATIO,
    )


def _strategy_stage_label(strategy_label: str) -> str:
    labels = {
        RetrievalExperimentStrategy.SECTION_AWARE_LEXICAL.value: "Section-Aware Lexical",
        RetrievalExperimentStrategy.NO_SECTION_FILTER.value: "No Section Filter",
        RetrievalExperimentStrategy.NO_QUERY_EXPANSION.value: "No Query Expansion",
    }
    return labels.get(strategy_label, strategy_label)


def _default_dataset_path() -> Path:
    return Path(__file__).parent / "datasets" / "stage1_live_rag_cases.json"


def _hard_dataset_path() -> Path:
    return Path(__file__).parent / "datasets" / "stage1_hard_rag_cases.json"


def _filing_document_from_ref(*, filing_dir: Path, filing_ref: str) -> FilingDocument:
    path = filing_dir / f"{filing_ref}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Missing RAG eval filing fixture: {path}")
    ticker, filing_date, filing_type = _filing_metadata_from_ref(filing_ref)
    return FilingDocument(
        ticker=ticker,
        filing_type=filing_type,
        filing_date=filing_date,
        accession_number=filing_ref,
        text=path.read_text(encoding="utf-8"),
    )


def _filing_metadata_from_ref(filing_ref: str) -> tuple[str, str | None, str]:
    parts = filing_ref.split("_")
    ticker = parts[0].upper()
    year = parts[1] if len(parts) > 1 and parts[1].isdigit() else "2026"
    quarter = parts[2] if len(parts) > 2 and parts[2].startswith("q") else "q1"
    filing_type = parts[3].upper() if len(parts) > 3 else "10Q"
    quarter_dates = {
        "q1": f"{year}-03-31",
        "q2": f"{year}-06-30",
        "q3": f"{year}-09-30",
        "q4": f"{year}-12-31",
    }
    normalized_filing_type = filing_type.replace("10Q", "10-Q").replace("10K", "10-K")
    return ticker, quarter_dates.get(quarter), normalized_filing_type
