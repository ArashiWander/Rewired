"""P5.2: Property-based tests for the 2D L×T sizing solver.

Uses Hypothesis to generate random inputs and verify invariants that
must hold regardless of input values.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st

from rewired.models.portfolio import Portfolio, Position
from rewired.models.signals import SignalColor
from rewired.models.universe import Layer, Stock, Tier, Universe
from rewired.portfolio.sizing import _solve_lxt, _hedge_pct, _frozen_tiers, _eligible_tiers

from tests.conftest import make_composite


# ── Strategies ──────────────────────────────────────────────────────────────

regimes = st.sampled_from(list(SignalColor))
positive_floats = st.floats(min_value=100.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False)

VALID_CONFIG = {
    "layer_budgets": {"L1": 0.175, "L2": 0.190, "L3": 0.250, "L5": 0.075},
    "cash_floors": {"green": 0.05, "yellow": 0.07, "orange": 0.10, "red": 0.18},
    "tier_ratios": {"T1": 0.500, "T2": 0.275, "T3": 0.100, "T4": 0.055},
    "constraints": {"max_single_position_pct": 15.0, "min_position_eur": 10.0},
}

SMALL_UNIVERSE = Universe(stocks=[
    Stock(ticker="NVDA", name="NVIDIA", layer=Layer.L1, tier=Tier.T1, max_weight_pct=15.0),
    Stock(ticker="MSFT", name="Microsoft", layer=Layer.L2, tier=Tier.T1, max_weight_pct=12.0),
    Stock(ticker="CRM", name="Salesforce", layer=Layer.L3, tier=Tier.T2, max_weight_pct=5.0),
    Stock(ticker="AAPL", name="Apple", layer=Layer.L4, tier=Tier.T1, max_weight_pct=8.0),
    Stock(ticker="IONQ", name="IonQ", layer=Layer.L5, tier=Tier.T4, max_weight_pct=3.0),
])


# ── Property tests ─────────────────────────────────────────────────────────


class TestSolverInvariants:
    """Properties that must hold for any valid input."""

    @given(total=positive_floats, regime=regimes)
    @settings(max_examples=50)
    def test_all_targets_non_negative(self, total, regime):
        """No target allocation should ever be negative."""
        targets = _solve_lxt(VALID_CONFIG, SMALL_UNIVERSE, regime, total)
        for ticker, value in targets.items():
            assert value >= 0, f"{ticker} has negative target {value}"

    @given(total=positive_floats, regime=regimes)
    @settings(max_examples=50)
    def test_total_targets_do_not_exceed_capital(self, total, regime):
        """Sum of all targets must not exceed total capital (within rounding)."""
        targets = _solve_lxt(VALID_CONFIG, SMALL_UNIVERSE, regime, total)
        target_sum = sum(targets.values())
        assert target_sum <= total * 1.01, (
            f"Target sum {target_sum:.2f} exceeds total {total:.2f}"
        )

    @given(total=positive_floats)
    @settings(max_examples=20)
    def test_monotonic_defense_cash_floors(self, total):
        """RED keeps more cash than ORANGE, which keeps more than YELLOW, etc."""
        results = {}
        for regime in SignalColor:
            targets = _solve_lxt(VALID_CONFIG, SMALL_UNIVERSE, regime, total)
            cash_ticker = "XEON.DE"
            results[regime] = targets.get(cash_ticker, 0.0)

        assert results[SignalColor.RED] >= results[SignalColor.ORANGE]
        assert results[SignalColor.ORANGE] >= results[SignalColor.YELLOW]
        assert results[SignalColor.YELLOW] >= results[SignalColor.GREEN]


class TestHedgeProtocolProperties:
    """Hedge allocation follows monotonic escalation."""

    def test_hedge_pct_green_zero(self):
        assert _hedge_pct(SignalColor.GREEN) == 0.0

    def test_hedge_pct_yellow_zero(self):
        assert _hedge_pct(SignalColor.YELLOW) == 0.0

    def test_hedge_pct_orange_positive(self):
        assert _hedge_pct(SignalColor.ORANGE) > 0.0

    def test_hedge_pct_red_greater_than_orange(self):
        assert _hedge_pct(SignalColor.RED) > _hedge_pct(SignalColor.ORANGE)

    @given(total=positive_floats)
    @settings(max_examples=20)
    def test_hedge_monotonic_in_targets(self, total):
        """Hedge target in solver output is monotonically escalating."""
        hedge_ticker = "DXS3.DE"
        results = {}
        for regime in SignalColor:
            targets = _solve_lxt(VALID_CONFIG, SMALL_UNIVERSE, regime, total)
            results[regime] = targets.get(hedge_ticker, 0.0)

        assert results[SignalColor.RED] >= results[SignalColor.ORANGE]
        assert results[SignalColor.ORANGE] >= results[SignalColor.YELLOW]
        assert results[SignalColor.GREEN] == 0.0


class TestFrozenTierProperties:
    """Tier freezing behavior under different regimes."""

    def test_green_nothing_frozen(self):
        assert _frozen_tiers(SignalColor.GREEN) == set()

    def test_non_green_freezes_t3_t4(self):
        for regime in (SignalColor.YELLOW, SignalColor.ORANGE, SignalColor.RED):
            frozen = _frozen_tiers(regime)
            assert Tier.T3 in frozen
            assert Tier.T4 in frozen

    def test_green_all_eligible(self):
        eligible = _eligible_tiers(SignalColor.GREEN)
        assert eligible == {Tier.T1, Tier.T2, Tier.T3, Tier.T4}

    def test_non_green_only_t1_t2_eligible(self):
        for regime in (SignalColor.YELLOW, SignalColor.ORANGE, SignalColor.RED):
            eligible = _eligible_tiers(regime)
            assert eligible == {Tier.T1, Tier.T2}


class TestEdgeCases:
    """Edge cases that should not crash the solver."""

    def test_zero_total_capital(self):
        targets = _solve_lxt(VALID_CONFIG, SMALL_UNIVERSE, SignalColor.GREEN, 0.0)
        for v in targets.values():
            assert v == 0.0

    def test_very_small_capital(self):
        targets = _solve_lxt(VALID_CONFIG, SMALL_UNIVERSE, SignalColor.GREEN, 1.0)
        for v in targets.values():
            assert v >= 0.0

    def test_empty_universe(self):
        empty = Universe(stocks=[])
        targets = _solve_lxt(VALID_CONFIG, empty, SignalColor.GREEN, 10000.0)
        # Should still have cash and hedge entries
        assert "XEON.DE" in targets

    def test_single_stock_universe(self):
        single = Universe(stocks=[
            Stock(ticker="NVDA", name="NVIDIA", layer=Layer.L1, tier=Tier.T1, max_weight_pct=15.0),
        ])
        targets = _solve_lxt(VALID_CONFIG, single, SignalColor.GREEN, 10000.0)
        assert targets["NVDA"] >= 0.0
        assert targets["XEON.DE"] >= 0.0
