"""AI structural health signal calculator — pure Python math trend computation.

The LLM is confined to flat-JSON extraction.  All CAPEX trend analysis
(VETO, acceleration, deceleration, stable) is computed here using
deterministic mathematical derivatives on the validated per-company data.
"""

from __future__ import annotations

import logging
from datetime import datetime

import yaml

from rewired import get_config_dir
from rewired.data.ai_health import get_ai_health_readings
from rewired.models.signals import (
    CategorySignal,
    SignalCategory,
    SignalColor,
)
from rewired.signals.rules import evaluate_ai_health_rules

logger = logging.getLogger(__name__)

_BIG4 = ("MSFT", "GOOGL", "AMZN", "META")


def _load_ai_health_config() -> dict:
    """Load ai_health rules config (fresh each call, per convention)."""
    config_path = get_config_dir() / "signals.yaml"
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("ai_health", {}).get("rules", {})


def calculate_ai_health_signal() -> CategorySignal:
    """Calculate AI health signal using deterministic boolean rules.

    1. Fetch readings (LLM extraction + quantitative ETF momentum).
    2. Compute CAPEX trend via pure Python math (veto → acceleration).
    3. Inject computed trend into the reading metadata.
    4. Delegate final color assignment to the rules engine.
    """
    readings = get_ai_health_readings()
    now = datetime.now()

    if not readings:
        return CategorySignal(
            category=SignalCategory.AI_HEALTH,
            readings=[],
            composite_color=SignalColor.ORANGE,
            timestamp=now,
            explanation="No AI health data available - defaulting to ORANGE (defensive)",
            rule_triggered="DATA_MISSING",
        )

    # Find the CAPEX extraction reading and compute trend
    capex_reading = None
    for r in readings:
        if r.name == "AI CAPEX Health (Agent)":
            capex_reading = r
            break

    if capex_reading is not None:
        trend = _compute_capex_trend(capex_reading.metadata)
        # Inject computed trend back into metadata for rules engine
        capex_reading.metadata["capex_trend"] = trend
        # Override veto_triggered based on pure math (belt-and-suspenders)
        if trend == "contracting":
            capex_reading.metadata["veto_triggered"] = True

    color, explanation = evaluate_ai_health_rules(readings)

    return CategorySignal(
        category=SignalCategory.AI_HEALTH,
        readings=readings,
        composite_color=color,
        timestamp=now,
        explanation=explanation,
        rule_triggered=explanation.split(":")[0] if ":" in explanation else color.value,
    )


