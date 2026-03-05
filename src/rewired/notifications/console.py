"""Console output using Rich for terminal display."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from rewired.models.universe import Universe, Layer, Tier, LAYER_NAMES, TIER_NAMES

console = Console(force_terminal=True)

# Use EUR text instead of € symbol to avoid Windows GBK encoding issues
EUR = "EUR"

SIGNAL_STYLE = {
    "green": "bold green",
    "yellow": "bold yellow",
    "orange": "bold rgb(255,165,0)",
    "red": "bold red",
}


def print_universe(universe: Universe) -> None:
    """Display the LxT matrix as a rich table."""
    table = Table(title="Rewired Index - LxT Universe", show_lines=True)

    table.add_column("Layer", style="bold cyan", width=20)
    for tier in Tier:
        table.add_column(TIER_NAMES[tier], justify="center", width=18)

    for layer in Layer:
        row = [f"L{layer.value} {LAYER_NAMES[layer]}"]
        for tier in Tier:
            stocks = universe.get_by_coordinate(layer, tier)
            if stocks:
                cell = "\n".join(f"{s.ticker} ({s.max_weight_pct:.0f}%)" for s in stocks)
            else:
                cell = "[dim]-[/dim]"
            row.append(cell)
        table.add_row(*row)

    console.print()
    console.print(table)
    console.print(f"\n[dim]Total stocks: {len(universe.stocks)}[/dim]")


def print_signals(composite) -> None:
    """Display signal lights as a rich table."""
    from rewired.models.signals import SignalCategory

    table = Table(title="Rewired Index - Signal Board", show_lines=True)
    table.add_column("Category", style="bold", width=16)
    table.add_column("Signal", justify="center", width=10)
    table.add_column("Key Driver", width=40)

    for cat in SignalCategory:
        if cat in composite.categories:
            cs = composite.categories[cat]
            color = cs.composite_color.value
            style = SIGNAL_STYLE.get(color, "")
            label = cat.value.upper().replace("_", " ")
            table.add_row(label, f"[{style}]{color.upper()}[/{style}]", cs.explanation)

    # Composite row
    overall = composite.overall_color.value
    style = SIGNAL_STYLE.get(overall, "")
    table.add_row(
        "[bold]COMPOSITE[/bold]",
        f"[{style}]{overall.upper()}[/{style}]",
        composite.summary,
        style="on rgb(30,30,30)",
    )

    console.print()
    console.print(table)


def print_portfolio(portfolio) -> None:
    """Display portfolio positions as a rich table."""
    if not portfolio.positions:
        console.print("\n[dim]No positions yet. Use [bold]rewired portfolio add[/bold] to record a trade.[/dim]\n")
        _print_portfolio_summary(portfolio)
        return

    table = Table(title="Rewired Index - Portfolio", show_lines=True)
    table.add_column("Ticker", style="bold", width=8)
    table.add_column("Shares", justify="right", width=8)
    table.add_column("Avg Cost", justify="right", width=10)
    table.add_column("Current", justify="right", width=10)
    table.add_column("Value", justify="right", width=10)
    table.add_column("P&L", justify="right", width=10)
    table.add_column("Weight", justify="right", width=8)

    for ticker, pos in sorted(portfolio.positions.items()):
        pnl_style = "green" if pos.unrealized_pnl_eur >= 0 else "red"
        table.add_row(
            ticker,
            f"{pos.shares:.4f}",
            f"{pos.avg_cost_eur:.2f} {EUR}",
            f"{pos.current_price_eur:.2f} {EUR}",
            f"{pos.market_value_eur:.2f} {EUR}",
            f"[{pnl_style}]{pos.unrealized_pnl_eur:+.2f} {EUR}[/{pnl_style}]",
            f"{pos.weight_pct:.1f}%",
        )

    console.print()
    console.print(table)
    _print_portfolio_summary(portfolio)


def _print_portfolio_summary(portfolio) -> None:
    """Print portfolio summary line."""
    console.print(f"\n  Cash: [bold]{portfolio.cash_eur:.2f} {EUR}[/bold]  |  "
                  f"Invested: [bold]{portfolio.invested_eur:.2f} {EUR}[/bold]  |  "
                  f"Total: [bold]{portfolio.total_value_eur:.2f} {EUR}[/bold]\n")


def print_suggestions(suggestions: list, composite) -> None:
    """Display position sizing suggestions with phase labels."""
    overall = composite.overall_color.value
    style = SIGNAL_STYLE.get(overall, "")

    console.print(f"\n[bold]Signal:[/bold] [{style}]{overall.upper()}[/{style}]")

    if not suggestions:
        console.print("[dim]No actions needed - portfolio is balanced.[/dim]\n")
        return

    phase_labels = {1: "TP", 2: "Signal", 3: "Buy", 4: "Redist"}

    table = Table(title="Suggested Actions", show_lines=True)
    table.add_column("Ticker", style="bold", width=8)
    table.add_column("Action", width=8)
    table.add_column("Amount (EUR)", justify="right", width=14)
    table.add_column("Phase", justify="center", width=8)
    table.add_column("Reason", width=36)

    for s in suggestions:
        action_style = "green" if s["action"] == "BUY" else "red"
        phase = phase_labels.get(s.get("priority"), "?")
        table.add_row(
            s["ticker"],
            f"[{action_style}]{s['action']}[/{action_style}]",
            f"{s['amount_eur']:.2f} {EUR}",
            phase,
            s["reason"],
        )

    console.print()
    console.print(table)
    console.print()


def print_pies_allocation(allocations: list, composite) -> None:
    """Display the T212 Pies target allocation table."""
    overall = composite.overall_color.value
    style = SIGNAL_STYLE.get(overall, "")

    console.print(f"\n[bold]Signal:[/bold] [{style}]{overall.upper()}[/{style}]")

    table = Table(title="Trading 212 Pies - Target Allocation", show_lines=True)
    table.add_column("Ticker", style="bold", width=8)
    table.add_column("Name", width=20)
    table.add_column("Layer", justify="center", width=6)
    table.add_column("Tier", justify="center", width=6)
    table.add_column("Target %", justify="right", width=10)
    table.add_column(f"Target {EUR}", justify="right", width=12)

    for a in allocations:
        row_style = "dim" if a["ticker"] == "CASH" else ""
        table.add_row(
            a["ticker"],
            a["name"],
            a["layer"],
            a["tier"],
            f"{a['target_pct']:.1f}%",
            f"{a['target_eur']:.2f} {EUR}",
            style=row_style,
        )

    console.print()
    console.print(table)

    total_alloc = sum(a["target_pct"] for a in allocations if a["ticker"] != "CASH")
    cash_pct = next((a["target_pct"] for a in allocations if a["ticker"] == "CASH"), 0)
    console.print(f"\n  Allocated: [bold]{total_alloc:.1f}%[/bold]  |  "
                  f"Cash reserve: [bold]{cash_pct:.1f}%[/bold]\n")


def print_regime_assessment(assessment) -> None:
    """Display the AI market regime assessment."""
    regime_styles = {
        "risk_on": "bold green",
        "neutral": "bold yellow",
        "risk_off": "bold rgb(255,165,0)",
        "crisis": "bold red",
    }
    style = regime_styles.get(assessment.regime, "")
    label = assessment.regime.upper().replace("_", " ")

    console.print(f"\n[bold]Market Regime:[/bold] [{style}]{label}[/{style}]"
                  f"  (confidence: {assessment.confidence:.0%})")
    console.print(f"  {assessment.reasoning}")
    console.print(f"\n  [bold]Action:[/bold] {assessment.actionable_insight}")
    console.print(f"  [bold]Key Risk:[/bold] {assessment.key_risk}")
    console.print(f"  [dim]Regime shift probability (2wk): {assessment.regime_shift_probability:.0%}[/dim]\n")


def print_signal_history() -> None:
    """Display signal color change history."""
    import json

    from rewired import get_data_dir

    history_path = get_data_dir() / "signal_history.json"
    if not history_path.exists():
        console.print("\n[dim]No signal history yet. Run [bold]rewired signals[/bold] first.[/dim]\n")
        return

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    if not history:
        console.print("\n[dim]No signal changes recorded yet.[/dim]\n")
        return

    table = Table(title="Signal History", show_lines=True)
    table.add_column("Time", width=20)
    table.add_column("From", justify="center", width=10)
    table.add_column("To", justify="center", width=10)
    table.add_column("Summary", width=36)

    for entry in history[-20:]:  # Last 20 entries
        from_color = entry.get("from_color", "?")
        to_color = entry.get("to_color", "?")
        from_style = SIGNAL_STYLE.get(from_color, "")
        to_style = SIGNAL_STYLE.get(to_color, "")

        from_text = f"[{from_style}]{from_color.upper()}[/{from_style}]" if from_style else from_color.upper()
        to_text = f"[{to_style}]{to_color.upper()}[/{to_style}]" if to_style else to_color.upper()

        table.add_row(
            entry.get("timestamp", "?"),
            from_text,
            to_text,
            entry.get("summary", ""),
        )

    console.print()
    console.print(table)
    console.print()
