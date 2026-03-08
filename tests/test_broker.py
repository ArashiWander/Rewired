"""Tests for the Trading 212 broker client (data/broker.py)."""

from __future__ import annotations

import base64
import os
from unittest.mock import MagicMock, patch

import pytest

from rewired.data.broker import (
    get_account_summary,
    get_pie_detail,
    get_pies_list,
    get_portfolio,
    get_positions,
    is_configured,
    normalize_t212_ticker,
)
from rewired.models.signals import BrokerUnavailableError


# ── Ticker normalisation ────────────────────────────────────────────────


class TestNormalizeT212Ticker:
    def test_us_equity(self):
        assert normalize_t212_ticker("AAPL_US_EQ") == "AAPL"

    def test_us_equity_nvidia(self):
        assert normalize_t212_ticker("NVDA_US_EQ") == "NVDA"

    def test_lse_equity(self):
        assert normalize_t212_ticker("QQQS_LSE_EQ") == "QQQS.L"

    def test_amsterdam_equity(self):
        assert normalize_t212_ticker("ASML_AMS_EQ") == "ASML.AS"

    def test_unknown_exchange(self):
        assert normalize_t212_ticker("SAP_XYZZ_EQ") == "SAP.XYZZ"

    def test_two_part_ticker(self):
        # Some edge cases may have only symbol_exchange
        result = normalize_t212_ticker("AAPL_US")
        assert result == "AAPL"

    def test_plain_ticker(self):
        # Already-plain ticker returns as-is
        assert normalize_t212_ticker("AAPL") == "AAPL"

    def test_xetra(self):
        assert normalize_t212_ticker("SAP_XETRA_EQ") == "SAP.DE"


# ── Configuration check ─────────────────────────────────────────────────


class TestIsConfigured:
    def test_not_configured_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert is_configured() is False

    def test_not_configured_placeholder(self):
        with patch.dict(
            os.environ,
            {
                "TRADING212_API_KEY_ID": "your_key_here",
                "TRADING212_SECRET_KEY": "your_secret_here",
            },
        ):
            assert is_configured() is False

    def test_configured(self):
        with patch.dict(
            os.environ,
            {
                "TRADING212_API_KEY_ID": "real_key_123",
                "TRADING212_SECRET_KEY": "real_secret_456",
            },
        ):
            assert is_configured() is True


# ── API call mocking ────────────────────────────────────────────────────


_MOCK_CASH_RESPONSE = {
    "cash": {
        "availableToTrade": 1500.50,
    },
    "investments": {
        "currentValue": 1600.00,
    },
    "totalValue": 3100.50,
}

_MOCK_POSITIONS_RESPONSE = [
    {
        "averagePricePaid": 120.5,
        "currentPrice": 135.0,
        "instrument": {"ticker": "NVDA_US_EQ", "currencyCode": "USD"},
        "quantity": 5.0,
        "walletImpact": 72.5,
        "quantityInPies": 3.0,
        "quantityAvailableForTrading": 2.0,
    },
    {
        "averagePricePaid": 3.80,
        "currentPrice": 3.50,
        "instrument": {"ticker": "QQQS_LSE_EQ", "currencyCode": "GBP"},
        "quantity": 100.0,
        "walletImpact": -30.0,
        "quantityInPies": 0.0,
        "quantityAvailableForTrading": 100.0,
    },
]


@pytest.fixture()
def _mock_t212_env():
    """Set T212 API key pair env vars for tests."""
    with patch.dict(
        os.environ,
        {
            "TRADING212_API_KEY_ID": "test_key_abc",
            "TRADING212_SECRET_KEY": "test_secret_xyz",
        },
    ):
        yield


