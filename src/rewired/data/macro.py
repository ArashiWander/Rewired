"""Macro economic data from FRED API.

Fetches both the metrics required by the boolean rules engine (ISM PMI,
Core PCE MoM, Retail Sales MoM, Unemployment MoM, Yield Curve) and
supporting indicators (GDP, capacity utilisation, jobless claims, CPI,
consumer sentiment) for informational display.
"""

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

    # ── ISM Manufacturing PMI (CRITICAL for rules engine) ─────────────
    try:
        data = fred.get_series("NAPM", observation_start="2024-06-01")
        if not data.empty:
            values = data.dropna()
            current = float(values.iloc[-1])

            # Count consecutive months below 48 (from most recent backwards)
            consecutive_below_48 = 0
            for v in reversed(values.values):
                if float(v) < 48:
                    consecutive_below_48 += 1
                else:
                    break

            if current > 52:
                color = SignalColor.GREEN
            elif current > 50:
                color = SignalColor.YELLOW
            elif current > 48:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED

            readings.append(SignalReading(
                name="ISM PMI",
                value=current,
                color=color,
                timestamp=now,
                source="FRED:NAPM",
                detail=f"ISM Manufacturing PMI: {current:.1f}",
                metadata={
                    "consecutive_below_threshold": consecutive_below_48,
                    "previous": float(values.iloc[-2]) if len(values) >= 2 else None,
                },
            ))
    except Exception:
        pass

    # ── Core PCE MoM % (CRITICAL for rules engine) ───────────────────
    try:
        data = fred.get_series("PCEPILFE", observation_start="2024-06-01")
        if not data.empty:
            values = data.dropna()
            if len(values) >= 2:
                current_idx = float(values.iloc[-1])
                prev_idx = float(values.iloc[-2])
                mom_pct = ((current_idx / prev_idx) - 1) * 100

                if mom_pct <= 0.1:
                    color = SignalColor.GREEN
                elif mom_pct <= 0.2:
                    color = SignalColor.YELLOW
                elif mom_pct <= 0.3:
                    color = SignalColor.ORANGE
                else:
                    color = SignalColor.RED

                readings.append(SignalReading(
                    name="Core PCE MoM",
                    value=mom_pct,
                    color=color,
                    timestamp=now,
                    source="FRED:PCEPILFE",
                    detail=f"Core PCE: {mom_pct:.2f}% MoM",
                    metadata={"current_index": current_idx, "prev_index": prev_idx},
                ))
    except Exception:
        pass

    # ── Retail Sales MoM % (CRITICAL for rules engine) ────────────────
    try:
        data = fred.get_series("RSAFS", observation_start="2024-06-01")
        if not data.empty:
            values = data.dropna()
            if len(values) >= 2:
                current_val = float(values.iloc[-1])
                prev_val = float(values.iloc[-2])
                mom_pct = ((current_val / prev_val) - 1) * 100

                if mom_pct > 0.3:
                    color = SignalColor.GREEN
                elif mom_pct > 0.0:
                    color = SignalColor.YELLOW
                elif mom_pct > -0.3:
                    color = SignalColor.ORANGE
                else:
                    color = SignalColor.RED

                readings.append(SignalReading(
                    name="Retail Sales MoM",
                    value=mom_pct,
                    color=color,
                    timestamp=now,
                    source="FRED:RSAFS",
                    detail=f"Retail Sales: {mom_pct:+.2f}% MoM",
                    metadata={"current_value": current_val, "prev_value": prev_val},
                ))
    except Exception:
        pass

    # ── Yield Curve 10Y-2Y (CRITICAL for rules engine) ───────────────
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
                metadata={"spread_pct": value, "inverted": value < 0},
            ))
    except Exception:
        pass

    # ── Unemployment MoM Change (CRITICAL for rules engine) ───────────
    try:
        data = fred.get_series("UNRATE", observation_start="2024-01-01")
        if not data.empty and len(data) >= 2:
            values = data.dropna()
            current = float(values.iloc[-1])
            prev = float(values.iloc[-2])
            mom_change = current - prev

            if mom_change <= 0.0:
                color = SignalColor.GREEN
            elif mom_change <= 0.1:
                color = SignalColor.YELLOW
            elif mom_change <= 0.2:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED

            readings.append(SignalReading(
                name="Unemployment MoM Change",
                value=mom_change,
                color=color,
                timestamp=now,
                source="FRED:UNRATE",
                detail=f"Unemployment: {current:.1f}% (MoM: {mom_change:+.2f}%)",
                metadata={"mom_change": mom_change, "current_rate": current},
            ))
    except Exception:
        pass

    # ── Non-Farm Payrolls MoM (supporting) ────────────────────────────
    try:
        data = fred.get_series("PAYEMS", observation_start="2024-06-01")
        if not data.empty:
            values = data.dropna()
            if len(values) >= 2:
                current = float(values.iloc[-1])
                prev = float(values.iloc[-2])
                change_k = current - prev  # in thousands

                if change_k > 200:
                    color = SignalColor.GREEN
                elif change_k > 100:
                    color = SignalColor.YELLOW
                elif change_k > 0:
                    color = SignalColor.ORANGE
                else:
                    color = SignalColor.RED

                readings.append(SignalReading(
                    name="Non-Farm Payrolls",
                    value=change_k,
                    color=color,
                    timestamp=now,
                    source="FRED:PAYEMS",
                    detail=f"NFP: {change_k:+.0f}K jobs MoM",
                    metadata={"current_k": current, "prev_k": prev, "change_k": change_k},
                ))
    except Exception:
        pass

    # ── Supporting indicators (informational, not used in boolean rules) ─

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
                metadata={"gdp_growth_pct": value},
            ))
    except Exception:
        pass

    # Capacity Utilization
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
                detail=f"Capacity: {value:.1f}%",
                metadata={"utilization_pct": value},
            ))
    except Exception:
        pass

    # Initial Jobless Claims
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
                metadata={"raw_claims": value, "claims_k": value_k},
            ))
    except Exception:
        pass

    # CPI Year-over-Year
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
                metadata={"current_cpi": current, "year_ago_cpi": year_ago, "yoy_pct": yoy},
            ))
    except Exception:
        pass

    # Consumer Sentiment
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
                metadata={"sentiment_index": value},
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
                metadata={"price": price, "ma50": ma50, "pct_above_ma": pct_above_ma},
            ))
    except Exception:
        pass

    return readings
