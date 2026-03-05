"""Shared test fixtures for Rewired Index test suite."""

from __future__ import annotations

from datetime import datetime

import pytest

from rewired.models.signals import (
    CategorySignal,
    CompositeSignal,
    SignalCategory,
    SignalColor,
    SignalReading,
)
from rewired.models.portfolio import Portfolio, Position
from rewired.models.universe import Layer, Stock, Tier, Universe


# ── Signal Reading factories ─────────────────────────────────────────────

_NOW = datetime(2026, 3, 5, 12, 0, 0)


def make_reading(
    name: str,
    value: float,
    color: SignalColor = SignalColor.GREEN,
    source: str = "test",
    metadata: dict | None = None,
) -> SignalReading:
    return SignalReading(
        name=name,
        value=value,
        color=color,
        timestamp=_NOW,
        source=source,
        metadata=metadata or {},
    )


def make_category_signal(
    category: SignalCategory,
    color: SignalColor,
    readings: list[SignalReading] | None = None,
    explanation: str = "test",
    rule_triggered: str = "",
) -> CategorySignal:
    return CategorySignal(
        category=category,
        readings=readings or [],
        composite_color=color,
        timestamp=_NOW,
        explanation=explanation,
        rule_triggered=rule_triggered,
    )


def make_composite(
    overall: SignalColor = SignalColor.GREEN,
    macro: SignalColor = SignalColor.GREEN,
    sentiment: SignalColor = SignalColor.GREEN,
    ai_health: SignalColor = SignalColor.GREEN,
    veto: bool = False,
) -> CompositeSignal:
    categories = {
        SignalCategory.MACRO: make_category_signal(SignalCategory.MACRO, macro),
        SignalCategory.SENTIMENT: make_category_signal(SignalCategory.SENTIMENT, sentiment),
        SignalCategory.AI_HEALTH: make_category_signal(SignalCategory.AI_HEALTH, ai_health),
    }
    return CompositeSignal(
        categories=categories,
        overall_color=overall,
        timestamp=_NOW,
        summary="test composite",
        veto_active=veto,
    )


# ── Macro readings ──────────────────────────────────────────────────────


@pytest.fixture()
def macro_green_readings() -> list[SignalReading]:
    """PMI > 50 AND Core PCE <= 0.2% → GREEN."""
    return [
        make_reading("ISM PMI", 52.3, metadata={"consecutive_below_threshold": 0}),
        make_reading("Core PCE MoM", 0.18),
        make_reading("Yield Curve (10Y-2Y)", 0.45),
        make_reading("Retail Sales MoM", 0.3),
        make_reading("Unemployment MoM Change", 0.0, metadata={"mom_change": 0.0}),
    ]


@pytest.fixture()
def macro_red_readings() -> list[SignalReading]:
    """PMI < 48 for 2 months AND Retail Sales negative → RED."""
    return [
        make_reading("ISM PMI", 46.5, metadata={"consecutive_below_threshold": 3}),
        make_reading("Core PCE MoM", 0.35),
        make_reading("Yield Curve (10Y-2Y)", -0.15),
        make_reading("Retail Sales MoM", -0.4),
        make_reading("Unemployment MoM Change", 0.3, metadata={"mom_change": 0.3}),
    ]


@pytest.fixture()
def macro_orange_readings() -> list[SignalReading]:
    """Core PCE > 0.2% AND Yield Curve inverted → ORANGE."""
    return [
        make_reading("ISM PMI", 51.0, metadata={"consecutive_below_threshold": 0}),
        make_reading("Core PCE MoM", 0.35),
        make_reading("Yield Curve (10Y-2Y)", -0.10),
        make_reading("Retail Sales MoM", 0.2),
        make_reading("Unemployment MoM Change", 0.1, metadata={"mom_change": 0.1}),
    ]


@pytest.fixture()
def macro_yellow_readings() -> list[SignalReading]:
    """Unemployment +0.2% BUT PMI > 50 → YELLOW."""
    return [
        make_reading("ISM PMI", 51.5, metadata={"consecutive_below_threshold": 0}),
        make_reading("Core PCE MoM", 0.15),
        make_reading("Yield Curve (10Y-2Y)", 0.30),
        make_reading("Retail Sales MoM", 0.1),
        make_reading("Unemployment MoM Change", 0.25, metadata={"mom_change": 0.25}),
    ]


# ── Sentiment readings ──────────────────────────────────────────────────


