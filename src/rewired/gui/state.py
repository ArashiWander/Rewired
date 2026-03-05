"""Dashboard data state - fetches and caches all data needed by the GUI."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from rewired import get_data_dir

# Cache TTL in seconds
_SIGNAL_TTL = 300       # 5 minutes
_PORTFOLIO_TTL = 120    # 2 minutes
_PIES_TTL = 300         # 5 minutes


@dataclass
class DashboardState:
    """Holds cached dashboard data with TTL-based refresh."""

    _signal_cache: object = field(default=None, repr=False)
    _signal_ts: float = 0
    _portfolio_cache: object = field(default=None, repr=False)
    _portfolio_ts: float = 0
    _pies_cache: list = field(default_factory=list, repr=False)
    _pies_ts: float = 0
    _suggestions_cache: list = field(default_factory=list, repr=False)
    _suggestions_ts: float = 0
    _universe_cache: object = field(default=None, repr=False)

    def get_signals(self):
        """Get signals, refreshing if stale."""
        if self._signal_cache and (time.time() - self._signal_ts < _SIGNAL_TTL):
            return self._signal_cache
        try:
            from rewired.signals.engine import compute_signals
            self._signal_cache = compute_signals()
            self._signal_ts = time.time()
        except Exception:
            pass
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
        except Exception:
            pass
        return self._portfolio_cache

    def get_pies(self) -> list[dict]:
        """Get Pies allocation."""
        if self._pies_cache and (time.time() - self._pies_ts < _PIES_TTL):
            return self._pies_cache
        try:
            from rewired.models.universe import load_universe
            from rewired.portfolio.sizing import calculate_pies_allocation
            sig = self.get_signals()
            pf = self.get_portfolio()
            uni = self.get_universe()
            if sig and pf and uni:
                self._pies_cache = calculate_pies_allocation(pf, uni, sig)
                self._pies_ts = time.time()
        except Exception:
            pass
        return self._pies_cache

    def get_suggestions(self) -> list[dict]:
        """Get sizing suggestions."""
        if self._suggestions_cache and (time.time() - self._suggestions_ts < _PIES_TTL):
            return self._suggestions_cache
        try:
            from rewired.models.universe import load_universe
            from rewired.portfolio.sizing import calculate_suggestions
            sig = self.get_signals()
            pf = self.get_portfolio()
            uni = self.get_universe()
            if sig and pf and uni:
                self._suggestions_cache = calculate_suggestions(pf, uni, sig)
                self._suggestions_ts = time.time()
        except Exception:
            pass
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
        except Exception:
            pass
        return self._universe_cache

    def refresh_all(self) -> None:
        """Force refresh all caches by resetting timestamps."""
        self._signal_ts = 0
        self._portfolio_ts = 0
        self._pies_ts = 0
        self._suggestions_ts = 0
        self._universe_cache = None


# Singleton instance
dashboard_state = DashboardState()
