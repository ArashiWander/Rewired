"""Portfolio models: Position, Portfolio.

Portfolio data comes exclusively from the Trading 212 broker API
(``data/broker.py``).  There is no local JSON persistence.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Position(BaseModel):
    """A current holding sourced from the T212 broker API."""
    ticker: str
    shares: float
    avg_cost_eur: float
    current_price_eur: float = 0.0
    market_value_eur: float = 0.0
    unrealized_pnl_eur: float = 0.0
    weight_pct: float = 0.0
    last_updated: datetime | None = None

    # Raw instrument-currency prices from T212 (USD for US stocks, GBP for LSE, etc.)
    current_price_usd: float = 0.0
    avg_cost_usd: float = 0.0

    # Pie constituent data from T212 positions endpoint
    quantity_in_pies: float = 0.0
    quantity_free: float = 0.0


class Portfolio(BaseModel):
    """Live portfolio state from T212.

    ``total_value_eur`` is a stored field (from T212 account summary)
    rather than computed, because T212 is the authoritative source.
    """
    cash_eur: float = 0.0
    positions: dict[str, Position] = {}
    last_updated: datetime | None = None

    @property
    def invested_eur(self) -> float:
        return sum(p.market_value_eur for p in self.positions.values())

    @property
    def total_value_eur(self) -> float:
        return self.cash_eur + self.invested_eur
