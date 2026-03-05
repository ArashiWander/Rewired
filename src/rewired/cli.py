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


@main.command("evaluate")
@click.option("--ticker", "-t", default=None, help="Evaluate a single ticker (e.g. NVDA)")
@click.option("--all", "all_stocks", is_flag=True, help="Evaluate entire universe")
def evaluate_cmd(ticker, all_stocks):
    """Run Gemini per-company fundamental evaluation."""
    if not ticker and not all_stocks:
        console.print("[dim]Specify --ticker NVDA or --all to evaluate the universe.[/dim]")
        return

    if all_stocks:
        from rewired.agent.evaluator import evaluate_universe
        from rewired.notifications.console import print_evaluation_batch

        console.print("[dim]Evaluating full universe (this may take a minute)...[/dim]")
        batch = evaluate_universe()
        print_evaluation_batch(batch)
    else:
        from rewired.agent.evaluator import evaluate_stock_by_ticker
        from rewired.notifications.console import print_evaluation

        console.print(f"[dim]Evaluating {ticker.upper()}...[/dim]")
        ev = evaluate_stock_by_ticker(ticker)
        print_evaluation(ev)


@main.command("resolve")
@click.argument("query")
def resolve_cmd(query):
    """Resolve a company name or alias to a ticker."""
    from rewired.data.ticker_resolver import resolve

    result = resolve(query)
    if result is None:
        console.print(f"[red]Could not resolve:[/red] {query}")
        return

    in_uni = "[green]Yes[/green]" if result.in_universe else "[dim]No[/dim]"
    console.print(f"\n  [bold]{result.ticker}[/bold]  {result.name}")
    console.print(f"  Score: {result.score:.0f}  Source: {result.source}  In universe: {in_uni}")
    if result.metadata:
        console.print(f"  {result.metadata}")
    console.print()


@main.command("execute")
@click.option("--dry-run", is_flag=True, default=True, help="Print trades without executing (default: on)")
@click.option("--live", is_flag=True, help="ACTUALLY execute trades via IBKR (overrides --dry-run)")
@click.option("--broker", type=click.Choice(["ibkr", "dry"]), default="dry", help="Broker to use")
def execute_cmd(dry_run, live, broker):
    """Run full pipeline: signals -> sizing -> broker orders."""
    from rewired.notifications.console import print_execution_plan, print_execution_results

    if live:
        dry_run = False

    console.print("[bold]Rewired Index — Execution Pipeline[/bold]\n")
    console.print("[dim]Step 1: Computing signals...[/dim]")
    from rewired.signals.engine import compute_signals
    sig = compute_signals()

    console.print("[dim]Step 2: Loading portfolio & universe...[/dim]")
    from rewired.models.universe import load_universe
    from rewired.portfolio.manager import load_portfolio, refresh_prices
    uni = load_universe()
    pf = load_portfolio()
    if pf.positions:
        refresh_prices(pf)

    console.print("[dim]Step 3: Computing sizing suggestions...[/dim]")
    from rewired.portfolio.sizing import calculate_suggestions
    suggestions = calculate_suggestions(pf, uni, sig)

    if not suggestions:
        console.print("\n[green]No trades needed — portfolio is on target.[/green]")
        return

    # Convert suggestions to OrderRequests
    from rewired.broker.interface import OrderRequest, OrderSide
    orders = []
    for s in suggestions:
        orders.append(OrderRequest(
            ticker=s["ticker"],
            side=OrderSide.BUY if s["action"] == "BUY" else OrderSide.SELL,
            amount_eur=s["amount_eur"],
            reason=s.get("reason", ""),
            priority=s.get("priority", 0),
        ))

    print_execution_plan(orders, sig, dry_run=dry_run)

    if dry_run:
        console.print("\n[yellow]DRY RUN — no orders sent.[/yellow]")
        console.print("[dim]Use --live to execute these trades via IBKR.[/dim]")
        return

    # Confirm before live execution
    if not click.confirm("\nExecute these trades?", default=False):
        console.print("[dim]Aborted.[/dim]")
        return

    # Select broker
    if broker == "ibkr":
        try:
            from rewired.broker.ibkr import IBKRBroker
            brk = IBKRBroker()
        except ImportError:
            console.print("[red]ib_insync not installed.[/red] Install with:")
            console.print('  pip install -e ".[broker]"')
            return
    else:
        from rewired.broker.interface import DryRunBroker
        brk = DryRunBroker()

    console.print(f"\n[dim]Connecting to {brk.name}...[/dim]")
    try:
        brk.connect()
        results = brk.execute_batch(orders)
        print_execution_results(results)
    except Exception as e:
        console.print(f"[red]Broker error: {e}[/red]")
    finally:
        try:
            brk.disconnect()
        except Exception:
            pass


@main.command("pipeline")
@click.option("--dry-run", is_flag=True, default=True, help="Full DAG run without placing trades")
@click.option("--live", is_flag=True, help="Execute trades at the end of the pipeline")
@click.option("--evaluate", is_flag=True, help="Include per-company evaluation step")
@click.option("--notify/--no-notify", default=True, help="Send Telegram notifications")
def pipeline_cmd(dry_run, live, evaluate, notify):
    """Run the full end-to-end DAG pipeline."""
    if live:
        dry_run = False

    from rewired.pipeline import run_pipeline

    console.print("[bold]Rewired Index — Full Pipeline[/bold]\n")
    run_pipeline(
        dry_run=dry_run,
        include_evaluation=evaluate,
        send_notifications=notify,
    )
