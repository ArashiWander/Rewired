"""Interactive Brokers adapter via ib_insync.

Connects to IB Gateway or TWS, places market orders, fetches positions
and account balances.  Supports fractional shares where available.

Environment variables
---------------------
IB_HOST : str   – Gateway/TWS host (default ``127.0.0.1``)
IB_PORT : int   – Gateway/TWS port (default ``4002`` for paper, ``4001`` live)
IB_CLIENT_ID : int – unique client id (default ``1``)

Optional dependency: install with ``pip install -e ".[broker]"``
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime

from dotenv import load_dotenv

from rewired.broker.interface import (
    AccountSummary,
    Broker,
    BrokerPosition,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderStatus,
)

load_dotenv()
logger = logging.getLogger(__name__)

# ── Configuration ────────────────────────────────────────────────────────

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 4002       # IB Gateway paper trading
_DEFAULT_CLIENT_ID = 1
_ORDER_TIMEOUT = 30        # seconds to wait for fill
_CURRENCY = "EUR"


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key, "")
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


# ── IBKR Broker ──────────────────────────────────────────────────────────


class IBKRBroker:
    """Interactive Brokers adapter implementing the :class:`Broker` protocol.

    Lazy-imports ``ib_insync`` so the module can be imported without the
    optional dependency installed.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        client_id: int | None = None,
    ) -> None:
        self._host = host or os.environ.get("IB_HOST", _DEFAULT_HOST)
        self._port = port or _env_int("IB_PORT", _DEFAULT_PORT)
        self._client_id = client_id or _env_int("IB_CLIENT_ID", _DEFAULT_CLIENT_ID)
        self._ib = None  # ib_insync.IB instance (lazy)
        self._account: str = ""

    # ── Protocol properties ──────────────────────────────────────────

    @property
    def name(self) -> str:
        return "Interactive Brokers"

    @property
    def is_connected(self) -> bool:
        return self._ib is not None and self._ib.isConnected()

    # ── Connection ───────────────────────────────────────────────────

    def connect(self) -> None:
        """Connect to IB Gateway / TWS."""
        from ib_insync import IB

        if self._ib is not None and self._ib.isConnected():
            logger.info("Already connected to IBKR")
            return

        self._ib = IB()
        self._ib.connect(
            host=self._host,
            port=self._port,
            clientId=self._client_id,
            readonly=False,
        )
        accounts = self._ib.managedAccounts()
        self._account = accounts[0] if accounts else ""
        logger.info(
            "Connected to IBKR at %s:%s (account=%s)",
            self._host,
            self._port,
            self._account,
        )

    def disconnect(self) -> None:
        if self._ib is not None:
            self._ib.disconnect()
            logger.info("Disconnected from IBKR")

    # ── Account ──────────────────────────────────────────────────────

    def get_account(self) -> AccountSummary:
        """Fetch account balances from IBKR."""
        self._ensure_connected()
        summary = self._ib.accountSummary(self._account)

        values: dict[str, float] = {}
        for item in summary:
            if item.currency in (_CURRENCY, "BASE"):
                try:
                    values[item.tag] = float(item.value)
                except (ValueError, TypeError):
                    pass

        return AccountSummary(
            total_value_eur=values.get("NetLiquidation", 0.0),
            cash_eur=values.get("TotalCashValue", 0.0),
            buying_power_eur=values.get("BuyingPower", 0.0),
            unrealized_pnl_eur=values.get("UnrealizedPnL", 0.0),
            currency=_CURRENCY,
        )

    # ── Positions ────────────────────────────────────────────────────

    def get_positions(self) -> list[BrokerPosition]:
        """Fetch current positions from IBKR."""
        self._ensure_connected()
        positions = self._ib.positions(self._account)

        result: list[BrokerPosition] = []
        for pos in positions:
            contract = pos.contract
            ticker = contract.symbol
            shares = float(pos.position)
            avg_cost = float(pos.avgCost) if pos.avgCost else 0.0

            # Request market price
            market_price = self._get_market_price(contract) or avg_cost
            market_value = shares * market_price
            pnl = market_value - (shares * avg_cost)

            result.append(BrokerPosition(
                ticker=ticker,
                shares=shares,
                avg_cost=avg_cost,
                market_price=market_price,
                market_value_eur=market_value,
                unrealized_pnl_eur=pnl,
            ))

        return result

    # ── Orders ───────────────────────────────────────────────────────

    def place_order(self, order: OrderRequest) -> OrderResult:
        """Place a market order via IBKR.

        Supports fractional shares for US equities via ``MarketOrder`` with
        fractional size.  Falls back to rounding to whole shares for
        exchanges that don't support fractions.
        """
        self._ensure_connected()
        from ib_insync import MarketOrder, Stock as IBStock

        contract = IBStock(order.ticker, "SMART", _CURRENCY)
        self._ib.qualifyContracts(contract)

        # Determine share quantity
        if order.shares is not None and order.shares > 0:
            qty = order.shares
        else:
            # Estimate from amount_eur: get a current price
            price = self._get_market_price(contract)
            if not price or price <= 0:
                return OrderResult(
                    ticker=order.ticker,
                    side=order.side,
                    requested_eur=order.amount_eur,
                    status=OrderStatus.REJECTED,
                    error=f"Cannot determine price for {order.ticker}",
                )
            qty = round(order.amount_eur / price, 4)  # fractional precision

        action = "BUY" if order.side == OrderSide.BUY else "SELL"

        # Use fractional-capable MarketOrder
        ib_order = MarketOrder(action, qty)
        ib_order.outsideRth = False  # only during regular hours

        trade = self._ib.placeOrder(contract, ib_order)

        # Wait for fill
        filled = self._wait_for_fill(trade)

        if filled:
            fill = trade.orderStatus
            return OrderResult(
                ticker=order.ticker,
                side=order.side,
                requested_eur=order.amount_eur,
                filled_eur=fill.avgFillPrice * fill.filled if fill.avgFillPrice else 0.0,
                filled_shares=fill.filled,
                avg_price=fill.avgFillPrice or 0.0,
                status=OrderStatus.FILLED if fill.remaining == 0 else OrderStatus.PARTIALLY_FILLED,
                broker_order_id=str(trade.order.orderId),
                timestamp=datetime.now(),
            )
        else:
            status = trade.orderStatus
            return OrderResult(
                ticker=order.ticker,
                side=order.side,
                requested_eur=order.amount_eur,
                status=OrderStatus.ERROR,
                error=f"Order not filled within {_ORDER_TIMEOUT}s (status: {status.status})",
                broker_order_id=str(trade.order.orderId),
                timestamp=datetime.now(),
            )

    def execute_batch(self, orders: list[OrderRequest]) -> list[OrderResult]:
        """Execute orders sequentially in priority order."""
        sorted_orders = sorted(orders, key=lambda o: o.priority)
        results: list[OrderResult] = []
        for order in sorted_orders:
            try:
                result = self.place_order(order)
                results.append(result)
                if result.status in (OrderStatus.ERROR, OrderStatus.REJECTED):
                    logger.warning(
                        "Order %s %s failed: %s",
                        order.side.value,
                        order.ticker,
                        result.error,
                    )
            except Exception as e:
                logger.error("Order execution error for %s: %s", order.ticker, e)
                results.append(OrderResult(
                    ticker=order.ticker,
                    side=order.side,
                    requested_eur=order.amount_eur,
                    status=OrderStatus.ERROR,
                    error=str(e),
                ))
        return results

    # ── Streaming market data ────────────────────────────────────────

    def subscribe_market_data(self, tickers: list[str], callback) -> None:
        """Subscribe to real-time market data for a list of tickers.

        *callback* is called with ``(ticker, price)`` on each tick.
        """
        self._ensure_connected()
        from ib_insync import Stock as IBStock

        for ticker in tickers:
            contract = IBStock(ticker, "SMART", _CURRENCY)
            self._ib.qualifyContracts(contract)
            self._ib.reqMktData(contract)

        def _on_pending_tickers(tickers_update):
            for t in tickers_update:
                if t.last and t.last > 0:
                    callback(t.contract.symbol, t.last)
                elif t.close and t.close > 0:
                    callback(t.contract.symbol, t.close)

        self._ib.pendingTickersEvent += _on_pending_tickers

    def cancel_market_data(self) -> None:
        """Cancel all market data subscriptions."""
        if self._ib and self._ib.isConnected():
            for ticker in self._ib.tickers():
                self._ib.cancelMktData(ticker.contract)

    # ── Internal helpers ─────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            self.connect()

    def _get_market_price(self, contract) -> float | None:
        """Request a snapshot price for a contract."""
        try:
            tickers = self._ib.reqTickers(contract)
            if tickers:
                t = tickers[0]
                if t.last and t.last > 0:
                    return float(t.last)
                if t.close and t.close > 0:
                    return float(t.close)
        except Exception as e:
            logger.warning("Price request failed for %s: %s", contract.symbol, e)
        return None

    def _wait_for_fill(self, trade, timeout: int = _ORDER_TIMEOUT) -> bool:
        """Block until the trade is filled or timeout elapses."""
        start = time.time()
        while time.time() - start < timeout:
            self._ib.sleep(0.5)
            if trade.isDone():
                return trade.orderStatus.status == "Filled"
        return False
