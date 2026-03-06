"""Tests for composite signal — truth-table waterfall (no weighted averaging)."""

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
    """Weights retained for backward compat — still sum to 1.0."""

    def test_weights_sum_to_one(self):
        total = sum(CATEGORY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001


class TestTruthTableWaterfall:
    """Truth-table waterfall: first matching rule wins."""

    def test_all_green(self):
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.GREEN
        assert veto is False
        assert transparency["rule_matched"] == "ALL_GREEN"

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
        """2 GREEN + 1 YELLOW → GREEN (majority green, no orange)."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.YELLOW),
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
        """1 ORANGE among green/yellow → YELLOW (not green)."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.ORANGE),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.YELLOW
        assert transparency["rule_matched"] == "SINGLE_ORANGE_YELLOW"

    def test_two_orange_yields_orange(self):
        """2 ORANGE → ORANGE floor."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.ORANGE),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.ORANGE),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.ORANGE
        assert transparency["rule_matched"] == "MULTI_ORANGE_FLOOR"


class TestVetoOverride:
    """AI Health RED triggers absolute veto → global signal = RED."""

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
        """AI Health ORANGE should NOT trigger veto but caps at ORANGE."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.ORANGE),
        }
        color, veto, transparency = compute_composite(cats)
        assert veto is False
        assert color == SignalColor.ORANGE
        assert transparency["rule_matched"] == "AI_HEALTH_ORANGE_CAP"


class TestWorstOfOverride:
    """Any non-AI category RED → composite floor = ORANGE."""

    def test_macro_red_caps_at_orange(self):
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.RED),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.ORANGE
        assert veto is False
        assert transparency["rule_matched"] == "ANY_RED_FLOOR_ORANGE"

    def test_sentiment_red_caps_at_orange(self):
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.RED),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto, transparency = compute_composite(cats)
        assert color == SignalColor.ORANGE
        assert transparency["rule_matched"] == "ANY_RED_FLOOR_ORANGE"
