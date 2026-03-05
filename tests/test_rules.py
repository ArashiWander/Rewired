"""Unit tests for every boolean rule in signals/rules.py.

Tests cover the four signal colors for each category (macro, sentiment,
AI health) plus edge cases at exact threshold values and missing data.
"""

from __future__ import annotations

import pytest

from rewired.signals.rules import (
    evaluate_ai_health_rules,
    evaluate_macro_rules,
    evaluate_sentiment_rules,
)
from rewired.models.signals import SignalColor
from tests.conftest import make_reading


# ═════════════════════════════════════════════════════════════════════════
# MACRO RULES
# ═════════════════════════════════════════════════════════════════════════


class TestMacroRules:
    """Tests for evaluate_macro_rules()."""

    # ── GREEN ────────────────────────────────────────────────────────

    def test_green_goldilocks(self, macro_green_readings):
        color, explanation = evaluate_macro_rules(macro_green_readings)
        assert color == SignalColor.GREEN
        assert "Goldilocks" in explanation or "PMI" in explanation

    def test_green_pmi_above_50_pce_missing(self):
        """GREEN when PMI > 50 and PCE data is absent."""
        readings = [
            make_reading("ISM PMI", 53.0, metadata={"consecutive_below_threshold": 0}),
            make_reading("Retail Sales MoM", 0.5),
        ]
        color, _ = evaluate_macro_rules(readings)
        assert color == SignalColor.GREEN

    # ── RED ──────────────────────────────────────────────────────────

    def test_red_confirmed_recession(self, macro_red_readings):
        color, explanation = evaluate_macro_rules(macro_red_readings)
        assert color == SignalColor.RED
        assert "recession" in explanation.lower() or "PMI" in explanation

    def test_red_pmi_exactly_at_threshold(self):
        """PMI exactly at 48 (below threshold) with negative retail sales → RED."""
        readings = [
            make_reading("ISM PMI", 47.9, metadata={"consecutive_below_threshold": 2}),
            make_reading("Core PCE MoM", 0.1),
            make_reading("Yield Curve (10Y-2Y)", 0.2),
            make_reading("Retail Sales MoM", -0.01),
        ]
        color, _ = evaluate_macro_rules(readings)
        assert color == SignalColor.RED

    def test_red_requires_both_conditions(self):
        """PMI < 48 but retail sales positive → should NOT be RED."""
        readings = [
            make_reading("ISM PMI", 46.0, metadata={"consecutive_below_threshold": 3}),
            make_reading("Core PCE MoM", 0.1),
            make_reading("Yield Curve (10Y-2Y)", 0.2),
            make_reading("Retail Sales MoM", 0.5),  # positive
        ]
        color, _ = evaluate_macro_rules(readings)
        assert color != SignalColor.RED

    def test_red_needs_consecutive_months(self):
        """PMI < 48 but only 1 consecutive month → not RED."""
        readings = [
            make_reading("ISM PMI", 47.0, metadata={"consecutive_below_threshold": 1}),
            make_reading("Core PCE MoM", 0.1),
            make_reading("Retail Sales MoM", -0.2),
        ]
        color, _ = evaluate_macro_rules(readings)
        assert color != SignalColor.RED

    # ── ORANGE ───────────────────────────────────────────────────────

    def test_orange_stagflation(self, macro_orange_readings):
        color, explanation = evaluate_macro_rules(macro_orange_readings)
        assert color == SignalColor.ORANGE
        assert "Stagflation" in explanation or "PCE" in explanation

    def test_orange_pce_exactly_at_threshold(self):
        """PCE exactly at 0.2% (not >) should NOT trigger ORANGE by itself."""
        readings = [
            make_reading("ISM PMI", 51.0, metadata={"consecutive_below_threshold": 0}),
            make_reading("Core PCE MoM", 0.2),  # exactly at threshold, not above
            make_reading("Yield Curve (10Y-2Y)", -0.05),
            make_reading("Retail Sales MoM", 0.1),
        ]
        color, _ = evaluate_macro_rules(readings)
        assert color != SignalColor.ORANGE  # 0.2 is NOT > 0.2

    def test_orange_pce_above_inverted_curve(self):
        """PCE 0.21% AND inverted curve → ORANGE."""
        readings = [
            make_reading("ISM PMI", 51.0, metadata={"consecutive_below_threshold": 0}),
            make_reading("Core PCE MoM", 0.21),
            make_reading("Yield Curve (10Y-2Y)", -0.01),
            make_reading("Retail Sales MoM", 0.1),
        ]
        color, _ = evaluate_macro_rules(readings)
        assert color == SignalColor.ORANGE

    # ── YELLOW ───────────────────────────────────────────────────────

    def test_yellow_unemployment_rising_pmi_ok(self, macro_yellow_readings):
        color, explanation = evaluate_macro_rules(macro_yellow_readings)
        assert color == SignalColor.YELLOW
        assert "Slowdown" in explanation or "Unemployment" in explanation

    def test_yellow_unemployment_exactly_at_threshold(self):
        """Unemployment change exactly 0.2% (not >) → should NOT trigger YELLOW."""
        readings = [
            make_reading("ISM PMI", 52.0, metadata={"consecutive_below_threshold": 0}),
            make_reading("Core PCE MoM", 0.15),
            make_reading("Yield Curve (10Y-2Y)", 0.3),
            make_reading("Retail Sales MoM", 0.2),
            make_reading("Unemployment MoM Change", 0.2, metadata={"mom_change": 0.2}),
        ]
        color, _ = evaluate_macro_rules(readings)
        # 0.2 is NOT > 0.2 so YELLOW rule should NOT fire → should be GREEN
        assert color == SignalColor.GREEN

    # ── Missing data ─────────────────────────────────────────────────

    def test_missing_all_critical_data(self):
        """No PMI, PCE, or retail → defaults to ORANGE."""
        readings = [
            make_reading("Yield Curve (10Y-2Y)", 0.5),
        ]
        color, explanation = evaluate_macro_rules(readings)
        assert color == SignalColor.ORANGE
        assert "DATA_MISSING" in explanation

    def test_completely_empty_readings(self):
        color, explanation = evaluate_macro_rules([])
        assert color == SignalColor.ORANGE
        assert "DATA_MISSING" in explanation