def _compute_capex_trend(metadata: dict) -> str:
    """Compute CAPEX trend from validated per-company data using pure math.

    Decision tree (evaluated in order, first match wins):

    1. VETO (CONTRACTING): If ANY Big 4 has significant YoY contraction
       (< -5%) AND management quote contains fatal phrasing
       → "contracting" (RED)

    2. MILD-DIP ORANGE: If ANY Big 4 has a mild YoY dip (−5% to 0%) AND
       ≥ N/2 companies are dipping → "decelerating" (ORANGE)

    3. DECELERATING: Compute acceleration = current_qoq - previous_qoq.
       If acceleration ≤ 0 for 2 consecutive quarters for ≥ N/2 companies
       → "decelerating" (ORANGE)

    4. ACCELERATING: If acceleration > 0 for ≥ N/2 companies
       → "accelerating" (GREEN)

    5. Otherwise → "stable" (YELLOW)
    """
    companies = metadata.get("companies", {})
    if not companies:
        return "unknown"

    # Load configurable thresholds
    cfg = _load_ai_health_config()
    red_cfg = cfg.get("red", {})
    yoy_threshold = red_cfg.get("yoy_contraction_threshold", -5.0)
    fatal_phrases = [p.lower() for p in red_cfg.get("fatal_phrases", [
        "weakening demand", "ROI pressure", "cutting infrastructure spend",
    ])]

    # ── VETO check: significant contraction AND fatal phrasing ────────
    valid_companies = [t for t in _BIG4 if t in companies]
    mild_dip_count = 0

    for ticker in _BIG4:
        co = companies.get(ticker, {})
        yoy = co.get("yoy_growth_pct", 0.0)
        quote = co.get("exact_capex_quote", "").lower()

        # RED: significant contraction AND fatal management language
        if yoy < yoy_threshold and any(phrase in quote for phrase in fatal_phrases):
            logger.warning(
                "CAPEX VETO: %s YoY %.1f%% < %.1f%% with fatal phrasing",
                ticker, yoy, yoy_threshold,
            )
            return "contracting"

        # Track mild dips (efficiency phase → ORANGE route)
        if yoy_threshold <= yoy < 0.0:
            mild_dip_count += 1

    n = len(valid_companies)
    if n == 0:
        return "unknown"

    # ── Mild-dip ORANGE: ≥ N/2 companies with minor YoY contraction ──
    if mild_dip_count >= (n / 2):
        logger.info("CAPEX mild dip: %d/%d companies in efficiency phase", mild_dip_count, n)
        return "decelerating"

    # ── Velocity & Acceleration check ─────────────────────────────────
    history = metadata.get("quarterly_history", [])

    # If we have at least 2 quarters of history, compute acceleration
    if len(history) >= 2:
        current_q = history[-1]
        previous_q = history[-2]

        accelerating_count = 0
        decelerating_count = 0

        for ticker in valid_companies:
            curr_data = current_q.get(ticker, {})
            prev_data = previous_q.get(ticker, {})

            curr_qoq = curr_data.get("qoq_growth_pct", 0.0)
            prev_qoq = prev_data.get("qoq_growth_pct", 0.0)

            acceleration = curr_qoq - prev_qoq

            if acceleration > 0.0:
                accelerating_count += 1
            elif acceleration <= 0.0:
                decelerating_count += 1

        # Check for 2 consecutive quarters of deceleration
        decel_consecutive = _check_consecutive_deceleration(
            history, valid_companies, n,
        )

        if decel_consecutive and decelerating_count >= (n / 2):
            return "decelerating"

        if accelerating_count >= (n / 2):
            return "accelerating"

        return "stable"

    # Single quarter: use raw QoQ growth to approximate
    positive_growth_count = 0
    for ticker in valid_companies:
        co = companies.get(ticker, {})
        if co.get("qoq_growth_pct", 0.0) > 0:
            positive_growth_count += 1

    if positive_growth_count >= (n / 2):
        return "accelerating"

    return "stable"


def _check_consecutive_deceleration(
    history: list[dict],
    valid_companies: list[str],
    n: int,
) -> bool:
    """Check if ≥ N/2 companies had deceleration for 2 consecutive quarters.

    Returns True only if the deceleration pattern holds across the two
    most recent quarter transitions (Q[-2]→Q[-1] AND Q[-3]→Q[-2]).
    """
    if len(history) < 3:
        return False

    threshold = n / 2

    # Check transition Q[-3] → Q[-2]
    q_prev2 = history[-3]
    q_prev1 = history[-2]
    decel_prev = 0
    for ticker in valid_companies:
        p2 = q_prev2.get(ticker, {}).get("qoq_growth_pct", 0.0)
        p1 = q_prev1.get(ticker, {}).get("qoq_growth_pct", 0.0)
        if (p1 - p2) <= 0.0:
            decel_prev += 1

    # Check transition Q[-2] → Q[-1]
    q_curr = history[-1]
    decel_curr = 0
    for ticker in valid_companies:
        p1 = q_prev1.get(ticker, {}).get("qoq_growth_pct", 0.0)
        c = q_curr.get(ticker, {}).get("qoq_growth_pct", 0.0)
        if (c - p1) <= 0.0:
            decel_curr += 1

    return decel_prev >= threshold and decel_curr >= threshold
