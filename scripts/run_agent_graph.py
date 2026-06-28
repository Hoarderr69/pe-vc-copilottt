import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.graph.graph_builder import build_portfolio_monitor_graph

load_dotenv()


def main():
    print("\n========== AGENT GRAPH RUN ==========")

    graph = build_portfolio_monitor_graph()

    initial_state = {
        "company_id": "demo_aapl_proxy_001",
        "company_name": "DemoCo / Apple proxy",
        "ticker": "AAPL",
        "cik": "0000320193",
        "valuation_mode": "pe_deal",
        "source_type": "edgar",
        "deal_metadata_path": "data/raw/deal_metadata/demo_deal.json",
    }

    final_state = graph.invoke(initial_state)

    output_path = PROJECT_ROOT / "data" / "processed" / "agent_graph_state.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(final_state, indent=2, default=str),
        encoding="utf-8",
    )

    print("\n========== GRAPH FINAL STATE SUMMARY ==========")
    print(f"Status: {final_state.get('status')}")
    print(f"Ticker: {final_state.get('ticker')}")
    print(f"Source type: {final_state.get('source_type')}")
    print(f"Raw rows: {final_state.get('raw_rows')}")
    print(f"Model rows: {final_state.get('model_rows')}")
    print(f"KPI records: {final_state.get('kpi_records_count')}")
    print(f"Evidence refs: {final_state.get('evidence_refs_count')}")
    print(f"Forecast rows: {final_state.get('forecast_rows')}")
    print(f"IRR rows: {final_state.get('irr_rows')}")
    print(f"HITL status: {final_state.get('hitl_status')}")
    print(f"Alerts: {len(final_state.get('alerts', []))}")
    print(f"Saved: {output_path}")

    if final_state.get("alerts"):
        print("\nAlerts:")
        for alert in final_state["alerts"]:
            print(f"- [{alert.get('severity')}] {alert.get('summary')}")

    print("\nGenerated KPI artifacts:")
    print(f"- {final_state.get('kpi_records_path')}")
    print(f"- {final_state.get('evidence_refs_path')}")
    print(f"- {final_state.get('source_quality_report_path')}")


if __name__ == "__main__":
    main()
