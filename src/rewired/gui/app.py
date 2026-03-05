"""Rewired Index NiceGUI dashboard application."""

from __future__ import annotations

from nicegui import ui

from rewired.gui.state import dashboard_state
from rewired.gui import components


def _build_dashboard() -> None:
    """Build the single-page dashboard layout."""

    @ui.page("/")
    def index():
        ui.dark_mode().enable()

        # Header
        with ui.header().classes("items-center justify-between"):
            ui.label("REWIRED INDEX").classes("text-h4").style("font-weight:bold")
            with ui.row().classes("items-center gap-2"):
                status_label = ui.label("").classes("text-caption text-grey")
                ui.button(
                    "Refresh All",
                    on_click=lambda: refresh_dashboard(),
                    icon="refresh",
                ).props("flat color=white")

        # Main content
        with ui.column().classes("w-full max-w-7xl mx-auto p-4 gap-4"):

            # Row 1: Signal Board (full width)
            signal_container = ui.column().classes("w-full")

            # Row 2: Universe + Portfolio
            with ui.row().classes("w-full gap-4"):
                universe_container = ui.column().classes("w-full lg:w-1/2")
                portfolio_container = ui.column().classes("w-full lg:w-1/2")

            # Row 3: Pies + Suggestions
            with ui.row().classes("w-full gap-4"):
                pies_container = ui.column().classes("w-full lg:w-1/2")
                suggestions_container = ui.column().classes("w-full lg:w-1/2")

            # Row 4: AI Analysis (full width)
            ai_container = ui.column().classes("w-full")

            # Row 5: Signal History (full width)
            history_container = ui.column().classes("w-full")

        async def refresh_dashboard():
            """Force refresh all data and rebuild."""
            status_label.set_text("Refreshing...")
            dashboard_state.refresh_all()
            await populate()
            status_label.set_text("")

        async def populate():
            """Populate all containers with current data."""
            from rewired.gui.components import _run_in_thread

            try:
                # Fetch data in thread pool (blocking yfinance/FRED calls)
                sig = await _run_in_thread(dashboard_state.get_signals)
                pf = await _run_in_thread(dashboard_state.get_portfolio)
                uni = await _run_in_thread(dashboard_state.get_universe)
            except Exception:
                sig = dashboard_state._signal_cache
                pf = dashboard_state._portfolio_cache
                uni = dashboard_state._universe_cache

            signal_container.clear()
            with signal_container:
                if sig:
                    components.signal_board(sig)
                else:
                    with ui.card().classes("w-full"):
                        ui.label("Signal data unavailable. Click Refresh.").classes(
                            "text-grey"
                        )

            universe_container.clear()
            with universe_container:
                if uni:
                    components.universe_matrix(uni)

            portfolio_container.clear()
            with portfolio_container:
                components.portfolio_table(pf)

            pies_container.clear()
            with pies_container:
                if sig:
                    try:
                        allocs = await _run_in_thread(dashboard_state.get_pies)
                        if allocs:
                            components.pies_allocation_table(allocs, sig)
                        else:
                            with ui.card().classes("w-full"):
                                ui.label("Pies data unavailable.").classes("text-grey")
                    except Exception:
                        with ui.card().classes("w-full"):
                            ui.label("Error loading Pies data.").classes("text-grey")

            suggestions_container.clear()
            with suggestions_container:
                if sig:
                    try:
                        suggs = await _run_in_thread(dashboard_state.get_suggestions)
                        components.suggestions_panel(suggs or [], sig)
                    except Exception:
                        with ui.card().classes("w-full"):
                            ui.label("Error loading suggestions.").classes("text-grey")

            ai_container.clear()
            with ai_container:
                components.ai_analysis_panel()

            history_container.clear()
            with history_container:
                history = dashboard_state.get_signal_history()
                components.signal_history_timeline(history)

        # Initial population (slight delay to let the page render)
        ui.timer(0.5, populate, once=True)

        # Auto-refresh every 5 minutes
        ui.timer(300, populate)


def launch(port: int = 8080, reload: bool = False) -> None:
    """Launch the NiceGUI dashboard."""
    _build_dashboard()
    ui.run(
        title="Rewired Index",
        port=port,
        reload=reload,
        show=True,
        dark=True,
    )
