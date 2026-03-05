"""Abstract broker protocol shared by IBKR automated and T212 manual modes.

Every concrete broker adapter must implement the :class:`Broker` protocol so
that the execution pipeline is broker-agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol, runtime_checkable


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    ERROR = "error"


@dataclass
class OrderRequest:
    """A trade the execution engine wants to place."""

    ticker: str
    side: OrderSide
    amount_eur: float
    reason: str = ""
    priority: int = 0
    shares: float | None = None  # pre-computed; broker may recalculate


@dataclass
class OrderResult:
    """Broker response after submitting an order."""

    ticker: str
    side: OrderSide
    requested_eur: float
    filled_eur: float = 0.0
    filled_shares: float = 0.0
    avg_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    broker_order_id: str = ""
    error: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class AccountSummary:
    """Snapshot of the brokerage account."""

    total_value_eur: float = 0.0
    cash_eur: float = 0.0
    buying_power_eur: float = 0.0
    unrealized_pnl_eur: float = 0.0
    currency: str = "EUR"


@dataclass
class BrokerPosition:
    """A single position as reported by the broker."""

    ticker: str
    shares: float
    avg_cost: float
    market_price: float = 0.0
    market_value_eur: float = 0.0
    unrealized_pnl_eur: float = 0.0


@runtime_checkable
class Broker(Protocol):
    """Protocol every broker adapter must satisfy.

    The execution pipeline only interacts through this interface, ensuring
    the same code works with IBKR automated, T212 manual, or any future
    broker.
    """

    @property
    def name(self) -> str:
        """Human-readable broker name (e.g. 'Interactive Brokers')."""
        ...

    @property
    def is_connected(self) -> bool:
        """True when the broker connection is live and ready for orders."""
        ...

    def connect(self) -> None:
        """Establish connection (e.g. IB Gateway/TWS)."""
        ...

    def disconnect(self) -> None:
        """Cleanly close the connection."""
        ...

    def get_account(self) -> AccountSummary:
        """Fetch account balances."""
        ...

    def get_positions(self) -> list[BrokerPosition]:
        """Fetch current positions."""
        ...

    def place_order(self, order: OrderRequest) -> OrderResult:
        """Submit a single order.  Returns after fill or rejection."""
        ...

    def execute_batch(self, orders: list[OrderRequest]) -> list[OrderResult]:
        """Submit multiple orders sequentially, honouring priority order.

        Default implementation calls :meth:`place_order` for each.
        """
        ...


# ── Manual / dry-run adapter ────────────────────────────────────────────


class DryRunBroker:
    """No-op broker that logs trades without executing.

    Used for ``--dry-run`` and the T212 manual workflow.
    """

    @property
    def name(self) -> str:
        return "Dry-Run (no execution)"

    @property
    def is_connected(self) -> bool:
        return True

    def connect(self) -> None:
        pass

    def disconnect(self) -> None:
        pass

    def get_account(self) -> AccountSummary:
        return AccountSummary()

    def get_positions(self) -> list[BrokerPosition]:
        return []

    def place_order(self, order: OrderRequest) -> OrderResult:
        return OrderResult(
            ticker=order.ticker,
            side=order.side,
            requested_eur=order.amount_eur,
            filled_eur=order.amount_eur,
            filled_shares=order.shares or 0.0,
            status=OrderStatus.FILLED,
            broker_order_id="DRY-RUN",
        )

    def execute_batch(self, orders: list[OrderRequest]) -> list[OrderResult]:
        return [self.place_order(o) for o in orders]
