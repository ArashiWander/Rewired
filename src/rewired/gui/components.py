"""Reusable NiceGUI component builders for the Rewired Index dashboard."""

from __future__ import annotations

import re

from nicegui import ui

from rewired.gui.i18n import t, smart_truncate, layer_name, tier_name

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


# ── Header Components ────────────────────────────────────────────────────────


def header_signal_indicator(composite) -> None:
    """Compact composite signal indicator for the persistent header."""
    if composite is None:
        with ui.row().classes("items-center gap-2"):
            ui.html(
                '<div style="width:28px;height:28px;border-radius:50%;'
                'background:#555;"></div>'
            )
            ui.label(t("header.no_data")).classes("text-bold text-grey")
        return

    overall = composite.overall_color.value
    hex_color = SIGNAL_COLORS.get(overall, "#888")
    with ui.row().classes("items-center gap-2"):
        ui.html(
            f'<div style="width:28px;height:28px;border-radius:50%;'
            f'background:{hex_color};box-shadow:0 0 12px {hex_color};'
            f'border:2px solid white;"></div>'
        )
        ui.label(overall.upper()).style(
            f"color:{hex_color};font-weight:bold;font-size:1.1em"
        )


def data_status_bar(statuses: dict) -> None:
    """Render colored status badges for each data source.

    Shows green dots for healthy sources, yellow/red for errors with details.
    """
    all_ok = all(s.ok for s in statuses.values())

    if all_ok and any(s.last_success > 0 for s in statuses.values()):
        with ui.row().classes("items-center gap-1"):
            ui.html(
                '<div style="width:8px;height:8px;border-radius:50%;'
                'background:#22c55e;display:inline-block;"></div>'
            )
            ui.label(t("header.all_data_fresh")).classes("text-caption text-grey")
        return

    with ui.row().classes("items-center gap-3 flex-wrap"):
        for name, status in statuses.items():
            if status.last_success == 0 and not status.last_error:
                # Never fetched yet
                _status_badge(name, "#555", t("status.pending"))
            elif status.ok:
                _status_badge(name, "#22c55e", t("status.ok"))
            elif status.last_error and status.last_success > 0:
                # Has cached data but refresh failed
                age = status.age_seconds
                age_str = _format_age(age)
                _status_badge(
                    name, "#eab308",
                    t("status.stale", age=age_str),
                    tooltip=smart_truncate(status.last_error, 100),
                )
            else:
                # No cached data and error
                _status_badge(
                    name, "#ef4444",
                    t("status.failed"),
                    tooltip=smart_truncate(status.last_error, 100),
                )


def _status_badge(name: str, color: str, label: str, tooltip: str = "") -> None:
    """Render a single status badge."""
    with ui.row().classes("items-center gap-1"):
        ui.html(
            f'<div style="width:8px;height:8px;border-radius:50%;'
            f'background:{color};display:inline-block;"></div>'
        )
        badge_label = ui.label(f"{name}: {label}").classes("text-caption")
        if tooltip:
            badge_label.tooltip(tooltip)


