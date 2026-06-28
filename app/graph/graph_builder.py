from __future__ import annotations

from app.graph.nodes import (
    initialize_state_node,
    kpi_extraction_node,
    quant_forecast_node,
    irr_scenario_node,
    placeholder_covenant_node,
    placeholder_alert_node,
)
from app.graph.state import PortfolioMonitorState


def build_portfolio_monitor_graph():
    """Build the Week 2 LangGraph orchestration graph."""

    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise ImportError(
            "LangGraph is not installed. Install it with: uv add langgraph"
        ) from exc

    graph = StateGraph(PortfolioMonitorState)

    graph.add_node("initialize", initialize_state_node)
    graph.add_node("kpi_extraction", kpi_extraction_node)
    graph.add_node("quant_forecast", quant_forecast_node)
    graph.add_node("irr_scenarios", irr_scenario_node)
    graph.add_node("covenant_check", placeholder_covenant_node)
    graph.add_node("alert_synthesis", placeholder_alert_node)

    graph.set_entry_point("initialize")
    graph.add_edge("initialize", "kpi_extraction")
    graph.add_edge("kpi_extraction", "quant_forecast")
    graph.add_edge("quant_forecast", "irr_scenarios")
    graph.add_edge("irr_scenarios", "covenant_check")
    graph.add_edge("covenant_check", "alert_synthesis")
    graph.add_edge("alert_synthesis", END)

    return graph.compile()
