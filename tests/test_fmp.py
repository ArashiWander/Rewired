"""Tests for FMP API client with mocked HTTP responses."""

from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

import pytest

from rewired.data import fmp


# ── Helpers ──────────────────────────────────────────────────────────────

def _mock_response(data, status=200):
    """Create a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data
    if status >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status}")
    else:
        resp.raise_for_status.return_value = None
    return resp


# ── Tests ────────────────────────────────────────────────────────────────


class TestFMPConfiguration:
    """Test API key detection."""

    @patch.dict("os.environ", {"FMP_API_KEY": ""})
    def test_not_configured_empty(self):
        assert fmp.is_configured() is False

    @patch.dict("os.environ", {"FMP_API_KEY": "your_fmp_api_key_here"})
    def test_not_configured_placeholder(self):
        assert fmp.is_configured() is False

    @patch.dict("os.environ", {"FMP_API_KEY": "abc123"})
    def test_configured(self):
        assert fmp.is_configured() is True


class TestGetProfile:
    """Test company profile parsing."""

    @patch("rewired.data.fmp.is_configured", return_value=True)
    @patch("rewired.data.fmp.requests.get")
    def test_normal_profile(self, mock_get, _):
        mock_get.return_value = _mock_response([{
            "symbol": "NVDA",
            "companyName": "NVIDIA Corporation",
            "mktCap": 3000000000000,
            "sector": "Technology",
            "industry": "Semiconductors",
        }])
        result = fmp.get_profile("NVDA")
        assert result["symbol"] == "NVDA"
        assert result["mktCap"] == 3000000000000

    @patch("rewired.data.fmp.is_configured", return_value=False)
    def test_not_configured_returns_empty(self, _):
        result = fmp.get_profile("NVDA")
        assert result == {}

    @patch("rewired.data.fmp.is_configured", return_value=True)
    @patch("rewired.data.fmp.requests.get")
    def test_empty_response(self, mock_get, _):
        mock_get.return_value = _mock_response([])
        result = fmp.get_profile("FAKE")
        assert result == {}

    @patch("rewired.data.fmp.is_configured", return_value=True)
    @patch("rewired.data.fmp.requests.get")
    def test_http_error_returns_empty(self, mock_get, _):
        mock_get.return_value = _mock_response({}, status=500)
        result = fmp.get_profile("NVDA")
        assert result == {}


class TestGetIncomeStatement:
    """Test income statement parsing."""

    @patch("rewired.data.fmp.is_configured", return_value=True)
    @patch("rewired.data.fmp.requests.get")
    def test_quarterly_statements(self, mock_get, _):
        mock_get.return_value = _mock_response([
            {"date": "2025-12-31", "revenue": 50000000000, "netIncome": 10000000000},
            {"date": "2025-09-30", "revenue": 45000000000, "netIncome": 9000000000},
        ])
        result = fmp.get_income_statement("NVDA", period="quarter", limit=2)
        assert len(result) == 2
        assert result[0]["revenue"] == 50000000000


class TestGetQuote:
    """Test real-time quote parsing."""

    @patch("rewired.data.fmp.is_configured", return_value=True)
    @patch("rewired.data.fmp.requests.get")
    def test_single_quote(self, mock_get, _):
        mock_get.return_value = _mock_response([{
            "symbol": "NVDA",
            "price": 950.0,
            "change": 15.5,
            "changesPercentage": 1.66,
            "volume": 42000000,
        }])
        result = fmp.get_quote("NVDA")
        assert result["price"] == 950.0

    @patch("rewired.data.fmp.is_configured", return_value=True)
    @patch("rewired.data.fmp.requests.get")
    def test_batch_quotes(self, mock_get, _):
        mock_get.return_value = _mock_response([
            {"symbol": "NVDA", "price": 950.0},
            {"symbol": "MSFT", "price": 420.0},
        ])
        result = fmp.get_quote("NVDA,MSFT")
        assert len(result) == 2


class TestCapexHelpers:
    """Test CAPEX history helpers."""

    @patch("rewired.data.fmp.is_configured", return_value=True)
    @patch("rewired.data.fmp.requests.get")
    def test_get_capex_history(self, mock_get, _):
        mock_get.return_value = _mock_response([
            {"date": "2025-12-31", "capitalExpenditure": -15000000000},
            {"date": "2024-12-31", "capitalExpenditure": -12000000000},
        ])
        result = fmp.get_capex_history("MSFT", limit=2)
        assert len(result) == 2
        assert result[0]["capex"] == 15000000000