# ═════════════════════════════════════════════════════════════════════════
# SENTIMENT RULES
# ═════════════════════════════════════════════════════════════════════════


class TestSentimentRules:
    """Tests for evaluate_sentiment_rules()."""

    # ── GREEN ────────────────────────────────────────────────────────

    def test_green_low_vix_contango(self, sentiment_green_readings):
        color, explanation = evaluate_sentiment_rules(sentiment_green_readings)
        assert color == SignalColor.GREEN
        assert "contango" in explanation.lower() or "Stable" in explanation

    def test_green_vix_just_below_18(self):
        """VIX = 17.9 with contango → GREEN."""
        readings = [
            make_reading("VIX", 17.9, metadata={"ma5_above_ma20": False}),
            make_reading("VIX Term Structure", 1.5),
        ]
        color, _ = evaluate_sentiment_rules(readings)
        assert color == SignalColor.GREEN

    # ── RED ──────────────────────────────────────────────────────────

    def test_red_liquidity_crisis(self, sentiment_red_readings):
        color, explanation = evaluate_sentiment_rules(sentiment_red_readings)
        assert color == SignalColor.RED
        assert "crisis" in explanation.lower() or "backwardation" in explanation.lower()

    def test_red_vix_at_35_backwardation(self):
        """VIX exactly at 35 (not >) → should NOT be RED."""
        readings = [
            make_reading("VIX", 35.0, metadata={"ma5_above_ma20": True}),
            make_reading("VIX Term Structure", -2.0),
        ]
        color, _ = evaluate_sentiment_rules(readings)
        assert color != SignalColor.RED  # > 35 not >= 35

    def test_red_vix_35_1_backwardation(self):
        """VIX = 35.1 with backwardation → RED."""
        readings = [
            make_reading("VIX", 35.1, metadata={"ma5_above_ma20": True}),
            make_reading("VIX Term Structure", -1.0),
        ]
        color, _ = evaluate_sentiment_rules(readings)
        assert color == SignalColor.RED

    def test_red_requires_backwardation(self):
        """VIX > 35 but contango → should be ORANGE not RED."""
        readings = [
            make_reading("VIX", 38.0, metadata={"ma5_above_ma20": True}),
            make_reading("VIX Term Structure", 1.0),  # contango
        ]
        color, _ = evaluate_sentiment_rules(readings)
        assert color != SignalColor.RED
        assert color == SignalColor.ORANGE  # VIX > 25 + ma5 > ma20

    # ── ORANGE ───────────────────────────────────────────────────────

    def test_orange_deteriorating(self, sentiment_orange_readings):
        color, explanation = evaluate_sentiment_rules(sentiment_orange_readings)
        assert color == SignalColor.ORANGE
        assert "Deteriorating" in explanation or "VIX" in explanation

    def test_orange_vix_exactly_25(self):
        """VIX exactly at 25 → NOT ORANGE (> 25 required)."""
        readings = [
            make_reading("VIX", 25.0, metadata={"ma5_above_ma20": True}),
            make_reading("VIX Term Structure", 0.5),
        ]
        color, _ = evaluate_sentiment_rules(readings)
        assert color != SignalColor.ORANGE  # 25 is not > 25

    # ── YELLOW ───────────────────────────────────────────────────────

    def test_yellow_mid_range(self, sentiment_yellow_readings):
        color, explanation = evaluate_sentiment_rules(sentiment_yellow_readings)
        assert color == SignalColor.YELLOW
        assert "Divergence" in explanation or "range" in explanation

    def test_yellow_vix_exactly_18(self):
        """VIX exactly at 18 → YELLOW (18-25 range includes 18)."""
        readings = [
            make_reading("VIX", 18.0, metadata={"ma5_above_ma20": False}),
            make_reading("VIX Term Structure", 1.0),
        ]
        color, _ = evaluate_sentiment_rules(readings)
        assert color == SignalColor.YELLOW

    def test_yellow_vix_exactly_25_no_ma_crossover(self):
        """VIX = 25 without MA crossover → YELLOW (in 18-25 range)."""
        readings = [
            make_reading("VIX", 25.0, metadata={"ma5_above_ma20": False}),
            make_reading("VIX Term Structure", 0.5),
        ]
        color, _ = evaluate_sentiment_rules(readings)
        assert color == SignalColor.YELLOW

    # ── Missing data ─────────────────────────────────────────────────

    def test_missing_vix(self):
        """No VIX data → defaults to ORANGE."""
        readings = [
            make_reading("VIX Term Structure", 1.0),
        ]
        color, explanation = evaluate_sentiment_rules(readings)
        assert color == SignalColor.ORANGE
        assert "DATA_MISSING" in explanation


