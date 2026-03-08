"""Market-hours awareness for smart refresh gating.

Uses ``pandas_market_calendars`` to determine whether any tracked
exchange is currently open.  The GUI refresh timer can skip expensive
price fetches when all markets are closed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import NamedTuple

logger = logging.getLogger(__name__)

# Exchanges we care about (covers the universe portfolio).
# The calendar library uses XETR as the market code for Deutsche Boerse Xetra.
_CALENDAR_SPECS = [("NYSE", "NYSE"), ("LSE", "LSE"), ("XETR", "XETRA")]

# Cache the calendar objects to avoid repeated construction.
_calendars: list | None = None
_calendar_import_failed = False


def _get_calendars():
    global _calendars, _calendar_import_failed
    if _calendars is None:
        try:
            import pandas_market_calendars as mcal
        except ModuleNotFoundError:
            if not _calendar_import_failed:
                logger.warning(
                    "Market hours check failed: pandas_market_calendars is not installed; assuming open"
                )
                _calendar_import_failed = True
            raise
        _calendars = [
            (mcal.get_calendar(calendar_name), display_name)
            for calendar_name, display_name in _CALENDAR_SPECS
        ]
    return _calendars


class MarketStatus(NamedTuple):
    """Snapshot of market openness."""
    any_open: bool
    open_exchanges: list[str]
    next_open: datetime | None


def get_market_status() -> MarketStatus:
    """Check whether any tracked exchange is currently in a trading session.

    Returns a ``MarketStatus`` with ``any_open``, a list of open exchange
    names, and the ``next_open`` datetime (UTC) if all are closed.
    """
    try:
        import pandas as pd
        now = pd.Timestamp.now(tz="UTC")
        today_str = now.strftime("%Y-%m-%d")
        tomorrow_str = (now + timedelta(days=3)).strftime("%Y-%m-%d")

        open_names: list[str] = []
        earliest_next: datetime | None = None

        for cal, name in _get_calendars():
            schedule = cal.schedule(start_date=today_str, end_date=tomorrow_str)
            if schedule.empty:
                continue

            for _, row in schedule.iterrows():
                market_open = row["market_open"]
                market_close = row["market_close"]
                if market_open <= now <= market_close:
                    open_names.append(name)
                    break
                elif now < market_open:
                    dt = market_open.to_pydatetime()
                    if earliest_next is None or dt < earliest_next:
                        earliest_next = dt
                    break

        return MarketStatus(
            any_open=len(open_names) > 0,
            open_exchanges=open_names,
            next_open=earliest_next,
        )
    except Exception as exc:
        if not isinstance(exc, ModuleNotFoundError):
            logger.warning("Market hours check failed: %s — assuming open", exc)
        return MarketStatus(any_open=True, open_exchanges=[], next_open=None)


def is_any_market_open() -> bool:
    """Quick boolean: is any tracked exchange currently open?"""
    return get_market_status().any_open
