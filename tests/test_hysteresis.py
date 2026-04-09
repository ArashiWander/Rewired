"""Tests for the hysteresis state machine in engine.py.

The 3-day upgrade confirmation prevents whipsaw regime flips:
  - Downgrades are immediate.
  - Veto forces RED instantly.
  - Upgrades need 3 consecutive calendar days of the same signal.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from rewired.models.signals import RegimeState, SignalColor
from rewired.signals.engine import _apply_hysteresis


class TestImmediateDowngrade:
    """Downgrades bypass the confirmation window."""

    def test_green_to_red_immediate(self):
        state = RegimeState(current_regime=SignalColor.GREEN, last_updated=date.today())
        result = _apply_hysteresis(state, SignalColor.RED, veto=False)
        assert result == SignalColor.RED
        assert state.current_regime == SignalColor.RED
        assert state.pending_upgrade is None
        assert state.consecutive_days == 0

    def test_yellow_to_orange_immediate(self):
        state = RegimeState(current_regime=SignalColor.YELLOW, last_updated=date.today())
        result = _apply_hysteresis(state, SignalColor.ORANGE, veto=False)
        assert result == SignalColor.ORANGE

    def test_green_to_orange_immediate(self):
        state = RegimeState(current_regime=SignalColor.GREEN, last_updated=date.today())
        result = _apply_hysteresis(state, SignalColor.ORANGE, veto=False)
        assert result == SignalColor.ORANGE


class TestVetoOverride:
    """Veto always forces RED regardless of current regime."""

    def test_veto_from_green(self):
        state = RegimeState(current_regime=SignalColor.GREEN, last_updated=date.today())
        result = _apply_hysteresis(state, SignalColor.RED, veto=True)
        assert result == SignalColor.RED
        assert state.current_regime == SignalColor.RED

    def test_veto_cancels_pending_upgrade(self):
        state = RegimeState(
            current_regime=SignalColor.ORANGE,
            pending_upgrade=SignalColor.YELLOW,
            consecutive_days=2,
            last_updated=date.today() - timedelta(days=1),
        )
        result = _apply_hysteresis(state, SignalColor.RED, veto=True)
        assert result == SignalColor.RED
        assert state.pending_upgrade is None
        assert state.consecutive_days == 0


class TestUpgradeConfirmation:
    """Upgrades require 3 consecutive calendar days of the same signal."""

    def test_upgrade_starts_counting(self):
        state = RegimeState(
            current_regime=SignalColor.RED,
            last_updated=date.today() - timedelta(days=1),
        )
        result = _apply_hysteresis(state, SignalColor.ORANGE, veto=False)
        # Should NOT upgrade yet — day 1 of 3
        assert result == SignalColor.RED
        assert state.pending_upgrade == SignalColor.ORANGE
        assert state.consecutive_days == 1

    def test_upgrade_day_2(self):
        state = RegimeState(
            current_regime=SignalColor.RED,
            pending_upgrade=SignalColor.ORANGE,
            consecutive_days=1,
            last_updated=date.today() - timedelta(days=1),
        )
        result = _apply_hysteresis(state, SignalColor.ORANGE, veto=False)
        # Day 2 of 3 — still holding
        assert result == SignalColor.RED
        assert state.consecutive_days == 2

    def test_upgrade_day_3_confirms(self):
        state = RegimeState(
            current_regime=SignalColor.RED,
            pending_upgrade=SignalColor.ORANGE,
            consecutive_days=2,
            last_updated=date.today() - timedelta(days=1),
        )
        result = _apply_hysteresis(state, SignalColor.ORANGE, veto=False)
        # Day 3 — upgrade confirmed!
        assert result == SignalColor.ORANGE
        assert state.current_regime == SignalColor.ORANGE
        assert state.pending_upgrade is None
        assert state.consecutive_days == 0


class TestMidUpgradeReset:
    """If signal drops during upgrade window, the counter resets."""

    def test_signal_drops_during_upgrade(self):
        state = RegimeState(
            current_regime=SignalColor.RED,
            pending_upgrade=SignalColor.ORANGE,
            consecutive_days=2,
            last_updated=date.today() - timedelta(days=1),
        )
        # Signal goes back to RED (same as current)
        result = _apply_hysteresis(state, SignalColor.RED, veto=False)
        assert result == SignalColor.RED
        assert state.pending_upgrade is None
        assert state.consecutive_days == 0

    def test_stronger_raw_signal_clamps_to_same_slot(self):
        """Under the clamped upgrade model, a stronger raw signal does NOT reset the counter.

        Pre-clamp behavior (obsolete): raw=YELLOW would be treated as a 'new target'
        that resets the counter away from ORANGE.

        Post-clamp behavior: raw=YELLOW while current=RED clamps to ORANGE (one rank
        above current), which matches pending_upgrade. The counter continues, and
        the ladder step confirms normally. This is consistent — the destination of
        the next 3-day window is deterministic from `current`, not from `raw`.
        """
        state = RegimeState(
            current_regime=SignalColor.RED,
            pending_upgrade=SignalColor.ORANGE,
            consecutive_days=2,
            last_updated=date.today() - timedelta(days=1),
        )
        result = _apply_hysteresis(state, SignalColor.YELLOW, veto=False)
        assert result == SignalColor.ORANGE  # confirmed on day 3
        assert state.current_regime == SignalColor.ORANGE
        assert state.pending_upgrade is None
        assert state.consecutive_days == 0


class TestSameDayNoIncrement:
    """Multiple calls on the same day don't double-count."""

    def test_same_day_no_double_count(self):
        state = RegimeState(
            current_regime=SignalColor.RED,
            pending_upgrade=SignalColor.ORANGE,
            consecutive_days=1,
            last_updated=date.today(),  # Same day!
        )
        result = _apply_hysteresis(state, SignalColor.ORANGE, veto=False)
        # Should NOT increment — same day
        assert result == SignalColor.RED
        assert state.consecutive_days == 1


