"""Portfolio state management: load, save, record transactions."""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime
from pathlib import Path

from rewired import get_data_dir
from rewired.models.portfolio import Portfolio, Position, Transaction
from rewired.models.signals import SignalColor
from rewired.data.prices import get_current_prices
from rewired.data.fx import usd_to_eur

_log = logging.getLogger("rewired")


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


# ---------------------------------------------------------------------------
# Factory reset
# ---------------------------------------------------------------------------

def factory_reset(new_capital: float) -> None:
    """Purge all state and reinitialise with *new_capital*.

    Resets portfolio, regime state, signal history and deletes caches.
    Shared by both CLI ``rewired reset`` and the GUI Danger Zone.
    """
    from rewired.models.signals import RegimeState, SignalColor as _SC

    data_dir = get_data_dir()

    # 1. Portfolio
    pf = Portfolio(total_capital_eur=new_capital, cash_eur=new_capital)
    with open(data_dir / "portfolio.json", "w", encoding="utf-8") as f:
        f.write(pf.model_dump_json(indent=2))

    # 2. Regime state
    rs = RegimeState(
        current_regime=_SC.YELLOW,
        pending_upgrade=None,
        consecutive_days=0,
        last_updated=date(1970, 1, 1),
    )
    with open(data_dir / "regime_state.json", "w", encoding="utf-8") as f:
        f.write(rs.model_dump_json(indent=2))

    # 3. Signal history
    with open(data_dir / "signal_history.json", "w", encoding="utf-8") as f:
        json.dump([], f)

    # 4. Delete caches
    for name in ("capex_cache.json", "edgar_cache.json",
                 "capex_quarterly_history.json"):
        p = data_dir / name
        if p.exists():
            p.unlink()

    _log.info("FACTORY_RESET: capital=%.2f at %s",
              new_capital, datetime.now().isoformat())


# ---------------------------------------------------------------------------
# Transaction deletion (replay strategy)
# ---------------------------------------------------------------------------

def _replay_transactions(
    total_capital: float,
    transactions: list[Transaction],
) -> tuple[float, dict[str, Position]]:
    """Replay a list of transactions on a fresh ledger.

    Returns ``(cash_eur, positions_dict)`` after applying every tx in order.
    """
    cash = total_capital
    positions: dict[str, Position] = {}

    for tx in transactions:
        if tx.action == "DEPOSIT":
            cash += tx.price_eur
        elif tx.action == "WITHDRAW":
            cash -= tx.price_eur
        elif tx.action == "BUY":
            cost = tx.price_eur * tx.shares
            if tx.ticker in positions:
                pos = positions[tx.ticker]
                total_cost = pos.avg_cost_eur * pos.shares + cost
                pos.shares += tx.shares
                pos.avg_cost_eur = total_cost / pos.shares if pos.shares > 0 else 0
            else:
                positions[tx.ticker] = Position(
                    ticker=tx.ticker,
                    shares=tx.shares,
                    avg_cost_eur=tx.price_eur,
                )
            cash -= cost
        elif tx.action == "SELL":
            if tx.ticker in positions:
                pos = positions[tx.ticker]
                pos.shares -= tx.shares
                if pos.shares <= 0.0001:
                    del positions[tx.ticker]
            cash += tx.price_eur * tx.shares

    return cash, positions


def delete_transaction(portfolio: Portfolio, tx_id: str) -> bool:
    """Remove a transaction by *tx_id* and replay the remaining ledger.

    Returns ``True`` if a transaction was found and deleted.
    """
    original_len = len(portfolio.transactions)
    remaining = [t for t in portfolio.transactions if t.id != tx_id]

    if len(remaining) == original_len:
        return False  # nothing matched

    # Compute base capital (original total_capital plus any deposits minus
    # any withdrawals are handled by replay, so we start from the capital
    # that was set at the FIRST reset before any transactions).
    # We derive it from total_capital_eur which should still reflect the
    # initial seeded capital (adjusted by DEPOSIT/WITHDRAW through replay).
    base_capital = portfolio.total_capital_eur

    # Replay deposits/withdrawals to figure out the true base seed.
    # total_capital_eur already includes past DEPOSIT/WITHDRAW adjustments,
    # so we need to subtract them to get the pre-tx seed, then let replay
    # re-apply them.
    deposit_sum = sum(t.price_eur for t in portfolio.transactions
                      if t.action == "DEPOSIT")
    withdraw_sum = sum(t.price_eur for t in portfolio.transactions
                       if t.action == "WITHDRAW")
    seed_capital = base_capital - deposit_sum + withdraw_sum

    cash, positions = _replay_transactions(seed_capital, remaining)

    portfolio.transactions = remaining
    portfolio.cash_eur = cash
    portfolio.positions = positions
    # Recalculate total_capital for DEPOSIT/WITHDRAW that survived.
    new_deposits = sum(t.price_eur for t in remaining if t.action == "DEPOSIT")
    new_withdrawals = sum(t.price_eur for t in remaining
                         if t.action == "WITHDRAW")
    portfolio.total_capital_eur = seed_capital + new_deposits - new_withdrawals

    return True


# ---------------------------------------------------------------------------
# Capital adjustments (inject / withdraw)
# ---------------------------------------------------------------------------

def adjust_capital(
    portfolio: Portfolio,
    amount: float,
    reason: str = "",
) -> Transaction:
    """Inject (*amount* > 0) or withdraw (*amount* < 0) cash.

    Updates ``cash_eur`` and ``total_capital_eur`` and records a
    DEPOSIT / WITHDRAW transaction in the unified ledger.

    Raises ``ValueError`` if a withdrawal exceeds available cash.
    """
    if amount == 0:
        raise ValueError("Adjustment amount must be non-zero.")

    if amount < 0 and abs(amount) > portfolio.cash_eur:
        raise ValueError(
            f"Cannot withdraw {abs(amount):.2f} EUR — "
            f"only {portfolio.cash_eur:.2f} EUR cash available."
        )

    action = "DEPOSIT" if amount > 0 else "WITHDRAW"
    tx = Transaction(
        ticker="",
        action=action,
        shares=0.0,
        price_eur=abs(amount),
        date=date.today(),
        notes=reason or f"Capital {action.lower()}",
    )
    portfolio.transactions.append(tx)
    portfolio.cash_eur += amount
    portfolio.total_capital_eur += amount

    return tx
