"""Boolean rules engine for deterministic signal evaluation.

Implements the Rewired Index decision rules as strict IF-THEN logic trees.
Rules are evaluated top-to-bottom (most defensive first).  The first matching
rule determines the category color.  If no rule matches, defaults to YELLOW.
If critical data is missing, defaults to ORANGE (defensive).

Architecture principle: Cold Determinism.  No dialectical analysis,
no "however/but", no "on the other hand".  Boolean conditions only.
If multiple conditions conflict, the most defensive rule takes precedence.
"""

from __future__ import annotations

import yaml
from typing import Any

from rewired import get_config_dir
from rewired.models.signals import SignalColor, SignalReading


# ── Config loader ─────────────────────────────────────────────────────────


def _load_signal_config() -> dict:
    """Load and validate signal rules configuration (fresh each call)."""
    from rewired.models.config import SignalRulesConfig

    config_path = get_config_dir() / "signals.yaml"
    validated = SignalRulesConfig.from_yaml(config_path)
    # Return as dict for backward compatibility with rules engine internals
    return validated.model_dump()


# ── Helpers ───────────────────────────────────────────────────────────────


def _find_reading(readings: list[SignalReading], name: str) -> SignalReading | None:
    """Find a reading by name (case-insensitive)."""
    for r in readings:
        if r.name.lower() == name.lower():
            return r
    return None


def _get_meta(reading: SignalReading | None, key: str, default: Any = None) -> Any:
    """Safely get metadata value from a reading."""
    if reading is None:
        return default
    return reading.metadata.get(key, default)


# ── Macro Rules ───────────────────────────────────────────────────────────


def evaluate_macro_rules(readings: list[SignalReading]) -> tuple[SignalColor, str]:
    """Evaluate macro boolean rules.  Most defensive rule wins.

    RED (1pt):    PMI < 48 for 2 consecutive months AND Retail Sales MoM negative.
    ORANGE (2pt): Core PCE > 0.2% MoM AND Yield Curve (10Y-2Y) inverted.
    YELLOW (3pt): Unemployment rises > 0.2% in single month BUT PMI > 50.
    GREEN (4pt):  PMI > 50 AND disinflation trend intact (PCE at/below 0.2%).
    """
    cfg = _load_signal_config().get("macro", {}).get("rules", {})

    pmi = _find_reading(readings, "ISM PMI")
    retail = _find_reading(readings, "Retail Sales MoM")
    pce = _find_reading(readings, "Core PCE MoM")
    yield_curve = _find_reading(readings, "Yield Curve (10Y-2Y)")
    unemployment = _find_reading(readings, "Unemployment MoM Change")

    # ── Data availability check ───────────────────────────────────────
    if pmi is None and pce is None and retail is None:
        return SignalColor.ORANGE, "DATA_MISSING: No critical macro metrics available"

    # ── RED: Confirmed Recession ──────────────────────────────────────
    pmi_threshold = cfg.get("red", {}).get("pmi_threshold", 48)
    pmi_months = cfg.get("red", {}).get("pmi_consecutive_months", 2)

    if pmi is not None and retail is not None:
        consecutive_below = _get_meta(pmi, "consecutive_below_threshold", 0)
        if pmi.value < pmi_threshold and consecutive_below >= pmi_months and retail.value < 0:
            return SignalColor.RED, (
                f"Confirmed recession: PMI {pmi.value:.1f} < {pmi_threshold} for "
                f"{consecutive_below} months, Retail Sales {retail.value:+.1f}% MoM"
            )

    # ── ORANGE: Stagflation / Defense ─────────────────────────────────
    pce_threshold = cfg.get("orange", {}).get("pce_mom_threshold", 0.2)

    if pce is not None and yield_curve is not None:
        if pce.value > pce_threshold and yield_curve.value < 0:
            return SignalColor.ORANGE, (
                f"Stagflation risk: Core PCE {pce.value:.2f}% MoM > {pce_threshold}% "
                f"AND Yield Curve inverted at {yield_curve.value:+.2f}%"
            )

    # ── YELLOW: Slowdown / Transition ─────────────────────────────────
    unemp_threshold = cfg.get("yellow", {}).get("unemployment_mom_rise", 0.2)

    if unemployment is not None and pmi is not None:
        mom_change = _get_meta(unemployment, "mom_change", unemployment.value)
        if mom_change > unemp_threshold and pmi.value > 50:
            return SignalColor.YELLOW, (
                f"Slowdown: Unemployment +{mom_change:.2f}% MoM "
                f"but PMI {pmi.value:.1f} still expansionary"
            )

    # ── GREEN: Goldilocks ─────────────────────────────────────────────
    if pmi is not None:
        pce_ok = pce is None or pce.value <= cfg.get("green", {}).get("pce_mom_max", 0.2)
        if pmi.value > 50 and pce_ok:
            return SignalColor.GREEN, (
                f"Goldilocks: PMI {pmi.value:.1f} > 50"
                + (f", Core PCE {pce.value:.2f}% MoM in line" if pce else "")
            )

    # ── Default: no clear rule match ──────────────────────────────────
    return SignalColor.YELLOW, "Mixed macro signals - no clear rule triggered"


