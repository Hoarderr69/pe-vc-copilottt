from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd


RAW_SYNTHETIC_DIR = Path("data/raw/synthetic_portcos")
IC_MEMO_DIR = Path("data/raw/ic_memos")
PROCESSED_DIR = Path("data/processed")

MONTHS = 24
START_PERIOD = "2026-01-31"
PLAN_CHECKPOINT_MONTHS = [3, 6, 9, 12, 15, 18, 21, 24]


@dataclass
class PortcoProfile:
    """
    One synthetic portfolio company.

    The VCP targets are NOT hard-coded. They are derived from a clean, noise-free
    "plan" simulation (see derive_plan_targets) so that the status a company earns
    against its VCP is an honest consequence of how its actuals track the plan:

      - A performer (is_performer=True) follows the plan for all 24 months and
        lands on/around target  -> Green.
      - A drifter follows the plan for months 1-12, then revenue growth decelerates
        and SG&A intensity rises from anomaly_start_month -> margin compression,
        leverage blow-out -> Red.
    """

    company_id: str
    company_name: str
    sector: str
    currency: str

    start_revenue: float            # month-1 monthly revenue
    gross_margin: float

    # Plan trajectory (the underwriting case). Actuals track this while on-plan.
    plan_monthly_growth: float      # planned monthly revenue growth
    plan_sga_start: float           # SG&A % of revenue at month 1
    plan_sga_end: float             # SG&A % of revenue at month 24 (operating leverage)

    # Drift trajectory (drifters only, from anomaly_start_month onward).
    drift_monthly_growth: float
    drift_sga: float

    starting_cash: float
    starting_net_debt: float

    is_performer: bool = False
    anomaly_start_month: int = 13


def build_profiles() -> List[PortcoProfile]:
    return [
        # Drifter: revenue plateaus and SG&A rises after month 12.
        PortcoProfile(
            company_id="portco_a_saas",
            company_name="Company A — B2B SaaS",
            sector="B2B SaaS",
            currency="GBP",
            start_revenue=1_650_000,
            gross_margin=0.78,
            plan_monthly_growth=0.025,
            plan_sga_start=0.60,
            plan_sga_end=0.54,
            drift_monthly_growth=0.006,
            drift_sga=0.66,
            starting_cash=8_000_000,
            starting_net_debt=12_000_000,
            is_performer=False,
        ),
        # Drifter: thin-margin industrial, leverage blows out under compression.
        PortcoProfile(
            company_id="portco_b_industrial",
            company_name="Company B — Industrial Manufacturing",
            sector="Industrial Manufacturing",
            currency="GBP",
            start_revenue=3_750_000,
            gross_margin=0.36,
            plan_monthly_growth=0.013,
            plan_sga_start=0.24,
            plan_sga_end=0.18,
            drift_monthly_growth=0.003,
            drift_sga=0.285,
            starting_cash=5_500_000,
            starting_net_debt=28_000_000,
            is_performer=False,
        ),
        # Performer: tracks the plan for all 24 months -> on-track / Green.
        PortcoProfile(
            company_id="portco_c_healthcare",
            company_name="Company C — Healthcare Services",
            sector="Healthcare Services",
            currency="GBP",
            start_revenue=2_500_000,
            gross_margin=0.48,
            plan_monthly_growth=0.018,
            plan_sga_start=0.33,
            plan_sga_end=0.28,
            drift_monthly_growth=0.018,   # unused (performer), kept = plan for clarity
            drift_sga=0.28,
            starting_cash=6_500_000,
            starting_net_debt=18_000_000,
            is_performer=True,
        ),
    ]


def _plan_sga_pct(profile: PortcoProfile, month_idx: int) -> float:
    """Planned SG&A % declines linearly from start to end across the 24 months."""
    frac = (month_idx - 1) / (MONTHS - 1)
    return profile.plan_sga_start + (profile.plan_sga_end - profile.plan_sga_start) * frac


