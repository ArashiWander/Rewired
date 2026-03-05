"""Universe models: Layer, Tier enums and Stock/Universe classes."""

from __future__ import annotations

import os
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
        stocks.append(Stock(
            ticker=entry["ticker"],
            name=entry["name"],
            layer=layer,
            tier=tier,
            max_weight_pct=entry["max_weight_pct"],
            notes=entry.get("notes", ""),
        ))

    return Universe(stocks=stocks)
