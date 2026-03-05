"""AI structural health metrics - combines quantitative signals with Gemini CAPEX analysis.

The Rewired Index's core moat: tracking underlying capital expenditures (CAPEX) in the AI
super cycle. This module keeps two quantitative signals (semiconductor and cloud ETF momentum)
and replaces the old stock-price proxies with a Gemini-powered analysis of actual CAPEX data
from hyperscaler earnings and recent news.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from rewired import get_data_dir
from rewired.data.prices import get_moving_averages
from rewired.models.signals import SignalColor, SignalReading


def get_ai_health_readings() -> list[SignalReading]:
    """Fetch AI structural health signal readings.

    Combines:
    - Quantitative: SMH momentum, WCLD momentum (price-based, legitimate structural signals)
    - Qualitative: Gemini CAPEX analysis (the Rewired-unique edge)
    """
    readings = []
    now = datetime.now()

    # Quantitative signals (keep - these are structural, not redundant with sentiment)
    readings.extend(_semiconductor_momentum(now))
    readings.extend(_cloud_momentum(now))

    # Qualitative signal from Gemini (the real CAPEX analysis)
    readings.extend(_capex_analysis(now))

    return readings


# ── Quantitative signals ──────────────────────────────────────────────────

def _semiconductor_momentum(now: datetime) -> list[SignalReading]:
    """SMH (semiconductor ETF) 50MA vs 200MA."""
    try:
        ma = get_moving_averages("SMH")
        if ma["price"] is None or ma["ma50"] is None:
            return []

        if ma["ma200"] is None:
            pct = ((ma["price"] / ma["ma50"]) - 1) * 100
            if pct > 2:
                color = SignalColor.GREEN
            elif pct > -2:
                color = SignalColor.YELLOW
            elif pct > -5:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED
            detail = f"SMH {pct:+.1f}% vs 50MA"
            value = pct
        else:
            pct_50_200 = ((ma["ma50"] / ma["ma200"]) - 1) * 100
            if pct_50_200 > 3:
                color = SignalColor.GREEN
            elif pct_50_200 > 0:
                color = SignalColor.YELLOW
            elif pct_50_200 > -3:
                color = SignalColor.ORANGE
            else:
                color = SignalColor.RED
            detail = f"SMH 50MA {pct_50_200:+.1f}% vs 200MA"
            value = pct_50_200

        return [SignalReading(
            name="Semiconductor Momentum",
            value=value,
            color=color,
            timestamp=now,
            source="yfinance:SMH",
            detail=detail,
        )]
    except Exception:
        return []


def _cloud_momentum(now: datetime) -> list[SignalReading]:
    """WCLD (cloud computing ETF) momentum."""
    try:
        ma = get_moving_averages("WCLD")
        if ma["price"] is None or ma["ma50"] is None:
            return []

        pct = ((ma["price"] / ma["ma50"]) - 1) * 100
        if pct > 3:
            color = SignalColor.GREEN
        elif pct > -2:
            color = SignalColor.YELLOW
        elif pct > -5:
            color = SignalColor.ORANGE
        else:
            color = SignalColor.RED

        return [SignalReading(
            name="Cloud Momentum",
            value=pct,
            color=color,
            timestamp=now,
            source="yfinance:WCLD",
            detail=f"WCLD {pct:+.1f}% vs 50MA",
        )]
    except Exception:
        return []


# ── Gemini CAPEX Analysis (the Rewired-unique edge) ──────────────────────

_CAPEX_CACHE_HOURS = 12  # Only call Gemini once per 12 hours


def _load_capex_cache() -> dict | None:
    """Load cached CAPEX analysis if still fresh."""
    cache_path = get_data_dir() / "capex_cache.json"
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
        cached_at = datetime.fromisoformat(cache["timestamp"])
        if datetime.now() - cached_at < timedelta(hours=_CAPEX_CACHE_HOURS):
            return cache
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        pass
    return None


def _save_capex_cache(data: dict) -> None:
    """Save CAPEX analysis result to cache."""
    data["timestamp"] = datetime.now().isoformat()
    cache_path = get_data_dir() / "capex_cache.json"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _fetch_capex_financials() -> str:
    """Fetch actual CAPEX data from yfinance quarterly financials."""
    import yfinance as yf

    tickers = ["MSFT", "GOOGL", "AMZN", "META"]
    lines = []

    for symbol in tickers:
        try:
            t = yf.Ticker(symbol)

            # Get quarterly cash flow statement (contains CapEx)
            cf = t.quarterly_cashflow
            if cf is not None and not cf.empty:
                # Look for capital expenditure row
                capex_row = None
                for idx in cf.index:
                    idx_lower = str(idx).lower()
                    if "capital expenditure" in idx_lower or "capex" in idx_lower:
                        capex_row = idx
                        break

                if capex_row is not None:
                    recent = cf.loc[capex_row].dropna().head(4)
                    capex_values = []
                    for date, val in recent.items():
                        q_label = date.strftime("%Y-Q%q") if hasattr(date, 'strftime') else str(date)[:7]
                        capex_b = abs(float(val)) / 1e9
                        capex_values.append(f"{q_label}: ${capex_b:.1f}B")
                    if capex_values:
                        lines.append(f"{symbol} CAPEX (quarterly): {', '.join(capex_values)}")

            # Get revenue for context
            fin = t.quarterly_financials
            if fin is not None and not fin.empty:
                for idx in fin.index:
                    if "total revenue" in str(idx).lower() or "revenue" == str(idx).lower():
                        recent_rev = fin.loc[idx].dropna().head(2)
                        if len(recent_rev) >= 2:
                            curr = float(recent_rev.iloc[0]) / 1e9
                            prev = float(recent_rev.iloc[1]) / 1e9
                            growth = ((curr / prev) - 1) * 100 if prev > 0 else 0
                            lines.append(f"{symbol} Revenue: ${curr:.1f}B (QoQ: {growth:+.1f}%)")
                        break

        except Exception as e:
            lines.append(f"{symbol}: data unavailable ({e})")

    return "\n".join(lines) if lines else "Financial data unavailable"


def _run_gemini_capex_analysis(financial_data: str) -> dict:
    """Ask Gemini to analyze CAPEX trends and produce a structured score.

    Grounds the analysis with SEC EDGAR 8-K filings and Google Search
    to avoid hallucination from relying on model training data alone.
    Returns dict with score (1-4), color, and explanation.
    """
    from rewired.agent.gemini import generate, is_configured

    if not is_configured():
        return {"score": 2, "color": "yellow", "explanation": "Gemini not configured - defaulting to YELLOW"}

    # Fetch real SEC filings to ground the analysis
    edgar_text = "[SEC filing data unavailable]"
    try:
        from rewired.data.edgar import fetch_earnings_filings
        edgar_text = fetch_earnings_filings()
    except Exception:
        pass

    prompt = f"""You are analyzing the AI Super Cycle CAPEX health for the Rewired Index investment framework.

