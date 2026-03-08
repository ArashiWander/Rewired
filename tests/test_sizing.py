"""Tests for 2D L×T constraint solver and position sizing.

Tests cover the 5-phase allocation engine: cash floor, layer budgets,
L4 dynamic residual, intra-layer tier distribution, and tolerance band.
Also tests hedge protocols and suggestion generation.
"""

from __future__ import annotations

import pytest
from unittest.mock import patch

from rewired.models.signals import SignalColor
from rewired.models.portfolio import Portfolio, Position
from rewired.models.universe import Layer, Stock, Tier, Universe
from rewired.portfolio.sizing import (
    _solve_lxt,
    _eligible_tiers,
    calculate_suggestions,
    calculate_pies_allocation,
    _HEDGE_TICKER,
)
from tests.conftest import make_composite


# ── Shared config & fixtures ─────────────────────────────────────────────

_LXT_CONFIG = {
    "layer_budgets": {"L1": 0.175, "L2": 0.190, "L3": 0.250, "L5": 0.075},
    "cash_floors": {"green": 0.05, "yellow": 0.15, "orange": 0.30, "red": 0.70},
    "tier_ratios": {"T1": 0.500, "T2": 0.275, "T3": 0.100, "T4": 0.055},
    "constraints": {
        "max_single_position_pct": 15.0,
        "min_position_eur": 10.0,
        "max_positions": 15,
    },
}


@pytest.fixture()
def mock_portfolio_config():
    with patch("rewired.portfolio.sizing._load_portfolio_config", return_value=_LXT_CONFIG):
        yield


@pytest.fixture()
def lxt_universe() -> Universe:
    """Universe covering all 5 layers and multiple tiers."""
    return Universe(stocks=[
        Stock(ticker="NVDA", name="NVIDIA", layer=Layer.L1, tier=Tier.T1, max_weight_pct=15),
        Stock(ticker="AVGO", name="Broadcom", layer=Layer.L1, tier=Tier.T2, max_weight_pct=10),
        Stock(ticker="MSFT", name="Microsoft", layer=Layer.L2, tier=Tier.T1, max_weight_pct=12),
        Stock(ticker="AMZN", name="Amazon", layer=Layer.L2, tier=Tier.T2, max_weight_pct=10),
        Stock(ticker="GOOGL", name="Alphabet", layer=Layer.L3, tier=Tier.T1, max_weight_pct=12),
        Stock(ticker="META", name="Meta", layer=Layer.L3, tier=Tier.T2, max_weight_pct=10),
        Stock(ticker="PLTR", name="Palantir", layer=Layer.L4, tier=Tier.T3, max_weight_pct=5),
        Stock(ticker="SNOW", name="Snowflake", layer=Layer.L4, tier=Tier.T2, max_weight_pct=6),
        Stock(ticker="IONQ", name="IonQ", layer=Layer.L5, tier=Tier.T4, max_weight_pct=3),
    ])


@pytest.fixture()
def small_universe() -> Universe:
    return Universe(stocks=[
        Stock(ticker="NVDA", name="NVIDIA", layer=Layer.L1, tier=Tier.T1, max_weight_pct=15),
        Stock(ticker="MSFT", name="Microsoft", layer=Layer.L3, tier=Tier.T1, max_weight_pct=12),
        Stock(ticker="PLTR", name="Palantir", layer=Layer.L4, tier=Tier.T3, max_weight_pct=5),
        Stock(ticker="IONQ", name="IonQ", layer=Layer.L5, tier=Tier.T4, max_weight_pct=3),
    ])


