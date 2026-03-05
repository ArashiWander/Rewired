"""Notification dispatcher - routes to active channels."""

from __future__ import annotations

from rich.console import Console

from rewired.notifications import telegram

console = Console()


def dispatch_signal_change(from_color: str, to_color: str, summary: str) -> None:
    """Dispatch a signal color change notification to all active channels."""
    # Always print to console
    console.print(f"\n[bold]SIGNAL CHANGE:[/bold] {from_color.upper()} -> {to_color.upper()}")
    console.print(f"  {summary}\n")

    # Send via Telegram if configured
    if telegram.is_configured():
        success = telegram.send_signal_change(from_color, to_color, summary)
        if success:
            console.print("[dim]Telegram notification sent.[/dim]")
        else:
            console.print("[dim yellow]Telegram notification failed.[/dim yellow]")


def dispatch_portfolio_summary(summary_text: str) -> None:
    """Dispatch portfolio summary to all active channels."""
    console.print(summary_text)

    if telegram.is_configured():
        telegram.send_portfolio_summary(summary_text)


def dispatch_alert(message: str) -> None:
    """Dispatch a general alert."""
    console.print(f"[bold]{message}[/bold]")

    if telegram.is_configured():
        telegram.send_alert(message)
