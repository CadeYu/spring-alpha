from pathlib import Path

from app.evals.baseline import (
    RagBaselineEvalArtifact,
    RagEvalMetricFormat,
    RetrievalExperimentStrategy,
    build_hard_live_pipeline_eval_dataset,
    build_live_pipeline_eval_dataset,
    build_stage0_eval_dataset,
    build_stage1_hard_dashboard_artifact,
    load_live_rag_filing_corpus,
    run_live_pipeline_eval,
    run_live_pipeline_experiment_suite,
    run_stage0_baseline_eval,
    write_stage1_hard_dashboard_artifact,
)
from app.rag.llamaindex_pipeline import LlamaIndexRagPipeline


def test_stage0_eval_dataset_covers_mvp_tasks() -> None:
    dataset = build_stage0_eval_dataset()

    task_types = {case.task_type.value for case in dataset.cases}

    assert dataset.name == "stage0_mvp_retrieval_baseline"
    assert task_types == {
        "latest_earnings_readout",
        "business_driver_deep_dive",
        "cash_flow_capital_allocation",
    }
    assert all(case.expected_sections for case in dataset.cases)
    assert all(case.query for case in dataset.cases)


def test_stage0_baseline_eval_records_retrieval_metrics() -> None:
    dataset = build_stage0_eval_dataset()

    artifact = run_stage0_baseline_eval(dataset)

    assert isinstance(artifact, RagBaselineEvalArtifact)
    assert artifact.stage == "stage_0_baseline"
    assert artifact.system_under_test == "bounded_workflow_placeholder"
    assert artifact.baseline_label == "current_placeholder_retrieval"
    assert artifact.dataset_name == dataset.name
    assert len(artifact.records) == len(dataset.cases)
    assert _is_ratio(artifact.aggregate_metrics.retrieval_recall_at_5)
    assert _is_ratio(artifact.aggregate_metrics.context_precision)
    assert _is_ratio(artifact.aggregate_metrics.faithfulness)
    assert _is_ratio(artifact.aggregate_metrics.answer_term_coverage)
    assert _is_ratio(artifact.aggregate_metrics.citation_coverage)
    assert artifact.aggregate_metrics.fallback_rate == 0.0
    assert artifact.aggregate_metrics.total_latency_ms == 0
    assert artifact.aggregate_metrics.cost_usd == 0.0
    assert all(record.retrieved_node_ids for record in artifact.records)
    assert all(record.expected_terms for record in artifact.records)
    assert all(_is_ratio(record.metrics.faithfulness) for record in artifact.records)


def test_stage0_baseline_eval_artifact_is_json_safe() -> None:
    artifact = run_stage0_baseline_eval(build_stage0_eval_dataset())

    payload = artifact.model_dump(mode="json")

    assert payload["stage"] == "stage_0_baseline"
    assert payload["records"][0]["task_type"] in {
        "latest_earnings_readout",
        "business_driver_deep_dive",
        "cash_flow_capital_allocation",
    }
    assert payload["system_under_test"] == "bounded_workflow_placeholder"
    assert "retrieval_recall_at_5" in payload["aggregate_metrics"]
    assert "faithfulness" in payload["aggregate_metrics"]
    assert "answer_term_coverage" in payload["aggregate_metrics"]
    assert "total_latency_ms" in payload["aggregate_metrics"]


def test_live_pipeline_eval_records_retrieval_quality_and_payload_metrics() -> None:
    artifact = run_live_pipeline_eval(build_live_pipeline_eval_dataset())

    assert artifact.stage == "stage_1_live_pipeline"
    assert artifact.system_under_test == "llamaindex_request_pipeline"
    assert artifact.baseline_label == "section_aware_lexical_retrieval"
    assert artifact.aggregate_metrics.expected_section_hit_rate == 1.0
    assert artifact.aggregate_metrics.expected_term_hit_rate > 0.8
    assert artifact.aggregate_metrics.top_1_section_correctness == 1.0
    assert artifact.aggregate_metrics.empty_retrieval_rate == 0.0
    assert artifact.aggregate_metrics.bad_section_leak_rate == 0.0
    assert artifact.aggregate_metrics.average_snippet_length > 0
    assert artifact.aggregate_metrics.max_source_payload_bytes > 0
    assert all(record.retrieved_node_ids for record in artifact.records)
    assert all(record.bad_sections for record in artifact.records)
    assert all(record.metrics.bad_section_leak_rate == 0.0 for record in artifact.records)
    assert all(record.metrics.top_1_section_correctness == 1.0 for record in artifact.records)


def test_live_rag_eval_dataset_is_large_enough_for_hybrid_baselines() -> None:
    dataset = build_live_pipeline_eval_dataset()
    corpus = load_live_rag_filing_corpus(dataset)

    tickers = {case.ticker for case in dataset.cases}
    task_types = {case.task_type.value for case in dataset.cases}
    expected_sections = {section for case in dataset.cases for section in case.expected_sections}

    assert dataset.name == "stage1_live_rag_eval"
    assert len(dataset.cases) >= 30
    assert len(tickers) >= 5
    assert len(corpus.filings) == len({case.filing_ref for case in dataset.cases})
    assert task_types == {
        "latest_earnings_readout",
        "business_driver_deep_dive",
        "cash_flow_capital_allocation",
    }
    required_sections = {
        "MD&A",
        "Segment Information",
        "Liquidity and Capital Resources",
        "Risk Factors",
    }
    assert required_sections.issubset(expected_sections)
    assert all(case.filing_ref for case in dataset.cases)
    assert all(case.expected_terms for case in dataset.cases)
    assert all(case.bad_sections for case in dataset.cases)