@pytest.fixture()
def invested_portfolio() -> Portfolio:
    """Portfolio with positions in NVDA (overweight) and PLTR at 3100 total."""
    return Portfolio(
        total_capital_eur=3100.0,
        cash_eur=1500.0,
        positions={
            "NVDA": Position(
                ticker="NVDA",
                shares=5.0,
                avg_cost_eur=120.0,
                current_price_eur=140.0,
                market_value_eur=700.0,
                weight_pct=22.6,
            ),
            "PLTR": Position(
                ticker="PLTR",
                shares=10.0,
                avg_cost_eur=25.0,
                current_price_eur=30.0,
                market_value_eur=300.0,
                weight_pct=9.7,
            ),
            "IONQ": Position(
                ticker="IONQ",
                shares=20.0,
                avg_cost_eur=15.0,
                current_price_eur=15.0,
                market_value_eur=300.0,
                weight_pct=9.7,
            ),
        },
    )


# ═════════════════════════════════════════════════════════════════════════
# PHASE 1: CASH FLOOR
# ═════════════════════════════════════════════════════════════════════════


class TestCashFloor:
    """Cash floor varies by regime color."""

    def test_green_5pct_cash_floor(self, lxt_universe):
        """GREEN cash floor is 5% — 95% of capital is investable."""
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.GREEN, 10000.0)
        stock_total = sum(v for k, v in targets.items() if k != _HEDGE_TICKER)
        # 5% cash floor → max investable = 9500; tier ratios + caps reduce further
        assert stock_total > 5000.0
        assert stock_total <= 9500.0 + 10

    def test_yellow_15pct_cash(self, lxt_universe):
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.YELLOW, 10000.0)
        stock_total = sum(v for k, v in targets.items() if k != _HEDGE_TICKER)
        assert stock_total <= 8500.0 + 10  # 85% invested

    def test_orange_30pct_cash(self, lxt_universe):
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.ORANGE, 10000.0)
        stock_total = sum(v for k, v in targets.items() if k != _HEDGE_TICKER)
        # 30% cash floor + 6% hedge → stock total should be ≤ 64%
        assert stock_total <= 7000.0 + 10

    def test_red_70pct_cash(self, lxt_universe):
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.RED, 10000.0)
        stock_total = sum(v for k, v in targets.items() if k != _HEDGE_TICKER)
        # 70% cash floor (bunker) → stock total should be ≤ 30%
        assert stock_total <= 3000.0 + 10


# ═════════════════════════════════════════════════════════════════════════
# PHASE 2+3: LAYER BUDGETS AND L4 RESIDUAL
# ═════════════════════════════════════════════════════════════════════════


class TestLayerBudgets:
    """Static layer budget allocation and L4 dynamic residual."""

    def test_l5_zero_under_red(self, lxt_universe):
        """RED regime → L5 budget is zeroed out (crisis liquidation)."""
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.RED, 10000.0)
        ionq_target = targets.get("IONQ", 0.0)
        assert ionq_target == 0.0

    def test_l4_residual_positive_green(self, lxt_universe):
        """GREEN: L4 = investable - (L1+L2+L3+L5) should be positive."""
        total = 10000.0
        # L1=17.5%, L2=19%, L3=25%, L5=7.5% = 69% → L4 = 31%
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.GREEN, total)
        l4_stocks = [s for s in lxt_universe.stocks if s.layer == Layer.L4]
        l4_total = sum(targets.get(s.ticker, 0.0) for s in l4_stocks)
        assert l4_total > 0


class TestDeficitSafeguard:
    """When L4 would go negative, proportional reduction kicks in."""

    def test_deficit_clamps_l4_to_zero(self):
        """If layer budgets exceed investable, L4 = 0 (not negative)."""
        extreme_config = {
            "layer_budgets": {"L1": 0.40, "L2": 0.40, "L3": 0.20, "L5": 0.10},
            "cash_floors": {"red": 0.20},
            "tier_ratios": {"T1": 1.0},
            "constraints": {"max_single_position_pct": 100.0},
        }
        universe = Universe(stocks=[
            Stock(ticker="A", name="A", layer=Layer.L1, tier=Tier.T1, max_weight_pct=100),
            Stock(ticker="B", name="B", layer=Layer.L2, tier=Tier.T1, max_weight_pct=100),
            Stock(ticker="C", name="C", layer=Layer.L3, tier=Tier.T1, max_weight_pct=100),
            Stock(ticker="D", name="D", layer=Layer.L4, tier=Tier.T1, max_weight_pct=100),
            Stock(ticker="E", name="E", layer=Layer.L5, tier=Tier.T1, max_weight_pct=100),
        ])
        # RED: cash=20%, static layers = 110% > 80% investable → deficit
        targets = _solve_lxt(extreme_config, universe, SignalColor.RED, 10000.0)
        d_target = targets.get("D", 0.0)
        assert d_target == 0.0
        # All targets should be >= 0
        for v in targets.values():
            assert v >= 0.0


