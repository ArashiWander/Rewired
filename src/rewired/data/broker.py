"""Trading 212 broker API client — READ-ONLY live data.

Provides account summary and positions from the Trading 212 Equity API.
This is the SINGLE SOURCE OF TRUTH for portfolio data. There is no
offline fallback, no local cache, no portfolio.json. If T212 is
unreachable, ``BrokerUnavailableError`` is raised and the pipeline halts.

Environment variables:
- ``TRADING212_API_KEY_ID`` or legacy ``TRADING212_API_KEY``
- ``TRADING212_SECRET_KEY`` or legacy ``TRADING212_API_SECRET``

Docs: https://docs.trading212.com
"""

from __future__ import annotations

import base64
import logging
import os
from datetime import datetime
from typing import Any

import requests
from dotenv import load_dotenv

from rewired.models.portfolio import Portfolio, Position
from rewired.models.signals import BrokerUnavailableError

load_dotenv()

_BASE_URL = "https://live.trading212.com/api/v0"
_TIMEOUT = 15  # seconds

logger = logging.getLogger(__name__)

# ── Exchange suffix mapping: T212 exchange code → Yahoo-style suffix ─────
# T212 tickers follow the pattern: SYMBOL_EXCHANGE_TYPE (e.g. AAPL_US_EQ)
_EXCHANGE_SUFFIX: dict[str, str] = {
    "US": "",       # US equities: AAPL_US_EQ → AAPL
    "LSE": ".L",    # London Stock Exchange: QQQS_LSE_EQ → QQQS.L
    "XETRA": ".DE", # Frankfurt: SAP_XETRA_EQ → SAP.DE
    "EPA": ".PA",   # Euronext Paris
    "AMS": ".AS",   # Euronext Amsterdam: ASML_AMS_EQ → ASML.AS
    "MIL": ".MI",   # Milan
    "BME": ".MC",   # Madrid
    "SWX": ".SW",   # Swiss Exchange
    "TSE": ".TO",   # Toronto
    "ASX": ".AX",   # Australian
    "HKG": ".HK",   # Hong Kong
}

# ── Exchange → instrument currency ──────────────────────────────────────
# T212 returns averagePricePaid and currentPrice in instrument currency.
# EUR-denominated exchanges need no FX conversion.
_EXCHANGE_CURRENCY: dict[str, str] = {
    "US": "USD",
    "LSE": "GBP",
    "XETRA": "EUR",
    "EPA": "EUR",
    "AMS": "EUR",
    "MIL": "EUR",
    "BME": "EUR",
    "SWX": "CHF",
    "TSE": "CAD",
    "ASX": "AUD",
    "HKG": "HKD",
}


# ── Auth & plumbing ─────────────────────────────────────────────────────


def is_configured() -> bool:
    """Return True when a usable T212 key pair is present."""
    key_id = os.environ.get("TRADING212_API_KEY_ID") or os.environ.get("TRADING212_API_KEY", "")
    secret = os.environ.get("TRADING212_SECRET_KEY") or os.environ.get("TRADING212_API_SECRET", "")
    return bool(
        key_id
        and secret
        and not key_id.startswith("your_")
        and not secret.startswith("your_")
    )


def _auth_header() -> str:
    key_id = os.environ.get("TRADING212_API_KEY_ID") or os.environ.get("TRADING212_API_KEY", "")
    secret = os.environ.get("TRADING212_SECRET_KEY") or os.environ.get("TRADING212_API_SECRET", "")

    if not key_id or key_id.startswith("your_"):
        raise BrokerUnavailableError(
            "TRADING212_API_KEY_ID not set or is a placeholder value"
        )
    if not secret or secret.startswith("your_"):
        raise BrokerUnavailableError(
            "TRADING212_SECRET_KEY not set or is a placeholder value"
        )

    credentials = f"{key_id}:{secret}".encode("utf-8")
    encoded = base64.b64encode(credentials).decode("ascii")
    return f"Basic {encoded}"


def _request(path: str) -> Any:
    """Execute a GET against the T212 Equity API.

    Raises ``BrokerUnavailableError`` on ANY failure — auth, network,
    timeout, unexpected status.  No silent degradation.
    """
    url = f"{_BASE_URL}/{path}"
    headers = {"Authorization": _auth_header()}

    try:
        resp = requests.get(url, headers=headers, timeout=_TIMEOUT)
    except requests.ConnectionError as exc:
        raise BrokerUnavailableError(
            f"T212 connection failed: {exc}"
        ) from exc
    except requests.Timeout as exc:
        raise BrokerUnavailableError(
            f"T212 request timed out ({_TIMEOUT}s): {exc}"
        ) from exc
    except requests.RequestException as exc:
        raise BrokerUnavailableError(
            f"T212 request error: {exc}"
        ) from exc

    if resp.status_code in (401, 403):
        raise BrokerUnavailableError(
            f"T212 auth rejected (HTTP {resp.status_code}). "
            "Check TRADING212_API_KEY_ID / TRADING212_SECRET_KEY."
        )

    if resp.status_code == 429:
        raise BrokerUnavailableError(
            "T212 rate limit exceeded (HTTP 429). Try again later."
        )

    if resp.status_code != 200:
        raise BrokerUnavailableError(
            f"T212 unexpected HTTP {resp.status_code}: "
            f"{resp.text[:200]}"
        )

    try:
        return resp.json()
    except ValueError as exc:
        raise BrokerUnavailableError(
            f"T212 returned invalid JSON: {exc}"
        ) from exc