def _format_age(seconds: float) -> str:
    """Format age in seconds to human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.0f}m"
    else:
        return f"{seconds / 3600:.1f}h"


# ── Tab 1: Actions ───────────────────────────────────────────────────────────


def pies_allocation_table(allocations: list[dict], composite) -> None:
    """Render the T212 Pies allocation target table."""
    # ── Donut chart ──────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label(t("pies.chart_title")).classes("text-h6 q-mb-sm")
        from rewired.gui.charts import pies_donut_chart
        pies_donut_chart(allocations)

    with ui.card().classes("w-full"):
        overall = composite.overall_color.value
        hex_color = SIGNAL_COLORS.get(overall, "#888")
        with ui.row().classes("items-center gap-3"):
            ui.label(t("pies.title")).classes("text-h5")
            ui.html(
                f'<span style="color:{hex_color};font-weight:bold">'
                f'{t("pies.signal", color=overall.upper())}</span>'
            )

        columns = [
            {"name": "ticker", "label": t("th.ticker"), "field": "ticker", "align": "left"},
            {"name": "name", "label": t("th.name"), "field": "name", "align": "left"},
            {"name": "layer", "label": t("th.layer"), "field": "layer", "align": "center"},
            {"name": "tier", "label": t("th.tier"), "field": "tier", "align": "center"},
            {"name": "target_pct", "label": t("th.target_pct"), "field": "target_pct", "align": "right"},
            {"name": "target_eur", "label": t("th.target_eur"), "field": "target_eur", "align": "right"},
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
            ui.label(t("pies.allocated", pct=f"{total_alloc:.1f}")).classes("text-bold")
            ui.label(t("pies.cash_reserve", pct=f"{cash_pct:.1f}")).classes("text-bold")


def actions_logic_explainer(composite) -> None:
    """Explain how action conclusions are generated and how to execute them."""
    with ui.card().classes("w-full"):
        overall = composite.overall_color.value if composite else "unknown"
        ui.label(t("actions.how_title")).classes("text-h6")
        ui.markdown(t("actions.how_body"))

        with ui.row().classes("items-center q-mt-sm"):
            ui.label(t("actions.composite_label")).classes("text-bold")
            ui.label(overall.upper()).classes("text-bold")


def actions_playbook(composite, suggestions: list[dict]) -> None:
    """Show what the user should do now based on current signal and actions."""
    with ui.card().classes("w-full"):
        ui.label(t("actions.playbook_title")).classes("text-h6")

        if not composite:
            ui.markdown(t("actions.playbook_nodata"))
            return

        signal = composite.overall_color.value
        guidance_keys = {
            "green": "actions.guidance_green",
            "yellow": "actions.guidance_yellow",
            "orange": "actions.guidance_orange",
            "red": "actions.guidance_red",
        }
        guidance = t(guidance_keys.get(signal, "actions.guidance_yellow"))

        ui.markdown(
            t("actions.signal_posture", color=signal.upper(), guidance=guidance)
            + "\n"
            + t("actions.execution_order")
            + "\n"
            + t("actions.after_trading")
        )

        if not suggestions:
            ui.label(t("actions.no_actions")).classes("text-grey")
            return

        sell_count = sum(1 for s in suggestions if s.get("action") == "SELL")
        buy_count = sum(1 for s in suggestions if s.get("action") == "BUY")
        ui.label(
            t("actions.queue", total=len(suggestions), sell=sell_count, buy=buy_count)
        ).classes("text-bold")


def suggestions_panel(suggestions: list[dict], composite) -> None:
    """Render the suggestions panel with BUY/SELL actions."""
    with ui.card().classes("w-full"):
        ui.label(t("suggest.title")).classes("text-h5 q-mb-md")

        if not suggestions:
            ui.label(t("suggest.balanced")).classes("text-grey")
            return

        phase_labels = {
            1: t("suggest.phase_tp"),
            2: t("suggest.phase_exit"),
            3: t("suggest.phase_buy"),
            4: t("suggest.phase_redist"),
        }

        columns = [
            {"name": "ticker", "label": t("th.ticker"), "field": "ticker", "align": "left"},
            {"name": "action", "label": t("th.action"), "field": "action", "align": "center"},
            {"name": "amount", "label": t("th.amount_eur"), "field": "amount", "align": "right"},
            {"name": "phase", "label": t("th.phase"), "field": "phase", "align": "center"},
            {"name": "reason", "label": t("th.reason"), "field": "reason", "align": "left"},
        ]

        rows = []
        for s in suggestions:
            rows.append({
                "ticker": s["ticker"],
                "action": s["action"],
                "amount": f"{s['amount_eur']:.2f}",
                "phase": phase_labels.get(s.get("priority", 0), "?"),
                "reason": s["reason"],
            })

        ui.table(columns=columns, rows=rows, row_key="ticker").classes("w-full")

        # ── Execute button with confirmation modal ───────────────
        if suggestions:
            _execute_trades_button(suggestions, composite)


def _execute_trades_button(suggestions: list[dict], composite) -> None:
    """Render an Execute button that opens a confirmation modal before sending to IBKR."""

    async def _show_confirm():
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

        with ui.dialog() as dialog, ui.card().classes("min-w-[600px]"):
            ui.label(t("exec.confirm_title")).classes("text-h5 q-mb-sm")

            color = composite.overall_color.value
            hex_c = SIGNAL_COLORS.get(color, "#888")
            ui.html(
                f'<span style="color:{hex_c};font-weight:bold;font-size:1.1em">'
                f'Signal: {color.upper()}</span>'
            )
            if composite.veto_active:
                ui.label("AI HEALTH VETO ACTIVE").classes("text-red font-bold")

            # Order summary table
            cols = [
                {"name": "side", "label": "Side", "field": "side", "align": "center"},
                {"name": "ticker", "label": "Ticker", "field": "ticker", "align": "left"},
                {"name": "amount", "label": "Amount EUR", "field": "amount", "align": "right"},
                {"name": "reason", "label": "Reason", "field": "reason", "align": "left"},
            ]
            rows = []
            for o in orders:
                rows.append({
                    "side": o.side.value,
                    "ticker": o.ticker,
                    "amount": f"{o.amount_eur:,.2f}",
                    "reason": o.reason,
                })
            ui.table(columns=cols, rows=rows, row_key="ticker").classes("w-full q-my-md")

            total_buy = sum(o.amount_eur for o in orders if o.side == OrderSide.BUY)
            total_sell = sum(o.amount_eur for o in orders if o.side == OrderSide.SELL)
            ui.label(f"Total BUY: {total_buy:,.2f} EUR   Total SELL: {total_sell:,.2f} EUR").classes("text-caption")

            result_container = ui.column().classes("w-full gap-2 q-mt-md")

            async def _do_execute():
                result_container.clear()
                with result_container:
                    ui.label(t("exec.sending")).classes("text-grey")
                try:
                    from rewired.broker.ibkr import IBKRBroker
                    brk = IBKRBroker()
                    brk_results = await _run_in_thread(lambda: (brk.connect(), brk.execute_batch(orders))[-1])
                    brk.disconnect()
                    result_container.clear()
                    with result_container:
                        filled = sum(1 for r in brk_results if r.status.value == "filled")
                        ui.label(f"{filled}/{len(brk_results)} orders filled").classes("text-green font-bold")
                        for r in brk_results:
                            color = "green" if r.status.value == "filled" else "red"
                            ui.label(
                                f"{r.side.value} {r.ticker}: {r.status.value.upper()} "
                                f"({r.filled_shares:.4f} shares @ {r.avg_price:.2f})"
                            ).style(f"color:{color}")
                except ImportError:
                    result_container.clear()
                    with result_container:
                        ui.label("ib_insync not installed. Install with: pip install -e \".[broker]\"").classes("text-red")
                except Exception as e:
                    result_container.clear()
                    with result_container:
                        ui.label(f"Broker error: {e}").classes("text-red")

            with ui.row().classes("justify-end gap-3 q-mt-md"):
                ui.button(t("exec.cancel"), on_click=dialog.close).props("flat")
                ui.button(
                    t("exec.confirm_btn"), on_click=_do_execute, icon="send"
                ).props("color=negative")

        dialog.open()

    with ui.row().classes("q-mt-md justify-end"):
        ui.button(
            t("exec.btn_execute"), on_click=_show_confirm, icon="rocket_launch"
        ).props("color=primary outline")


# ── Tab 2: Signals ───────────────────────────────────────────────────────────


def signal_board(composite) -> None:
    """Render the Signal Board card with traffic lights for each category + composite."""
    with ui.card().classes("w-full"):
        ui.label(t("signal.board_title")).classes("text-h5 q-mb-md")

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
                    ui.label(smart_truncate(cat_sig.explanation, 40)).classes(
                        "text-caption text-grey"
                    ).style("max-width:240px;text-align:center")

            # Composite (larger, emphasized)
            overall = composite.overall_color.value
            hex_color = SIGNAL_COLORS.get(overall, "#888")
            with ui.column().classes("items-center"):
                ui.html(
                    f'<div style="width:80px;height:80px;border-radius:50%;'
                    f'background:{hex_color};box-shadow:0 0 25px {hex_color};'
                    f'border:3px solid white;margin:0 auto;"></div>'
                )
                ui.label(t("signal.composite")).classes("text-subtitle1 q-mt-sm").style(
                    "font-weight:bold"
                )
                ui.label(overall.upper()).style(
                    f"color:{hex_color};font-weight:bold;font-size:1.2em"
                )
                ui.label(smart_truncate(composite.summary, 50)).classes(
                    "text-caption text-grey"
                ).style("max-width:300px;text-align:center")


def signal_logic_explainer(composite) -> None:
    """Explain signal model mechanics so users can interpret the board correctly."""
    with ui.card().classes("w-full"):
        ui.label(t("signal.explain_title")).classes("text-h6")
        ui.markdown(t("signal.explain_body"))

        if composite:
            ui.label(
                t("signal.current_summary", summary=composite.summary)
            ).classes("text-caption text-grey")


def signal_drilldown(composite) -> None:
    """Expandable drill-down showing individual readings per signal category."""
    for cat, cat_sig in composite.categories.items():
        label = cat.value.upper().replace("_", " ")
        color = cat_sig.composite_color.value
        hex_color = SIGNAL_COLORS.get(color, "#888")

        with ui.expansion(
            f"{label} -- {color.upper()}",
            icon="circle",
        ).classes("w-full"):
            if not cat_sig.readings:
                ui.label(t("signal.no_readings")).classes("text-grey")
                continue

            columns = [
                {"name": "name", "label": t("th.indicator"), "field": "name", "align": "left"},
                {"name": "value", "label": t("th.value"), "field": "value", "align": "right"},
                {"name": "color", "label": t("th.signal"), "field": "color", "align": "center"},
                {"name": "detail", "label": t("th.detail"), "field": "detail", "align": "left"},
                {"name": "source", "label": t("th.source"), "field": "source", "align": "left"},
            ]

            rows = []
            for r in cat_sig.readings:
                rows.append({
                    "name": r.name,
                    "value": f"{r.value:.2f}",
                    "color": r.color.value.upper(),
                    "detail": smart_truncate(r.detail, 60),
                    "source": r.source,
                })

            ui.table(columns=columns, rows=rows, row_key="name").classes("w-full")


def signal_history_timeline(history: list[dict]) -> None:
    """Render the signal history as a chart + table."""
    # ── ECharts timeline ─────────────────────────────────
    if history:
        with ui.card().classes("w-full"):
            ui.label(t("signal.chart_title")).classes("text-h6 q-mb-sm")
            from rewired.gui.charts import signal_history_chart
            signal_history_chart(history)

    with ui.card().classes("w-full"):
        ui.label(t("signal.history_title")).classes("text-h5 q-mb-md")

        if not history:
            ui.label(t("signal.no_history")).classes("text-grey")
            return

        columns = [
            {"name": "time", "label": t("th.time"), "field": "time", "align": "left"},
            {"name": "from_c", "label": t("th.from"), "field": "from_c", "align": "center"},
            {"name": "to_c", "label": t("th.to"), "field": "to_c", "align": "center"},
            {"name": "summary", "label": t("th.summary"), "field": "summary", "align": "left"},
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


# ── Tab 3: Portfolio ─────────────────────────────────────────────────────────


def portfolio_table(portfolio) -> None:
    """Render portfolio positions with treemap + table."""
    # ── Treemap chart ────────────────────────────────────
    if portfolio and portfolio.positions:
        with ui.card().classes("w-full"):
            ui.label(t("portfolio.treemap_title")).classes("text-h6 q-mb-sm")
            from rewired.gui.charts import portfolio_weight_treemap
            portfolio_weight_treemap(portfolio)

    with ui.card().classes("w-full"):
        ui.label(t("portfolio.title")).classes("text-h5 q-mb-md")

        if not portfolio or not portfolio.positions:
            ui.label(t("portfolio.no_positions")).classes("text-grey")
            _portfolio_summary(portfolio)
            return

        columns = [
            {"name": "ticker", "label": t("th.ticker"), "field": "ticker", "align": "left", "sortable": True},
            {"name": "shares", "label": t("th.shares"), "field": "shares", "align": "right"},
            {"name": "avg_cost", "label": t("th.avg_cost"), "field": "avg_cost", "align": "right"},
            {"name": "current", "label": t("th.current"), "field": "current", "align": "right"},
            {"name": "value", "label": t("th.value_eur"), "field": "value", "align": "right", "sortable": True},
            {"name": "pnl", "label": t("th.pnl_eur"), "field": "pnl", "align": "right", "sortable": True},
            {"name": "weight", "label": t("th.weight_pct"), "field": "weight", "align": "right", "sortable": True},
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
        ui.label(t("portfolio.cash", val=f"{portfolio.cash_eur:.2f}")).classes("text-bold")
        ui.label(t("portfolio.invested", val=f"{portfolio.invested_eur:.2f}")).classes("text-bold")
        ui.label(t("portfolio.total", val=f"{portfolio.total_value_eur:.2f}")).classes("text-bold")


def universe_matrix(universe) -> None:
    """Render the LxT Universe Matrix as a heatmap + table."""
    from rewired.models.universe import Layer, Tier

    # ── Heatmap chart ────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label(t("universe.heatmap_title")).classes("text-h6 q-mb-sm")
        from rewired.gui.charts import lxt_heatmap
        lxt_heatmap(universe)

    with ui.card().classes("w-full"):
        ui.label(t("universe.title")).classes("text-h5 q-mb-md")

        columns = [
            {"name": "layer", "label": t("th.layer"), "field": "layer", "align": "left"},
        ]
        for tier_val in Tier:
            columns.append({
                "name": f"t{tier_val.value}",
                "label": tier_name(tier_val.value),
                "field": f"t{tier_val.value}",
                "align": "center",
            })

        rows = []
        for lyr in Layer:
            row = {"layer": f"L{lyr.value} {layer_name(lyr.value)}"}
            for tier_val in Tier:
                stocks = universe.get_by_coordinate(lyr, tier_val)
                row[f"t{tier_val.value}"] = (
                    ", ".join(s.ticker for s in stocks) if stocks else "-"
                )
            rows.append(row)

        ui.table(columns=columns, rows=rows, row_key="layer").classes("w-full")


# ── Tab 4: Analysis ──────────────────────────────────────────────────────────


def ai_analysis_panel() -> None:
    """Render the AI analysis panel with on-demand Gemini analysis."""
    with ui.card().classes("w-full"):
        ui.label(t("analysis.title")).classes("text-h5 q-mb-md")

        ui.markdown(t("analysis.intro"))

        output_area = ui.markdown(t("analysis.placeholder"))

        async def run_analysis_click():
            output_area.set_content(t("analysis.running"))
            try:
                from rewired.agent.analyst import run_analysis
                result = await _run_in_thread(run_analysis)
                output_area.set_content(result)
            except Exception as e:
                output_area.set_content(t("analysis.error", err=str(e)))

        async def run_regime_click():
            output_area.set_content(t("analysis.running_regime"))
            try:
                from rewired.agent.analyst import market_regime_assessment
                result = await _run_in_thread(market_regime_assessment)
                regime_label = result.regime.upper().replace("_", " ")
                hex_color = REGIME_COLORS.get(result.regime, "#888")
                text = (
                    f"{t('analysis.regime_label')} <span style='color:{hex_color}'>{regime_label}</span> "
                    f"(confidence: {result.confidence:.0%})\n\n"
                    f"{result.reasoning}\n\n"
                    f"{t('analysis.action_label')} {result.actionable_insight}\n\n"
                    f"{t('analysis.risk_label')} {result.key_risk}\n\n"
                    f"{t('analysis.shift_prob')} {result.regime_shift_probability:.0%}"
                )
                output_area.set_content(text)
            except Exception as e:
                output_area.set_content(t("analysis.error", err=str(e)))

        with ui.row().classes("q-mt-sm"):
            ui.button(t("analysis.btn_analysis"), on_click=run_analysis_click, icon="analytics")
            ui.button(t("analysis.btn_regime"), on_click=run_regime_click, icon="assessment")


# ── Tab 3: Portfolio – Trade Recording ────────────────────────────────────────


def trade_recording_form(on_trade_recorded) -> None:
    """Render a form to record BUY/SELL transactions with full validation.

    Non-universe tickers show extra fields (layer, tier, name) to add
    the stock to the universe automatically on first BUY.
    """
    _TICKER_RE = re.compile(r"^[A-Z0-9.]{1,10}$")

    with ui.card().classes("w-full"):
        ui.label(t("trade.title")).classes("text-h5 q-mb-md")
        ui.markdown(t("trade.intro"))

        ticker_input = ui.input(
            t("trade.ticker_label"), placeholder=t("trade.ticker_placeholder"),
        ).classes("w-64")
        action_select = ui.toggle(["BUY", "SELL"], value="BUY").classes("q-mt-sm")
        with ui.row().classes("items-end gap-4"):
            shares_input = ui.number(
                t("trade.shares_label"), value=1.0, min=0.0001, step=0.1, format="%.4f",
            )
            price_input = ui.number(
                t("trade.price_label"), value=0.0, min=0.0, step=0.01, format="%.2f",
            )
        notes_input = ui.input(
            t("trade.notes_label"), placeholder=t("trade.notes_placeholder"),
        ).classes("w-full")

        # ── New-ticker conditional fields (hidden by default) ────────
        new_ticker_container = ui.column().classes("w-full gap-2")
        new_ticker_container.set_visibility(False)
        with new_ticker_container:
            ui.label(t("trade.new_ticker_note")).classes("text-caption text-warning")
            with ui.row().classes("items-end gap-4"):
                stock_name_input = ui.input(
                    t("trade.stock_name_label"),
                    placeholder=t("trade.stock_name_placeholder"),
                ).classes("w-64")
                from rewired.models.universe import Layer, Tier
                layer_select = ui.select(
                    {lyr.value: f"L{lyr.value} {layer_name(lyr.value)}" for lyr in Layer},
                    value=Layer.L3.value,
                    label=t("th.layer"),
                )
                tier_select = ui.select(
                    {tr.value: tier_name(tr.value) for tr in Tier},
                    value=Tier.T3.value,
                    label=t("th.tier"),
                )
                max_weight_input = ui.number(
                    t("trade.max_weight_label"), value=5.0, min=1.0, max=15.0,
                    step=0.5, format="%.1f",
                )

        # Show/hide new-ticker fields based on ticker content
        def _on_ticker_blur(_):
            """Check universe membership when user leaves the ticker field."""
            val = (ticker_input.value or "").strip().upper()
            if not val or not _TICKER_RE.match(val):
                new_ticker_container.set_visibility(False)
                return
            from rewired.models.universe import load_universe
            try:
                uni = load_universe()
                is_known = uni.get_stock(val) is not None
            except Exception:
                is_known = False
            new_ticker_container.set_visibility(not is_known)

        ticker_input.on("blur", _on_ticker_blur)

        feedback = ui.label("").classes("text-caption")

        async def submit_trade():
            # ── Validate inputs ──────────────────────────────────
            ticker_val = (ticker_input.value or "").strip().upper()
            if not ticker_val:
                feedback.set_text(t("trade.err_ticker_required"))
                feedback.style("color:#ef4444")
                return
            if not _TICKER_RE.match(ticker_val):
                feedback.set_text(t("trade.err_ticker_format"))
                feedback.style("color:#ef4444")
                return

            shares_val = shares_input.value or 0
            price_val = price_input.value or 0
            if shares_val <= 0 or price_val <= 0:
                feedback.set_text(t("trade.err_positive"))
                feedback.style("color:#ef4444")
                return
            if price_val > 100_000:
                feedback.set_text(t("trade.err_price_limit"))
                feedback.style("color:#ef4444")
                return

            action_val = action_select.value or "BUY"
            notes_val = (notes_input.value or "").strip()
            if len(notes_val) > 200:
                feedback.set_text(t("trade.err_notes_long"))
                feedback.style("color:#ef4444")
                return

            # SELL validations
            if action_val == "SELL":
                from rewired.portfolio.manager import load_portfolio
                pf_check = await _run_in_thread(load_portfolio)
                pos = pf_check.positions.get(ticker_val) if pf_check else None
                if not pos:
                    feedback.set_text(t("trade.err_sell_no_position", ticker=ticker_val))
                    feedback.style("color:#ef4444")
                    return
                if shares_val > pos.shares + 0.0001:
                    feedback.set_text(t(
                        "trade.err_sell_too_many",
                        shares=f"{shares_val:.4f}",
                        ticker=ticker_val,
                        held=f"{pos.shares:.4f}",
                    ))
                    feedback.style("color:#ef4444")
                    return

            # New-ticker validations
            is_new_ticker = new_ticker_container.visible
            stock_name_val = ""
            layer_val = None
            tier_val = None
            max_weight_val = 5.0
            if is_new_ticker and action_val == "BUY":
                stock_name_val = (stock_name_input.value or "").strip()
                if not stock_name_val:
                    feedback.set_text(t("trade.err_name_required"))
                    feedback.style("color:#ef4444")
                    return
                layer_val = layer_select.value
                tier_val = tier_select.value
                max_weight_val = max_weight_input.value or 5.0

            # ── Confirmation dialog ──────────────────────────────
            total_eur = shares_val * price_val
            confirmed = await _confirm_dialog(
                t("trade.confirm_title"),
                t(
                    "trade.confirm_body",
                    action=action_val,
                    shares=f"{shares_val:.4f}",
                    ticker=ticker_val,
                    price=f"{price_val:.2f}",
                    total=f"{total_eur:.2f}",
                ),
            )
            if not confirmed:
                return

            # ── Execute ──────────────────────────────────────────
            feedback.set_text(t("trade.recording"))
            feedback.style("color:#eab308")

            try:
                def _do_record():
                    from rewired.portfolio.manager import load_portfolio, record_transaction, save_portfolio
                    # Add new ticker to universe if needed
                    if is_new_ticker and action_val == "BUY" and stock_name_val:
                        from rewired.models.universe import Stock, load_universe, save_universe, Layer as Lyr, Tier as Tr
                        uni = load_universe()
                        if uni.get_stock(ticker_val) is None:
                            uni.stocks.append(Stock(
                                ticker=ticker_val,
                                name=stock_name_val,
                                layer=Lyr(layer_val),
                                tier=Tr(tier_val),
                                max_weight_pct=max_weight_val,
                            ))
                            save_universe(uni)

                    pf = load_portfolio()
                    record_transaction(
                        pf,
                        ticker=ticker_val,
                        action=action_val,
                        shares=shares_val,
                        price_eur=price_val,
                        notes=notes_val,
                    )
                    save_portfolio(pf)

                await _run_in_thread(_do_record)

                msg = t(
                    "trade.recorded",
                    action=action_val,
                    shares=f"{shares_val:.4f}",
                    ticker=ticker_val,
                    price=f"{price_val:.2f}",
                )
                if is_new_ticker and action_val == "BUY" and stock_name_val:
                    msg += " " + t(
                        "trade.added_to_universe",
                        ticker=ticker_val,
                        layer=layer_val,
                        tier=tier_val,
                    )
                feedback.set_text(msg)
                feedback.style("color:#22c55e")
                # Reset fields
                ticker_input.set_value("")
                shares_input.set_value(1.0)
                price_input.set_value(0.0)
                notes_input.set_value("")
                new_ticker_container.set_visibility(False)
                # Trigger dashboard refresh
                if on_trade_recorded:
                    await on_trade_recorded()
            except Exception as e:
                feedback.set_text(t("trade.error", err=str(e)))
                feedback.style("color:#ef4444")

        ui.button(t("trade.submit"), on_click=submit_trade, icon="add_circle").props(
            "color=primary"
        ).classes("q-mt-md")


def transaction_history_table(portfolio) -> None:
    """Render the full transaction log."""
    with ui.card().classes("w-full"):
        ui.label(t("txn.title")).classes("text-h5 q-mb-md")

        if not portfolio or not portfolio.transactions:
            ui.label(t("txn.empty")).classes("text-grey")
            return

        columns = [
            {"name": "date", "label": t("th.date"), "field": "date", "align": "left", "sortable": True},
            {"name": "ticker", "label": t("th.ticker"), "field": "ticker", "align": "left"},
            {"name": "action", "label": t("th.action"), "field": "action", "align": "center"},
            {"name": "shares", "label": t("th.shares"), "field": "shares", "align": "right"},
            {"name": "price", "label": t("th.price_eur"), "field": "price", "align": "right"},
            {"name": "total", "label": t("th.total_eur"), "field": "total", "align": "right"},
            {"name": "signal", "label": t("th.signal"), "field": "signal", "align": "center"},
            {"name": "notes", "label": t("th.notes"), "field": "notes", "align": "left"},
        ]

        rows = []
        for i, tx in enumerate(reversed(portfolio.transactions)):
            sig_color = tx.signal_color_at_time.value.upper() if tx.signal_color_at_time else "-"
            rows.append({
                "id": i,
                "date": str(tx.date),
                "ticker": tx.ticker,
                "action": tx.action,
                "shares": f"{tx.shares:.4f}",
                "price": f"{tx.price_eur:.2f}",
                "total": f"{tx.shares * tx.price_eur:.2f}",
                "signal": sig_color,
                "notes": tx.notes or "-",
            })

        ui.table(
            columns=columns, rows=rows, row_key="id", pagination={"rowsPerPage": 15}
        ).classes("w-full")


# ── Monitor Control Panel ────────────────────────────────────────────────────


def monitor_control_panel() -> None:
    """Render a monitor control panel (CLI ``monitor`` equivalent)."""
    with ui.card().classes("w-full"):
        ui.label(t("monitor.title")).classes("text-h5 q-mb-md")
        ui.markdown(t("monitor.intro"))

        with ui.row().classes("items-center gap-4"):
            status_label = ui.label(t("monitor.stopped")).classes("text-bold")
            status_label.style("color:#ef4444")

        ui.markdown(t("monitor.schedule"))

        last_check_label = ui.label("").classes("text-caption text-grey")
        monitor_log = ui.log(max_lines=30).classes("w-full h-48 q-mt-sm")

        # State holder
        _monitor_state = {"timer": None, "running": False, "check_count": 0}

        async def _run_check():
            """Execute a single signal check cycle."""
            from datetime import datetime
            _monitor_state["check_count"] += 1
            n = _monitor_state["check_count"]
            now = datetime.now().strftime("%H:%M:%S")
            monitor_log.push(t("monitor.check_start", time=now, n=n))
            try:
                def _do_check():
                    from rewired.scheduler import check_signals
                    check_signals()
                await _run_in_thread(_do_check)
                now2 = datetime.now().strftime("%H:%M:%S")
                monitor_log.push(t("monitor.check_done", time=now2, n=n))
                last_check_label.set_text(t("monitor.last_check", time=now2))
            except Exception as e:
                monitor_log.push(t("monitor.error", err=str(e)))

        def start_monitor():
            if _monitor_state["running"]:
                return
            _monitor_state["running"] = True
            status_label.set_text(t("monitor.running"))
            status_label.style("color:#22c55e")
            monitor_log.push(t("monitor.started"))
            _monitor_state["timer"] = ui.timer(14400, _run_check)
            ui.timer(0.5, _run_check, once=True)

        def stop_monitor():
            if not _monitor_state["running"]:
                return
            _monitor_state["running"] = False
            status_label.set_text(t("monitor.stopped"))
            status_label.style("color:#ef4444")
            monitor_log.push(t("monitor.stopped_log"))
            if _monitor_state["timer"]:
                _monitor_state["timer"].cancel()
                _monitor_state["timer"] = None

        with ui.row().classes("gap-2 q-mt-sm"):
            ui.button(t("monitor.btn_start"), on_click=start_monitor, icon="play_arrow").props(
                "color=positive"
            )
            ui.button(t("monitor.btn_stop"), on_click=stop_monitor, icon="stop").props(
                "color=negative"
            )
            ui.button(t("monitor.btn_once"), on_click=_run_check, icon="bolt").props(
                "outline"
            )


# ── Data Export ──────────────────────────────────────────────────────────────


def export_panel(get_pies_fn, get_portfolio_fn) -> None:
    """Render data export buttons for portfolio and allocation data."""
    with ui.card().classes("w-full"):
        ui.label(t("export.title")).classes("text-h5 q-mb-md")
        ui.markdown(t("export.intro"))

        feedback = ui.label("").classes("text-caption")

        async def export_portfolio():
            feedback.set_text(t("export.preparing_portfolio"))
            try:
                pf = await _run_in_thread(get_portfolio_fn)
                if not pf:
                    feedback.set_text(t("export.no_portfolio"))
                    return
                content = pf.model_dump_json(indent=2)
                ui.download(content.encode("utf-8"), "portfolio_export.json")
                feedback.set_text(t("export.portfolio_done"))
                feedback.style("color:#22c55e")
            except Exception as e:
                feedback.set_text(t("export.failed", err=str(e)))
                feedback.style("color:#ef4444")

        async def export_pies():
            feedback.set_text(t("export.preparing_pies"))
            try:
                pies = await _run_in_thread(get_pies_fn)
                if not pies:
                    feedback.set_text(t("export.no_pies"))
                    return
                import json as _json
                content = _json.dumps(pies, indent=2)
                ui.download(content.encode("utf-8"), "pies_allocation.json")
                feedback.set_text(t("export.pies_done"))
                feedback.style("color:#22c55e")
            except Exception as e:
                feedback.set_text(t("export.failed", err=str(e)))
                feedback.style("color:#ef4444")

        async def export_pies_csv():
            feedback.set_text(t("export.preparing_csv"))
            try:
                pies = await _run_in_thread(get_pies_fn)
                if not pies:
                    feedback.set_text(t("export.no_pies"))
                    return
                header = "Ticker,Name,Layer,Tier,Target %,Target EUR\n"
                rows = []
                for a in pies:
                    rows.append(
                        f"{a['ticker']},{a['name']},{a['layer']},{a['tier']},"
                        f"{a['target_pct']:.1f},{a['target_eur']:.2f}"
                    )
                content = header + "\n".join(rows)
                ui.download(content.encode("utf-8"), "pies_allocation.csv")
                feedback.set_text(t("export.csv_done"))
                feedback.style("color:#22c55e")
            except Exception as e:
                feedback.set_text(t("export.failed", err=str(e)))
                feedback.style("color:#ef4444")

        with ui.row().classes("gap-2 q-mt-sm"):
            ui.button(t("export.btn_portfolio"), on_click=export_portfolio, icon="download").props("outline")
            ui.button(t("export.btn_pies"), on_click=export_pies, icon="download").props("outline")
            ui.button(t("export.btn_csv"), on_click=export_pies_csv, icon="table_chart").props("outline")


# ── Universe Management ──────────────────────────────────────────────────────


def universe_management_card(on_change=None) -> None:
    """Render a card to view, edit, and remove stocks from the universe.

    Each row has Edit / Remove buttons.  Edit exposes inline Layer, Tier,
    and max-weight inputs.  Removal is blocked when the user holds the stock.
    """
    from rewired.models.universe import Layer, Tier, load_universe

    with ui.card().classes("w-full"):
        ui.label(t("unimgmt.title")).classes("text-h5 q-mb-md")
        ui.markdown(t("unimgmt.intro"))

        try:
            uni = load_universe()
        except Exception:
            return

        feedback = ui.label("").classes("text-caption")

        for stock in sorted(uni.stocks, key=lambda s: (s.layer.value, s.tier.value)):
            with ui.row().classes("items-center gap-3 w-full q-py-xs").style(
                "border-bottom:1px solid rgba(255,255,255,0.08)"
            ):
                ui.label(stock.ticker).classes("text-bold").style("min-width:80px")
                ui.label(stock.name).style("min-width:140px")
                ui.label(f"L{stock.layer.value}").style("min-width:30px")
                ui.label(f"T{stock.tier.value}").style("min-width:30px")
                ui.label(f"{stock.max_weight_pct:.1f}%").style("min-width:60px")

                # ── Edit flow ────────────────────────────────────
                edit_container = ui.column().classes("gap-1")
                edit_container.set_visibility(False)

                def _make_edit(stk=stock, container=edit_container):
                    container.set_visibility(not container.visible)

                ui.button(
                    t("unimgmt.btn_edit"), on_click=_make_edit, icon="edit",
                ).props("flat dense size=sm")

                with edit_container:
                    with ui.row().classes("items-end gap-2"):
                        _elayer = ui.select(
                            {lyr.value: f"L{lyr.value}" for lyr in Layer},
                            value=stock.layer.value,
                            label=t("th.layer"),
                        ).props("dense")
                        _etier = ui.select(
                            {tr.value: f"T{tr.value}" for tr in Tier},
                            value=stock.tier.value,
                            label=t("th.tier"),
                        ).props("dense")
                        _emw = ui.number(
                            t("th.max_weight"), value=stock.max_weight_pct,
                            min=1.0, max=15.0, step=0.5, format="%.1f",
                        ).props("dense").style("width:80px")

                        def _save_edit(
                            stk=stock, lsel=_elayer, tsel=_etier, mwi=_emw, ctr=edit_container,
                        ):
                            from rewired.models.universe import load_universe as _lu, save_universe as _su
                            u = _lu()
                            s = u.get_stock(stk.ticker)
                            if s:
                                s.layer = Layer(lsel.value)
                                s.tier = Tier(tsel.value)
                                s.max_weight_pct = mwi.value or 5.0
                                _su(u)
                            feedback.set_text(t("unimgmt.saved", ticker=stk.ticker))
                            feedback.style("color:#22c55e")
                            ctr.set_visibility(False)

                        ui.button(
                            t("unimgmt.btn_save"), on_click=_save_edit, icon="save",
                        ).props("flat dense size=sm color=primary")

                # ── Remove flow ──────────────────────────────────
                async def _remove(stk=stock):
                    from rewired.portfolio.manager import load_portfolio
                    pf = await _run_in_thread(load_portfolio)
                    if pf and stk.ticker in pf.positions:
                        feedback.set_text(t("unimgmt.held_warning", ticker=stk.ticker))
                        feedback.style("color:#ef4444")
                        return
                    ok = await _confirm_dialog(
                        t("unimgmt.btn_remove"),
                        t("unimgmt.confirm_remove", ticker=stk.ticker),
                    )
                    if not ok:
                        return
                    from rewired.models.universe import load_universe as _lu, save_universe as _su
                    u = _lu()
                    u.stocks = [s for s in u.stocks if s.ticker != stk.ticker]
                    _su(u)
                    feedback.set_text(t("unimgmt.removed", ticker=stk.ticker))
                    feedback.style("color:#22c55e")
                    if on_change:
                        await on_change()

                ui.button(
                    t("unimgmt.btn_remove"), on_click=_remove, icon="delete",
                ).props("flat dense size=sm color=negative")


# ── Tab 6: Evaluation ────────────────────────────────────────────────────────


def evaluation_panel() -> None:
    """Render the per-company evaluation panel with on-demand Gemini evaluation."""
    with ui.card().classes("w-full"):
        ui.label(t("eval.title")).classes("text-h5 q-mb-md")
        ui.markdown(t("eval.intro"))

        eval_output = ui.column().classes("w-full gap-4")

        async def run_single_eval():
            ticker_val = (ticker_in.value or "").strip().upper()
            if not ticker_val:
                return
            eval_output.clear()
            with eval_output:
                ui.label(t("eval.running", ticker=ticker_val)).classes("text-grey")
            try:
                from rewired.agent.evaluator import evaluate_stock_by_ticker
                ev = await _run_in_thread(evaluate_stock_by_ticker, ticker_val)
                eval_output.clear()
                with eval_output:
                    _render_single_evaluation(ev)
            except Exception as e:
                eval_output.clear()
                with eval_output:
                    ui.label(t("eval.error", err=str(e))).classes("text-red")

        async def run_universe_eval():
            eval_output.clear()
            with eval_output:
                ui.label(t("eval.running_all")).classes("text-grey")
            try:
                from rewired.agent.evaluator import evaluate_universe
                batch = await _run_in_thread(evaluate_universe)
                eval_output.clear()
                with eval_output:
                    _render_evaluation_batch(batch)
            except Exception as e:
                eval_output.clear()
                with eval_output:
                    ui.label(t("eval.error", err=str(e))).classes("text-red")

        with ui.row().classes("items-end gap-3 q-mt-sm"):
            ticker_in = ui.input(
                t("eval.ticker_label"), placeholder="NVDA"
            ).classes("w-48")
            ui.button(
                t("eval.btn_single"), on_click=run_single_eval, icon="person_search"
            ).props("color=primary")
            ui.button(
                t("eval.btn_universe"), on_click=run_universe_eval, icon="groups"
            ).props("outline")


def _render_single_evaluation(ev) -> None:
    """Render a single CompanyEvaluation with radar chart + details."""
    from rewired.gui.charts import evaluation_radar_chart

    with ui.row().classes("w-full gap-4 items-start"):
        with ui.column().classes("w-1/2"):
            evaluation_radar_chart(ev, height="300px")
        with ui.column().classes("w-1/2 gap-2"):
            score = ev.composite_score
            if score >= 7.5:
                style = "color:#22c55e"
            elif score >= 5.0:
                style = "color:#eab308"
            elif score >= 3.0:
                style = "color:#f97316"
            else:
                style = "color:#ef4444"

            ui.label(f"{ev.ticker}").classes("text-h5")
            ui.html(f'<span style="{style};font-size:1.5em;font-weight:bold">{ev.composite_score:.1f}/10</span>')
            ui.label(
                f"Fundamental: {ev.fundamental_score:.1f}  |  "
                f"AI-Relevance: {ev.ai_relevance_score:.1f}  |  "
                f"Moat: {ev.moat_score:.1f}  |  "
                f"Management: {ev.management_score:.1f}"
            ).classes("text-caption")
            ui.label(f"Conviction: {ev.conviction_level.upper()}  |  "
                      f"Earnings: {ev.earnings_trend}  |  "
                      f"Data: {ev.data_quality}").classes("text-caption text-grey")

            if not ev.tier_appropriate and ev.suggested_tier_change:
                ui.label(f"Tier mismatch: suggest {ev.suggested_tier_change}").style("color:#f97316")
            if ev.biggest_catalyst:
                ui.html(f'<span style="color:#22c55e">Catalyst:</span> {ev.biggest_catalyst}')
            if ev.biggest_risk:
                ui.html(f'<span style="color:#ef4444">Risk:</span> {ev.biggest_risk}')
            if ev.reasoning:
                ui.label(ev.reasoning).classes("text-caption text-grey q-mt-sm")


def _render_evaluation_batch(batch) -> None:
    """Render a full batch of evaluations with bar chart + table."""
    from rewired.gui.charts import evaluation_bar_chart

    if batch.evaluations:
        evaluation_bar_chart(batch.evaluations, height="380px")

    # Summary table
    columns = [
        {"name": "ticker", "label": "Ticker", "field": "ticker", "align": "left", "sortable": True},
        {"name": "composite", "label": "Score", "field": "composite", "align": "right", "sortable": True},
        {"name": "fundamental", "label": "Fund.", "field": "fundamental", "align": "right"},
        {"name": "ai_rel", "label": "AI-Rel.", "field": "ai_rel", "align": "right"},
        {"name": "moat", "label": "Moat", "field": "moat", "align": "right"},
        {"name": "mgmt", "label": "Mgmt", "field": "mgmt", "align": "right"},
        {"name": "conviction", "label": "Conv.", "field": "conviction", "align": "center"},
        {"name": "trend", "label": "Trend", "field": "trend", "align": "center"},
        {"name": "tier_ok", "label": "Tier OK", "field": "tier_ok", "align": "center"},
    ]

    rows = []
    for ev in sorted(batch.evaluations, key=lambda e: e.composite_score, reverse=True):
        rows.append({
            "ticker": ev.ticker,
            "composite": f"{ev.composite_score:.1f}",
            "fundamental": f"{ev.fundamental_score:.1f}",
            "ai_rel": f"{ev.ai_relevance_score:.1f}",
            "moat": f"{ev.moat_score:.1f}",
            "mgmt": f"{ev.management_score:.1f}",
            "conviction": ev.conviction_level.upper(),
            "trend": ev.earnings_trend,
            "tier_ok": "Yes" if ev.tier_appropriate else ev.suggested_tier_change or "No",
        })

    ui.table(columns=columns, rows=rows, row_key="ticker").classes("w-full q-mt-md")

    if batch.errors:
        ui.label(f"Errors: {', '.join(batch.errors.keys())}").classes("text-caption text-grey q-mt-sm")
    ui.label(
        f"Success rate: {batch.success_rate:.0%} "
        f"({len(batch.evaluations)}/{len(batch.evaluations) + len(batch.errors)})"
    ).classes("text-caption text-grey")

    # Tier mismatches
    mismatches = batch.tier_mismatches()
    if mismatches:
        with ui.card().classes("w-full q-mt-md"):
            ui.label(t("eval.tier_mismatches")).classes("text-h6")
            for ev in mismatches:
                ui.label(f"{ev.ticker}: suggest {ev.suggested_tier_change} \u2014 {ev.reasoning[:80]}").classes("text-caption")


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _confirm_dialog(title: str, body: str) -> bool:
    """Show a modal confirmation dialog and return True if the user confirms."""
    import asyncio
    result: asyncio.Future[bool] = asyncio.get_event_loop().create_future()

    with ui.dialog() as dialog, ui.card():
        ui.label(title).classes("text-h6")
        ui.markdown(body)
        with ui.row().classes("justify-end gap-2 q-mt-sm"):
            ui.button(t("trade.confirm_cancel"), on_click=lambda: (result.set_result(False), dialog.close())).props("flat")
            ui.button(t("trade.confirm_ok"), on_click=lambda: (result.set_result(True), dialog.close())).props("color=primary")

    dialog.open()
    return await result


async def _run_in_thread(func, *args):
    """Run a blocking function in a thread pool to keep UI responsive."""
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)