ACTUAL QUARTERLY FINANCIAL DATA (yfinance):
{financial_data}

RECENT SEC EARNINGS FILINGS (8-K):
{edgar_text}

YOUR TASK:
Based ONLY on the financial data and SEC filings provided above, plus any recent information
from web search, assess the health of the AI CAPEX super cycle.

Key questions to answer:
1. Are the big four cloud providers (MSFT, GOOGL, AMZN, META) INCREASING or DECREASING their CAPEX?
2. What does their most recent earnings guidance say about future CAPEX plans?
3. Is AI training/inference cost declining (good for adoption) or is there spending fatigue?
4. Are there any signs of CAPEX cuts or slowdown that would be a warning signal?

OUTPUT FORMAT - You MUST respond with ONLY a valid JSON object, no other text:
{{
  "score": <1-4 integer>,
  "reasoning": "<2-3 sentence explanation of the CAPEX trend, citing specific data>",
  "capex_trend": "<accelerating|stable|decelerating|contracting>",
  "key_signal": "<the single most important data point driving your assessment>"
}}

SCORING:
- 1 = GREEN: CAPEX accelerating, strong AI investment cycle, positive management guidance
- 2 = YELLOW: CAPEX stable or mixed signals, some uncertainty
- 3 = ORANGE: CAPEX growth decelerating, early warning signs of spending fatigue
- 4 = RED: CAPEX cuts announced, investment cycle turning negative"""

    raw = generate(
        prompt,
        system_instruction="You are a financial data analyst. Output ONLY valid JSON. Base your analysis strictly on the data provided and web search results.",
        search_grounding=True,
    )

    # Parse the JSON response
    try:
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        result = json.loads(text)
        score = int(result.get("score", 2))
        score = max(1, min(4, score))

        color_map = {1: "green", 2: "yellow", 3: "orange", 4: "red"}
        return {
            "score": score,
            "color": color_map[score],
            "explanation": result.get("reasoning", ""),
            "capex_trend": result.get("capex_trend", "unknown"),
            "key_signal": result.get("key_signal", ""),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        # If Gemini returns non-JSON, try to extract useful info
        return {
            "score": 2,
            "color": "yellow",
            "explanation": f"Agent analysis (unstructured): {raw[:200]}",
            "capex_trend": "unknown",
            "key_signal": "",
        }


def _capex_analysis(now: datetime) -> list[SignalReading]:
    """Run Gemini CAPEX analysis (cached for 12 hours).

    This is the Rewired Index's core differentiator: using an LLM to read actual
    earnings data and produce a qualitative assessment of the AI CAPEX super cycle.
    """
    # Check cache first
    cache = _load_capex_cache()
    if cache and "score" in cache:
        score = cache["score"]
        color_map = {1: SignalColor.GREEN, 2: SignalColor.YELLOW, 3: SignalColor.ORANGE, 4: SignalColor.RED}
        return [SignalReading(
            name="AI CAPEX Health (Agent)",
            value=float(score),
            color=color_map.get(score, SignalColor.YELLOW),
            timestamp=now,
            source="gemini:capex_analysis",
            detail=cache.get("explanation", "Cached analysis")[:100],
        )]

    # Fetch real financial data
    try:
        financial_data = _fetch_capex_financials()
    except Exception:
        financial_data = "Financial data fetch failed"

    # Run Gemini analysis
    result = _run_gemini_capex_analysis(financial_data)

    # Cache it
    _save_capex_cache(result)

    score = result["score"]
    color_map = {1: SignalColor.GREEN, 2: SignalColor.YELLOW, 3: SignalColor.ORANGE, 4: SignalColor.RED}

    readings = [SignalReading(
        name="AI CAPEX Health (Agent)",
        value=float(score),
        color=color_map.get(score, SignalColor.YELLOW),
        timestamp=now,
        source="gemini:capex_analysis",
        detail=result.get("explanation", "")[:100],
    )]

    # Add CAPEX trend as a separate readable signal
    trend = result.get("capex_trend", "unknown")
    key_signal = result.get("key_signal", "")
    if key_signal:
        readings.append(SignalReading(
            name="CAPEX Key Signal",
            value=float(score),
            color=color_map.get(score, SignalColor.YELLOW),
            timestamp=now,
            source="gemini:capex_key",
            detail=f"Trend: {trend} | {key_signal[:80]}",
        ))

    return readings
