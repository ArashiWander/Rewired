"""Composite signal aggregation across all categories."""

from __future__ import annotations

from rewired.models.signals import (
    CategorySignal,
    CompositeSignal,
    SignalCategory,
    SignalColor,
    SIGNAL_SCORES,
    score_to_color,
)

# Category weights in composite (must sum to 1.0)
# Blueprint: AI Health 50%, Macro 30%, Sentiment 20%
CATEGORY_WEIGHTS = {
    SignalCategory.MACRO: 0.30,
    SignalCategory.SENTIMENT: 0.20,
    SignalCategory.AI_HEALTH: 0.50,
}


def compute_composite(categories: dict[SignalCategory, CategorySignal]) -> tuple[SignalColor, bool]:
    """Compute overall signal color from category signals.

    Uses weighted average with two override rules:
    - AI Health RED triggers ABSOLUTE VETO -> global signal = RED.
    - Any other category RED -> composite floor = ORANGE.

    Returns (color, veto_active) tuple.
    """
    if not categories:
        return SignalColor.YELLOW, False

    # AI Health absolute veto: if AI Health is RED, entire signal = RED
    ai_health = categories.get(SignalCategory.AI_HEALTH)
    if ai_health and ai_health.composite_color == SignalColor.RED:
        return SignalColor.RED, True

    # Weighted score (higher = better)
    total_weight = 0.0
    weighted_score = 0.0
    for cat, signal in categories.items():
        w = CATEGORY_WEIGHTS.get(cat, 0.3)
        weighted_score += SIGNAL_SCORES[signal.composite_color] * w
        total_weight += w

    if total_weight > 0:
        weighted_score /= total_weight

    color = score_to_color(weighted_score)

    # Worst-of override: if any non-AI category is RED, floor = ORANGE
    any_red = any(
        s.composite_color == SignalColor.RED
        for cat, s in categories.items()
        if cat != SignalCategory.AI_HEALTH
    )
    if any_red and color in (SignalColor.GREEN, SignalColor.YELLOW):
        color = SignalColor.ORANGE

    return color, False
