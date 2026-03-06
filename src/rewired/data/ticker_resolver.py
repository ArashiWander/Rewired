"""Lightweight ticker ↔ company-name resolver.

Uses three resolution strategies in order:

1. **Exact** – case-insensitive ticker / name lookup against the universe YAML.
2. **Fuzzy** – rapidfuzz token-set-ratio against all ``ticker + name`` pairs in
   the universe and an optional alias table.  Threshold: 80 by default.
3. **FMP search** – online fallback via the Financial Modeling Prep ``/search``
   endpoint (requires FMP_API_KEY).

All heavy imports (``rapidfuzz``) are lazy so ``rewired --help`` stays fast.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ── result type ──────────────────────────────────────────────────────────


@dataclass
class ResolvedTicker:
    """The output of a resolution attempt."""

    ticker: str
    name: str
    score: float  # 0-100, 100 = exact match
    source: str  # "universe", "alias", "fuzzy", "fmp"
    in_universe: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


# ── alias table (common alternative names → canonical ticker) ────────────

_ALIASES: dict[str, str] = {
    # Shorthand / press names
    "google": "GOOGL",
    "alphabet": "GOOGL",
    "facebook": "META",
    "amazon": "AMZN",
    "aws": "AMZN",
    "microsoft": "MSFT",
    "azure": "MSFT",
    "apple": "AAPL",
    "appl": "AAPL",
    "nvidia": "NVDA",
    "tesla": "TSLA",
    "palantir": "PLTR",
    "coinbase": "COIN",
    "rocket lab": "RKLB",
    "ionq": "IONQ",
    "tsmc": "TSM",
    "taiwan semiconductor": "TSM",
    "asml": "ASML",
    "amd": "AMD",
    "advanced micro devices": "AMD",
    "meta platforms": "META",
    "meta": "META",
}


# ── public API ───────────────────────────────────────────────────────────


def resolve(
    query: str,
    *,
    threshold: int = 80,
    online_fallback: bool = True,
) -> ResolvedTicker | None:
    """Resolve a free-text query to a ticker.

    Parameters
    ----------
    query:
        Ticker symbol, company name, or alias (e.g. "NVDA", "nvidia",
        "Taiwan Semiconductor").
    threshold:
        Minimum fuzzy score (0-100) to accept a match.
    online_fallback:
        If True and no local match, try FMP /search.

    Returns
    -------
    ``ResolvedTicker`` on success, ``None`` if nothing matches.
    """
    if not query or not query.strip():
        return None

    q = query.strip()

    # 1. exact ticker / name from universe
    result = _exact_universe(q)
    if result is not None:
        return result

    # 2. alias table
    result = _alias_lookup(q)
    if result is not None:
        return result

    # 3. fuzzy match vs universe + aliases
    result = _fuzzy_match(q, threshold)
    if result is not None:
        return result

    # 4. FMP online search
    if online_fallback:
        result = _fmp_search(q)
        if result is not None:
            return result

    return None


def resolve_many(
    queries: list[str],
    *,
    threshold: int = 80,
    online_fallback: bool = True,
) -> dict[str, ResolvedTicker | None]:
    """Resolve multiple queries.  Returns ``{original_query: result}``."""
    return {q: resolve(q, threshold=threshold, online_fallback=online_fallback) for q in queries}


# ── strategy 1: exact universe match ────────────────────────────────────


def _load_universe_map() -> dict[str, tuple[str, str]]:
    """Return ``{TICKER: (ticker, name), lowercase_name: (ticker, name)}``."""
    from rewired.models.universe import load_universe

    uni = load_universe()
    mapping: dict[str, tuple[str, str]] = {}
    for s in uni.stocks:
        mapping[s.ticker.upper()] = (s.ticker, s.name)
        mapping[s.name.lower()] = (s.ticker, s.name)
    return mapping


def _exact_universe(query: str) -> ResolvedTicker | None:
    mapping = _load_universe_map()
    key = query.upper()
    if key in mapping:
        ticker, name = mapping[key]
        return ResolvedTicker(ticker=ticker, name=name, score=100.0, source="universe", in_universe=True)
    key = query.lower()
    if key in mapping:
        ticker, name = mapping[key]
        return ResolvedTicker(ticker=ticker, name=name, score=100.0, source="universe", in_universe=True)
    return None


# ── strategy 2: alias table ─────────────────────────────────────────────


def _alias_lookup(query: str) -> ResolvedTicker | None:
    key = query.lower().strip()
    ticker = _ALIASES.get(key)
    if ticker is None:
        return None

    # Look up the full name from universe
    mapping = _load_universe_map()
    entry = mapping.get(ticker.upper())
    name = entry[1] if entry else key.title()
    in_uni = entry is not None
    return ResolvedTicker(ticker=ticker, name=name, score=100.0, source="alias", in_universe=in_uni)


# ── strategy 3: fuzzy ───────────────────────────────────────────────────


def _build_candidates() -> list[tuple[str, str, str]]:
    """Return ``[(search_text, ticker, name)]`` for fuzzy matching."""
    from rewired.models.universe import load_universe

    uni = load_universe()
    candidates: list[tuple[str, str, str]] = []
    for s in uni.stocks:
        candidates.append((f"{s.ticker} {s.name}", s.ticker, s.name))
    for alias, ticker in _ALIASES.items():
        # Resolve name
        stock = uni.get_stock(ticker)
        name = stock.name if stock else alias.title()
        candidates.append((alias, ticker, name))
    return candidates


def _fuzzy_match(query: str, threshold: int) -> ResolvedTicker | None:
    try:
        from rapidfuzz import fuzz  # type: ignore[import-untyped]
    except ImportError:
        return None  # rapidfuzz not installed — skip this strategy

    candidates = _build_candidates()
    best_score = 0.0
    best: tuple[str, str] | None = None

    for search_text, ticker, name in candidates:
        score = fuzz.token_set_ratio(query.lower(), search_text.lower())
        if score > best_score:
            best_score = score
            best = (ticker, name)

    if best is not None and best_score >= threshold:
        mapping = _load_universe_map()
        in_uni = best[0].upper() in mapping
        return ResolvedTicker(
            ticker=best[0],
            name=best[1],
            score=best_score,
            source="fuzzy",
            in_universe=in_uni,
        )
    return None


# ── strategy 4: FMP online search ───────────────────────────────────────


def _fmp_search(query: str) -> ResolvedTicker | None:
    try:
        from rewired.data.fmp import search_ticker
    except ImportError:
        return None

    results = search_ticker(query, limit=3)
    if not results:
        return None

    top = results[0]
    ticker = top.get("symbol", "")
    name = top.get("name", "")
    if not ticker:
        return None

    mapping = _load_universe_map()
    in_uni = ticker.upper() in mapping

    return ResolvedTicker(
        ticker=ticker,
        name=name,
        score=75.0,  # online match — lower confidence than local
        source="fmp",
        in_universe=in_uni,
        metadata={
            "currency": top.get("currency", ""),
            "exchange": top.get("stockExchange", ""),
        },
    )