# ═════════════════════════════════════════════════════════════════════════
# PHASE 4: ELIGIBILITY FILTER
# ═════════════════════════════════════════════════════════════════════════


class TestEligibilityFilter:
    """Tier eligibility varies by regime."""

    def test_green_all_tiers(self):
        assert _eligible_tiers(SignalColor.GREEN) == {Tier.T1, Tier.T2, Tier.T3, Tier.T4}

    def test_yellow_all_tiers(self):
        assert _eligible_tiers(SignalColor.YELLOW) == {Tier.T1, Tier.T2, Tier.T3, Tier.T4}

    def test_orange_t1_t2_only(self):
        assert _eligible_tiers(SignalColor.ORANGE) == {Tier.T1, Tier.T2}

    def test_red_t1_t2_only(self):
        assert _eligible_tiers(SignalColor.RED) == {Tier.T1, Tier.T2}

    def test_orange_zeros_t3_t4(self, lxt_universe):
        """Under ORANGE, T3/T4 stocks should get 0 target."""
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.ORANGE, 10000.0)
        pltr_target = targets.get("PLTR", 0.0)  # L4/T3
        ionq_target = targets.get("IONQ", 0.0)  # L5/T4
        assert pltr_target == 0.0
        assert ionq_target == 0.0

    def test_red_zeros_t3_t4(self, lxt_universe):
        """Under RED, T3/T4 stocks should get 0 target."""
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.RED, 10000.0)
        pltr_target = targets.get("PLTR", 0.0)
        ionq_target = targets.get("IONQ", 0.0)
        assert pltr_target == 0.0
        assert ionq_target == 0.0


# ═════════════════════════════════════════════════════════════════════════
# HEDGE PROTOCOLS
# ═════════════════════════════════════════════════════════════════════════


class TestHedgeProtocol:
    """QQQS.L hedge deployment and unwind."""

    def test_orange_deploys_hedge(self, lxt_universe):
        """ORANGE → 6% into QQQS.L."""
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.ORANGE, 10000.0)
        assert targets[_HEDGE_TICKER] == pytest.approx(600.0, abs=1)

    def test_red_no_hedge(self, lxt_universe):
        """RED = full liquidation mode → 0% hedge."""
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.RED, 10000.0)
        assert targets[_HEDGE_TICKER] == 0.0

    def test_green_no_hedge(self, lxt_universe):
        """GREEN → hedge unwound / not deployed."""
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.GREEN, 10000.0)
        assert targets[_HEDGE_TICKER] == 0.0

    def test_yellow_no_hedge(self, lxt_universe):
        """YELLOW → hedge unwound / not deployed."""
        targets = _solve_lxt(_LXT_CONFIG, lxt_universe, SignalColor.YELLOW, 10000.0)
        assert targets[_HEDGE_TICKER] == 0.0

    def test_hedge_unwind_sells(self, mock_portfolio_config, small_universe):
        """When regime upgrades to GREEN with an existing hedge, generate sell for QQQS.L."""
        pf = Portfolio(
            total_capital_eur=3100.0,
            cash_eur=1000.0,
            positions={
                _HEDGE_TICKER: Position(
                    ticker=_HEDGE_TICKER,
                    shares=10.0,
                    avg_cost_eur=20.0,
                    current_price_eur=20.0,
                    market_value_eur=200.0,
                    weight_pct=6.5,
                ),
            },
        )
        sig = make_composite(overall=SignalColor.GREEN)
        suggestions = calculate_suggestions(pf, small_universe, sig)

        hedge_sells = [s for s in suggestions if s["ticker"] == _HEDGE_TICKER and s["action"] == "SELL"]
        assert len(hedge_sells) == 1
        assert hedge_sells[0]["amount_eur"] > 0