def _simulate(profile: PortcoProfile, mode: str, seed: int = 0) -> pd.DataFrame:
    """
    Simulate 24 months of monthly financials.

    mode="plan"   -> deterministic underwriting case, no noise, no drift.
                     Used only to derive VCP targets and the plan path.
    mode="actual" -> the financials written to disk: plan + noise, with drift
                     applied after anomaly_start_month for drifters.
    """

    is_actual = mode == "actual"
    rng = np.random.default_rng(seed)
    periods = pd.date_range(START_PERIOD, periods=MONTHS, freq="ME")

    def noise(scale: float) -> float:
        return rng.normal(0, scale) if is_actual else 0.0

    rows = []
    revenue = profile.start_revenue
    net_debt = profile.starting_net_debt
    cash = profile.starting_cash

    for month_idx, period_end in enumerate(periods, start=1):
        drifting = (
            is_actual
            and not profile.is_performer
            and month_idx >= profile.anomaly_start_month
        )

        # Performers execute modestly ahead of the underwriting plan, so they land
        # on/above target even after single-month snapshot noise (a healthy portco).
        perf_growth_bonus = 0.001 if (is_actual and profile.is_performer) else 0.0
        perf_sga_relief = 0.012 if (is_actual and profile.is_performer) else 0.0

        growth = profile.drift_monthly_growth if drifting else profile.plan_monthly_growth
        revenue *= 1 + growth + perf_growth_bonus + noise(0.010)

        gross_margin = profile.gross_margin + noise(0.006)
        gross_profit = revenue * gross_margin
        cogs = revenue - gross_profit

        sga_pct = profile.drift_sga if drifting else _plan_sga_pct(profile, month_idx)
        sga_pct -= perf_sga_relief
        sga = revenue * (sga_pct + noise(0.008))
        ebitda = gross_profit - sga
        ebitda_margin = ebitda / revenue if revenue else np.nan

        capex = revenue * (0.035 + noise(0.003))
        ar = revenue * (0.16 + noise(0.008))
        inventory = revenue * (0.09 + noise(0.006))
        ap = cogs * (0.12 + noise(0.006))

        # Simple cash / debt mechanics for synthetic realism. The paydown rate is
        # deliberately modest so the plan deleverages at a credible PE pace
        # (~0.3-0.5x net-debt/EBITDA per year) rather than collapsing to near-zero.
        free_cash_flow = ebitda - capex - max(ar + inventory - ap, 0) * 0.03
        debt_paydown = max(free_cash_flow, 0) * 0.15
        net_debt = max(net_debt - debt_paydown + max(-free_cash_flow, 0) * 0.25, 0)
        cash = max(cash + free_cash_flow * 0.25, 500_000)

        rows.append(
            {
                "company_id": profile.company_id,
                "company_name": profile.company_name,
                "sector": profile.sector,
                "period_end": period_end.date().isoformat(),
                "period_type": "month",
                "currency": profile.currency,
                "revenue": round(revenue, 2),
                "cogs": round(cogs, 2),
                "gross_profit": round(gross_profit, 2),
                "sga": round(sga, 2),
                "ebitda": round(ebitda, 2),
                "ebitda_margin": round(ebitda_margin, 4),
                "capex": round(capex, 2),
                "cash": round(cash, 2),
                "ar": round(ar, 2),
                "inventory": round(inventory, 2),
                "ap": round(ap, 2),
                "net_debt": round(net_debt, 2),
                "free_cash_flow": round(free_cash_flow, 2),
                "anomaly_flag_design": drifting,
            }
        )

    return pd.DataFrame(rows)


def _annual_revenue_runrate(monthly_revenue: float) -> float:
    """Match the drift node: annual revenue = latest month revenue x 12."""
    return monthly_revenue * 12.0


def _leverage(net_debt: float, monthly_ebitda: float) -> float:
    return net_debt / (monthly_ebitda * 12.0)


