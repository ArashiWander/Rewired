"""Reusable NiceGUI component builders for the Rewired Index dashboard."""

from __future__ import annotations

from nicegui import ui

# Color mapping for signal colors
SIGNAL_COLORS = {
    "green": "#22c55e",
    "yellow": "#eab308",
    "orange": "#f97316",
    "red": "#ef4444",
}

REGIME_COLORS = {
    "risk_on": "#22c55e",
    "neutral": "#eab308",
    "risk_off": "#f97316",
    "crisis": "#ef4444",
}


def signal_board(composite) -> None:
    """Render the Signal Board card with traffic lights for each category + composite."""
    with ui.card().classes("w-full"):
        ui.label("Signal Board").classes("text-h5 q-mb-md")

        with ui.row().classes("justify-around w-full items-start"):
            # One traffic light per category
            for cat, cat_sig in composite.categories.items():
                color = cat_sig.composite_color.value
                hex_color = SIGNAL_COLORS.get(color, "#888")
                label = cat.value.upper().replace("_", " ")

                with ui.column().classes("items-center"):
                    ui.html(
                        f'<div style="width:60px;height:60px;border-radius:50%;'
                        f'background:{hex_color};box-shadow:0 0 15px {hex_color};'
                        f'margin:0 auto;"></div>'
                    )
                    ui.label(label).classes("text-subtitle2 q-mt-sm")
                    ui.label(color.upper()).style(f"color:{hex_color};font-weight:bold")
                    ui.label(cat_sig.explanation[:60]).classes(
                        "text-caption text-grey"
                    ).style("max-width:160px;text-align:center")

            # Composite (larger, emphasized)
            overall = composite.overall_color.value
            hex_color = SIGNAL_COLORS.get(overall, "#888")
            with ui.column().classes("items-center"):
                ui.html(
                    f'<div style="width:80px;height:80px;border-radius:50%;'
                    f'background:{hex_color};box-shadow:0 0 25px {hex_color};'
                    f'border:3px solid white;margin:0 auto;"></div>'
                )
                ui.label("COMPOSITE").classes("text-subtitle1 q-mt-sm").style(
                    "font-weight:bold"
                )
                ui.label(overall.upper()).style(
                    f"color:{hex_color};font-weight:bold;font-size:1.2em"
                )
                ui.label(composite.summary[:80]).classes(
                    "text-caption text-grey"
                ).style("max-width:200px;text-align:center")


def universe_matrix(universe) -> None:
    """Render the LxT Universe Matrix as a table."""
    from rewired.models.universe import Layer, Tier, LAYER_NAMES, TIER_NAMES

    with ui.card().classes("w-full"):
        ui.label("LxT Universe Matrix").classes("text-h5 q-mb-md")

        columns = [
            {"name": "layer", "label": "Layer", "field": "layer", "align": "left"},
        ]
        for tier in Tier:
            columns.append({
                "name": f"t{tier.value}",
                "label": TIER_NAMES[tier],
                "field": f"t{tier.value}",
                "align": "center",
            })

        rows = []
        for layer in Layer:
            row = {"layer": f"L{layer.value} {LAYER_NAMES[layer]}"}
            for tier in Tier:
                stocks = universe.get_by_coordinate(layer, tier)
                row[f"t{tier.value}"] = (
                    ", ".join(s.ticker for s in stocks) if stocks else "-"
                )
            rows.append(row)

        ui.table(columns=columns, rows=rows, row_key="layer").classes("w-full")


