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


def start_monitor() -> None:
    """Start the scheduled monitoring loop."""
    # Signal check every 4 hours during market hours
    schedule.every(4).hours.do(check_signals)

    # Daily portfolio summary at 18:30
    schedule.every().day.at("18:30").do(daily_portfolio_summary)

    # Weekly summary on Monday at 08:00
    schedule.every().monday.at("08:00").do(daily_portfolio_summary)

    # Run an initial check immediately
    check_signals()

    console.print("\n[bold green]Monitor active.[/bold green] Scheduled tasks:")
    console.print("  - Signal check: every 4 hours")
    console.print("  - Portfolio summary: daily at 18:30")
    console.print("  - Weekly summary: Monday at 08:00")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    try:
        while True:
            schedule.run_pending()
            time.sleep(60)
    except KeyboardInterrupt:
        console.print("\n[bold]Monitor stopped.[/bold]")
