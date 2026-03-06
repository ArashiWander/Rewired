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


def compute_composite(
    categories: dict[SignalCategory, CategorySignal],
) -> tuple[SignalColor, bool, dict]:
    """Compute overall signal color from category signals.

    Uses weighted average with worst-of override:
    - If any category is RED, composite cannot be better than ORANGE.
    - If AI_HEALTH is RED, absolute veto → force RED.

    Returns ``(color, veto_active, transparency)`` where *transparency*
    contains the full calculation breakdown for the Glass-Box UI.
    """
    transparency: dict = {
        "category_scores": {},
        "weights": {k.value: v for k, v in CATEGORY_WEIGHTS.items()},
        "weighted_terms": {},
        "weighted_sum": 0.0,
        "pre_override_color": "",
        "override_applied": "none",
        "final_color": "",
    }

    if not categories:
        transparency["final_color"] = SignalColor.YELLOW.value
        return SignalColor.YELLOW, False, transparency

    # Weighted score
    total_weight = 0.0
    weighted_score = 0.0
    for cat, signal in categories.items():
        w = CATEGORY_WEIGHTS.get(cat, 0.3)
        cat_score = SIGNAL_SCORES[signal.composite_color]
        weighted_score += cat_score * w
        total_weight += w
        transparency["category_scores"][cat.value] = {
            "color": signal.composite_color.value,
            "score": cat_score,
        }
        transparency["weighted_terms"][cat.value] = round(cat_score * w, 4)

    if total_weight > 0:
        weighted_score /= total_weight

    transparency["weighted_sum"] = round(weighted_score, 4)
    color = score_to_color(weighted_score)
    transparency["pre_override_color"] = color.value

    # AI Health veto: if AI_HEALTH is RED → force overall RED
    veto_active = False
    ai_sig = categories.get(SignalCategory.AI_HEALTH)
    if ai_sig and ai_sig.composite_color == SignalColor.RED:
        veto_active = True
        color = SignalColor.RED
        transparency["override_applied"] = "ai_health_veto"

    # Worst-of override: if any other RED, composite is at most ORANGE
    if not veto_active:
        any_red = any(s.composite_color == SignalColor.RED for s in categories.values())
        if any_red and color in (SignalColor.GREEN, SignalColor.YELLOW):
            color = SignalColor.ORANGE
            transparency["override_applied"] = "worst_of_orange"

    transparency["final_color"] = color.value
    return color, veto_active, transparency
