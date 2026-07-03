import os
import time
from typing import Dict, List, Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

SEC_BASE_URL = "https://data.sec.gov/api/xbrl/companyfacts"
SEC_USER_AGENT = os.getenv(
    "SEC_USER_AGENT",
    "value-creation-copilot contact@example.com",
)

HEADERS = {
    "User-Agent": SEC_USER_AGENT,
    "Accept-Encoding": "gzip, deflate",
    "Host": "data.sec.gov",
}

METRIC_TAGS = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
    ],
    "net_income": [
        "NetIncomeLoss",
    ],
    "gross_profit": [
        "GrossProfit",
    ],
    # SaaS/subscription ARR proxies: Remaining Performance Obligation (RPO, post-ASC 606)
    # and deferred-revenue tags. Not every filer discloses these (RPO is optional under
    # ASC 606's one-year practical expedient), so this category is sparsely populated for
    # non-SaaS filers and that's fine — it's an additive proxy, not a required field.
    "arr_proxy": [
        "RevenueRemainingPerformanceObligation",
        "ContractWithCustomerLiabilityCurrent",
        "DeferredRevenueCurrent",
    ],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "assets_current": [
        "AssetsCurrent",
    ],
    "liabilities_current": [
        "LiabilitiesCurrent",
    ],
    "debt_current": [
        "ShortTermBorrowings",
        "ShortTermDebt",
        "CurrentPortionOfLongTermDebt",
    ],
    "debt_noncurrent": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ],
}


def normalize_cik(cik: str) -> str:
    cik = str(cik).strip().replace("-", "")
    return cik.zfill(10)


def fetch_company_facts(cik: str) -> Dict:
    cik = normalize_cik(cik)
    url = f"{SEC_BASE_URL}/CIK{cik}.json"

    response = requests.get(url, headers=HEADERS, timeout=30)
    response.raise_for_status()

    time.sleep(0.15)
    return response.json()


def _get_usd_facts(company_facts: Dict, tag: str) -> List[Dict]:
    try:
        tag_obj = company_facts["facts"]["us-gaap"][tag]
        units = tag_obj.get("units", {})

        if "USD" in units:
            return units["USD"]

        # Some metrics may use shares, pure, or other units.
        # For this project we mainly need USD values.
        return []
    except KeyError:
        return []


def _facts_to_quarterly_df(
    company_facts: Dict,
    metric_name: str,
    tags: List[str],
) -> pd.DataFrame:
    rows = []

    for tag in tags:
        facts = _get_usd_facts(company_facts, tag)

        for item in facts:
            form = item.get("form")
            fp = item.get("fp")
            end = item.get("end")
            val = item.get("val")
            filed = item.get("filed")
            frame = item.get("frame")

            if form not in {"10-Q", "10-K"}:
                continue

            if end is None or val is None:
                continue

            # Prefer quarterly facts. Some annual values can duplicate periods.
            is_quarterly = False
            if fp in {"Q1", "Q2", "Q3", "Q4"}:
                is_quarterly = True
            if isinstance(frame, str) and "Q" in frame:
                is_quarterly = True

            if not is_quarterly:
                continue

            rows.append(
                {
                    "metric": metric_name,
                    "tag": tag,
                    "period_end": end,
                    "value": float(val),
                    "form": form,
                    "fp": fp,
                    "fy": item.get("fy"),
                    "filed": filed,
                    "frame": frame,
                }
            )

        # if rows:
        #     # Use first tag that returns usable data.
        #     break

    if not rows:
        return pd.DataFrame(
            columns=[
                "metric",
                "tag",
                "period_end",
                "value",
                "form",
                "fp",
                "fy",
                "filed",
                "frame",
            ]
        )

    df = pd.DataFrame(rows)
    df["period_end"] = pd.to_datetime(df["period_end"])
    df["filed"] = pd.to_datetime(df["filed"], errors="coerce")

    # If duplicates exist for same period, keep latest filed version.
    df = (
        df.sort_values(["period_end", "filed"])
        .drop_duplicates(subset=["metric", "period_end"], keep="last")
        .sort_values("period_end")
        .reset_index(drop=True)
    )

    return df


def fetch_kpi_long(cik: str) -> pd.DataFrame:
    company_facts = fetch_company_facts(cik)

    all_metric_dfs = []
    for metric_name, tags in METRIC_TAGS.items():
        metric_df = _facts_to_quarterly_df(company_facts, metric_name, tags)
        if not metric_df.empty:
            all_metric_dfs.append(metric_df)

    if not all_metric_dfs:
        return pd.DataFrame()

    return pd.concat(all_metric_dfs, ignore_index=True)


def fetch_kpi_wide(cik: str, limit_quarters: Optional[int] = 60) -> pd.DataFrame:
    long_df = fetch_kpi_long(cik)

    if long_df.empty:
        return pd.DataFrame()

    wide = (
        long_df.pivot_table(
            index="period_end",
            columns="metric",
            values="value",
            aggfunc="last",
        )
        .reset_index()
        .sort_values("period_end")
    )

    wide.columns.name = None

    # Derived metrics
    if {"assets_current", "liabilities_current"}.issubset(wide.columns):
        wide["working_capital"] = wide["assets_current"] - wide["liabilities_current"]

    debt_cols = [c for c in ["debt_current", "debt_noncurrent"] if c in wide.columns]
    if debt_cols:
        wide["total_debt"] = wide[debt_cols].fillna(0).sum(axis=1)

    if {"total_debt", "cash"}.issubset(wide.columns):
        wide["net_debt"] = wide["total_debt"] - wide["cash"]

    # EBITDA is often not directly available in standard XBRL.
    # For Week 1 demo, operating_income is used as the first operating proxy.
    if "operating_income" in wide.columns and "ebitda_proxy" not in wide.columns:
        wide["ebitda_proxy"] = wide["operating_income"]

    if limit_quarters:
        wide = wide.tail(limit_quarters)

    return wide.reset_index(drop=True)


def save_edgar_kpis(cik: str, output_path: str) -> str:
    df = fetch_kpi_wide(cik)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


if __name__ == "__main__":
    test_cik = os.getenv("DEFAULT_CIK", "0000320193")
    df = fetch_kpi_wide(test_cik)
    print(df.tail())
    print(f"Rows: {len(df)}")