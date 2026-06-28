import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _clean_name(raw: str) -> str:
    """Strip _ic_memo noise and title-case for display."""
    s = re.sub(r"[_\s]?ic[_\s]?memo$", "", raw, flags=re.IGNORECASE).strip("_- ")
    return " ".join(w.capitalize() for w in re.split(r"[_\-\s]+", s) if w) or raw

from app.graph.vcp_monitoring_graph_builder import build_vcp_monitoring_graph

PROCESSED = PROJECT_ROOT / "data" / "processed"
VCP_SEED = PROCESSED / "synthetic_vcp_milestones_seed.json"
VCP_STORE = PROCESSED / "vcp_store.json"

# Static seed companies — always included if their KPI records exist.
_SEED_PORTCOS = [
    {"company_id": "portco_a_saas", "company_name": "Company A — B2B SaaS", "vcp_path": str(VCP_SEED)},
    {"company_id": "portco_b_industrial", "company_name": "Company B — Industrial Manufacturing", "vcp_path": str(VCP_SEED)},
    {"company_id": "portco_c_healthcare", "company_name": "Company C — Healthcare Services", "vcp_path": str(VCP_SEED)},
]


def _build_portco_list() -> list:
    """Merge seed companies with any confirmed VCP-store companies that have KPI data."""
    portcos = []
    seen = set()

    for p in _SEED_PORTCOS:
        kpi = PROCESSED / f"{p['company_id']}_kpi_records.json"
        if kpi.exists():
            portcos.append(p)
            seen.add(p["company_id"])

    if VCP_STORE.exists():
        store = json.loads(VCP_STORE.read_text(encoding="utf-8"))
        for m in store:
            cid = m.get("company_id")
            if not cid or cid in seen or not m.get("confirmed"):
                continue
            kpi = PROCESSED / f"{cid}_kpi_records.json"
            if not kpi.exists():
                continue
            raw_name = m.get("company_name") or cid
            portcos.append({
                "company_id": cid,
                "company_name": _clean_name(raw_name),
                "vcp_path": str(VCP_STORE),
            })
            seen.add(cid)

    return portcos


def main():
    print("\n========== PORTFOLIO VCP MONITORING RUN ==========")

    graph = build_vcp_monitoring_graph()
    portcos = _build_portco_list()

    portfolio_results = []
    portfolio_alerts = []

    for portco in portcos:
        company_id = portco["company_id"]

        print(f"\nRunning VCP monitoring for: {company_id}")

        initial_state = {
            "company_scope": company_id,
            "company_id": company_id,
            "vcp_store_path": portco["vcp_path"],
            "kpi_records_path": f"data/processed/{company_id}_kpi_records.json",
            "vcp_drift_scores_path": (
                f"data/processed/{company_id}_vcp_drift_kpi_graph.json"
            ),
        }

        final_state = graph.invoke(initial_state)

        company_summary = {
            "company_id": company_id,
            "company_name": portco["company_name"],
            "status": final_state.get("status"),
            "vcp_confirmed": final_state.get("vcp_confirmed"),
            "vcp_drift_result_count": final_state.get("vcp_drift_result_count"),
            "vcp_drift_status_counts": final_state.get("vcp_drift_status_counts"),
            "hitl_status": final_state.get("hitl_status"),
            "alert_count": len(final_state.get("alerts", [])),
            "alerts": final_state.get("alerts", []),
            "errors": final_state.get("errors", []),
        }

        portfolio_results.append(company_summary)
        portfolio_alerts.extend(final_state.get("alerts", []))

        print(
            f"  -> Alerts: {company_summary['alert_count']}, "
            f"Counts: {company_summary['vcp_drift_status_counts']}"
        )

    severity_counts = {}
    for alert in portfolio_alerts:
        severity = alert.get("severity", "Unknown")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

    payload = {
        "portfolio_company_count": len(portcos),
        "total_alerts": len(portfolio_alerts),
        "severity_counts": severity_counts,
        "companies": portfolio_results,
        "alerts": portfolio_alerts,
    }

    output_path = Path("data/processed/portfolio_vcp_monitoring_summary.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    print("\n========== PORTFOLIO SUMMARY ==========")
    print(f"Companies: {payload['portfolio_company_count']}")
    print(f"Total alerts: {payload['total_alerts']}")
    print(f"Severity counts: {payload['severity_counts']}")
    print(f"Saved: {output_path}")

    print("\nTop alerts:")
    for alert in portfolio_alerts[:10]:
        print(
            f"- [{alert.get('severity')}] "
            f"{alert.get('company_id')} | "
            f"{alert.get('metric')} | "
            f"{alert.get('summary')}"
        )


if __name__ == "__main__":
    main()