def portfolio_table(portfolio) -> None:
    """Render portfolio positions with P&L."""
    with ui.card().classes("w-full"):
        ui.label("Portfolio").classes("text-h5 q-mb-md")

        if not portfolio or not portfolio.positions:
            ui.label("No positions yet.").classes("text-grey")
            _portfolio_summary(portfolio)
            return

        columns = [
            {"name": "ticker", "label": "Ticker", "field": "ticker", "align": "left", "sortable": True},
            {"name": "shares", "label": "Shares", "field": "shares", "align": "right"},
            {"name": "avg_cost", "label": "Avg Cost", "field": "avg_cost", "align": "right"},
            {"name": "current", "label": "Current", "field": "current", "align": "right"},
            {"name": "value", "label": "Value (EUR)", "field": "value", "align": "right", "sortable": True},
            {"name": "pnl", "label": "P&L (EUR)", "field": "pnl", "align": "right", "sortable": True},
            {"name": "weight", "label": "Weight %", "field": "weight", "align": "right", "sortable": True},
        ]

        rows = []
        for ticker, pos in sorted(portfolio.positions.items()):
            rows.append({
                "ticker": ticker,
                "shares": f"{pos.shares:.4f}",
                "avg_cost": f"{pos.avg_cost_eur:.2f}",
                "current": f"{pos.current_price_eur:.2f}",
                "value": f"{pos.market_value_eur:.2f}",
                "pnl": f"{pos.unrealized_pnl_eur:+.2f}",
                "weight": f"{pos.weight_pct:.1f}%",
            })

        ui.table(columns=columns, rows=rows, row_key="ticker").classes("w-full")
        _portfolio_summary(portfolio)


def _portfolio_summary(portfolio) -> None:
    """Render portfolio summary metrics."""
    if not portfolio:
        return
    with ui.row().classes("q-mt-md justify-around w-full"):
        ui.label(f"Cash: {portfolio.cash_eur:.2f} EUR").classes("text-bold")
        ui.label(f"Invested: {portfolio.invested_eur:.2f} EUR").classes("text-bold")
        ui.label(f"Total: {portfolio.total_value_eur:.2f} EUR").classes("text-bold")


def pies_allocation_table(allocations: list[dict], composite) -> None:
    """Render the T212 Pies allocation target table."""
    with ui.card().classes("w-full"):
        overall = composite.overall_color.value
        hex_color = SIGNAL_COLORS.get(overall, "#888")
        ui.label("Trading 212 Pies Allocation").classes("text-h5 q-mb-sm")
        ui.html(
            f'<span style="color:{hex_color};font-weight:bold">'
            f"Signal: {overall.upper()}</span>"
        )

        columns = [
            {"name": "ticker", "label": "Ticker", "field": "ticker", "align": "left"},
            {"name": "name", "label": "Name", "field": "name", "align": "left"},
            {"name": "layer", "label": "Layer", "field": "layer", "align": "center"},
            {"name": "tier", "label": "Tier", "field": "tier", "align": "center"},
            {"name": "target_pct", "label": "Target %", "field": "target_pct", "align": "right"},
            {"name": "target_eur", "label": "Target EUR", "field": "target_eur", "align": "right"},
        ]

        rows = []
        for a in allocations:
            rows.append({
                "ticker": a["ticker"],
                "name": a["name"],
                "layer": a["layer"],
                "tier": a["tier"],
                "target_pct": f"{a['target_pct']:.1f}%",
                "target_eur": f"{a['target_eur']:.2f}",
            })

        ui.table(columns=columns, rows=rows, row_key="ticker").classes("w-full")

        # Summary
        total_alloc = sum(a["target_pct"] for a in allocations if a["ticker"] != "CASH")
        cash_pct = next(
            (a["target_pct"] for a in allocations if a["ticker"] == "CASH"), 0
        )
        with ui.row().classes("q-mt-sm justify-around"):
            ui.label(f"Allocated: {total_alloc:.1f}%").classes("text-bold")
            ui.label(f"Cash reserve: {cash_pct:.1f}%").classes("text-bold")


