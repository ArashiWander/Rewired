"""Macro economic data from FRED API."""

from __future__ import annotations

import os
from datetime import datetime

from dotenv import load_dotenv

from rewired.models.signals import SignalColor, SignalReading

load_dotenv()


def _get_fred_client():
    """Get FRED API client. Returns None if no API key configured."""
    api_key = os.environ.get("FRED_API_KEY", "")
    if not api_key or api_key == "your_fred_api_key_here":
        return None
    from fredapi import Fred
    return Fred(api_key=api_key)


def get_macro_readings() -> list[SignalReading]:
    """Fetch macro economic readings from FRED.

    Falls back to yfinance-based proxies if FRED API key is not set.
    """
    fred = _get_fred_client()
    readings = []
    now = datetime.now()

    if fred:
        readings.extend(_fred_readings(fred, now))
    else:
        readings.extend(_proxy_readings(now))

    return readings


def _fred_readings(fred, now: datetime) -> list[SignalReading]:
    """Fetch readings using FRED API."""
    readings = []

    # Yield curve 10Y-2Y
    try:
        data = fred.get_series("T10Y2Y", observation_start="2024-01-01")
        if not data.empty:
            value = float(data.dropna().iloc[-1])
            if value > 0.5:
                color = SignalColor.GREEN
            elif value > 0.0:
                color = SignalColor.YELLOW
            elif value > -0.5:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED
            readings.append(SignalReading(
                name="Yield Curve (10Y-2Y)",
                value=value,
                color=color,
                timestamp=now,
                source="FRED:T10Y2Y",
                detail=f"Spread: {value:.2f}%",
            ))
    except Exception:
        pass

    # Unemployment rate
    try:
        data = fred.get_series("UNRATE", observation_start="2023-01-01")
        if not data.empty and len(data) >= 7:
            current = float(data.iloc[-1])
            six_months_ago = float(data.iloc[-7])
            change = current - six_months_ago
            if change <= 0.0:
                color = SignalColor.GREEN
            elif change <= 0.3:
                color = SignalColor.YELLOW
            elif change <= 0.8:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED
            readings.append(SignalReading(
                name="Unemployment",
                value=current,
                color=color,
                timestamp=now,
                source="FRED:UNRATE",
                detail=f"{current:.1f}% (6mo change: {change:+.1f}%)",
            ))
    except Exception:
        pass

    # GDP growth
    try:
        data = fred.get_series("A191RL1Q225SBEA", observation_start="2023-01-01")
        if not data.empty:
            value = float(data.dropna().iloc[-1])
            if value >= 2.0:
                color = SignalColor.GREEN
            elif value >= 1.0:
                color = SignalColor.YELLOW
            elif value >= 0.0:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED
            readings.append(SignalReading(
                name="GDP Growth",
                value=value,
                color=color,
                timestamp=now,
                source="FRED:GDP",
                detail=f"Real GDP growth: {value:.1f}%",
            ))
    except Exception:
        pass

    # Capacity Utilization (manufacturing health, leading indicator)
    try:
        data = fred.get_series("TCU", observation_start="2024-01-01")
        if not data.empty:
            value = float(data.dropna().iloc[-1])
            if value > 78:
                color = SignalColor.GREEN
            elif value > 75:
                color = SignalColor.YELLOW
            elif value > 72:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED
            readings.append(SignalReading(
                name="Capacity Utilization",
                value=value,
                color=color,
                timestamp=now,
                source="FRED:TCU",
                detail=f"Capacity: {value:.1f}% ({'strong' if value > 78 else 'moderate' if value > 75 else 'weak'})",
            ))
    except Exception:
        pass

    # Initial Jobless Claims (weekly, most timely labor signal)
    try:
        data = fred.get_series("ICSA", observation_start="2024-01-01")
        if not data.empty:
            value = float(data.dropna().iloc[-1])
            value_k = value / 1000
            if value < 220_000:
                color = SignalColor.GREEN
            elif value < 260_000:
                color = SignalColor.YELLOW
            elif value < 320_000:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED
            readings.append(SignalReading(
                name="Initial Jobless Claims",
                value=value_k,
                color=color,
                timestamp=now,
                source="FRED:ICSA",
                detail=f"{value_k:.0f}K weekly claims",
            ))
    except Exception:
        pass

    # CPI Year-over-Year (inflation drives Fed policy)
    try:
        data = fred.get_series("CPIAUCSL", observation_start="2023-01-01")
        if not data.empty and len(data) >= 13:
            current = float(data.iloc[-1])
            year_ago = float(data.iloc[-13])
            yoy = ((current / year_ago) - 1) * 100
            if yoy < 2.5:
                color = SignalColor.GREEN
            elif yoy < 3.5:
                color = SignalColor.YELLOW
            elif yoy < 5.0:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED
            readings.append(SignalReading(
                name="CPI YoY",
                value=yoy,
                color=color,
                timestamp=now,
                source="FRED:CPIAUCSL",
                detail=f"CPI inflation: {yoy:.1f}% YoY",
            ))
    except Exception:
        pass

    # Consumer Sentiment (forward-looking spending intent)
    try:
        data = fred.get_series("UMCSENT", observation_start="2024-01-01")
        if not data.empty:
            value = float(data.dropna().iloc[-1])
            if value > 80:
                color = SignalColor.GREEN
            elif value > 65:
                color = SignalColor.YELLOW
            elif value > 50:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED
            readings.append(SignalReading(
                name="Consumer Sentiment",
                value=value,
                color=color,
                timestamp=now,
                source="FRED:UMCSENT",
                detail=f"UMich Sentiment: {value:.1f}",
            ))
    except Exception:
        pass

    return readings


def _proxy_readings(now: datetime) -> list[SignalReading]:
    """Fallback: use yfinance proxies when FRED API key is not available."""
    import yfinance as yf

    readings = []

    # TLT (20+ year treasury ETF) as bond market proxy
    try:
        tlt = yf.Ticker("TLT")
        hist = tlt.history(period="6mo")
        if not hist.empty and len(hist) >= 50:
            price = float(hist["Close"].iloc[-1])
            ma50 = float(hist["Close"].rolling(50).mean().iloc[-1])
            # Bonds rising (price up) = risk-off = macro weakening
            pct_above_ma = ((price / ma50) - 1) * 100
            if pct_above_ma < -3:
                color = SignalColor.GREEN  # Bonds falling = risk-on
            elif pct_above_ma < 0:
                color = SignalColor.YELLOW
            elif pct_above_ma < 3:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED  # Bonds surging = flight to safety
            readings.append(SignalReading(
                name="Bond Market (TLT proxy)",
                value=pct_above_ma,
                color=color,
                timestamp=now,
                source="yfinance:TLT",
                detail=f"TLT {pct_above_ma:+.1f}% vs 50MA",
            ))
    except Exception:
        pass

    return readings