def derive_plan_targets(profile: PortcoProfile) -> Dict[str, object]:
    """
    Run the noise-free plan simulation and derive VCP targets + plan path.

    Targets are the month-24 plan values; the plan path is the quarterly planned
    trajectory each financial metric is expected to follow between close and exit.
    Baselines are the month-1 plan values (deal-close starting point).
    """

    plan = _simulate(profile, mode="plan")
    m1 = plan.iloc[0]
    m24 = plan.iloc[-1]

    revenue_target = round(_annual_revenue_runrate(m24["revenue"]) / 100_000) * 100_000
    margin_target = round(float(m24["ebitda_margin"]), 3)
    leverage_target = round(_leverage(m24["net_debt"], m24["ebitda"]), 1)

    revenue_baseline = round(_annual_revenue_runrate(m1["revenue"]) / 100_000) * 100_000
    margin_baseline = round(float(m1["ebitda_margin"]), 3)
    leverage_baseline = round(_leverage(m1["net_debt"], m1["ebitda"]), 1)

    def plan_path(value_fn) -> List[Dict[str, object]]:
        path = []
        for m in PLAN_CHECKPOINT_MONTHS:
            row = plan.iloc[m - 1]
            path.append(
                {
                    "month": m,
                    "period_end": row["period_end"],
                    "planned_value": value_fn(row),
                }
            )
        return path

    return {
        "revenue_target": revenue_target,
        "margin_target": margin_target,
        "leverage_target": leverage_target,
        "revenue_baseline": revenue_baseline,
        "margin_baseline": margin_baseline,
        "leverage_baseline": leverage_baseline,
        "revenue_plan_path": plan_path(
            lambda r: round(_annual_revenue_runrate(r["revenue"]), 2)
        ),
        "margin_plan_path": plan_path(lambda r: round(float(r["ebitda_margin"]), 4)),
        "leverage_plan_path": plan_path(
            lambda r: round(_leverage(r["net_debt"], r["ebitda"]), 3)
        ),
    }


def build_ic_memo_markdown(profile: PortcoProfile, targets: Dict[str, object]) -> str:
    rev_target = targets["revenue_target"]
    margin_target = targets["margin_target"]
    leverage_target = targets["leverage_target"]

    return f"""# Investment Committee Memorandum — {profile.company_name}

## Executive Summary

The proposed investment in {profile.company_name} is based on a focused value creation plan over the first 24 months post-close. The company operates in the {profile.sector} sector and has meaningful opportunity to improve commercial execution, margin discipline, and capital efficiency.

## Value Creation Plan

Management and the sponsor expect to grow the annual revenue run-rate to approximately £{rev_target:,.0f} by Month 24 through improved sales execution, tighter pricing governance, and better customer retention. This represents continued organic growth from the current run-rate of roughly £{targets['revenue_baseline']:,.0f}.

The underwriting case assumes EBITDA margin improves from approximately {targets['margin_baseline']:.0%} at close to approximately {margin_target:.0%} by Month 24. This improvement is expected to come from operating leverage, SG&A discipline, and tighter procurement controls.

The capital structure plan expects net debt to EBITDA to reduce from approximately {targets['leverage_baseline']:.1f}x at close toward {leverage_target:.1f}x by Month 24, supported by cash generation and disciplined capex.

The operating team should reduce SG&A intensity over the investment period. In the first year, the company should identify cost actions that move SG&A toward the long-term target range while avoiding disruption to revenue growth.

The company should hire a Chief Revenue Officer within 90 days of close to improve pipeline management, sales accountability, and revenue forecasting quality.

There is also an expectation that management will improve monthly reporting cadence and produce a KPI pack that includes revenue, EBITDA, cash, net debt, working capital, and pipeline metrics. The exact completion date for the reporting upgrade is still to be confirmed with management.

## Monitoring Priorities

The operating partner should monitor revenue growth, EBITDA margin, SG&A intensity, free cash flow conversion, and net debt to EBITDA every month. Any sustained revenue plateau combined with rising SG&A should be escalated because it would indicate margin compression risk.
"""


