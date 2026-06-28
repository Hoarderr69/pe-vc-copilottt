import os
from typing import Any, Dict, Optional

import yfinance as yf
from curl_cffi import requests as curl_requests
from dotenv import load_dotenv

load_dotenv()


def _as_bool(value: str, default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() not in {"false", "0", "no", "n"}


def _safe_get(info: Dict[str, Any], key: str) -> Optional[Any]:
    value = info.get(key)
    if value in ["None", "N/A", "NaN", "", None]:
        return None
    return value


def _get_yfinance_session():
    """
    Corporate networks sometimes break Yahoo/yfinance SSL verification because
    traffic is intercepted by an enterprise proxy.

    For local demo only:
        YFINANCE_VERIFY_SSL=false

    For normal environments:
        YFINANCE_VERIFY_SSL=true
    """
    verify_ssl = _as_bool(os.getenv("YFINANCE_VERIFY_SSL", "true"))

    return curl_requests.Session(
        impersonate="chrome",
        verify=verify_ssl,
    )


def fetch_market_snapshot(ticker: str) -> Dict[str, Any]:
    ticker = ticker.upper().strip()

    default_exit_multiple = float(os.getenv("DEFAULT_EXIT_EBITDA_MULTIPLE", "15.0"))

    try:
        session = _get_yfinance_session()
        obj = yf.Ticker(ticker, session=session)

        info = obj.info or {}

        return {
            "ticker": ticker,
            "company_name": _safe_get(info, "longName"),
            "sector": _safe_get(info, "sector"),
            "industry": _safe_get(info, "industry"),
            "market_cap": _safe_get(info, "marketCap"),
            "enterprise_value": _safe_get(info, "enterpriseValue"),
            "enterprise_to_revenue": _safe_get(info, "enterpriseToRevenue"),
            "enterprise_to_ebitda": _safe_get(info, "enterpriseToEbitda"),
            "trailing_pe": _safe_get(info, "trailingPE"),
            "currency": _safe_get(info, "currency"),
            "source": "yfinance",
            "is_fallback": False,
        }

    except Exception as exc:
        # Do not block the full Week 1 pipeline if Yahoo is blocked.
        # EDGAR is the real core financial source. Multiples can be demo defaults.
        return {
            "ticker": ticker,
            "company_name": None,
            "sector": None,
            "industry": None,
            "market_cap": None,
            "enterprise_value": None,
            "enterprise_to_revenue": None,
            "enterprise_to_ebitda": default_exit_multiple,
            "trailing_pe": None,
            "currency": "USD",
            "source": "fallback_default_multiple",
            "is_fallback": True,
            "warning": str(exc),
        }


def fetch_price_history(ticker: str, period: str = "5y") -> Dict[str, Any]:
    ticker = ticker.upper().strip()

    try:
        session = _get_yfinance_session()
        obj = yf.Ticker(ticker, session=session)

        hist = obj.history(period=period)
        hist = hist.reset_index()

        return {
            "ticker": ticker,
            "period": period,
            "rows": len(hist),
            "data": hist.tail(20).to_dict(orient="records"),
            "source": "yfinance",
            "is_fallback": False,
        }

    except Exception as exc:
        return {
            "ticker": ticker,
            "period": period,
            "rows": 0,
            "data": [],
            "source": "fallback_empty_history",
            "is_fallback": True,
            "warning": str(exc),
        }


if __name__ == "__main__":
    print(fetch_market_snapshot("AAPL"))