def test_hard_live_rag_eval_dataset_exercises_retrieval_failures() -> None:
    dataset = build_hard_live_pipeline_eval_dataset()
    corpus = load_live_rag_filing_corpus(dataset)

    assert dataset.name == "stage1_hard_rag_eval"
    assert len(dataset.cases) >= 10
    assert len({case.ticker for case in dataset.cases}) >= 5
    assert len(corpus.filings) == len({case.filing_ref for case in dataset.cases})
    assert any(case.expected_sections == ["Segment Information"] for case in dataset.cases)
    assert any(case.expected_sections == ["Risk Factors"] for case in dataset.cases)
    assert all(case.expected_terms for case in dataset.cases)
    assert all(case.bad_sections for case in dataset.cases)


def test_live_pipeline_experiment_suite_compares_retrieval_strategies() -> None:
    dataset = build_hard_live_pipeline_eval_dataset()

    suite = run_live_pipeline_experiment_suite(dataset)

    assert {artifact.baseline_label for artifact in suite} == {
        RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL.value,
        RetrievalExperimentStrategy.SECTION_AWARE_LEXICAL.value,
        RetrievalExperimentStrategy.NO_SECTION_FILTER.value,
        RetrievalExperimentStrategy.NO_QUERY_EXPANSION.value,
    }
    metrics_by_label = {
        artifact.baseline_label: artifact.aggregate_metrics for artifact in suite
    }
    section_aware = metrics_by_label[RetrievalExperimentStrategy.SECTION_AWARE_LEXICAL.value]
    hybrid = metrics_by_label[RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL.value]
    no_section_filter = metrics_by_label[RetrievalExperimentStrategy.NO_SECTION_FILTER.value]
    no_query_expansion = metrics_by_label[RetrievalExperimentStrategy.NO_QUERY_EXPANSION.value]

    assert hybrid.expected_term_hit_rate == 1.0
    assert hybrid.expected_term_hit_rate > section_aware.expected_term_hit_rate
    assert hybrid.empty_retrieval_rate < section_aware.empty_retrieval_rate
    assert hybrid.expected_term_hit_rate >= section_aware.expected_term_hit_rate
    assert hybrid.bad_section_leak_rate == 0.0
    assert hybrid.empty_retrieval_rate == 0.0
    assert section_aware.expected_term_hit_rate >= 0.9
    assert section_aware.top_1_section_correctness >= 0.9
    assert section_aware.bad_section_leak_rate == 0.0
    assert section_aware.expected_section_hit_rate >= no_section_filter.expected_section_hit_rate
    assert section_aware.bad_section_leak_rate <= no_section_filter.bad_section_leak_rate
    assert section_aware.expected_term_hit_rate >= no_query_expansion.expected_term_hit_rate
    assert no_query_expansion.empty_retrieval_rate > 0.0
    assert any(
        record.metrics.bad_section_leak_rate > 0
        for artifact in suite
        if artifact.baseline_label == RetrievalExperimentStrategy.NO_SECTION_FILTER.value
        for record in artifact.records
    )


def test_live_pipeline_eval_accepts_pipeline_factory_for_vector_store_experiments() -> None:
    created_pipelines: list[LlamaIndexRagPipeline] = []

    def pipeline_factory(strategy: RetrievalExperimentStrategy) -> LlamaIndexRagPipeline:
        assert strategy == RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL
        pipeline = LlamaIndexRagPipeline(enable_hybrid_retrieval=True)
        created_pipelines.append(pipeline)
        return pipeline

    artifact = run_live_pipeline_eval(
        build_hard_live_pipeline_eval_dataset(),
        strategy=RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL,
        pipeline_factory=pipeline_factory,
    )

    assert created_pipelines
    assert artifact.baseline_label == RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL.value
    assert artifact.aggregate_metrics.empty_retrieval_rate == 0.0


def test_stage1_hard_dashboard_artifact_is_frontend_safe() -> None:
    artifact = build_stage1_hard_dashboard_artifact()

    assert artifact.stage == "stage_1_hard_rag"
    assert artifact.dataset_name == "stage1_hard_rag_eval"
    assert artifact.baseline_label == RetrievalExperimentStrategy.HYBRID_SEMANTIC_LEXICAL.value
    assert artifact.stage_comparisons
    assert artifact.metrics[0].key == "expectedTermHitRate"
    assert artifact.metrics[0].format == RagEvalMetricFormat.RATIO
    assert any(
        comparison.baseline_label == RetrievalExperimentStrategy.SECTION_AWARE_LEXICAL.value
        for comparison in artifact.stage_comparisons
    )
    payload = artifact.model_dump(mode="json", by_alias=True)
    assert payload["stageLabel"] == "Stage 1 Hard RAG"
    assert payload["stageComparisons"][0]["baselineLabel"]
    assert payload["metrics"][0]["key"] == "expectedTermHitRate"


def test_stage1_hard_dashboard_artifact_can_be_written_to_json(tmp_path: Path) -> None:
    target = tmp_path / "stage1-hard.json"

    written_path = write_stage1_hard_dashboard_artifact(target)

    assert written_path == target
    payload = target.read_text(encoding="utf-8")
    assert '"stage": "stage_1_hard_rag"' in payload
    assert '"hybrid_semantic_lexical_retrieval"' in payload


def _is_ratio(value: float) -> bool:
    return 0.0 <= value <= 1.0
