"""Dashboard data state - fetches and caches all data needed by the GUI.

Includes DataStatus tracking so the UI can surface errors and stale-data
warnings instead of silently swallowing failures.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from rewired import get_data_dir

# Cache TTL in seconds
_SIGNAL_TTL = 300       # 5 minutes
_PORTFOLIO_TTL = 120    # 2 minutes
_PIES_TTL = 300         # 5 minutes
_EVAL_TTL = 600         # 10 minutes (Gemini calls are expensive)


_HEATMAP_TTL = 60      # 1 minute — fast enough for live heatmap refresh


@dataclass
class DataStatus:
    """Status of a single data source."""

    last_success: float = 0        # timestamp of last successful fetch
    last_error: str = ""           # last error message (empty = OK)
    last_error_ts: float = 0       # when the error occurred
    is_stale: bool = False         # TTL expired and refresh failed

    @property
    def ok(self) -> bool:
        """True when data is fresh and no unresolved error."""
        return not self.last_error or self.last_success > self.last_error_ts

    @property
    def age_seconds(self) -> float:
        """Seconds since last successful fetch (0 if never fetched)."""
        if self.last_success == 0:
            return 0
        return time.time() - self.last_success

    def mark_success(self) -> None:
        self.last_success = time.time()
        self.last_error = ""
        self.is_stale = False

    def mark_error(self, error: str) -> None:
        self.last_error = error
        self.last_error_ts = time.time()
        self.is_stale = True


@dataclass
class DashboardState:
    """Holds cached dashboard data with TTL-based refresh and error tracking."""

    _signal_cache: object = field(default=None, repr=False)
    _signal_ts: float = 0
    _signal_status: DataStatus = field(default_factory=DataStatus)

    _portfolio_cache: object = field(default=None, repr=False)
    _portfolio_ts: float = 0
    _portfolio_status: DataStatus = field(default_factory=DataStatus)

    _pies_cache: list = field(default_factory=list, repr=False)
    _pies_ts: float = 0
    _pies_status: DataStatus = field(default_factory=DataStatus)

    _suggestions_cache: list = field(default_factory=list, repr=False)
    _suggestions_ts: float = 0
    _suggestions_status: DataStatus = field(default_factory=DataStatus)

    _universe_cache: object = field(default=None, repr=False)
    _universe_status: DataStatus = field(default_factory=DataStatus)

    _evaluation_cache: object = field(default=None, repr=False)
    _evaluation_ts: float = 0
    _evaluation_status: DataStatus = field(default_factory=DataStatus)

    _heatmap_cache: dict = field(default_factory=dict, repr=False)
    _heatmap_ts: float = 0
    _heatmap_status: DataStatus = field(default_factory=DataStatus)

    def get_signals(self):
        """Get signals, refreshing if stale."""
        if self._signal_cache and (time.time() - self._signal_ts < _SIGNAL_TTL):
            return self._signal_cache
        try:
            from rewired.signals.engine import compute_signals
            self._signal_cache = compute_signals()
            self._signal_ts = time.time()
            self._signal_status.mark_success()
        except Exception as e:
            self._signal_status.mark_error(str(e))
        return self._signal_cache

    def get_portfolio(self):
        """Get portfolio with refreshed prices."""
        if self._portfolio_cache and (time.time() - self._portfolio_ts < _PORTFOLIO_TTL):
            return self._portfolio_cache
        try:
            from rewired.portfolio.manager import load_portfolio, refresh_prices
            pf = load_portfolio()
            if pf.positions:
                refresh_prices(pf)
            self._portfolio_cache = pf
            self._portfolio_ts = time.time()
            self._portfolio_status.mark_success()
        except Exception as e:
            self._portfolio_status.mark_error(str(e))
        return self._portfolio_cache

    def get_pies(self) -> list[dict]:
        """Get Pies allocation."""
        if self._pies_cache and (time.time() - self._pies_ts < _PIES_TTL):
            return self._pies_cache
        try:
            from rewired.portfolio.sizing import calculate_pies_allocation
            sig = self.get_signals()
            pf = self.get_portfolio()
            uni = self.get_universe()
            if sig and pf and uni:
                self._pies_cache = calculate_pies_allocation(pf, uni, sig)
                self._pies_ts = time.time()
                self._pies_status.mark_success()
        except Exception as e:
            self._pies_status.mark_error(str(e))
        return self._pies_cache

    def get_suggestions(self) -> list[dict]:
        """Get sizing suggestions."""
        if self._suggestions_cache and (time.time() - self._suggestions_ts < _PIES_TTL):
            return self._suggestions_cache
        try:
            from rewired.portfolio.sizing import calculate_suggestions
            sig = self.get_signals()
            pf = self.get_portfolio()
            uni = self.get_universe()
            if sig and pf and uni:
                self._suggestions_cache = calculate_suggestions(pf, uni, sig)
                self._suggestions_ts = time.time()
                self._suggestions_status.mark_success()
        except Exception as e:
            self._suggestions_status.mark_error(str(e))
        return self._suggestions_cache

    def get_signal_history(self) -> list[dict]:
        """Get signal color change history."""
        try:
            history_path = get_data_dir() / "signal_history.json"
            if history_path.exists():
                with open(history_path, encoding="utf-8") as f:
                    return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
        return []

    def get_universe(self):
        """Get the stock universe (static, cached permanently)."""
        if self._universe_cache is not None:
            return self._universe_cache
        try:
            from rewired.models.universe import load_universe
            self._universe_cache = load_universe()
            self._universe_status.mark_success()
        except Exception as e:
            self._universe_status.mark_error(str(e))
        return self._universe_cache

    def get_evaluations(self):
        """Get cached evaluation batch, refreshing if stale."""
        if self._evaluation_cache and (time.time() - self._evaluation_ts < _EVAL_TTL):
            return self._evaluation_cache
        try:
            from rewired.agent.evaluator import evaluate_universe
            self._evaluation_cache = evaluate_universe()
            self._evaluation_ts = time.time()
            self._evaluation_status.mark_success()
        except Exception as e:
            self._evaluation_status.mark_error(str(e))
        return self._evaluation_cache

    def get_heatmap_data(self) -> dict:
        """Get enriched heatmap data: prices, portfolio values, daily changes.

        Returns a dict keyed by ``(layer_int, tier_int)`` → list of dicts
        with keys: ticker, name, price_eur, portfolio_value_eur, weight_pct,
        daily_change_pct, max_weight_pct.
        """
        if self._heatmap_cache and (time.time() - self._heatmap_ts < _HEATMAP_TTL):
            return self._heatmap_cache
        try:
            uni = self.get_universe()
            pf = self.get_portfolio()
            if not uni:
                return self._heatmap_cache

            all_tickers = uni.tickers
            from rewired.data.prices import get_current_prices_eur, get_daily_changes
            prices_eur = get_current_prices_eur(all_tickers) if all_tickers else {}
            daily_changes = get_daily_changes(all_tickers) if all_tickers else {}

            result: dict[tuple[int, int], list[dict]] = {}
            for stock in uni.stocks:
                key = (stock.layer.value, stock.tier.value)
                pos = pf.positions.get(stock.ticker) if pf and pf.positions else None
                entry = {
                    "ticker": stock.ticker,
                    "name": stock.name,
                    "price_eur": round(prices_eur.get(stock.ticker, 0.0), 2),
                    "portfolio_value_eur": round(pos.market_value_eur, 2) if pos else 0.0,
                    "weight_pct": round(pos.weight_pct, 1) if pos else 0.0,
                    "daily_change_pct": daily_changes.get(stock.ticker, 0.0),
                    "max_weight_pct": stock.max_weight_pct,
                }
                result.setdefault(key, []).append(entry)

            self._heatmap_cache = result
            self._heatmap_ts = time.time()
            self._heatmap_status.mark_success()
        except Exception as e:
            self._heatmap_status.mark_error(str(e))
        return self._heatmap_cache

    def get_all_statuses(self) -> dict[str, DataStatus]:
        """Return status of all data sources for the UI status bar."""
        return {
            "Signals": self._signal_status,
            "Portfolio": self._portfolio_status,
            "Pies": self._pies_status,
            "Suggestions": self._suggestions_status,
            "Universe": self._universe_status,
            "Evaluation": self._evaluation_status,
            "Heatmap": self._heatmap_status,
        }

    def refresh_all(self) -> None:
        """Force refresh all caches by resetting timestamps."""
        self._signal_ts = 0
        self._portfolio_ts = 0
        self._pies_ts = 0
        self._suggestions_ts = 0
        self._heatmap_ts = 0
        self._universe_cache = None


# Singleton instance
dashboard_state = DashboardState()


def invalidate_universe() -> None:
    """Invalidate the universe cache after external mutation (e.g. rebalancer)."""
    dashboard_state._universe_cache = None
    dashboard_state._universe_status = DataStatus()