# ── Sentiment Rules ───────────────────────────────────────────────────────


def evaluate_sentiment_rules(readings: list[SignalReading]) -> tuple[SignalColor, str]:
    """Evaluate sentiment boolean rules.  Most defensive rule wins.

    Dual Radar:
      Radar A (VIX/VIX3M): contango/backwardation for liquidity assessment.
      Radar B (VXN):        tech-sector panic threshold + 3-day velocity.

    RED (1pt):    VXN > 35 AND VIX term structure in severe backwardation.
    ORANGE (2pt): VXN > 25 AND 5MA > 20MA (expanding volatility trend).
    YELLOW (3pt): VXN 18-25, market seeking narrative.
    GREEN (4pt):  VXN < 18 AND VIX term structure in normal contango.
    """
    cfg = _load_signal_config().get("sentiment", {}).get("rules", {})

    vxn = _find_reading(readings, "VXN Level & Velocity")
    term_structure = _find_reading(readings, "VIX Term Structure")

    # ── Data availability check ───────────────────────────────────────
    if vxn is None:
        return SignalColor.ORANGE, "DATA_MISSING: VXN data unavailable"

    vxn_val = vxn.value
    # spread = VIX3M - VIX: positive = contango = calm, negative = backwardation = panic
    spread = term_structure.value if term_structure is not None else 0.0
    is_backwardation = term_structure is not None and spread < 0
    is_contango = term_structure is not None and spread > 0
    ma5_above_ma20 = _get_meta(vxn, "ma5_above_ma20", False)
    velocity_3d_pct = _get_meta(vxn, "velocity_3d_pct", 0.0) or 0.0

    # ── VELOCITY GATE: 3-day spike → force ORANGE ─────────────────────
    vel_cfg = _load_signal_config().get("sentiment", {}).get("data_sources", {}).get("velocity", {})
    spike_threshold = vel_cfg.get("spike_threshold_pct", 20.0)
    min_absolute = vel_cfg.get("min_absolute", 18)
    if velocity_3d_pct > spike_threshold and vxn_val > min_absolute:
        return SignalColor.ORANGE, (
            f"Velocity spike: VXN surged {velocity_3d_pct:.1f}% in 3 trading days "
            f"(>{spike_threshold}%) with VXN {vxn_val:.1f} > {min_absolute}"
        )

    # ── RED: Liquidity Crisis ─────────────────────────────────────────
    red_vxn = cfg.get("red", {}).get("vxn_above", 35)
    if vxn_val > red_vxn and is_backwardation:
        return SignalColor.RED, (
            f"Liquidity crisis: VXN {vxn_val:.1f} > {red_vxn} "
            f"with backwardation (spread: {spread:+.1f})"
        )

    # ── ORANGE: Deteriorating ─────────────────────────────────────────
    orange_vxn = cfg.get("orange", {}).get("vxn_above", 25)
    if vxn_val > orange_vxn and ma5_above_ma20:
        return SignalColor.ORANGE, (
            f"Deteriorating: VXN {vxn_val:.1f} > {orange_vxn} "
            f"with 5MA > 20MA (expanding volatility)"
        )

    # ORANGE fallback: VXN > threshold even without trend data
    if vxn_val > orange_vxn:
        return SignalColor.ORANGE, f"Elevated risk: VXN {vxn_val:.1f} > {orange_vxn}"

    # ── YELLOW: Divergence ────────────────────────────────────────────
    yellow_low = cfg.get("yellow", {}).get("vxn_low", 18)
    yellow_high = cfg.get("yellow", {}).get("vxn_high", 25)
    if yellow_low <= vxn_val <= yellow_high:
        return SignalColor.YELLOW, (
            f"Divergence: VXN {vxn_val:.1f} in {yellow_low}-{yellow_high} range, "
            f"market seeking direction"
        )

    # ── GREEN: Stable / Complacent ────────────────────────────────────
    green_vxn = cfg.get("green", {}).get("vxn_below", 18)
    if vxn_val < green_vxn and is_contango:
        return SignalColor.GREEN, (
            f"Stable/Complacent: VXN {vxn_val:.1f} < {green_vxn} "
            f"with contango (spread: {spread:+.1f})"
        )

    # VXN < threshold but no contango confirmation
    if vxn_val < green_vxn:
        return SignalColor.GREEN, f"Low volatility: VXN {vxn_val:.1f} < {green_vxn}"

    return SignalColor.YELLOW, "Mixed sentiment signals"


