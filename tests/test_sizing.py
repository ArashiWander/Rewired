"""Tests for position sizing: execution matrix actions per signal color."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from rewired.models.signals import SignalColor
from rewired.models.portfolio import Portfolio, Position
from rewired.models.universe import Layer, Stock, Tier, Universe
from rewired.portfolio.sizing import calculate_suggestions, calculate_pies_allocation
from tests.conftest import make_composite


# ── Shared helpers ───────────────────────────────────────────────────────

_SAMPLE_PORTFOLIO_CONFIG = {
    "allocation_by_tier": {"T1": 0.40, "T2": 0.30, "T3": 0.20, "T4": 0.10},
    "signal_multipliers": {"green": 1.0, "yellow": 0.85, "orange": 0.6, "red": 0.3},
    "constraints": {
        "max_single_position_pct": 15,
        "min_position_eur": 10,
        "max_positions": 15,
    },
    "tier_rules_by_signal": {
        "green": {"T1": "hold", "T2": "hold", "T3": "hold", "T4": "hold"},
        "yellow": {"T1": "hold", "T2": "hold", "T3": "hold", "T4": "trim_50"},
        "orange": {"T1": "hold", "T2": "hold", "T3": "trim_50", "T4": "exit"},
        "red": {"T1": "hold", "T2": "trim_50", "T3": "exit", "T4": "exit"},
    },
}


@pytest.fixture()
def mock_portfolio_config():
    with patch("rewired.portfolio.sizing._load_portfolio_config", return_value=_SAMPLE_PORTFOLIO_CONFIG):
        yield


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
                weight_pct=22.6,  # over 15% cap
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
# PHASE 1: TAKE PROFIT
# ═════════════════════════════════════════════════════════════════════════


class TestTakeProfit:
    """Take-profit sells work in ALL signal colors."""

    def test_overweight_triggers_sell(self, mock_portfolio_config, invested_portfolio, small_universe):
        """NVDA at 22.6% > 15% cap → take-profit SELL."""
        sig = make_composite(overall=SignalColor.GREEN)
        suggestions = calculate_suggestions(invested_portfolio, small_universe, sig)

        tp_sells = [s for s in suggestions if s["priority"] == 1]
        assert any(s["ticker"] == "NVDA" for s in tp_sells)
        nvda_sell = next(s for s in tp_sells if s["ticker"] == "NVDA")
        assert nvda_sell["action"] == "SELL"
        assert nvda_sell["amount_eur"] > 0

    def test_take_profit_works_in_red(self, mock_portfolio_config, invested_portfolio, small_universe):
        """Take-profit fires even under RED signal."""
        sig = make_composite(overall=SignalColor.RED)
        suggestions = calculate_suggestions(invested_portfolio, small_universe, sig)

        tp_sells = [s for s in suggestions if s["priority"] == 1]
        nvda_sells = [s for s in tp_sells if s["ticker"] == "NVDA"]
        assert len(nvda_sells) == 1


# ═════════════════════════════════════════════════════════════════════════
# PHASE 2: SIGNAL-DRIVEN EXITS
# ═════════════════════════════════════════════════════════════════════════


class TestSignalExits:
    """Tier rules trigger exits and trims based on signal color."""

    def test_red_exits_t4(self, mock_portfolio_config, invested_portfolio, small_universe):
        """RED signal → T4 exit (IONQ should be sold)."""
        sig = make_composite(overall=SignalColor.RED)
        suggestions = calculate_suggestions(invested_portfolio, small_universe, sig)

        ionq_sells = [s for s in suggestions if s["ticker"] == "IONQ" and s["action"] == "SELL"]
        assert len(ionq_sells) >= 1

    def test_red_exits_t3(self, mock_portfolio_config, invested_portfolio, small_universe):
        """RED signal → T3 exit (PLTR should be sold)."""
        sig = make_composite(overall=SignalColor.RED)
        suggestions = calculate_suggestions(invested_portfolio, small_universe, sig)

        pltr_sells = [s for s in suggestions if s["ticker"] == "PLTR" and s["action"] == "SELL"]
        assert len(pltr_sells) >= 1

    def test_orange_exits_t4(self, mock_portfolio_config, invested_portfolio, small_universe):
        """ORANGE signal → T4 exit."""
        sig = make_composite(overall=SignalColor.ORANGE)
        suggestions = calculate_suggestions(invested_portfolio, small_universe, sig)

        ionq_sells = [s for s in suggestions if s["ticker"] == "IONQ" and s["action"] == "SELL"]
        assert len(ionq_sells) >= 1

    def test_orange_trims_t3(self, mock_portfolio_config, invested_portfolio, small_universe):
        """ORANGE signal → T3 trim 50%."""
        sig = make_composite(overall=SignalColor.ORANGE)
        suggestions = calculate_suggestions(invested_portfolio, small_universe, sig)

        pltr_sells = [s for s in suggestions if s["ticker"] == "PLTR" and s["action"] == "SELL"]
        if pltr_sells:
            # Should be a trim (not full exit), so amount < full position
            assert pltr_sells[0]["amount_eur"] < 300.0

    def test_green_no_signal_exits(self, mock_portfolio_config, invested_portfolio, small_universe):
        """GREEN signal → no signal-driven exits (phase 2 is empty)."""
        sig = make_composite(overall=SignalColor.GREEN)
        suggestions = calculate_suggestions(invested_portfolio, small_universe, sig)

        phase2 = [s for s in suggestions if s["priority"] == 2]
        assert len(phase2) == 0


# ═════════════════════════════════════════════════════════════════════════
# PHASE 3: BUY TARGETS
# ═════════════════════════════════════════════════════════════════════════


class TestBuyTargets:
    """New positions for unheld stocks."""

    def test_green_generates_buys(self, mock_portfolio_config, small_universe):
        """GREEN signal + cash → buy suggestions for unheld stocks."""
        pf = Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)
        sig = make_composite(overall=SignalColor.GREEN)
        suggestions = calculate_suggestions(pf, small_universe, sig)

        buys = [s for s in suggestions if s["action"] == "BUY"]
        assert len(buys) > 0
        tickers = [s["ticker"] for s in buys]
        assert "NVDA" in tickers or "MSFT" in tickers

    def test_red_no_new_t4_buys(self, mock_portfolio_config, small_universe):
        """RED signal → should NOT buy T4 stocks (exit rule)."""
        pf = Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)
        sig = make_composite(overall=SignalColor.RED)
        suggestions = calculate_suggestions(pf, small_universe, sig)

        t4_buys = [s for s in suggestions if s["ticker"] == "IONQ" and s["action"] == "BUY"]
        assert len(t4_buys) == 0

    def test_no_buys_below_minimum(self, mock_portfolio_config, small_universe):
        """Should not generate buy suggestions below min_position_eur (10)."""
        pf = Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)
        sig = make_composite(overall=SignalColor.GREEN)
        suggestions = calculate_suggestions(pf, small_universe, sig)

        for s in suggestions:
            if s["action"] == "BUY":
                assert s["amount_eur"] >= 10


# ═════════════════════════════════════════════════════════════════════════
# PIES ALLOCATION
# ═════════════════════════════════════════════════════════════════════════


class TestPiesAllocation:
    """Trading 212 Pies allocation output."""

    def test_allocations_sum_to_100(self, mock_portfolio_config, small_universe):
        """All target percentages must sum to ~100%."""
        pf = Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)
        sig = make_composite(overall=SignalColor.GREEN)
        allocs = calculate_pies_allocation(pf, small_universe, sig)

        total = sum(a["target_pct"] for a in allocs)
        assert abs(total - 100.0) < 1.0  # within 1% due to rounding

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

    def test_multiplier_reduces_allocation(self, mock_portfolio_config, small_universe):
        """Lower signal → lower multiplier → more cash."""
        pf = Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)

        green_sig = make_composite(overall=SignalColor.GREEN)
        green_allocs = calculate_pies_allocation(pf, small_universe, green_sig)
        green_invested = sum(a["target_pct"] for a in green_allocs if a["ticker"] != "CASH")

        yellow_sig = make_composite(overall=SignalColor.YELLOW)
        yellow_allocs = calculate_pies_allocation(pf, small_universe, yellow_sig)
        yellow_invested = sum(a["target_pct"] for a in yellow_allocs if a["ticker"] != "CASH")

        assert green_invested >= yellow_invested


# ═════════════════════════════════════════════════════════════════════════
# SUGGESTION ORDERING
# ═════════════════════════════════════════════════════════════════════════


class TestSuggestionOrdering:
    """Suggestions should be sorted by priority."""

    def test_priority_ordering(self, mock_portfolio_config, invested_portfolio, small_universe):
        """Lower priority number = first in list."""
        sig = make_composite(overall=SignalColor.RED)
        suggestions = calculate_suggestions(invested_portfolio, small_universe, sig)

        priorities = [s.get("priority", 99) for s in suggestions]
        assert priorities == sorted(priorities)
