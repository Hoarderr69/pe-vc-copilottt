from __future__ import annotations

from app.graph.extraction_nodes import (
    confirm_and_store_node,
    extract_milestones_node,
    hitl_review_node,
    route_after_extraction,
)
from app.graph.extraction_state import VCPExtractionState


def build_vcp_extraction_graph(checkpointer=None):
    """
    Build the setup/extraction graph.

    This is a fresh graph, not a revival of app/graph/nodes.py — that pipeline
    turned out to be a different, superseded "Week 2" KPI/quant/IRR monitor
    graph. The IC-memo extraction + confirm flow the original brief's "Setup
    Graph" describes exists today only as two independent HTTP requests
    (POST /extract-upload, POST /extract/{id}/confirm) with no shared
    server-side state between them.

    Flow:
    extract_milestones  [VCP Extraction Agent — Azure OpenAI or offline fallback]
    -> route_after_extraction  [conditional: stop if nothing was extracted]
       -> hitl_review           [interrupts — operating partner reviews/edits candidates]
          -> confirm_and_store  [locks reviewed milestones into VCPStore]
       -> END (empty extraction)
    -> END

    Pass `checkpointer=` (a PostgresSaver in production — see
    app.graph.checkpointer.get_checkpointer) so the review pause survives
    across the extract-upload / confirm HTTP requests.
    """
    try:
        from langgraph.graph import END, StateGraph
    except ImportError as exc:
        raise ImportError(
            "LangGraph is not installed. Install it with: uv add langgraph"
        ) from exc

    graph = StateGraph(VCPExtractionState)

    graph.add_node("extract_milestones", extract_milestones_node)
    graph.add_node("hitl_review", hitl_review_node)
    graph.add_node("confirm_and_store", confirm_and_store_node)

    graph.set_entry_point("extract_milestones")

    graph.add_conditional_edges(
        "extract_milestones",
        route_after_extraction,
        {
            "review": "hitl_review",
            "stop": END,
        },
    )

    graph.add_edge("hitl_review", "confirm_and_store")
    graph.add_edge("confirm_and_store", END)

    return graph.compile(checkpointer=checkpointer)


_compiled_graph = None


def get_vcp_extraction_graph():
    """Process-wide compiled graph, built once with the Postgres checkpointer
    (app.graph.checkpointer.get_checkpointer) so /api/vcp/graph/extract-upload
    and /api/vcp/graph/{thread_id}/confirm share one connection."""
    global _compiled_graph

    if _compiled_graph is None:
        from app.graph.checkpointer import get_checkpointer

        _compiled_graph = build_vcp_extraction_graph(checkpointer=get_checkpointer())

    return _compiled_graph
