"""Reusable NiceGUI component builders for the Rewired Index dashboard."""

from __future__ import annotations

import json
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
    """Render the T212 Pies execution matrix with Action column."""
    _ACTION_COLORS = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#888"}

    # ── Donut chart ──────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label(t("pies.chart_title")).classes("text-h6 q-mb-sm")
        from rewired.gui.charts import pies_donut_chart
        pies_donut_chart(allocations)

    with ui.card().classes("w-full").style("border:1px solid rgba(59,130,246,0.3)"):
        overall = composite.overall_color.value
        hex_color = SIGNAL_COLORS.get(overall, "#888")
        with ui.row().classes("items-center gap-3"):
            ui.label(t("pies.exec_title")).classes("text-h5")
            ui.html(
                f'<span style="color:{hex_color};font-weight:bold">'
                f'{t("pies.signal", color=overall.upper())}</span>'
            )

        columns = [
            {"name": "ticker", "label": t("th.ticker"), "field": "ticker", "align": "left", "sortable": True},
            {"name": "name", "label": t("th.name"), "field": "name", "align": "left"},
            {"name": "lxt", "label": "L\u00d7T", "field": "lxt", "align": "center"},
            {"name": "current_pct", "label": t("pies.current_pct"), "field": "current_pct", "align": "right"},
            {"name": "target_pct", "label": t("th.target_pct"), "field": "target_pct", "align": "right"},
            {"name": "target_eur", "label": t("th.target_eur"), "field": "target_eur", "align": "right"},
            {"name": "delta_eur", "label": t("pies.delta_eur"), "field": "delta_eur", "align": "right", "sortable": True},
            {"name": "action", "label": t("pies.action"), "field": "action", "align": "center", "sortable": True},
        ]

        # Sort: SELL first (by |delta|), then BUY (by |delta|), then HOLD
        _action_order = {"SELL": 0, "BUY": 1, "HOLD": 2}
        sorted_allocs = sorted(
            allocations,
            key=lambda a: (_action_order.get(a.get("action", "HOLD"), 2), -abs(a.get("delta_eur", 0))),
        )

        rows = []
        for a in sorted_allocs:
            action = a.get("action", "HOLD")
            delta = a.get("delta_eur", 0)
            action_color = _ACTION_COLORS.get(action, "#888")
            rows.append({
                "ticker": a["ticker"],
                "name": smart_truncate(a["name"], 20),
                "lxt": f"{a['layer']}/{a['tier']}",
                "current_pct": f"{a.get('current_pct', 0):.1f}%",
                "target_pct": f"{a['target_pct']:.1f}%",
                "target_eur": f"\u20ac{a['target_eur']:,.2f}",
                "delta_eur": f"{'+' if delta >= 0 else ''}\u20ac{delta:,.2f}",
                "action": action,
            })

        ui.table(columns=columns, rows=rows, row_key="ticker").classes("w-full")

        # ── Rebalance summary ────────────────────────────────
        buy_total = sum(a.get("delta_eur", 0) for a in allocations
                        if a.get("action") == "BUY")
        sell_total = sum(abs(a.get("delta_eur", 0)) for a in allocations
                         if a.get("action") == "SELL")
        net = buy_total - sell_total

        total_alloc = sum(a["target_pct"] for a in allocations if a["ticker"] != "CASH")
        cash_pct = next(
            (a["target_pct"] for a in allocations if a["ticker"] == "CASH"), 0
        )

        with ui.row().classes("q-mt-sm justify-around flex-wrap"):
            ui.label(t("pies.allocated", pct=f"{total_alloc:.1f}")).classes("text-bold")
            ui.label(t("pies.cash_reserve", pct=f"{cash_pct:.1f}")).classes("text-bold")
            ui.html(
                f'<span style="color:#22c55e">{t("pies.buy_total")}: '
                f'\u20ac{buy_total:,.2f}</span>'
            ).classes("text-bold")
            ui.html(
                f'<span style="color:#ef4444">{t("pies.sell_total")}: '
                f'\u20ac{sell_total:,.2f}</span>'
            ).classes("text-bold")
            ui.label(f'{t("pies.net_rebalance")}: \u20ac{net:+,.2f}').classes("text-bold")

        # ── Sizing logic transparency (D3) ───────────────
        with ui.expansion(
            t("transparency.sizing_logic"),
            icon="data_object",
        ).classes("w-full q-mt-sm").props("dense"):
            for a in sorted_allocs:
                if a["ticker"] == "CASH":
                    continue
                reasoning = a.get("reasoning", "")
                if reasoning:
                    ui.label(f"{a['ticker']}: {reasoning}").classes("text-caption text-grey")



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
                ui.label(t("exec.veto_active")).classes("text-red font-bold")

            # Order summary table
            cols = [
                {"name": "side", "label": t("exec.col_side"), "field": "side", "align": "center"},
                {"name": "ticker", "label": t("exec.col_ticker"), "field": "ticker", "align": "left"},
                {"name": "amount", "label": t("exec.col_amount"), "field": "amount", "align": "right"},
                {"name": "reason", "label": t("exec.col_reason"), "field": "reason", "align": "left"},
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
            ui.label(t("exec.totals", buy=f"{total_buy:,.2f}", sell=f"{total_sell:,.2f}")).classes("text-caption")

            result_container = ui.column().classes("w-full gap-2 q-mt-md")

            async def _do_execute():
                try:
                    result_container.clear()
                except RuntimeError:
                    return
                with result_container:
                    ui.label(t("exec.sending")).classes("text-grey")
                try:
                    from rewired.broker.ibkr import IBKRBroker
                    brk = IBKRBroker()
                    brk_results = await _run_in_thread(lambda: (brk.connect(), brk.execute_batch(orders))[-1])
                    brk.disconnect()
                    try:
                        result_container.clear()
                    except RuntimeError:
                        return
                    with result_container:
                        filled = sum(1 for r in brk_results if r.status.value == "filled")
                        ui.label(t("exec.filled_count", filled=filled, total=len(brk_results))).classes("text-green font-bold")
                        for r in brk_results:
                            color = "green" if r.status.value == "filled" else "red"
                            ui.label(
                                t("exec.order_result",
                                  side=r.side.value, ticker=r.ticker,
                                  status=r.status.value.upper(),
                                  shares=f"{r.filled_shares:.4f}",
                                  price=f"{r.avg_price:.2f}")
                            ).style(f"color:{color}")
                except ImportError:
                    try:
                        result_container.clear()
                    except RuntimeError:
                        return
                    with result_container:
                        ui.label(t("exec.err_no_ibkr")).classes("text-red")
                except Exception as e:
                    try:
                        result_container.clear()
                    except RuntimeError:
                        return
                    with result_container:
                        ui.label(t("exec.err_broker", err=str(e))).classes("text-red")

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

            # ── Transparency: raw metadata accordion ──────────────
            readings_with_meta = [r for r in cat_sig.readings if r.metadata]
            if readings_with_meta:
                with ui.expansion(
                    t("transparency.signal_inputs"),
                    icon="data_object",
                ).classes("w-full q-mt-sm").props("dense"):
                    for r in readings_with_meta:
                        ui.label(r.name).classes("text-bold text-caption q-mt-xs")
                        ui.code(
                            json.dumps(r.metadata, indent=2, default=str),
                            language="json",
                        ).classes("w-full")

    # ── Composite Calculation Transparency ────────────────────────
    transparency = getattr(composite, "composite_transparency", {})
    if transparency:
        with ui.expansion(
            t("transparency.composite_calc"),
            icon="calculate",
        ).classes("w-full q-mt-sm").props("dense"):
            # Show the weighted-average formula
            terms = transparency.get("weighted_terms", {})
            scores = transparency.get("category_scores", {})
            weights = transparency.get("weights", {})
            lines = []
            for cat_name, term_val in terms.items():
                cat_info = scores.get(cat_name, {})
                w = weights.get(cat_name, "?")
                s = cat_info.get("score", "?")
                c = cat_info.get("color", "?").upper()
                lines.append(f"{cat_name.upper()} = {c} (score {s}) \u00d7 {w} = {term_val}")
            weighted_sum = transparency.get("weighted_sum", 0)
            pre_color = transparency.get("pre_override_color", "?").upper()
            override = transparency.get("override_applied", "none")
            final_color = transparency.get("final_color", "?").upper()
            lines.append(f"Weighted sum = {weighted_sum:.4f} \u2192 {pre_color}")
            if override != "none":
                lines.append(f"Override: {override} \u2192 {final_color}")
            else:
                lines.append(f"No override \u2192 {final_color}")
            ui.code("\n".join(lines), language="text").classes("w-full")


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


def interactive_universe_panel(on_change=None, heatmap_data: dict | None = None) -> None:
    """Unified single-pane-of-glass heatmap with live metrics.

    Each cell shows tickers with live EUR prices and portfolio values.
    Clicking a cell opens an expansion panel with full detail rows
    (price, daily change, weight, tier controls, remove).
    Onboarding form at the bottom with autocomplete (when D2 lands).

    A 5-second async timer pushes fresh prices into the chart via
    ECharts ``setOption()`` so the heatmap updates **in-place** without
    a full DOM rebuild.
    """
    from datetime import datetime as _dt
    from rewired.models.universe import Layer, Tier, load_universe, save_universe

    try:
        uni = load_universe()
    except Exception:
        with ui.card().classes("w-full"):
            ui.label(t("universe.load_error")).classes("text-red")
        return

    feedback = ui.label("").classes("text-caption q-mt-sm")

    # Mutable container so the refresh timer can update data for the
    # click-handler closure too.
    _live = {"heatmap_data": heatmap_data}

    # ── Heatmap card ─────────────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label(t("universe.heatmap_title")).classes("text-h6 q-mb-sm")
        ui.label(t("heatmap.click_hint")).classes("text-caption text-grey q-mb-xs")

        if heatmap_data is None:
            # Still fetching live data — skeleton loader
            with ui.column().classes("w-full items-center justify-center").style(
                "height:520px"
            ):
                ui.spinner("dots", size="xl", color="primary")
                ui.label("Loading live market data\u2026").classes(
                    "text-caption text-grey q-mt-sm"
                )
            chart = None
        else:
            from rewired.gui.charts import interactive_lxt_heatmap
            chart = interactive_lxt_heatmap(uni, heatmap_data=heatmap_data, height="520px")

        # "Last updated" timestamp — shown below chart
        _ts_now = _dt.now().strftime("%H:%M:%S")
        updated_ts_label = ui.label(f"\u231a {_ts_now}").classes(
            "text-caption text-grey"
        ).style("margin-top:2px;opacity:0.7")

    # ── 5-second live-refresh timer ──────────────────────────────
    _hm_timer = None  # will be assigned after chart guard

    async def _refresh_heatmap():
        """Push fresh prices into the heatmap via setOption()."""
        try:
            if chart is None:
                return
            if not chart.client.has_socket_connection:
                if _hm_timer:
                    _hm_timer.active = False
                return

            from rewired.gui.state import dashboard_state
            new_data = await _run_in_thread(dashboard_state.get_heatmap_data)
            if not new_data:
                return

            # Update shared state so click handler sees fresh data too
            _live["heatmap_data"] = new_data

            from rewired.gui.charts import build_heatmap_update
            update = build_heatmap_update(uni, new_data)
            chart.run_chart_method(":setOption", update)

            # Refresh timestamp
            updated_ts_label.set_text(
                f"\u231a {_dt.now().strftime('%H:%M:%S')}"
            )
        except Exception:
            # Chart element was deleted (container cleared) — deactivate
            if _hm_timer:
                _hm_timer.active = False

    if chart is not None:
        _hm_timer = ui.timer(5, _refresh_heatmap)

    # ── Cell detail dialog (modal) ──────────────────────────────
    cell_dialog = ui.dialog().props("persistent=false")

    def _show_cell_detail(e):
        """Handle heatmap cell click — open dialog with full stock metrics."""
        try:
            data = e.args if isinstance(e.args, dict) else (e.args[0] if isinstance(e.args, list) else {})
            raw_val = None
            if isinstance(data.get("value"), list):
                raw_val = data["value"]
            elif isinstance(data.get("data"), dict) and isinstance(data["data"].get("value"), list):
                raw_val = data["data"]["value"]
            elif isinstance(data.get("data"), list):
                raw_val = data["data"]
            if not raw_val or len(raw_val) < 2:
                return
            tier_idx = int(raw_val[0])
            layer_idx = int(raw_val[1])
        except (IndexError, TypeError, ValueError, KeyError):
            return

        try:
            sel_layer = Layer(layer_idx + 1)
            sel_tier = Tier(tier_idx + 1)
        except ValueError:
            return

        key = (sel_layer.value, sel_tier.value)
        enriched = _live["heatmap_data"].get(key, []) if _live["heatmap_data"] else []
        stocks_raw = uni.get_by_coordinate(sel_layer, sel_tier)

        try:
            cell_dialog.clear()
        except RuntimeError:
            return

        with cell_dialog, ui.card().style(
            "min-width:560px;max-width:780px;max-height:82vh;"
            "overflow-y:auto;background:#1a1a2e;border:1px solid rgba(255,255,255,0.1)"
        ):
            # Header
            with ui.row().classes("items-center justify-between w-full q-mb-sm"):
                ui.label(
                    f"L{sel_layer.value} / T{sel_tier.value} \u2014 "
                    f"{layer_name(sel_layer.value)} / {tier_name(sel_tier.value)}"
                ).classes("text-h6")
                ui.button(icon="close", on_click=cell_dialog.close).props(
                    "flat dense round size=sm color=grey"
                )

            if not stocks_raw:
                ui.label(t("heatmap.empty_cell")).classes("text-grey q-pa-md")
            else:
                enr_map = {e["ticker"]: e for e in enriched}

                for stk in stocks_raw:
                    enr = enr_map.get(stk.ticker, {})
                    price = enr.get("price_eur", 0.0)
                    change = enr.get("daily_change_pct", 0.0)
                    value = enr.get("portfolio_value_eur", 0.0)
                    weight = enr.get("weight_pct", 0.0)
                    max_w = enr.get("max_weight_pct", stk.max_weight_pct)

                    # P&L accent bar color
                    accent = "#22c55e" if change >= 0 else "#ef4444"

                    with ui.column().classes("w-full q-py-xs gap-1").style(
                        f"border-left:3px solid {accent};"
                        "border-bottom:1px solid rgba(255,255,255,0.06);"
                        "padding-left:10px;margin-bottom:4px"
                    ):
                        with ui.row().classes("items-center w-full gap-3 flex-wrap"):
                            # Ticker + Name
                            ui.label(stk.ticker).classes("text-bold").style(
                                "min-width:60px;font-size:15px"
                            )
                            ui.label(smart_truncate(stk.name, 22)).style(
                                "min-width:110px;color:#aaa;font-size:13px"
                            )

                            # Price EUR
                            if price > 0:
                                ui.label(f"\u20ac{price:,.2f}").style(
                                    "min-width:85px;font-weight:600"
                                )
                            else:
                                with ui.row().classes("items-center gap-1"):
                                    ui.spinner("dots", size="xs")
                                    ui.label("Loading\u2026").style(
                                        "min-width:85px;color:#555;font-size:11px"
                                    )

                            # Daily change
                            chg_color = "#22c55e" if change >= 0 else "#ef4444"
                            chg_str = f"{change:+.2f}%" if price > 0 else "-"
                            ui.label(chg_str).style(
                                f"min-width:60px;color:{chg_color};font-weight:600"
                            )

                            # Portfolio value + weight vs max
                            if value > 0:
                                ui.label(
                                    f"\u20ac{value:,.0f} ({weight:.1f}% / {max_w:.0f}% max)"
                                ).style("min-width:140px;font-size:12px")
                            else:
                                ui.label(t("heatmap.not_held")).style(
                                    "min-width:140px;color:#555;font-size:12px"
                                )

                        # Controls row
                        with ui.row().classes("items-center gap-2 q-mt-xs"):
                            tier_sel = ui.select(
                                {tr.value: f"T{tr.value}" for tr in Tier},
                                value=stk.tier.value,
                                label=t("heatmap.change_tier"),
                            ).props("dense outlined").style("min-width:90px")

                            def _apply_tier(stock=stk, sel=tier_sel):
                                new_tier = Tier(sel.value)
                                if new_tier == stock.tier:
                                    return
                                u = load_universe()
                                s = u.get_stock(stock.ticker)
                                if s:
                                    from datetime import datetime as _dt
                                    s.tier = new_tier
                                    s.last_tier_change = _dt.now()
                                    save_universe(u)
                                    feedback.set_text(
                                        t("heatmap.tier_changed",
                                          ticker=stock.ticker,
                                          old_tier=stock.tier.value,
                                          new_tier=new_tier.value)
                                    )
                                    feedback.style("color:#22c55e")

                            ui.button(icon="save", on_click=_apply_tier).props(
                                "flat dense size=sm color=primary"
                            )

                            async def _reevaluate(stock=stk):
                                feedback.set_text(t("heatmap.reevaluating", ticker=stock.ticker))
                                feedback.style("color:#eab308")
                                try:
                                    from rewired.models.universe import onboard_ticker
                                    updated = await _run_in_thread(onboard_ticker, stock.ticker)
                                    feedback.set_text(
                                        t("heatmap.reevaluated",
                                          ticker=updated.ticker,
                                          layer=updated.layer.value,
                                          tier=updated.tier.value)
                                    )
                                    feedback.style("color:#22c55e")
                                    if on_change:
                                        await on_change()
                                except Exception as exc:
                                    feedback.set_text(f"Re-evaluate failed: {exc}")
                                    feedback.style("color:#ef4444")

                            ui.button(icon="refresh", on_click=_reevaluate).props(
                                "flat dense size=sm color=accent"
                            ).tooltip(t("heatmap.reevaluate"))

                            async def _remove(stock=stk):
                                from rewired.portfolio.manager import load_portfolio
                                pf = await _run_in_thread(load_portfolio)
                                if pf and stock.ticker in pf.positions:
                                    feedback.set_text(t("unimgmt.held_warning", ticker=stock.ticker))
                                    feedback.style("color:#ef4444")
                                    return
                                ok = await _confirm_dialog(
                                    t("unimgmt.btn_remove"),
                                    t("unimgmt.confirm_remove", ticker=stock.ticker),
                                )
                                if not ok:
                                    return
                                u = load_universe()
                                u.stocks = [s for s in u.stocks if s.ticker != stock.ticker]
                                save_universe(u)
                                feedback.set_text(t("unimgmt.removed", ticker=stock.ticker))
                                feedback.style("color:#22c55e")
                                if on_change:
                                    await on_change()

                            ui.button(icon="delete", on_click=_remove).props(
                                "flat dense size=sm color=negative"
                            )

                        # Classification notes
                        notes = (stk.notes or "").strip()
                        if notes:
                            is_defaulted = any(tag in notes.lower() for tag in (
                                "defaulted", "defensive defaults", "gemini unavailable", "gemini error",
                            ))
                            if is_defaulted:
                                ui.html(
                                    f'<span style="background:#f97316;color:#000;padding:2px 6px;'
                                    f'border-radius:3px;font-size:11px;font-weight:bold">'
                                    f'\u26a0 DEFAULTED</span>'
                                    f' <span style="color:#aaa;font-size:11px">{notes}</span>'
                                )
                            else:
                                ui.label(notes).classes("text-caption text-grey").style(
                                    "padding-left:4px"
                                )
                        else:
                            ui.label(t("heatmap.no_classification")).classes(
                                "text-caption"
                            ).style("color:#555;padding-left:4px")

        cell_dialog.open()

    if chart is not None:
        chart.on("click", _show_cell_detail)

    # ── Onboarding (always visible) ──────────────────────────────
    with ui.card().classes("w-full q-mt-sm"):
        ui.label(t("onboard.title")).classes("text-h6 q-mb-sm")
        ui.markdown(t("onboard.intro"))

        with ui.row().classes("items-end gap-3"):
            onboard_input = ticker_input_for_onboard(
                label=t("onboard.ticker_label"),
                placeholder="ARM",
                css_class="w-48",
            )
            onboard_feedback = ui.label("").classes("text-caption")

            async def _do_onboard():
                ticker_val = _extract_ticker(onboard_input.value)
                if not ticker_val:
                    return
                onboard_feedback.set_text(t("onboard.adding", ticker=ticker_val))
                onboard_feedback.style("color:#eab308")
                try:
                    from rewired.models.universe import onboard_ticker
                    stock = await _run_in_thread(onboard_ticker, ticker_val)
                    onboard_feedback.set_text(
                        t("onboard.added",
                          ticker=stock.ticker,
                          name=stock.name,
                          layer=stock.layer.value,
                          tier=stock.tier.value)
                    )
                    onboard_feedback.style("color:#22c55e")
                    onboard_input.set_value("")
                    ui.notify(
                        f"{stock.ticker} -> L{stock.layer.value}/T{stock.tier.value}",
                        type="positive",
                    )
                    if on_change:
                        await on_change()
                except ValueError as exc:
                    onboard_feedback.set_text(str(exc))
                    onboard_feedback.style("color:#ef4444")
                except Exception as exc:
                    onboard_feedback.set_text(t("onboard.err_classify", err=str(exc)))
                    onboard_feedback.style("color:#ef4444")

            ui.button(
                t("onboard.btn_add"), on_click=_do_onboard, icon="add_circle",
            ).props("color=primary")


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

    # ── Raw Source Data Dump (D4) ─────────────────────────────────
    with ui.card().classes("w-full q-mt-sm"):
        with ui.expansion(
            t("analysis.raw_data_title"),
            icon="data_object",
        ).classes("w-full").props("dense"):
            raw_data_area = ui.column().classes("w-full gap-2")

            async def _fetch_raw_data():
                with raw_data_area:
                    raw_data_area.clear()
                    ui.label(t("analysis.raw_data_fetching")).classes("text-caption text-grey")
                try:
                    # Fetch macro + sentiment readings in background
                    def _collect():
                        from rewired.data.macro import get_macro_readings
                        from rewired.data.sentiment import get_sentiment_readings
                        macro = get_macro_readings()
                        sentiment = get_sentiment_readings()
                        return macro, sentiment

                    macro_readings, sent_readings = await _run_in_thread(_collect)

                    raw_data_area.clear()
                    with raw_data_area:
                        # Macro data
                        ui.label("MACRO (FRED)").classes("text-bold text-h6 q-mt-sm")
                        for r in macro_readings:
                            with ui.expansion(
                                f"{r.name} = {r.value:.4f}  [{r.color.value.upper()}]",
                                icon="show_chart",
                            ).classes("w-full").props("dense"):
                                ui.label(r.detail).classes("text-caption text-grey")
                                ui.label(f"Source: {r.source}").classes("text-caption")
                                if r.metadata:
                                    ui.code(
                                        json.dumps(r.metadata, indent=2, default=str),
                                        language="json",
                                    ).classes("w-full")

                        # Sentiment data
                        ui.label("SENTIMENT (VIX / yfinance)").classes("text-bold text-h6 q-mt-md")
                        for r in sent_readings:
                            with ui.expansion(
                                f"{r.name} = {r.value:.4f}  [{r.color.value.upper()}]",
                                icon="show_chart",
                            ).classes("w-full").props("dense"):
                                ui.label(r.detail).classes("text-caption text-grey")
                                ui.label(f"Source: {r.source}").classes("text-caption")
                                if r.metadata:
                                    ui.code(
                                        json.dumps(r.metadata, indent=2, default=str),
                                        language="json",
                                    ).classes("w-full")

                except Exception as exc:
                    raw_data_area.clear()
                    with raw_data_area:
                        ui.label(f"Error fetching raw data: {exc}").classes("text-red")

            ui.button(
                t("analysis.raw_data_fetch_btn"), on_click=_fetch_raw_data, icon="download",
            ).props("flat color=grey")


# ── Ticker input widgets (context-specific) ───────────────────────────────────


def _extract_ticker(value) -> str:
    """Extract a clean ticker symbol from a ui.select value.

    Handles both plain ticker strings and display strings like
    ``"PLTR — Palantir Technologies [New]"``.
    """
    raw = (str(value) if value else "").strip()
    if " — " in raw:
        raw = raw.split(" — ", 1)[0].strip()
    return raw.upper()


def ticker_input_for_onboard(
    *,
    label: str = "",
    placeholder: str = "ARM",
    css_class: str = "w-48",
) -> ui.select:
    """Ticker input for the **Add Stock** panel.

    Starts **empty** — no universe pre-population.  On typing, queries FMP
    to find real tickers.  Stocks already in the universe are flagged
    (not selectable as new).
    """
    from rewired.models.universe import load_universe

    _universe_tickers: set[str] = set()
    try:
        _universe_tickers = {s.ticker for s in load_universe().stocks}
    except Exception:
        pass

    sel = ui.select(
        options={},
        with_input=True,
        label=label or t("onboard.ticker_label"),
        value=None,
        clearable=True,
        new_value_mode="add-unique",
    ).classes(css_class).props(f'placeholder="{placeholder}" dense outlined input-debounce="300"')

    async def _on_filter(e):
        query = (e.args or "").strip() if hasattr(e, "args") else ""
        if not query or len(query) < 2:
            return
        try:
            from rewired.data.fmp import search_ticker
            results = await _run_in_thread(search_ticker, query.upper(), 8)
            new_opts: dict[str, str] = {}
            for item in results:
                sym = (item.get("symbol") or "").upper()
                name = item.get("name", sym)
                if not sym:
                    continue
                if sym in _universe_tickers:
                    new_opts[sym] = f"{sym} — {name}  [{t('onboard.err_exists')}]"
                else:
                    new_opts[sym] = f"{sym} — {name}"
            sel.options = new_opts
            sel.update()
        except Exception:
            pass

    sel.on("input-value", _on_filter)
    return sel


def ticker_input_for_trade(
    *,
    label: str = "",
    placeholder: str = "NVDA",
    on_select=None,
    css_class: str = "w-64",
) -> ui.select:
    """Ticker dropdown for the **Record a Trade** panel.

    Pre-populated from the universe (fuzzy match).  Unknown tickers typed
    by the user trigger an FMP search and are tagged for auto-onboard.
    """
    from rewired.models.universe import load_universe

    options: dict[str, str] = {}
    try:
        uni = load_universe()
        for s in uni.stocks:
            options[s.ticker] = f"{s.ticker} — {s.name}"
    except Exception:
        pass

    sel = ui.select(
        options=options,
        with_input=True,
        label=label or t("autocomplete.placeholder"),
        value=None,
        clearable=True,
        new_value_mode="add-unique",
    ).classes(css_class).props(f'placeholder="{placeholder}" dense outlined input-debounce="300"')

    async def _on_filter(e):
        query = (e.args or "").strip() if hasattr(e, "args") else ""
        if not query or len(query) < 2:
            return
        q_upper = query.upper()
        if q_upper in options:
            return
        try:
            from rewired.data.fmp import search_ticker
            results = await _run_in_thread(search_ticker, q_upper, 5)
            new_opts = dict(options)
            for item in results:
                sym = (item.get("symbol") or "").upper()
                name = item.get("name", sym)
                if sym and sym not in new_opts:
                    badge = t("autocomplete.new_badge")
                    new_opts[sym] = f"{sym} — {name}  {badge}"
            sel.options = new_opts
            sel.update()
        except Exception:
            pass

    sel.on("input-value", _on_filter)

    if on_select:
        sel.on("update:model-value", lambda e: on_select(e.args if hasattr(e, "args") else sel.value))

    return sel


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

        ticker_input = ticker_input_for_trade(
            label=t("trade.ticker_label"),
            placeholder=t("trade.ticker_placeholder"),
        )
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
        def _on_ticker_change(_):
            """Check universe membership when ticker is selected.

            For unknown tickers, trigger FMP + Gemini auto-classification to
            pre-populate the Layer/Tier fields.
            """
            val = _extract_ticker(ticker_input.value)
            if not val:
                new_ticker_container.set_visibility(False)
                return
            from rewired.models.universe import load_universe
            try:
                uni = load_universe()
                is_known = uni.get_stock(val) is not None
            except Exception:
                is_known = False
            new_ticker_container.set_visibility(not is_known)

            # Auto-classify unknown tickers via FMP + Gemini
            if not is_known:
                async def _auto_classify():
                    try:
                        def _classify():
                            import json as _json
                            from rewired.data.fmp import get_profile
                            profile = get_profile(val)
                            if not profile:
                                return None
                            name = profile.get("companyName", val)
                            sector = profile.get("sector", "Unknown")
                            industry = profile.get("industry", "Unknown")
                            mkt = profile.get("mktCap", 0)
                            desc = (profile.get("description") or "")[:500]
                            result = {"name": name, "layer": 4, "tier": 3, "max_weight": 5.0}
                            try:
                                from rewired.agent.gemini import generate, is_configured as gc
                                from rewired.agent.prompts import COMPANY_CLASSIFY, SYSTEM_CLASSIFIER
                                if gc():
                                    fmt_cap = f"${mkt / 1e9:.1f}B" if mkt and mkt > 0 else "N/A"
                                    prompt = COMPANY_CLASSIFY.format(
                                        ticker=val, name=name, sector=sector,
                                        industry=industry, market_cap=fmt_cap,
                                        description=desc,
                                    )
                                    raw = generate(prompt, system_instruction=SYSTEM_CLASSIFIER, json_output=True, max_retries=2)
                                    text = raw.strip()
                                    if text.startswith("```"):
                                        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                                    if text.endswith("```"):
                                        text = text[:-3]
                                    text = text.strip()
                                    if text.startswith("json"):
                                        text = text[4:].strip()
                                    data = _json.loads(text)
                                    from rewired.models.universe import Layer as _L, Tier as _T
                                    l_str = str(data.get("layer", "L4")).upper().strip()
                                    t_str = str(data.get("tier", "T3")).upper().strip()
                                    result["layer"] = _L[l_str].value if l_str in _L.__members__ else 4
                                    result["tier"] = _T[t_str].value if t_str in _T.__members__ else 3
                                    result["max_weight"] = max(1.0, min(15.0, float(data.get("max_weight_pct", 5.0))))
                            except Exception:
                                pass
                            return result
                        info = await _run_in_thread(_classify)
                        if info:
                            stock_name_input.set_value(info["name"])
                            layer_select.set_value(info["layer"])
                            tier_select.set_value(info["tier"])
                            max_weight_input.set_value(info["max_weight"])
                    except Exception:
                        pass
                import asyncio
                asyncio.ensure_future(_auto_classify())

        ticker_input.on("update:model-value", _on_ticker_change)

        feedback = ui.label("").classes("text-caption")

        async def submit_trade():
            # ── Validate inputs ──────────────────────────────────
            ticker_val = _extract_ticker(ticker_input.value)
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


def universe_onboarding_card(on_change=None) -> None:
    """Standalone card to add a stock to the universe by ticker only.

    Uses FMP profile hydration + Gemini COMPANY_CLASSIFY for automatic
    Layer/Tier assignment.  The user only needs to type a ticker.
    """
    with ui.card().classes("w-full"):
        ui.label(t("onboard.title")).classes("text-h5 q-mb-md")
        ui.markdown(t("onboard.intro"))

        with ui.row().classes("items-end gap-3"):
            onboard_input = ui.input(
                t("onboard.ticker_label"), placeholder="PLTR",
            ).classes("w-48")

            onboard_feedback = ui.label("").classes("text-caption")

            async def _do_onboard():
                ticker_val = (onboard_input.value or "").strip().upper()
                if not ticker_val:
                    return
                onboard_feedback.set_text(t("onboard.adding", ticker=ticker_val))
                onboard_feedback.style("color:#eab308")
                try:
                    from rewired.models.universe import onboard_ticker
                    stock = await _run_in_thread(onboard_ticker, ticker_val)
                    onboard_feedback.set_text(
                        t("onboard.added",
                          ticker=stock.ticker,
                          name=stock.name,
                          layer=stock.layer.value,
                          tier=stock.tier.value)
                    )
                    onboard_feedback.style("color:#22c55e")
                    onboard_input.set_value("")
                    ui.notify(
                        f"{stock.ticker} \u2192 L{stock.layer.value}/T{stock.tier.value}",
                        type="positive",
                    )
                    if on_change:
                        await on_change()
                except ValueError as e:
                    onboard_feedback.set_text(str(e))
                    onboard_feedback.style("color:#ef4444")
                    ui.notify(str(e), type="negative")
                except Exception as e:
                    onboard_feedback.set_text(t("onboard.err_classify", err=str(e)))
                    onboard_feedback.style("color:#ef4444")

            ui.button(
                t("onboard.btn_add"), on_click=_do_onboard, icon="add_circle",
            ).props("color=primary")


# ── Tab 6: Evaluation ────────────────────────────────────────────────────────


def evaluation_panel() -> None:
    """Render the per-company evaluation panel with on-demand Gemini evaluation."""
    with ui.card().classes("w-full"):
        ui.label(t("eval.title")).classes("text-h5 q-mb-md")
        ui.markdown(t("eval.intro"))

        eval_output = ui.column().classes("w-full gap-4")

        def _eval_clear() -> bool:
            """Safely clear eval_output; returns False if client gone."""
            try:
                eval_output.clear()
                return True
            except RuntimeError:
                return False

        async def run_single_eval():
            ticker_val = (ticker_in.value or "").strip().upper()
            if not ticker_val:
                return
            if not _eval_clear():
                return
            with eval_output:
                ui.label(t("eval.running", ticker=ticker_val)).classes("text-grey")
            try:
                from rewired.agent.evaluator import evaluate_stock_by_ticker
                ev = await _run_in_thread(evaluate_stock_by_ticker, ticker_val)
                if not _eval_clear():
                    return
                with eval_output:
                    _render_single_evaluation(ev)
            except Exception as e:
                if not _eval_clear():
                    return
                with eval_output:
                    ui.label(t("eval.error", err=str(e))).classes("text-red")

        async def run_universe_eval():
            if not _eval_clear():
                return
            with eval_output:
                ui.label(t("eval.running_all")).classes("text-grey")
            try:
                from rewired.agent.evaluator import evaluate_universe
                batch = await _run_in_thread(evaluate_universe)
                if not _eval_clear():
                    return
                with eval_output:
                    _render_evaluation_batch(batch)
            except Exception as e:
                if not _eval_clear():
                    return
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
            if hasattr(ev, 'in_universe') and not ev.in_universe:
                ui.label(t("eval.not_in_universe")).classes("text-caption text-orange q-ml-sm")
            ui.html(f'<span style="{style};font-size:1.5em;font-weight:bold">{ev.composite_score:.1f}/10</span>')
            ui.label(
                f"{t('eval.score_fundamental')}: {ev.fundamental_score:.1f}  |  "
                f"{t('eval.score_ai_rel')}: {ev.ai_relevance_score:.1f}  |  "
                f"{t('eval.score_moat')}: {ev.moat_score:.1f}  |  "
                f"{t('eval.score_mgmt')}: {ev.management_score:.1f}"
            ).classes("text-caption")
            ui.label(f"{t('eval.conviction_label')}: {ev.conviction_level.upper()}  |  "
                      f"{t('eval.earnings_label')}: {ev.earnings_trend}  |  "
                      f"{t('eval.data_quality_label')}: {ev.data_quality}").classes("text-caption text-grey")

            if not ev.tier_appropriate and ev.suggested_tier_change:
                ui.label(t("eval.tier_mismatch", tier=ev.suggested_tier_change)).style("color:#f97316")
            if ev.biggest_catalyst:
                ui.html(f'<span style="color:#22c55e">{t("eval.catalyst_label")}:</span> {ev.biggest_catalyst}')
            if ev.biggest_risk:
                ui.html(f'<span style="color:#ef4444">{t("eval.risk_label")}:</span> {ev.biggest_risk}')
            if ev.reasoning:
                ui.label(ev.reasoning).classes("text-caption text-grey q-mt-sm")

    # ── Transparency: raw input data accordion ────────────────────
    if ev.metadata:
        with ui.expansion(
            t("transparency.raw_data"),
            icon="data_object",
        ).classes("w-full q-mt-sm").props("dense"):
            if ev.metadata.get("financial_data"):
                with ui.expansion(t("transparency.fmp_data"), icon="account_balance").classes("w-full").props("dense"):
                    ui.code(ev.metadata["financial_data"]).classes("w-full")
            if ev.metadata.get("earnings_data"):
                with ui.expansion(t("transparency.earnings_data"), icon="trending_up").classes("w-full").props("dense"):
                    ui.code(ev.metadata["earnings_data"]).classes("w-full")
            if ev.metadata.get("metrics_data"):
                with ui.expansion(t("transparency.metrics_data"), icon="analytics").classes("w-full").props("dense"):
                    ui.code(ev.metadata["metrics_data"]).classes("w-full")
            if ev.metadata.get("prompt_sent"):
                with ui.expansion(t("transparency.prompt"), icon="psychology").classes("w-full").props("dense"):
                    ui.code(ev.metadata["prompt_sent"]).classes("w-full")
            if ev.metadata.get("raw_gemini_response"):
                with ui.expansion(t("transparency.gemini_response"), icon="smart_toy").classes("w-full").props("dense"):
                    ui.code(ev.metadata["raw_gemini_response"]).classes("w-full")


def _render_evaluation_batch(batch) -> None:
    """Render a full batch of evaluations with bar chart + table."""
    from rewired.gui.charts import evaluation_bar_chart

    if batch.evaluations:
        evaluation_bar_chart(batch.evaluations, height="380px")

    # Summary table
    columns = [
        {"name": "ticker", "label": t("eval.col_ticker"), "field": "ticker", "align": "left", "sortable": True},
        {"name": "composite", "label": t("eval.col_score"), "field": "composite", "align": "right", "sortable": True},
        {"name": "fundamental", "label": t("eval.col_fund"), "field": "fundamental", "align": "right"},
        {"name": "ai_rel", "label": t("eval.col_ai_rel"), "field": "ai_rel", "align": "right"},
        {"name": "moat", "label": t("eval.col_moat"), "field": "moat", "align": "right"},
        {"name": "mgmt", "label": t("eval.col_mgmt"), "field": "mgmt", "align": "right"},
        {"name": "conviction", "label": t("eval.col_conviction"), "field": "conviction", "align": "center"},
        {"name": "trend", "label": t("eval.col_trend"), "field": "trend", "align": "center"},
        {"name": "tier_ok", "label": t("eval.col_tier_ok"), "field": "tier_ok", "align": "center"},
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
            "tier_ok": t("eval.yes") if ev.tier_appropriate else ev.suggested_tier_change or t("eval.no"),
        })

    ui.table(columns=columns, rows=rows, row_key="ticker").classes("w-full q-mt-md")

    if batch.errors:
        ui.label(t("eval.errors", tickers=", ".join(batch.errors.keys()))).classes("text-caption text-grey q-mt-sm")
    ui.label(
        t("eval.success_rate",
          rate=f"{batch.success_rate:.0%}",
          ok=len(batch.evaluations),
          total=len(batch.evaluations) + len(batch.errors))
    ).classes("text-caption text-grey")

    # Tier mismatches
    mismatches = batch.tier_mismatches()
    if mismatches:
        with ui.card().classes("w-full q-mt-md"):
            ui.label(t("eval.tier_mismatches")).classes("text-h6")
            for ev in mismatches:
                ui.label(f"{ev.ticker}: {t('eval.tier_mismatch', tier=ev.suggested_tier_change)} \u2014 {ev.reasoning[:80]}").classes("text-caption")


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
