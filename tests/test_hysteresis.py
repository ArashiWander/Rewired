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

    def test_different_upgrade_target_resets(self):
        state = RegimeState(
            current_regime=SignalColor.RED,
            pending_upgrade=SignalColor.ORANGE,
            consecutive_days=2,
            last_updated=date.today() - timedelta(days=1),
        )
        # Different upgrade target (YELLOW instead of ORANGE)
        result = _apply_hysteresis(state, SignalColor.YELLOW, veto=False)
        assert result == SignalColor.RED
        # Counter should reset to 1 for the new target
        assert state.pending_upgrade == SignalColor.YELLOW
        assert state.consecutive_days == 1


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
