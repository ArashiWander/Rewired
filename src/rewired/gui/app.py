"""Rewired Index NiceGUI dashboard application.

Tab-based layout with persistent signal header:
- Header: title, composite signal indicator, data status badges, refresh button
- Tab 1 (Actions): Pies allocation + suggestions (default, most actionable)
- Tab 2 (Signals): Traffic lights, drill-down readings, history
- Tab 3 (Portfolio): Positions table, trade recording, transaction history, universe matrix
- Tab 4 (AI Copilot): System Spirit chat and briefings
- Tab 5 (Monitor): Background signal monitor, data export
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import datetime

from nicegui import ui

from rewired.gui.i18n import Lang, get_language, set_language, t
from rewired.gui.state import dashboard_state
from rewired.gui import components

logger = logging.getLogger(__name__)

# Maximum seconds to wait for a single data source before giving up.
_DATA_FETCH_TIMEOUT = 45

# ── Windows asyncio transport-error suppression ──────────────────────────────

_BENIGN_HANDLE_KEYWORDS = (
    "_ProactorBasePipeTransport",
    "_call_connection_lost",
)


def _is_benign_windows_asyncio_transport_error(context: dict) -> bool:
    """Return True if *context* is a harmless Windows proactor transport error.

    On Windows the ProactorEventLoop occasionally fires spurious
    ``ConnectionResetError [WinError 10054]`` exceptions inside its
    internal transport callbacks after a client disconnects.  These are
    benign and should be silently suppressed.
    """
    if sys.platform != "win32":
        return False

    exc = context.get("exception")
    if not isinstance(exc, (ConnectionResetError, OSError)):
        return False

    handle_str = str(context.get("handle", ""))
    return all(kw in handle_str for kw in _BENIGN_HANDLE_KEYWORDS)


def _build_gui_exception_handler(default_handler):
    """Return an asyncio exception handler that filters benign Windows errors."""

    def handler(loop, context):
        if _is_benign_windows_asyncio_transport_error(context):
            logger.debug("Suppressed benign Windows transport error: %s", context.get("exception"))
            return
        # Delegate everything else to the original handler.
        default_handler(loop, context)

    return handler


def _build_dashboard() -> None:
    """Build the tab-based dashboard layout."""

    @ui.page("/")
    def index():
        ui.dark_mode().enable()
        populate_lock = asyncio.Lock()

        # ── Persistent Header ────────────────────────────────────────
        with ui.header().classes("items-center justify-between"):
            ui.label(t("app.title")).classes("text-h4").style("font-weight:bold")

            # Signal indicator (updated after data loads)
            signal_indicator_container = ui.row().classes("items-center gap-2")

            # Status badges
            status_badge_container = ui.row().classes("items-center gap-2")

            with ui.row().classes("items-center gap-3"):
                updated_label = ui.label("").classes("text-caption text-grey")
                refresh_btn = ui.button(
                    t("app.refresh"),
                    on_click=lambda: refresh_dashboard(),
                    icon="refresh",
                ).props("flat color=white dense")

                # ── Language toggle ───────────────────────────────
                def _on_lang_change(e):
                    lang = Lang.ZH if e.value == "中文" else Lang.EN
                    set_language(lang)
                    ui.navigate.reload()

                ui.toggle(
                    ["EN", "中文"],
                    value="中文" if get_language() == Lang.ZH else "EN",
                    on_change=_on_lang_change,
                ).props("dense flat color=white text-color=white").classes("q-ml-sm")

        # ── Tab Navigation ───────────────────────────────────────────
        with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-0"):
            with ui.tabs().classes("w-full") as tabs:
                actions_tab = ui.tab(t("tab.actions"), icon="checklist")
                signals_tab = ui.tab(t("tab.signals"), icon="traffic")
                portfolio_tab = ui.tab(t("tab.portfolio"), icon="account_balance_wallet")
                analysis_tab = ui.tab("AI Copilot", icon="smart_toy")
                evaluation_tab = ui.tab("Oracle Gateway", icon="cloud_upload")
                monitor_tab = ui.tab(t("tab.monitor"), icon="monitor_heart")

            with ui.tab_panels(tabs, value=actions_tab).classes("w-full"):

                # ── Tab 1: Actions ───────────────────────────────
                with ui.tab_panel(actions_tab):
                    actions_container = ui.column().classes("w-full gap-4")

                # ── Tab 2: Signals ───────────────────────────────
                with ui.tab_panel(signals_tab):
                    signals_container = ui.column().classes("w-full gap-4")

                # ── Tab 3: Portfolio ─────────────────────────────
                with ui.tab_panel(portfolio_tab):
                    portfolio_container = ui.column().classes("w-full gap-4")

                # ── Tab 4: Analysis ──────────────────────────────
                with ui.tab_panel(analysis_tab):
                    analysis_container = ui.column().classes("w-full gap-4")

                # ── Tab 5: Evaluation ────────────────────────────
                with ui.tab_panel(evaluation_tab):
                    evaluation_container = ui.column().classes("w-full gap-4")

                # ── Tab 6: Monitor ───────────────────────────────
                with ui.tab_panel(monitor_tab):
                    monitor_container = ui.column().classes("w-full gap-4")

        # ── Data Loading & Rendering ─────────────────────────────────

        async def refresh_dashboard():
            """Force refresh all data and rebuild."""
            updated_label.set_text(t("app.refreshing"))
            dashboard_state.refresh_all()
            await populate()

        async def refresh_after_trade():
            """Refresh portfolio-related caches only (skip signal re-fetch)."""
            updated_label.set_text(t("app.refreshing"))
            dashboard_state.refresh_portfolio_related()
            await populate()

        async def refresh_after_universe_change():
            """Refresh universe-related caches only (skip signal re-fetch)."""
            updated_label.set_text(t("app.refreshing"))
            dashboard_state.refresh_universe_related()
            await populate()

        def _is_connected() -> bool:
            """Check if the client WebSocket is still alive."""
            try:
                return signal_indicator_container.client.has_socket_connection
            except Exception:
                return False

        def _try_clear(container) -> bool:
            """Clear a UI container, returning True on success.

            Unlike the old ``_safe_clear`` this is used inside per-section
            try/except blocks so a failure here does NOT abort the whole
            populate — only the current section.
            """
            try:
                if not container.client.has_socket_connection:
                    return False
                container.clear()
                return True
            except (RuntimeError, Exception):
                return False

        async def populate():
            """Populate all tabs with current data."""
            if not _is_connected():
                return

            async with populate_lock:
                try:
                    await _populate_inner()
                except RuntimeError:
                    # Client disconnected mid-render – nothing to do.
                    return

        def _render_section_error(section_title: str, detail: str = "") -> None:
            """Render a visible fallback card for tab-level render failures."""
            with ui.card().classes("w-full").style("border:1px solid rgba(239,68,68,0.35)"):
                ui.label(t("app.section_error", section=section_title)).classes(
                    "text-negative text-h6"
                )
                ui.label(t("app.try_refresh")).classes("text-grey")
                if detail:
                    ui.label(detail).classes("text-caption text-grey")
                ui.button(
                    t("app.refresh"),
                    on_click=lambda: refresh_dashboard(),
                    icon="refresh",
                ).props("outline color=negative")

        def _render_section(
            container,
            render_fn,
            label: str,
            *,
            section_title: str | None = None,
            show_error_card: bool = True,
        ) -> None:
            """Clear *container* and call *render_fn* synchronously inside it.

            No ``await`` may appear inside a ``with container:`` block —
            NiceGUI's slot-stack (ContextVar) can lose track of the active
            parent across async suspension points, causing elements to
            silently attach to the wrong slot and leaving tabs blank.
            """
            try:
                if _try_clear(container):
                    with container:
                        render_fn()
            except Exception as exc:
                logger.warning("%s render failed: %s", label, exc)
                if not show_error_card or not _is_connected():
                    return
                try:
                    if _try_clear(container):
                        with container:
                            _render_section_error(
                                section_title or label,
                                str(exc)[:180],
                            )
                except Exception as error_exc:
                    logger.warning("%s error fallback failed: %s", label, error_exc)

        async def _populate_inner():
            """Inner populate logic – rebuilds every tab independently.

            Key design constraints:
            - ALL async data fetching happens in Phase 1 **before** any
              UI container is touched.  Phase 2 is purely synchronous.
            - Each tab is wrapped in its own try/except (via
              ``_render_section``) so one failure never prevents other
              tabs from rendering.
            """
            from rewired.gui.components import _run_in_thread

            # ── Phase 1: Fetch ALL data with timeouts ────────────
            # Every await happens here, before any `with container:`.
            sig = pf = uni = allocs = suggs = heatmap_data = None

            try:
                sig = await asyncio.wait_for(
                    _run_in_thread(dashboard_state.get_signals),
                    timeout=_DATA_FETCH_TIMEOUT,
                )
            except (asyncio.TimeoutError, Exception) as exc:
                logger.warning("Signal fetch failed/timed out: %s", exc)
                sig = dashboard_state._signal_cache

            try:
                pf = await asyncio.wait_for(
                    _run_in_thread(dashboard_state.get_portfolio),
                    timeout=_DATA_FETCH_TIMEOUT,
                )
            except (asyncio.TimeoutError, Exception) as exc:
                logger.warning("Portfolio fetch failed/timed out: %s", exc)
                pf = dashboard_state._portfolio_cache

            try:
                uni = await asyncio.wait_for(
                    _run_in_thread(dashboard_state.get_universe),
                    timeout=_DATA_FETCH_TIMEOUT,
                )
            except (asyncio.TimeoutError, Exception) as exc:
                logger.warning("Universe fetch failed/timed out: %s", exc)
                uni = dashboard_state._universe_cache

            try:
                allocs = await asyncio.wait_for(
                    _run_in_thread(dashboard_state.get_pies),
                    timeout=_DATA_FETCH_TIMEOUT,
                )
            except (asyncio.TimeoutError, Exception) as exc:
                logger.warning("Pies fetch failed/timed out: %s", exc)
                allocs = dashboard_state._pies_cache

            try:
                suggs = await asyncio.wait_for(
                    _run_in_thread(dashboard_state.get_suggestions),
                    timeout=_DATA_FETCH_TIMEOUT,
                )
            except (asyncio.TimeoutError, Exception) as exc:
                logger.warning("Suggestions fetch failed/timed out: %s", exc)
                suggs = dashboard_state._suggestions_cache

            if uni:
                try:
                    heatmap_data = await asyncio.wait_for(
                        _run_in_thread(dashboard_state.get_heatmap_data),
                        timeout=_DATA_FETCH_TIMEOUT,
                    )
                except (asyncio.TimeoutError, Exception) as exc:
                    logger.warning("Heatmap fetch failed/timed out: %s", exc)
                    heatmap_data = None

            if not _is_connected():
                return

            # ── Phase 2: Rebuild UI (purely synchronous) ─────────

            # Header signal indicator
            _render_section(signal_indicator_container, lambda: (
                components.header_signal_indicator(sig)
            ), "Header indicator", show_error_card=False)

            # Header status badges
            def _render_status_badges():
                statuses = dashboard_state.get_all_statuses()
                components.data_status_bar(statuses)

            _render_section(
                status_badge_container,
                _render_status_badges,
                "Status badges",
                show_error_card=False,
            )

            # Update timestamp
            try:
                updated_label.set_text(
                    t("app.updated", time=datetime.now().strftime("%H:%M:%S"))
                )
            except Exception:
                pass

            # ── Actions tab ──────────────────────────────────
            def _render_actions():
                if sig:
                    components.actions_logic_explainer(sig)
                    if allocs:
                        components.pies_allocation_table(allocs, sig)
                    else:
                        with ui.card().classes("w-full"):
                            ui.label(t("app.pies_unavailable")).classes("text-grey")
                    components.actions_playbook(sig, suggs or [])
                    components.suggestions_panel(suggs or [], sig)
                else:
                    components.actions_playbook(None, [])
                    with ui.card().classes("w-full"):
                        ui.label(t("app.signal_unavailable")).classes("text-grey")

            _render_section(
                actions_container,
                _render_actions,
                "Actions tab",
                section_title=t("tab.actions"),
            )

            # ── Signals tab ──────────────────────────────────
            def _render_signals():
                if sig:
                    components.signal_logic_explainer(sig)
                    components.signal_board(sig)
                    components.signal_drilldown(sig)
                else:
                    with ui.card().classes("w-full"):
                        ui.label(t("app.signal_unavailable_short")).classes("text-grey")
                history = dashboard_state.get_signal_history()
                components.signal_history_timeline(history)

            _render_section(
                signals_container,
                _render_signals,
                "Signals tab",
                section_title=t("tab.signals"),
            )

            # ── Portfolio tab ────────────────────────────────
            def _render_portfolio():
                components.portfolio_table(pf)
                components.trade_recording_form(on_trade_recorded=refresh_after_trade)
                components.transaction_history_table(pf)
                if uni:
                    components.interactive_universe_panel(
                        on_change=refresh_after_universe_change,
                        heatmap_data=heatmap_data,
                    )

            _render_section(
                portfolio_container,
                _render_portfolio,
                "Portfolio tab",
                section_title=t("tab.portfolio"),
            )

            # ── AI Copilot tab ────────────────────────────────
            _render_section(
                analysis_container,
                components.ai_copilot_panel,
                "AI Copilot tab",
                section_title="AI Copilot",
            )

            # ── Oracle Gateway tab ─────────────────────────────
            _render_section(
                evaluation_container,
                components.oracle_gateway_panel,
                "Oracle Gateway tab",
                section_title="Oracle Gateway",
            )

            # ── Monitor tab ──────────────────────────────────
            def _render_monitor():
                components.monitor_control_panel()
                components.export_panel(
                    get_pies_fn=dashboard_state.get_pies,
                    get_portfolio_fn=dashboard_state.get_portfolio,
                )
                # ── Regime state display ─────────────────────────
                regime = dashboard_state.get_regime_state()
                if regime:
                    with ui.card().classes("w-full"):
                        ui.label("Hysteresis Regime State").classes("text-bold text-lg")
                        with ui.row().classes("gap-4"):
                            ui.label(f"Current: {regime.current_regime.value.upper()}")
                            if regime.pending_upgrade:
                                ui.label(
                                    f"Pending upgrade: {regime.pending_upgrade.value.upper()} "
                                    f"({regime.consecutive_days}/3 days)"
                                ).classes("text-yellow")
                            else:
                                ui.label("No pending upgrade").classes("text-grey")
                            ui.label(f"Last updated: {regime.last_updated}")

                # ── Danger Zone: Factory Reset ───────────────────
                with ui.card().classes("w-full").style("border:1px solid #ef4444"):
                    ui.label("Danger Zone").classes("text-bold text-lg text-red")
                    ui.label(
                        "Factory reset will purge all portfolio state, signal history, "
                        "and caches. This action cannot be undone."
                    ).classes("text-grey text-sm")

                    reset_input = ui.number(
                        "New capital (EUR)", value=3100.0, min=0.0, format="%.2f",
                    ).classes("w-48")

                    async def _do_reset():
                        capital = reset_input.value or 3100.0
                        from rewired.portfolio.manager import factory_reset
                        await _run_in_thread(lambda: factory_reset(capital))
                        dashboard_state.refresh_portfolio_related()
                        ui.notify(f"Reset complete. Capital: {capital:.2f} EUR", type="positive")

                    ui.button(
                        "Factory Reset",
                        on_click=lambda: confirm_dialog.open(),
                        color="red",
                    ).props("outline")

                    with ui.dialog() as confirm_dialog:
                        with ui.card():
                            ui.label("Confirm Factory Reset").classes("text-bold text-lg")
                            ui.label("This will destroy ALL portfolio data. Are you sure?")
                            with ui.row():
                                ui.button("Cancel", on_click=confirm_dialog.close)

                                async def _confirm_reset():
                                    confirm_dialog.close()
                                    await _do_reset()

                                ui.button(
                                    "Yes, Reset Everything",
                                    on_click=_confirm_reset,
                                    color="red",
                                )

                # ── Capital Adjustment ────────────────────────────
                with ui.card().classes("w-full").style("border:1px solid #f59e0b"):
                    ui.label("Capital Adjustment").classes("text-bold text-lg")
                    ui.label(
                        "Inject or withdraw cash without wiping the portfolio."
                    ).classes("text-grey text-sm")

                    cap_amount = ui.number(
                        "Amount (EUR)", value=0.0, format="%.2f",
                    ).classes("w-48")
                    cap_reason = ui.input("Reason / note").classes("w-64")

                    async def _do_inject():
                        amt = cap_amount.value or 0.0
                        if amt <= 0:
                            ui.notify("Enter a positive amount to inject.", type="warning")
                            return
                        from rewired.portfolio.manager import (
                            load_portfolio, adjust_capital, save_portfolio,
                        )

                        def _go():
                            pf = load_portfolio()
                            adjust_capital(pf, amt, cap_reason.value or "")
                            save_portfolio(pf)
                            return pf.cash_eur

                        try:
                            cash = await _run_in_thread(_go)
                            dashboard_state.refresh_portfolio_related()
                            ui.notify(f"Injected {amt:.2f} EUR. Cash: {cash:.2f} EUR", type="positive")
                        except ValueError as e:
                            ui.notify(str(e), type="negative")

                    async def _do_withdraw():
                        amt = cap_amount.value or 0.0
                        if amt <= 0:
                            ui.notify("Enter a positive amount to withdraw.", type="warning")
                            return
                        from rewired.portfolio.manager import (
                            load_portfolio, adjust_capital, save_portfolio,
                        )

                        def _go():
                            pf = load_portfolio()
                            adjust_capital(pf, -amt, cap_reason.value or "")
                            save_portfolio(pf)
                            return pf.cash_eur

                        try:
                            cash = await _run_in_thread(_go)
                            dashboard_state.refresh_portfolio_related()
                            ui.notify(f"Withdrew {amt:.2f} EUR. Cash: {cash:.2f} EUR", type="positive")
                        except ValueError as e:
                            ui.notify(str(e), type="negative")

                    with ui.row().classes("gap-2"):
                        ui.button("Inject", on_click=_do_inject, color="green").props("outline")
                        ui.button("Withdraw", on_click=_do_withdraw, color="orange").props("outline")

                # ── Transaction Management ────────────────────────
                with ui.card().classes("w-full").style("border:1px solid #ef4444"):
                    ui.label("Delete Transaction").classes("text-bold text-lg")
                    ui.label(
                        "Remove a specific ledger entry. The portfolio will be "
                        "rebuilt from scratch by replaying all remaining transactions."
                    ).classes("text-grey text-sm")

                    tx_list_container = ui.column().classes("w-full")

                    async def _refresh_tx_list():
                        tx_list_container.clear()
                        from rewired.portfolio.manager import load_portfolio
                        pf = await _run_in_thread(load_portfolio)
                        if not pf.transactions:
                            with tx_list_container:
                                ui.label("No transactions.").classes("text-grey")
                            return
                        with tx_list_container:
                            for tx in reversed(pf.transactions):
                                ticker = tx.ticker or "--"
                                label = (
                                    f"{tx.date}  {tx.action:<8} {ticker:<8} "
                                    f"{tx.shares:.4f} x {tx.price_eur:.2f} EUR"
                                )
                                with ui.row().classes("items-center gap-2 w-full"):
                                    ui.label(label).classes("font-mono text-sm flex-grow")

                                    def _make_del(tid: str):
                                        async def _handler():
                                            from rewired.portfolio.manager import (
                                                load_portfolio as _lp,
                                                delete_transaction as _dt,
                                                save_portfolio as _sp,
                                            )

                                            def _go():
                                                p = _lp()
                                                ok = _dt(p, tid)
                                                if ok:
                                                    _sp(p)
                                                return ok

                                            ok = await _run_in_thread(_go)
                                            if ok:
                                                dashboard_state.refresh_portfolio_related()
                                                ui.notify("Deleted & replayed.", type="positive")
                                                await _refresh_tx_list()
                                            else:
                                                ui.notify("Transaction not found.", type="negative")
                                        return _handler

                                    ui.button(icon="delete", on_click=_make_del(tx.id), color="red").props(
                                        "flat dense round size=sm"
                                    )

                    ui.button("Load transactions", on_click=_refresh_tx_list).props("flat")

            _render_section(
                monitor_container,
                _render_monitor,
                "Monitor tab",
                section_title=t("tab.monitor"),
            )

        # Initial population (slight delay to let the page render)
        ui.timer(0.5, populate, once=True)

        # Auto-refresh every 5 minutes – store reference for cleanup
        auto_refresh = ui.timer(300, populate)

        # ── Disconnect cleanup ───────────────────────────────────
        def _on_client_disconnect():
            auto_refresh.active = False

        ui.context.client.on_disconnect(_on_client_disconnect)


def launch(port: int = 8080, reload: bool = False) -> None:
    """Launch the NiceGUI dashboard."""
    _build_dashboard()
    ui.run(
        title=t("app.browser_title"),
        port=port,
        reload=reload,
        show=True,
        dark=True,
    )
