"""Rewired Index NiceGUI dashboard application.

Tab-based layout with persistent signal header:
- Header: title, composite signal indicator, data status badges, refresh button
- Tab 1 (Actions): Pies allocation + suggestions (default, most actionable)
- Tab 2 (Signals): Traffic lights, drill-down readings, history
- Tab 3 (Portfolio): Positions table, trade recording, transaction history, universe matrix
- Tab 4 (Analysis): Gemini analyst panel
- Tab 5 (Monitor): Background signal monitor, data export
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from nicegui import ui

from rewired.gui.i18n import Lang, get_language, set_language, t
from rewired.gui.state import dashboard_state
from rewired.gui import components


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
                analysis_tab = ui.tab(t("tab.analysis"), icon="psychology")
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

                # ── Tab 5: Monitor ───────────────────────────────
                with ui.tab_panel(monitor_tab):
                    monitor_container = ui.column().classes("w-full gap-4")

        # ── Data Loading & Rendering ─────────────────────────────────

        async def refresh_dashboard():
            """Force refresh all data and rebuild."""
            updated_label.set_text(t("app.refreshing"))
            dashboard_state.refresh_all()
            await populate()

        async def populate():
            """Populate all tabs with current data."""
            async with populate_lock:
                from rewired.gui.components import _run_in_thread

                try:
                    sig = await _run_in_thread(dashboard_state.get_signals)
                    pf = await _run_in_thread(dashboard_state.get_portfolio)
                    uni = await _run_in_thread(dashboard_state.get_universe)
                except Exception:
                    sig = dashboard_state._signal_cache
                    pf = dashboard_state._portfolio_cache
                    uni = dashboard_state._universe_cache

                # Update header signal indicator
                signal_indicator_container.clear()
                with signal_indicator_container:
                    components.header_signal_indicator(sig)

                # Update header status badges
                status_badge_container.clear()
                with status_badge_container:
                    statuses = dashboard_state.get_all_statuses()
                    components.data_status_bar(statuses)

                # Update timestamp
                updated_label.set_text(
                    t("app.updated", time=datetime.now().strftime("%H:%M:%S"))
                )

                # ── Populate Actions tab ─────────────────────────
                actions_container.clear()
                with actions_container:
                    if sig:
                        components.actions_logic_explainer(sig)
                        try:
                            allocs = await _run_in_thread(dashboard_state.get_pies)
                            if allocs:
                                components.pies_allocation_table(allocs, sig)
                            else:
                                with ui.card().classes("w-full"):
                                    ui.label(t("app.pies_unavailable")).classes("text-grey")
                        except Exception:
                            with ui.card().classes("w-full"):
                                ui.label(t("app.pies_error")).classes("text-grey")

                        try:
                            suggs = await _run_in_thread(dashboard_state.get_suggestions)
                            components.actions_playbook(sig, suggs or [])
                            components.suggestions_panel(suggs or [], sig)
                        except Exception:
                            components.actions_playbook(sig, [])
                            with ui.card().classes("w-full"):
                                ui.label(t("app.suggest_error")).classes("text-grey")
                    else:
                        components.actions_playbook(None, [])
                        with ui.card().classes("w-full"):
                            ui.label(
                                t("app.signal_unavailable")
                            ).classes("text-grey")

                # ── Populate Signals tab ─────────────────────────
                signals_container.clear()
                with signals_container:
                    if sig:
                        components.signal_logic_explainer(sig)
                        components.signal_board(sig)
                        components.signal_drilldown(sig)
                    else:
                        with ui.card().classes("w-full"):
                            ui.label(t("app.signal_unavailable_short")).classes("text-grey")

                    history = dashboard_state.get_signal_history()
                    components.signal_history_timeline(history)

                # ── Populate Portfolio tab ────────────────────────
                portfolio_container.clear()
                with portfolio_container:
                    components.portfolio_table(pf)
                    components.trade_recording_form(on_trade_recorded=refresh_dashboard)
                    components.transaction_history_table(pf)
                    if uni:
                        components.universe_matrix(uni)
                    components.universe_management_card(on_change=refresh_dashboard)

                # ── Populate Analysis tab ────────────────────────
                analysis_container.clear()
                with analysis_container:
                    components.ai_analysis_panel()

                # ── Populate Monitor tab ─────────────────────────
                monitor_container.clear()
                with monitor_container:
                    components.monitor_control_panel()
                    components.export_panel(
                        get_pies_fn=dashboard_state.get_pies,
                        get_portfolio_fn=dashboard_state.get_portfolio,
                    )

        # Initial population (slight delay to let the page render)
        ui.timer(0.5, populate, once=True)

        # Auto-refresh every 5 minutes
        ui.timer(300, populate)


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
