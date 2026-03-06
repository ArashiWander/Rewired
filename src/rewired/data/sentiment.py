"""Market sentiment data from yfinance.

Provides the data points required by the boolean rules engine:
- VIX absolute level (with 5MA/20MA trend metadata)
- VIX Term Structure: spot VIX vs VIX3M (3-month implied volatility)
  Contango (VIX3M > VIX) = normal/calm.
  Backwardation (VIX > VIX3M) = panic/institutional hedging.
"""

from __future__ import annotations

from datetime import datetime

import yfinance as yf

from rewired.models.signals import SignalColor, SignalReading


def get_sentiment_readings() -> list[SignalReading]:
    """Fetch sentiment signal readings for the rules engine."""
    readings = []
    now = datetime.now()

    readings.extend(_vix_reading(now))
    readings.extend(_vix_term_structure(now))

    return readings


def _vix_reading(now: datetime) -> list[SignalReading]:
    """VIX level with 5MA/20MA trend metadata.

    Blueprint thresholds: <18 GREEN, 18-25 YELLOW, 25-35 ORANGE, >35 RED.
    The rules engine uses MA crossover (5MA > 20MA) to detect expanding vol.
    """
    try:
        vix = yf.Ticker("^VIX")
        data = vix.history(period="3mo")
        if data.empty:
            return []

        value = float(data["Close"].iloc[-1])

        # Compute 5MA and 20MA for trend detection (used by rules engine)
        ma5 = None
        ma20 = None
        ma5_above_ma20 = False
        if len(data) >= 20:
            ma5 = float(data["Close"].rolling(5).mean().iloc[-1])
            ma20 = float(data["Close"].rolling(20).mean().iloc[-1])
            ma5_above_ma20 = ma5 > ma20

        # Blueprint thresholds for per-reading color (informational)
        if value < 18:
            color = SignalColor.GREEN
        elif value <= 25:
            color = SignalColor.YELLOW
        elif value <= 35:
            color = SignalColor.ORANGE
        else:
            color = SignalColor.RED

        return [SignalReading(
            name="VIX",
            value=value,
            color=color,
            timestamp=now,
            source="yfinance:^VIX",
            detail=f"VIX: {value:.1f}" + (f" (5MA>20MA)" if ma5_above_ma20 else ""),
            metadata={
                "ma5_above_ma20": ma5_above_ma20,
                "ma5": ma5,
                "ma20": ma20,
            },
        )]
    except Exception:
        return []


def _vix_term_structure(now: datetime) -> list[SignalReading]:
    """VIX term structure: spot VIX vs VIX3M (3-month implied vol).

    spread = VIX3M - VIX:
      Positive = contango = normal market = GREEN/YELLOW
      Negative = backwardation = institutional panic = ORANGE/RED
    """
    try:
        vix_data = yf.Ticker("^VIX").history(period="5d")
        vix3m_data = yf.Ticker("^VIX3M").history(period="5d")

        if vix_data.empty or vix3m_data.empty:
            return []

        vix = float(vix_data["Close"].iloc[-1])
        vix3m = float(vix3m_data["Close"].iloc[-1])
        # Positive spread = contango = calm; Negative = backwardation = panic
        spread = vix3m - vix

        if spread > 2:
            color = SignalColor.GREEN
        elif spread > 0:
            color = SignalColor.YELLOW
        elif spread > -3:
            color = SignalColor.ORANGE
        else:
            color = SignalColor.RED

        structure = "contango" if spread > 0 else "backwardation"
        return [SignalReading(
            name="VIX Term Structure",
            value=spread,
            color=color,
            timestamp=now,
            source="yfinance:VIX/VIX3M",
            detail=f"VIX3M-VIX spread: {spread:+.1f} ({structure})",
            metadata={"vix_spot": vix, "vix3m": vix3m, "spread": spread, "structure": structure},
        )]
    except Exception:
        return []
