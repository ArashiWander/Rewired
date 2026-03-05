"""Portfolio state management: load, save, record transactions."""

from __future__ import annotations

import json
import os
from datetime import date, datetime
from pathlib import Path

from rewired import get_data_dir
from rewired.models.portfolio import Portfolio, Position, Transaction
from rewired.models.signals import SignalColor
from rewired.data.prices import get_current_prices
from rewired.data.fx import usd_to_eur


def _portfolio_path() -> Path:
    return get_data_dir() / "portfolio.json"


def load_portfolio() -> Portfolio:
    """Load portfolio from JSON file, or return empty portfolio."""
    path = _portfolio_path()
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return Portfolio.model_validate(data)
        except (json.JSONDecodeError, Exception):
            pass
    return Portfolio()


def save_portfolio(portfolio: Portfolio) -> None:
    """Save portfolio to JSON file."""
    portfolio.last_updated = datetime.now()
    path = _portfolio_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write(portfolio.model_dump_json(indent=2))


def record_transaction(
    portfolio: Portfolio,
    ticker: str,
    action: str,
    shares: float,
    price_eur: float,
    notes: str = "",
    signal_color: SignalColor | None = None,
) -> None:
    """Record a buy/sell transaction and update positions."""
    tx = Transaction(
        ticker=ticker,
        action=action,
        shares=shares,
        price_eur=price_eur,
        date=date.today(),
        signal_color_at_time=signal_color,
        notes=notes,
    )
    portfolio.transactions.append(tx)

    if action == "BUY":
        if ticker in portfolio.positions:
            pos = portfolio.positions[ticker]
            total_cost = pos.avg_cost_eur * pos.shares + price_eur * shares
            pos.shares += shares
            pos.avg_cost_eur = total_cost / pos.shares if pos.shares > 0 else 0
        else:
            portfolio.positions[ticker] = Position(
                ticker=ticker,
                shares=shares,
                avg_cost_eur=price_eur,
            )
        portfolio.cash_eur -= price_eur * shares

    elif action == "SELL":
        if ticker in portfolio.positions:
            pos = portfolio.positions[ticker]
            pos.shares -= shares
            if pos.shares <= 0.0001:
                del portfolio.positions[ticker]
            portfolio.cash_eur += price_eur * shares


def refresh_prices(portfolio: Portfolio) -> None:
    """Update current prices and calculate P&L for all positions."""
    if not portfolio.positions:
        return

    tickers = list(portfolio.positions.keys())
    usd_prices = get_current_prices(tickers)

    total_invested = 0.0
    for ticker, pos in portfolio.positions.items():
        if ticker in usd_prices:
            pos.current_price_eur = usd_to_eur(usd_prices[ticker])
            pos.market_value_eur = pos.shares * pos.current_price_eur
            pos.unrealized_pnl_eur = pos.market_value_eur - (pos.shares * pos.avg_cost_eur)
            pos.last_updated = datetime.now()
            total_invested += pos.market_value_eur

    # Calculate weights
    total_value = portfolio.cash_eur + total_invested
    if total_value > 0:
        for pos in portfolio.positions.values():
            pos.weight_pct = (pos.market_value_eur / total_value) * 100
