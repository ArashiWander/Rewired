"""Rewired Index CLI entry point."""

import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option(package_name="rewired-index")
def main():
    """Rewired Index: AI-powered 5-layer investment framework."""
    pass


@main.command()
def signals():
    """Show current signal lights (macro, sentiment, AI health)."""
    from rewired.signals.engine import compute_signals
    from rewired.notifications.console import print_signals

    result = compute_signals()
    print_signals(result)


@main.command()
def universe():
    """Display the LxT stock universe matrix."""
    from rewired.notifications.console import print_universe
    from rewired.models.universe import load_universe

    uni = load_universe()
    print_universe(uni)


@main.group(invoke_without_command=True)
@click.pass_context
def portfolio(ctx):
    """Show or manage portfolio positions."""
    if ctx.invoked_subcommand is None:
        from rewired.portfolio.manager import load_portfolio, refresh_prices, save_portfolio
        from rewired.notifications.console import print_portfolio

        pf = load_portfolio()
        if pf.positions:
            console.print("[dim]Refreshing prices...[/dim]")
            refresh_prices(pf)
            save_portfolio(pf)
        print_portfolio(pf)


@portfolio.command("add")
@click.option("--ticker", required=True, help="Stock ticker (e.g. NVDA)")
@click.option("--action", required=True, type=click.Choice(["BUY", "SELL"]))
@click.option("--shares", required=True, type=float, help="Number of shares")
@click.option("--price", required=True, type=float, help="Price per share in EUR")
@click.option("--notes", default="", help="Optional trade notes")
def portfolio_add(ticker, action, shares, price, notes):
    """Record a trade executed on Trading 212."""
    from rewired.portfolio.manager import load_portfolio, record_transaction, save_portfolio

    pf = load_portfolio()
    record_transaction(pf, ticker=ticker.upper(), action=action, shares=shares, price_eur=price, notes=notes)
    save_portfolio(pf)
    console.print(f"[green]Recorded: {action} {shares} x {ticker.upper()} @ {price:.2f} EUR[/green]")


@main.command()
def suggest():
    """Get position sizing suggestions based on current signals."""
    from rewired.models.universe import load_universe
    from rewired.portfolio.manager import load_portfolio, refresh_prices
    from rewired.portfolio.sizing import calculate_suggestions
    from rewired.signals.engine import compute_signals
    from rewired.notifications.console import print_suggestions

    uni = load_universe()
    pf = load_portfolio()
    if pf.positions:
        refresh_prices(pf)
    sig = compute_signals()
    suggestions = calculate_suggestions(pf, uni, sig)
    print_suggestions(suggestions, sig)


@main.command()
def pies():
    """Show target Pies allocation for Trading 212."""
    from rewired.models.universe import load_universe
    from rewired.portfolio.manager import load_portfolio, refresh_prices
    from rewired.portfolio.sizing import calculate_pies_allocation
    from rewired.signals.engine import compute_signals
    from rewired.notifications.console import print_pies_allocation

    uni = load_universe()
    pf = load_portfolio()
    if pf.positions:
        console.print("[dim]Refreshing prices...[/dim]")
        refresh_prices(pf)
    sig = compute_signals()
    allocations = calculate_pies_allocation(pf, uni, sig)
    print_pies_allocation(allocations, sig)


@main.command()
def analyze():
    """Run Gemini AI analysis on portfolio and signals."""
    from rewired.agent.analyst import run_analysis

    console.print("[dim]Running Gemini analysis...[/dim]")
    result = run_analysis()
    console.print(result)


@main.command()
def regime():
    """Get AI market regime assessment."""
    from rewired.agent.analyst import market_regime_assessment
    from rewired.notifications.console import print_regime_assessment

    console.print("[dim]Running Gemini regime assessment...[/dim]")
    result = market_regime_assessment()
    print_regime_assessment(result)


@main.command()
@click.option("--port", default=8080, help="Port for the web dashboard")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def gui(port, reload):
    """Launch the Rewired Index web dashboard."""
    try:
        from rewired.gui.app import launch
    except ImportError:
        console.print("[red]NiceGUI not installed.[/red] Install with:")
        console.print("  pip install -e \".[gui]\"")
        return

    console.print(f"[bold]Starting Rewired Index Dashboard on http://localhost:{port}[/bold]")
    launch(port=port, reload=reload)


@main.command()
def monitor():
    """Start the scheduled signal monitor (runs in foreground)."""
    from rewired.scheduler import start_monitor

    console.print("[bold]Starting Rewired Index monitor...[/bold]")
    console.print("[dim]Press Ctrl+C to stop[/dim]")
    start_monitor()


@main.command()
def history():
    """Show signal color change history."""
    from rewired.notifications.console import print_signal_history

    print_signal_history()
