"""Reusable NiceGUI component builders for the Rewired Index dashboard."""

from __future__ import annotations

import json
import re

from nicegui import ui

from rewired.gui.i18n import t, smart_truncate, layer_name, tier_name
from rewired.models.signals import SignalCategory

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


# ── Colour-coded status helpers ──────────────────────────────────────────────

_ALL_COLORS = {**SIGNAL_COLORS, **REGIME_COLORS}
def _color_hex(color_value: str) -> str:
    """Return the hex colour for a signal/regime colour name."""
    return _ALL_COLORS.get(color_value.lower().strip(), "#888")


def _colored_status_label(color_value: str, extra_classes: str = "") -> None:
    """Render a NiceGUI label for a signal colour word styled in its matching hex colour."""
    ui.label(color_value.upper()).style(
        f"color:{_color_hex(color_value)};font-weight:bold"
    ).classes(extra_classes)


def _add_color_cell_slot(table, column_name: str, color_field: str | None = None) -> None:
    """Add a body-cell slot to *table* that renders *column_name* in a row-provided colour.

    The previous implementation injected a JS-side object literal into the
    Vue template. NiceGUI's client-side compiler can choke on that when the
    tab is mounted, blanking the entire panel. Using a plain row field keeps
    the template simple and avoids client-side syntax errors.
    """
    color_field = color_field or f"{column_name}_hex"
    table.add_slot(
        f'body-cell-{column_name}',
        r'<q-td :props="props">'
        r'<span :style="{'
        + f"color: props.row.{color_field} || '#888',"
        + r"fontWeight: 'bold'"
        + r'}">'
        '{{ props.value }}'
        '</span>'
        '</q-td>',
    )


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


