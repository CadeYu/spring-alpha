import json

from langchain_core.tools import BaseTool

from app.contracts.research_task import ResearchTaskType
from app.rag.langchain_tools import (
    EvidencePackInput,
    SecEvidenceSearchInput,
    create_evidence_pack_tool,
    create_sec_evidence_search_tool,
)
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


def test_sec_evidence_search_tool_returns_standard_evidence_pack() -> None:
    pipeline = LlamaIndexRagPipeline(section_chunk_max_chars=220)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000010",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Services revenue increased because installed base engagement improved.
Product revenue benefited from resilient iPhone demand and disciplined pricing.

Item 1A. Risk Factors
Competition and supply constraints could affect future results.
""",
        )
    )
    tool = create_sec_evidence_search_tool(
        rag_pipeline=pipeline,
        run_id="run_langchain_pack",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
    )

    payload = tool.invoke(
        {
            "query": "services revenue installed base pricing",
            "sections": ["MD&A"],
            "top_k": 3,
        }
    )

    data = json.loads(payload)
    pack = data["evidence_pack"]

    assert pack["run_id"] == "run_langchain_pack"
    assert pack["ticker"] == "AAPL"
    assert pack["task_type"] == "latest_earnings_readout"
    assert pack["query"] == "services revenue installed base pricing"
    assert pack["retrieval_status"] == "ok"
    assert pack["filing_context"] == {
        "filing_type": "10-Q",
        "filing_date": "2026-04-30",
        "accession_number": "0000320193-26-000010",
    }
    assert pack["metric_facts"] == []
    assert pack["filing_evidence"]
    assert pack["filing_evidence"][0]["source_type"] == "sec_filing"
    assert pack["filing_evidence"][0]["section"] == "MD&A"
    assert "Services revenue increased" in pack["filing_evidence"][0]["snippet"]
    assert pack["filing_evidence"][0]["relevance_note"]
    assert len(pack["filing_evidence"]) <= 3


def test_create_evidence_pack_tool_uses_task_templates() -> None:
    pipeline = LlamaIndexRagPipeline(section_chunk_max_chars=220)
    pipeline.ingest_filing(
        FilingDocument(
            ticker="AAPL",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000320193-26-000011",
            text="""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
Revenue grew because services revenue, product demand, and gross margin improved.
Segment operating income benefited from services mix and pricing discipline.

Item 1A. Risk Factors
Competition and supply constraints could affect future results.
""",
        )
    )

    tool = create_evidence_pack_tool(
        rag_pipeline=pipeline,
        run_id="run_build_pack",
        ticker="AAPL",
        task_type=ResearchTaskType.LATEST_EARNINGS_READOUT,
    )

    payload = tool.invoke({})

    data = json.loads(payload)
    pack = data["evidence_pack"]

    assert isinstance(tool, BaseTool)
    assert tool.name == "build_evidence_pack"
    assert tool.args_schema is EvidencePackInput
    assert pack["ticker"] == "AAPL"
    assert pack["task_type"] == "latest_earnings_readout"
    assert pack["retrieval_status"] == "ok"
    assert pack["filing_evidence"]
    assert len(pack["filing_evidence"]) <= 5
    snippets = " ".join(item["snippet"] for item in pack["filing_evidence"])
    assert "Revenue grew" in snippets
    assert "Segment operating income" in snippets
    assert "source_refs" in data


def test_evidence_pack_tool_enforces_compact_budget() -> None:
    pipeline = LlamaIndexRagPipeline(section_chunk_max_chars=260)
    long_sentence = (
        "Revenue growth was supported by services demand, product demand, pricing "
        "discipline, installed base engagement, enterprise customers, geographic mix, "
        "gross margin leverage, operating expense discipline, and channel execution. "
    )
    pipeline.ingest_filing(
        FilingDocument(
            ticker="MSFT",
            filing_type="10-Q",
            filing_date="2026-04-30",
            accession_number="0000789019-26-000010",
            text=f"""
Item 2. Management's Discussion and Analysis of Financial Condition and Results of Operations
{long_sentence * 10}
Segment Information
{long_sentence * 8}
""",
        )
    )
    tool = create_evidence_pack_tool(
        rag_pipeline=pipeline,
        run_id="run_budget_pack",
        ticker="MSFT",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
    )

    payload = tool.invoke({"top_k": 8})

    data = json.loads(payload)
    pack = data["evidence_pack"]
    serialized_pack = json.dumps(pack, ensure_ascii=True)

    assert len(pack["filing_evidence"]) <= 4
    assert len(serialized_pack) <= 3600
    assert all(len(item["snippet"]) <= 380 for item in pack["filing_evidence"])
    assert "business driver evidence" in pack["query"].lower()
