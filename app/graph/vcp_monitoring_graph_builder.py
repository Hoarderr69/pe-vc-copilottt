from __future__ import annotations

from app.graph.vcp_nodes import (
    VCPMonitoringState,
    alert_synthesis_node,
    hitl_digest_node,
    hitl_immediate_node,
    hitl_skip_node,
    initialize_vcp_monitoring_state_node,
    route_after_alert_synthesis,
    route_after_vcp_confirmation,
    vcp_confirmation_check_node,
    vcp_drift_from_kpi_records_node,
)


def build_vcp_monitoring_graph():
    """
    Build the VCP monitoring graph.

    Flow:
    initialize
    -> vcp_confirmation_check  [conditional: stop if not confirmed]
    -> vcp_drift_from_kpi_records
    -> alert_synthesis         [GPT-4o or offline fallback]
    -> severity_router         [conditional: Red / Amber / Green]
       -> hitl_immediate       (Red)
       -> hitl_digest          (Amber)
       -> hitl_skip            (Green)
    -> END
    """

    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise ImportError(
            "LangGraph is not installed. Install it with: uv add langgraph"
        ) from exc

    graph = StateGraph(VCPMonitoringState)

    graph.add_node("initialize", initialize_vcp_monitoring_state_node)
    graph.add_node("vcp_confirmation_check", vcp_confirmation_check_node)
    graph.add_node("vcp_drift_from_kpi_records", vcp_drift_from_kpi_records_node)
    graph.add_node("alert_synthesis", alert_synthesis_node)
    graph.add_node("hitl_immediate", hitl_immediate_node)
    graph.add_node("hitl_digest", hitl_digest_node)
    graph.add_node("hitl_skip", hitl_skip_node)

    graph.set_entry_point("initialize")

    graph.add_edge("initialize", "vcp_confirmation_check")

    graph.add_conditional_edges(
        "vcp_confirmation_check",
        route_after_vcp_confirmation,
        {
            "continue": "vcp_drift_from_kpi_records",
            "stop": END,
        },
    )

    graph.add_edge("vcp_drift_from_kpi_records", "alert_synthesis")

    graph.add_conditional_edges(
        "alert_synthesis",
        route_after_alert_synthesis,
        {
            "red_hitl": "hitl_immediate",
            "amber_hitl": "hitl_digest",
            "green_skip": "hitl_skip",
        },
    )

    graph.add_edge("hitl_immediate", END)
    graph.add_edge("hitl_digest", END)
    graph.add_edge("hitl_skip", END)

    return graph.compile()