def market_status_badge() -> None:
    """Render a market open/closed badge for the header."""
    try:
        from rewired.data.market_hours import get_market_status
        status = get_market_status()
    except Exception:
        return

    if status.any_open:
        label = f"LIVE: {', '.join(status.open_exchanges)}"
        color = "#22c55e"
        icon_name = "radio_button_checked"
    else:
        label = "Markets Closed"
        color = "#888"
        icon_name = "pause_circle_outline"

    with ui.row().classes("items-center gap-1"):
        ui.icon(icon_name).style(f"color:{color};font-size:16px")
        ui.label(label).style(
            f"color:{color};font-size:12px;font-weight:600"
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



def action_instructions_panel(allocations: list[dict], composite) -> None:
    """Single consolidated T212 Execution Matrix.

    Layout: Signal Header (huge) → Aggregates → Table → After-trading note.
    """
    _ACTION_COLORS = {"BUY": "#22c55e", "SELL": "#ef4444", "HOLD": "#888"}

    overall = composite.overall_color.value if composite else "unknown"
    hex_color = SIGNAL_COLORS.get(overall, "#888")

    # ── 1. Signal Header (huge) ──────────────────────────
    with ui.card().classes("w-full").style(
        f"border:2px solid {hex_color};border-radius:12px"
    ):
        with ui.row().classes("items-center gap-4"):
            ui.html(
                f'<div style="width:48px;height:48px;border-radius:50%;'
                f'background:{hex_color};box-shadow:0 0 18px {hex_color};'
                f'border:3px solid white;"></div>'
            )
            ui.label(t("actions.instructions_title")).classes("text-h4")
            ui.label(overall.upper()).style(
                f"color:{hex_color};font-weight:bold;font-size:1.8em"
            )

        # Signal posture guidance
        guidance_keys = {
            "green": "actions.guidance_green",
            "yellow": "actions.guidance_yellow",
            "orange": "actions.guidance_orange",
            "red": "actions.guidance_red",
        }
        guidance = t(guidance_keys.get(overall, "actions.guidance_yellow"))
        ui.markdown(
            t("actions.signal_posture", color=overall.upper(), guidance=guidance)
        ).classes("q-mt-xs")

    # ── 1b. Donut chart (live T212 allocation) ───────────
    with ui.card().classes("w-full"):
        ui.label(t("pies.chart_title")).classes("text-h6 q-mb-sm")
        from rewired.gui.charts import pies_donut_chart
        pies_donut_chart(allocations)

    buys = [a for a in allocations if a.get("action") == "BUY"]
    sells = [a for a in allocations if a.get("action") == "SELL"]

    # ── 2. Aggregates ────────────────────────────────────
    buy_total = sum(abs(a.get("delta_eur", 0)) for a in buys)
    sell_total = sum(abs(a.get("delta_eur", 0)) for a in sells)
    net = buy_total - sell_total

    with ui.card().classes("w-full"):
        with ui.row().classes("justify-around flex-wrap gap-4"):
            ui.html(
                f'<span style="color:#22c55e;font-size:1.3em;font-weight:bold">'
                f'BUY: \u20ac{buy_total:,.2f}</span>'
            )
            ui.html(
                f'<span style="color:#ef4444;font-size:1.3em;font-weight:bold">'
                f'SELL: \u20ac{sell_total:,.2f}</span>'
            )
            ui.label(f"Net: \u20ac{net:+,.2f}").classes("text-bold text-h6")
        ui.label(
            t("actions.queue",
              total=len(buys) + len(sells),
              sell=len(sells), buy=len(buys))
        ).classes("text-caption text-grey q-mt-xs")

    # ── 3. T212 Execution Matrix ─────────────────────────
    with ui.card().classes("w-full"):
        if not buys and not sells:
            with ui.row().classes("items-center q-pa-sm"):
                ui.icon("check_circle", color="green").classes("text-h4")
                ui.label(t("actions.no_actions")).classes("text-h6 text-green")
            return

        columns = [
            {"name": "action", "label": t("th.action"), "field": "action", "align": "center", "sortable": True},
            {"name": "ticker", "label": t("th.ticker"), "field": "ticker", "align": "left", "sortable": True},
            {"name": "lxt", "label": "L\u00d7T", "field": "lxt", "align": "center"},
            {"name": "target_pct", "label": t("th.target_pct"), "field": "target_pct", "align": "right"},
            {"name": "current_pct", "label": t("th.current_pct"), "field": "current_pct", "align": "right"},
            {"name": "delta_eur", "label": t("pies.delta_eur"), "field": "delta_eur", "align": "right", "sortable": True},
            {"name": "reason", "label": t("th.reason"), "field": "reason", "align": "left"},
        ]

        # Sort: SELL first (by |delta| desc), then BUY (by |delta| desc)
        _action_order = {"SELL": 0, "BUY": 1, "HOLD": 2}
        sorted_allocs = sorted(
            [a for a in allocations if a.get("action") in ("SELL", "BUY")],
            key=lambda a: (_action_order.get(a.get("action", "HOLD"), 2), -abs(a.get("delta_eur", 0))),
        )

        rows = []
        for idx, a in enumerate(sorted_allocs):
            action = a.get("action", "HOLD")
            delta = a.get("delta_eur", 0)
            rows.append({
                "id": idx,
                "action": action,
                "action_hex": _ACTION_COLORS.get(action, "#888"),
                "ticker": a["ticker"],
                "lxt": f"{a.get('layer', '?')}/{a.get('tier', '?')}",
                "target_pct": f"{a.get('target_pct', 0):.1f}%",
                "current_pct": f"{a.get('current_pct', 0):.1f}%",
                "delta_eur": f"{'+' if delta >= 0 else ''}\u20ac{delta:,.2f}",
                "reason": a.get("reasoning", "") or a.get("reason", ""),
            })

        tbl = ui.table(columns=columns, rows=rows, row_key="id").classes("w-full")
        _add_color_cell_slot(tbl, "action")

        # ── After-trading note ───────────────────────────
        ui.markdown(
            t("actions.execution_order")
            + "\n"
            + t("actions.after_trading")
        ).classes("q-mt-sm text-caption")


def actions_logic_explainer(composite) -> None:
    """Explain how action conclusions are generated and how to execute them."""
    with ui.card().classes("w-full"):
        overall = composite.overall_color.value if composite else "unknown"
        ui.label(t("actions.how_title")).classes("text-h6")
        ui.markdown(t("actions.how_body"))

        with ui.row().classes("items-center q-mt-sm"):
            ui.label(t("actions.composite_label")).classes("text-bold")
            _colored_status_label(overall, "text-bold")


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

        sell_count = sum(1 for s in suggestions if (s.action if hasattr(s, "action") else s.get("action")) == "SELL")
        buy_count = sum(1 for s in suggestions if (s.action if hasattr(s, "action") else s.get("action")) == "BUY")
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
            sd = s.model_dump() if hasattr(s, "model_dump") else s
            rows.append({
                "ticker": sd["ticker"],
                "action": sd["action"],
                "amount": f"{sd['amount_eur']:.2f}",
                "phase": phase_labels.get(sd.get("priority", 0), "?"),
                "reason": sd["reason"],
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
            sd = s.model_dump() if hasattr(s, "model_dump") else s
            orders.append(OrderRequest(
                ticker=sd["ticker"],
                side=OrderSide.BUY if sd["action"] == "BUY" else OrderSide.SELL,
                amount_eur=sd["amount_eur"],
                reason=sd.get("reason", ""),
                priority=sd.get("priority", 0),
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


def _capex_audit_drawer(cat_sig) -> None:
    """3-tier collapsible accordion for CAPEX pipeline transparency.

    Tier 1 — Source Material: raw financial data input, cache status
    Tier 2 — Extracted Evidence: per-company LLM extraction table
    Tier 3 — Mathematical Verdict: computed trend, veto, acceleration
    """
    capex_reading = next(
        (r for r in cat_sig.readings if r.name == "AI CAPEX Health (Agent)"),
        None,
    )
    if capex_reading is None or not capex_reading.metadata:
        return

    meta = capex_reading.metadata
    na = t("audit.data_unavailable")

    with ui.expansion(
        t("audit.title"),
        icon="policy",
    ).classes("w-full q-mt-sm").props("dense"):

        # ── Tier 1: Source Material ───────────────────────────────
        with ui.expansion(
            t("audit.tier1_title"),
            icon="source",
        ).classes("w-full q-mt-xs").props("dense"):
            ui.label(f"{t('audit.cached')}: {meta.get('cached', na)}").classes("text-caption")
            ui.label(f"{t('audit.validated')}: {meta.get('validated', na)}").classes("text-caption")
            raw_fin = meta.get("raw_financial_data", "")
            if raw_fin:
                ui.code(
                    str(raw_fin)[:4000] if len(str(raw_fin)) > 4000 else str(raw_fin),
                    language="text",
                ).classes("w-full")
            else:
                ui.label(na).classes("text-caption text-grey")

        # ── Tier 2: Extracted Evidence ────────────────────────────
        with ui.expansion(
            t("audit.tier2_title"),
            icon="analytics",
        ).classes("w-full q-mt-xs").props("dense"):
            companies = meta.get("companies", {})
            if companies:
                cols = [
                    {"name": "ticker", "label": "Ticker", "field": "ticker", "align": "left"},
                    {"name": "capex_bn", "label": "CapEx ($B)", "field": "capex_bn", "align": "right"},
                    {"name": "qoq", "label": "QoQ %", "field": "qoq", "align": "right"},
                    {"name": "yoy", "label": "YoY %", "field": "yoy", "align": "right"},
                    {"name": "cut", "label": "Cut?", "field": "cut", "align": "center"},
                    {"name": "quote", "label": "Quote", "field": "quote", "align": "left"},
                ]
                rows = []
                for ticker, co in companies.items():
                    rows.append({
                        "ticker": ticker,
                        "capex_bn": f"{co.get('capex_absolute_bn', 0):.2f}" if co.get("capex_absolute_bn") is not None else na,
                        "qoq": f"{co.get('qoq_growth_pct', 0):.1f}" if co.get("qoq_growth_pct") is not None else na,
                        "yoy": f"{co.get('yoy_growth_pct', 0):.1f}" if co.get("yoy_growth_pct") is not None else na,
                        "cut": "YES" if co.get("explicit_guidance_cut_mentioned") else "no",
                        "quote": smart_truncate(co.get("exact_capex_quote", na), 80),
                    })
                ui.table(columns=cols, rows=rows, row_key="ticker").classes("w-full")
            else:
                ui.label(na).classes("text-caption text-grey")

            raw_gemini = meta.get("raw_gemini_response", "")
            if raw_gemini:
                with ui.expansion(
                    "Raw Gemini Response",
                    icon="smart_toy",
                ).classes("w-full q-mt-xs").props("dense"):
                    ui.code(
                        str(raw_gemini)[:6000] if len(str(raw_gemini)) > 6000 else str(raw_gemini),
                        language="json",
                    ).classes("w-full")

        # ── Tier 3: Mathematical Verdict ──────────────────────────
        with ui.expansion(
            t("audit.tier3_title"),
            icon="calculate",
        ).classes("w-full q-mt-xs").props("dense"):
            trend = meta.get("capex_trend", na)
            veto = meta.get("veto_triggered", False)
            key_quote = meta.get("key_management_quote", "")
            trend_color = {
                "accelerating": "#22c55e", "stable": "#eab308",
                "decelerating": "#f97316", "contracting": "#ef4444",
            }.get(trend, "#888")

            ui.label(f"{t('audit.trend')}: {trend.upper()}").classes(
                "text-bold"
            ).style(f"color:{trend_color}")
            ui.label(f"{t('audit.veto')}: {'YES' if veto else 'no'}").classes("text-caption")
            if key_quote:
                ui.label(f"\u201c{key_quote}\u201d").classes("text-caption text-italic q-mt-xs")


def signal_drilldown(composite) -> None:
    """Expandable drill-down showing individual readings per signal category."""
    for cat, cat_sig in composite.categories.items():
        label = cat.value.upper().replace("_", " ")
        color = cat_sig.composite_color.value
        hex_color = SIGNAL_COLORS.get(color, "#888")

        with ui.expansion(
            f"{label} \u2014 {color.upper()}",
            icon="circle",
        ).classes("w-full").style(f"--q-color-primary:{hex_color}"):
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
                    "color_hex": _color_hex(r.color.value),
                    "detail": smart_truncate(r.detail, 60),
                    "source": r.source,
                })

            tbl = ui.table(columns=columns, rows=rows, row_key="name").classes("w-full")
            _add_color_cell_slot(tbl, 'color')

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

            # ── CAPEX Audit Drawer (AI Health only) ───────────────
            if cat == SignalCategory.AI_HEALTH:
                _capex_audit_drawer(cat_sig)

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
            from_color = entry.get("from_color", "?")
            to_color = entry.get("to_color", "?")
            rows.append({
                "time": entry.get("timestamp", "?"),
                "from_c": from_color.upper(),
                "from_c_hex": _color_hex(from_color),
                "to_c": to_color.upper(),
                "to_c_hex": _color_hex(to_color),
                "summary": entry.get("summary", ""),
            })

        tbl = ui.table(columns=columns, rows=rows, row_key="time").classes("w-full")
        _add_color_cell_slot(tbl, 'from_c')
        _add_color_cell_slot(tbl, 'to_c')


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
            {"name": "price_usd", "label": "Price ($)", "field": "price_usd", "align": "right", "sortable": True},
            {"name": "avg_cost", "label": t("th.avg_cost"), "field": "avg_cost", "align": "right"},
            {"name": "value", "label": t("th.value_eur"), "field": "value", "align": "right", "sortable": True},
            {"name": "pnl", "label": t("th.pnl_eur"), "field": "pnl", "align": "right", "sortable": True},
            {"name": "weight", "label": t("th.weight_pct"), "field": "weight", "align": "right", "sortable": True},
            {"name": "in_pie", "label": "In Pie", "field": "in_pie", "align": "center"},
        ]

        rows = []
        for ticker, pos in sorted(portfolio.positions.items()):
            pie_pct = (pos.quantity_in_pies / pos.shares * 100) if pos.shares > 0 else 0.0
            rows.append({
                "ticker": ticker,
                "shares": f"{pos.shares:.4f}",
                "price_usd": f"${pos.current_price_usd:,.2f}",
                "avg_cost": f"\u20ac{pos.avg_cost_eur:.2f}",
                "value": f"\u20ac{pos.market_value_eur:.2f}",
                "pnl": f"{pos.unrealized_pnl_eur:+.2f}",
                "weight": f"{pos.weight_pct:.1f}%",
                "in_pie": f"{pie_pct:.0f}%" if pie_pct > 0 else "-",
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
                    price_usd = enr.get("price_usd", 0.0)
                    price_eur = enr.get("price_eur", 0.0)
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

                            # Price USD (native instrument currency)
                            if price_usd > 0:
                                ui.label(f"${price_usd:,.2f}").style(
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
                            chg_str = f"{change:+.2f}%" if price_usd > 0 else "-"
                            ui.label(chg_str).style(
                                f"min-width:60px;color:{chg_color};font-weight:600"
                            )

                            # Portfolio value (EUR) + weight vs max
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

                            async def _remove(stock=stk):
                                try:
                                    from rewired.data.broker import get_portfolio, is_configured
                                    if is_configured():
                                        pf = await _run_in_thread(get_portfolio)
                                        if pf and stock.ticker in pf.positions:
                                            feedback.set_text(t("unimgmt.held_warning", ticker=stock.ticker))
                                            feedback.style("color:#ef4444")
                                            return
                                except Exception:
                                    pass  # Allow removal if broker unavailable
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


def ai_copilot_panel() -> None:
    """Render the AI Copilot (System Spirit) panel.

    Provides a briefing button, a chat interface for follow-up questions,
    and the regime / raw-data displays.  Conversation history is session-only
    (cleared on page refresh).
    """
    # ── Session-local conversation store ──────────────────────────
    conversation: list[dict[str, str]] = []

    async def _with_timeout(func, *args, timeout_s: int = 90):
        """Run *func* in a thread with a timeout; raise on expiry."""
        import asyncio
        return await asyncio.wait_for(
            _run_in_thread(func, *args), timeout=timeout_s,
        )

    # ── Spirit Briefing card ──────────────────────────────────────
    with ui.card().classes("w-full"):
        ui.label("System Spirit").classes("text-h5 q-mb-sm")
        ui.markdown(
            "Read-only AI Copilot. It can **see** all signals and positions "
            "but has **zero authority** to change them."
        ).classes("text-caption text-grey q-mb-sm")

        briefing_output = ui.markdown("*Click the button below to generate a market briefing.*")

        async def _briefing_click():
            briefing_output.set_content("Generating briefing...")
            elapsed = ui.label("\u231b 0 s").classes("text-caption text-grey")
            _t = {"s": 0, "active": True}

            async def _tick():
                if not _t["active"]:
                    return
                _t["s"] += 1
                try:
                    elapsed.set_text(f"\u231b {_t['s']} s")
                except RuntimeError:
                    _t["active"] = False

            timer = ui.timer(1.0, _tick)
            try:
                from rewired.agent.analyst import generate_briefing
                result = await _with_timeout(generate_briefing, timeout_s=90)
                briefing_output.set_content(result)
                conversation.append({"role": "spirit", "text": result[:500]})
            except TimeoutError:
                briefing_output.set_content(
                    "**\u26a0 Briefing timed out** (> 90 s).  "
                    "Gemini may be overloaded \u2014 please try again later."
                )
            except Exception as e:
                briefing_output.set_content(f"**Error:** {e}")
            finally:
                _t["active"] = False
                timer.cancel()
                try:
                    elapsed.delete()
                except RuntimeError:
                    pass

        with ui.row().classes("q-mt-sm"):
            ui.button("Generate Briefing", on_click=_briefing_click, icon="auto_awesome")

    # ── Chat card ─────────────────────────────────────────────────
    with ui.card().classes("w-full q-mt-sm"):
        ui.label("Ask the Spirit").classes("text-h6 q-mb-sm")

        chat_container = ui.column().classes("w-full gap-2")
        chat_container.style(
            "max-height: 400px; overflow-y: auto; padding: 8px; "
            "border: 1px solid #333; border-radius: 8px; background: #1a1a2e;"
        )

        def _render_bubble(role: str, text: str) -> None:
            """Add a chat bubble to the container."""
            is_user = role == "user"
            align = "items-end" if is_user else "items-start"
            bg = "#2d2d44" if is_user else "#1e3a5f"
            label_text = "You" if is_user else "Spirit"
            with chat_container:
                with ui.column().classes(f"w-full {align}"):
                    with ui.card().style(
                        f"background: {bg}; max-width: 80%; padding: 8px 12px;"
                    ):
                        ui.label(label_text).classes("text-caption text-grey")
                        ui.markdown(text).classes("text-body2")

        with ui.row().classes("w-full q-mt-sm items-end gap-2"):
            chat_input = ui.input(
                placeholder="Ask about signals, portfolio, rules...",
            ).classes("flex-grow").props('outlined dense')

            async def _send():
                question = (chat_input.value or "").strip()
                if not question:
                    return
                chat_input.set_value("")
                conversation.append({"role": "user", "text": question})
                _render_bubble("user", question)

                # Show thinking indicator
                thinking_label = None
                with chat_container:
                    thinking_label = ui.label("Spirit is thinking...").classes(
                        "text-caption text-grey italic"
                    )

                try:
                    from rewired.agent.analyst import ask_followup
                    answer = await _with_timeout(
                        ask_followup, question, list(conversation), timeout_s=90,
                    )
                    conversation.append({"role": "spirit", "text": answer})
                    if thinking_label:
                        thinking_label.delete()
                    _render_bubble("spirit", answer)
                except TimeoutError:
                    if thinking_label:
                        thinking_label.delete()
                    _render_bubble("spirit", "\u26a0 Timed out. Try a shorter question.")
                except Exception as e:
                    if thinking_label:
                        thinking_label.delete()
                    _render_bubble("spirit", f"\u26a0 Error: {e}")

            send_btn = ui.button(icon="send", on_click=_send).props("flat dense color=primary")
            chat_input.on("keydown.enter", _send)

    # ── Regime Assessment card (deterministic, no Gemini) ─────────
    with ui.card().classes("w-full q-mt-sm"):
        ui.label("Regime Assessment").classes("text-h6 q-mb-sm")
        regime_output = ui.markdown("")

        async def _regime_click():
            regime_output.set_content("Computing regime...")
            try:
                from rewired.agent.analyst import market_regime_assessment
                result = await _with_timeout(market_regime_assessment, timeout_s=30)
                regime_label = result.regime.upper().replace("_", " ")
                text = (
                    f"**Regime:** {regime_label} "
                    f"(confidence: {result.confidence:.0%})\n\n"
                    f"{result.reasoning}\n\n"
                    f"**Action:** {result.actionable_insight}\n\n"
                    f"**Key Risk:** {result.key_risk}"
                )
                regime_output.set_content(text)
            except Exception as e:
                regime_output.set_content(f"**Error:** {e}")

        ui.button("Compute Regime", on_click=_regime_click, icon="assessment").props("flat")

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
                            color_val = r.color.value.upper()
                            hex_c = _color_hex(r.color.value)
                            with ui.expansion(
                                f"{r.name} = {r.value:.4f}  [{color_val}]",
                                icon="show_chart",
                            ).classes("w-full").props("dense").style(
                                f"--q-color-primary:{hex_c}"
                            ):
                                ui.label(r.detail).classes("text-caption text-grey")
                                ui.label(f"Source: {r.source}").classes("text-caption")
                                if r.metadata:
                                    ui.code(
                                        json.dumps(r.metadata, indent=2, default=str),
                                        language="json",
                                    ).classes("w-full")

                        # Sentiment data
                        ui.label("SENTIMENT (VIX structure + VXN tech stress)").classes("text-bold text-h6 q-mt-md")
                        for r in sent_readings:
                            color_val = r.color.value.upper()
                            hex_c = _color_hex(r.color.value)
                            with ui.expansion(
                                f"{r.name} = {r.value:.4f}  [{color_val}]",
                                icon="show_chart",
                            ).classes("w-full").props("dense").style(
                                f"--q-color-primary:{hex_c}"
                            ):
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
                    try:
                        from rewired.data.broker import get_portfolio, is_configured
                        if is_configured():
                            pf = await _run_in_thread(get_portfolio)
                            if pf and stk.ticker in pf.positions:
                                feedback.set_text(t("unimgmt.held_warning", ticker=stk.ticker))
                                feedback.style("color:#ef4444")
                                return
                    except Exception:
                        pass  # Allow removal if broker unavailable
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

    Uses FMP profile hydration for name lookup.  Defaults to L4/T3/5%.
    The user only needs to type a ticker.
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


def oracle_gateway_panel() -> None:
    """Oracle JSON Gateway — accept external AI evaluations to manage universe."""
    from rewired.models.universe import (
        Layer, Tier, Stock, load_universe, save_universe,
    )

    _EXAMPLE_SINGLE = """\
{
  "ticker": "NVDA",
  "name": "NVIDIA Corporation",
  "layer": "L1",
  "tier": "T1",
  "max_weight_pct": 15.0,
  "notes": "Dominant AI GPU supplier"
}"""

    _EXAMPLE_BATCH = """\
[
  {
    "ticker": "NVDA",
    "name": "NVIDIA Corporation",
    "layer": "L1",
    "tier": "T1",
    "max_weight_pct": 15.0,
    "notes": "Dominant AI GPU supplier"
  },
  {
    "ticker": "PLTR",
    "name": "Palantir Technologies",
    "layer": "L4",
    "tier": "T3",
    "max_weight_pct": 5.0,
    "notes": "AI analytics platform"
  }
]"""

    _LAYER_MAP = {"L1": Layer.L1, "L2": Layer.L2, "L3": Layer.L3,
                  "L4": Layer.L4, "L5": Layer.L5}
    _TIER_MAP = {"T1": Tier.T1, "T2": Tier.T2, "T3": Tier.T3, "T4": Tier.T4}

    def _strip_fences(text: str) -> str:
        """Strip markdown code fences before JSON parsing."""
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()
        return text

    def _validate_entry(raw: dict) -> tuple[dict | None, str]:
        """Validate a single Oracle entry dict. Returns (clean, error)."""
        import json as _json

        ticker = str(raw.get("ticker", "")).strip().upper()
        if not ticker:
            return None, "Missing required field: ticker"

        name = str(raw.get("name", "")).strip()
        if not name:
            return None, f"{ticker}: Missing required field: name"

        layer_str = str(raw.get("layer", "")).strip().upper()
        if layer_str not in _LAYER_MAP:
            return None, f"{ticker}: Invalid layer '{raw.get('layer')}'. Must be L1-L5."

        tier_str = str(raw.get("tier", "")).strip().upper()
        if tier_str not in _TIER_MAP:
            return None, f"{ticker}: Invalid tier '{raw.get('tier')}'. Must be T1-T4."

        try:
            max_w = float(raw.get("max_weight_pct", 0))
        except (ValueError, TypeError):
            return None, f"{ticker}: max_weight_pct must be a number."
        if not 1.0 <= max_w <= 15.0:
            return None, f"{ticker}: max_weight_pct must be between 1.0 and 15.0 (got {max_w})."

        notes = str(raw.get("notes", "")).strip()

        return {
            "ticker": ticker,
            "name": name,
            "layer": layer_str,
            "tier": tier_str,
            "max_weight_pct": max_w,
            "notes": notes,
        }, ""

    with ui.card().classes("w-full"):
        ui.label("Oracle JSON Gateway").classes("text-h5 q-mb-md")
        ui.markdown(
            "Paste a **JSON object** (single stock) or **JSON array** (batch) "
            "generated by your external AI oracle. The system will validate, "
            "then upsert each entry into `universe.yaml`."
        )

        json_input = ui.textarea(
            label="Paste Oracle JSON here",
            placeholder='{ "ticker": "NVDA", ... }',
        ).classes("w-full font-mono").props("rows=12 outlined")

        result_area = ui.column().classes("w-full gap-2 q-mt-sm")

        async def _submit():
            import json as _json

            raw_text = (json_input.value or "").strip()
            if not raw_text:
                ui.notify("Paste some JSON first.", type="warning")
                return

            result_area.clear()
            cleaned = _strip_fences(raw_text)

            try:
                parsed = _json.loads(cleaned)
            except _json.JSONDecodeError as e:
                with result_area:
                    ui.label(f"JSON parse error: {e}").classes("text-red")
                return

            entries = parsed if isinstance(parsed, list) else [parsed]

            if not entries:
                with result_area:
                    ui.label("Empty JSON array.").classes("text-orange")
                return

            # Validate all entries first
            valid_entries: list[dict] = []
            errors: list[str] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    errors.append(f"Expected object, got {type(entry).__name__}")
                    continue
                clean, err = _validate_entry(entry)
                if err:
                    errors.append(err)
                else:
                    valid_entries.append(clean)

            if errors:
                with result_area:
                    ui.label("Validation errors:").classes("text-red text-bold")
                    for err_msg in errors:
                        ui.label(f"  \u2022 {err_msg}").classes("text-red text-sm")

            if not valid_entries:
                return

            # Apply to universe
            def _apply():
                from datetime import datetime
                uni = load_universe()
                results_log = []
                for entry in valid_entries:
                    existing = uni.get_stock(entry["ticker"])
                    if existing:
                        existing.name = entry["name"]
                        existing.layer = _LAYER_MAP[entry["layer"]]
                        existing.tier = _TIER_MAP[entry["tier"]]
                        existing.max_weight_pct = entry["max_weight_pct"]
                        existing.notes = entry["notes"]
                        existing.last_tier_change = datetime.now()
                        results_log.append(("UPDATED", entry["ticker"], entry))
                    else:
                        stock = Stock(
                            ticker=entry["ticker"],
                            name=entry["name"],
                            layer=_LAYER_MAP[entry["layer"]],
                            tier=_TIER_MAP[entry["tier"]],
                            max_weight_pct=entry["max_weight_pct"],
                            notes=entry["notes"],
                            last_tier_change=datetime.now(),
                        )
                        uni.stocks.append(stock)
                        results_log.append(("ADDED", entry["ticker"], entry))
                save_universe(uni)
                return results_log

            try:
                log = await _run_in_thread(_apply)
            except Exception as exc:
                with result_area:
                    ui.label(f"Save error: {exc}").classes("text-red")
                return

            # Invalidate GUI cache
            try:
                from rewired.gui.state import dashboard_state
                dashboard_state.refresh_all()
            except Exception:
                pass

            with result_area:
                ui.label(f"Successfully processed {len(log)} stock(s):").classes(
                    "text-green text-bold"
                )
                for action, ticker, entry in log:
                    ui.label(
                        f"  {action}: {ticker} \u2192 {entry['layer']}/T{entry['tier'][-1]}  "
                        f"max_weight={entry['max_weight_pct']:.1f}%"
                    ).classes("text-sm")

            ui.notify(f"Oracle: {len(log)} stock(s) processed.", type="positive")

        ui.button(
            "Validate & Submit", on_click=_submit, icon="upload",
        ).props("color=primary").classes("q-mt-sm")

    # Example JSON template
    with ui.card().classes("w-full q-mt-md"):
        ui.label("Example JSON Templates").classes("text-bold text-lg")
        ui.label("Single stock:").classes("text-sm text-grey q-mt-sm")
        ui.code(_EXAMPLE_SINGLE, language="json").classes("w-full")
        ui.label("Batch (array of stocks):").classes("text-sm text-grey q-mt-sm")
        ui.code(_EXAMPLE_BATCH, language="json").classes("w-full")


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
