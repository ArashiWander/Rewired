"""AI analyst - structured prompts for Gemini analysis and market regime assessment."""

from __future__ import annotations

import json

from pydantic import BaseModel

from rewired.agent.gemini import generate, is_configured
from rewired.agent.prompts import (
    PORTFOLIO_ANALYSIS,
    REGIME_ASSESS,
    SIGNAL_ANALYSIS,
    STOCK_ANALYSIS,
    SYSTEM_ANALYST,
    SYSTEM_REGIME,
)

SYSTEM_PROMPT = SYSTEM_ANALYST


# ── Market Regime Assessment (structured qualitative overlay) ────────────


class MarketRegimeAssessment(BaseModel):
    """Structured qualitative overlay from the AI analyst."""
    regime: str              # risk_on | neutral | risk_off | crisis
    confidence: float        # 0.0-1.0
    reasoning: str           # 2-3 sentence explanation
    actionable_insight: str  # One specific recommendation
    key_risk: str            # Most important risk to watch
    regime_shift_probability: float  # 0.0-1.0, probability of regime change in next 2 weeks


def market_regime_assessment() -> MarketRegimeAssessment:
    """Produce a structured market regime assessment using Gemini.

    Interprets the cross-signal picture (macro + sentiment + AI health together)
    and produces a higher-level regime label. This is a qualitative overlay,
    not a new signal category - it does NOT duplicate the CAPEX scoring in ai_health.py.
    """
    if not is_configured():
        return MarketRegimeAssessment(
            regime="neutral",
            confidence=0.0,
            reasoning="Gemini not configured - defaulting to neutral regime.",
            actionable_insight="Configure GEMINI_API_KEY in .env for AI-powered regime assessment.",
            key_risk="No AI analysis available.",
            regime_shift_probability=0.5,
        )

    signal_data = _get_signal_summary()
    portfolio_data = _get_portfolio_summary()
    pies_data = _get_pies_summary()

    prompt = REGIME_ASSESS.format(
        signal_data=signal_data,
        portfolio_data=portfolio_data,
        pies_data=pies_data,
    )

    raw = generate(prompt, system_instruction=SYSTEM_REGIME, json_output=True)

    try:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

        data = json.loads(text)

        regime = data.get("regime", "neutral")
        if regime not in ("risk_on", "neutral", "risk_off", "crisis"):
            regime = "neutral"

        return MarketRegimeAssessment(
            regime=regime,
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
            reasoning=str(data.get("reasoning", ""))[:500],
            actionable_insight=str(data.get("actionable_insight", ""))[:300],
            key_risk=str(data.get("key_risk", ""))[:300],
            regime_shift_probability=max(0.0, min(1.0, float(data.get("regime_shift_probability", 0.5)))),
        )
    except (json.JSONDecodeError, ValueError, TypeError):
        return MarketRegimeAssessment(
            regime="neutral",
            confidence=0.3,
            reasoning=f"Agent analysis (unstructured): {raw[:200]}",
            actionable_insight="Review signals manually - structured parsing failed.",
            key_risk="AI analysis unavailable.",
            regime_shift_probability=0.5,
        )


# ── Existing analysis functions (enhanced with Pies context) ─────────────


def run_analysis() -> str:
    """Run a full portfolio + signal + Pies analysis."""
    if not is_configured():
        return "[Gemini API key not configured. Set GEMINI_API_KEY in .env file.]"

    signal_data = _get_signal_summary()
    portfolio_data = _get_portfolio_summary()
    pies_data = _get_pies_summary()

    prompt = PORTFOLIO_ANALYSIS.format(
        signal_data=signal_data,
        portfolio_data=portfolio_data,
        pies_data=pies_data,
    )

    return generate(prompt, system_instruction=SYSTEM_PROMPT)


def analyze_signals_only() -> str:
    """Analyze current signals without portfolio context."""
    if not is_configured():
        return "[Gemini API key not configured.]"

    signal_data = _get_signal_summary()

    prompt = SIGNAL_ANALYSIS.format(signal_data=signal_data)

    return generate(prompt, system_instruction=SYSTEM_PROMPT)


def analyze_stock(ticker: str) -> str:
    """Analyze a specific stock within the Rewired Index framework."""
    if not is_configured():
        return "[Gemini API key not configured.]"

    from rewired.models.universe import load_universe
    uni = load_universe()
    stock = uni.get_stock(ticker.upper())

    if not stock:
        return f"[{ticker} is not in the Rewired Index universe.]"

    prompt = STOCK_ANALYSIS.format(
        name=stock.name,
        ticker=stock.ticker,
        layer=stock.layer.value,
        tier=stock.tier.value,
        max_weight_pct=stock.max_weight_pct,
        notes=stock.notes,
    )

    return generate(prompt, system_instruction=SYSTEM_PROMPT)


# ── Data helpers ─────────────────────────────────────────────────────────


def _get_signal_summary() -> str:
    """Get current signals as text for the prompt."""
    try:
        from rewired.signals.engine import compute_signals
        sig = compute_signals()

        lines = [f"Overall: {sig.overall_color.value.upper()}"]
        for cat, cs in sig.categories.items():
            lines.append(f"\n{cat.value.upper()}:")
            lines.append(f"  Composite: {cs.composite_color.value.upper()}")
            for r in cs.readings:
                lines.append(f"  - {r.name}: {r.value:.2f} ({r.color.value}) - {r.detail}")

        return "\n".join(lines)
    except Exception as e:
        return f"[Error fetching signals: {e}]"


def _get_portfolio_summary() -> str:
    """Get current portfolio state as text for the prompt."""
    try:
        from rewired.portfolio.manager import load_portfolio, refresh_prices

        pf = load_portfolio()
        if pf.positions:
            refresh_prices(pf)

        lines = [
            f"Total value: {pf.total_value_eur:.2f} EUR",
            f"Cash: {pf.cash_eur:.2f} EUR ({pf.cash_eur/pf.total_value_eur*100:.1f}%)" if pf.total_value_eur > 0 else f"Cash: {pf.cash_eur:.2f} EUR",
            f"Positions: {len(pf.positions)}",
        ]

        if pf.positions:
            lines.append("\nHoldings:")
            for t, p in sorted(pf.positions.items()):
                pnl = f"+{p.unrealized_pnl_eur:.2f}" if p.unrealized_pnl_eur >= 0 else f"{p.unrealized_pnl_eur:.2f}"
                lines.append(f"  {t}: {p.shares:.4f} shares, {p.market_value_eur:.2f} EUR, P&L: {pnl} EUR, Weight: {p.weight_pct:.1f}%")
        else:
            lines.append("\nNo current positions (all cash).")

        return "\n".join(lines)
    except Exception as e:
        return f"[Error fetching portfolio: {e}]"


def _get_pies_summary() -> str:
    """Get current Pies allocation as text for the prompt."""
    try:
        from rewired.models.universe import load_universe
        from rewired.portfolio.manager import load_portfolio, refresh_prices
        from rewired.portfolio.sizing import calculate_pies_allocation
        from rewired.signals.engine import compute_signals

        uni = load_universe()
        pf = load_portfolio()
        if pf.positions:
            refresh_prices(pf)
        sig = compute_signals()
        allocs = calculate_pies_allocation(pf, uni, sig)

        lines = []
        for a in allocs:
            lines.append(f"  {a['ticker']} ({a['layer']}/{a['tier']}): {a['target_pct']}% = {a['target_eur']:.0f} EUR")
        return "\n".join(lines)
    except Exception as e:
        return f"[Error fetching pies: {e}]"