def build_seed_vcp_milestones(profile: PortcoProfile, targets: Dict[str, object]) -> List[Dict]:
    return [
        {
            "company_id": profile.company_id,
            "company_name": profile.company_name,
            "initiative": "Revenue growth plan",
            "metric": "annual_revenue",
            "baseline_value": targets["revenue_baseline"],
            "target_value": targets["revenue_target"],
            "target_date": "2027-12-31",
            "category": "financial",
            "owner_role": "Chief Revenue Officer",
            "confidence": 0.92,
            "source_document": f"{profile.company_id}_ic_memo.md",
            "metadata": {"plan_path": targets["revenue_plan_path"]},
        },
        {
            "company_id": profile.company_id,
            "company_name": profile.company_name,
            "initiative": "EBITDA margin expansion",
            "metric": "ebitda_margin",
            "baseline_value": targets["margin_baseline"],
            "target_value": targets["margin_target"],
            "target_date": "2027-12-31",
            "category": "financial",
            "owner_role": "CFO",
            "confidence": 0.94,
            "source_document": f"{profile.company_id}_ic_memo.md",
            "metadata": {"plan_path": targets["margin_plan_path"]},
        },
        {
            "company_id": profile.company_id,
            "company_name": profile.company_name,
            "initiative": "Deleveraging plan",
            "metric": "net_debt_to_ebitda",
            "baseline_value": targets["leverage_baseline"],
            "target_value": targets["leverage_target"],
            "target_date": "2027-12-31",
            "category": "financial",
            "owner_role": "CFO",
            "confidence": 0.91,
            "source_document": f"{profile.company_id}_ic_memo.md",
            "metadata": {"plan_path": targets["leverage_plan_path"]},
        },
        {
            "company_id": profile.company_id,
            "company_name": profile.company_name,
            "initiative": "Chief Revenue Officer hire",
            "metric": "cro_hired",
            "baseline_value": 0,
            "target_value": 1,
            "target_date": "2026-03-31",
            "category": "organizational",
            "owner_role": "CEO",
            "confidence": 0.88,
            "source_document": f"{profile.company_id}_ic_memo.md",
            "metadata": {},
        },
        {
            "company_id": profile.company_id,
            "company_name": profile.company_name,
            "initiative": "Monthly KPI reporting upgrade",
            "metric": "reporting_cadence_upgrade_complete",
            "baseline_value": 0,
            "target_value": 1,
            "target_date": None,
            "category": "operational",
            "owner_role": "CFO",
            "confidence": 0.62,
            "source_document": f"{profile.company_id}_ic_memo.md",
            "metadata": {},
        },
    ]


def main() -> None:
    RAW_SYNTHETIC_DIR.mkdir(parents=True, exist_ok=True)
    IC_MEMO_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    profiles = build_profiles()
    all_milestones: List[Dict] = []
    manifest: List[Dict] = []

    for idx, profile in enumerate(profiles, start=1):
        company_dir = RAW_SYNTHETIC_DIR / profile.company_id
        company_dir.mkdir(parents=True, exist_ok=True)

        targets = derive_plan_targets(profile)
        df = _simulate(profile, mode="actual", seed=100 + idx)

        csv_path = company_dir / f"{profile.company_id}_monthly_financials.csv"
        xlsx_path = company_dir / f"{profile.company_id}_monthly_financials.xlsx"
        memo_path = IC_MEMO_DIR / f"{profile.company_id}_ic_memo.md"

        df.to_csv(csv_path, index=False)
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Financials", index=False)

        memo_path.write_text(build_ic_memo_markdown(profile, targets), encoding="utf-8")
        all_milestones.extend(build_seed_vcp_milestones(profile, targets))

        manifest.extend(
            [
                {
                    "company_id": profile.company_id,
                    "company_name": profile.company_name,
                    "source_type": "csv",
                    "doc_type": "financials_monthly",
                    "path": str(csv_path),
                },
                {
                    "company_id": profile.company_id,
                    "company_name": profile.company_name,
                    "source_type": "excel",
                    "doc_type": "financials_monthly",
                    "path": str(xlsx_path),
                },
                {
                    "company_id": profile.company_id,
                    "company_name": profile.company_name,
                    "source_type": "markdown",
                    "doc_type": "ic_memo",
                    "path": str(memo_path),
                },
            ]
        )

    (PROCESSED_DIR / "synthetic_vcp_milestones_seed.json").write_text(
        json.dumps(all_milestones, indent=2), encoding="utf-8"
    )
    (PROCESSED_DIR / "synthetic_source_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    print("Synthetic data generated successfully.")
    print(f"Companies: {len(profiles)}  (performers: {sum(p.is_performer for p in profiles)})")
    print(f"Financial files: {len(profiles) * 2}")
    print(f"IC memo markdown files: {len(profiles)}")
    print(f"Seed VCP milestones: {len(all_milestones)}")


if __name__ == "__main__":
    main()