# ── Ticker normalisation ────────────────────────────────────────────────


def normalize_t212_ticker(t212_ticker: str) -> str:
    """Convert a T212 instrument ticker to the format used in universe.yaml.

    T212 format: ``SYMBOL_EXCHANGE_TYPE`` (e.g. ``AAPL_US_EQ``).
    Universe format: ``SYMBOL`` or ``SYMBOL.SUFFIX`` (e.g. ``AAPL``, ``QQQS.L``).

    Strategy: split from the right on ``_``, take the symbol and exchange
    parts, and map the exchange to a suffix.
    """
    parts = t212_ticker.rsplit("_", maxsplit=2)

    if len(parts) == 3:
        symbol, exchange, _ = parts
    elif len(parts) == 2:
        symbol, exchange = parts[0], parts[1]
    else:
        # Unknown format — return as-is
        return t212_ticker

    suffix = _EXCHANGE_SUFFIX.get(exchange, f".{exchange}")
    return f"{symbol}{suffix}"


# ── Public API ──────────────────────────────────────────────────────────


def get_account_summary() -> dict[str, float]:
    """Fetch account cash and value from T212.

    Returns dict with keys: ``total_value_eur``, ``cash_eur``, ``invested_eur``.
    Raises ``BrokerUnavailableError`` on any failure.
    """
    data = _request("equity/account/cash")

    cash = data.get("cash") or {}
    investments = data.get("investments") or {}

    return {
        "total_value_eur": float(data.get("totalValue", data.get("total", 0)) or 0),
        "cash_eur": float(cash.get("availableToTrade", data.get("free", 0)) or 0),
        "invested_eur": float(investments.get("currentValue", data.get("invested", 0)) or 0),
    }


def _extract_exchange(t212_ticker: str) -> str:
    """Extract the exchange code from a T212 ticker (e.g. 'US' from 'AAPL_US_EQ')."""
    parts = t212_ticker.rsplit("_", maxsplit=2)
    if len(parts) == 3:
        return parts[1]
    if len(parts) == 2:
        return parts[1]
    return "US"  # default assumption


def get_positions() -> list[dict[str, Any]]:
    """Fetch all open positions from T212.

    Returns a list of dicts with keys:
    ``ticker``, ``t212_ticker``, ``shares``, ``avg_cost_instrument``,
    ``current_price_instrument``, ``currency``, ``pnl_eur``,
    ``quantity_in_pies``, ``quantity_free``.

    Price fields (``avg_cost_instrument``, ``current_price_instrument``)
    are in the **instrument currency** (USD for US stocks, GBP for LSE,
    EUR for XETRA/AMS etc.).  The ``currency`` field identifies which.

    ``pnl_eur`` is extracted from ``walletImpact`` which T212 returns
    in the account base currency (EUR).

    Raises ``BrokerUnavailableError`` on any failure.
    """
    data = _request("equity/positions")

    positions = []
    for item in data:
        instrument = item.get("instrument") or {}
        t212_ticker = item.get("ticker") or instrument.get("ticker", "")
        ticker = normalize_t212_ticker(t212_ticker)
        exchange = _extract_exchange(t212_ticker)
        currency = instrument.get("currencyCode") or _EXCHANGE_CURRENCY.get(exchange, "USD")

        quantity = float(item.get("quantity", 0))
        avg_price = float(item.get("averagePricePaid", item.get("averagePrice", 0)) or 0)
        current_price = float(item.get("currentPrice", 0))

        # walletImpact: T212 may return a dict or a scalar (legacy).
        # When it's a dict, prefer the "investedValue" fields; when
        # scalar, it's the P&L in account currency (EUR).
        wi_raw = item.get("walletImpact", 0)
        if isinstance(wi_raw, dict):
            pnl_eur = float(wi_raw.get("result", wi_raw.get("ppl", 0)) or 0)
        else:
            pnl_eur = float(wi_raw or 0)

        quantity_in_pies = float(item.get("quantityInPies", 0))
        quantity_free = float(item.get("quantityAvailableForTrading", 0))

        positions.append({
            "ticker": ticker,
            "t212_ticker": t212_ticker,
            "shares": quantity,
            "avg_cost_instrument": avg_price,
            "current_price_instrument": current_price,
            "currency": currency,
            "pnl_eur": pnl_eur,
            "quantity_in_pies": quantity_in_pies,
            "quantity_free": quantity_free,
        })

    return positions


