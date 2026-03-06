"""Regression tests for the AI health CAPEX analysis pipeline."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import patch

from rewired.data import ai_health


class TestCapexFinancialFetch:
    """Test CAPEX financial extraction and formatting."""

    @patch("rewired.data.ai_health._fetch_capex_financials_from_yfinance", return_value=[])
    @patch("rewired.data.ai_health._fetch_capex_financials_from_fmp")
    def test_fetch_capex_financials_prefers_fmp(self, mock_fmp, _):
        mock_fmp.return_value = [
            "MSFT CAPEX (quarterly): 2025-Q4: $15.0B (10.1% rev), 2025-Q3: $14.0B (9.6% rev)",
            "GOOGL CAPEX (quarterly): 2025-Q4: $13.0B (12.3% rev)",
        ]

        result = ai_health._fetch_capex_financials()

        assert "MSFT CAPEX (quarterly): 2025-Q4: $15.0B" in result
        assert "GOOGL CAPEX (quarterly): 2025-Q4: $13.0B" in result

    def test_format_quarter_label(self):
        assert ai_health._format_quarter_label("2025-09-30") == "2025-Q3"
        assert ai_health._format_quarter_label("2025-12-31", "Q4") == "2025-Q4"


class TestGeminiCapexAnalysis:
    """Test Gemini CAPEX parsing contract (AIHealthExtraction schema)."""

    @patch("rewired.data.edgar.fetch_earnings_filings")
    @patch("rewired.agent.gemini.generate")
    @patch("rewired.agent.gemini.is_configured")
    def test_run_gemini_capex_analysis_validates_big4(
        self,
        mock_configured,
        mock_generate,
        mock_filings,
    ):
        mock_configured.return_value = True
        mock_filings.return_value = "sample filing"

        # Mock response matching AIHealthExtraction schema
        company = {
            "capex_absolute_bn": 15.0,
            "qoq_growth_pct": 5.4,
            "yoy_growth_pct": 22.1,
            "explicit_guidance_cut_mentioned": False,
            "exact_capex_quote": "We continue to invest aggressively.",
        }
        mock_generate.return_value = json.dumps({
            "MSFT": company,
            "GOOGL": {**company, "capex_absolute_bn": 13.0},
            "AMZN": {**company, "capex_absolute_bn": 12.0},
            "META": {**company, "capex_absolute_bn": 11.0},
        })

        result = ai_health._run_gemini_capex_analysis("MSFT CAPEX (quarterly): 2025-Q4: $15.0B")

        assert result["validated"] is True
        assert result["veto_triggered"] is False
        assert "companies" in result
        assert result["companies"]["MSFT"]["capex_absolute_bn"] == 15.0
        _, kwargs = mock_generate.call_args
        assert kwargs["search_grounding"] is False
        assert kwargs["json_output"] is True

    @patch("rewired.data.edgar.fetch_earnings_filings")
    @patch("rewired.agent.gemini.generate")
    @patch("rewired.agent.gemini.is_configured")
    def test_veto_triggered_when_cut_mentioned(
        self,
        mock_configured,
        mock_generate,
        mock_filings,
    ):
        mock_configured.return_value = True
        mock_filings.return_value = "sample filing"

        company = {
            "capex_absolute_bn": 15.0,
            "qoq_growth_pct": -5.0,
            "yoy_growth_pct": -10.0,
            "explicit_guidance_cut_mentioned": False,
            "exact_capex_quote": "Normal operations.",
        }
        cut_company = {**company, "explicit_guidance_cut_mentioned": True,
                       "exact_capex_quote": "We are reducing capital expenditure."}
        mock_generate.return_value = json.dumps({
            "MSFT": company,
            "GOOGL": cut_company,  # One cut = veto
            "AMZN": company,
            "META": company,
        })

        result = ai_health._run_gemini_capex_analysis("MSFT CAPEX")
        assert result["veto_triggered"] is True


class TestCapexCache:
    """Test CAPEX cache invalidation on schema changes."""

    def test_load_capex_cache_invalidates_old_schema(self, tmp_path):
        cache_path = tmp_path / "capex_cache.json"
        cache_path.write_text(json.dumps({
            "schema_version": ai_health._CAPEX_CACHE_VERSION - 1,
            "timestamp": datetime.now().isoformat(),
            "score": 3,
        }), encoding="utf-8")

        with patch("rewired.data.ai_health.get_data_dir", return_value=tmp_path):
            assert ai_health._load_capex_cache() is None

    def test_load_capex_cache_accepts_fresh_current_schema(self, tmp_path):
        cache_path = tmp_path / "capex_cache.json"
        cache_path.write_text(json.dumps({
            "schema_version": ai_health._CAPEX_CACHE_VERSION,
            "timestamp": (datetime.now() - timedelta(minutes=5)).isoformat(),
            "score": 4,
            "capex_trend": "accelerating",
        }), encoding="utf-8")

        with patch("rewired.data.ai_health.get_data_dir", return_value=tmp_path):
            result = ai_health._load_capex_cache()

        assert result is not None
        assert result["capex_trend"] == "accelerating"