class TestGetAccountSummary:
    @pytest.mark.usefixtures("_mock_t212_env")
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_CASH_RESPONSE

        with patch("rewired.data.broker.requests.get", return_value=mock_resp):
            result = get_account_summary()

        assert result["total_value_eur"] == 3100.50
        assert result["cash_eur"] == 1500.50
        assert result["invested_eur"] == 1600.00

    @pytest.mark.usefixtures("_mock_t212_env")
    def test_uses_basic_auth_header(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_CASH_RESPONSE

        with patch("rewired.data.broker.requests.get", return_value=mock_resp) as mock_get:
            get_account_summary()

        auth_header = mock_get.call_args.kwargs["headers"]["Authorization"]
        expected = base64.b64encode(b"test_key_abc:test_secret_xyz").decode("ascii")

        assert auth_header == f"Basic {expected}"
        assert mock_get.call_args.args[0].endswith("/equity/account/cash")

    @pytest.mark.usefixtures("_mock_t212_env")
    def test_auth_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"

        with patch("rewired.data.broker.requests.get", return_value=mock_resp):
            with pytest.raises(BrokerUnavailableError, match="auth rejected"):
                get_account_summary()

    @pytest.mark.usefixtures("_mock_t212_env")
    def test_timeout(self):
        import requests as req

        with patch("rewired.data.broker.requests.get", side_effect=req.Timeout("timed out")):
            with pytest.raises(BrokerUnavailableError, match="timed out"):
                get_account_summary()

    @pytest.mark.usefixtures("_mock_t212_env")
    def test_connection_error(self):
        import requests as req

        with patch("rewired.data.broker.requests.get", side_effect=req.ConnectionError("refused")):
            with pytest.raises(BrokerUnavailableError, match="connection failed"):
                get_account_summary()

    def test_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(BrokerUnavailableError, match="not set"):
                get_account_summary()

    @pytest.mark.usefixtures("_mock_t212_env")
    def test_rate_limit(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Rate limit"

        with patch("rewired.data.broker.requests.get", return_value=mock_resp):
            with pytest.raises(BrokerUnavailableError, match="rate limit"):
                get_account_summary()


class TestGetPositions:
    @pytest.mark.usefixtures("_mock_t212_env")
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_POSITIONS_RESPONSE

        with patch("rewired.data.broker.requests.get", return_value=mock_resp):
            positions = get_positions()

        assert len(positions) == 2
        assert positions[0]["ticker"] == "NVDA"
        assert positions[0]["t212_ticker"] == "NVDA_US_EQ"
        assert positions[0]["shares"] == 5.0
        assert positions[0]["current_price_instrument"] == 135.0
        assert positions[0]["avg_cost_instrument"] == 120.5
        assert positions[0]["currency"] == "USD"
        assert positions[0]["pnl_eur"] == 72.5
        assert positions[0]["quantity_in_pies"] == 3.0
        assert positions[0]["quantity_free"] == 2.0
        assert positions[1]["ticker"] == "QQQS.L"
        assert positions[1]["t212_ticker"] == "QQQS_LSE_EQ"
        assert positions[1]["currency"] == "GBP"

    @pytest.mark.usefixtures("_mock_t212_env")
    def test_uses_positions_endpoint(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = _MOCK_POSITIONS_RESPONSE

        with patch("rewired.data.broker.requests.get", return_value=mock_resp) as mock_get:
            get_positions()

        assert mock_get.call_args.args[0].endswith("/equity/positions")


class TestGetPortfolio:
    @pytest.mark.usefixtures("_mock_t212_env")
    def test_success(self):
        mock_cash = MagicMock()
        mock_cash.status_code = 200
        mock_cash.json.return_value = _MOCK_CASH_RESPONSE

        mock_pos = MagicMock()
        mock_pos.status_code = 200
        mock_pos.json.return_value = _MOCK_POSITIONS_RESPONSE

        with patch("rewired.data.broker.requests.get", side_effect=[mock_cash, mock_pos]), \
             patch("rewired.data.broker._instrument_to_eur", side_effect=lambda amt, cur: amt):
            pf = get_portfolio()

        assert pf.cash_eur == 1500.50
        assert "NVDA" in pf.positions
        assert "QQQS.L" in pf.positions
        assert pf.positions["NVDA"].shares == 5.0
        # With _instrument_to_eur mocked as identity, EUR prices equal instrument prices
        assert pf.positions["NVDA"].current_price_eur == 135.0
        assert pf.positions["NVDA"].current_price_usd == 135.0
        assert pf.positions["NVDA"].quantity_in_pies == 3.0
        assert pf.positions["NVDA"].quantity_free == 2.0
        # Weights should be computed
        assert pf.positions["NVDA"].weight_pct > 0
        assert pf.total_value_eur > 0

    @pytest.mark.usefixtures("_mock_t212_env")
    def test_empty_positions(self):
        mock_cash = MagicMock()
        mock_cash.status_code = 200
        mock_cash.json.return_value = {
            "cash": {"availableToTrade": 3100.0},
            "investments": {"currentValue": 0},
            "totalValue": 3100.0,
        }

        mock_pos = MagicMock()
        mock_pos.status_code = 200
        mock_pos.json.return_value = []

        with patch("rewired.data.broker.requests.get", side_effect=[mock_cash, mock_pos]):
            pf = get_portfolio()

        assert pf.cash_eur == 3100.0
        assert len(pf.positions) == 0
        assert pf.total_value_eur == 3100.0

    @pytest.mark.usefixtures("_mock_t212_env")
    def test_broker_down_propagates(self):
        """If T212 is down during get_portfolio(), BrokerUnavailableError MUST propagate."""
        import requests as req

        with patch("rewired.data.broker.requests.get", side_effect=req.ConnectionError("down")):
            with pytest.raises(BrokerUnavailableError):
                get_portfolio()


# ── Pies API ────────────────────────────────────────────────────────────


class TestGetPiesList:
    @pytest.mark.usefixtures("_mock_t212_env")
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"id": 42, "cash": 10.5, "progress": 0.95, "status": "active"},
        ]

        with patch("rewired.data.broker.requests.get", return_value=mock_resp):
            pies = get_pies_list()

        assert len(pies) == 1
        assert pies[0]["id"] == 42
        assert pies[0]["cash"] == 10.5


class TestGetPieDetail:
    @pytest.mark.usefixtures("_mock_t212_env")
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "instruments": [
                {
                    "ticker": "NVDA_US_EQ",
                    "currentShare": 0.40,
                    "expectedShare": 0.45,
                    "ownedQuantity": 3.0,
                    "result": 55.0,
                    "issues": [],
                },
            ],
            "settings": {"name": "AI Core", "id": 42, "goal": 5000.0, "instrumentShares": {}},
        }

        with patch("rewired.data.broker.requests.get", return_value=mock_resp):
            detail = get_pie_detail(42)

        assert detail["settings"]["name"] == "AI Core"
        assert len(detail["instruments"]) == 1
        assert detail["instruments"][0]["ticker"] == "NVDA"
        assert detail["instruments"][0]["current_share"] == 0.40
