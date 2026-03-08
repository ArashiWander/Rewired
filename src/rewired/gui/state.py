"""Dashboard data state - fetches and caches all data needed by the GUI.

Includes DataStatus tracking so the UI can surface errors and stale-data
warnings instead of silently swallowing failures.

Each public ``get_*`` method uses a non-blocking lock so that only one
thread fetches a given data source at a time.  If a fetch is already in
progress, callers immediately receive the (possibly stale) cached value
instead of spawning a duplicate API call chain.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field

from rewired import get_data_dir

logger = logging.getLogger(__name__)

# Cache TTL in seconds
_SIGNAL_TTL = 300       # 5 minutes
_PORTFOLIO_TTL = 120    # 2 minutes
_PIES_TTL = 300         # 5 minutes


_HEATMAP_TTL = 60      # 1 minute — fast enough for live heatmap refresh
_REGIME_TTL = 120      # 2 minutes — regime state from JSON file


def _ttl_is_fresh(timestamp: float, ttl_seconds: float) -> bool:
    return timestamp > 0 and (time.time() - timestamp < ttl_seconds)


def _cache_age(timestamp: float) -> float:
    if timestamp <= 0:
        return 0.0
    return time.time() - timestamp


def _log_fetch_start(name: str) -> float:
    started = time.perf_counter()
    logger.info("Fetching %s data", name)
    return started


def _log_fetch_success(name: str, started: float, detail: str = "") -> None:
    suffix = f" ({detail})" if detail else ""
    logger.info(
        "Fetched %s data in %.2fs%s",
        name,
        time.perf_counter() - started,
        suffix,
    )


def _log_fetch_failure(name: str, started: float, exc: Exception) -> None:
    logger.warning(
        "Failed to fetch %s data after %.2fs: %s",
        name,
        time.perf_counter() - started,
        exc,
    )


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
    """Holds cached dashboard data with TTL-based refresh and error tracking.

    Each ``get_*`` method acquires a per-source non-blocking lock before
    fetching.  If a fetch is already in progress the caller receives the
    (possibly stale) cached value immediately, preventing duplicate API
    call chains that saturate thread pools and produce the "fetching data
    endlessly" symptom.
    """

    _signal_cache: object = field(default=None, repr=False)
    _signal_ts: float = 0
    _signal_status: DataStatus = field(default_factory=DataStatus)
    _signal_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    _portfolio_cache: object = field(default=None, repr=False)
    _portfolio_ts: float = 0
    _portfolio_status: DataStatus = field(default_factory=DataStatus)
    _portfolio_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    _pies_cache: list = field(default_factory=list, repr=False)
    _pies_ts: float = 0
    _pies_status: DataStatus = field(default_factory=DataStatus)
    _pies_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    _suggestions_cache: list = field(default_factory=list, repr=False)
    _suggestions_ts: float = 0
    _suggestions_status: DataStatus = field(default_factory=DataStatus)
    _suggestions_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    _universe_cache: object = field(default=None, repr=False)
    _universe_status: DataStatus = field(default_factory=DataStatus)
    _universe_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    _heatmap_cache: dict = field(default_factory=dict, repr=False)
    _heatmap_ts: float = 0
    _heatmap_status: DataStatus = field(default_factory=DataStatus)
    _heatmap_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    _regime_cache: object = field(default=None, repr=False)
    _regime_ts: float = 0
    _regime_status: DataStatus = field(default_factory=DataStatus)
    _regime_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    _pie_detail_cache: dict = field(default_factory=dict, repr=False)
    _pie_detail_ts: float = 0
    _pie_detail_status: DataStatus = field(default_factory=DataStatus)
    _pie_detail_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get_signals(self):
        """Get signals, refreshing if stale.

        Uses a non-blocking lock so concurrent callers return the cached
        value instead of spawning duplicate ``compute_signals()`` chains.
        """
        if self._signal_cache and _ttl_is_fresh(self._signal_ts, _SIGNAL_TTL):
            logger.debug("Using cached signals data (age %.1fs)", _cache_age(self._signal_ts))
            return self._signal_cache
        if not self._signal_lock.acquire(blocking=False):
            logger.debug("Signals fetch already in progress; returning cached data")
            return self._signal_cache
        started = _log_fetch_start("signals")
        try:
            from rewired.signals.engine import compute_signals
            self._signal_cache = compute_signals()
            self._signal_ts = time.time()
            self._signal_status.mark_success()
            overall = getattr(getattr(self._signal_cache, "overall_color", None), "value", "unknown")
            _log_fetch_success("signals", started, f"overall={overall}")
        except Exception as e:
            self._signal_status.mark_error(str(e))
            _log_fetch_failure("signals", started, e)
        finally:
            self._signal_lock.release()
        return self._signal_cache

    def get_portfolio(self):
        """Get portfolio from live T212 broker data.  No local fallback."""
        if self._portfolio_cache and _ttl_is_fresh(self._portfolio_ts, _PORTFOLIO_TTL):
            logger.debug("Using cached portfolio data (age %.1fs)", _cache_age(self._portfolio_ts))
            return self._portfolio_cache
        if not self._portfolio_lock.acquire(blocking=False):
            logger.debug("Portfolio fetch already in progress; returning cached data")
            return self._portfolio_cache
        started = _log_fetch_start("portfolio")
        try:
            from rewired.data.broker import get_portfolio
            pf = get_portfolio()
            self._portfolio_cache = pf
            self._portfolio_ts = time.time()
            self._portfolio_status.mark_success()
            positions = len(pf.positions) if pf and pf.positions else 0
            _log_fetch_success("portfolio", started, f"positions={positions}")
        except Exception as e:
            self._portfolio_status.mark_error(str(e))
            _log_fetch_failure("portfolio", started, e)
        finally:
            self._portfolio_lock.release()
        return self._portfolio_cache

    def get_pies(self) -> list[dict]:
        """Get Pies allocation."""
        if self._pies_cache and _ttl_is_fresh(self._pies_ts, _PIES_TTL):
            logger.debug("Using cached pies data (age %.1fs)", _cache_age(self._pies_ts))
            return self._pies_cache
        if not self._pies_lock.acquire(blocking=False):
            logger.debug("Pies fetch already in progress; returning cached data")
            return self._pies_cache
        started = _log_fetch_start("pies")
        try:
            from rewired.portfolio.sizing import calculate_pies_allocation
            sig = self.get_signals()
            pf = self.get_portfolio()
            uni = self.get_universe()
            if sig and pf and uni:
                self._pies_cache = calculate_pies_allocation(pf, uni, sig)
                self._pies_ts = time.time()
                self._pies_status.mark_success()
                _log_fetch_success("pies", started, f"rows={len(self._pies_cache)}")
            else:
                logger.info("Skipped pies fetch because prerequisite data is missing")
        except Exception as e:
            self._pies_status.mark_error(str(e))
            _log_fetch_failure("pies", started, e)
        finally:
            self._pies_lock.release()
        return self._pies_cache

    def get_suggestions(self) -> list[dict]:
        """Get sizing suggestions."""
        if self._suggestions_cache and _ttl_is_fresh(self._suggestions_ts, _PIES_TTL):
            logger.debug(
                "Using cached suggestions data (age %.1fs)",
                _cache_age(self._suggestions_ts),
            )
            return self._suggestions_cache
        if not self._suggestions_lock.acquire(blocking=False):
            logger.debug("Suggestions fetch already in progress; returning cached data")
            return self._suggestions_cache
        started = _log_fetch_start("suggestions")
        try:
            from rewired.portfolio.sizing import calculate_suggestions
            sig = self.get_signals()
            pf = self.get_portfolio()
            uni = self.get_universe()
            if sig and pf and uni:
                self._suggestions_cache = calculate_suggestions(pf, uni, sig)
                self._suggestions_ts = time.time()
                self._suggestions_status.mark_success()
                _log_fetch_success("suggestions", started, f"rows={len(self._suggestions_cache)}")
            else:
                logger.info("Skipped suggestions fetch because prerequisite data is missing")
        except Exception as e:
            self._suggestions_status.mark_error(str(e))
            _log_fetch_failure("suggestions", started, e)
        finally:
            self._suggestions_lock.release()
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
            logger.debug("Using cached universe data")
            return self._universe_cache
        if not self._universe_lock.acquire(blocking=False):
            logger.debug("Universe fetch already in progress; returning cached data")
            return self._universe_cache
        started = _log_fetch_start("universe")
        try:
            from rewired.models.universe import load_universe
            self._universe_cache = load_universe()
            self._universe_status.mark_success()
            count = len(getattr(self._universe_cache, "stocks", [])) if self._universe_cache else 0
            _log_fetch_success("universe", started, f"stocks={count}")
        except Exception as e:
            self._universe_status.mark_error(str(e))
            _log_fetch_failure("universe", started, e)
        finally:
            self._universe_lock.release()
        return self._universe_cache

    def get_heatmap_data(self) -> dict:
        """Get enriched heatmap data: prices, portfolio values, daily changes.

        Returns a dict keyed by ``(layer_int, tier_int)`` → list of dicts
        with keys: ticker, name, price_usd (native instrument currency for
        display), price_eur, portfolio_value_eur, weight_pct,
        daily_change_pct, max_weight_pct.
        """
        if self._heatmap_cache and _ttl_is_fresh(self._heatmap_ts, _HEATMAP_TTL):
            logger.debug("Using cached heatmap data (age %.1fs)", _cache_age(self._heatmap_ts))
            return self._heatmap_cache
        if not self._heatmap_lock.acquire(blocking=False):
            logger.debug("Heatmap fetch already in progress; returning cached data")
            return self._heatmap_cache
        started = _log_fetch_start("heatmap")
        try:
            uni = self.get_universe()
            pf = self.get_portfolio()
            if not uni:
                logger.info("Skipped heatmap fetch because universe data is unavailable")
                return self._heatmap_cache

            all_tickers = uni.tickers
            from rewired.data.prices import get_current_prices, get_daily_changes
            prices_usd = get_current_prices(all_tickers) if all_tickers else {}
            daily_changes = get_daily_changes(all_tickers) if all_tickers else {}

            result: dict[tuple[int, int], list[dict]] = {}
            for stock in uni.stocks:
                key = (stock.layer.value, stock.tier.value)
                pos = pf.positions.get(stock.ticker) if pf and pf.positions else None
                entry = {
                    "ticker": stock.ticker,
                    "name": stock.name,
                    "price_usd": round(prices_usd.get(stock.ticker, 0.0), 2),
                    "price_eur": round(pos.current_price_eur, 2) if pos else 0.0,
                    "portfolio_value_eur": round(pos.market_value_eur, 2) if pos else 0.0,
                    "weight_pct": round(pos.weight_pct, 1) if pos else 0.0,
                    "daily_change_pct": daily_changes.get(stock.ticker, 0.0),
                    "max_weight_pct": stock.max_weight_pct,
                }
                result.setdefault(key, []).append(entry)

            self._heatmap_cache = result
            self._heatmap_ts = time.time()
            self._heatmap_status.mark_success()
            cells = sum(len(items) for items in result.values())
            _log_fetch_success("heatmap", started, f"cells={cells}")
        except Exception as e:
            self._heatmap_status.mark_error(str(e))
            _log_fetch_failure("heatmap", started, e)
        finally:
            self._heatmap_lock.release()
        return self._heatmap_cache

    def get_all_statuses(self) -> dict[str, DataStatus]:
        """Return status of all data sources for the UI status bar."""
        return {
            "Signals": self._signal_status,
            "Portfolio": self._portfolio_status,
            "Pies": self._pies_status,
            "Suggestions": self._suggestions_status,
            "Universe": self._universe_status,
            "Heatmap": self._heatmap_status,
            "Regime": self._regime_status,
        }

    def get_regime_state(self):
        """Get the current regime state (hysteresis) from disk cache.

        Returns a RegimeState instance or None.
        """
        if self._regime_cache and _ttl_is_fresh(self._regime_ts, _REGIME_TTL):
            logger.debug("Using cached regime data (age %.1fs)", _cache_age(self._regime_ts))
            return self._regime_cache
        if not self._regime_lock.acquire(blocking=False):
            logger.debug("Regime fetch already in progress; returning cached data")
            return self._regime_cache
        started = _log_fetch_start("regime")
        try:
            regime_path = get_data_dir() / "regime_state.json"
            if regime_path.exists():
                with open(regime_path, encoding="utf-8") as f:
                    data = json.load(f)
                from rewired.models.signals import RegimeState
                self._regime_cache = RegimeState.model_validate(data)
            self._regime_ts = time.time()
            self._regime_status.mark_success()
            current = getattr(getattr(self._regime_cache, "current_regime", None), "value", "none")
            _log_fetch_success("regime", started, f"current={current}")
        except Exception as e:
            self._regime_status.mark_error(str(e))
            _log_fetch_failure("regime", started, e)
        finally:
            self._regime_lock.release()
        return self._regime_cache

    def refresh_all(self) -> None:
        """Force refresh all caches by resetting timestamps."""
        self._signal_ts = 0
        self._portfolio_ts = 0
        self._pies_ts = 0
        self._suggestions_ts = 0
        self._heatmap_ts = 0
        self._universe_cache = None

    def refresh_portfolio_related(self) -> None:
        """Invalidate portfolio, pies, suggestions, and heatmap.

        Use after trade recording, capital adjustments, or transaction
        deletes — operations that change the portfolio but NOT the
        macro/sentiment/AI-health signals.
        """
        self._portfolio_ts = 0
        self._pies_ts = 0
        self._suggestions_ts = 0
        self._heatmap_ts = 0

    def refresh_universe_related(self) -> None:
        """Invalidate universe and everything that depends on it."""
        self._universe_cache = None
        self._pies_ts = 0
        self._suggestions_ts = 0
        self._heatmap_ts = 0


# Singleton instance
dashboard_state = DashboardState()


def invalidate_universe() -> None:
    """Invalidate the universe cache after external mutation (e.g. rebalancer)."""
    dashboard_state._universe_cache = None
    dashboard_state._universe_status = DataStatus()
