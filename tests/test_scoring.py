"""Tests for scoring convention: polarity flip (GREEN=4, RED=1).

Verifies the SIGNAL_SCORES mapping and score_to_color round-trip
functions conform to the blueprint convention.
"""

from __future__ import annotations

import pytest

from rewired.models.signals import SignalColor, SIGNAL_SCORES, score_to_color


class TestSignalScores:
    """Verify the numeric score mapping."""

    def test_green_is_4(self):
        assert SIGNAL_SCORES[SignalColor.GREEN] == 4.0

    def test_yellow_is_3(self):
        assert SIGNAL_SCORES[SignalColor.YELLOW] == 3.0

    def test_orange_is_2(self):
        assert SIGNAL_SCORES[SignalColor.ORANGE] == 2.0

    def test_red_is_1(self):
        assert SIGNAL_SCORES[SignalColor.RED] == 1.0

    def test_higher_is_better(self):
        """GREEN > YELLOW > ORANGE > RED in numeric value."""
        assert (
            SIGNAL_SCORES[SignalColor.GREEN]
            > SIGNAL_SCORES[SignalColor.YELLOW]
            > SIGNAL_SCORES[SignalColor.ORANGE]
            > SIGNAL_SCORES[SignalColor.RED]
        )


class TestScoreToColor:
    """Verify the score → color conversion thresholds."""

    @pytest.mark.parametrize("score,expected", [
        (4.0, SignalColor.GREEN),
        (3.5, SignalColor.GREEN),
        (3.49, SignalColor.YELLOW),
        (3.0, SignalColor.YELLOW),
        (2.5, SignalColor.YELLOW),
        (2.49, SignalColor.ORANGE),
        (2.0, SignalColor.ORANGE),
        (1.5, SignalColor.ORANGE),
        (1.49, SignalColor.RED),
        (1.0, SignalColor.RED),
        (0.5, SignalColor.RED),
    ])
    def test_thresholds(self, score, expected):
        assert score_to_color(score) == expected

    def test_roundtrip_green(self):
        """GREEN (4.0) → score_to_color → GREEN."""
        score = SIGNAL_SCORES[SignalColor.GREEN]
        assert score_to_color(score) == SignalColor.GREEN

    def test_roundtrip_red(self):
        score = SIGNAL_SCORES[SignalColor.RED]
        assert score_to_color(score) == SignalColor.RED

    def test_boundary_3_5(self):
        """Exactly 3.5 → GREEN (≥ 3.5)."""
        assert score_to_color(3.5) == SignalColor.GREEN

    def test_boundary_2_5(self):
        """Exactly 2.5 → YELLOW (≥ 2.5)."""
        assert score_to_color(2.5) == SignalColor.YELLOW

    def test_boundary_1_5(self):
        """Exactly 1.5 → ORANGE (≥ 1.5)."""
        assert score_to_color(1.5) == SignalColor.ORANGE
