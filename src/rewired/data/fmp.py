"""Financial Modeling Prep (FMP) API client — **stable** endpoint.

Provides fundamental data, financial statements, earnings, and company
profiles.  Falls back gracefully when the API key is missing or rate-limited.

As of 2025-09 FMP deprecated all ``/api/v3`` legacy endpoints.  This module
targets the ``/stable/`` base with ``?symbol=`` query-parameter syntax.

Environment variable: FMP_API_KEY
Docs: https://site.financialmodelingprep.com/developer/docs
"""

from __future__ import annotations

import logging
import os
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

_BASE_URL = "https://financialmodelingprep.com/stable"
_TIMEOUT = 15  # seconds

logger = logging.getLogger(__name__)


# ── helpers ──────────────────────────────────────────────────────────────


def is_configured() -> bool:
    """Return True when a usable FMP API key is present."""
    key = os.environ.get("FMP_API_KEY", "")
    return bool(key and not key.startswith("your_"))


def _api_key() -> str:
    return os.environ.get("FMP_API_KEY", "")


def _get(endpoint: str, params: dict[str, Any] | None = None) -> Any:
    """Execute a GET against the FMP **stable** API and return parsed JSON.

    The stable API uses ``/stable/{endpoint}?symbol=X&apikey=…`` style.
    Retries on transient network errors (timeouts, connection resets).
    Raises ``RuntimeError`` on HTTP errors so callers can decide how to
    degrade.
    """
    from rewired.resilience import retry_on_transient

    @retry_on_transient
    def _do_get():
        params_ = dict(params or {})
        params_["apikey"] = _api_key()
        url = f"{_BASE_URL}/{endpoint}"
        resp = requests.get(url, params=params_, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()

    return _do_get()


# ── company profile ─────────────────────────────────────────────────────


def get_profile(ticker: str) -> dict[str, Any]:
    """Fetch a company profile (sector, industry, mktCap, description …).

    Returns an empty dict on failure.
    """
    if not is_configured():
        return {}
    try:
        data = _get("profile", {"symbol": ticker.upper()})
        return data[0] if data else {}
    except Exception:
        return {}


def get_profiles(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch profiles for multiple tickers (sequential calls).

    The stable API does not support comma-separated batch profiles, so
    each ticker is fetched individually.
    """
    if not is_configured() or not tickers:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for t in tickers:
        p = get_profile(t)
        if p:
            result[p.get("symbol", t.upper())] = p
    return result


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
        return _get("income-statement", {"symbol": ticker.upper(), "period": period, "limit": limit}) or []
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
        return _get("balance-sheet-statement", {"symbol": ticker.upper(), "period": period, "limit": limit}) or []
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
        data = _get("cash-flow-statement", {"symbol": ticker.upper(), "period": period, "limit": limit}) or []
        if data or period != "quarter" or limit <= 4:
            return data

        # The stable API can return an empty payload for larger quarterly
        # limits even when recent quarterly cash-flow data exists. Retry with
        # four quarters so CAPEX helpers remain usable on lower-tier plans.
        logger.debug(
            "cash-flow quarterly request returned empty for %s at limit=%s; retrying with limit=4",
            ticker,
            limit,
        )
        return _get("cash-flow-statement", {"symbol": ticker.upper(), "period": period, "limit": 4}) or []
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 402 and period == "quarter" and limit > 4:
            logger.debug(
                "cash-flow quarterly request premium-gated for %s at limit=%s; retrying with limit=4",
                ticker,
                limit,
            )
            try:
                return _get("cash-flow-statement", {"symbol": ticker.upper(), "period": period, "limit": 4}) or []
            except Exception:
                return []
        return []
    except Exception:
        return []


# ── key metrics & ratios ────────────────────────────────────────────────


def get_key_metrics(
    ticker: str,
    period: str = "annual",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Fetch key financial metrics (PE, ROE, FCF yield …).

    Note: quarterly period requires a premium FMP plan.  Falls back to
    annual if the quarterly request is rejected (HTTP 402).
    """
    if not is_configured():
        return []
    try:
        return _get("key-metrics", {"symbol": ticker.upper(), "period": period, "limit": limit}) or []
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 402 and period != "annual":
            logger.debug("key-metrics quarterly premium-gated for %s, falling back to annual", ticker)
            try:
                return _get("key-metrics", {"symbol": ticker.upper(), "period": "annual", "limit": limit}) or []
            except Exception:
                return []
        return []
    except Exception:
        return []


def get_financial_ratios(
    ticker: str,
    period: str = "annual",
    limit: int = 4,
) -> list[dict[str, Any]]:
    """Fetch financial ratios (gross margin, operating margin …).

    Note: quarterly period requires a premium FMP plan.  Falls back to
    annual if the quarterly request is rejected (HTTP 402).
    """
    if not is_configured():
        return []
    try:
        return _get("ratios", {"symbol": ticker.upper(), "period": period, "limit": limit}) or []
    except requests.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 402 and period != "annual":
            logger.debug("ratios quarterly premium-gated for %s, falling back to annual", ticker)
            try:
                return _get("ratios", {"symbol": ticker.upper(), "period": "annual", "limit": limit}) or []
            except Exception:
                return []
        return []
    except Exception:
        return []


# ── earnings & estimates ─────────────────────────────────────────────────


def get_earnings_surprises(ticker: str) -> list[dict[str, Any]]:
    """Fetch historical earnings surprises (actual vs estimated EPS).

    This endpoint may not be available on all FMP plans under the stable
    API.  Returns an empty list when the endpoint is missing (404).
    """
    if not is_configured():
        return []
    try:
        return _get("earnings-surprises", {"symbol": ticker.upper()}) or []
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
        return _get("analyst-estimates", {"symbol": ticker.upper(), "period": period, "limit": limit}) or []
    except Exception:
        return []


# ── real-time quote ──────────────────────────────────────────────────────


def get_quote(ticker: str) -> dict[str, Any]:
    """Fetch a real-time quote (price, change, volume …)."""
    if not is_configured():
        return {}
    try:
        data = _get("quote", {"symbol": ticker.upper()})
        return data[0] if data else {}
    except Exception:
        return {}


def get_quotes(tickers: list[str]) -> dict[str, dict[str, Any]]:
    """Fetch quotes for multiple tickers.

    The stable API may not support comma-separated batch quotes on all
    plans, so we fall back to sequential calls when needed.
    """
    if not is_configured() or not tickers:
        return {}
    # Try comma-separated first (works on some plans)
    try:
        joined = ",".join(t.upper() for t in tickers)
        data = _get("quote", {"symbol": joined})
        if data:
            return {item["symbol"]: item for item in data}
    except Exception:
        pass
    # Fallback: sequential
    result: dict[str, dict[str, Any]] = {}
    for t in tickers:
        q = get_quote(t)
        if q:
            result[q.get("symbol", t.upper())] = q
    return result


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

    Uses the ``/stable/search-name`` endpoint.
    Returns list of ``{symbol, name, currency, exchangeFullName}``.
    """
    if not is_configured():
        return []
    try:
        return _get("search-name", {"query": query, "limit": limit}) or []
    except Exception:
        return []
