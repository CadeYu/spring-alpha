import json

from app.agents.tool_registry import (
    DeterministicToolRunner,
    RegisteredTool,
    ToolRegistry,
    default_tool_registry,
)
from app.contracts.agent import (
    MVP_TOOL_NAMES,
    AgentPhase,
    AgentRunStatus,
    AgentState,
    ToolCall,
    ToolResult,
    ToolStatus,
    default_task_policy,
)
from app.contracts.research_task import ResearchTaskType
from app.contracts.tools import FilingSectionSearchInput


def test_default_tool_registry_contains_all_mvp_tools() -> None:
    registry = default_tool_registry()

    assert registry.tool_names == MVP_TOOL_NAMES


def test_tool_registry_executes_allowed_tool_and_updates_state() -> None:
    registry = ToolRegistry(
        [
            RegisteredTool(
                name="search_filing_sections",
                input_model=FilingSectionSearchInput,
                handler=search_handler,
            )
        ]
    )
    state = business_driver_state()

    updated = registry.execute(
        state,
        ToolCall(
            run_id="run_tool_001",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            step_index=0,
            tool_name="search_filing_sections",
            tool_input={
                "run_id": "run_tool_001",
                "ticker": "AAPL",
                "task_type": "business_driver_deep_dive",
                "sections": ["MD&A"],
                "query": "services demand",
            },
            summary="Search filing evidence for Services demand.",
        ),
    )

    assert updated.tool_call_count == 1
    assert updated.step_index == 1
    assert updated.evidence_memory.source_refs[0]["section"] == "MD&A"
    assert updated.retrieval_records[0]["tool_name"] == "search_filing_sections"
    assert updated.tool_events[0].phase == AgentPhase.RETRIEVE_EVIDENCE
    assert updated.tool_events[0].summary == "Search filing evidence for Services demand."

    serialized = json.dumps(updated.model_dump(mode="json"))
    assert "chain_of_thought" not in serialized
    assert "scratchpad" not in serialized


def test_tool_registry_rejects_tool_outside_task_policy() -> None:
    registry = ToolRegistry(
        [
            RegisteredTool(
                name="get_company_facts",
                input_model=FilingSectionSearchInput,
                handler=search_handler,
            )
        ]
    )
    state = business_driver_state()

    updated = registry.execute(
        state,
        ToolCall(
            run_id="run_tool_002",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            step_index=0,
            tool_name="get_company_facts",
            tool_input={
                "run_id": "run_tool_002",
                "ticker": "AAPL",
                "task_type": "business_driver_deep_dive",
                "sections": ["MD&A"],
                "query": "services demand",
            },
            summary="Try a disallowed tool.",
        ),
    )

    assert updated.tool_call_count == 0
    assert updated.degraded_reasons == [
        "Tool get_company_facts is not allowed for business_driver_deep_dive."
    ]
    assert updated.tool_events[-1].status == ToolStatus.DEGRADED
    assert updated.tool_events[-1].phase == AgentPhase.DEGRADED


def test_tool_registry_rejects_unknown_tool_name() -> None:
    registry = ToolRegistry(
        [
            RegisteredTool(
                name="search_filing_sections",
                input_model=FilingSectionSearchInput,
                handler=search_handler,
            )
        ]
    )
    state = business_driver_state()

    updated = registry.execute(
        state,
        ToolCall(
            run_id="run_tool_unknown",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            step_index=0,
            tool_name="unknown_tool",
            tool_input={
                "run_id": "run_tool_unknown",
                "ticker": "AAPL",
                "task_type": "business_driver_deep_dive",
            },
            summary="Try an unknown tool.",
        ),
    )

    assert updated.tool_call_count == 0
    assert updated.degraded_reasons == ["Unknown tool unknown_tool."]
    assert updated.tool_events[-1].status == ToolStatus.DEGRADED


