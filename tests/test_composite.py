"""Tests for composite signal calculation, veto override, and circuit breaker."""

from __future__ import annotations

import pytest

from rewired.models.signals import (
    CategorySignal,
    SignalCategory,
    SignalColor,
    SIGNAL_SCORES,
)
from rewired.signals.composite import CATEGORY_WEIGHTS, compute_composite
from tests.conftest import make_category_signal


class TestCategoryWeights:
    """Verify the documented weight distribution."""

    def test_weights_sum_to_one(self):
        total = sum(CATEGORY_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001

    def test_ai_health_weight_is_50(self):
        assert CATEGORY_WEIGHTS[SignalCategory.AI_HEALTH] == 0.50

    def test_macro_weight_is_30(self):
        assert CATEGORY_WEIGHTS[SignalCategory.MACRO] == 0.30

    def test_sentiment_weight_is_20(self):
        assert CATEGORY_WEIGHTS[SignalCategory.SENTIMENT] == 0.20


class TestCompositeCalculation:
    """Verify weighted average composite calculation."""

    def test_all_green(self):
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto = compute_composite(cats)
        assert color == SignalColor.GREEN
        assert veto is False

    def test_all_red(self):
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.RED),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.RED),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.RED),
        }
        color, veto = compute_composite(cats)
        assert color == SignalColor.RED
        assert veto is True  # AI health RED triggers veto

    def test_mixed_weighted_average(self):
        """Macro GREEN (4*0.3=1.2), Sentiment YELLOW (3*0.2=0.6), AI GREEN (4*0.5=2.0)
        Total = 3.8 → GREEN (>= 3.5)."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.YELLOW),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto = compute_composite(cats)
        assert color == SignalColor.GREEN
        assert veto is False

    def test_empty_categories(self):
        color, veto = compute_composite({})
        assert color == SignalColor.YELLOW
        assert veto is False


class TestVetoOverride:
    """AI Health RED triggers absolute veto → global signal = RED."""

    def test_ai_health_red_veto(self):
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.RED),
        }
        color, veto = compute_composite(cats)
        assert color == SignalColor.RED
        assert veto is True

    def test_ai_health_orange_no_veto(self):
        """AI Health ORANGE should NOT trigger veto."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.ORANGE),
        }
        color, veto = compute_composite(cats)
        assert veto is False


class TestWorstOfOverride:
    """Any non-AI category RED → composite floor = ORANGE."""

    def test_macro_red_caps_at_orange(self):
        """Macro RED + others GREEN → no better than ORANGE."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.RED),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.GREEN),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto = compute_composite(cats)
        assert color == SignalColor.ORANGE
        assert veto is False  # Only AI Health RED triggers veto

    def test_sentiment_red_caps_at_orange(self):
        """Sentiment RED + others GREEN → capped at ORANGE."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.GREEN),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.RED),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.GREEN),
        }
        color, veto = compute_composite(cats)
        assert color == SignalColor.ORANGE

    def test_already_orange_stays_orange(self):
        """If weighted average already yields ORANGE, worst-of doesn't change it."""
        cats = {
            SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, SignalColor.RED),
            SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, SignalColor.RED),
            SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, SignalColor.ORANGE),
        }
        color, veto = compute_composite(cats)
        # AI not RED so no veto; worst-of already in effect
        assert color in (SignalColor.ORANGE, SignalColor.RED)
        assert veto is False
