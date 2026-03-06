"""Scheduled monitoring - periodic signal checks and notifications."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import schedule
from rich.console import Console

from rewired import get_data_dir
from rewired.notifications.dispatcher import dispatch_signal_change, dispatch_portfolio_summary

console = Console()


def _get_last_signal_color() -> str | None:
    """Read the last known signal color from history."""
    history_path = get_data_dir() / "signal_history.json"
    if not history_path.exists():
        return None
    try:
        with open(history_path, encoding="utf-8") as f:
            history = json.load(f)
        if history:
            return history[-1].get("to_color")
    except (json.JSONDecodeError, OSError):
        pass
    return None


def check_signals() -> None:
    """Run a signal check and notify on color change."""
    from rewired.signals.engine import compute_signals
    from rewired.notifications.console import print_signals

    console.print(f"\n[dim]--- Signal check at {datetime.now().strftime('%H:%M')} ---[/dim]")

    old_color = _get_last_signal_color()
    result = compute_signals()
    new_color = result.overall_color.value

    print_signals(result)

    if old_color and old_color != new_color:
        dispatch_signal_change(old_color, new_color, result.summary)


def daily_portfolio_summary() -> None:
    """Generate and send daily portfolio summary."""
    from rewired.portfolio.manager import load_portfolio, refresh_prices
    from rewired.portfolio.tracker import snapshot_portfolio

    pf = load_portfolio()
    if pf.positions:
        refresh_prices(pf)
        snapshot_portfolio(pf)

    total = pf.total_value_eur
    cash = pf.cash_eur
    invested = pf.invested_eur
    num = len(pf.positions)

    lines = [
        f"Total: {total:.2f} EUR",
        f"Cash: {cash:.2f} EUR ({cash/total*100:.1f}%)" if total > 0 else f"Cash: {cash:.2f} EUR",
        f"Invested: {invested:.2f} EUR ({invested/total*100:.1f}%)" if total > 0 else f"Invested: {invested:.2f} EUR",
        f"Positions: {num}",
    ]

    if pf.positions:
        lines.append("\nTop positions:")
        sorted_pos = sorted(pf.positions.values(), key=lambda p: p.market_value_eur, reverse=True)
        for p in sorted_pos[:5]:
            pnl_sign = "+" if p.unrealized_pnl_eur >= 0 else ""
            lines.append(f"  {p.ticker}: {p.market_value_eur:.2f} EUR ({pnl_sign}{p.unrealized_pnl_eur:.2f})")

    summary = "\n".join(lines)
    dispatch_portfolio_summary(summary)


def reeval_universe() -> None:
    """Log a universe snapshot (tier changes are now manual-only)."""
    from rewired.agent.rebalancer import rebalance_universe

    console.print(f"\n[dim]--- Universe snapshot at {datetime.now().strftime('%H:%M')} ---[/dim]")

    try:
        snapshot = rebalance_universe()
        console.print(f"[dim]Universe: {len(snapshot)} stocks loaded.[/dim]")
    except Exception as exc:
        console.print(f"[red]Universe snapshot error: {exc}[/red]")


def start_monitor() -> None:
    """Start the scheduled monitoring loop."""
    # Signal check every 4 hours during market hours
    schedule.every(4).hours.do(check_signals)

    # Daily portfolio summary at 18:30
    schedule.every().day.at("18:30").do(daily_portfolio_summary)

    # Weekly summary on Monday at 08:00
    schedule.every().monday.at("08:00").do(daily_portfolio_summary)

    # Weekly universe rebalance on Sunday at 20:00
    schedule.every().sunday.at("20:00").do(reeval_universe)

    # Run an initial check immediately
    check_signals()

    console.print("\n[bold green]Monitor active.[/bold green] Scheduled tasks:")
    console.print("  - Signal check: every 4 hours")
    console.print("  - Portfolio summary: daily at 18:30")
    console.print("  - Weekly summary: Monday at 08:00")
    console.print("  - Universe rebalance: Sunday at 20:00")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        console.print("\n[bold]Monitor stopped.[/bold]")


# ── Live price feed ──────────────────────────────────────────────────────

# In-memory price cache: {ticker: (price, timestamp)}
_price_cache: dict[str, tuple[float, float]] = {}
_price_callbacks: list = []

_PRICE_POLL_INTERVAL = 60  # seconds


def get_cached_price(ticker: str) -> float | None:
    """Get the last known price for a ticker from the live cache."""
    entry = _price_cache.get(ticker)
    if entry:
        return entry[0]
    return None


def get_all_cached_prices() -> dict[str, float]:
    """Return all cached prices as {ticker: price}."""
    return {t: v[0] for t, v in _price_cache.items()}


def register_price_callback(callback) -> None:
    """Register a callback ``fn(ticker, price)`` for live price updates."""
    _price_callbacks.append(callback)


def _notify_callbacks(ticker: str, price: float) -> None:
    """Fire all registered callbacks."""
    for cb in _price_callbacks:
        try:
            cb(ticker, price)
        except Exception:
            pass


def poll_prices_yfinance(tickers: list[str]) -> None:
    """Fetch current prices via yfinance and update the cache.

    Called periodically by the scheduler as a fallback when IBKR is not
    connected.  Thread-safe for background execution.
    """
    import yfinance as yf

    if not tickers:
        return

    try:
        data = yf.download(
            tickers,
            period="1d",
            interval="1m",
            progress=False,
            threads=True,
        )
        if data.empty:
            return

        now = time.time()
        # yfinance returns multi-level columns for multiple tickers
        if len(tickers) == 1:
            last = data["Close"].iloc[-1]
            if last and last > 0:
                _price_cache[tickers[0]] = (float(last), now)
                _notify_callbacks(tickers[0], float(last))
        else:
            close = data["Close"]
            for ticker in tickers:
                if ticker in close.columns:
                    val = close[ticker].iloc[-1]
                    if val and val > 0:
                        _price_cache[ticker] = (float(val), now)
                        _notify_callbacks(ticker, float(val))
    except Exception as e:
        console.print(f"[dim]Price poll error: {e}[/dim]")


def start_price_feed(tickers: list[str], use_ibkr: bool = False) -> None:
    """Start a background price feed.

    If *use_ibkr* is True and IBKR is connected, uses streaming market data.
    Otherwise falls back to yfinance polling every 60 seconds.
    """
    import threading

    if use_ibkr:
        try:
            from rewired.broker.ibkr import IBKRBroker

            brk = IBKRBroker()
            brk.connect()

            def _on_tick(ticker: str, price: float):
                _price_cache[ticker] = (price, time.time())
                _notify_callbacks(ticker, price)

            brk.subscribe_market_data(tickers, _on_tick)
            console.print(f"[green]IBKR streaming active for {len(tickers)} tickers[/green]")
            return
        except Exception as e:
            console.print(f"[yellow]IBKR streaming failed ({e}), falling back to yfinance polling[/yellow]")

    # yfinance polling fallback
    def _poll_loop():
        while True:
            poll_prices_yfinance(tickers)
            time.sleep(_PRICE_POLL_INTERVAL)

    thread = threading.Thread(target=_poll_loop, daemon=True, name="price-feed")
    thread.start()
    console.print(f"[green]Price feed active (yfinance, every {_PRICE_POLL_INTERVAL}s, {len(tickers)} tickers)[/green]")
