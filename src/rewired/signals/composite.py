"""Composite signal aggregation — truth-table waterfall (no weighted averaging).

Rules are evaluated top-to-bottom, most defensive first.  The first
matching row determines the composite color.  AI Health RED is an
absolute veto that overrides all other signals to RED.
"""

from __future__ import annotations

from rewired.models.signals import (
    CategorySignal,
    SignalCategory,
    SignalColor,
    SIGNAL_SCORES,
    score_to_color,
)

# Category weights retained for backward compat / GUI display only.
# They are NOT used in the truth-table evaluation path.
CATEGORY_WEIGHTS = {
    SignalCategory.MACRO: 0.30,
    SignalCategory.SENTIMENT: 0.30,
    SignalCategory.AI_HEALTH: 0.40,
}


def compute_composite(
    categories: dict[SignalCategory, CategorySignal],
) -> tuple[SignalColor, bool, dict]:
    """Compute overall signal color via deterministic truth-table waterfall.

    Evaluation order (first match wins):
      0. AI_HEALTH RED → global RED (absolute veto)
      1. Any category RED → ORANGE floor (worst-of override)
      2. AI_HEALTH ORANGE → composite cannot exceed ORANGE
      3. MACRO RED or SENTIMENT RED → composite = ORANGE
      4. All three GREEN → GREEN
      5. ≥2 categories GREEN, no ORANGE or RED → GREEN
      6. Any ORANGE present → YELLOW
      7. Default → YELLOW

    Returns ``(color, veto_active, transparency)`` where *transparency*
    contains the full decision breakdown for the Glass-Box UI.
    """
    transparency: dict = {
        "category_colors": {},
        "rule_matched": "",
        "veto_active": False,
        "final_color": "",
    }

    if not categories:
        transparency["rule_matched"] = "NO_DATA_DEFAULT_YELLOW"
        transparency["final_color"] = SignalColor.YELLOW.value
        return SignalColor.YELLOW, False, transparency

    # Extract per-category colors
    macro_color = _cat_color(categories, SignalCategory.MACRO)
    sentiment_color = _cat_color(categories, SignalCategory.SENTIMENT)
    ai_color = _cat_color(categories, SignalCategory.AI_HEALTH)

    transparency["category_colors"] = {
        "macro": macro_color.value if macro_color else "missing",
        "sentiment": sentiment_color.value if sentiment_color else "missing",
        "ai_health": ai_color.value if ai_color else "missing",
    }

    colors = [c for c in (macro_color, sentiment_color, ai_color) if c is not None]

    # ── Rule 0: AI Health VETO (absolute) ─────────────────────────────
    if ai_color == SignalColor.RED:
        transparency["veto_active"] = True
        transparency["rule_matched"] = "AI_HEALTH_VETO_RED"
        transparency["final_color"] = SignalColor.RED.value
        return SignalColor.RED, True, transparency

    # ── Rule 1: Any category RED → ORANGE floor ──────────────────────
    if SignalColor.RED in colors:
        transparency["rule_matched"] = "ANY_RED_FLOOR_ORANGE"
        transparency["final_color"] = SignalColor.ORANGE.value
        return SignalColor.ORANGE, False, transparency

    # ── Rule 2: AI Health ORANGE → cap at ORANGE ─────────────────────
    if ai_color == SignalColor.ORANGE:
        transparency["rule_matched"] = "AI_HEALTH_ORANGE_CAP"
        transparency["final_color"] = SignalColor.ORANGE.value
        return SignalColor.ORANGE, False, transparency

    # ── Rule 3: Two or more ORANGE → ORANGE ──────────────────────────
    orange_count = colors.count(SignalColor.ORANGE)
    if orange_count >= 2:
        transparency["rule_matched"] = "MULTI_ORANGE_FLOOR"
        transparency["final_color"] = SignalColor.ORANGE.value
        return SignalColor.ORANGE, False, transparency

    # ── Rule 4: All GREEN → GREEN ────────────────────────────────────
    if all(c == SignalColor.GREEN for c in colors) and len(colors) == 3:
        transparency["rule_matched"] = "ALL_GREEN"
        transparency["final_color"] = SignalColor.GREEN.value
        return SignalColor.GREEN, False, transparency

    # ── Rule 5: ≥2 GREEN, no ORANGE/RED → GREEN ─────────────────────
    green_count = colors.count(SignalColor.GREEN)
    if green_count >= 2 and orange_count == 0:
        transparency["rule_matched"] = "MAJORITY_GREEN"
        transparency["final_color"] = SignalColor.GREEN.value
        return SignalColor.GREEN, False, transparency

    # ── Rule 6: Any single ORANGE → YELLOW ──────────────────────────
    if orange_count >= 1:
        transparency["rule_matched"] = "SINGLE_ORANGE_YELLOW"
        transparency["final_color"] = SignalColor.YELLOW.value
        return SignalColor.YELLOW, False, transparency

    # ── Rule 7: Default → YELLOW ─────────────────────────────────────
    transparency["rule_matched"] = "DEFAULT_YELLOW"
    transparency["final_color"] = SignalColor.YELLOW.value
    return SignalColor.YELLOW, False, transparency


def _cat_color(
    categories: dict[SignalCategory, CategorySignal],
    cat: SignalCategory,
) -> SignalColor | None:
    """Extract color for a category, or None if missing."""
    sig = categories.get(cat)
    return sig.composite_color if sig else None
