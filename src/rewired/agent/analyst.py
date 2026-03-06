"""AI analyst - structured prompts for Gemini analysis and market regime assessment."""

from __future__ import annotations

import json

from pydantic import BaseModel

from rewired.agent.gemini import generate, is_configured
from rewired.agent.prompts import (
    MARKET_BRIEFING,
    PORTFOLIO_ANALYSIS,
    SIGNAL_ANALYSIS,
    SPIRIT_FOLLOWUP,
    STOCK_ANALYSIS,
    SYSTEM_ANALYST,
    SYSTEM_REGIME,
    SYSTEM_SPIRIT,
)

SYSTEM_PROMPT = SYSTEM_ANALYST


def _cached_signals():
    """Return signals from the dashboard cache if available, else compute fresh."""
    try:
        from rewired.gui.state import dashboard_state
        cached = dashboard_state.get_signals()
        if cached is not None:
            return cached
    except Exception:
        pass
    from rewired.signals.engine import compute_signals
    return compute_signals()


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
    """Produce a deterministic market regime assessment from the truth table.

    Regime is now computed by the Boolean truth-table waterfall and
    hysteresis state machine \u2014 NOT by Gemini.  This function reads the
    computed regime and translates it into the MarketRegimeAssessment
    structure expected by CLI / GUI callers.
    """
    result = _cached_signals()
    color = result.overall_color.value

    regime_map = {"green": "risk_on", "yellow": "neutral", "orange": "risk_off", "red": "crisis"}
    regime = regime_map.get(color, "neutral")

    rule = result.composite_transparency.get("rule_matched", "")
    veto = result.veto_active

    return MarketRegimeAssessment(
        regime=regime,
        confidence=1.0,
        reasoning=(
            f"Deterministic truth-table regime: {color.upper()}. "
            f"Rule matched: {rule}. Veto: {'ACTIVE' if veto else 'inactive'}."
        ),
        actionable_insight=f"Follow the {color.upper()} signal playbook from the constraint solver.",
        key_risk="AI Health VETO" if veto else rule or "Monitor all signal dimensions.",
        regime_shift_probability=0.0,
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


# ── System Spirit (read-only AI Copilot) ─────────────────────────────────


def generate_briefing() -> str:
    """Generate a market briefing from the System Spirit.

    Gathers live signal, portfolio, and allocation data and sends it
    through the MARKET_BRIEFING prompt with the SYSTEM_SPIRIT persona.
    Returns Markdown text.
    """
    if not is_configured():
        return "[Gemini API key not configured. Set GEMINI_API_KEY in .env file.]"

    signal_data = _get_signal_summary()
    portfolio_data = _get_portfolio_summary()
    pies_data = _get_pies_summary()

    prompt = MARKET_BRIEFING.format(
        signal_data=signal_data,
        portfolio_data=portfolio_data,
        pies_data=pies_data,
    )

    return generate(prompt, system_instruction=SYSTEM_SPIRIT)


def ask_followup(question: str, history: list[dict[str, str]] | None = None) -> str:
    """Ask the System Spirit a follow-up question.

    ``history`` is a list of ``{"role": "user"|"spirit", "text": "..."}``
    dicts representing the conversation so far.  Only the last 10 turns
    are included in the prompt to stay within context limits.

    Returns the Spirit's Markdown response.
    """
    if not is_configured():
        return "[Gemini API key not configured.]"

    # Build condensed history string
    turns = (history or [])[-10:]
    history_str = "\n".join(
        f"{'User' if t['role'] == 'user' else 'Spirit'}: {t['text']}"
        for t in turns
    ) or "(no prior conversation)"

    # Grab lightweight signal/portfolio summaries
    signal_summary = "unavailable"
    portfolio_value = "?"
    cash_pct = "?"
    try:
        sig = _cached_signals()
        signal_summary = sig.overall_color.value.upper()
    except Exception:
        pass
    try:
        from rewired.portfolio.manager import load_portfolio
        pf = load_portfolio()
        portfolio_value = f"{pf.total_value_eur:.0f}"
        if pf.total_value_eur > 0:
            cash_pct = f"{pf.cash_eur / pf.total_value_eur * 100:.1f}"
    except Exception:
        pass

    prompt = SPIRIT_FOLLOWUP.format(
        history=history_str,
        signal_summary=signal_summary,
        portfolio_value=portfolio_value,
        cash_pct=cash_pct,
        question=question,
    )

    return generate(prompt, system_instruction=SYSTEM_SPIRIT)


# ── Data helpers ─────────────────────────────────────────────────────


def _get_signal_summary() -> str:
    """Get current signals as text for the prompt."""
    try:
        sig = _cached_signals()

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

        uni = load_universe()
        pf = load_portfolio()
        if pf.positions:
            refresh_prices(pf)
        sig = _cached_signals()
        allocs = calculate_pies_allocation(pf, uni, sig)

        lines = []
        for a in allocs:
            lines.append(f"  {a['ticker']} ({a['layer']}/{a['tier']}): {a['target_pct']}% = {a['target_eur']:.0f} EUR")
        return "\n".join(lines)
    except Exception as e:
        return f"[Error fetching pies: {e}]"
