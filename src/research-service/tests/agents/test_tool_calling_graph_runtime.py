from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[2] / "app" / "agents"


def test_task_agents_share_tool_calling_graph_runtime() -> None:
    runtime_source = (AGENT_DIR / "tool_calling_graph.py").read_text(encoding="utf-8")

    assert "StateGraph" in runtime_source
    for filename in ("earnings_agent.py", "business_driver_agent.py", "cash_flow_agent.py"):
        source = (AGENT_DIR / filename).read_text(encoding="utf-8")
        assert "run_tool_calling_graph_agent" in source
        assert "StateGraph" not in source