def test_tool_registry_converts_invalid_input_to_degraded_event() -> None:
    registry = ToolRegistry(
        [
            RegisteredTool(
                name="search_filing_sections",
                input_model=FilingSectionSearchInput,
                handler=search_handler,
            )
        ]
    )
    state = business_driver_state()

    updated = registry.execute(
        state,
        ToolCall(
            run_id="run_tool_003",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            step_index=0,
            tool_name="search_filing_sections",
            tool_input={
                "run_id": "run_tool_003",
                "ticker": "AAPL",
                "task_type": "business_driver_deep_dive",
                "query": "missing sections",
            },
            summary="Search with invalid input.",
        ),
    )

    assert updated.tool_call_count == 0
    assert any(
        "Invalid input for search_filing_sections" in reason for reason in updated.degraded_reasons
    )
    assert updated.tool_events[-1].status == ToolStatus.ERROR


def test_tool_registry_converts_handler_exception_to_degraded_event() -> None:
    registry = ToolRegistry(
        [
            RegisteredTool(
                name="search_filing_sections",
                input_model=FilingSectionSearchInput,
                handler=failing_handler,
            )
        ]
    )
    state = business_driver_state()

    updated = registry.execute(
        state,
        ToolCall(
            run_id="run_tool_004",
            task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
            step_index=0,
            tool_name="search_filing_sections",
            tool_input={
                "run_id": "run_tool_004",
                "ticker": "AAPL",
                "task_type": "business_driver_deep_dive",
                "sections": ["MD&A"],
                "query": "services demand",
            },
            summary="Search filing evidence.",
        ),
    )

    assert updated.tool_call_count == 0
    assert updated.tool_events[-1].status == ToolStatus.ERROR
    assert any("provider unavailable" in reason for reason in updated.degraded_reasons)


def test_deterministic_runner_stops_at_tool_budget() -> None:
    registry = ToolRegistry(
        [
            RegisteredTool(
                name="search_filing_sections",
                input_model=FilingSectionSearchInput,
                handler=search_handler,
            )
        ]
    )
    runner = DeterministicToolRunner(registry)
    state = business_driver_state(max_tool_calls=1)
    calls = [
        filing_call("run_tool_005", 0),
        filing_call("run_tool_005", 1),
    ]

    updated = runner.run(state, calls)

    assert updated.tool_call_count == 1
    assert updated.status == AgentRunStatus.DEGRADED
    assert updated.tool_events[-1].phase == AgentPhase.DEGRADED
    assert any("Tool budget exhausted" in reason for reason in updated.degraded_reasons)


def business_driver_state(*, max_tool_calls: int = 5) -> AgentState:
    policy = default_task_policy(ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE).model_copy(
        update={"max_tool_calls": max_tool_calls}
    )
    return AgentState(
        run_id="run_tool_001",
        ticker="AAPL",
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        language="en",
        task_policy=policy,
    )


def filing_call(run_id: str, step_index: int) -> ToolCall:
    return ToolCall(
        run_id=run_id,
        task_type=ResearchTaskType.BUSINESS_DRIVER_DEEP_DIVE,
        step_index=step_index,
        tool_name="search_filing_sections",
        tool_input={
            "run_id": run_id,
            "ticker": "AAPL",
            "task_type": "business_driver_deep_dive",
            "sections": ["MD&A"],
            "query": "services demand",
        },
        summary="Search filing evidence.",
    )


def search_handler(tool_input: FilingSectionSearchInput, state: AgentState) -> ToolResult:
    return ToolResult.ok(
        data={
            "retrieved_nodes": [
                {
                    "source_id": f"{state.run_id}:src:1",
                    "section": tool_input.sections[0],
                    "snippet": "Services revenue increased.",
                    "citation_status": "unverified",
                }
            ]
        },
        latency_ms=12,
        source_refs=[
            {
                "source_id": f"{state.run_id}:src:1",
                "section": tool_input.sections[0],
                "snippet": "Services revenue increased.",
                "citation_status": "unverified",
            }
        ],
    )


def failing_handler(tool_input: FilingSectionSearchInput, state: AgentState) -> ToolResult:
    raise RuntimeError("provider unavailable")