@pytest.fixture()
def sentiment_green_readings() -> list[SignalReading]:
    """VIX < 18 AND contango → GREEN."""
    return [
        make_reading("VIX", 14.5, metadata={"ma5_above_ma20": False}),
        make_reading("VIX Term Structure", 2.1),  # VIX3M - VIX = positive = contango
    ]


@pytest.fixture()
def sentiment_red_readings() -> list[SignalReading]:
    """VIX > 35 AND backwardation → RED."""
    return [
        make_reading("VIX", 42.0, metadata={"ma5_above_ma20": True}),
        make_reading("VIX Term Structure", -3.5),  # negative = backwardation
    ]


@pytest.fixture()
def sentiment_orange_readings() -> list[SignalReading]:
    """VIX > 25 AND 5MA > 20MA → ORANGE."""
    return [
        make_reading("VIX", 28.0, metadata={"ma5_above_ma20": True}),
        make_reading("VIX Term Structure", 0.5),
    ]


@pytest.fixture()
def sentiment_yellow_readings() -> list[SignalReading]:
    """VIX 18-25 → YELLOW."""
    return [
        make_reading("VIX", 21.0, metadata={"ma5_above_ma20": False}),
        make_reading("VIX Term Structure", 1.0),
    ]


# ── AI Health readings ──────────────────────────────────────────────────


@pytest.fixture()
def ai_health_green_readings() -> list[SignalReading]:
    """CAPEX accelerating → GREEN."""
    return [
        make_reading("AI CAPEX Health (Agent)", 4.0, metadata={
            "capex_trend": "accelerating",
            "veto_triggered": False,
            "key_management_quote": "unprecedented demand for AI infrastructure",
        }),
    ]


@pytest.fixture()
def ai_health_red_readings() -> list[SignalReading]:
    """CAPEX cut/veto → RED."""
    return [
        make_reading("AI CAPEX Health (Agent)", 1.0, metadata={
            "capex_trend": "contracting",
            "veto_triggered": True,
            "key_management_quote": "We are prudently reducing capital expenditure",
        }),
    ]


# ── Universe fixtures ────────────────────────────────────────────────────


@pytest.fixture()
def sample_universe() -> Universe:
    """A small test universe with 4 stocks across layers/tiers."""
    return Universe(stocks=[
        Stock(ticker="NVDA", name="NVIDIA", layer=Layer.L1, tier=Tier.T1, max_weight_pct=15),
        Stock(ticker="MSFT", name="Microsoft", layer=Layer.L3, tier=Tier.T1, max_weight_pct=12),
        Stock(ticker="PLTR", name="Palantir", layer=Layer.L4, tier=Tier.T3, max_weight_pct=5),
        Stock(ticker="IONQ", name="IonQ", layer=Layer.L5, tier=Tier.T4, max_weight_pct=3),
    ])


# ── Portfolio fixtures ───────────────────────────────────────────────────


@pytest.fixture()
def empty_portfolio() -> Portfolio:
    return Portfolio(total_capital_eur=3100.0, cash_eur=3100.0)


@pytest.fixture()
def sample_portfolio() -> Portfolio:
    return Portfolio(
        total_capital_eur=3100.0,
        cash_eur=1500.0,
        positions={
            "NVDA": Position(
                ticker="NVDA",
                shares=5.0,
                avg_cost_eur=120.0,
                current_price_eur=130.0,
                market_value_eur=650.0,
                unrealized_pnl_eur=50.0,
                weight_pct=20.9,
            ),
            "MSFT": Position(
                ticker="MSFT",
                shares=3.0,
                avg_cost_eur=300.0,
                current_price_eur=316.67,
                market_value_eur=950.0,
                unrealized_pnl_eur=50.0,
                weight_pct=30.6,
            ),
        },
    )


# ── Composite fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def green_composite() -> CompositeSignal:
    return make_composite(
        overall=SignalColor.GREEN,
        macro=SignalColor.GREEN,
        sentiment=SignalColor.GREEN,
        ai_health=SignalColor.GREEN,
    )


@pytest.fixture()
def red_composite() -> CompositeSignal:
    return make_composite(
        overall=SignalColor.RED,
        macro=SignalColor.RED,
        sentiment=SignalColor.RED,
        ai_health=SignalColor.RED,
        veto=True,
    )


@pytest.fixture()
def orange_composite() -> CompositeSignal:
    return make_composite(
        overall=SignalColor.ORANGE,
        macro=SignalColor.ORANGE,
        sentiment=SignalColor.YELLOW,
        ai_health=SignalColor.ORANGE,
    )
