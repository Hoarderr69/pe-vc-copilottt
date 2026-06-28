import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.vcp_monitoring_graph_builder import build_vcp_monitoring_graph


def main():
    print("\n========== CLEAN VCP MONITORING GRAPH RUN ==========")

    graph = build_vcp_monitoring_graph()

    initial_state = {
        "company_scope": "portco_a_saas",
        "company_id": "portco_a_saas",
        "vcp_store_path": "data/processed/synthetic_vcp_milestones_seed.json",
        "kpi_records_path": "data/processed/portco_a_saas_kpi_records.json",
        "vcp_drift_scores_path": (
            "data/processed/portco_a_saas_vcp_drift_kpi_graph.json"
        ),
    }

    final_state = graph.invoke(initial_state)

    output_path = (
        PROJECT_ROOT
        / "data"
        / "processed"
        / "portco_a_saas_vcp_monitoring_graph_state.json"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(final_state, indent=2, default=str),
        encoding="utf-8",
    )

    print("\n========== CLEAN VCP MONITORING GRAPH SUMMARY ==========")
    print(f"Status: {final_state.get('status')}")
    print(f"VCP confirmed: {final_state.get('vcp_confirmed')}")
    print(f"VCP milestones: {final_state.get('vcp_milestones_count')}")
    print(f"VCP companies: {final_state.get('vcp_company_count')}")
    print(f"Drift results: {final_state.get('vcp_drift_result_count')}")
    print(f"Status counts: {final_state.get('vcp_drift_status_counts')}")
    print(f"HITL status: {final_state.get('hitl_status')}")
    print(f"Alerts: {len(final_state.get('alerts', []))}")
    print(f"Saved: {output_path}")

    if final_state.get("errors"):
        print("\nErrors:")
        for error in final_state["errors"]:
            print(f"- {error}")

    if final_state.get("alerts"):
        print("\nAlerts:")
        for alert in final_state["alerts"]:
            print(
                f"- [{alert.get('severity')}] "
                f"{alert.get('company_id')} | "
                f"{alert.get('metric')} | "
                f"{alert.get('summary')}"
            )


if __name__ == "__main__":
    main()