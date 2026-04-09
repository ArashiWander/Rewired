"""Tests for composite signal — divergence-aware truth-table waterfall."""

from __future__ import annotations

import pytest

from rewired.models.signals import (
    CategorySignal,
    SignalCategory,
    SignalColor,
)
from rewired.signals.composite import CATEGORY_WEIGHTS, compute_composite
from tests.conftest import make_category_signal


class TestCategoryWeights:
    """Weights sum to 1.0 with updated sentiment/AI split."""

    def test_weights_sum_to_one(self):
        total = sum(CATEGORY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_ai_health_largest_weight(self):
        assert CATEGORY_WEIGHTS[SignalCategory.AI_HEALTH] == 0.50


class TestTruthTableWaterfall:
    """Divergence-aware truth-table waterfall: first matching rule wins."""

    def test_all_green(self):
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.GREEN
        assert veto is False
        # Rule 2 (macro green) fires before Rule 6 (all green)
        assert transparency["rule_matched"] == "MACRO_GREEN_CONTRARIAN"

    def test_all_red_triggers_veto(self):
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.RED),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.RED),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.RED),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.RED
        assert veto is True
        assert transparency["rule_matched"] == "AI_HEALTH_VETO_RED"

    def test_majority_green_no_orange(self):
        """MACRO YELLOW + AI GREEN + SENTIMENT GREEN → majority green."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.YELLOW),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.GREEN
        assert transparency["rule_matched"] == "MAJORITY_GREEN"

    def test_empty_categories_default_yellow(self):
        color, veto, transparency = compute_composite({})
        assert color == SignalColor.YELLOW
        assert veto is False

    def test_single_orange_yields_yellow(self):
        """MACRO YELLOW + SENTIMENT ORANGE + AI YELLOW → YELLOW."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.YELLOW),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.ORANGE),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.YELLOW),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.YELLOW
        assert transparency["rule_matched"] == "SINGLE_ORANGE_YELLOW"


class TestVetoOverride:
    """AI Health RED triggers absolute veto; ORANGE caps composite."""

    def test_ai_health_red_veto(self):
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.RED),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.RED
        assert veto is True
        assert transparency["rule_matched"] == "AI_HEALTH_VETO_RED"

    def test_ai_health_orange_no_veto(self):
        """AI Health ORANGE → caps at ORANGE, no veto flag."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.ORANGE),
        }
        color, veto, transparency = compute_composite(cats)
        assert veto is False
        assert color == SignalColor.ORANGE
        assert transparency["rule_matched"] == "AI_HEALTH_ORANGE_CAP"

    def test_ai_health_orange_overrides_macro_green(self):
        """AI ORANGE caps composite even when MACRO is GREEN (Rule 1 > Rule 2)."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.RED),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.ORANGE),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.ORANGE
        assert transparency["rule_matched"] == "AI_HEALTH_ORANGE_CAP"


class TestDivergenceLogic:
    """Core contrarian divergence rules — the heart of the philosophy."""

    def test_macro_green_sentiment_red_caps_yellow(self):
        """MACRO GREEN + SENTIMENT RED → YELLOW (liquidity crisis cap).

        The contrarian rule is carved out for sentiment RED — a genuine
        liquidity crisis (VXN > 35 + backwardation) is no longer ignored.
        """
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.RED),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.YELLOW
        assert veto is False
        assert transparency["rule_matched"] == "MACRO_GREEN_SENTIMENT_CRISIS_CAP"

    def test_macro_green_sentiment_yellow_still_contrarian(self):
        """MACRO GREEN + SENTIMENT YELLOW → GREEN (contrarian still fires)."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.YELLOW),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.GREEN
        assert transparency["rule_matched"] == "MACRO_GREEN_CONTRARIAN"

    def test_macro_green_overrides_sentiment_orange(self):
        """MACRO GREEN + SENTIMENT ORANGE → GREEN (divergence)."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.ORANGE),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.GREEN
        assert transparency["rule_matched"] == "MACRO_GREEN_CONTRARIAN"

    def test_macro_red_floor_orange(self):
        """MACRO RED → composite floor = ORANGE."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.RED),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.ORANGE
        assert veto is False
        assert transparency["rule_matched"] == "MACRO_RED_FLOOR_ORANGE"

    def test_complacency_trap(self):
        """MACRO ORANGE + SENTIMENT GREEN → ORANGE (complacency trap)."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.ORANGE),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.ORANGE
        assert transparency["rule_matched"] == "COMPLACENCY_TRAP_ORANGE"

    def test_complacency_trap_with_yellow_sentiment(self):
        """MACRO ORANGE + SENTIMENT YELLOW → ORANGE (still complacent)."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.ORANGE),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.YELLOW),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.ORANGE
        assert transparency["rule_matched"] == "COMPLACENCY_TRAP_ORANGE"

    def test_market_pricing_in(self):
        """MACRO ORANGE + SENTIMENT RED → YELLOW (market already fearful)."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.ORANGE),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.RED),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.YELLOW
        assert transparency["rule_matched"] == "MACRO_WEAK_SENTIMENT_PRICING_IN"

    def test_market_pricing_in_orange_sentiment(self):
        """MACRO ORANGE + SENTIMENT ORANGE → YELLOW (fearful markets)."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.ORANGE),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.ORANGE),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.YELLOW
        assert transparency["rule_matched"] == "MACRO_WEAK_SENTIMENT_PRICING_IN"
