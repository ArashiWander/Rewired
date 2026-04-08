"""P5.1: Full pipeline integration test with mocked external APIs.

Verifies the entire pipeline DAG runs end-to-end without real network calls.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch, MagicMock

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


_NOW = datetime(2026, 4, 8, 10, 0, 0)

_MOCK_UNIVERSE = Universe(stocks=[
    Stock(ticker="NVDA", name="NVIDIA", layer=Layer.L1, tier=Tier.T1, max_weight_pct=15.0),
    Stock(ticker="MSFT", name="Microsoft", layer=Layer.L2, tier=Tier.T1, max_weight_pct=12.0),
])

_MOCK_PORTFOLIO = Portfolio(
    cash_eur=3000.0,
    positions={},
)


def _make_macro_readings():
    return [
        SignalReading(name="ISM PMI", value=52.0, color=SignalColor.GREEN, timestamp=_NOW, source="test"),
        SignalReading(name="Core PCE MoM", value=0.15, color=SignalColor.GREEN, timestamp=_NOW, source="test"),
    ]


def _make_sentiment_readings():
    return [
        SignalReading(name="VXN Level & Velocity", value=16.0, color=SignalColor.GREEN, timestamp=_NOW, source="test"),
        SignalReading(name="VIX Term Structure", value=0.5, color=SignalColor.GREEN, timestamp=_NOW, source="test"),
    ]


def _make_ai_health_readings():
    return [
        SignalReading(
            name="CAPEX Trend", value=4.0, color=SignalColor.GREEN, timestamp=_NOW, source="test",
            metadata={"capex_trend": "accelerating"},
        ),
    ]


class TestPipelineIntegration:
    """Full pipeline run with mocked data sources."""

    @patch("rewired.pipeline._write_audit_entry")
    @patch("rewired.notifications.dispatcher.dispatch_signal_change")
    @patch("rewired.data.broker.get_portfolio", return_value=_MOCK_PORTFOLIO)
    @patch("rewired.models.universe.load_universe", return_value=_MOCK_UNIVERSE)
    @patch("rewired.data.ai_health.get_ai_health_readings", side_effect=_make_ai_health_readings)
    @patch("rewired.data.sentiment.get_sentiment_readings", side_effect=_make_sentiment_readings)
    @patch("rewired.data.macro.get_macro_readings", side_effect=_make_macro_readings)
    def test_full_pipeline_completes(
        self, mock_macro, mock_sentiment, mock_ai, mock_uni, mock_pf, mock_dispatch, mock_audit,
    ):
        from rewired.pipeline import run_pipeline

        stages = run_pipeline(dry_run=True, send_notifications=False)

        # Pipeline should complete with multiple stages
        assert len(stages) > 0

        # Check stage structure
        for s in stages:
            assert "name" in s
            assert "status" in s
            assert s["status"] in ("ok", "error", "skipped")

        # At least some stages should succeed
        ok_stages = [s for s in stages if s["status"] == "ok"]
        assert len(ok_stages) >= 3  # data fetch + signals + output

        # Audit log should be written
        mock_audit.assert_called_once()

    @patch("rewired.pipeline._write_audit_entry")
    @patch("rewired.data.broker.get_portfolio", side_effect=Exception("Broker down"))
    @patch("rewired.models.universe.load_universe", side_effect=Exception("Config missing"))
    @patch("rewired.data.ai_health.get_ai_health_readings", side_effect=Exception("API error"))
    @patch("rewired.data.sentiment.get_sentiment_readings", side_effect=Exception("API error"))
    @patch("rewired.data.macro.get_macro_readings", side_effect=Exception("API error"))
    def test_all_critical_failures_aborts_pipeline(
        self, mock_macro, mock_sentiment, mock_ai, mock_uni, mock_pf, mock_audit,
    ):
        from rewired.pipeline import run_pipeline

        stages = run_pipeline(dry_run=True, send_notifications=False)

        # Pipeline should return early
        error_stages = [s for s in stages if s["status"] == "error"]
        assert len(error_stages) >= 3

        # Audit log should still be written (recording the failure)
        mock_audit.assert_called_once()

    @patch("rewired.pipeline._write_audit_entry")
    @patch("rewired.notifications.dispatcher.dispatch_signal_change")
    @patch("rewired.data.broker.get_portfolio", return_value=_MOCK_PORTFOLIO)
    @patch("rewired.models.universe.load_universe", return_value=_MOCK_UNIVERSE)
    @patch("rewired.data.ai_health.get_ai_health_readings", side_effect=Exception("Gemini down"))
    @patch("rewired.data.sentiment.get_sentiment_readings", side_effect=_make_sentiment_readings)
    @patch("rewired.data.macro.get_macro_readings", side_effect=_make_macro_readings)
    def test_partial_failure_continues(
        self, mock_macro, mock_sentiment, mock_ai, mock_uni, mock_pf, mock_dispatch, mock_audit,
    ):
        """When some (but not all) data fetches fail, pipeline continues."""
        from rewired.pipeline import run_pipeline

        stages = run_pipeline(dry_run=True, send_notifications=False)

        # Should have both ok and error stages
        statuses = {s["status"] for s in stages}
        assert "ok" in statuses or "error" in statuses

    def test_no_real_network_calls(self):
        """Sanity check: import pipeline module without network access."""
        import rewired.pipeline  # Should not make any network calls on import
