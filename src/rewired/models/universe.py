"""Universe models: Layer, Tier enums and Stock/Universe classes."""

from __future__ import annotations

import os
from datetime import datetime
from enum import IntEnum
from pathlib import Path

import yaml
from pydantic import BaseModel


class Layer(IntEnum):
    """L dimension - structural position in the AI value chain."""
    L1 = 1  # Physical Infrastructure
    L2 = 2  # Digital Infrastructure
    L3 = 3  # Core Intelligence
    L4 = 4  # Dynamic Residual (Applications)
    L5 = 5  # Frontier Exploration


LAYER_NAMES = {
    Layer.L1: "Physical Infra",
    Layer.L2: "Digital Infra",
    Layer.L3: "Core Intelligence",
    Layer.L4: "Applications",
    Layer.L5: "Frontier",
}


class Tier(IntEnum):
    """T dimension - conviction and time horizon."""
    T1 = 1  # Core holdings
    T2 = 2  # Growth engine
    T3 = 3  # Thematic allocation
    T4 = 4  # Speculation


TIER_NAMES = {
    Tier.T1: "T1 Core",
    Tier.T2: "T2 Growth",
    Tier.T3: "T3 Thematic",
    Tier.T4: "T4 Speculation",
}


class Stock(BaseModel):
    """A single stock in the universe."""
    ticker: str
    name: str
    layer: Layer
    tier: Tier
    max_weight_pct: float
    notes: str = ""
    last_tier_change: datetime | None = None


class Universe(BaseModel):
    """The full stock universe organized as an LxT matrix."""
    stocks: list[Stock]

    def get_by_coordinate(self, layer: Layer, tier: Tier) -> list[Stock]:
        return [s for s in self.stocks if s.layer == layer and s.tier == tier]

    def get_by_layer(self, layer: Layer) -> list[Stock]:
        return [s for s in self.stocks if s.layer == layer]

    def get_by_tier(self, tier: Tier) -> list[Stock]:
        return [s for s in self.stocks if s.tier == tier]

    def get_stock(self, ticker: str) -> Stock | None:
        for s in self.stocks:
            if s.ticker == ticker:
                return s
        return None

    @property
    def tickers(self) -> list[str]:
        return [s.ticker for s in self.stocks]


def _config_dir() -> Path:
    """Return the config directory path."""
    from rewired import get_config_dir
    return get_config_dir()


def load_universe(config_path: Path | None = None) -> Universe:
    """Load the stock universe from YAML config."""
    if config_path is None:
        config_path = _config_dir() / "universe.yaml"

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    stocks = []
    for entry in raw["stocks"]:
        layer = Layer[entry["layer"]]
        tier = Tier[entry["tier"]]
        last_tc = None
        if entry.get("last_tier_change"):
            try:
                last_tc = datetime.fromisoformat(str(entry["last_tier_change"]))
            except (ValueError, TypeError):
                pass
        stocks.append(Stock(
            ticker=entry["ticker"],
            name=entry["name"],
            layer=layer,
            tier=tier,
            max_weight_pct=entry["max_weight_pct"],
            notes=entry.get("notes", ""),
            last_tier_change=last_tc,
        ))

    return Universe(stocks=stocks)