def suggestions_panel(suggestions: list[dict], composite) -> None:
    """Render the suggestions panel with BUY/SELL actions."""
    with ui.card().classes("w-full"):
        ui.label("Suggested Actions").classes("text-h5 q-mb-md")

        if not suggestions:
            ui.label("No actions needed - portfolio is balanced.").classes("text-grey")
            return

        phase_labels = {1: "Take Profit", 2: "Signal Exit", 3: "New Buy", 4: "Redistribute"}

        columns = [
            {"name": "ticker", "label": "Ticker", "field": "ticker", "align": "left"},
            {"name": "action", "label": "Action", "field": "action", "align": "center"},
            {"name": "amount", "label": "Amount (EUR)", "field": "amount", "align": "right"},
            {"name": "phase", "label": "Phase", "field": "phase", "align": "center"},
            {"name": "reason", "label": "Reason", "field": "reason", "align": "left"},
        ]

        rows = []
        for s in suggestions:
            rows.append({
                "ticker": s["ticker"],
                "action": s["action"],
                "amount": f"{s['amount_eur']:.2f}",
                "phase": phase_labels.get(s.get("priority"), "?"),
                "reason": s["reason"],
            })

        ui.table(columns=columns, rows=rows, row_key="ticker").classes("w-full")


def signal_history_timeline(history: list[dict]) -> None:
    """Render the signal history as a list."""
    with ui.card().classes("w-full"):
        ui.label("Signal History").classes("text-h5 q-mb-md")

        if not history:
            ui.label("No signal changes recorded yet.").classes("text-grey")
            return

        columns = [
            {"name": "time", "label": "Time", "field": "time", "align": "left"},
            {"name": "from_c", "label": "From", "field": "from_c", "align": "center"},
            {"name": "to_c", "label": "To", "field": "to_c", "align": "center"},
            {"name": "summary", "label": "Summary", "field": "summary", "align": "left"},
        ]

        rows = []
        for entry in reversed(history[-20:]):
            rows.append({
                "time": entry.get("timestamp", "?"),
                "from_c": entry.get("from_color", "?").upper(),
                "to_c": entry.get("to_color", "?").upper(),
                "summary": entry.get("summary", ""),
            })

        ui.table(columns=columns, rows=rows, row_key="time").classes("w-full")


def ai_analysis_panel() -> None:
    """Render the AI analysis panel with on-demand Gemini analysis."""
    with ui.card().classes("w-full"):
        ui.label("AI Analyst").classes("text-h5 q-mb-md")

        output_area = ui.markdown("Click a button below to run Gemini analysis.")

        async def run_analysis_click():
            output_area.set_content("*Running Gemini analysis...*")
            try:
                from rewired.agent.analyst import run_analysis
                result = await _run_in_thread(run_analysis)
                output_area.set_content(result)
            except Exception as e:
                output_area.set_content(f"**Error:** {e}")

        async def run_regime_click():
            output_area.set_content("*Running regime assessment...*")
            try:
                from rewired.agent.analyst import market_regime_assessment
                result = await _run_in_thread(market_regime_assessment)
                regime_label = result.regime.upper().replace("_", " ")
                hex_color = REGIME_COLORS.get(result.regime, "#888")
                text = (
                    f"**Regime:** <span style='color:{hex_color}'>{regime_label}</span> "
                    f"(confidence: {result.confidence:.0%})\n\n"
                    f"{result.reasoning}\n\n"
                    f"**Action:** {result.actionable_insight}\n\n"
                    f"**Key Risk:** {result.key_risk}\n\n"
                    f"*Regime shift probability (2wk):* {result.regime_shift_probability:.0%}"
                )
                output_area.set_content(text)
            except Exception as e:
                output_area.set_content(f"**Error:** {e}")

        with ui.row().classes("q-mt-sm"):
            ui.button("Run Analysis", on_click=run_analysis_click, icon="analytics")
            ui.button("Regime Assessment", on_click=run_regime_click, icon="assessment")


async def _run_in_thread(func, *args):
    """Run a blocking function in a thread pool to keep UI responsive."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)
