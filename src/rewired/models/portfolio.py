"""Portfolio models: Position, Transaction, Portfolio."""

from __future__ import annotations

import uuid
from datetime import date as _date, datetime
from typing import Literal

from pydantic import BaseModel, Field

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
    """A recorded buy/sell/deposit/withdrawal."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    ticker: str = ""
    action: Literal["BUY", "SELL", "DEPOSIT", "WITHDRAW"] = "BUY"
    shares: float = 0.0
    price_eur: float = 0.0
    date: _date = Field(default_factory=_date.today)
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
