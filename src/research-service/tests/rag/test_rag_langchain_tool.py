import json

from langchain_core.tools import BaseTool

from app.contracts.research_task import ResearchTaskType
from app.rag.langchain_tools import SecEvidenceSearchInput, create_sec_evidence_search_tool
from app.rag.llamaindex_pipeline import FilingDocument, LlamaIndexRagPipeline


def test_create_sec_evidence_search_tool_exposes_langchain_tool_schema() -> None:
    pipeline = LlamaIndexRagPipeline()

    tool = create_sec_evidence_search_tool(
        rag_pipeline=pipeline,
        run_id="run_langchain_schema",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
    )

    assert isinstance(tool, BaseTool)
    assert tool.name == "search_sec_evidence"
    assert tool.args_schema is SecEvidenceSearchInput
    assert "SEC filing evidence" in tool.description


def test_sec_evidence_search_tool_returns_compact_evidence_json() -> None:
    pipeline = LlamaIndexRagPipeline()
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000001",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased because installed base engagement improved.

Item 1A. Risk Factors
Competition and supply constraints could affect future results.
""",
        )
    )
    tool = create_sec_evidence_search_tool(
        rag_pipeline=pipeline,
        run_id="run_langchain_tool",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
    )

    payload = tool.invoke(
        {
            "query": "services revenue installed base",
            "sections": ["MD&A"],
            "top_k": 2,
        }
    )

    data = json.loads(payload)
    assert data["ticker"] == "AAPL"
    assert data["query"] == "services revenue installed base"
    assert data["fallback_status"] == "none"
    assert data["evidence"]
    assert data["evidence"][0]["section"] == "MD&A"
    assert "Services revenue increased" in data["evidence"][0]["snippet"]
    assert "verdict" not in data
    assert "analysis" not in data