# ── AI Health Rules ───────────────────────────────────────────────────────


def evaluate_ai_health_rules(readings: list[SignalReading]) -> tuple[SignalColor, str]:
    """Evaluate AI structural health rules. AI Health has ABSOLUTE VETO POWER.

    RED (1pt, VETO):  ANY Big 4 CapEx CUT announced.  Overrides all signals.
    ORANGE (2pt):     CapEx growing but YoY growth halved for 2 consecutive Qs.
    YELLOW (3pt):     CapEx meets but doesn't beat estimates.  Plateau phase.
    GREEN (4pt):      CapEx beats QoQ, "unprecedented demand" language confirmed.
    """
    capex = _find_reading(readings, "AI CAPEX Health (Agent)")

    if capex is None:
        return SignalColor.ORANGE, "DATA_MISSING: CAPEX analysis unavailable"

    capex_trend = _get_meta(capex, "capex_trend", "unknown")
    veto_triggered = _get_meta(capex, "veto_triggered", False)
    key_quote = _get_meta(capex, "key_management_quote", "")

    # ── RED (VETO): CapEx CUT by any Big 4 ──────────────────────────
    if veto_triggered or capex_trend == "contracting":
        return SignalColor.RED, (
            f"VETO ACTIVATED: AI CAPEX cycle broken - trend: {capex_trend}"
            + (f". Quote: \"{key_quote[:120]}\"" if key_quote else "")
        )

    # ── ORANGE: ROI Anxiety ───────────────────────────────────────────
    if capex_trend == "decelerating":
        return SignalColor.ORANGE, (
            f"ROI anxiety: CAPEX growth decelerating significantly"
            + (f". {key_quote[:120]}" if key_quote else "")
        )

    # ── YELLOW: Digestion Phase ───────────────────────────────────────
    if capex_trend == "stable":
        return SignalColor.YELLOW, (
            f"Digestion phase: CAPEX at historic highs but plateauing"
            + (f". {key_quote[:120]}" if key_quote else "")
        )

    # ── GREEN: Arms Race Continues ────────────────────────────────────
    if capex_trend == "accelerating":
        return SignalColor.GREEN, (
            f"Arms race continues: CAPEX accelerating across Big 4"
            + (f". Quote: \"{key_quote[:120]}\"" if key_quote else "")
        )

    # Unknown trend - default to YELLOW (cautious)
    return SignalColor.YELLOW, f"CAPEX trend: {capex_trend} - insufficient data for clear signal"
