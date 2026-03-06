"""Tests for defensive price-fetch error handling."""

from __future__ import annotations

from unittest.mock import patch

from rewired.data import prices


@patch("rewired.data.prices.yf.download", side_effect=ConnectionResetError("forcibly closed"))
def test_get_current_prices_returns_empty_on_fetch_error(_):
    assert prices.get_current_prices(["NVDA"]) == {}


@patch("rewired.data.prices.yf.Ticker")
def test_get_history_returns_empty_dataframe_on_fetch_error(mock_ticker):
    mock_ticker.return_value.history.side_effect = ConnectionResetError("forcibly closed")

    result = prices.get_history("NVDA")

    assert result.empty
