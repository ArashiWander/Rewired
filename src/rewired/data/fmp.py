"""Financial Modeling Prep (FMP) API client.

Provides fundamental data, financial statements, earnings, and company
profiles.  Falls back gracefully when the API key is missing or rate-limited.

Environment variable: FMP_API_KEY
Docs: https://site.financialmodelingprep.com/developer/docs
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

_BASE_URL = "https://financialmodelingprep.com/api/v3"
_TIMEOUT = 15  # seconds


# ── helpers ──────────────────────────────────────────────────────────────


def is_configured() -> bool:
    """Return True when a usable FMP API key is present."""
    key = os.environ.get("FMP_API_KEY", "")
    return bool(key and not key.startswith("your_"))


def _api_key() -> str:
    return os.environ.get("FMP_API_KEY", "")


def _get(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    """Execute a GET against the FMP API and return parsed JSON.

    Raises ``RuntimeError`` on HTTP errors so callers can decide how to
    degrade.
    """
    params = dict(params or {})
    params["apikey"] = _api_key()
    url = f"{_BASE_URL}/{endpoint}"
    resp = requests.get(url, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ── company profile ─────────────────────────────────────────────────────


def get_profile(ticker: str) -> dict[str, Any]:
    """Fetch a company profile (sector, industry, mktCap, description …).

    Returns an empty dict on failure.
    """
    if not is_configured():
        return {}
    try:
        data = _get(f"profile/{ticker.upper()}")
        return data[0] if data else {}
    except Exception:
        return {}


def get_profiles(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-fetch profiles for multiple tickers.

    FMP supports comma-separated tickers in one call.
    """
    if not is_configured() or not tickers:
        return {}
    try:
        joined = ",".join(t.upper() for t in tickers)
        data = _get(f"profile/{joined}")
        return {item["symbol"]: item for item in (data or [])}
    except Exception:
        return {}


# ── financial statements ─────────────────────────────────────────────────


def get_income_statement(
    ticker: str,
    period: str = "annual",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Fetch income statements (annual or quarter).

    Returns newest-first list.
    """
    if not is_configured():
        return []
    try:
        return _get(f"income-statement/{ticker.upper()}", {"period": period, "limit": limit}) or []
    except Exception:
        return []


def get_balance_sheet(
    ticker: str,
    period: str = "annual",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Fetch balance sheets."""
    if not is_configured():
        return []
    try:
        return _get(f"balance-sheet-statement/{ticker.upper()}", {"period": period, "limit": limit}) or []
    except Exception:
        return []


def get_cash_flow(
    ticker: str,
    period: str = "annual",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Fetch cash flow statements (contains capitalExpenditure)."""
    if not is_configured():
        return []
    try:
        return _get(f"cash-flow-statement/{ticker.upper()}", {"period": period, "limit": limit}) or []
    except Exception:
        return []


# ── key metrics & ratios ────────────────────────────────────────────────


def get_key_metrics(
    ticker: str,
    period: str = "annual",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Fetch key financial metrics (PE, ROE, FCF yield …)."""
    if not is_configured():
        return []
    try:
        return _get(f"key-metrics/{ticker.upper()}", {"period": period, "limit": limit}) or []
    except Exception:
        return []


def get_financial_ratios(
    ticker: str,
    period: str = "annual",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Fetch financial ratios (gross margin, operating margin …)."""
    if not is_configured():
        return []
    try:
        return _get(f"ratios/{ticker.upper()}", {"period": period, "limit": limit}) or []
    except Exception:
        return []


# ── earnings & estimates ─────────────────────────────────────────────────


def get_earnings_surprises(ticker: str) -> list[dict[str, Any]]:
    """Fetch historical earnings surprises (actual vs estimated EPS)."""
    if not is_configured():
        return []
    try:
        return _get(f"earnings-surprises/{ticker.upper()}") or []
    except Exception:
        return []


def get_analyst_estimates(
    ticker: str,
    period: str = "annual",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Fetch consensus analyst estimates."""
    if not is_configured():
        return []
    try:
        return _get(f"analyst-estimates/{ticker.upper()}", {"period": period, "limit": limit}) or []
    except Exception:
        return []


# ── real-time quote ──────────────────────────────────────────────────────


def get_quote(ticker: str) -> dict[str, Any]:
    """Fetch a real-time quote (price, change, volume …)."""
    if not is_configured():
        return {}
    try:
        data = _get(f"quote/{ticker.upper()}")
        return data[0] if data else {}
    except Exception:
        return {}


def get_quotes(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Batch-fetch quotes for multiple tickers."""
    if not is_configured() or not tickers:
        return {}
    try:
        joined = ",".join(t.upper() for t in tickers)
        data = _get(f"quote/{joined}")
        return {item["symbol"]: item for item in (data or [])}
    except Exception:
        return {}


# ── CAPEX-specific helpers ───────────────────────────────────────────────


def get_capex_history(
    ticker: str,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Return a simplified CAPEX history from cash-flow statements.

    Each entry has: date, capex (positive = spending), revenue, capex_pct_revenue.
    Most recent first.
    """
    cfs = get_cash_flow(ticker, period="quarter", limit=limit)
    if not cfs:
        return []

    history: list[dict[str, Any]] = []
    for cf in cfs:
        capex_raw = cf.get("capitalExpenditure", 0) or 0
        capex = abs(capex_raw)  # FMP reports CAPEX as negative
        revenue = cf.get("revenue", 0) or 0
        history.append({
            "date": cf.get("date", ""),
            "period": cf.get("period", ""),
            "capex": capex,
            "revenue": revenue,
            "capex_pct_revenue": round(capex / revenue * 100, 2) if revenue else 0.0,
            "free_cash_flow": cf.get("freeCashFlow", 0) or 0,
        })
    return history


def get_big4_capex_summary() -> dict[str, list[dict[str, Any]]]:
    """Fetch CAPEX history for the Big 4 hyperscalers.

    Returns ``{ticker: [capex_history_entries]}`` for
    MSFT, GOOGL, AMZN, META.
    """
    big4 = ["MSFT", "GOOGL", "AMZN", "META"]
    return {t: get_capex_history(t) for t in big4}


# ── company search ───────────────────────────────────────────────────────


def search_ticker(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search for a ticker by company name or partial symbol.

    Returns list of ``{symbol, name, currency, stockExchange}``.
    """
    if not is_configured():
        return []
    try:
        return _get("search", {"query": query, "limit": limit}) or []
    except Exception:
        return []