def save_universe(universe: Universe, config_path: Path | None = None) -> None:
    """Write the stock universe back to the YAML config file."""
    if config_path is None:
        config_path = _config_dir() / "universe.yaml"

    entries = []
    for s in universe.stocks:
        entry: dict = {
            "ticker": s.ticker,
            "name": s.name,
            "layer": f"L{s.layer.value}",
            "tier": f"T{s.tier.value}",
            "max_weight_pct": float(s.max_weight_pct),
        }
        if s.notes:
            entry["notes"] = s.notes
        if s.last_tier_change:
            entry["last_tier_change"] = s.last_tier_change.isoformat()
        entries.append(entry)

    with open(config_path, "w", encoding="utf-8") as f:
        f.write("# Rewired Index Stock Universe\n")
        f.write("# Each stock has a Layer (L1-L5) and Tier (T1-T4) coordinate\n\n")
        yaml.dump(
            {"stocks": entries},
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


# ── Automated onboarding ─────────────────────────────────────────────────


def onboard_ticker(ticker: str) -> Stock:
    """Onboard a new ticker into the universe automatically.

    1. Validate via FMP profile (404/null → ValueError).
    2. Duplicate check against current universe.
    3. Classify via Gemini COMPANY_CLASSIFY prompt (fallback to L4/T3).
    4. Persist to universe.yaml.

    Returns the fully-constructed ``Stock``.  Raises ``ValueError`` on
    invalid ticker or duplicate.
    """
    import json as _json
    import logging

    from rewired.data.fmp import get_profile, get_quote

    logger = logging.getLogger(__name__)

    raw_input = (ticker or "").strip()
    requested_ticker = raw_input.upper()
    if not requested_ticker:
        raise ValueError("Ticker must not be empty.")

    # ── Step 1: Duplicate check (before FMP calls) ──────────────────
    uni = load_universe()
    if uni.get_stock(requested_ticker) is not None:
        raise ValueError(f"'{requested_ticker}' is already in the universe.")

    # ── Step 2: FMP profile hydration ────────────────────────────────
    # Strategy: try the literal ticker first.  Only if that returns
    # nothing, use resolver + FMP search to build alternative candidates
    # and probe them.  This avoids "correcting" valid tickers (e.g.
    # NFLX) into unrelated fuzzy matches (e.g. NFLY).
    profile = get_profile(requested_ticker)
    ticker = requested_ticker
    unique_candidates: list[str] = []  # track all attempted tickers

    if not profile:
        # Literal ticker has no FMP profile — build candidates.
        candidates: list[str] = []

        # a) Resolver (alias/fuzzy/FMP text search)
        try:
            from rewired.data.ticker_resolver import resolve as resolve_ticker

            resolved = resolve_ticker(raw_input, threshold=65, online_fallback=True)
            if resolved is not None and resolved.ticker:
                candidates.append(resolved.ticker.upper())
        except Exception:
            pass

        # b) FMP /search-name expansion
        try:
            from rewired.data.fmp import search_ticker

            for item in search_ticker(raw_input, limit=5):
                symbol = (item.get("symbol") or "").strip().upper()
                if symbol:
                    candidates.append(symbol)
        except Exception:
            pass

        # Deduplicate, exclude already-tried ticker
        seen: set[str] = {requested_ticker}
        unique_candidates: list[str] = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                unique_candidates.append(c)

        # Probe profiles in candidate order
        for candidate in unique_candidates:
            # Check universe duplicate for each candidate
            if uni.get_stock(candidate) is not None:
                raise ValueError(f"'{candidate}' is already in the universe (input '{requested_ticker}' resolved to '{candidate}').")
            profile = get_profile(candidate)
            if profile:
                ticker = candidate
                break

    if not profile:
        all_tried = [requested_ticker] + (unique_candidates[:4] if unique_candidates else [])
        raise ValueError(
            f"Invalid ticker: no FMP profile found for '{requested_ticker}' "
            f"(tried: {', '.join(all_tried)})."
        )

    company_name = profile.get("companyName", ticker)
    sector = profile.get("sector", "Unknown")
    industry = profile.get("industry", "Unknown")
    market_cap = profile.get("mktCap", 0)
    description = (profile.get("description") or "")[:500]

    # Optional: validate price exists
    quote = get_quote(ticker)
    if not quote:
        logger.warning("No live quote for %s — proceeding with classification.", ticker)

    # ── Step 3: Agentic classification ───────────────────────────────
    layer = Layer.L4
    tier = Tier.T3
    max_weight = 5.0
    notes = ""

    try:
        from rewired.agent.gemini import generate, is_configured as gemini_configured
        from rewired.agent.prompts import COMPANY_CLASSIFY, SYSTEM_CLASSIFIER

        if gemini_configured():
            fmt_cap = f"${market_cap / 1e9:.1f}B" if market_cap and market_cap > 0 else "N/A"
            prompt = COMPANY_CLASSIFY.format(
                ticker=ticker,
                name=company_name,
                sector=sector,
                industry=industry,
                market_cap=fmt_cap,
                description=description,
            )
            raw = generate(
                prompt,
                system_instruction=SYSTEM_CLASSIFIER,
                json_output=True,
                max_retries=2,
            )
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()
            if text.startswith("json"):
                text = text[4:].strip()

            data = _json.loads(text)
            layer_str = str(data.get("layer", "L4")).upper().strip()
            tier_str = str(data.get("tier", "T3")).upper().strip()
            layer = Layer[layer_str] if layer_str in Layer.__members__ else Layer.L4
            tier = Tier[tier_str] if tier_str in Tier.__members__ else Tier.T3
            raw_weight = data.get("max_weight_pct", 5.0)
            max_weight = max(1.0, min(15.0, float(raw_weight)))
            reasoning = str(data.get("reasoning", ""))[:200]
            if reasoning:
                notes = f"Auto-classified: {reasoning}"
        else:
            notes = "\u26a0 DEFAULTED: Gemini unavailable \u2014 defensive defaults (L4/T3/5%)."
    except Exception as exc:
        logger.warning("Gemini classification failed for %s: %s", ticker, exc)
        notes = f"\u26a0 DEFAULTED: Gemini error \u2014 defensive defaults ({exc})"

    if ticker != requested_ticker:
        prefix = f"Resolved from input '{requested_ticker}' to '{ticker}'."
        notes = f"{prefix} {notes}".strip()

    # ── Step 4: Persist ──────────────────────────────────────────────
    stock = Stock(
        ticker=ticker,
        name=company_name,
        layer=layer,
        tier=tier,
        max_weight_pct=max_weight,
        notes=notes,
    )
    uni.stocks.append(stock)
    save_universe(uni)
    return stock
