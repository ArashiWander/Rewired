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
CATEGORY_WEIGHTS = {
    SignalCategory.MACRO: 0.30,
    SignalCategory.SENTIMENT: 0.30,
    SignalCategory.AI_HEALTH: 0.40,
}


def compute_composite(categories: dict[SignalCategory, CategorySignal]) -> SignalColor:
    """Compute overall signal color from category signals.

    Uses weighted average with worst-of override:
    - If any category is RED, composite cannot be better than ORANGE.
    """
    if not categories:
        return SignalColor.YELLOW

    # Weighted score
    total_weight = 0.0
    weighted_score = 0.0
    for cat, signal in categories.items():
        w = CATEGORY_WEIGHTS.get(cat, 0.3)
        weighted_score += SIGNAL_SCORES[signal.composite_color] * w
        total_weight += w

    if total_weight > 0:
        weighted_score /= total_weight

    color = score_to_color(weighted_score)

    # Worst-of override: if any RED, composite is at least ORANGE
    any_red = any(s.composite_color == SignalColor.RED for s in categories.values())
    if any_red and color in (SignalColor.GREEN, SignalColor.YELLOW):
        color = SignalColor.ORANGE

    return color
