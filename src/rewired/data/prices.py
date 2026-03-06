"""Stock price data fetching via yfinance."""

from __future__ import annotations

import yfinance as yf
import pandas as pd

from rewired.data.fx import usd_to_eur


def get_current_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current USD prices for a list of tickers.

    Returns dict mapping ticker -> price in USD.
    """
    prices = {}
    data = yf.download(tickers, period="1d", progress=False)
    if data.empty:
        return prices

    close = data["Close"]
    if isinstance(close, pd.Series):
        # Single ticker returns a Series
        if not close.empty:
            prices[tickers[0]] = float(close.iloc[-1])
    else:
        for ticker in tickers:
            if ticker in close.columns and not pd.isna(close[ticker].iloc[-1]):
                prices[ticker] = float(close[ticker].iloc[-1])

    return prices


def get_current_prices_eur(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices converted to EUR."""
    usd_prices = get_current_prices(tickers)
    return {t: usd_to_eur(p) for t, p in usd_prices.items()}


def get_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Fetch historical OHLCV data for a single ticker."""
    t = yf.Ticker(ticker)
    return t.history(period=period)


def get_moving_averages(ticker: str) -> dict[str, float | None]:
    """Calculate 50-day and 200-day moving averages for a ticker.

    Returns dict with keys: price, ma50, ma200, ma50_above_ma200.
    """
    hist = get_history(ticker, period="1y")
    if hist.empty or len(hist) < 50:
        return {"price": None, "ma50": None, "ma200": None, "ma50_above_ma200": None}

    price = float(hist["Close"].iloc[-1])
    ma50 = float(hist["Close"].rolling(50).mean().iloc[-1])
    ma200 = float(hist["Close"].rolling(200).mean().iloc[-1]) if len(hist) >= 200 else None

    return {
        "price": price,
        "ma50": ma50,
        "ma200": ma200,
        "ma50_above_ma200": ma50 > ma200 if ma200 else None,
    }


def get_daily_changes(tickers: list[str]) -> dict[str, float]:
    """Fetch daily percentage change for a list of tickers.

    Returns dict mapping ticker -> daily change % (e.g. 2.5 for +2.5%).
    Uses 5-day history to ensure we get at least two trading days.
    """
    changes: dict[str, float] = {}
    if not tickers:
        return changes
    try:
        data = yf.download(tickers, period="5d", progress=False)
        if data.empty:
            return changes
        close = data["Close"]
        if isinstance(close, pd.Series):
            # Single ticker
            if len(close.dropna()) >= 2:
                prev = float(close.dropna().iloc[-2])
                curr = float(close.dropna().iloc[-1])
                if prev > 0:
                    changes[tickers[0]] = round((curr - prev) / prev * 100, 2)
        else:
            for ticker in tickers:
                if ticker in close.columns:
                    col = close[ticker].dropna()
                    if len(col) >= 2:
                        prev = float(col.iloc[-2])
                        curr = float(col.iloc[-1])
                        if prev > 0:
                            changes[ticker] = round((curr - prev) / prev * 100, 2)
    except Exception:
        pass
    return changes


def get_relative_strength(ticker: str, benchmark: str = "^GSPC", period_days: int = 63) -> float | None:
    """Calculate relative strength of ticker vs benchmark over period.

    Returns the difference in percentage returns (ticker_return - benchmark_return).
    Positive means outperforming.
    """
    t_hist = get_history(ticker, period="6mo")
    b_hist = get_history(benchmark, period="6mo")

    if t_hist.empty or b_hist.empty:
        return None
    if len(t_hist) < period_days or len(b_hist) < period_days:
        return None

    t_return = (float(t_hist["Close"].iloc[-1]) / float(t_hist["Close"].iloc[-period_days]) - 1) * 100
    b_return = (float(b_hist["Close"].iloc[-1]) / float(b_hist["Close"].iloc[-period_days]) - 1) * 100

    return t_return - b_return
