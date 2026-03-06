"""AI structural health metrics - combines quantitative signals with Gemini CAPEX extraction.

The Rewired Index's core moat: tracking underlying capital expenditures (CAPEX) in the AI
super cycle. This module keeps two quantitative signals (semiconductor and cloud ETF momentum)
and uses Gemini STRICTLY as a flat-JSON data extractor for per-company CAPEX numbers from
earnings filings. All trend analysis is performed in pure Python math in
signals/ai_health_signal.py.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

from rewired import get_data_dir
from rewired.data.prices import get_moving_averages
from rewired.models.signals import SignalColor, SignalReading

logger = logging.getLogger(__name__)


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
            metadata={"price": ma["price"], "ma50": ma["ma50"], "ma200": ma.get("ma200")},
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
            metadata={"price": ma["price"], "ma50": ma["ma50"], "ma200": ma.get("ma200")},
        )]
    except Exception:
        return []


# ── Gemini CAPEX Analysis (the Rewired-unique edge) ──────────────────────

_CAPEX_CACHE_HOURS = 12  # Only call Gemini once per 12 hours
_CAPEX_CACHE_VERSION = 4  # v4: Pydantic-validated AIHealthExtraction schema
_BIG4_HYPERSCALERS = ("MSFT", "GOOGL", "AMZN", "META")


def _strip_markdown_json(raw: str) -> str:
    """Strip Markdown code fences and extract the pure JSON payload.

    Gemini frequently wraps JSON in ```json ... ``` blocks.  This must be
    cleaned before Pydantic validation to avoid wasting retry attempts on
    formatting errors.
    """
    text = raw.strip()
    # Remove opening ```json or ``` fence
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    # Remove closing ``` fence
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _load_capex_cache() -> dict | None:
    """Load cached CAPEX analysis if still fresh."""
    cache_path = get_data_dir() / "capex_cache.json"
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, encoding="utf-8") as f:
            cache = json.load(f)
        # Invalidate old cache versions (scoring polarity was flipped in v2)
        if cache.get("schema_version", 1) < _CAPEX_CACHE_VERSION:
            return None
        cached_at = datetime.fromisoformat(cache["timestamp"])
        if datetime.now() - cached_at < timedelta(hours=_CAPEX_CACHE_HOURS):
            return cache
    except (json.JSONDecodeError, KeyError, ValueError, OSError):
        pass
    return None


def _save_capex_cache(data: dict) -> None:
    """Save CAPEX analysis result to cache."""
    data["timestamp"] = datetime.now().isoformat()
    data["schema_version"] = _CAPEX_CACHE_VERSION
    cache_path = get_data_dir() / "capex_cache.json"
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _format_quarter_label(date_text: str, period: str = "") -> str:
    """Format a statement date into the ``YYYY-QN`` form used in prompts."""
    year = str(date_text)[:4] if date_text else ""
    period_text = str(period or "").upper()
    if year and period_text.startswith("Q"):
        return f"{year}-{period_text}"
    try:
        parsed = datetime.fromisoformat(str(date_text))
        quarter = ((parsed.month - 1) // 3) + 1
        return f"{parsed.year}-Q{quarter}"
    except ValueError:
        return str(date_text)[:7] if date_text else "unknown"


def _fetch_capex_financials_from_fmp() -> list[str]:
    """Fetch quarterly CAPEX history from FMP for the Big 4 hyperscalers."""
    from rewired.data.fmp import get_big4_capex_summary, is_configured as fmp_is_configured

    if not fmp_is_configured():
        return []

    lines: list[str] = []
    try:
        summary = get_big4_capex_summary()
    except Exception as exc:
        return [f"FMP CAPEX fetch unavailable ({exc})"]

    for symbol in _BIG4_HYPERSCALERS:
        history = summary.get(symbol, [])
        if not history:
            lines.append(f"{symbol}: data unavailable (FMP CAPEX history unavailable)")
            continue

        capex_values: list[str] = []
        for item in history[:4]:
            capex = float(item.get("capex", 0) or 0)
            if capex <= 0:
                continue
            q_label = _format_quarter_label(item.get("date", ""), item.get("period", ""))
            capex_b = capex / 1e9
            capex_pct_rev = item.get("capex_pct_revenue", 0)
            pct_text = f" ({capex_pct_rev:.1f}% rev)" if capex_pct_rev else ""
            capex_values.append(f"{q_label}: ${capex_b:.1f}B{pct_text}")

        if capex_values:
            lines.append(f"{symbol} CAPEX (quarterly): {', '.join(capex_values)}")
        else:
            lines.append(f"{symbol}: data unavailable (FMP CAPEX values missing)")

    return lines


def _fetch_capex_financials_from_yfinance() -> list[str]:
    """Fallback CAPEX fetcher when FMP is unavailable or partial."""
    import yfinance as yf

    lines: list[str] = []

    for symbol in _BIG4_HYPERSCALERS:
        try:
            ticker = yf.Ticker(symbol)

            cf = ticker.quarterly_cashflow
            if cf is not None and not cf.empty:
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
                        q_label = _format_quarter_label(str(date))
                        capex_b = abs(float(val)) / 1e9
                        capex_values.append(f"{q_label}: ${capex_b:.1f}B")
                    if capex_values:
                        lines.append(f"{symbol} CAPEX (quarterly): {', '.join(capex_values)}")

            fin = ticker.quarterly_financials
            if fin is not None and not fin.empty:
                for idx in fin.index:
                    idx_lower = str(idx).lower()
                    if "total revenue" in idx_lower or idx_lower == "revenue":
                        recent_rev = fin.loc[idx].dropna().head(2)
                        if len(recent_rev) >= 2:
                            curr = float(recent_rev.iloc[0]) / 1e9
                            prev = float(recent_rev.iloc[1]) / 1e9
                            growth = ((curr / prev) - 1) * 100 if prev > 0 else 0
                            lines.append(f"{symbol} Revenue: ${curr:.1f}B (QoQ: {growth:+.1f}%)")
                        break

        except Exception as exc:
            lines.append(f"{symbol}: data unavailable ({exc})")

    return lines


def _fetch_capex_financials() -> str:
    """Fetch actual CAPEX data with FMP as the primary source.

    FMP provides cleaner structured quarterly cash-flow data for this use case.
    yfinance is retained only as a fallback so transient FMP issues do not hard-fail
    the entire CAPEX signal.
    """
    fmp_lines = _fetch_capex_financials_from_fmp()
    if any("CAPEX (quarterly):" in line for line in fmp_lines):
        return "\n".join(fmp_lines)

    yfinance_lines = _fetch_capex_financials_from_yfinance()
    merged_lines = fmp_lines + [line for line in yfinance_lines if line not in fmp_lines]
    return "\n".join(merged_lines) if merged_lines else "Financial data unavailable"


def _run_gemini_capex_analysis(financial_data: str) -> dict:
    """Ask Gemini to extract CAPEX data and validate against AIHealthExtraction.

    Uses strict Pydantic validation. On ValidationError, appends the error
    to a penalty prompt and retries (max 3 total attempts).  Returns dict with
    the validated extraction data or a defensive ORANGE fallback.
    """
    from rewired.agent.gemini import generate, is_configured
    from rewired.models.signals import AIHealthExtraction

    if not is_configured():
        logger.warning("AI_HEALTH_BLIND_DEFAULT_ORANGE: Gemini not configured")
        return _orange_fallback("Gemini not configured - defaulting to ORANGE")

    # Fetch real SEC filings to ground the analysis
    edgar_text = "[SEC filing data unavailable]"
    try:
        from rewired.data.edgar import fetch_earnings_filings
        edgar_text = fetch_earnings_filings()
    except Exception:
        pass

    from rewired.agent.prompts import CAPEX_HEALTH, SYSTEM_CAPEX

    earnings_context = (
        f"ACTUAL QUARTERLY FINANCIAL DATA (FMP/yfinance):\n{financial_data}\n\n"
        f"RECENT SEC EARNINGS FILINGS (8-K):\n{edgar_text}"
    )
    prompt = CAPEX_HEALTH.format(earnings_context=earnings_context)

    max_attempts = 3
    last_error = ""

    for attempt in range(1, max_attempts + 1):
        retry_prompt = prompt
        if last_error:
            retry_prompt = (
                f"{prompt}\n\n--- PREVIOUS ATTEMPT FAILED ---\n"
                f"Your previous response failed validation with this error:\n"
                f"{last_error}\n\n"
                f"Fix the error and respond with ONLY valid JSON matching the "
                f"exact schema above. This is attempt {attempt} of {max_attempts}."
            )

        raw = generate(
            retry_prompt,
            system_instruction=SYSTEM_CAPEX,
            search_grounding=False,
            json_output=True,
            max_retries=1,
            timeout_seconds=30,
        )

        # Strip markdown fences before validation
        text = _strip_markdown_json(raw)

        try:
            extraction = AIHealthExtraction.model_validate_json(text)
            # Success — convert to flat dict for caching and downstream use
            return _extraction_to_result(extraction, raw)
        except Exception as exc:
            last_error = str(exc)[:500]
            logger.warning(
                "CAPEX Pydantic validation failed (attempt %d/%d): %s",
                attempt, max_attempts, last_error[:200],
            )

    # All attempts exhausted — circuit breaker
    logger.critical("AI_HEALTH_BLIND_DEFAULT_ORANGE: Pydantic validation failed after %d attempts", max_attempts)
    return _orange_fallback(f"LLM parsing failed after {max_attempts} attempts: {last_error[:150]}")


def _extraction_to_result(extraction, raw_response: str) -> dict:
    """Convert a validated AIHealthExtraction to the result dict for caching."""
    from rewired.models.signals import AIHealthExtraction

    companies = {}
    for ticker in _BIG4_HYPERSCALERS:
        company = getattr(extraction, ticker)
        companies[ticker] = {
            "capex_absolute_bn": company.capex_absolute_bn,
            "qoq_growth_pct": company.qoq_growth_pct,
            "yoy_growth_pct": company.yoy_growth_pct,
            "explicit_guidance_cut_mentioned": company.explicit_guidance_cut_mentioned,
            "exact_capex_quote": company.exact_capex_quote,
        }

    veto = any(
        getattr(extraction, t).explicit_guidance_cut_mentioned
        for t in _BIG4_HYPERSCALERS
    )

    # Find the best quote for display
    best_quote = ""
    for t in _BIG4_HYPERSCALERS:
        q = getattr(extraction, t).exact_capex_quote
        if q and q != "data unavailable" and len(q) > len(best_quote):
            best_quote = q

    return {
        "companies": companies,
        "veto_triggered": veto,
        "key_management_quote": best_quote,
        "raw_response": raw_response,
        "validated": True,
    }


def _orange_fallback(explanation: str) -> dict:
    """Return a defensive ORANGE result when CAPEX analysis fails."""
    empty_company = {
        "capex_absolute_bn": 0.0,
        "qoq_growth_pct": 0.0,
        "yoy_growth_pct": 0.0,
        "explicit_guidance_cut_mentioned": False,
        "exact_capex_quote": "data unavailable",
    }
    return {
        "companies": {t: dict(empty_company) for t in _BIG4_HYPERSCALERS},
        "veto_triggered": False,
        "key_management_quote": "",
        "explanation": explanation,
        "raw_response": "",
        "validated": False,
    }


def _capex_analysis(now: datetime) -> list[SignalReading]:
    """Run Gemini CAPEX extraction (cached for 12 hours).

    Returns SignalReading objects with per-company CAPEX data in metadata.
    The trend is NOT determined here — that is done by pure Python math in
    signals/ai_health_signal.py using velocity/acceleration calculations.
    """
    # Check cache first
    cache = _load_capex_cache()
    if cache and "companies" in cache:
        return _build_capex_readings(cache, now, cached=True)

    # Fetch real financial data
    try:
        financial_data = _fetch_capex_financials()
    except Exception:
        financial_data = "Financial data fetch failed"

    # Run Gemini extraction with Pydantic validation + retry
    result = _run_gemini_capex_analysis(financial_data)

    # Store raw financial data in result for cache persistence
    result["raw_financial_data"] = financial_data

    # Append to quarterly history for acceleration math
    _append_quarterly_snapshot(result)

    # Cache the current extraction
    _save_capex_cache(result)

    return _build_capex_readings(result, now, cached=False)


def _build_capex_readings(result: dict, now: datetime, cached: bool) -> list[SignalReading]:
    """Build SignalReading objects from a validated CAPEX extraction result."""
    companies = result.get("companies", {})
    veto = result.get("veto_triggered", False)
    validated = result.get("validated", False)
    key_quote = result.get("key_management_quote", "")

    # Load quarterly history for acceleration calculations
    history = _load_quarterly_history()

    return [SignalReading(
        name="AI CAPEX Health (Agent)",
        value=1.0 if veto else 3.0,  # Placeholder — trend determined by ai_health_signal.py
        color=SignalColor.RED if veto else SignalColor.YELLOW,
        timestamp=now,
        source="gemini:capex_extraction",
        detail=f"Validated: {validated}, Veto: {veto}"[:100],
        metadata={
            "companies": companies,
            "veto_triggered": veto,
            "key_management_quote": key_quote,
            "quarterly_history": history,
            "raw_financial_data": result.get("raw_financial_data", ""),
            "raw_gemini_response": result.get("raw_response", ""),
            "validated": validated,
            "cached": cached,
        },
    )]


def _append_quarterly_snapshot(result: dict) -> None:
    """Append the current extraction to the quarterly history file.

    Stores per-company qoq_growth_pct snapshots keyed by quarter label
    so that ai_health_signal.py can compute acceleration across quarters.
    """
    if not result.get("validated", False):
        return

    history_path = get_data_dir() / "capex_quarterly_history.json"
    history: list[dict] = []
    if history_path.exists():
        try:
            with open(history_path, encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            history = []

    quarter = _current_quarter_label()
    # Don't duplicate entries for the same quarter
    if history and history[-1].get("quarter") == quarter:
        history[-1] = _snapshot_entry(result, quarter)
    else:
        history.append(_snapshot_entry(result, quarter))

    # Keep max 8 quarters (2 years)
    history = history[-8:]

    with open(history_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)


def _snapshot_entry(result: dict, quarter: str) -> dict:
    """Build a quarterly snapshot dict from an extraction result."""
    companies = result.get("companies", {})
    entry = {"quarter": quarter, "timestamp": datetime.now().isoformat()}
    for ticker in _BIG4_HYPERSCALERS:
        co = companies.get(ticker, {})
        entry[ticker] = {
            "qoq_growth_pct": co.get("qoq_growth_pct", 0.0),
            "yoy_growth_pct": co.get("yoy_growth_pct", 0.0),
            "capex_absolute_bn": co.get("capex_absolute_bn", 0.0),
            "explicit_guidance_cut_mentioned": co.get("explicit_guidance_cut_mentioned", False),
        }
    return entry


def _current_quarter_label() -> str:
    """Return current quarter as 'YYYY-QN'."""
    now = datetime.now()
    quarter = ((now.month - 1) // 3) + 1
    return f"{now.year}-Q{quarter}"


def _load_quarterly_history() -> list[dict]:
    """Load the quarterly CAPEX history for acceleration math."""
    history_path = get_data_dir() / "capex_quarterly_history.json"
    if not history_path.exists():
        return []
    try:
        with open(history_path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
