"""Market sentiment data from yfinance."""

from __future__ import annotations

from datetime import datetime

import yfinance as yf

from rewired.models.signals import SignalColor, SignalReading


def get_sentiment_readings() -> list[SignalReading]:
    """Fetch sentiment signal readings."""
    readings = []
    now = datetime.now()

    readings.extend(_vix_reading(now))
    readings.extend(_sp500_vs_200ma(now))
    readings.extend(_vix_term_structure(now))

    return readings


def _vix_reading(now: datetime) -> list[SignalReading]:
    """VIX level as fear gauge."""
    try:
        vix = yf.Ticker("^VIX")
        data = vix.history(period="5d")
        if data.empty:
            return []

        value = float(data["Close"].iloc[-1])
        if value < 16:
            color = SignalColor.GREEN
        elif value < 22:
            color = SignalColor.YELLOW
        elif value < 30:
            color = SignalColor.ORANGE
        else:
            color = SignalColor.RED

        return [SignalReading(
            name="VIX",
            value=value,
            color=color,
            timestamp=now,
            source="yfinance:^VIX",
            detail=f"VIX: {value:.1f}",
        )]
    except Exception:
        return []


def _sp500_vs_200ma(now: datetime) -> list[SignalReading]:
    """S&P 500 distance from 200-day moving average."""
    try:
        sp = yf.Ticker("^GSPC")
        hist = sp.history(period="1y")
        if hist.empty or len(hist) < 200:
            return []

        price = float(hist["Close"].iloc[-1])
        ma200 = float(hist["Close"].rolling(200).mean().iloc[-1])
        pct = ((price / ma200) - 1) * 100

        if pct > 2:
            color = SignalColor.GREEN
        elif pct > -2:
            color = SignalColor.YELLOW
        elif pct > -8:
            color = SignalColor.ORANGE
        else:
            color = SignalColor.RED

        return [SignalReading(
            name="S&P 500 vs 200MA",
            value=pct,
            color=color,
            timestamp=now,
            source="yfinance:^GSPC",
            detail=f"S&P {pct:+.1f}% vs 200MA",
        )]
    except Exception:
        return []


def _vix_term_structure(now: datetime) -> list[SignalReading]:
    """VIX term structure: VIX vs VIX9D (9-day VIX).

    Contango (VIX > VIX9D) = normal/calm.
    Backwardation (VIX < VIX9D) = fear/hedging demand.
    """
    try:
        vix_data = yf.Ticker("^VIX").history(period="5d")
        vix9d_data = yf.Ticker("^VIX9D").history(period="5d")

        if vix_data.empty or vix9d_data.empty:
            return []

        vix = float(vix_data["Close"].iloc[-1])
        vix9d = float(vix9d_data["Close"].iloc[-1])
        spread = vix - vix9d  # Positive = contango = calm

        if spread > 2:
            color = SignalColor.GREEN
        elif spread > 0:
            color = SignalColor.YELLOW
        elif spread > -3:
            color = SignalColor.ORANGE
        else:
            color = SignalColor.RED

        return [SignalReading(
            name="VIX Term Structure",
            value=spread,
            color=color,
            timestamp=now,
            source="yfinance:VIX/VIX9D",
            detail=f"VIX-VIX9D spread: {spread:+.1f}",
        )]
    except Exception:
        return []
