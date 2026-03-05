"""EUR/USD conversion via yfinance."""

from __future__ import annotations

import yfinance as yf


_cached_rate: float | None = None


def get_eurusd_rate() -> float:
    """Fetch current EUR/USD exchange rate. Cached per session."""
    global _cached_rate
    if _cached_rate is not None:
        return _cached_rate

    ticker = yf.Ticker("EURUSD=X")
    data = ticker.history(period="1d")
    if data.empty:
        # Fallback to a reasonable default
        _cached_rate = 1.08
    else:
        _cached_rate = float(data["Close"].iloc[-1])
    return _cached_rate


def usd_to_eur(usd_amount: float) -> float:
    """Convert USD to EUR."""
    rate = get_eurusd_rate()
    return usd_amount / rate


def eur_to_usd(eur_amount: float) -> float:
    """Convert EUR to USD."""
    rate = get_eurusd_rate()
    return eur_amount * rate


def clear_cache() -> None:
    """Clear cached FX rate (for refreshing)."""
    global _cached_rate
    _cached_rate = None
