"""Market sentiment data from yfinance — Dual Radar System.

Radar A — Macro Term Structure (S&P 500):
  VIX Term Structure: spot ^VIX vs ^VIX3M (3-month implied vol).
  Contango (VIX3M > VIX) = normal/calm.
  Backwardation (VIX > VIX3M) = panic/institutional hedging.

Radar B — Tech Sector Velocity & Level (NASDAQ-100):
  VXN Level & Velocity: ^VXN absolute level, 5MA/20MA trend,
  and 3-trading-day velocity spike detection.
"""

from __future__ import annotations

import logging
from datetime import datetime

import yfinance as yf

from rewired.models.signals import SignalColor, SignalReading

logger = logging.getLogger(__name__)


def get_sentiment_readings() -> list[SignalReading]:
    """Fetch sentiment signal readings for the rules engine.

    Circuit breaker: if VIX data is completely unavailable,
    logs SENTIMENT_BLIND_DEFAULT_ORANGE.
    """
    readings = []
    now = datetime.now()

    readings.extend(_vxn_level_velocity(now))
    readings.extend(_vix_term_structure(now))

    # Circuit breaker: VXN level is the single critical metric
    vxn_present = any(r.name == "VXN Level & Velocity" for r in readings)
    if not vxn_present:
        logger.warning("SENTIMENT_BLIND_DEFAULT_ORANGE: VXN data unavailable")

    return readings


def _vxn_level_velocity(now: datetime) -> list[SignalReading]:
    """Radar B: VXN (NASDAQ-100 implied vol) level with velocity metadata.

    Blueprint thresholds: <18 GREEN, 18-25 YELLOW, 25-35 ORANGE, >35 RED.
    Also computes:
    - 5MA / 20MA crossover for trend detection
    - 3-trading-day velocity (prices[-4] → prices[-1]) to avoid weekend trap
    """
    try:
        vxn = yf.Ticker("^VXN")
        data = vxn.history(period="3mo")
        if data.empty:
            return []

        value = float(data["Close"].iloc[-1])

        # 3-trading-day velocity: uses index positions to avoid weekend trap
        velocity_3d_pct = None
        if len(data) >= 4:
            ref_price = float(data["Close"].iloc[-4])
            if ref_price > 0:
                velocity_3d_pct = (value - ref_price) / ref_price * 100.0

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
            name="VXN Level & Velocity",
            value=value,
            color=color,
            timestamp=now,
            source="yfinance:^VXN",
            detail=f"VXN: {value:.1f}" + (f" (5MA>20MA)" if ma5_above_ma20 else ""),
            metadata={
                "ma5_above_ma20": ma5_above_ma20,
                "ma5": ma5,
                "ma20": ma20,
                "velocity_3d_pct": velocity_3d_pct,
            },
        )]
    except Exception:
        return []


def _vix_term_structure(now: datetime) -> list[SignalReading]:
    """Radar A: Macro term structure — spot ^VIX vs ^VIX3M.

    spread = VIX3M - VIX:
      Positive = contango = normal market = GREEN/YELLOW
      Negative = backwardation = institutional panic = ORANGE/RED

    Uses S&P 500 volatility indices exclusively (no ^VXN3M).
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