# ═════════════════════════════════════════════════════════════════════════
# SUGGESTIONS AND PIES
# ═════════════════════════════════════════════════════════════════════════


class TestSuggestions:
    """Suggestion generation from solver targets."""

    def test_green_generates_buys(self, mock_portfolio_config, small_universe):
        """GREEN + cash → buy suggestions."""
        pf = Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)
        sig = make_composite(overall=SignalColor.GREEN)
        suggestions = calculate_suggestions(pf, small_universe, sig)

        buys = [s for s in suggestions if s["action"] == "BUY"]
        assert len(buys) > 0

    def test_red_no_new_t4_buys(self, mock_portfolio_config, small_universe):
        """RED signal → should NOT buy T4 stocks."""
        pf = Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)
        sig = make_composite(overall=SignalColor.RED)
        suggestions = calculate_suggestions(pf, small_universe, sig)

        t4_buys = [s for s in suggestions if s["ticker"] == "IONQ" and s["action"] == "BUY"]
        assert len(t4_buys) == 0

    def test_red_exits_t3_t4(self, mock_portfolio_config, invested_portfolio, small_universe):
        """RED → T3/T4 positions should be sold."""
        sig = make_composite(overall=SignalColor.RED)
        suggestions = calculate_suggestions(invested_portfolio, small_universe, sig)

        ionq_sells = [s for s in suggestions if s["ticker"] == "IONQ" and s["action"] == "SELL"]
        pltr_sells = [s for s in suggestions if s["ticker"] == "PLTR" and s["action"] == "SELL"]
        assert len(ionq_sells) >= 1
        assert len(pltr_sells) >= 1

    def test_priority_ordering(self, mock_portfolio_config, invested_portfolio, small_universe):
        """Lower priority number = first in list."""
        sig = make_composite(overall=SignalColor.RED)
        suggestions = calculate_suggestions(invested_portfolio, small_universe, sig)

        priorities = [s.get("priority", 99) for s in suggestions]
        assert priorities == sorted(priorities)


class TestPiesAllocation:
    """Trading 212 Pies allocation output."""

    def test_cash_slice_exists(self, mock_portfolio_config, small_universe):
        """Allocation always includes a CASH entry."""
        pf = Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)
        sig = make_composite(overall=SignalColor.GREEN)
        allocs = calculate_pies_allocation(pf, small_universe, sig)

        cash = [a for a in allocs if a["ticker"] == "CASH"]
        assert len(cash) == 1

    def test_red_exits_have_zero_pct(self, mock_portfolio_config, small_universe):
        """RED signal → T4 stocks get 0% target."""
        pf = Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)
        sig = make_composite(overall=SignalColor.RED)
        allocs = calculate_pies_allocation(pf, small_universe, sig)

        ionq_alloc = [a for a in allocs if a["ticker"] == "IONQ"]
        assert ionq_alloc[0]["target_pct"] == 0.0

    def test_green_invests_more_than_red(self, mock_portfolio_config, small_universe):
        """GREEN → more equity allocation than RED."""
        pf = Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)

        green_sig = make_composite(overall=SignalColor.GREEN)
        green_allocs = calculate_pies_allocation(pf, small_universe, green_sig)
        green_invested = sum(a["target_pct"] for a in green_allocs if a["ticker"] != "CASH")

        red_sig = make_composite(overall=SignalColor.RED)
        red_allocs = calculate_pies_allocation(pf, small_universe, red_sig)
        red_invested = sum(a["target_pct"] for a in red_allocs if a["ticker"] != "CASH")

        assert green_invested > red_invested
