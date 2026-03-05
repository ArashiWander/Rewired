"""Portfolio models: Position, Transaction, Portfolio."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from rewired.models.signals import SignalColor


class Position(BaseModel):
    """A current holding."""
    ticker: str
    shares: float
    avg_cost_eur: float
    current_price_eur: float = 0.0
    market_value_eur: float = 0.0
    unrealized_pnl_eur: float = 0.0
    weight_pct: float = 0.0
    last_updated: datetime | None = None


class Transaction(BaseModel):
    """A recorded buy/sell."""
    ticker: str
    action: str  # BUY or SELL
    shares: float
    price_eur: float
    date: date
    signal_color_at_time: SignalColor | None = None
    notes: str = ""


class Portfolio(BaseModel):
    """Full portfolio state."""
    total_capital_eur: float = 3100.0
    cash_eur: float = 3100.0
    positions: dict[str, Position] = {}
    transactions: list[Transaction] = []
    last_updated: datetime | None = None

    @property
    def invested_eur(self) -> float:
        return sum(p.market_value_eur for p in self.positions.values())

    @property
    def total_value_eur(self) -> float:
        return self.cash_eur + self.invested_eur