def _instrument_to_eur(amount: float, currency: str) -> float:
    """Convert an instrument-currency amount to EUR.

    EUR-denominated instruments pass through unchanged.
    USD and GBP use the yfinance-backed converters in ``data.fx``.
    Other currencies fall back to USD→EUR (acceptable approximation).
    """
    if currency == "EUR":
        return amount
    from rewired.data.fx import usd_to_eur, gbp_to_eur
    if currency == "GBP":
        return gbp_to_eur(amount)
    if currency == "USD":
        return usd_to_eur(amount)
    # Fallback: treat as USD (covers CHF, CAD, HKD etc.)
    return usd_to_eur(amount)


def get_portfolio() -> Portfolio:
    """Build a ``Portfolio`` model from live T212 data.

    This is the canonical function that replaces ``load_portfolio()`` from
    the deleted ``portfolio/manager.py``.  It calls T212 for account
    summary and positions, normalises tickers, and returns a ``Portfolio``
    object that the sizing engine can consume directly.

    Currency handling:
    - ``current_price_usd`` / ``avg_cost_usd``: raw instrument-currency
      prices from T212 (kept as "usd" for backward compat — actually
      the instrument's native currency).
    - ``current_price_eur`` / ``market_value_eur``: FX-converted to EUR
      using ``data.fx``.
    - ``unrealized_pnl_eur``: from T212 ``walletImpact`` (already EUR).

    Raises ``BrokerUnavailableError`` on ANY T212 failure.  No fallback.
    """
    summary = get_account_summary()
    raw_positions = get_positions()

    positions: dict[str, Position] = {}

    for rp in raw_positions:
        currency = rp["currency"]
        price_inst = rp["current_price_instrument"]
        avg_inst = rp["avg_cost_instrument"]
        shares = rp["shares"]

        price_eur = _instrument_to_eur(price_inst, currency)
        avg_eur = _instrument_to_eur(avg_inst, currency)
        mv_eur = round(price_eur * shares, 2)

        positions[rp["ticker"]] = Position(
            ticker=rp["ticker"],
            shares=shares,
            avg_cost_eur=round(avg_eur, 2),
            current_price_eur=round(price_eur, 2),
            market_value_eur=mv_eur,
            unrealized_pnl_eur=round(rp["pnl_eur"], 2),
            last_updated=datetime.now(),
            current_price_usd=price_inst,
            avg_cost_usd=avg_inst,
            quantity_in_pies=rp["quantity_in_pies"],
            quantity_free=rp["quantity_free"],
        )

    total_value = summary["total_value_eur"]

    # Calculate weights
    if total_value > 0:
        for pos in positions.values():
            pos.weight_pct = round((pos.market_value_eur / total_value) * 100, 2)

    return Portfolio(
        cash_eur=summary["cash_eur"],
        positions=positions,
        last_updated=datetime.now(),
    )


# ── Pies API (deprecated but operational) ──────────────────────────────


def get_pies_list() -> list[dict[str, Any]]:
    """Fetch all pies for the account.

    Returns list of dicts with keys: ``id``, ``cash``, ``progress``,
    ``status``.  Rate limit: 1 req / 30s.

    Raises ``BrokerUnavailableError`` on failure.
    """
    data = _request("equity/pies")
    return [
        {
            "id": int(pie.get("id", 0)),
            "cash": float(pie.get("cash", 0)),
            "progress": float(pie.get("progress", 0)),
            "status": pie.get("status", ""),
        }
        for pie in data
    ]


def get_pie_detail(pie_id: int) -> dict[str, Any]:
    """Fetch detailed info for a single pie.

    Returns dict with ``instruments`` list and ``settings`` dict.
    Each instrument has: ``ticker``, ``currentShare``, ``ownedQuantity``,
    ``result`` (P&L), ``expectedShare``, ``issues``.

    Rate limit: 1 req / 5s.

    Raises ``BrokerUnavailableError`` on failure.
    """
    data = _request(f"equity/pies/{pie_id}")
    instruments = []
    for inst in data.get("instruments", []):
        ticker_raw = inst.get("ticker", "")
        instruments.append({
            "ticker": normalize_t212_ticker(ticker_raw),
            "t212_ticker": ticker_raw,
            "current_share": float(inst.get("currentShare", 0)),
            "expected_share": float(inst.get("expectedShare", 0)),
            "owned_quantity": float(inst.get("ownedQuantity", 0)),
            "result": float(inst.get("result", 0)),
            "issues": inst.get("issues", []),
        })

    settings = data.get("settings", {})
    return {
        "instruments": instruments,
        "settings": {
            "name": settings.get("name", ""),
            "id": int(settings.get("id", pie_id)),
            "goal": float(settings.get("goal", 0)),
            "instrument_shares": settings.get("instrumentShares", {}),
        },
    }