# ═════════════════════════════════════════════════════════════════════════
# AI HEALTH RULES
# ═════════════════════════════════════════════════════════════════════════


class TestAIHealthRules:
    """Tests for evaluate_ai_health_rules()."""

    def test_green_accelerating(self, ai_health_green_readings):
        color, explanation = evaluate_ai_health_rules(ai_health_green_readings)
        assert color == SignalColor.GREEN
        assert "Arms race" in explanation or "accelerating" in explanation

    def test_red_veto_contracting(self, ai_health_red_readings):
        color, explanation = evaluate_ai_health_rules(ai_health_red_readings)
        assert color == SignalColor.RED
        assert "VETO" in explanation

    def test_red_veto_flag_only(self):
        """Veto flag alone triggers RED even if trend is not 'contracting'."""
        readings = [
            make_reading("AI CAPEX Health (Agent)", 2.0, metadata={
                "capex_trend": "stable",
                "veto_triggered": True,
            }),
        ]
        color, _ = evaluate_ai_health_rules(readings)
        assert color == SignalColor.RED

    def test_orange_decelerating(self):
        readings = [
            make_reading("AI CAPEX Health (Agent)", 2.0, metadata={
                "capex_trend": "decelerating",
                "veto_triggered": False,
            }),
        ]
        color, explanation = evaluate_ai_health_rules(readings)
        assert color == SignalColor.ORANGE
        assert "decelerat" in explanation.lower()

    def test_yellow_stable(self):
        readings = [
            make_reading("AI CAPEX Health (Agent)", 3.0, metadata={
                "capex_trend": "stable",
                "veto_triggered": False,
            }),
        ]
        color, explanation = evaluate_ai_health_rules(readings)
        assert color == SignalColor.YELLOW
        assert "plateau" in explanation.lower() or "Digestion" in explanation

    def test_missing_capex_data(self):
        """No CAPEX reading → defaults to ORANGE."""
        color, explanation = evaluate_ai_health_rules([])
        assert color == SignalColor.ORANGE
        assert "DATA_MISSING" in explanation

    def test_unknown_trend(self):
        """Unknown trend string → defaults to YELLOW."""
        readings = [
            make_reading("AI CAPEX Health (Agent)", 2.5, metadata={
                "capex_trend": "some_new_value",
                "veto_triggered": False,
            }),
        ]
        color, _ = evaluate_ai_health_rules(readings)
        assert color == SignalColor.YELLOW
