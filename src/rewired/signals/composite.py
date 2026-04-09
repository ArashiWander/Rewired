"""Composite signal aggregation — divergence-aware truth-table waterfall.

Core philosophy: "不跟着情绪走，用经济硬数据和市场情绪的背离来判断攻守节奏"
(Don't follow emotions.  Use the DIVERGENCE between hard economic data
and market sentiment to determine offensive/defensive rhythm.)

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
    SignalCategory.SENTIMENT: 0.20,
    SignalCategory.AI_HEALTH: 0.50,
}


def compute_composite(
    categories: dict[SignalCategory, CategorySignal],
) -> tuple[SignalColor, bool, dict]:
    """Compute overall signal color via divergence-aware truth-table waterfall.

    Evaluation order (first match wins):
      0. AI_HEALTH RED        -> global RED (absolute veto)
      1. AI_HEALTH ORANGE     -> cap at ORANGE (AI uncertainty)
      2. MACRO GREEN + SENT RED -> YELLOW (liquidity crisis cap)
      2. MACRO GREEN (else)   -> GREEN (contrarian: strong fundamentals
         override market fear)
      3. MACRO RED            -> ORANGE floor (severe weakness)
      4. MACRO ORANGE + Sentiment GREEN/YELLOW -> ORANGE (complacency trap)
      5. MACRO ORANGE + Sentiment ORANGE/RED   -> YELLOW (market pricing in)
      6. All three GREEN      -> GREEN
      7. >=2 GREEN, no ORANGE/RED -> GREEN
      8. Any ORANGE present   -> YELLOW
      9. Default              -> YELLOW

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

    # -- Rule 0: AI Health VETO (absolute) -----------------------------
    if ai_color == SignalColor.RED:
        transparency["veto_active"] = True
        transparency["rule_matched"] = "AI_HEALTH_VETO_RED"
        transparency["final_color"] = SignalColor.RED.value
        return SignalColor.RED, True, transparency

    # -- Rule 1: AI Health ORANGE -> cap at ORANGE ---------------------
    if ai_color == SignalColor.ORANGE:
        transparency["rule_matched"] = "AI_HEALTH_ORANGE_CAP"
        transparency["final_color"] = SignalColor.ORANGE.value
        return SignalColor.ORANGE, False, transparency

    # -- Rule 2: MACRO GREEN -> GREEN (contrarian core) ----------------
    # Strong fundamentals override market sentiment — the key divergence
    # rule from the philosophy.  EXCEPTION: sentiment RED signals a
    # liquidity crisis (VXN > 35 + backwardation), not ordinary fear.
    # In that case cap at YELLOW: the contrarian rule applies to
    # divergence, not to systemic breakdown.
    if macro_color == SignalColor.GREEN:
        if sentiment_color == SignalColor.RED:
            transparency["rule_matched"] = "MACRO_GREEN_SENTIMENT_CRISIS_CAP"
            transparency["final_color"] = SignalColor.YELLOW.value
            return SignalColor.YELLOW, False, transparency
        transparency["rule_matched"] = "MACRO_GREEN_CONTRARIAN"
        transparency["final_color"] = SignalColor.GREEN.value
        return SignalColor.GREEN, False, transparency

    # -- Rule 3: MACRO RED -> ORANGE floor -----------------------------
    if macro_color == SignalColor.RED:
        transparency["rule_matched"] = "MACRO_RED_FLOOR_ORANGE"
        transparency["final_color"] = SignalColor.ORANGE.value
        return SignalColor.ORANGE, False, transparency

    # -- Rule 4: MACRO ORANGE + Sentiment calm -> ORANGE (complacency) -
    if macro_color == SignalColor.ORANGE and sentiment_color in (
        SignalColor.GREEN, SignalColor.YELLOW,
    ):
        transparency["rule_matched"] = "COMPLACENCY_TRAP_ORANGE"
        transparency["final_color"] = SignalColor.ORANGE.value
        return SignalColor.ORANGE, False, transparency

    # -- Rule 5: MACRO ORANGE + Sentiment fearful -> YELLOW ------------
    if macro_color == SignalColor.ORANGE and sentiment_color in (
        SignalColor.ORANGE, SignalColor.RED,
    ):
        transparency["rule_matched"] = "MACRO_WEAK_SENTIMENT_PRICING_IN"
        transparency["final_color"] = SignalColor.YELLOW.value
        return SignalColor.YELLOW, False, transparency

    # -- Rule 6: All GREEN -> GREEN ------------------------------------
    if all(c == SignalColor.GREEN for c in colors) and len(colors) == 3:
        transparency["rule_matched"] = "ALL_GREEN"
        transparency["final_color"] = SignalColor.GREEN.value
        return SignalColor.GREEN, False, transparency

    # -- Rule 7: >=2 GREEN, no ORANGE/RED -> GREEN ---------------------
    green_count = colors.count(SignalColor.GREEN)
    orange_count = colors.count(SignalColor.ORANGE)
    if green_count >= 2 and orange_count == 0 and SignalColor.RED not in colors:
        transparency["rule_matched"] = "MAJORITY_GREEN"
        transparency["final_color"] = SignalColor.GREEN.value
        return SignalColor.GREEN, False, transparency

    # -- Rule 8: Any ORANGE present -> YELLOW --------------------------
    if orange_count >= 1:
        transparency["rule_matched"] = "SINGLE_ORANGE_YELLOW"
        transparency["final_color"] = SignalColor.YELLOW.value
        return SignalColor.YELLOW, False, transparency

    # -- Rule 9: Default -> YELLOW -------------------------------------
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