class TestClampedUpgrade:
    """Upgrades clamp to one rank above current — prevents multi-level jumps."""

    def test_red_to_green_clamps_to_orange_first(self):
        """current=RED, raw=GREEN → pending=ORANGE (not GREEN)."""
        state = RegimeState(
            current_regime=SignalColor.RED,
            last_updated=date.today() - timedelta(days=1),
        )
        result = _apply_hysteresis(state, SignalColor.GREEN, veto=False)
        assert result == SignalColor.RED  # still holding
        assert state.pending_upgrade == SignalColor.ORANGE  # clamped, not GREEN
        assert state.consecutive_days == 1

    def test_red_to_yellow_clamps_to_orange(self):
        """current=RED, raw=YELLOW → pending=ORANGE (clamped one level up)."""
        state = RegimeState(
            current_regime=SignalColor.RED,
            last_updated=date.today() - timedelta(days=1),
        )
        result = _apply_hysteresis(state, SignalColor.YELLOW, veto=False)
        assert result == SignalColor.RED
        assert state.pending_upgrade == SignalColor.ORANGE
        assert state.consecutive_days == 1

    def test_orange_to_green_clamps_to_yellow(self):
        """current=ORANGE, raw=GREEN → pending=YELLOW (clamped one level up)."""
        state = RegimeState(
            current_regime=SignalColor.ORANGE,
            last_updated=date.today() - timedelta(days=1),
        )
        result = _apply_hysteresis(state, SignalColor.GREEN, veto=False)
        assert result == SignalColor.ORANGE
        assert state.pending_upgrade == SignalColor.YELLOW
        assert state.consecutive_days == 1

    def test_red_to_green_confirms_to_orange_only(self):
        """3 days of raw=GREEN while current=RED → regime becomes ORANGE, not GREEN."""
        state = RegimeState(
            current_regime=SignalColor.RED,
            pending_upgrade=SignalColor.ORANGE,
            consecutive_days=2,
            last_updated=date.today() - timedelta(days=1),
        )
        result = _apply_hysteresis(state, SignalColor.GREEN, veto=False)
        assert result == SignalColor.ORANGE
        assert state.current_regime == SignalColor.ORANGE
        assert state.pending_upgrade is None
        assert state.consecutive_days == 0

    def test_full_ladder_red_to_green_takes_nine_days(self):
        """Sustained raw=GREEN from current=RED walks RED→ORANGE→YELLOW→GREEN over 9 days."""
        state = RegimeState(
            current_regime=SignalColor.RED,
            last_updated=date.today() - timedelta(days=1),
        )
        # Day-by-day: regime should ladder up one rank per 3-day window
        expected_sequence = [
            SignalColor.RED,     # Day 1: counting toward ORANGE (1/3)
            SignalColor.RED,     # Day 2: counting (2/3)
            SignalColor.ORANGE,  # Day 3: confirm ORANGE
            SignalColor.ORANGE,  # Day 4: start counting toward YELLOW (1/3)
            SignalColor.ORANGE,  # Day 5: counting (2/3)
            SignalColor.YELLOW,  # Day 6: confirm YELLOW
            SignalColor.YELLOW,  # Day 7: start counting toward GREEN (1/3)
            SignalColor.YELLOW,  # Day 8: counting (2/3)
            SignalColor.GREEN,   # Day 9: confirm GREEN
        ]
        for i, expected in enumerate(expected_sequence):
            if i > 0:
                # Roll last_updated back to simulate a new calendar day
                state.last_updated = date.today() - timedelta(days=1)
            result = _apply_hysteresis(state, SignalColor.GREEN, veto=False)
            assert result == expected, f"Day {i+1}: expected {expected.value}, got {result.value}"


class TestSameColorNoop:
    """Raw signal == current regime → no change, reset pending."""

    def test_same_color_resets_pending(self):
        state = RegimeState(
            current_regime=SignalColor.YELLOW,
            pending_upgrade=SignalColor.GREEN,
            consecutive_days=2,
            last_updated=date.today() - timedelta(days=1),
        )
        result = _apply_hysteresis(state, SignalColor.YELLOW, veto=False)
        assert result == SignalColor.YELLOW
        assert state.pending_upgrade is None
        assert state.consecutive_days == 0
