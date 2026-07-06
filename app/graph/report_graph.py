from __future__ import annotations

from app.graph.report_nodes import (
    alert_synthesis_node,
    build_slides_node,
    compute_drift_node,
    load_milestones_and_kpis_node,
    narrative_synthesis_node,
    peer_benchmark_node,
    persist_report_node,
    render_pdf_node,
)
from app.graph.report_state import ReportGenerationState


def build_report_graph(checkpointer=None):
    """
    Build the report-generation graph.

    Flow (mirrors generate_report() in app/api/report_routes.py, node-per-stage):
    load_milestones_and_kpis -> compute_drift -> alert_synthesis -> peer_benchmark
    -> narrative_synthesis -> build_slides -> render_pdf -> persist_report -> END

    Pass `checkpointer=` (a PostgresSaver in production — see
    app.graph.checkpointer.get_checkpointer) so a crash mid-run (e.g. render_pdf
    throwing) can resume from that node instead of re-running the LLM nodes.
    """
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise ImportError(
            "LangGraph is not installed. Install it with: uv add langgraph"
        ) from exc

    graph = StateGraph(ReportGenerationState)

    graph.add_node("load_milestones_and_kpis", load_milestones_and_kpis_node)
    graph.add_node("compute_drift", compute_drift_node)
    graph.add_node("alert_synthesis", alert_synthesis_node)
    graph.add_node("peer_benchmark", peer_benchmark_node)
    graph.add_node("narrative_synthesis", narrative_synthesis_node)
    graph.add_node("build_slides", build_slides_node)
    graph.add_node("render_pdf", render_pdf_node)
    graph.add_node("persist_report", persist_report_node)

    graph.set_entry_point("load_milestones_and_kpis")
    graph.add_edge("load_milestones_and_kpis", "compute_drift")
    graph.add_edge("compute_drift", "alert_synthesis")
    graph.add_edge("alert_synthesis", "peer_benchmark")
    graph.add_edge("peer_benchmark", "narrative_synthesis")
    graph.add_edge("narrative_synthesis", "build_slides")
    graph.add_edge("build_slides", "render_pdf")
    graph.add_edge("render_pdf", "persist_report")
    graph.add_edge("persist_report", END)

    return graph.compile(checkpointer=checkpointer)


_compiled_graph = None


def get_report_graph():
    """Process-wide compiled graph, built once with the Postgres checkpointer
    so /api/reports/graph/... routes all share one connection instead of
    reopening it per request."""
    global _compiled_graph

    if _compiled_graph is None:
        from app.graph.checkpointer import get_checkpointer

        _compiled_graph = build_report_graph(checkpointer=get_checkpointer())

    return _compiled_graph
